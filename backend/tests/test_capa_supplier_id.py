"""CAPA supplier_id schema + update lifecycle (US-E2E-01.6 §4.1 / §4.5)."""
import uuid

import pytest

from app.schemas.capa import CAPACreate, CAPAResponse, CAPAUpdate


def test_capa_create_accepts_supplier_id():
    sid = uuid.uuid4()
    c = CAPACreate(title="t", document_no="8D-T-001", supplier_id=sid)
    assert c.supplier_id == sid


def test_capa_create_supplier_id_optional():
    c = CAPACreate(title="t", document_no="8D-T-002")
    assert c.supplier_id is None


def test_capa_update_accepts_supplier_id():
    sid = uuid.uuid4()
    u = CAPAUpdate(supplier_id=sid)
    assert u.supplier_id == sid


def test_capa_response_includes_supplier_id():
    sid = uuid.uuid4()
    r = CAPAResponse.model_validate({
        "report_id": uuid.uuid4(),
        "document_no": "8D-T-003",
        "title": "t",
        "product_line_code": "DC-DC-100",
        "status": "D1_TEAM",
        "severity": "general",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "supplier_id": str(sid),
    })
    assert r.supplier_id == sid


# ── Service lifecycle (DB) ──────────────────────────────────────────

from app.models.capa import CAPAEightD
from app.models.factory import Factory
from app.models.supplier import Supplier
from app.services.capa_service import update_capa


async def _make_capa(db, factory_id, user_id, status="D4_ROOT_CAUSE", **extra):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-SID-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        created_by=user_id,
        status=status,
        **extra,
    )
    db.add(capa)
    await db.flush()
    return capa


async def _make_supplier(db, factory_id, user_id, *, supplier_no=None):
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=supplier_no or f"SUP-{uuid.uuid4().hex[:8]}",
        name="Test Supplier",
        short_name="Test",
        factory_id=factory_id,
        status="approved",
        created_by=user_id,
    )
    db.add(supplier)
    await db.flush()
    return supplier


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_update_capa_rejects_cross_factory_supplier(db, default_factory, admin_user):
    """supplier 与 capa 不同厂 → ValueError。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, status="D4_ROOT_CAUSE")
    other = Factory(id=uuid.uuid4(), code=f"OF-{uuid.uuid4().hex[:6]}", name="Other")
    db.add(other)
    await db.flush()
    other_supplier = await _make_supplier(db, other.id, admin_user.user_id)

    with pytest.raises(ValueError, match="同一工厂"):
        await update_capa(
            db, capa, {"supplier_id": other_supplier.supplier_id}, admin_user.user_id
        )


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_update_capa_rejects_missing_supplier(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, status="D4_ROOT_CAUSE")
    with pytest.raises(ValueError, match="供应商不存在"):
        await update_capa(db, capa, {"supplier_id": uuid.uuid4()}, admin_user.user_id)


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_update_capa_allows_same_factory_supplier_before_d7(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, status="D4_ROOT_CAUSE")
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    await update_capa(db, capa, {"supplier_id": sup.supplier_id}, admin_user.user_id)
    await db.refresh(capa)
    assert capa.supplier_id == sup.supplier_id


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_update_capa_locks_supplier_id_after_d7_completed(db, default_factory, admin_user):
    """D7_COMPLETED 后改 supplier_id → ValueError。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, status="D7_COMPLETED")
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    with pytest.raises(ValueError, match="D7"):
        await update_capa(db, capa, {"supplier_id": sup.supplier_id}, admin_user.user_id)


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_update_capa_allows_same_supplier_id_after_d7(db, default_factory, admin_user):
    """同值重提在锁定态允许（未实际变更）。"""
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id, status="D7_COMPLETED",
        supplier_id=sup.supplier_id,
    )
    await update_capa(db, capa, {"supplier_id": sup.supplier_id}, admin_user.user_id)
    await db.refresh(capa)
    assert capa.supplier_id == sup.supplier_id
