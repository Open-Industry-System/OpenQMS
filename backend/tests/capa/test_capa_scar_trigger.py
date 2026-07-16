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
async def test_trigger_body_description_still_appends_lots(
    engineer_client, db, default_factory, admin_user
):
    """FE always sends description; lots must still land in SCAR description."""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    await _make_d3_current_with_lot(db, capa, admin_user.user_id, "LOT-E2E-SCAR-001")

    resp = await engineer_client.post(
        f"/api/capa/{capa.report_id}/trigger-scar",
        json={
            "supplier_id": str(supplier.supplier_id),
            "description": f"{capa.document_no} {capa.title}\n[问题描述] {capa.d2_description}",
            "affected_batches": ["LOT-E2E-SCAR-001"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "LOT-E2E-SCAR-001" in body["description"]
    assert "受影响批次" in body["description"]
    # Lot line owned by affected_batches — single append, no double line
    assert body["description"].count("受影响批次") == 1

    # Embedded stale lot lines in description are replaced by affected_batches
    capa2 = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier2 = await _make_supplier(db, default_factory.id, admin_user.user_id)
    resp2 = await engineer_client.post(
        f"/api/capa/{capa2.report_id}/trigger-scar",
        json={
            "supplier_id": str(supplier2.supplier_id),
            "description": f"{capa2.document_no}\n受影响批次: OLD-LOT",
            "affected_batches": ["NEW-LOT"],
        },
    )
    assert resp2.status_code == 200, resp2.text
    desc2 = resp2.json()["description"]
    assert "NEW-LOT" in desc2
    assert "OLD-LOT" not in desc2
    assert desc2.count("受影响批次") == 1


@pytest.mark.asyncio
async def test_update_capa_keeps_linked_scar_projection(
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

    put = await engineer_client.put(
        f"/api/capa/{capa.report_id}",
        json={"d3_interim": "updated interim after scar link"},
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["linked_scar"] is not None
    assert body["linked_scar"]["scar_id"] == scar_id
    assert body["linked_scar"]["status"] == "open"
    assert body["d3_affected_lots"] == ["LOT-E2E-SCAR-001"]
    assert body["d3_interim"] == "updated interim after scar link"


@pytest.mark.asyncio
async def test_get_capa_wrong_pl_403(db, default_factory, admin_user):
    """GET detail enforces product-line isolation (same factory, wrong PL)."""
    await _seed_perm(db, admin_user.role_id, "capa", 3)
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id, product_line_code="DC-DC-100"
    )
    scope = _scope_for(
        admin_user,
        default_factory,
        accessible_factory_ids=None,
        pl_mode="EXPLICIT",
        pl_codes=["OTHER-PL"],
    )
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.get(f"/api/capa/{capa.report_id}")
    app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_linked_capa_product_line_forbidden(
    engineer_client, db, default_factory, admin_user
):
    from app.models.product_line import ProductLine

    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    trig = await engineer_client.post(
        f"/api/capa/{capa.report_id}/trigger-scar",
        json={"supplier_id": str(supplier.supplier_id)},
    )
    assert trig.status_code == 200, trig.text

    # Ensure target PL exists so failure is the scar-link guard, not missing PL
    existing = await db.execute(
        select(ProductLine).where(ProductLine.code == "DC-DC-200")
    )
    if existing.scalar_one_or_none() is None:
        db.add(
            ProductLine(
                code="DC-DC-200", name="DC-DC-200", factory_id=default_factory.id
            )
        )
        await db.flush()

    put = await engineer_client.put(
        f"/api/capa/{capa.report_id}",
        json={"product_line_code": "DC-DC-200"},
    )
    assert put.status_code == 400, put.text
    assert "已关联 SCAR" in put.json()["detail"]


@pytest.mark.asyncio
async def test_trigger_empty_batches_clears_embedded_lots(
    engineer_client, db, default_factory, admin_user
):
    """affected_batches=[] must clear lots even if description embeds old lot lines."""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)

    resp = await engineer_client.post(
        f"/api/capa/{capa.report_id}/trigger-scar",
        json={
            "supplier_id": str(supplier.supplier_id),
            "description": (
                f"{capa.document_no} {capa.title}\n"
                "受影响批次: LOT-SHOULD-CLEAR, LOT-OLD"
            ),
            "affected_batches": [],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "受影响批次" not in body["description"]
    assert "LOT-SHOULD-CLEAR" not in body["description"]
    assert "LOT-OLD" not in body["description"]


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


# ─── Task 4: transition SCAR_STATUS_SYNCED + hardened link-capa ───────────────


async def _make_scar(
    db,
    factory_id,
    user_id,
    supplier_id,
    *,
    product_line_code="DC-DC-100",
    capa_ref_id=None,
    status="open",
    source_type="manual",
):
    scar = SupplierSCAR(
        scar_id=uuid.uuid4(),
        scar_no=f"SCAR-T4-{uuid.uuid4().hex[:6]}",
        supplier_id=supplier_id,
        factory_id=factory_id,
        source_type=source_type,
        description="task4 scar",
        product_line_code=product_line_code,
        status=status,
        issued_by=user_id,
        capa_ref_id=capa_ref_id,
    )
    db.add(scar)
    await db.flush()
    return scar


@pytest.mark.asyncio
async def test_transition_writes_scar_status_synced(db, default_factory, admin_user):
    from app.services import scar_service

    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    scar = await _make_scar(
        db,
        default_factory.id,
        admin_user.user_id,
        supplier.supplier_id,
        capa_ref_id=capa.report_id,
        status="open",
    )
    capa.scar_ref_id = scar.scar_id
    await db.flush()

    updated = await scar_service.transition_scar(
        db, scar, "start", user_id=admin_user.user_id
    )
    assert updated.status == "in_progress"

    audit = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == capa.report_id,
                AuditLog.action == "SCAR_STATUS_SYNCED",
            )
        )
    ).scalar_one()
    assert audit.table_name == "capa_eightd"
    assert audit.operated_by == admin_user.user_id
    assert audit.factory_id == scar.factory_id
    cf = audit.changed_fields
    assert cf["scar_status"] == "in_progress"
    assert cf["old_status"] == "open"
    assert cf["new_status"] == "in_progress"
    assert cf["capa_id"] == str(capa.report_id)
    assert cf["scar_id"] == str(scar.scar_id)
    assert isinstance(cf["capa_id"], str)
    assert isinstance(cf["scar_id"], str)
    assert cf["scar_no"] == scar.scar_no


@pytest.mark.asyncio
async def test_transition_without_capa_ref_no_sync_audit(db, default_factory, admin_user):
    from app.services import scar_service

    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    scar = await _make_scar(
        db,
        default_factory.id,
        admin_user.user_id,
        supplier.supplier_id,
        capa_ref_id=None,
        status="open",
    )

    await scar_service.transition_scar(db, scar, "start", user_id=admin_user.user_id)

    rows = (
        await db.execute(
            select(AuditLog).where(AuditLog.action == "SCAR_STATUS_SYNCED")
        )
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_link_capa_bidirectional(engineer_client, db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    scar = await _make_scar(
        db, default_factory.id, admin_user.user_id, supplier.supplier_id
    )

    resp = await engineer_client.post(
        f"/api/scars/{scar.scar_id}/link-capa",
        json={"capa_ref_id": str(capa.report_id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["capa_ref_id"] == str(capa.report_id)

    await db.refresh(capa)
    await db.refresh(scar)
    assert capa.scar_ref_id == scar.scar_id
    assert scar.capa_ref_id == capa.report_id

    audit = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == scar.scar_id,
                AuditLog.action == "LINK_CAPA",
            )
        )
    ).scalar_one()
    assert audit.operated_by == admin_user.user_id
    assert audit.changed_fields["capa_ref_id"] == str(capa.report_id)


@pytest.mark.asyncio
async def test_link_capa_cross_factory_404(engineer_client, db, default_factory, admin_user):
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    scar = await _make_scar(
        db, default_factory.id, admin_user.user_id, supplier.supplier_id
    )
    other = Factory(
        id=uuid.uuid4(), code=f"OF-{uuid.uuid4().hex[:6]}", name="Other", is_active=True
    )
    db.add(other)
    await db.flush()
    foreign_capa = await _make_capa(db, other.id, admin_user.user_id)

    resp = await engineer_client.post(
        f"/api/scars/{scar.scar_id}/link-capa",
        json={"capa_ref_id": str(foreign_capa.report_id)},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_link_capa_cross_pl_400(engineer_client, db, default_factory, admin_user):
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id, product_line_code="OTHER-PL"
    )
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    scar = await _make_scar(
        db,
        default_factory.id,
        admin_user.user_id,
        supplier.supplier_id,
        product_line_code="DC-DC-100",
    )

    resp = await engineer_client.post(
        f"/api/scars/{scar.scar_id}/link-capa",
        json={"capa_ref_id": str(capa.report_id)},
    )
    assert resp.status_code == 400
    assert "产品线" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_link_capa_scar_pl_denied_403(db, default_factory, admin_user):
    await _seed_perm(db, admin_user.role_id, "capa", 3)
    await _seed_perm(db, admin_user.role_id, "scar", 3)
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id, product_line_code="DC-DC-100"
    )
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    scar = await _make_scar(
        db,
        default_factory.id,
        admin_user.user_id,
        supplier.supplier_id,
        product_line_code="DC-DC-100",
    )
    scope = _scope_for(
        admin_user,
        default_factory,
        accessible_factory_ids=None,
        pl_mode="EXPLICIT",
        pl_codes=["OTHER-PL"],
    )
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.post(
            f"/api/scars/{scar.scar_id}/link-capa",
            json={"capa_ref_id": str(capa.report_id)},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_link_capa_capa_pl_denied_403(db, default_factory, admin_user):
    """Defense-in-depth: CAPA PL check rejects when operator lacks CAPA PL access.

    Same-PL invariant means scar PL check usually fires first; assert 403 either way.
    """
    await _seed_perm(db, admin_user.role_id, "capa", 3)
    await _seed_perm(db, admin_user.role_id, "scar", 3)
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id, product_line_code="DC-DC-100"
    )
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    scar = await _make_scar(
        db,
        default_factory.id,
        admin_user.user_id,
        supplier.supplier_id,
        product_line_code="DC-DC-100",
    )
    scope = _scope_for(
        admin_user,
        default_factory,
        accessible_factory_ids=None,
        pl_mode="EXPLICIT",
        pl_codes=["OTHER-PL"],
    )
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.post(
            f"/api/scars/{scar.scar_id}/link-capa",
            json={"capa_ref_id": str(capa.report_id)},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_link_capa_scar_create_without_capa_edit_403(db, default_factory, admin_user):
    await _seed_perm(db, admin_user.role_id, "scar", 3)  # CREATE
    await _seed_perm(db, admin_user.role_id, "capa", 1)  # VIEW only
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    scar = await _make_scar(
        db, default_factory.id, admin_user.user_id, supplier.supplier_id
    )
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.post(
            f"/api/scars/{scar.scar_id}/link-capa",
            json={"capa_ref_id": str(capa.report_id)},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 403
    assert "capa" in resp.json()["detail"].lower() or "EDIT" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_link_capa_rebind_forbidden_400(engineer_client, db, default_factory, admin_user):
    capa_a = await _make_capa(db, default_factory.id, admin_user.user_id)
    capa_b = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    scar = await _make_scar(
        db,
        default_factory.id,
        admin_user.user_id,
        supplier.supplier_id,
        capa_ref_id=capa_a.report_id,
    )
    capa_a.scar_ref_id = scar.scar_id
    await db.flush()

    resp = await engineer_client.post(
        f"/api/scars/{scar.scar_id}/link-capa",
        json={"capa_ref_id": str(capa_b.report_id)},
    )
    assert resp.status_code == 400
    assert "换绑" in resp.json()["detail"] or "已关联" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_link_capa_target_already_bound_400(
    engineer_client, db, default_factory, admin_user
):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    scar_a = await _make_scar(
        db,
        default_factory.id,
        admin_user.user_id,
        supplier.supplier_id,
        capa_ref_id=capa.report_id,
    )
    capa.scar_ref_id = scar_a.scar_id
    await db.flush()
    scar_b = await _make_scar(
        db, default_factory.id, admin_user.user_id, supplier.supplier_id
    )

    resp = await engineer_client.post(
        f"/api/scars/{scar_b.scar_id}/link-capa",
        json={"capa_ref_id": str(capa.report_id)},
    )
    assert resp.status_code == 400
    assert "已关联" in resp.json()["detail"]


# ─── P1 round 3: effective-factory visibility + PL-change race ────────────────


@pytest.mark.asyncio
async def test_get_capa_effective_factory_mismatch_404(
    db, default_factory, admin_user
):
    """Multi-factory user with effective=A cannot GET CAPA at accessible B → 404."""
    await _seed_perm(db, admin_user.role_id, "capa", 3)
    factory_b = Factory(
        id=uuid.uuid4(), code=f"FB-{uuid.uuid4().hex[:6]}", name="Factory B", is_active=True
    )
    db.add(factory_b)
    await db.flush()
    capa_b = await _make_capa(db, factory_b.id, admin_user.user_id)

    scope = RequestScope(
        factory_scope=FactoryScope(
            accessible_factory_ids=[default_factory.id, factory_b.id],
            default_factory_id=default_factory.id,
        ),
        effective_factory_id=default_factory.id,  # effective A, CAPA at B
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=admin_user,
    )
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.get(f"/api/capa/{capa_b.report_id}")
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_capa_effective_factory_mismatch_404(
    db, default_factory, admin_user
):
    """Multi-factory user with effective=A cannot PUT CAPA at accessible B → 404."""
    await _seed_perm(db, admin_user.role_id, "capa", 3)
    factory_b = Factory(
        id=uuid.uuid4(), code=f"FB-{uuid.uuid4().hex[:6]}", name="Factory B", is_active=True
    )
    db.add(factory_b)
    await db.flush()
    capa_b = await _make_capa(db, factory_b.id, admin_user.user_id)

    scope = RequestScope(
        factory_scope=FactoryScope(
            accessible_factory_ids=[default_factory.id, factory_b.id],
            default_factory_id=default_factory.id,
        ),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=admin_user,
    )
    async with _client_for(db, admin_user, scope) as ac:
        resp = await ac.put(
            f"/api/capa/{capa_b.report_id}",
            json={"d3_interim": "should not land"},
        )
    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pl_change_blocked_when_scar_linked(
    engineer_client, db, default_factory, admin_user
):
    """PL move on a CAPA with a committed scar_ref_id is refused (race-safe path).

    The route locks the CAPA row FOR UPDATE and refreshes before checking the
    linked-SCAR invariant, so even a just-committed concurrent link is observed.
    This covers the same code path as the cross-session race; a true two-session
    deadlock-prone test is intentionally avoided to keep the suite hermetic.
    """
    from app.models.product_line import ProductLine

    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)
    trig = await engineer_client.post(
        f"/api/capa/{capa.report_id}/trigger-scar",
        json={"supplier_id": str(supplier.supplier_id)},
    )
    assert trig.status_code == 200, trig.text

    existing = await db.execute(
        select(ProductLine).where(ProductLine.code == "DC-DC-200")
    )
    if existing.scalar_one_or_none() is None:
        db.add(
            ProductLine(
                code="DC-DC-200", name="DC-DC-200", factory_id=default_factory.id
            )
        )
        await db.flush()

    put = await engineer_client.put(
        f"/api/capa/{capa.report_id}",
        json={"product_line_code": "DC-DC-200"},
    )
    assert put.status_code == 400, put.text
    assert "已关联 SCAR" in put.json()["detail"]


@pytest.mark.asyncio
async def test_lot_strip_preserves_prose_mentioning_batch(
    engineer_client, db, default_factory, admin_user
):
    """User prose mentioning 受影响批次 in a sentence must survive lot-line stripping."""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    supplier = await _make_supplier(db, default_factory.id, admin_user.user_id)

    resp = await engineer_client.post(
        f"/api/capa/{capa.report_id}/trigger-scar",
        json={
            "supplier_id": str(supplier.supplier_id),
            "description": "受影响批次分析结论：风险低，但需复测",
            "affected_batches": ["LOT-NEW"],
        },
    )
    assert resp.status_code == 200, resp.text
    desc = resp.json()["description"]
    assert "受影响批次分析结论：风险低" in desc  # prose preserved
    assert "LOT-NEW" in desc
    # Single emitted lot line; prose line kept
    assert desc.count("受影响批次:") == 1
    assert "受影响批次分析结论" in desc


# ─── P2: true two-session concurrency ─────────────────────────────────────────
import asyncio


async def _committed_scar_trigger_fixtures(sessionmaker):
    """Create factory, PL, role, user, supplier, capa in a real-commit session."""
    from app.models.factory import Factory
    from app.models.product_line import ProductLine
    from app.models.role import RoleDefinition, RolePermission
    from app.models.user import User
    from app.core.permissions import Module, PermissionLevel

    factory_id = uuid.uuid4()
    pl_code = f"PL-ST-{factory_id.hex[:8]}"
    async with sessionmaker() as s:
        factory = Factory(id=factory_id, code=f"ST-{factory_id.hex[:8]}", name="ST Factory")
        s.add(factory)
        s.add(ProductLine(code=pl_code, name=pl_code, factory_id=factory.id))
        role = RoleDefinition(
            role_key=f"admin_st_{factory_id.hex[:8]}",
            name_zh="ST Admin", name_en="ST Admin",
            is_system=True, is_editable=False, bypass_row_level_security=True,
            sort_order=1, is_active=True,
        )
        s.add(role)
        await s.flush()
        user = User(
            user_id=uuid.uuid4(),
            username=f"st-{factory_id.hex[:8]}",
            password_hash="x",
            factory_id=factory.id,
            role_id=role.id,
            legacy_role="admin",
            is_active=True,
        )
        s.add(user)
        await s.flush()
        supplier = Supplier(
            supplier_id=uuid.uuid4(),
            supplier_no=f"SUP-ST-{factory_id.hex[:8]}",
            factory_id=factory.id,
            name="ST Supplier",
            short_name="STS",
            created_by=user.user_id,
        )
        s.add(supplier)
        capa = CAPAEightD(
            report_id=uuid.uuid4(),
            document_no=f"8D-ST-{factory_id.hex[:8]}",
            title="ST capa",
            product_line_code=pl_code,
            factory_id=factory.id,
            created_by=user.user_id,
            status="D3_INTERIM",
            severity="serious",
            d2_description="来料外观不良",
        )
        s.add(capa)
        await s.commit()
        return {
            "factory_id": factory.id,
            "pl_code": pl_code,
            "user_id": user.user_id,
            "supplier_id": supplier.supplier_id,
            "capa_id": capa.report_id,
        }


@pytest.mark.asyncio
async def test_concurrent_trigger_one_succeeds_one_400(sessionmaker):
    """Two concurrent triggers on the same CAPA: exactly one succeeds, the other gets 400."""
    from app.services import capa_scar_service
    from app.core.deps import RequestScope
    from app.core.factory_scope import FactoryScope, ProductLineScope

    fx = await _committed_scar_trigger_fixtures(sessionmaker)
    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=fx["factory_id"]),
        effective_factory_id=fx["factory_id"],
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=type("U", (), {"user_id": fx["user_id"], "role_definition": type("R", (), {"bypass_row_level_security": True})()})(),
    )

    results: list = []

    async def worker():
        async with sessionmaker() as s:
            try:
                await capa_scar_service.trigger_scar_from_capa(
                    s,
                    fx["capa_id"],
                    supplier_id=fx["supplier_id"],
                    user_id=fx["user_id"],
                    scope=scope,
                )
                results.append("ok")
            except ValueError:
                await s.rollback()
                results.append("conflict")
            except Exception:
                await s.rollback()
                results.append("error")

    await asyncio.gather(worker(), worker())

    assert sorted(results) == ["conflict", "ok"], f"expected one ok + one conflict, got {results}"


@pytest.mark.asyncio
async def test_concurrent_link_capa_one_succeeds_one_400(sessionmaker):
    """Two concurrent link_capa binds on the same SCAR: exactly one 200, the other 400 (not 500)."""
    from app.services import scar_service
    from app.core.deps import RequestScope
    from app.core.factory_scope import FactoryScope, ProductLineScope

    fx = await _committed_scar_trigger_fixtures(sessionmaker)
    # First, create a SCAR manually via a committed session, plus a second target CAPA
    async with sessionmaker() as s:
        scar = SupplierSCAR(
            scar_id=uuid.uuid4(),
            scar_no=f"SCAR-LK-{uuid.uuid4().hex[:6]}",
            supplier_id=fx["supplier_id"],
            factory_id=fx["factory_id"],
            source_type="manual",
            description="link race scar",
            product_line_code=fx["pl_code"],
            status="open",
            issued_by=fx["user_id"],
        )
        s.add(scar)
        capa_b = CAPAEightD(
            report_id=uuid.uuid4(),
            document_no=f"8D-LKB-{uuid.uuid4().hex[:6]}",
            title="link race capa b",
            product_line_code=fx["pl_code"],
            factory_id=fx["factory_id"],
            created_by=fx["user_id"],
            status="D3_INTERIM",
            severity="serious",
        )
        s.add(capa_b)
        await s.commit()
        scar_id = scar.scar_id
        capa_b_id = capa_b.report_id

    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=fx["factory_id"]),
        effective_factory_id=fx["factory_id"],
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=type("U", (), {"user_id": fx["user_id"], "role_definition": type("R", (), {"bypass_row_level_security": True})()})(),
    )

    results: list = []

    async def worker(target_capa_id):
        async with sessionmaker() as s:
            scar_obj = await s.get(SupplierSCAR, scar_id)
            try:
                await scar_service.link_capa(s, scar_obj, target_capa_id, fx["user_id"], scope)
                results.append("ok")
            except ValueError:
                await s.rollback()
                results.append("conflict")
            except Exception as e:
                await s.rollback()
                results.append(f"error:{type(e).__name__}")

    # Both try to bind the same SCAR to two different CAPAs — only one can win the 1:1
    await asyncio.gather(worker(fx["capa_id"]), worker(capa_b_id))
    assert "ok" in results and results.count("ok") == 1, f"expected exactly one ok, got {results}"
    assert all(r != "ok" and not r.startswith("error") for r in results if r != "ok"), f"non-conflict error leaked: {results}"
