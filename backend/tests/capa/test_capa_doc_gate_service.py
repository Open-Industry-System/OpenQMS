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
