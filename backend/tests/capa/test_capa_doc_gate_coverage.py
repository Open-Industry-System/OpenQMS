"""Tests for capa_doc_gate_service.run_audit (US-E2E-01.7 Task 3)."""
import pytest
from sqlalchemy import select

from app.services import capa_doc_gate_service
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgAudit, CapaDocgDecision


@pytest.mark.asyncio
async def test_empty_affected_docs_run_audit_raises(db, capa_with_empty_done_analysis):
    """Empty affected_docs -> run_audit raises (must use confirm_no_affected)."""
    capa, user = capa_with_empty_done_analysis
    with pytest.raises(ValueError, match="空影响清单须人工确认"):
        await capa_doc_gate_service.run_audit(db, capa, user.user_id)


@pytest.mark.asyncio
async def test_run_audit_inserts_audit_and_decision_rows(db, capa_with_done_analysis_and_bumped_doc):
    """run_audit inserts CapaDocgAudit rows + a CapaDocgDecision row with revision."""
    capa, user = capa_with_done_analysis_and_bumped_doc
    result = await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    assert result["decision"] == "passed"
    own_analyses = select(CapaDocgAnalysis.analysis_id).where(CapaDocgAnalysis.capa_id == capa.report_id)
    audits = (await db.execute(select(CapaDocgAudit).where(CapaDocgAudit.analysis_id.in_(own_analyses)))).scalars().all()
    assert len(audits) >= 1
    decisions = (await db.execute(select(CapaDocgDecision).where(CapaDocgDecision.analysis_id.in_(own_analyses)))).scalars().all()
    assert len(decisions) == 1
    assert decisions[0].revision == 0
    assert decisions[0].decision == "passed"
