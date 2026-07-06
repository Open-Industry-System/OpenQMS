import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.capa import CAPAEightD
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
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_capa(db, factory_id, user_id, doc_no):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=doc_no, title="t",
        product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status="D4_ROOT_CAUSE")
    db.add(capa); await db.flush()
    return capa


@pytest.mark.asyncio
async def test_adopt_endpoint_appends_d4(capa_client, db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-ADOPT")
    resp = await capa_client.post(f"/api/capa/{capa.report_id}/adopt-recommendation",
        json={"d_step": "d4", "adopted_text": "根因B", "source": "fmea_graph",
              "item_ref": {"failure_cause_node_id": "c1"}})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["field_value"] == "根因B"
    assert body["d_step"] == "d4"


@pytest.mark.asyncio
async def test_adopt_rejects_d7_step(capa_client, db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-D7REJ")
    resp = await capa_client.post(f"/api/capa/{capa.report_id}/adopt-recommendation",
        json={"d_step": "d7", "adopted_text": "x", "source": "rule"})
    assert resp.status_code == 422   # Literal["d4","d5"] 拒绝


@pytest.mark.asyncio
async def test_create_and_list_verification(capa_client, db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-VER")
    r1 = await capa_client.post(f"/api/capa/{capa.report_id}/root-cause-verifications",
        json={"root_cause_text": "rc", "method": "复测", "is_verified": True})
    assert r1.status_code == 200, r1.text
    assert r1.json()["is_verified"] is True
    r2 = await capa_client.get(f"/api/capa/{capa.report_id}/root-cause-verifications")
    assert r2.status_code == 200
    assert len(r2.json()) == 1


@pytest.mark.asyncio
async def test_patch_verification_other_capa_404(capa_client, db, default_factory, admin_user):
    capa_a = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-A")
    capa_b = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-B")
    r = await capa_client.post(f"/api/capa/{capa_b.report_id}/root-cause-verifications",
        json={"root_cause_text": "b"})
    vid = r.json()["verification_id"]
    # 用 capa_a 的 URL 改 capa_b 的记录
    patch = await capa_client.patch(f"/api/capa/{capa_a.report_id}/root-cause-verifications/{vid}",
        json={"is_verified": True})
    assert patch.status_code == 404


@pytest.mark.asyncio
async def test_advance_d4_to_d5_blocked_api(capa_client, db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-GATE")
    resp = await capa_client.post(f"/api/capa/{capa.report_id}/advance", json={})
    assert resp.status_code == 400


@pytest.fixture
async def low_perm_client_builder(db, admin_user, default_factory):
    """工厂：按指定 capa 权限级别构造 AsyncClient（这些端点只校验 CAPA 模块；fmea 固定 5 不影响）。级别用 PermissionLevel 数值（NONE=0/VIEW=1/CREATE=2/EDIT=3/APPROVE=4/ADMIN=5）。"""
    async def _build(capa_level: int):
        existing = (await db.execute(select(RolePermission).where(
            RolePermission.role_id == admin_user.role_id, RolePermission.module == "capa"))).scalar_one_or_none()
        if existing is None:
            db.add(RolePermission(role_id=admin_user.role_id, module="capa", permission_level=capa_level))
        else:
            existing.permission_level = capa_level
        await db.flush()
        scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_request_scope] = lambda: scope
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield _build
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_adopt_403_without_capa_edit(low_perm_client_builder, db, default_factory, admin_user):
    # capa=CREATE(2) < EDIT(3) → adopt 应 403
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-ADOPT-403")
    ac = await low_perm_client_builder(capa_level=2)
    async with ac:
        resp = await ac.post(f"/api/capa/{capa.report_id}/adopt-recommendation",
            json={"d_step": "d4", "adopted_text": "x", "source": "fmea_graph"})
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_verification_403_without_capa_edit(low_perm_client_builder, db, default_factory, admin_user):
    # capa=CREATE(2) < EDIT(3) → create verification 应 403
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-CRT-403")
    ac = await low_perm_client_builder(capa_level=2)
    async with ac:
        resp = await ac.post(f"/api/capa/{capa.report_id}/root-cause-verifications",
            json={"root_cause_text": "rc"})
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_verification_200_with_capa_view(low_perm_client_builder, db, default_factory, admin_user):
    # capa=VIEW(1) ≥ VIEW(1) → list 应 200（先以 EDIT 建一条记录，再降到 VIEW 列举）
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-LIST-200")
    ac_edit = await low_perm_client_builder(capa_level=3)
    async with ac_edit:
        await ac_edit.post(f"/api/capa/{capa.report_id}/root-cause-verifications",
            json={"root_cause_text": "rc"})
    ac_view = await low_perm_client_builder(capa_level=1)
    async with ac_view:
        r = await ac_view.get(f"/api/capa/{capa.report_id}/root-cause-verifications")
        assert r.status_code == 200
        assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_list_verification_403_without_capa_view(low_perm_client_builder, db, default_factory, admin_user):
    # capa=NONE(0) < VIEW(1) → list 应 403
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-LIST-403")
    ac = await low_perm_client_builder(capa_level=0)
    async with ac:
        r = await ac.get(f"/api/capa/{capa.report_id}/root-cause-verifications")
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_adopt_403_when_capa_product_line_out_of_scope(db, default_factory, admin_user):
    # 用户 pl_scope EXPLICIT 只允许 OTHER-PL；CAPA 在 DC-DC-100 → adopt 应 403（产品线隔离）
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-PL-ADOPT")
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None,
                       pl_mode="EXPLICIT", pl_codes=["OTHER-PL"])
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(f"/api/capa/{capa.report_id}/adopt-recommendation",
            json={"d_step": "d4", "adopted_text": "x", "source": "fmea_graph"})
        assert r.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_verification_403_when_capa_product_line_out_of_scope(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "8D-API-PL-CRT")
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None,
                       pl_mode="EXPLICIT", pl_codes=["OTHER-PL"])
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(f"/api/capa/{capa.report_id}/root-cause-verifications",
            json={"root_cause_text": "rc"})
        assert r.status_code == 403
    app.dependency_overrides.clear()
