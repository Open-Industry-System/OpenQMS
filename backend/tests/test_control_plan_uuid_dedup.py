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


@pytest.mark.asyncio
async def test_update_fmea_ref_id_audit_serializes_uuid(db, default_factory, admin_user):
    """缺陷修复 #3：control_plan_service.py:214 把 UUID 直接塞进 changed_fields →
    AuditLog JSONB 序列化崩溃（500）。期望：changed_fields 存 str，更新本身成功。"""
    import json
    from app.models.audit import AuditLog
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-REF-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="draft",
        created_by=admin_user.user_id,
    )
    db.add(cp)
    await db.flush()
    # fmea_ref_id 有 FK → 需先落一条真实 FMEA
    from app.models.fmea import FMEADocument
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-REF-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=default_factory.id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1, created_by=admin_user.user_id,
    )
    db.add(fmea)
    await db.flush()
    new_ref = fmea.fmea_id
    data = ControlPlanUpdate(fmea_ref_id=new_ref)
    await update_control_plan(db, cp, data, admin_user.user_id)
    await db.flush()
    assert cp.fmea_ref_id == new_ref
    row = (await db.execute(select(AuditLog).where(
        AuditLog.table_name == "control_plans",
        AuditLog.record_id == cp.cp_id,
        AuditLog.action == "UPDATE",
    ))).scalars().all()[-1]
    # changed_fields 必须可 JSON 序列化（不抛 TypeError），且值是 str 形式
    json.dumps(row.changed_fields)
    assert row.changed_fields["fmea_ref_id"] == str(new_ref)
