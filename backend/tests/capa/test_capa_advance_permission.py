"""基于边的 advance 权限测试（US-E2E-01.3）：APPROVE 边 vs EDIT 边。

权限级别用 PermissionLevel 数值：NONE=0/VIEW=1/CREATE=2/EDIT=3/APPROVE=4/ADMIN=5。
- field_qe 行为 ≡ capa=EDIT(3)
- manager 行为 ≡ capa=APPROVE(4)

复用 test_capa_verification_api.py:97 的 low_perm_client_builder fixture（工厂：按指定 capa 权限级别构造 AsyncClient）。
该 fixture 已在 test_capa_verification_api.py 中定义——但 pytest fixture 不跨文件共享，
需把 low_perm_client_builder 复制到本文件（或抽到 conftest.py）。本计划采用「复制到本文件」最小改动。
"""
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


async def _make_capa(db, factory_id, user_id, status):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-PERM-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status=status, d5_correction="措施A",
        d6_verification="已验证", d7_prevention="预防",
    )
    db.add(capa); await db.flush()
    return capa


@pytest.fixture
async def perm_client_builder(db, admin_user, default_factory):
    """工厂：按指定 capa 权限级别构造 AsyncClient（复制自 test_capa_verification_api.py:97）。"""
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
async def test_field_qe_can_advance_d7_to_d7_completed(perm_client_builder, db, default_factory, admin_user):
    """D7_PREVENTION→D7_COMPLETED 是 EDIT 边，EDIT(3) 可推进（不 403）。
    注意：D7→D7_COMPLETED 需 node-action 完整性；未处置 → 400 也算权限放行（非 403）。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D7_PREVENTION")
    ac = await perm_client_builder(capa_level=3)  # EDIT
    async with ac:
        resp = await ac.post(f"/api/capa/{capa.report_id}/advance",
                             json={"target_state": "D7_COMPLETED"})
    assert resp.status_code != 403  # 权限放行（400 gate 阻断也算通过权限）


@pytest.mark.asyncio
async def test_field_qe_cannot_approve_d8_closure(perm_client_builder, db, default_factory, admin_user):
    """D8_APPROVAL_PENDING→D8_CLOSURE 是 APPROVE 边，EDIT(3) → 403。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D8_APPROVAL_PENDING")
    ac = await perm_client_builder(capa_level=3)  # EDIT
    async with ac:
        resp = await ac.post(f"/api/capa/{capa.report_id}/advance",
                             json={"target_state": "D8_CLOSURE"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_field_qe_cannot_reject(perm_client_builder, db, default_factory, admin_user):
    """D8_APPROVAL_PENDING→D7_PREVENTION（驳回）是 APPROVE 边，EDIT(3) → 403。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D8_APPROVAL_PENDING")
    ac = await perm_client_builder(capa_level=3)  # EDIT
    async with ac:
        resp = await ac.post(f"/api/capa/{capa.report_id}/advance",
                             json={"target_state": "D7_PREVENTION", "reject_reason": "x"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_field_qe_cannot_archive(perm_client_builder, db, default_factory, admin_user):
    """D8_CLOSURE→ARCHIVED（归档）是 APPROVE 边，EDIT(3) → 403。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D8_CLOSURE")
    ac = await perm_client_builder(capa_level=3)  # EDIT
    async with ac:
        resp = await ac.post(f"/api/capa/{capa.report_id}/advance", json={})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_manager_can_approve_d8_closure(perm_client_builder, db, default_factory, admin_user):
    """APPROVE(4) 可推进 D8_APPROVAL_PENDING→D8_CLOSURE。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D8_APPROVAL_PENDING")
    ac = await perm_client_builder(capa_level=4)  # APPROVE
    async with ac:
        resp = await ac.post(f"/api/capa/{capa.report_id}/advance",
                             json={"target_state": "D8_CLOSURE"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_manager_can_archive(perm_client_builder, db, default_factory, admin_user):
    """APPROVE(4) 可归档（D8_CLOSURE→ARCHIVED，target_state=None 线性）。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D8_CLOSURE")
    ac = await perm_client_builder(capa_level=4)  # APPROVE
    async with ac:
        resp = await ac.post(f"/api/capa/{capa.report_id}/advance", json={})
    assert resp.status_code == 200
