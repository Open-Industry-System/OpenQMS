"""Control plan item_id stability for doc-gate target_key (US-E2E-01.7)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.control_plan import ControlPlan, ControlPlanItem
from app.schemas.control_plan import ControlPlanItemCreate, ControlPlanUpdate
from app.services.control_plan_service import update_control_plan


@pytest.mark.asyncio
async def test_update_preserves_existing_item_id(db, default_factory, admin_user):
    """Request with existing item_id reuses UUID; only missing items are deleted; new get new UUID."""
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-ID-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="draft",
        created_by=admin_user.user_id,
    )
    db.add(cp)
    await db.flush()
    old_id = uuid.uuid4()
    db.add(ControlPlanItem(
        item_id=old_id, cp_id=cp.cp_id, step_no="10",
        product_characteristic="A", control_method="old",
        source_fmea_node_id="step-1", sort_order=0,
        factory_id=default_factory.id,
    ))
    await db.flush()

    data = ControlPlanUpdate(items=[
        ControlPlanItemCreate(
            item_id=str(old_id),
            step_no="10",
            product_characteristic="B",  # field change
            control_method="new",
            source_fmea_node_id="step-1",
        ),
        ControlPlanItemCreate(  # new row, no id
            step_no="20",
            product_characteristic="C",
            control_method="x",
            source_fmea_node_id="step-2",
        ),
    ])
    await update_control_plan(db, cp, data, admin_user.user_id)
    await db.flush()

    items = (await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id).order_by(ControlPlanItem.sort_order)
    )).scalars().all()
    assert len(items) == 2
    assert items[0].item_id == old_id  # preserved
    assert items[0].product_characteristic == "B"
    assert items[0].control_method == "new"
    assert items[1].item_id != old_id  # new UUID
    assert items[1].product_characteristic == "C"


@pytest.mark.asyncio
async def test_update_deletes_missing_items(db, default_factory, admin_user):
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-DEL-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="draft",
        created_by=admin_user.user_id,
    )
    db.add(cp)
    await db.flush()
    keep = uuid.uuid4()
    drop = uuid.uuid4()
    for iid, step in ((keep, "10"), (drop, "20")):
        db.add(ControlPlanItem(
            item_id=iid, cp_id=cp.cp_id, step_no=step,
            product_characteristic=step, control_method="m",
            source_fmea_node_id=f"s-{step}", sort_order=int(step),
            factory_id=default_factory.id,
        ))
    await db.flush()

    data = ControlPlanUpdate(items=[
        ControlPlanItemCreate(
            item_id=str(keep), step_no="10", product_characteristic="10",
            control_method="m", source_fmea_node_id="s-10",
        ),
    ])
    await update_control_plan(db, cp, data, admin_user.user_id)
    await db.flush()
    items = (await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id)
    )).scalars().all()
    assert len(items) == 1
    assert items[0].item_id == keep


@pytest.mark.asyncio
async def test_update_rejects_duplicate_item_id(db, default_factory, admin_user):
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-DUP-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="draft",
        created_by=admin_user.user_id,
    )
    db.add(cp)
    await db.flush()
    iid = uuid.uuid4()
    db.add(ControlPlanItem(
        item_id=iid, cp_id=cp.cp_id, step_no="10",
        product_characteristic="A", control_method="m",
        source_fmea_node_id="s", sort_order=0, factory_id=default_factory.id,
    ))
    await db.flush()
    data = ControlPlanUpdate(items=[
        ControlPlanItemCreate(item_id=str(iid), step_no="10", product_characteristic="A",
                              control_method="m", source_fmea_node_id="s"),
        ControlPlanItemCreate(item_id=str(iid), step_no="20", product_characteristic="B",
                              control_method="m", source_fmea_node_id="s"),
    ])
    with pytest.raises(ValueError, match="重复 item_id"):
        await update_control_plan(db, cp, data, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_rejects_foreign_item_id(db, default_factory, admin_user):
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-FOR-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="draft",
        created_by=admin_user.user_id,
    )
    db.add(cp)
    await db.flush()
    foreign = uuid.uuid4()
    data = ControlPlanUpdate(items=[
        ControlPlanItemCreate(item_id=str(foreign), step_no="10", product_characteristic="A",
                              control_method="m", source_fmea_node_id="s"),
    ])
    with pytest.raises(ValueError, match="不属于当前控制计划"):
        await update_control_plan(db, cp, data, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_temp_id_creates_new(db, default_factory, admin_user):
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-TMP-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="draft",
        created_by=admin_user.user_id,
    )
    db.add(cp)
    await db.flush()
    data = ControlPlanUpdate(items=[
        ControlPlanItemCreate(item_id="temp-abc123", step_no="10", product_characteristic="A",
                              control_method="m", source_fmea_node_id="s"),
    ])
    await update_control_plan(db, cp, data, admin_user.user_id)
    await db.flush()
    items = (await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id)
    )).scalars().all()
    assert len(items) == 1
    assert str(items[0].item_id) != "temp-abc123"
