"""Tests for capa_doc_gate_service.run_audit (US-E2E-01.7 Task 3)."""
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from app.services import capa_doc_gate_service
from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgAudit, CapaDocgDecision


@pytest.mark.asyncio
async def test_run_audit_passed_when_bump_and_covered(db, capa_with_done_analysis_and_bumped_doc):
    """baseline→version_after diff covers all key_points -> all passed -> decision=passed."""
    capa, user = capa_with_done_analysis_and_bumped_doc
    result = await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    assert result["decision"] == "passed"


@pytest.mark.asyncio
async def test_run_audit_pending_when_no_new_version(db, capa_with_done_analysis_no_bump):
    capa, user = capa_with_done_analysis_no_bump
    result = await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    assert result["decision"] == "blocked"


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
    await capa_doc_gate_service.run_audit(db, capa, user.user_id)
    audits = (await db.execute(select(CapaDocgAudit))).scalars().all()
    assert len(audits) >= 1
    decisions = (await db.execute(select(CapaDocgDecision))).scalars().all()
    assert len(decisions) == 1
    assert decisions[0].revision == 0
