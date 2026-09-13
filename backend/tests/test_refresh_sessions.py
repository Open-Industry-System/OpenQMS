import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import delete, select, text

from app.api import auth as auth_api
from app.config import settings
from app.core.security import create_refresh_token, decode_refresh_token, hash_password
from app.database import get_db
from app.main import app
from app.models.role import RoleDefinition
from app.models.user import User
from app.models.user_refresh_session import UserRefreshSession
from app.services.refresh_session_service import issue_refresh_session

pytestmark = pytest.mark.requires_db

VALID_PASSWORD = "Viewer@2026"


@pytest.fixture(autouse=True)
def clear_login_rate_limiter():
    auth_api._login_attempts.clear()
    yield
    auth_api._login_attempts.clear()


async def make_loginable_viewer(db, default_factory, username: str) -> User:
    role = (
        await db.execute(
            select(RoleDefinition).where(RoleDefinition.role_key == "viewer")
        )
    ).scalar_one()
    user = User(
        user_id=uuid.uuid4(),
        username=username,
        display_name="Refresh Session Viewer",
        password_hash=hash_password(VALID_PASSWORD),
        role_id=role.id,
        legacy_role="viewer",
        is_active=True,
        factory_id=default_factory.id,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_refresh_sessions_allow_multiple_rows_per_user(db, admin_user):
    first = UserRefreshSession(
        session_id=uuid.uuid4(),
        user_id=admin_user.user_id,
        token_hash=hashlib.sha256(b"first").hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    second = UserRefreshSession(
        session_id=uuid.uuid4(),
        user_id=admin_user.user_id,
        token_hash=hashlib.sha256(b"second").hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add_all([first, second])
    await db.flush()

    rows = (
        await db.execute(
            select(UserRefreshSession).where(
                UserRefreshSession.user_id == admin_user.user_id
            )
        )
    ).scalars().all()
    assert {row.session_id for row in rows} == {
        first.session_id,
        second.session_id,
    }


@pytest.mark.asyncio
async def test_two_logins_create_two_refresh_sessions(
    admin_client, db, default_factory
):
    user = await make_loginable_viewer(
        db, default_factory, f"shared_viewer_{uuid.uuid4().hex[:8]}"
    )

    first = await admin_client.post(
        "/api/auth/login",
        json={"username": user.username, "password": VALID_PASSWORD},
    )
    second = await admin_client.post(
        "/api/auth/login",
        json={"username": user.username, "password": VALID_PASSWORD},
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["refresh_token"] != second.json()["refresh_token"]
    rows = (
        await db.execute(
            select(UserRefreshSession).where(
                UserRefreshSession.user_id == user.user_id,
                UserRefreshSession.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_rotating_one_session_invalidates_only_its_old_token(
    admin_client, db, default_factory
):
    user = await make_loginable_viewer(
        db, default_factory, f"rotating_viewer_{uuid.uuid4().hex[:8]}"
    )
    first_login = await admin_client.post(
        "/api/auth/login",
        json={"username": user.username, "password": VALID_PASSWORD},
    )
    second_login = await admin_client.post(
        "/api/auth/login",
        json={"username": user.username, "password": VALID_PASSWORD},
    )
    first_token = first_login.json()["refresh_token"]
    second_token = second_login.json()["refresh_token"]

    first_rotation = await admin_client.post(
        "/api/auth/refresh", json={"refresh_token": first_token}
    )
    first_reuse = await admin_client.post(
        "/api/auth/refresh", json={"refresh_token": first_token}
    )
    second_rotation = await admin_client.post(
        "/api/auth/refresh", json={"refresh_token": second_token}
    )

    assert first_rotation.status_code == 200
    assert first_reuse.status_code == 401
    assert second_rotation.status_code == 200
    rotated_first_token = first_rotation.json()["refresh_token"]
    first_payload = decode_refresh_token(first_token)
    rotated_first_payload = decode_refresh_token(rotated_first_token)
    assert first_payload is not None
    assert rotated_first_payload is not None
    assert rotated_first_payload["sid"] == first_payload["sid"]
    assert rotated_first_payload["jti"] != first_payload["jti"]
    assert rotated_first_token != first_token
    assert second_rotation.json()["refresh_token"] != second_token


@pytest.mark.asyncio
@pytest.mark.parametrize("session_state", ["expired", "revoked"])
async def test_expired_or_revoked_refresh_session_returns_401(
    admin_client, db, default_factory, session_state
):
    user = await make_loginable_viewer(
        db, default_factory, f"{session_state}_viewer_{uuid.uuid4().hex[:8]}"
    )
    login_response = await admin_client.post(
        "/api/auth/login",
        json={"username": user.username, "password": VALID_PASSWORD},
    )
    raw_token = login_response.json()["refresh_token"]
    payload = decode_refresh_token(raw_token)
    assert payload is not None
    assert payload.get("sid") is not None
    session = await db.get(UserRefreshSession, uuid.UUID(payload["sid"]))
    assert session is not None
    if session_state == "expired":
        session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    else:
        session.revoked_at = datetime.now(UTC)
    await db.flush()

    response = await admin_client.post(
        "/api/auth/refresh", json={"refresh_token": raw_token}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_legacy_refresh_token_upgrades_once_and_clears_legacy_fields(
    admin_client, db, default_factory
):
    user = await make_loginable_viewer(
        db, default_factory, f"legacy_viewer_{uuid.uuid4().hex[:8]}"
    )
    legacy_token, legacy_expires = create_refresh_token(str(user.user_id))
    user.refresh_token = legacy_token
    user.refresh_token_expires = legacy_expires
    await db.flush()

    upgraded = await admin_client.post(
        "/api/auth/refresh", json={"refresh_token": legacy_token}
    )
    reused = await admin_client.post(
        "/api/auth/refresh", json={"refresh_token": legacy_token}
    )

    assert upgraded.status_code == 200
    upgraded_token = upgraded.json()["refresh_token"]
    upgraded_payload = decode_refresh_token(upgraded_token)
    assert upgraded_payload is not None
    assert upgraded_payload.get("sid") is not None
    assert upgraded_payload.get("jti") is not None
    assert user.refresh_token is None
    assert user.refresh_token_expires is None
    rows = (
        await db.execute(
            select(UserRefreshSession).where(
                UserRefreshSession.user_id == user.user_id
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert reused.status_code == 401


@pytest.mark.asyncio
async def test_concurrent_rotation_of_same_token_has_at_most_one_success(sessionmaker):
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()
    raw_token = jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "jti": str(uuid.uuid4()),
            "type": "refresh",
            "exp": datetime.now(UTC) + timedelta(days=7),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    async with sessionmaker() as setup_db:
        role = (
            await setup_db.execute(
                select(RoleDefinition).where(RoleDefinition.role_key == "viewer")
            )
        ).scalar_one()
        setup_db.add(
            User(
                user_id=user_id,
                username=f"concurrent_viewer_{uuid.uuid4().hex[:8]}",
                display_name="Concurrent Refresh Viewer",
                password_hash="unused",
                role_id=role.id,
                legacy_role="viewer",
                is_active=True,
                factory_id=None,
            )
        )
        setup_db.add(
            UserRefreshSession(
                session_id=session_id,
                user_id=user_id,
                token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
        await setup_db.commit()

    async def request_db():
        async with sessionmaker() as session:
            yield session

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = request_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            responses = await asyncio.gather(
                client.post(
                    "/api/auth/refresh", json={"refresh_token": raw_token}
                ),
                client.post(
                    "/api/auth/refresh", json={"refresh_token": raw_token}
                ),
            )

        assert sorted(response.status_code for response in responses) == [200, 401]
        successful = next(response for response in responses if response.status_code == 200)
        new_token = successful.json()["refresh_token"]
        async with sessionmaker() as verify_db:
            session = await verify_db.get(UserRefreshSession, session_id)
            assert session is not None
            assert session.token_hash == hashlib.sha256(
                new_token.encode("utf-8")
            ).hexdigest()
            assert session.token_hash != hashlib.sha256(
                raw_token.encode("utf-8")
            ).hexdigest()
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
        async with sessionmaker() as cleanup_db:
            await cleanup_db.execute(
                delete(UserRefreshSession).where(
                    UserRefreshSession.user_id == user_id
                )
            )
            await cleanup_db.execute(delete(User).where(User.user_id == user_id))
            await cleanup_db.commit()


@pytest.mark.asyncio
async def test_issuance_locks_user_before_cleaning_expired_sessions(sessionmaker):
    user_id = uuid.uuid4()
    expired_session_id = uuid.uuid4()
    async with sessionmaker() as setup_db:
        role = (
            await setup_db.execute(
                select(RoleDefinition).where(RoleDefinition.role_key == "viewer")
            )
        ).scalar_one()
        setup_db.add(
            User(
                user_id=user_id,
                username=f"lock_order_viewer_{uuid.uuid4().hex[:8]}",
                display_name="Lock Order Viewer",
                password_hash="unused",
                role_id=role.id,
                legacy_role="viewer",
                is_active=True,
                factory_id=None,
            )
        )
        setup_db.add(
            UserRefreshSession(
                session_id=expired_session_id,
                user_id=user_id,
                token_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        await setup_db.commit()

    issue_task = None
    try:
        async with (
            sessionmaker() as user_lock_db,
            sessionmaker() as issue_db,
            sessionmaker() as observer_db,
        ):
            try:
                await user_lock_db.execute(
                    select(User.user_id)
                    .where(User.user_id == user_id)
                    .with_for_update()
                )
                issue_pid = await issue_db.scalar(text("SELECT pg_backend_pid()"))
                issue_task = asyncio.create_task(
                    issue_refresh_session(issue_db, user_id)
                )

                for _ in range(100):
                    wait_event_type = await observer_db.scalar(
                        text(
                            "SELECT wait_event_type FROM pg_stat_activity "
                            "WHERE pid = :pid"
                        ),
                        {"pid": issue_pid},
                    )
                    if wait_event_type == "Lock":
                        break
                    await asyncio.sleep(0.01)
                else:
                    pytest.fail("refresh issuance did not reach a database lock wait")

                unlocked_expired_session = (
                    await observer_db.execute(
                        select(UserRefreshSession.session_id)
                        .where(UserRefreshSession.session_id == expired_session_id)
                        .with_for_update(nowait=True)
                    )
                ).scalar_one()
                assert unlocked_expired_session == expired_session_id
                await observer_db.rollback()
                await user_lock_db.rollback()
                await asyncio.wait_for(issue_task, timeout=2)
            finally:
                await observer_db.rollback()
                await user_lock_db.rollback()
                if issue_task is not None:
                    await asyncio.gather(issue_task, return_exceptions=True)
                await issue_db.rollback()
    finally:
        async with sessionmaker() as cleanup_db:
            await cleanup_db.execute(
                delete(UserRefreshSession).where(
                    UserRefreshSession.user_id == user_id
                )
            )
            await cleanup_db.execute(delete(User).where(User.user_id == user_id))
            await cleanup_db.commit()
