"""update_capa 冻结字段后端约束测试（US-E2E-01.3）：防 direct API 修改冻结字段。"""
import uuid
import pytest
from app.models.capa import CAPAEightD
from app.services.capa_service import update_capa

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, status, **extra):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-FRZ-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status=status, d5_correction="措施A",
        d6_verification="已验证", d7_prevention="预防", d8_closure="关闭报告",
        **extra,
    )
    db.add(capa); await db.flush()
    return capa


@pytest.mark.asyncio
async def test_d7_completed_freezes_d7_prevention(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D7_COMPLETED")
    with pytest.raises(ValueError, match="冻结字段不可修改"):
        await update_capa(db, capa, {"d7_prevention": "改写"}, admin_user.user_id)


@pytest.mark.asyncio
async def test_d7_completed_allows_other_fields(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D7_COMPLETED", d2_description="orig")
    await update_capa(db, capa, {"d2_description": "改"}, admin_user.user_id)
    await db.refresh(capa)
    assert capa.d2_description == "改"


@pytest.mark.parametrize("status", ["D8_GATE_PENDING", "D8_APPROVAL_PENDING"])
@pytest.mark.asyncio
async def test_d8_pending_states_freeze_d8_closure(status, db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, status)
    with pytest.raises(ValueError, match="冻结字段不可修改"):
        await update_capa(db, capa, {"d8_closure": "改写"}, admin_user.user_id)


@pytest.mark.asyncio
async def test_d8_closure_allows_d8_closure_edit(db, default_factory, admin_user):
    """例外：D8_CLOSURE 态 d8_closure 不冻结（关闭后可补报告）。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D8_CLOSURE")
    await update_capa(db, capa, {"d8_closure": "补报告"}, admin_user.user_id)
    await db.refresh(capa)
    assert capa.d8_closure == "补报告"


@pytest.mark.asyncio
async def test_d8_closure_freezes_d7_prevention(db, default_factory, admin_user):
    """D7 永久冻结：D8_CLOSURE 态也不可改 d7_prevention。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D8_CLOSURE")
    with pytest.raises(ValueError, match="冻结字段不可修改"):
        await update_capa(db, capa, {"d7_prevention": "改写"}, admin_user.user_id)


@pytest.mark.asyncio
async def test_archived_freezes_all(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "ARCHIVED")
    with pytest.raises(ValueError, match="冻结字段不可修改"):
        await update_capa(db, capa, {"d7_prevention": "改"}, admin_user.user_id)
    with pytest.raises(ValueError, match="冻结字段不可修改"):
        await update_capa(db, capa, {"d8_closure": "改"}, admin_user.user_id)


# ── HTTP 级：验证 API try/except 映 400（非 500）──
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.role import RolePermission
from tests.conftest import _scope_for


@pytest.fixture
async def capa_put_client(db, admin_user, default_factory):
    """复制自 test_capa_verification_api.py:24 capa_client（PUT 需 admin scope）。"""
    for mod, lvl in [("capa", 5), ("fmea", 5)]:
        existing = await db.execute(select(RolePermission).where(
            RolePermission.role_id == admin_user.role_id, RolePermission.module == mod))
        if existing.scalar_one_or_none() is None:
            db.add(RolePermission(role_id=admin_user.role_id, module=mod, permission_level=lvl))
    await db.flush()
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_put_frozen_field_returns_400_not_500(capa_put_client, db, default_factory, admin_user):
    """D7_COMPLETED 态 PUT d7_prevention → 400（非 500，验证 API 层 try/except）。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D7_COMPLETED")
    resp = await capa_put_client.put(f"/api/capa/{capa.report_id}", json={"d7_prevention": "改写"})
    assert resp.status_code == 400, f"expected 400, got {resp.status_code}"


@pytest.mark.asyncio
async def test_put_allowed_field_returns_200(capa_put_client, db, default_factory, admin_user):
    """D7_COMPLETED 态 PUT 非冻结字段 → 200。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, "D7_COMPLETED", d2_description="orig")
    resp = await capa_put_client.put(f"/api/capa/{capa.report_id}", json={"d2_description": "改"})
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
