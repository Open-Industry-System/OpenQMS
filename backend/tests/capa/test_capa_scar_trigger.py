"""CAPA → SCAR trigger API/service tests (US-E2E-01.5 Task 3)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.deps import get_current_user, get_db, get_request_scope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.deps import RequestScope
from app.main import app
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.capa_d3 import CapaD3ImpactReport, CapaD3ImportRun
from app.models.factory import Factory
from app.models.role import RolePermission
from app.models.supplier import Supplier, SupplierSCAR
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


async def _seed_perm(db, role_id, module, level):
    existing = await db.execute(
        select(RolePermission).where(
            RolePermission.role_id == role_id, RolePermission.module == module
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        db.add(RolePermission(role_id=role_id, module=module, permission_level=level))
    else:
        row.permission_level = level
    await db.flush()


async def _make_capa(
    db,
    factory_id,
    user_id,
    *,
    status="D3_INTERIM",
    product_line_code="DC-DC-100",
    d2_description="来料外观不良",
    d4_root_cause="供应商工艺偏移",
    document_no=None,
    title="SCAR trigger CAPA",
):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=document_no or f"8D-SCAR-{uuid.uuid4().hex[:6]}",
        title=title,
        product_line_code=product_line_code,
        factory_id=factory_id,
        created_by=user_id,
        status=status,
        severity="serious",
        d2_description=d2_description,
        d4_root_cause=d4_root_cause,
    )
    db.add(capa)
    await db.flush()
    return capa


async def _make_supplier(db, factory_id, user_id, *, supplier_no=None, name="SCAR Supplier"):
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=supplier_no or f"SUP-SCAR-{uuid.uuid4().hex[:6]}",
        factory_id=factory_id,
        name=name,
        short_name="SS",
        created_by=user_id,
    )
    db.add(supplier)
    await db.flush()
    return supplier


async def _make_d3_current_with_lot(db, capa, user_id, lot_no="LOT-E2E-SCAR-001"):
    """Insert current completed D3 import run + done current impact report with lot_no."""
    now = datetime.now(timezone.utc)
    run = CapaD3ImportRun(
        run_id=uuid.uuid4(),
        capa_id=capa.report_id,
        factory_id=capa.factory_id,
        is_current=True,
        status="completed",
        imported_types=["inventory"],
        analysis_context={"risk_mapping_version": "v1"},
        started_at=now,
        completed_at=now,
        imported_by=user_id,
    )
    db.add(run)
    await db.flush()

    report = CapaD3ImpactReport(
        report_id=uuid.uuid4(),
        run_id=run.run_id,
        factory_id=capa.factory_id,
        is_current=True,
        status="done",
        attempt_token=uuid.uuid4(),
        started_at=now,
        completed_at=now,
        generated_by=user_id,
        stage_runs=[],
        prompt_stats={},
        llm_available=True,
        model="test-model",
        batches=[
            {"material_code": "M1", "lot_no": lot_no},
            {"material_code": "M1", "lot_no": lot_no},  # dup should collapse
            {"material_code": "M2", "lot_no": ""},  # empty skipped
        ],
        impact_qty={"inventory": 1},
        customer_impact=[],
        time_window={"start": None, "end": None},
        risk_level="medium",
        risk_floor="low",
        risk_explanation="test risk",
    )
    db.add(report)
    await db.flush()
    return run, report


def _client_for(db, user, scope):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def engineer_client(db, admin_user, default_factory):
    """CAPA EDIT=3 client (admin role matrix, factory unlimited)."""
    await _seed_perm(db, admin_user.role_id, "capa", 3)
    await _seed_perm(db, admin_user.role_id, "scar", 3)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    async with _client_for(db, admin_user, scope) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_trigger_success_bidirectional_and_audit(
    engineer_client, db, default_factory, admin_user
):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    await _make_d3_current_with_lot(db, capa, admin_user.user_id, "LOT-E2E-SCAR-001")

    resp = await engineer_client.post(
        f"/api/capa/{capa.report_id}/trigger-scar",
        json={"supplier_id": str(supplier.supplier_id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_type"] == "capa"
    assert body["capa_ref_id"] == str(capa.report_id)
    assert body["source_id"] == str(capa.report_id)
    assert body["supplier_id"] == str(supplier.supplier_id)
    assert body["product_line_code"] == capa.product_line_code
    assert "来料外观不良" in body["description"]
    assert "供应商工艺偏移" in body["description"]
    assert "LOT-E2E-SCAR-001" in body["description"]
    assert "受影响批次" in body["description"]

    await db.refresh(capa)
    assert capa.scar_ref_id == uuid.UUID(body["scar_id"])

    scar = await db.get(SupplierSCAR, uuid.UUID(body["scar_id"]))
    assert scar is not None
    assert scar.capa_ref_id == capa.report_id
    assert scar.source_type == "capa"
    assert scar.factory_id == capa.factory_id

    audit = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == capa.report_id,
                AuditLog.action == "SCAR_TRIGGERED",
            )
        )
    ).scalar_one()
    assert audit.operated_by == admin_user.user_id
    assert audit.factory_id == capa.factory_id
    assert audit.table_name == "capa_eightd"
    cf = audit.changed_fields
    assert cf["capa_id"] == str(capa.report_id)
    assert cf["scar_id"] == str(scar.scar_id)
    assert cf["supplier_id"] == str(supplier.supplier_id)
    assert isinstance(cf["capa_id"], str)
    assert isinstance(cf["scar_id"], str)
    assert isinstance(cf["supplier_id"], str)
    assert cf["source_type"] == "capa"
    assert "LOT-E2E-SCAR-001" in cf["affected_batches"]


@pytest.mark.asyncio
async def test_trigger_without_d3_report_succeeds(
    engineer_client, db, default_factory, admin_user
):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)

    resp = await engineer_client.post(
        f"/api/capa/{capa.report_id}/trigger-scar",
        json={"supplier_id": str(supplier.supplier_id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_type"] == "capa"
    assert "受影响批次" not in body["description"]


@pytest.mark.asyncio
async def test_trigger_duplicate_400(engineer_client, db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)

    r1 = await engineer_client.post(
        f"/api/capa/{capa.report_id}/trigger-scar",
        json={"supplier_id": str(supplier.supplier_id)},
    )
    assert r1.status_code == 200, r1.text

    r2 = await engineer_client.post(
        f"/api/capa/{capa.report_id}/trigger-scar",
        json={"supplier_id": str(supplier.supplier_id)},
    )
    assert r2.status_code == 400
    assert "已关联" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_trigger_d1_d2_archived_400(
    engineer_client, db, default_factory, admin_user
):
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    for status in ("D1_TEAM", "D2_DESCRIPTION", "ARCHIVED"):
        capa = await _make_capa(
            db, default_factory.id, admin_user.user_id, status=status
        )
        resp = await engineer_client.post(
            f"/api/capa/{capa.report_id}/trigger-scar",
            json={"supplier_id": str(supplier.supplier_id)},
        )
        assert resp.status_code == 400, (status, resp.text)
        assert "不允许发起 SCAR" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_trigger_cross_factory_supplier_400(
    engineer_client, db, default_factory, admin_user
):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    other = Factory(
        id=uuid.uuid4(), code=f"OF-{uuid.uuid4().hex[:6]}", name="Other", is_active=True
    )
    db.add(other)
    await db.flush()
    foreign_supplier = await _make_supplier(db, other.id, admin_user.user_id)

    resp = await engineer_client.post(
        f"/api/capa/{capa.report_id}/trigger-scar",
        json={"supplier_id": str(foreign_supplier.supplier_id)},
    )
    assert resp.status_code == 400
    assert "同厂" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_trigger_cross_factory_capa_uuid_404(
    engineer_client, db, default_factory, admin_user
):
    other = Factory(
        id=uuid.uuid4(), code=f"OF-{uuid.uuid4().hex[:6]}", name="Other", is_active=True
    )
    db.add(other)
    await db.flush()
    capa = await _make_capa(db, other.id, admin_user.user_id)
    supplier = await _make_supplier(db, other.id, admin_user.user_id)

    # engineer_client effective_factory_id = default_factory → other CAPA invisible
    resp = await engineer_client.post(
        f"/api/capa/{capa.report_id}/trigger-scar",
        json={"supplier_id": str(supplier.supplier_id)},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_effective_factory_mismatch_404(db, default_factory, admin_user):
    """Multi-factory user with effective=A cannot trigger CAPA at accessible B."""
    await _seed_perm(db, admin_user.role_id, "capa", 3)
    factory_b = Factory(
        id=uuid.uuid4(), code=f"FB-{uuid.uuid4().hex[:6]}", name="Factory B", is_active=True
    )
    db.add(factory_b)
    await db.flush()
    capa_b = await _make_capa(db, factory_b.id, admin_user.user_id)
    supplier_b = await _make_supplier(db, factory_b.id, admin_user.user_id)

    scope = RequestScope(
        factory_scope=FactoryScope(
            accessible_factory_ids=[default_factory.id, factory_b.id],
            default_factory_id=default_factory.id,
        ),
        effective_factory_id=default_factory.id,  # A
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=admin_user,
    )
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.post(
            f"/api/capa/{capa_b.report_id}/trigger-scar",
            json={"supplier_id": str(supplier_b.supplier_id)},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_same_factory_pl_denied_403(db, default_factory, admin_user):
    await _seed_perm(db, admin_user.role_id, "capa", 3)
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id, product_line_code="DC-DC-100"
    )
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)

    scope = _scope_for(
        admin_user,
        default_factory,
        accessible_factory_ids=None,
        pl_mode="EXPLICIT",
        pl_codes=["OTHER-PL"],
    )
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.post(
            f"/api/capa/{capa.report_id}/trigger-scar",
            json={"supplier_id": str(supplier.supplier_id)},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_trigger_no_capa_edit_403(db, default_factory, admin_user):
    await _seed_perm(db, admin_user.role_id, "capa", 1)  # VIEW only
    await _seed_perm(db, admin_user.role_id, "scar", 3)
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.post(
            f"/api/capa/{capa.report_id}/trigger-scar",
            json={"supplier_id": str(supplier.supplier_id)},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403
    assert "EDIT" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_capa_linked_scar_and_d3_lots(
    engineer_client, db, default_factory, admin_user
):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    await _make_d3_current_with_lot(db, capa, admin_user.user_id, "LOT-E2E-SCAR-001")

    trig = await engineer_client.post(
        f"/api/capa/{capa.report_id}/trigger-scar",
        json={"supplier_id": str(supplier.supplier_id)},
    )
    assert trig.status_code == 200, trig.text
    scar_id = trig.json()["scar_id"]
    scar_no = trig.json()["scar_no"]

    get_resp = await engineer_client.get(f"/api/capa/{capa.report_id}")
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["scar_ref_id"] == scar_id
    assert body["linked_scar"] is not None
    assert body["linked_scar"]["scar_id"] == scar_id
    assert body["linked_scar"]["scar_no"] == scar_no
    assert body["linked_scar"]["status"] == "open"
    assert body["linked_scar"]["supplier_id"] == str(supplier.supplier_id)
    assert body["d3_affected_lots"] == ["LOT-E2E-SCAR-001"]


@pytest.mark.asyncio
async def test_public_scar_create_rejects_source_type_capa_422(
    engineer_client, db, default_factory, admin_user
):
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    resp = await engineer_client.post(
        "/api/scars",
        json={
            "supplier_id": str(supplier.supplier_id),
            "source_type": "capa",
            "description": "should reject",
            "product_line_code": "DC-DC-100",
        },
    )
    assert resp.status_code == 422
