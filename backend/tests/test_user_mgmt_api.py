"""HTTP tests for PATCH/DELETE /api/auth/users/{id}, GET /api/auth/roles|factories."""
import uuid

import pytest
from sqlalchemy import select

from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.audit import AuditLog
from app.models.factory import Factory, UserFactory
from app.models.role import RoleDefinition, RolePermission
from app.models.user import User
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


async def _seed_user_mgmt_perm(db, role_id):
    existing = await db.execute(select(RolePermission).where(
        RolePermission.role_id == role_id, RolePermission.module == "user_mgmt"))
    if existing.scalar_one_or_none() is None:
        db.add(RolePermission(role_id=role_id, module="user_mgmt", permission_level=5))
        await db.flush()


@pytest.fixture
async def user_mgmt_client(db, admin_user, default_factory):
    """admin_client equivalent but with user_mgmt ADMIN permission seeded for the admin role."""
    await _seed_user_mgmt_perm(db, admin_user.role_id)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_user(db, username, role_key="viewer", factory_id=None):
    role = (await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == role_key))).scalar_one()
    u = User(user_id=uuid.uuid4(), username=username, display_name=username,
             password_hash="h", role_id=role.id, legacy_role=role_key, is_active=True, factory_id=factory_id)
    db.add(u); await db.flush(); await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_patch_update_display_name(user_mgmt_client, db, admin_user):
    target = await _make_user(db, "api_dn")
    resp = await user_mgmt_client.patch(f"/api/auth/users/{target.user_id}",
        json={"display_name": "NewName"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["display_name"] == "NewName"


@pytest.mark.asyncio
async def test_patch_password_reset(user_mgmt_client, db, admin_user):
    target = await _make_user(db, "api_pw")
    resp = await user_mgmt_client.patch(f"/api/auth/users/{target.user_id}",
        json={"password": "ValidPass123!"})
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_patch_password_weak_400(user_mgmt_client, db):
    target = await _make_user(db, "api_pw2")
    resp = await user_mgmt_client.patch(f"/api/auth/users/{target.user_id}",
        json={"password": "weak"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_factory_ids_replace(user_mgmt_client, db):
    target = await _make_user(db, "api_fi")
    f1 = Factory(id=uuid.uuid4(), code="APIF1", name="APIF1"); f2 = Factory(id=uuid.uuid4(), code="APIF2", name="APIF2")
    db.add_all([f1, f2]); await db.flush()
    resp = await user_mgmt_client.patch(f"/api/auth/users/{target.user_id}",
        json={"factory_ids": [str(f1.id), str(f2.id)], "default_factory_id": str(f1.id)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["factory_scope"]["default_factory_id"] == str(f1.id)
    ids = {f["id"] for f in body["factories"]}
    assert ids == {str(f1.id), str(f2.id)}


@pytest.mark.asyncio
async def test_patch_default_factory_not_in_set_400(user_mgmt_client, db):
    target = await _make_user(db, "api_df")
    f1 = Factory(id=uuid.uuid4(), code="ADF1", name="ADF1"); f2 = Factory(id=uuid.uuid4(), code="ADF2", name="ADF2")
    db.add_all([f1, f2]); await db.flush()
    resp = await user_mgmt_client.patch(f"/api/auth/users/{target.user_id}",
        json={"factory_ids": [str(f1.id)], "default_factory_id": str(f2.id)})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_non_nullable_null_400(user_mgmt_client, db):
    target = await _make_user(db, "api_nn")
    resp = await user_mgmt_client.patch(f"/api/auth/users/{target.user_id}", json={"role_key": None})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_self_deactivate_400(user_mgmt_client, admin_user):
    resp = await user_mgmt_client.patch(f"/api/auth/users/{admin_user.user_id}", json={"is_active": False})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_not_found_404(user_mgmt_client):
    resp = await user_mgmt_client.patch(f"/api/auth/users/{uuid.uuid4()}", json={"display_name": "x"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_forbidden_without_user_mgmt(db, default_factory):
    # temp role WITHOUT user_mgmt permission + temp user -> must get 403
    from httpx import ASGITransport, AsyncClient
    role = RoleDefinition(role_key="no_user_mgmt_test", name_zh="无用户管理", name_en="NoUM",
                          is_system=False, is_active=True)
    db.add(role); await db.flush()
    user = User(user_id=uuid.uuid4(), username="no_um_user", display_name="N",
                password_hash="h", role_id=role.id, legacy_role="no_user_mgmt_test",
                is_active=True, factory_id=default_factory.id)
    db.add(user); await db.flush()
    scope = _scope_for(user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch(f"/api/auth/users/{user.user_id}", json={"display_name": "x"})
            assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_user_success(user_mgmt_client, db, admin_user, default_factory):
    target = await _make_user(db, "api_del", factory_id=default_factory.id)
    resp = await user_mgmt_client.delete(f"/api/auth/users/{target.user_id}")
    assert resp.status_code == 200, resp.text
    assert (await db.execute(select(User).where(User.user_id == target.user_id))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_self_400(user_mgmt_client, admin_user):
    resp = await user_mgmt_client.delete(f"/api/auth/users/{admin_user.user_id}")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_blocked_by_fk_409(user_mgmt_client, db, admin_user, default_factory):
    target = await _make_user(db, "api_fk", factory_id=default_factory.id)
    # audit_log.operated_by has FK to users (NO ondelete -> RESTRICT)
    db.add(AuditLog(table_name="users", record_id=target.user_id, action="UPDATE",
                    changed_fields={}, operated_by=target.user_id))
    await db.flush()
    resp = await user_mgmt_client.delete(f"/api/auth/users/{target.user_id}")
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_get_roles(user_mgmt_client):
    resp = await user_mgmt_client.get("/api/auth/roles")
    assert resp.status_code == 200
    body = resp.json()
    assert all({"role_key", "name_zh", "name_en"} <= set(r.keys()) for r in body)


@pytest.mark.asyncio
async def test_get_factories(user_mgmt_client, default_factory):
    resp = await user_mgmt_client.get("/api/auth/factories")
    assert resp.status_code == 200
    body = resp.json()
    assert all({"id", "code", "name", "is_active"} <= set(f.keys()) for f in body)
    assert all(f["is_active"] for f in body)
