"""login() must write a login_audit_logs row on success and failure."""
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.login_audit_log import LoginAuditLog
from app.models.role import RoleDefinition
from app.models.user import User

pytestmark = pytest.mark.requires_db

VALID_PASSWORD = "ValidPass123!"


async def _make_loginable_user(db, default_factory, role, username="loginlog_user"):
    user = User(
        user_id=uuid.uuid4(),
        username=username,
        display_name="Login Log",
        password_hash=hash_password(VALID_PASSWORD),
        role_id=role.id,
        legacy_role=role.role_key,
        is_active=True,
        factory_id=default_factory.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_login_success_writes_log(admin_client, db, default_factory):
    # ensure admin role + a loginable user
    from sqlalchemy import select as _sel
    role = (await db.execute(_sel(RoleDefinition).where(RoleDefinition.role_key == "admin"))).scalar_one()
    user = await _make_loginable_user(db, default_factory, role, username="ll_success")
    resp = await admin_client.post("/api/auth/login", json={"username": user.username, "password": VALID_PASSWORD})
    assert resp.status_code == 200, resp.text
    rows = (await db.execute(select(LoginAuditLog).where(LoginAuditLog.username == user.username))).scalars().all()
    assert len(rows) == 1
    assert rows[0].success is True
    assert rows[0].user_id == user.user_id
    assert rows[0].ip_address is not None


@pytest.mark.asyncio
async def test_login_failure_writes_log(admin_client, db, default_factory):
    from sqlalchemy import select as _sel
    role = (await db.execute(_sel(RoleDefinition).where(RoleDefinition.role_key == "admin"))).scalar_one()
    user = await _make_loginable_user(db, default_factory, role, username="ll_fail")
    resp = await admin_client.post("/api/auth/login", json={"username": user.username, "password": "WrongPass9!"})
    assert resp.status_code == 401
    rows = (await db.execute(select(LoginAuditLog).where(LoginAuditLog.username == user.username))).scalars().all()
    assert len(rows) == 1
    assert rows[0].success is False
    assert rows[0].user_id is None
    assert rows[0].failure_reason is not None
