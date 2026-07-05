import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument
from app.models.role import RolePermission
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


async def _seed_perms(db, role_id):
    for mod, lvl in [("capa", 5), ("fmea", 5)]:
        if (await db.execute(select(RolePermission).where(
            RolePermission.role_id == role_id, RolePermission.module == mod))).scalar_one_or_none() is None:
            db.add(RolePermission(role_id=role_id, module=mod, permission_level=lvl))
            await db.flush()


@pytest.fixture
async def d7_client(db, admin_user, default_factory):
    await _seed_perms(db, admin_user.role_id)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make(db, factory_id, user_id, doc_no, d5="监控"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=doc_no, title="t",
        product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status="D7_PREVENTION", d5_correction=d5)
    db.add(capa); await db.flush()
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-{doc_no}", title="t", fmea_type="PFMEA",
        product_line_code="DC-DC-100", factory_id=factory_id, status="draft",
        created_by=user_id,
        graph_data={"nodes": [
            {"id": "fm-1", "type": "FailureMode", "name": "虚焊"},
            {"id": "c-1", "type": "FailureCause", "name": "参数偏移"},
        ], "edges": [{"source": "c-1", "target": "fm-1", "type": "CAUSE_OF"}]})
    db.add(fmea); await db.flush()
    return capa, fmea


@pytest.mark.asyncio
async def test_d7_record_and_list(d7_client, db, default_factory, admin_user):
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-1")
    r = await d7_client.post(f"/api/capa/{capa.report_id}/d7-node-actions",
        json={"action": "confirmed", "fmea_id": str(fmea.fmea_id),
              "failure_mode_node_id": "fm-1", "failure_cause_node_id": "c-1", "match_source": "linked"})
    assert r.status_code == 200, r.text
    lst = await d7_client.get(f"/api/capa/{capa.report_id}/d7-node-actions")
    assert lst.status_code == 200
    assert len(lst.json()) == 1
    assert lst.json()[0]["action"] == "confirmed"


@pytest.mark.asyncio
async def test_d7_auto_fill_returns_new_control(d7_client, db, default_factory, admin_user):
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-2", d5="新监控")
    r = await d7_client.post(f"/api/capa/{capa.report_id}/d7-auto-fill",
        json={"fmea_id": str(fmea.fmea_id), "failure_mode_node_id": "fm-1",
              "failure_cause_node_id": "c-1", "match_source": "linked"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_new_control"] is True
    assert body["prevention_control_name_after"] == "新监控"


@pytest.mark.asyncio
async def test_d7_auto_fill_repeat_409(d7_client, db, default_factory, admin_user):
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-3")
    payload = {"fmea_id": str(fmea.fmea_id), "failure_mode_node_id": "fm-1",
               "failure_cause_node_id": "c-1", "match_source": "linked"}
    await d7_client.post(f"/api/capa/{capa.report_id}/d7-auto-fill", json=payload)
    r2 = await d7_client.post(f"/api/capa/{capa.report_id}/d7-auto-fill", json=payload)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_d7_auto_fill_d5_empty_400(d7_client, db, default_factory, admin_user):
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-4", d5=None)
    r = await d7_client.post(f"/api/capa/{capa.report_id}/d7-auto-fill",
        json={"fmea_id": str(fmea.fmea_id), "failure_mode_node_id": "fm-1",
              "failure_cause_node_id": "c-1", "match_source": "linked"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_d7_record_cross_factory_fmea_403(d7_client, db, default_factory, admin_user):
    from app.models.factory import Factory
    capa, _ = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-5")
    other = Factory(id=uuid.uuid4(), code="OTHER2", name="Other2")
    db.add(other); await db.flush()
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no="PFMEA-X", title="t", fmea_type="PFMEA",
        product_line_code="DC-DC-100", factory_id=other.id, status="draft",
        created_by=admin_user.user_id, graph_data={"nodes": [], "edges": []})
    db.add(fmea); await db.flush()
    r = await d7_client.post(f"/api/capa/{capa.report_id}/d7-node-actions",
        json={"action": "confirmed", "fmea_id": str(fmea.fmea_id),
              "failure_mode_node_id": "fm-1", "match_source": "linked"})
    assert r.status_code == 403


@pytest.fixture
async def low_perm_client_builder(db, admin_user, default_factory):
    """工厂：按指定 capa/fmea 权限级别构造 AsyncClient。级别用 PermissionLevel 数值（NONE=0/VIEW=1/CREATE=2/EDIT=3/APPROVE=4/ADMIN=5）。"""
    async def _build(capa_level: int, fmea_level: int):
        for mod, lvl in (("capa", capa_level), ("fmea", fmea_level)):
            existing = (await db.execute(select(RolePermission).where(
                RolePermission.role_id == admin_user.role_id, RolePermission.module == mod))).scalar_one_or_none()
            if existing is None:
                db.add(RolePermission(role_id=admin_user.role_id, module=mod, permission_level=lvl))
            else:
                existing.permission_level = lvl
        await db.flush()
        scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_request_scope] = lambda: scope
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield _build
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_d7_record_403_without_capa_edit(low_perm_client_builder, db, default_factory, admin_user):
    # capa=CREATE(2) < EDIT(3) → d7-node-actions 应 403（fmea 给到 ADMIN 仍不够）
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-6")
    ac = await low_perm_client_builder(capa_level=2, fmea_level=5)
    async with ac:
        r = await ac.post(f"/api/capa/{capa.report_id}/d7-node-actions",
            json={"action": "confirmed", "fmea_id": str(fmea.fmea_id),
                  "failure_mode_node_id": "fm-1", "failure_cause_node_id": "c-1", "match_source": "linked"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_d7_record_403_without_fmea_view(low_perm_client_builder, db, default_factory, admin_user):
    # fmea=NONE(0) < VIEW(1) → d7-node-actions 应 403（capa 给到 ADMIN 仍不够）
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-7")
    ac = await low_perm_client_builder(capa_level=5, fmea_level=0)
    async with ac:
        r = await ac.post(f"/api/capa/{capa.report_id}/d7-node-actions",
            json={"action": "confirmed", "fmea_id": str(fmea.fmea_id),
                  "failure_mode_node_id": "fm-1", "failure_cause_node_id": "c-1", "match_source": "linked"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_d7_auto_fill_403_without_fmea_edit(low_perm_client_builder, db, default_factory, admin_user):
    # fmea=CREATE(2) < EDIT(3) → d7-auto-fill 应 403（capa 给到 ADMIN 仍不够）
    capa, fmea = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-8", d5="新监控")
    ac = await low_perm_client_builder(capa_level=5, fmea_level=2)
    async with ac:
        r = await ac.post(f"/api/capa/{capa.report_id}/d7-auto-fill",
            json={"fmea_id": str(fmea.fmea_id), "failure_mode_node_id": "fm-1",
                  "failure_cause_node_id": "c-1", "match_source": "linked"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_d7_list_403_without_fmea_view(low_perm_client_builder, db, default_factory, admin_user):
    # capa=VIEW(1) 但 fmea=NONE(0)：GET /d7-node-actions 返回 FMEA 衍生元数据，读也需 FMEA VIEW → 403
    capa, _ = await _make(db, default_factory.id, admin_user.user_id, "8D-D7-API-9")
    ac = await low_perm_client_builder(capa_level=1, fmea_level=0)
    async with ac:
        r = await ac.get(f"/api/capa/{capa.report_id}/d7-node-actions")
        assert r.status_code == 403
