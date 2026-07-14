"""Tests for capa_doc_gate_service.generate_impact_analysis (US-E2E-01.7)."""
import uuid
import pytest
from sqlalchemy import select
from unittest.mock import AsyncMock

from app.services import capa_doc_gate_service
from app.models.capa_doc_gate import CapaDocgAnalysis


@pytest.mark.asyncio
async def test_generate_impact_analysis_blocked_when_no_llm(db, capa_d8_gate, docg_no_creds):
    """No LLM credentials -> status='failed'+blocked, is_current not set, raises BLOCKED."""
    capa, user = capa_d8_gate
    with pytest.raises(ValueError, match="BLOCKED"):
        await capa_doc_gate_service.generate_impact_analysis(db, capa, user.user_id)
    latest = await db.scalar(
        select(CapaDocgAnalysis).order_by(CapaDocgAnalysis.created_at.desc())
    )
    assert latest.status == "failed"
    assert latest.is_current is False
    assert latest.llm_available is False
    assert latest.completed_at is not None


@pytest.mark.asyncio
async def test_generate_impact_analysis_done_success(db, capa_d8_gate_with_docs, docg_llm_mock):
    """LLM returns valid affected_docs -> status='done', is_current=true, analysis_input_hash set."""
    capa, user = capa_d8_gate_with_docs
    docg_llm_mock.return_value = {
        "affected_docs": [
            {
                "doc_id": str(capa.fmea_ref_id),
                "key_points": [
                    {
                        "target_kind": "fmea_node",
                        "expected_action": "modify",
                        "field": "prevention_control",
                        "target_key": "node-1",
                    }
                ],
                "update_suggestion": "建议更新预防控制",
            }
        ]
    }
    result = await capa_doc_gate_service.generate_impact_analysis(db, capa, user.user_id)
    assert result["status"] == "done"
    analysis = await db.scalar(
        select(CapaDocgAnalysis).where(CapaDocgAnalysis.is_current == True)
    )
    assert analysis.status == "done"
    assert analysis.affected_docs is not None and len(analysis.affected_docs) > 0
    assert analysis.analysis_input_hash is not None
    assert analysis.llm_available is True


@pytest.mark.asyncio
async def test_generate_rejects_empty_key_points(db, capa_d8_gate_with_docs, docg_llm_mock):
    """LLM returns doc with empty key_points -> status='failed' (vacuous pass prevention)."""
    capa, user = capa_d8_gate_with_docs
    docg_llm_mock.return_value = {
        "affected_docs": [
            {
                "doc_id": str(capa.fmea_ref_id),
                "key_points": [],
                "update_suggestion": "建议",
            }
        ]
    }
    result = await capa_doc_gate_service.generate_impact_analysis(db, capa, user.user_id)
    assert result["status"] == "failed"
    analysis = await db.scalar(
        select(CapaDocgAnalysis).where(CapaDocgAnalysis.status == "failed")
    )
    assert "key_points" in (analysis.error or "")


@pytest.mark.asyncio
async def test_record_defer_inserts_deferred_decision(db, capa_with_done_analysis_no_bump):
    """record_defer on a blocked decision -> inserts deferred decision (still blocks gate)."""
    from app.models.capa_doc_gate import CapaDocgDecision
    capa, user = capa_with_done_analysis_no_bump
    # First run_audit to get a blocked decision (no bump)
    await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    result = await capa_doc_gate_service.record_defer(
        db, capa, "等待 SOP 更新", user.user_id, "2026-08-01", user.user_id
    )
    assert result["decision"] == "deferred"
    from sqlalchemy import select
    decisions = (await db.execute(select(CapaDocgDecision).order_by(CapaDocgDecision.revision.desc()))).scalars().all()
    assert decisions[0].decision == "deferred"
    assert decisions[0].defer_reason == "等待 SOP 更新"


@pytest.mark.asyncio
async def test_record_defer_owner_not_in_factory_raises(db, capa_with_done_analysis_no_bump, viewer_user):
    """defer_owner belonging to a different factory -> raise."""
    capa, user = capa_with_done_analysis_no_bump
    # viewer_user has a different factory (NULL or other) — use admin_user which has factory_id set
    from app.models.user import User
    # Create an owner in a different factory
    from app.models.factory import Factory
    other_factory = Factory(id=uuid.uuid4(), code="FAC-OTHER", name="Other", is_active=True)
    db.add(other_factory)
    await db.flush()
    other_user = User(
        user_id=uuid.uuid4(), username="other_owner", display_name="Other",
        email="o@e.com", password_hash="h", role_id=user.role_id,
        legacy_role="quality_engineer", is_active=True, factory_id=other_factory.id,
    )
    db.add(other_user)
    await db.flush()
    with pytest.raises(ValueError, match="owner"):
        await capa_doc_gate_service.record_defer(
            db, capa, "r", other_user.user_id, "2026-08-01", user.user_id
        )


@pytest.mark.asyncio
async def test_confirm_no_affected_passes_empty_list(db, capa_with_empty_done_analysis):
    """Empty affected_docs + confirm_no_affected -> decision=passed, no_affected_confirmed=True."""
    from app.models.capa_doc_gate import CapaDocgDecision
    from sqlalchemy import select
    capa, user = capa_with_empty_done_analysis
    result = await capa_doc_gate_service.confirm_no_affected(db, capa, user.user_id)
    assert result["decision"] == "passed"
    assert result["no_affected_confirmed"] is True
    dec = (await db.execute(select(CapaDocgDecision))).scalar_one()
    assert dec.no_affected_confirmed is True


@pytest.mark.asyncio
async def test_confirm_no_affected_rejects_non_empty(db, capa_with_done_analysis_no_bump):
    """confirm_no_affected on a non-empty affected_docs -> raise."""
    capa, user = capa_with_done_analysis_no_bump
    with pytest.raises(ValueError, match="仅空清单可确认"):
        await capa_doc_gate_service.confirm_no_affected(db, capa, user.user_id)


@pytest.mark.asyncio
async def test_get_latest_analysis_returns_failed(db, capa_d8_gate):
    """get_latest_analysis returns the latest analysis incl failed status."""
    capa, user = capa_d8_gate
    # No analysis yet
    assert await capa_doc_gate_service.get_latest_analysis(db, capa) is None
    # Insert a failed analysis (not is_current)
    from datetime import datetime, timezone
    failed = CapaDocgAnalysis(
        analysis_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=capa.factory_id,
        is_current=False, status="failed", error="LLM 未配置", llm_available=False,
        completed_at=datetime.now(timezone.utc),
        generated_by=user.user_id,
    )
    db.add(failed)
    await db.flush()
    result = await capa_doc_gate_service.get_latest_analysis(db, capa)
    assert result is not None
    assert result["status"] == "failed"
    assert result["is_current"] is False
    assert result["error"] == "LLM 未配置"
