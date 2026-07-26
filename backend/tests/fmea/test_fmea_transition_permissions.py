"""N5 安全回归：transition 端点缺 EDIT 校验（越权）。

修复前：require_approve_permission 只在 target_status == "approved" 时校验 APPROVE，
任意已认证用户（哪怕 fmea 模块只有 VIEW(1)）也能执行 draft->in_review 等过渡。
修复后：所有过渡需 >= EDIT(3)；target_status == "approved" 另需 >= APPROVE(4)。

权限级别用 PermissionLevel 数值：NONE=0/VIEW=1/CREATE=2/EDIT=3/APPROVE=4/ADMIN=5。
测试 harness 复制自 tests/capa/test_capa_advance_permission.py（perm_client_builder），
FMEA 文档构造复制自 tests/fmea/test_fmea_version_factory_id.py（_make_fmea）。
"""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.fmea import FMEADocument
from app.models.role import RolePermission
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


async def _make_fmea(db, factory_id, user_id, status):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-N5-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=factory_id,
        status=status, created_by=user_id,
        # P1.10 起 draft→in_review 需 wizardScope.wizard_completed==true（422 门禁），
        # 这里置 True 以满足提交前提（不影响 VIEW/EDIT/APPROVE 权限断言）。
        graph_data={"nodes": [], "edges": [], "wizardScope": {"wizard_completed": True}},
    )
    db.add(fmea); await db.flush()
    return fmea


@pytest.fixture
async def perm_client_builder(db, admin_user, default_factory):
    """工厂：按指定 fmea 权限级别构造 AsyncClient（复制自 test_capa_advance_permission.py）。"""
    async def _build(fmea_level: int):
        existing = (await db.execute(select(RolePermission).where(
            RolePermission.role_id == admin_user.role_id, RolePermission.module == "fmea"))).scalar_one_or_none()
        if existing is None:
            db.add(RolePermission(role_id=admin_user.role_id, module="fmea", permission_level=fmea_level))
        else:
            existing.permission_level = fmea_level
        await db.flush()
        scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_request_scope] = lambda: scope
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield _build
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_view_only_cannot_transition(perm_client_builder, db, default_factory, admin_user):
    """Case A: VIEW(1) 用户对 draft FMEA 提交 in_review → 403（修复前：成功，即越权）。"""
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, "draft")
    ac = await perm_client_builder(fmea_level=1)  # VIEW
    async with ac:
        resp = await ac.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "in_review"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_edit_cannot_approve(perm_client_builder, db, default_factory, admin_user):
    """Case B: EDIT(3) 但无 APPROVE 的用户对 in_review FMEA 审批 approved → 403。"""
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, "in_review")
    ac = await perm_client_builder(fmea_level=3)  # EDIT
    async with ac:
        resp = await ac.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "approved"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_edit_can_submit(perm_client_builder, db, default_factory, admin_user):
    """正向控制：EDIT(3) 可提交 draft->in_review → 200（避免过度阻断合法流程）。"""
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, "draft")
    ac = await perm_client_builder(fmea_level=3)  # EDIT
    async with ac:
        resp = await ac.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "in_review"})
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_approve_can_approve(perm_client_builder, db, default_factory, admin_user):
    """正向控制：APPROVE(4) 可审批 in_review->approved → 200。"""
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, "in_review")
    ac = await perm_client_builder(fmea_level=4)  # APPROVE
    async with ac:
        resp = await ac.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "approved"})
    assert resp.status_code == 200, resp.text
