"""API tests for CAPA confirm-repeat + supplier_risk_input projection (US-E2E-01.6 Task 7)."""
from __future__ import annotations

import os
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-capa-confirm-repeat")

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.supplier import Supplier
from app.models.supplier_risk import SupplierRiskConfig
from app.models.supplier_risk_capa_input import SupplierRiskCapaInput

pytestmark = pytest.mark.requires_db


async def _make_supplier(db, factory_id, user_id) -> Supplier:
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=f"SUP-CR-{uuid.uuid4().hex[:8]}",
        name="Confirm Repeat Supplier",
        short_name="CR",
        factory_id=factory_id,
        status="approved",
        created_by=user_id,
    )
    db.add(supplier)
    await db.flush()
    await db.refresh(supplier)
    return supplier


async def _make_capa(db, factory_id, user_id, supplier_id) -> CAPAEightD:
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-CR-{uuid.uuid4().hex[:8].upper()}",
        title="Confirm Repeat CAPA",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        created_by=user_id,
        status="D8_CLOSURE",
        severity="严重",
        supplier_id=supplier_id,
    )
    db.add(capa)
    await db.flush()
    return capa


async def _ensure_rule_config(
    db,
    *,
    factory_id,
    user_id,
    rule_id: str,
    enabled: bool = True,
    category: str = "quality",
    weight: float = 10.0,
    thresholds: dict | None = None,
):
    q = select(SupplierRiskConfig).where(
        SupplierRiskConfig.rule_id == rule_id,
        SupplierRiskConfig.supplier_id.is_(None),
        SupplierRiskConfig.product_line_code.is_(None),
    )
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing is not None:
        existing.enabled = enabled
        existing.weight = weight
        existing.thresholds = thresholds or {}
        existing.category = category
        await db.flush()
        return existing

    cfg = SupplierRiskConfig(
        rule_id=rule_id,
        enabled=enabled,
        category=category,
        weight=weight,
        thresholds=thresholds or {},
        factory_id=factory_id,
        product_line_code=None,
        supplier_id=None,
        updated_by=user_id,
    )
    db.add(cfg)
    await db.flush()
    return cfg


@pytest_asyncio.fixture
async def processed_input_with_capa(db, admin_user, default_factory):
    """CAPA + Supplier + processed SupplierRiskCapaInput + R01/R11 configs."""
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, supplier.supplier_id)

    await _ensure_rule_config(
        db,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        rule_id="R01",
        thresholds={"ppm_limit": 1000, "window_days": 90},
        weight=15.0,
    )
    await _ensure_rule_config(
        db,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        rule_id="R11",
        thresholds={"base_score": 10, "severe_bonus": 10, "repeat_bonus": 10},
        weight=12.0,
    )

    inp = SupplierRiskCapaInput(
        input_id=uuid.uuid4(),
        capa_id=capa.report_id,
        supplier_id=supplier.supplier_id,
        factory_id=default_factory.id,
        product_line_code=capa.product_line_code,
        created_by=admin_user.user_id,
        severity="严重",
        disposition="退货",
        repeat_suggested=True,
        repeat_detection_status="matched",
        matched_capa_nos=["8D-2025-001"],
        status="processed",
        evaluated_risk_level="medium",
        evaluated_risk_score=42.0,
    )
    db.add(inp)
    await db.flush()
    await db.refresh(inp)
    return capa, inp


@pytest.mark.asyncio
async def test_confirm_repeat_409_when_not_processed(admin_client, processed_input_with_capa, db):
    """input 非 processed → 409。"""
    capa, inp = processed_input_with_capa
    inp.status = "pending"
    await db.flush()

    resp = await admin_client.post(
        f"/api/capa/{capa.report_id}/confirm-repeat",
        json={"repeat_confirmed": True},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_confirm_repeat_success_writes_changed_audit(
    admin_client, processed_input_with_capa, db
):
    """processed → confirm → SUPPLIER_RISK_CHANGED + 投影返回。"""
    capa, inp = processed_input_with_capa
    inp.status = "processed"
    inp.evaluated_risk_level = "medium"
    await db.flush()

    resp = await admin_client.post(
        f"/api/capa/{capa.report_id}/confirm-repeat",
        json={"repeat_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("supplier_risk_input") is not None
    assert body["supplier_risk_input"]["status"] == "processed"
    assert body["supplier_risk_input"]["repeat_confirmed"] is True
    assert body["supplier_risk_input"]["evaluated_risk_level"] is not None

    changed = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == capa.report_id,
                AuditLog.action == "SUPPLIER_RISK_CHANGED",
            )
        )
    ).scalars().all()
    assert len(changed) == 1
    cf = changed[0].changed_fields
    assert "old_level" in cf and "new_level" in cf
    assert cf["repeat_confirmed"] is True
    assert changed[0].operated_by is not None


@pytest.mark.asyncio
async def test_get_capa_includes_supplier_risk_input_projection(
    admin_client, processed_input_with_capa, db
):
    """GET /capa/{id} 含 supplier_risk_input 投影。"""
    capa, inp = processed_input_with_capa
    inp.status = "processed"
    inp.evaluated_risk_level = "high"
    await db.flush()

    resp = await admin_client.get(f"/api/capa/{capa.report_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("supplier_risk_input") is not None
    assert body["supplier_risk_input"]["evaluated_risk_level"] == "high"
    assert body["supplier_risk_input"]["status"] == "processed"
    assert body["supplier_risk_input"]["input_id"] == str(inp.input_id)
