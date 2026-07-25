"""user_service.update_user / delete_user — validation, guards, factory set (DB)."""
import uuid

import pytest
from sqlalchemy import select

from app.models.factory import Factory, UserFactory
from app.models.role import RoleDefinition
from app.models.user import User
from app.services import user_service

pytestmark = pytest.mark.requires_db


async def _make_user(db, username, role_key="viewer", factory_id=None):
    role = (await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == role_key))).scalar_one_or_none()
    if role is None:
        # Destructive tests (test_apqp_service/test_ppap_service/test_spc_fmea_match)
        # Base.metadata.drop_all+create_all the shared test DB mid-suite, wiping
        # 028's seeded roles. The last-admin tests below use only the `db` fixture
        # (not admin_user, which re-seeds roles), so recreate the role idempotently
        # to stay self-sufficient.
        role = RoleDefinition(role_key=role_key, name_zh=role_key, name_en=role_key,
                              is_system=True, is_active=True)
        db.add(role); await db.flush()
    u = User(user_id=uuid.uuid4(), username=username, display_name=username,
             password_hash="h", role_id=role.id, legacy_role=role_key, is_active=True,
             factory_id=factory_id)
    db.add(u); await db.flush(); await db.refresh(u)
    return u


async def _make_factory(db, code):
    f = Factory(id=uuid.uuid4(), code=code, name=code)
    db.add(f); await db.flush(); await db.refresh(f)
    return f


@pytest.mark.asyncio
async def test_update_display_name_and_email(db, admin_user):
    target = await _make_user(db, "t_dn")
    user = await user_service.update_user(db, target.user_id,
        {"display_name": "New", "email": "n@x.com"}, admin_user.user_id)
    assert user.display_name == "New" and user.email == "n@x.com"


@pytest.mark.asyncio
async def test_update_email_empty_string_clears(db, admin_user):
    target = await _make_user(db, "t_em", factory_id=None)
    user = await user_service.update_user(db, target.user_id, {"email": "  "}, admin_user.user_id)
    assert user.email is None


@pytest.mark.asyncio
async def test_update_password_resets_hash_and_refresh_token(db, admin_user):
    target = await _make_user(db, "t_pw")
    target.refresh_token = "old"; await db.flush()
    user = await user_service.update_user(db, target.user_id, {"password": "ValidPass123!"}, admin_user.user_id)
    assert user.password_hash != "h"
    assert user.refresh_token is None and user.refresh_token_expires is None


@pytest.mark.asyncio
async def test_update_password_weak_raises(db, admin_user):
    target = await _make_user(db, "t_pw2")
    with pytest.raises(ValueError):
        await user_service.update_user(db, target.user_id, {"password": "weak"}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_password_weak_rolls_back_factory_ids(db, admin_user, default_factory):
    target = await _make_user(db, "t_pw3")
    f = await _make_factory(db, "F_PW3")
    # weak password + valid factory_ids together -> raises and factories NOT applied
    with pytest.raises(ValueError):
        await user_service.update_user(db, target.user_id,
            {"password": "weak", "factory_ids": [f.id]}, admin_user.user_id)
    rows = (await db.execute(select(UserFactory).where(UserFactory.user_id == target.user_id))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_update_role_key_invalid_raises(db, admin_user):
    target = await _make_user(db, "t_rk")
    with pytest.raises(ValueError):
        await user_service.update_user(db, target.user_id, {"role_key": "nope"}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_role_key_valid(db, admin_user):
    target = await _make_user(db, "t_rk2", role_key="viewer")
    user = await user_service.update_user(db, target.user_id, {"role_key": "manager"}, admin_user.user_id)
    assert user.legacy_role == "manager"


@pytest.mark.asyncio
async def test_update_factory_ids_replace(db, admin_user):
    target = await _make_user(db, "t_fi")
    f1 = await _make_factory(db, "F1"); f2 = await _make_factory(db, "F2")
    db.add(UserFactory(user_id=target.user_id, factory_id=f1.id)); await db.flush()
    await user_service.update_user(db, target.user_id, {"factory_ids": [f2.id]}, admin_user.user_id)
    ids = {r.factory_id for r in (await db.execute(select(UserFactory).where(UserFactory.user_id == target.user_id))).scalars().all()}
    assert ids == {f2.id}


@pytest.mark.asyncio
async def test_update_factory_ids_invalid_id_raises(db, admin_user):
    target = await _make_user(db, "t_fi2")
    with pytest.raises(ValueError):
        await user_service.update_user(db, target.user_id, {"factory_ids": [uuid.uuid4()]}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_factory_ids_duplicate_raises(db, admin_user):
    target = await _make_user(db, "t_dup")
    f1 = await _make_factory(db, "FDUP")
    with pytest.raises(ValueError):
        await user_service.update_user(db, target.user_id, {"factory_ids": [f1.id, f1.id]}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_factory_ids_empty_clears_and_default_to_none(db, admin_user, default_factory):
    target = await _make_user(db, "t_fi3", factory_id=default_factory.id)
    f = await _make_factory(db, "F_CLR")
    db.add(UserFactory(user_id=target.user_id, factory_id=f.id)); await db.flush()
    user = await user_service.update_user(db, target.user_id, {"factory_ids": []}, admin_user.user_id)
    assert user.factory_id is None
    rows = (await db.execute(select(UserFactory).where(UserFactory.user_id == target.user_id))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_update_factory_ids_auto_adjusts_default_to_first(db, admin_user):
    target = await _make_user(db, "t_fi4", factory_id=None)
    f1 = await _make_factory(db, "FA1"); f2 = await _make_factory(db, "FA2")
    user = await user_service.update_user(db, target.user_id, {"factory_ids": [f1.id, f2.id]}, admin_user.user_id)
    assert user.factory_id == f1.id


@pytest.mark.asyncio
async def test_update_default_factory_not_in_set_raises(db, admin_user):
    target = await _make_user(db, "t_df")
    f1 = await _make_factory(db, "FB1"); f2 = await _make_factory(db, "FB2")
    db.add(UserFactory(user_id=target.user_id, factory_id=f1.id)); await db.flush()
    with pytest.raises(ValueError):
        await user_service.update_user(db, target.user_id, {"default_factory_id": f2.id}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_default_factory_null_clears(db, admin_user, default_factory):
    target = await _make_user(db, "t_df2", factory_id=default_factory.id)
    user = await user_service.update_user(db, target.user_id, {"default_factory_id": None}, admin_user.user_id)
    assert user.factory_id is None


@pytest.mark.asyncio
async def test_update_non_nullable_null_rejected(db, admin_user):
    target = await _make_user(db, "t_nn")
    for key in ("role_key", "password", "is_active", "factory_ids"):
        with pytest.raises(ValueError):
            await user_service.update_user(db, target.user_id, {key: None}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_self_deactivate_raises(db, admin_user):
    with pytest.raises(ValueError):
        await user_service.update_user(db, admin_user.user_id, {"is_active": False}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_not_found_raises(db, admin_user):
    with pytest.raises(LookupError):
        await user_service.update_user(db, uuid.uuid4(), {"display_name": "x"}, admin_user.user_id)


@pytest.mark.asyncio
async def test_update_last_admin_deactivate_raises(db, default_factory):
    # actor: a non-admin role with no admin privileges; target: the only active admin
    mgr_role = RoleDefinition(role_key="user_mgr_test", name_zh="用户管理员", name_en="User Mgr",
                              is_system=False, is_active=True)
    db.add(mgr_role); await db.flush()
    actor = User(user_id=uuid.uuid4(), username="mgr_actor", display_name="M",
                 password_hash="h", role_id=mgr_role.id, legacy_role="user_mgr_test",
                 is_active=True, factory_id=default_factory.id)
    db.add(actor); await db.flush()
    target_admin = await _make_user(db, "only_admin", role_key="admin", factory_id=default_factory.id)
    # neutralize any pre-existing active admins so target is the last one
    result = await db.execute(select(User).where(User.is_active == True))  # noqa: E712
    for u in result.scalars().all():
        if u.role_definition.role_key == "admin" and u.user_id != target_admin.user_id:
            u.is_active = False
    await db.flush()
    with pytest.raises(ValueError):
        await user_service.update_user(db, target_admin.user_id, {"is_active": False}, actor.user_id)
    with pytest.raises(ValueError):
        await user_service.update_user(db, target_admin.user_id, {"role_key": "viewer"}, actor.user_id)


@pytest.mark.asyncio
async def test_delete_user_success(db, admin_user, default_factory):
    target = await _make_user(db, "t_del", factory_id=default_factory.id)
    f = await _make_factory(db, "F_DEL")
    db.add(UserFactory(user_id=target.user_id, factory_id=f.id)); await db.flush()
    await user_service.delete_user(db, target.user_id, admin_user.user_id)
    await db.flush()
    assert (await db.execute(select(User).where(User.user_id == target.user_id))).scalar_one_or_none() is None
    # user_factories cascaded
    rows = (await db.execute(select(UserFactory).where(UserFactory.user_id == target.user_id))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_delete_self_raises(db, admin_user):
    with pytest.raises(ValueError):
        await user_service.delete_user(db, admin_user.user_id, admin_user.user_id)


@pytest.mark.asyncio
async def test_delete_not_found_raises(db, admin_user):
    with pytest.raises(LookupError):
        await user_service.delete_user(db, uuid.uuid4(), admin_user.user_id)


@pytest.mark.asyncio
async def test_delete_last_admin_raises(db, default_factory):
    mgr_role = RoleDefinition(role_key="user_mgr_test2", name_zh="用户管理员", name_en="User Mgr",
                              is_system=False, is_active=True)
    db.add(mgr_role); await db.flush()
    actor = User(user_id=uuid.uuid4(), username="mgr_actor2", display_name="M",
                 password_hash="h", role_id=mgr_role.id, legacy_role="user_mgr_test2",
                 is_active=True, factory_id=default_factory.id)
    db.add(actor); await db.flush()
    target_admin = await _make_user(db, "only_admin2", role_key="admin", factory_id=default_factory.id)
    # neutralize any pre-existing active admins so target is the last one
    result = await db.execute(select(User).where(User.is_active == True))  # noqa: E712
    for u in result.scalars().all():
        if u.role_definition.role_key == "admin" and u.user_id != target_admin.user_id:
            u.is_active = False
    await db.flush()
    with pytest.raises(ValueError):
        await user_service.delete_user(db, target_admin.user_id, actor.user_id)
