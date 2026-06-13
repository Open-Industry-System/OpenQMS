"""Integration test for batch_validation_summaries endpoint.

Covers the critical bug: historical runs' occurrences must NOT leak into
the latest-run-only counts.  Tests three CP scenarios in one batch:
  1. CP with no validation runs → absent from summaries
  2. CP with a clean run (0 findings) → success badge data
  3. CP with two runs: run-1 has an open finding, run-2 resolves it
     and finds a new warning → only run-2 counts must appear
"""
import uuid
import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.api.cp_validation import batch_validation_summaries, ValidationSummariesRequest
from app.models.cp_validation import (
    CPValidationRun, CPValidationFinding, CPValidationOccurrence,
)
from app.models.control_plan import ControlPlan, ControlPlanItem


def _make_cp(suffix: str = "") -> ControlPlan:
    return ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-BATCH-{uuid.uuid4().hex[:8]}{suffix}",
        title=f"Batch test CP{suffix}",
        product_line_code="DC-DC-100",
    )


def _make_run(cp_id: uuid.UUID, user_id: uuid.UUID, started_at: datetime,
              status: str = "completed", rule_count: int = 0,
              error_count: int = 0, warning_count: int = 0, info_count: int = 0,
              trigger: str = "manual") -> CPValidationRun:
    return CPValidationRun(
        cp_id=cp_id,
        trigger=trigger,
        status=status,
        rule_count=rule_count,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=1),
        created_by=user_id,
    )


def _make_finding(cp_id: uuid.UUID, rule_id: str, severity: str,
                  category: str, status: str = "open") -> CPValidationFinding:
    return CPValidationFinding(
        cp_id=cp_id,
        finding_hash=f"hash-{rule_id}-{uuid.uuid4().hex[:6]}",
        rule_id=rule_id,
        severity=severity,
        category=category,
        status=status,
    )


def _make_occurrence(run_id: uuid.UUID, finding_id: uuid.UUID, cp_id: uuid.UUID,
                     title: str, present: bool = True) -> CPValidationOccurrence:
    return CPValidationOccurrence(
        run_id=run_id,
        finding_id=finding_id,
        cp_id=cp_id,
        validation_type="rule",
        title=title,
        description="test",
        present=present,
    )


@pytest.mark.asyncio
async def test_batch_summaries_no_runs_clean_and_history(db, admin_user):
    """Three CPs: no runs, clean run, two-run history with state change."""
    now = datetime.now(timezone.utc)
    uid = admin_user.user_id

    # ── CP-A: no validation runs at all ──
    cp_a = _make_cp("-A")
    db.add(cp_a)
    await db.flush()

    # ── CP-B: one clean run (0 findings) ──
    cp_b = _make_cp("-B")
    db.add(cp_b)
    await db.flush()

    run_b1 = _make_run(cp_b.cp_id, uid, now - timedelta(minutes=30),
                        rule_count=0, error_count=0, warning_count=0, info_count=0)
    db.add(run_b1)
    await db.flush()

    # ── CP-C: two runs with history ──
    #   Run 1: 1 error (R001) → finding F1 open
    #   Run 2: F1 resolved + 1 new warning (R002) → finding F2 open
    #   Expected: latest run shows open_count=1, resolved_count=1
    #   (NOT open_count=2 from leaking run-1's occurrence)
    cp_c = _make_cp("-C")
    db.add(cp_c)
    await db.flush()

    # Need an item for the CP so the engine would find issues (not strictly
    # needed for the batch endpoint test, but keeps the CP valid)
    item_c = ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp_c.cp_id, step_no="10",
        source_fmea_node_id="pfmea-step-1", control_method="",
    )
    db.add(item_c)
    await db.flush()

    # Run 1 (older)
    run_c1 = _make_run(cp_c.cp_id, uid, now - timedelta(hours=2),
                        rule_count=1, error_count=1)
    db.add(run_c1)
    await db.flush()

    finding_c1 = _make_finding(cp_c.cp_id, "R001", "error", "completeness", status="open")
    db.add(finding_c1)
    await db.flush()

    occ_c1_run1 = _make_occurrence(run_c1.run_id, finding_c1.finding_id, cp_c.cp_id,
                                    title="控制方法缺失")
    db.add(occ_c1_run1)
    await db.flush()

    # Run 2 (latest) — F1 is resolved, new finding F2 is open
    run_c2 = _make_run(cp_c.cp_id, uid, now - timedelta(hours=1),
                        rule_count=2, error_count=0, warning_count=1)
    db.add(run_c2)
    await db.flush()

    # Mark F1 as resolved (user action between runs)
    finding_c1.status = "resolved"
    await db.flush()

    # Occurrence for F1 in run 2 (present=True because it was detected —
    # but the finding is now resolved, so it contributes to resolved_count)
    occ_c1_run2 = _make_occurrence(run_c2.run_id, finding_c1.finding_id, cp_c.cp_id,
                                    title="控制方法缺失")
    db.add(occ_c1_run2)

    # New finding F2 (warning) in run 2
    finding_c2 = _make_finding(cp_c.cp_id, "R002", "warning", "completeness", status="open")
    db.add(finding_c2)
    await db.flush()

    occ_c2_run2 = _make_occurrence(run_c2.run_id, finding_c2.finding_id, cp_c.cp_id,
                                    title="反应计划缺失")
    db.add(occ_c2_run2)
    await db.flush()

    # ── Call the batch endpoint ──
    from app.core.deps import RequestScope
    from app.core.factory_scope import FactoryScope, ProductLineScope
    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=admin_user.factory_id),
        effective_factory_id=admin_user.factory_id,
        pl_scope=ProductLineScope(mode="ALL", codes=["DC-DC-100"]),
        user=admin_user,
    )
    req = ValidationSummariesRequest(cp_ids=[cp_a.cp_id, cp_b.cp_id, cp_c.cp_id])
    resp = await batch_validation_summaries(req, db, scope)
    summaries = resp.summaries

    # CP-A: no runs → absent from summaries
    assert str(cp_a.cp_id) not in summaries

    # CP-B: clean run → 0 errors, 0 warnings, success
    sum_b = summaries[str(cp_b.cp_id)]
    assert sum_b.error_count == 0
    assert sum_b.warning_count == 0
    assert sum_b.run_id == run_b1.run_id

    # CP-C: latest run only → open_count=1 (F2), resolved_count=1 (F1)
    # The critical assertion: run-1's occurrence of F1 must NOT leak
    sum_c = summaries[str(cp_c.cp_id)]
    assert sum_c.run_id == run_c2.run_id, "Should use latest run"
    assert sum_c.open_count == 1, f"Expected open=1 (F2 only), got {sum_c.open_count}"
    assert sum_c.resolved_count == 1, f"Expected resolved=1 (F1), got {sum_c.resolved_count}"
    assert sum_c.rejected_count == 0
    assert sum_c.warning_count == 1


@pytest.mark.asyncio
async def test_batch_summaries_rejected_finding_not_leaked(db, admin_user):
    """A finding rejected in run-2 must not have its run-1 open occurrence counted."""
    now = datetime.now(timezone.utc)
    uid = admin_user.user_id

    cp = _make_cp("-R")
    db.add(cp)
    await db.flush()

    # Run 1: finding F1 open
    run1 = _make_run(cp.cp_id, uid, now - timedelta(hours=1),
                     rule_count=1, error_count=1)
    db.add(run1)
    await db.flush()

    f1 = _make_finding(cp.cp_id, "R001", "error", "completeness", status="open")
    db.add(f1)
    await db.flush()

    occ1 = _make_occurrence(run1.run_id, f1.finding_id, cp.cp_id, title="控制方法缺失")
    db.add(occ1)
    await db.flush()

    # Run 2: F1 rejected
    run2 = _make_run(cp.cp_id, uid, now, rule_count=1, error_count=0)
    db.add(run2)
    await db.flush()

    f1.status = "rejected"
    await db.flush()

    occ2 = _make_occurrence(run2.run_id, f1.finding_id, cp.cp_id, title="控制方法缺失")
    db.add(occ2)
    await db.flush()

    from app.core.deps import RequestScope
    from app.core.factory_scope import FactoryScope, ProductLineScope
    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=admin_user.factory_id),
        effective_factory_id=admin_user.factory_id,
        pl_scope=ProductLineScope(mode="ALL", codes=["DC-DC-100"]),
        user=admin_user,
    )
    req = ValidationSummariesRequest(cp_ids=[cp.cp_id])
    resp = await batch_validation_summaries(req, db, scope)
    sum_cp = resp.summaries[str(cp.cp_id)]

    assert sum_cp.run_id == run2.run_id
    assert sum_cp.rejected_count == 1, f"Expected rejected=1, got {sum_cp.rejected_count}"
    assert sum_cp.open_count == 0, f"Expected open=0 (no leak from run-1), got {sum_cp.open_count}"
