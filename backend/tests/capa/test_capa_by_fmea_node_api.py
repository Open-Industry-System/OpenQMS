import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.capa import CAPAEightD
from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.role import RolePermission
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


async def _seed_perms(db, role_id):
    for mod, lvl in [("capa", 5), ("fmea", 5)]:
        existing = await db.execute(select(RolePermission).where(
            RolePermission.role_id == role_id, RolePermission.module == mod))
        if existing.scalar_one_or_none() is None:
            db.add(RolePermission(role_id=role_id, module=mod, permission_level=lvl))
            await db.flush()


@pytest.fixture
async def capa_client(db, admin_user, default_factory):
    await _seed_perms(db, admin_user.role_id)
    # Single-factory scope: effective_factory_id = default; other factories are invisible.
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _seed(db, factory_id, user_id):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-API-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=factory_id,
        status="draft", created_by=user_id, graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea)
    await db.flush()
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-API-{uuid.uuid4().hex[:6]}", title="t",
        product_line_code="DC-DC-100", factory_id=factory_id, created_by=user_id,
        status="D4_ROOT_CAUSE", fmea_ref_id=fmea.fmea_id,
    )
    db.add(capa)
    await db.flush()
    return fmea, capa


@pytest.mark.asyncio
async def test_invisible_fmea_returns_404(db, default_factory, admin_user, capa_client):
    # FMEA in a factory the admin (single-factory, default) cannot see
    other = Factory(name="other", code=f"OTHER-{uuid.uuid4().hex[:6]}")
    db.add(other)
    await db.flush()
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-X-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=other.id,
        status="draft", created_by=admin_user.user_id, graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea)
    await db.flush()
    resp = await capa_client.get(f"/api/capa/by-fmea-node/{fmea.fmea_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_nonexistent_fmea_returns_404(db, default_factory, admin_user, capa_client):
    resp = await capa_client.get(f"/api/capa/by-fmea-node/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_visible_empty_returns_200_list(db, default_factory, admin_user, capa_client):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-E-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", created_by=admin_user.user_id, graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea)
    await db.flush()
    resp = await capa_client.get(f"/api/capa/by-fmea-node/{fmea.fmea_id}")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_visible_returns_capa_with_sources(db, default_factory, admin_user, capa_client):
    fmea, capa = await _seed(db, default_factory.id, admin_user.user_id)
    resp = await capa_client.get(f"/api/capa/by-fmea-node/{fmea.fmea_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["report_id"] == str(capa.report_id)
    assert body[0]["link_sources"] == ["header"]
