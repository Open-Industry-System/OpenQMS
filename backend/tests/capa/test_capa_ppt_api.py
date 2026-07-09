import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.capa import CAPAEightD, CapaPptExport
from app.models.role import RolePermission
from app.services.agent import provider_adapter
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


@pytest.fixture(autouse=True)
def _no_llm_for_ppt_export(monkeypatch):
    """保持测试确定性：强制 LLM 未配置，使 review 走 skipped 分支。"""
    async def _raise(*args, **kwargs):
        raise provider_adapter.ProviderNotConfiguredError("LLM not configured")
    monkeypatch.setattr(provider_adapter, "build_client", _raise)


async def _seed_perm(db, role_id, mod, lvl):
    """Upsert role permission level（覆盖现有，便于测 viewer=1 阻断 / engineer=2 放行）。"""
    existing = (await db.execute(select(RolePermission).where(
        RolePermission.role_id == role_id, RolePermission.module == mod))).scalar_one_or_none()
    if existing is None:
        db.add(RolePermission(role_id=role_id, module=mod, permission_level=lvl))
    else:
        existing.permission_level = lvl
    await db.flush()


@pytest.fixture
async def qe_client(db, admin_user, default_factory):
    # engineer (L2) 等价：用 admin seed capa=2 模拟 engineer 权限
    await _seed_perm(db, admin_user.role_id, "capa", 2)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_closed_capa(db, factory_id, user_id, status="D8_CLOSURE"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no="8D-API-001", title="t",
        product_line_code="DC-DC-100", factory_id=factory_id, created_by=user_id,
        status=status, d2_description="d2", d8_closure="c",
    )
    db.add(capa)
    await db.flush()
    return capa


async def test_generate_ppt_d8_closure(qe_client, db, admin_user, default_factory):
    capa = await _make_closed_capa(db, default_factory.id, admin_user.user_id)
    r = await qe_client.post(f"/api/capa/{capa.report_id}/ppt-export")
    assert r.status_code == 200
    assert "presentationml.presentation" in r.headers.get("content-type", "")
    assert r.headers.get("x-ppt-review-status") == "skipped"  # LLM 未配置
    assert r.headers.get("x-ppt-export-id") is not None
    # export 记录入库
    export_id = r.headers["x-ppt-export-id"]
    rec = (await db.execute(select(CapaPptExport).where(CapaPptExport.export_id == uuid.UUID(export_id)))).scalar_one()
    assert rec.review_status == "skipped"


async def test_generate_ppt_archived_allowed(qe_client, db, admin_user, default_factory):
    capa = await _make_closed_capa(db, default_factory.id, admin_user.user_id, status="ARCHIVED")
    r = await qe_client.post(f"/api/capa/{capa.report_id}/ppt-export")
    assert r.status_code == 200


async def test_generate_ppt_not_closed_400(qe_client, db, admin_user, default_factory):
    capa = await _make_closed_capa(db, default_factory.id, admin_user.user_id, status="D7_PREVENTION")
    r = await qe_client.post(f"/api/capa/{capa.report_id}/ppt-export")
    assert r.status_code == 400


@pytest.fixture
async def viewer_client(db, admin_user, default_factory):
    """viewer (capa=1=VIEW) → 不可生成 PPT。"""
    await _seed_perm(db, admin_user.role_id, "capa", 1)  # VIEW
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_viewer_cannot_generate_ppt(viewer_client, db, admin_user, default_factory):
    capa = await _make_closed_capa(db, default_factory.id, admin_user.user_id)
    r = await viewer_client.post(f"/api/capa/{capa.report_id}/ppt-export")
    assert r.status_code == 403


async def test_get_export_detail(qe_client, db, admin_user, default_factory):
    capa = await _make_closed_capa(db, default_factory.id, admin_user.user_id)
    r = await qe_client.post(f"/api/capa/{capa.report_id}/ppt-export")
    export_id = r.headers["x-ppt-export-id"]
    r2 = await qe_client.get(f"/api/capa/{capa.report_id}/ppt-exports/{export_id}")
    assert r2.status_code == 200
    assert r2.json()["export_id"] == export_id


@pytest.fixture
async def no_capa_perm_client(db, admin_user, default_factory):
    """角色有 factory 访问但 CAPA 模块权限=0（NONE）→ 读 export 应 403。"""
    await _seed_perm(db, admin_user.role_id, "capa", 0)  # NONE
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_get_export_requires_capa_view(db, admin_user, default_factory):
    """get_ppt_export 必须校验 CAPA 模块 VIEW 权限（与同级 GET 端点一致），而非仅 factory 访问。"""
    capa = await _make_closed_capa(db, default_factory.id, admin_user.user_id)
    # 1. 用 CREATE 权限生成 export 记录
    await _seed_perm(db, admin_user.role_id, "capa", 2)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        gen = await ac.post(f"/api/capa/{capa.report_id}/ppt-export")
        assert gen.status_code == 200
        export_id = gen.headers["x-ppt-export-id"]
    # 2. 降到 NONE 权限再读 → 应 403
    await _seed_perm(db, admin_user.role_id, "capa", 0)
    transport2 = ASGITransport(app=app)
    async with AsyncClient(transport=transport2, base_url="http://test") as ac2:
        r = await ac2.get(f"/api/capa/{capa.report_id}/ppt-exports/{export_id}")
    assert r.status_code == 403
    app.dependency_overrides.clear()


async def test_generate_ppt_llm_runtime_error_returns_500(db, admin_user, default_factory, monkeypatch):
    """LLM 运行时异常（审查闭环异常，非未配置）→ 500（故事 §92 FAILED），不返回 200/needs_review，不落 export。"""
    # build_client 返回伪 client（不 raise ProviderNotConfigured）→ 走 LLM 审查路径
    async def _build(*a, **kw):
        return object()
    monkeypatch.setattr(provider_adapter, "build_client", _build)
    async def _boom(*a, **kw):
        raise RuntimeError("llm timeout")
    monkeypatch.setattr(provider_adapter, "complete_json", _boom)

    await _seed_perm(db, admin_user.role_id, "capa", 2)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    capa = await _make_closed_capa(db, default_factory.id, admin_user.user_id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(f"/api/capa/{capa.report_id}/ppt-export")
    assert r.status_code == 500
    # 失败不应落 export 记录
    rows = (await db.execute(select(CapaPptExport).where(CapaPptExport.capa_id == capa.report_id))).scalars().all()
    assert rows == []
    app.dependency_overrides.clear()
