import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.models.user_refresh_session import UserRefreshSession
from app.services.refresh_session_service import issue_refresh_session


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_startup_does_not_create_a_public_admin(sessionmaker, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "async_session", sessionmaker)
    monkeypatch.setattr(settings, "TENANT_MODE", "single")
    async with sessionmaker() as session:
        assert (await session.execute(select(User).where(User.username == "admin"))).scalar_one_or_none() is None
    from app.models.role import RoleDefinition
    role_id = None
    async with sessionmaker() as session:
        if (await session.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))).scalar_one_or_none() is None:
            role = RoleDefinition(role_key="admin", name_zh="管理员", name_en="Admin", bypass_row_level_security=True)
            session.add(role)
            await session.flush()
            role_id = role.id
            await session.commit()
    created_id = None
    try:
        async with main.lifespan(main.app):
            async with sessionmaker() as session:
                admin = (await session.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
                created_id = admin.user_id if admin else None
                assert admin is None
    finally:
        if created_id:
            from sqlalchemy import delete
            async with sessionmaker() as session:
                await session.execute(delete(User).where(User.user_id == created_id))
                await session.commit()
        if role_id:
            from sqlalchemy import delete
            async with sessionmaker() as session:
                await session.execute(delete(RoleDefinition).where(RoleDefinition.id == role_id))
                await session.commit()


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_existing_public_admin_password_is_rejected(admin_client, db, admin_user, monkeypatch):
    monkeypatch.setattr(settings, "E2E_MODE", False)
    admin_user.password_hash = hash_password("Admin@2026")
    await db.flush()
    response = await admin_client.post("/api/auth/login", json={"username": admin_user.username, "password": "Admin@2026"})
    assert response.status_code == 403
    sessions = (await db.execute(select(UserRefreshSession).where(UserRefreshSession.user_id == admin_user.user_id))).scalars().all()
    assert sessions == []


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_private_bootstrap_rotates_existing_admin_and_revokes_sessions(db, admin_user, monkeypatch):
    from app.cli.bootstrap_admin import bootstrap_admin
    monkeypatch.setattr(settings, "TENANT_MODE", "single")
    old, _ = await issue_refresh_session(db, admin_user.user_id)
    admin_user.refresh_token = "legacy-refresh"
    admin_user.refresh_token_expires = None
    await db.flush()
    fresh = "Installation-Only!2026!"
    user = await bootstrap_admin(db, username=admin_user.username, password=fresh, replace_existing=True)
    assert user.user_id == admin_user.user_id
    assert verify_password(fresh, user.password_hash)
    assert not verify_password("Admin@2026", user.password_hash)
    assert user.refresh_token is None
    sessions = (await db.execute(select(UserRefreshSession).where(UserRefreshSession.user_id == user.user_id))).scalars().all()
    assert len(sessions) == 1 and sessions[0].revoked_at is not None


@pytest.mark.asyncio
async def test_bootstrap_rejects_public_password_before_database_access(monkeypatch):
    from app.cli.bootstrap_admin import bootstrap_admin
    monkeypatch.setattr(settings, "TENANT_MODE", "single")
    db = AsyncMock()
    with pytest.raises(ValueError):
        await bootstrap_admin(db, username="admin", password="Admin@2026")
    db.execute.assert_not_awaited()


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_preupgrade_public_admin_cannot_refresh(admin_client, db, admin_user, monkeypatch, legacy):
    from app.core.security import create_refresh_token
    monkeypatch.setattr(settings, "E2E_MODE", False)
    admin_user.password_hash = hash_password("Admin@2026")
    if legacy:
        old, expiry = create_refresh_token(str(admin_user.user_id))
        admin_user.refresh_token, admin_user.refresh_token_expires = old, expiry
    else:
        old, _ = await issue_refresh_session(db, admin_user.user_id)
    await db.flush()
    response = await admin_client.post("/api/auth/refresh", json={"refresh_token": old})
    assert response.status_code == 401
    assert admin_user.refresh_token is None
    sessions = (await db.execute(select(UserRefreshSession).where(UserRefreshSession.user_id == admin_user.user_id))).scalars().all()
    assert all(row.revoked_at is not None for row in sessions)


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_preupgrade_public_admin_access_token_is_rejected(db, admin_user, monkeypatch):
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    from app.core.permissions import get_current_user
    from app.core.security import create_access_token
    monkeypatch.setattr(settings, "E2E_MODE", False)
    admin_user.password_hash = hash_password("Admin@2026")
    await db.flush()
    access = create_access_token({"sub": str(admin_user.user_id), "role_id": str(admin_user.role_id)})
    with pytest.raises(HTTPException) as error:
        await get_current_user(request=None, credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=access), db=db)
    assert error.value.status_code == 401
