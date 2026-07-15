"""API + gate tests for US-E2E-01.7 D8 doc update gate (Task 5)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgDecision
from app.schemas.capa import AdvanceRequest
from app.services import capa_doc_gate_service, capa_service
from app.state_machines.eightd_state import EightDState

pytestmark = pytest.mark.requires_db


# ---------------------------------------------------------------------------
# Service-level gate tests (reuse doc-gate fixtures)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_d8_gate_blocks_when_no_analysis(db, capa_d8_gate):
    """advance D8_GATE_PENDING->D8_APPROVAL_PENDING with no analysis -> raise."""
    capa, user = capa_d8_gate
    with pytest.raises(ValueError, match="影响分析"):
        await capa_service.advance_capa(
            db, capa, user.user_id,
            AdvanceRequest(target_state=EightDState.D8_APPROVAL_PENDING),
        )


@pytest.mark.asyncio
async def test_d8_gate_blocks_when_decision_blocked(db, capa_with_done_analysis_no_bump):
    """run_audit → blocked decision → advance raises."""
    capa, user = capa_with_done_analysis_no_bump
    result = await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    assert result["decision"] == "blocked"
    with pytest.raises(ValueError, match="文档门禁未通过"):
        await capa_service.advance_capa(
            db, capa, user.user_id,
            AdvanceRequest(target_state=EightDState.D8_APPROVAL_PENDING),
        )


@pytest.mark.asyncio
async def test_d8_gate_blocks_when_deferred(db, capa_with_done_analysis_no_bump):
    """deferred decision still blocks advance."""
    capa, user = capa_with_done_analysis_no_bump
    await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    await capa_doc_gate_service.record_defer(
        db, capa, "等待更新", user.user_id, "2026-08-01", user.user_id
    )
    with pytest.raises(ValueError, match="文档门禁未通过"):
        await capa_service.advance_capa(
            db, capa, user.user_id,
            AdvanceRequest(target_state=EightDState.D8_APPROVAL_PENDING),
        )


@pytest.mark.asyncio
async def test_d8_gate_passes_when_decision_passed(db, capa_with_empty_done_analysis):
    """confirm_no_affected → passed → advance to D8_APPROVAL_PENDING."""
    capa, user = capa_with_empty_done_analysis
    result = await capa_doc_gate_service.confirm_no_affected(db, capa, user.user_id)
    assert result["decision"] == "passed"
    advanced = await capa_service.advance_capa(
        db, capa, user.user_id,
        AdvanceRequest(target_state=EightDState.D8_APPROVAL_PENDING),
    )
    assert advanced.status == EightDState.D8_APPROVAL_PENDING.value


@pytest.mark.asyncio
async def test_d8_gate_passes_when_audit_passed(db, capa_with_done_analysis_and_bumped_doc):
    """run_audit with bump+coverage → passed → advance succeeds."""
    capa, user = capa_with_done_analysis_and_bumped_doc
    result = await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    assert result["decision"] == "passed"
    advanced = await capa_service.advance_capa(
        db, capa, user.user_id,
        AdvanceRequest(target_state=EightDState.D8_APPROVAL_PENDING),
    )
    assert advanced.status == EightDState.D8_APPROVAL_PENDING.value


# ---------------------------------------------------------------------------
# HTTP API tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_advance_blocks_without_analysis(admin_client, capa_d8_gate):
    capa, _ = capa_d8_gate
    resp = await admin_client.post(
        f"/api/capa/{capa.report_id}/advance",
        json={"target_state": "D8_APPROVAL_PENDING"},
    )
    assert resp.status_code == 400
    assert "影响分析" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_advance_passes_after_confirm(admin_client, capa_with_empty_done_analysis):
    capa, _ = capa_with_empty_done_analysis
    conf = await admin_client.post(
        f"/api/capa/{capa.report_id}/doc-gate/confirm-no-affected"
    )
    assert conf.status_code == 200
    assert conf.json()["decision"] == "passed"
    resp = await admin_client.post(
        f"/api/capa/{capa.report_id}/advance",
        json={"target_state": "D8_APPROVAL_PENDING"},
    )
    assert resp.status_code == 200
    assert resp.json()["capa"]["status"] == "D8_APPROVAL_PENDING"


@pytest.mark.asyncio
async def test_api_get_impact_404_when_none(admin_client, capa_d8_gate):
    capa, _ = capa_d8_gate
    resp = await admin_client.get(f"/api/capa/{capa.report_id}/doc-gate/impact")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_impact_blocked_no_llm(admin_client, capa_d8_gate, docg_no_creds):
    capa, _ = capa_d8_gate
    resp = await admin_client.post(f"/api/capa/{capa.report_id}/doc-gate/impact")
    assert resp.status_code == 422
    body = resp.json()["detail"]
    assert body["blocked"] is True


@pytest.mark.asyncio
async def test_api_get_impact_returns_failed(admin_client, capa_d8_gate, docg_no_creds):
    capa, _ = capa_d8_gate
    await admin_client.post(f"/api/capa/{capa.report_id}/doc-gate/impact")
    resp = await admin_client.get(f"/api/capa/{capa.report_id}/doc-gate/impact")
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    assert resp.json()["is_current"] is False


@pytest.mark.asyncio
async def test_api_audit_and_decision(admin_client, capa_with_done_analysis_no_bump):
    capa, _ = capa_with_done_analysis_no_bump
    resp = await admin_client.post(f"/api/capa/{capa.report_id}/doc-gate/audit")
    assert resp.status_code == 200
    assert resp.json()["decision"] == "blocked"
    get_audit = await admin_client.get(f"/api/capa/{capa.report_id}/doc-gate/audit")
    assert get_audit.status_code == 200
    assert get_audit.json()["audit_run_id"] is not None
    assert len(get_audit.json()["audits"]) >= 1
    dec = await admin_client.get(f"/api/capa/{capa.report_id}/doc-gate/decision")
    assert dec.status_code == 200
    assert dec.json()["decision"] == "blocked"


@pytest.mark.asyncio
async def test_api_defer(admin_client, capa_with_done_analysis_no_bump, db):
    capa, user = capa_with_done_analysis_no_bump
    await admin_client.post(f"/api/capa/{capa.report_id}/doc-gate/audit")
    resp = await admin_client.post(
        f"/api/capa/{capa.report_id}/doc-gate/defer",
        json={
            "reason": "等待 SOP",
            "owner_id": str(user.user_id),
            "deadline": "2026-08-15",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["decision"] == "deferred"
    dec = await admin_client.get(f"/api/capa/{capa.report_id}/doc-gate/decision")
    assert dec.json()["decision"] == "deferred"
    assert dec.json()["defer_reason"] == "等待 SOP"


@pytest.mark.asyncio
async def test_api_confirm_rejects_non_empty(admin_client, capa_with_done_analysis_no_bump):
    capa, _ = capa_with_done_analysis_no_bump
    resp = await admin_client.post(
        f"/api/capa/{capa.report_id}/doc-gate/confirm-no-affected"
    )
    assert resp.status_code == 400
    assert "空清单" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_wrong_stage_rejected(admin_client, db, admin_user, default_factory):
    """POST impact on non-D8_GATE_PENDING capa → 400."""
    from app.models.capa import CAPAEightD
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no="CAPA-DOCG-STAGE", title="t",
        product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="D7_PREVENTION", severity="serious",
        created_by=admin_user.user_id,
    )
    db.add(capa)
    await db.flush()
    resp = await admin_client.post(f"/api/capa/{capa.report_id}/doc-gate/impact")
    assert resp.status_code == 400
    assert "D8_GATE_PENDING" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_waiver_rejects_plain_no_bump(admin_client, capa_with_done_analysis_no_bump):
    """Ordinary pending_update (no bump) cannot be waived — only blocked_modify."""
    capa, _ = capa_with_done_analysis_no_bump
    await admin_client.post(f"/api/capa/{capa.report_id}/doc-gate/audit")
    # Even with a fabricated item, server rejects because no uncovered CP modify exists
    resp = await admin_client.post(
        f"/api/capa/{capa.report_id}/doc-gate/waiver",
        json={
            "reason": "try to bypass no-bump",
            "items": [{
                "doc_type": "control_plan",
                "doc_id": str(uuid.uuid4()),
                "target_key": "x",
                "field": "control_method",
            }],
        },
    )
    assert resp.status_code == 400
    # advance must still be blocked
    adv = await admin_client.post(
        f"/api/capa/{capa.report_id}/advance",
        json={"target_state": "D8_APPROVAL_PENDING"},
    )
    assert adv.status_code == 400


@pytest.mark.asyncio
async def test_api_waiver_passes_for_blocked_modify(admin_client, capa_with_cp_blocked_modify):
    """Structured waiver of exact CP blocked_modify → advance succeeds."""
    capa, _, cp, tk, field = capa_with_cp_blocked_modify
    await admin_client.post(f"/api/capa/{capa.report_id}/doc-gate/audit")
    resp = await admin_client.post(
        f"/api/capa/{capa.report_id}/doc-gate/waiver",
        json={
            "reason": "lineage break: delete+add intentional",
            "items": [{
                "doc_type": "control_plan",
                "doc_id": str(cp.cp_id),
                "target_key": tk,
                "field": field,
            }],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "passed"
    assert body["waiver_items"]
    assert body["waiver_items"][0]["target_key"] == tk
    adv = await admin_client.post(
        f"/api/capa/{capa.report_id}/advance",
        json={"target_state": "D8_APPROVAL_PENDING"},
    )
    assert adv.status_code == 200, adv.text


@pytest.mark.asyncio
async def test_api_waiver_rejects_without_audit(admin_client, capa_with_cp_blocked_modify):
    """Waiver before running audit → 400."""
    capa, _, cp, tk, field = capa_with_cp_blocked_modify
    resp = await admin_client.post(
        f"/api/capa/{capa.report_id}/doc-gate/waiver",
        json={
            "reason": "jumping the gun",
            "items": [{
                "doc_type": "control_plan",
                "doc_id": str(cp.cp_id),
                "target_key": tk,
                "field": field,
            }],
        },
    )
    assert resp.status_code == 400
    assert "请先运行文档审核" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_waiver_rejects_missing_reason(admin_client, capa_with_cp_blocked_modify):
    capa, _, cp, tk, field = capa_with_cp_blocked_modify
    await admin_client.post(f"/api/capa/{capa.report_id}/doc-gate/audit")
    resp = await admin_client.post(
        f"/api/capa/{capa.report_id}/doc-gate/waiver",
        json={
            "reason": "   ",
            "items": [{
                "doc_type": "control_plan",
                "doc_id": str(cp.cp_id),
                "target_key": tk,
                "field": field,
            }],
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_waiver_rejects_on_deferred(admin_client, capa_with_cp_blocked_modify):
    """waiver on a deferred analysis → 400 (only blocked can be waived)."""
    capa, user, cp, tk, field = capa_with_cp_blocked_modify
    await admin_client.post(f"/api/capa/{capa.report_id}/doc-gate/audit")
    await admin_client.post(
        f"/api/capa/{capa.report_id}/doc-gate/defer",
        json={"reason": "等待更新", "owner_id": str(user.user_id), "deadline": "2026-08-01"},
    )
    resp = await admin_client.post(
        f"/api/capa/{capa.report_id}/doc-gate/waiver",
        json={
            "reason": "try to waiver deferred",
            "items": [{
                "doc_type": "control_plan",
                "doc_id": str(cp.cp_id),
                "target_key": tk,
                "field": field,
            }],
        },
    )
    assert resp.status_code == 400
    assert "deferred" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_decision_includes_waiver_items(admin_client, capa_with_cp_blocked_modify):
    capa, _, cp, tk, field = capa_with_cp_blocked_modify
    await admin_client.post(f"/api/capa/{capa.report_id}/doc-gate/audit")
    await admin_client.post(
        f"/api/capa/{capa.report_id}/doc-gate/waiver",
        json={
            "reason": "accepted break",
            "items": [{
                "doc_type": "control_plan",
                "doc_id": str(cp.cp_id),
                "target_key": tk,
                "field": field,
            }],
        },
    )
    dec = await admin_client.get(f"/api/capa/{capa.report_id}/doc-gate/decision")
    body = dec.json()
    assert body["decision"] == "passed"
    assert body["waiver_reason"] == "accepted break"
    assert body["waiver_items"]
    assert body["waiver_items"][0]["target_key"] == tk
    assert body["waiver_items"][0]["field"] == field


@pytest.mark.asyncio
async def test_api_waiver_rejects_missing_items(admin_client, capa_with_cp_blocked_modify):
    """items required by schema — empty list rejected with 422."""
    capa, _, _, _, _ = capa_with_cp_blocked_modify
    await admin_client.post(f"/api/capa/{capa.report_id}/doc-gate/audit")
    resp = await admin_client.post(
        f"/api/capa/{capa.report_id}/doc-gate/waiver",
        json={"reason": "no items", "items": []},
    )
    assert resp.status_code == 422
