"""Unit tests for CPValidationEngine orchestrator (two-table model)."""
import uuid
import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import select, func

from app.services.cp_validation.engine import CPValidationEngine, ValidationAlreadyRunning
from app.models.cp_validation import (
    CPValidationRun, CPValidationFinding, CPValidationOccurrence,
)
from app.models.control_plan import ControlPlan, ControlPlanItem


def _make_cp(factory_id: uuid.UUID | None = None):
    return ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-TEST-{uuid.uuid4().hex[:8]}",
        title="Test CP",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
    )


@pytest.mark.asyncio
async def test_validate_creates_run_and_occurrences(db, admin_user):
    cp = _make_cp(factory_id=admin_user.factory_id)
    db.add(cp)
    await db.flush()

    item = ControlPlanItem(
        item_id=uuid.uuid4(),
        cp_id=cp.cp_id,
        step_no="10",
        process_name="焊接",
        source_fmea_node_id="pfmea-step-1",
        control_method="",
        reaction_plan="",
        factory_id=admin_user.factory_id,
    )
    db.add(item)
    await db.flush()

    engine = CPValidationEngine()
    run = await engine.validate(db, cp.cp_id, admin_user.user_id, trigger="manual")

    assert run.status == "completed"
    assert run.error_count >= 2
    assert run.failed_rules == []

    result = await db.execute(
        select(CPValidationOccurrence).where(CPValidationOccurrence.run_id == run.run_id)
    )
    occurrences = result.scalars().all()
    assert len(occurrences) >= 2
    assert all(o.present for o in occurrences)

    result2 = await db.execute(
        select(CPValidationFinding).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    findings = result2.scalars().all()
    assert len(findings) >= 2
    assert all(f.status == "open" for f in findings)


@pytest.mark.asyncio
async def test_finding_reused_across_runs(db, admin_user):
    """Same finding_hash (from stable business key) creates one finding, two occurrences."""
    cp = _make_cp(factory_id=admin_user.factory_id)
    db.add(cp)
    await db.flush()

    item = ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10",
        source_fmea_node_id="pfmea-step-1", control_method="",
        factory_id=admin_user.factory_id,
    )
    db.add(item)
    await db.flush()

    engine = CPValidationEngine()
    run1 = await engine.validate(db, cp.cp_id, admin_user.user_id)

    result_f = await db.execute(
        select(func.count()).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    finding_count = result_f.scalar()

    # Second run with same data — stable_key unchanged so finding reused
    run2 = await engine.validate(db, cp.cp_id, admin_user.user_id)

    result_f2 = await db.execute(
        select(func.count()).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    assert result_f2.scalar() == finding_count  # no new findings

    result_o2 = await db.execute(
        select(func.count()).where(CPValidationOccurrence.run_id == run2.run_id)
    )
    assert result_o2.scalar() >= 1  # new occurrences for run2


@pytest.mark.asyncio
async def test_finding_survives_item_uuid_change(db, admin_user):
    """When update_control_plan deletes+recreates items with new UUIDs,
    the finding_hash (based on source_fmea_node_id) remains stable."""
    cp = _make_cp(factory_id=admin_user.factory_id)
    db.add(cp)
    await db.flush()

    # Run 1: item with UUID-A, source_fmea_node_id="pfmea-step-1"
    item1 = ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10",
        source_fmea_node_id="pfmea-step-1", control_method="",
        factory_id=admin_user.factory_id,
    )
    db.add(item1)
    await db.flush()

    engine = CPValidationEngine()
    run1 = await engine.validate(db, cp.cp_id, admin_user.user_id)

    result1 = await db.execute(
        select(CPValidationFinding).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    findings_before = result1.scalars().all()
    assert len(findings_before) >= 1

    # Simulate what update_control_plan does: delete old item, create new with new UUID
    await db.delete(item1)
    await db.flush()
    item2 = ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10",
        source_fmea_node_id="pfmea-step-1", control_method="",  # same business identity
        factory_id=admin_user.factory_id,
    )
    db.add(item2)
    await db.flush()

    # Run 2: new item UUID but same source_fmea_node_id
    run2 = await engine.validate(db, cp.cp_id, admin_user.user_id)

    result2 = await db.execute(
        select(CPValidationFinding).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    findings_after = result2.scalars().all()
    # Same number of findings — no duplicates because hash is stable
    assert len(findings_after) == len(findings_before)


@pytest.mark.asyncio
async def test_stale_run_auto_failed(db, admin_user):
    """A run stuck in 'running' for >5 min should be auto-failed on next validate."""
    from datetime import datetime, timedelta, timezone

    cp = _make_cp(factory_id=admin_user.factory_id)
    db.add(cp)
    await db.flush()

    # Manually create a stale running run
    stale_run = CPValidationRun(
        cp_id=cp.cp_id, trigger="auto_on_save", status="running",
        factory_id=admin_user.factory_id,
        created_by=admin_user.user_id,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db.add(stale_run)
    await db.flush()

    item = ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10",
        source_fmea_node_id="pfmea-step-1", control_method="",
        factory_id=admin_user.factory_id,
    )
    db.add(item)
    await db.flush()

    engine = CPValidationEngine()
    run = await engine.validate(db, cp.cp_id, admin_user.user_id, trigger="manual")

    assert run.status == "completed"

    # Verify the stale run was marked failed
    await db.refresh(stale_run)
    assert stale_run.status == "failed"
