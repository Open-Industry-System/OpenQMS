"""Tests for capa_doc_gate_preflight + UUID canonical dedup (US-E2E-01.7)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.control_plan import ControlPlan, ControlPlanItem
from app.schemas.control_plan import ControlPlanItemCreate, ControlPlanUpdate
from app.services.control_plan_service import update_control_plan


@pytest.mark.asyncio
async def test_update_rejects_canonical_equivalent_uuid_variants(db, default_factory, admin_user):
    """Different text forms of the same UUID (case/braces/no-dashes) → 400."""
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-CAN-{uuid.uuid4().hex[:6]}",
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
    sid = str(iid)
    # Same UUID, four text forms that all parse to the same canonical id
    upper = sid.upper()
    no_dash = sid.replace("-", "")
    braced = "{" + sid + "}"
    data = ControlPlanUpdate(items=[
        ControlPlanItemCreate(item_id=sid, step_no="10", product_characteristic="A",
                              control_method="m", source_fmea_node_id="s"),
        ControlPlanItemCreate(item_id=upper, step_no="10", product_characteristic="A",
                              control_method="m", source_fmea_node_id="s"),
        ControlPlanItemCreate(item_id=no_dash, step_no="10", product_characteristic="A",
                              control_method="m", source_fmea_node_id="s"),
        ControlPlanItemCreate(item_id=braced, step_no="10", product_characteristic="A",
                              control_method="m", source_fmea_node_id="s"),
    ])
    with pytest.raises(ValueError, match="重复 item_id"):
        await update_control_plan(db, cp, data, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_accepts_braced_uuid_when_single(db, default_factory, admin_user):
    """A single braced UUID still resolves to the canonical existing id."""
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-BR-{uuid.uuid4().hex[:6]}",
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
        ControlPlanItemCreate(item_id="{" + str(iid) + "}", step_no="10",
                              product_characteristic="A2", control_method="m",
                              source_fmea_node_id="s"),
    ])
    await update_control_plan(db, cp, data, admin_user.user_id)
    await db.flush()
    items = (await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id)
    )).scalars().all()
    assert len(items) == 1
    assert items[0].item_id == iid  # preserved (canonical match)
    assert items[0].product_characteristic == "A2"
