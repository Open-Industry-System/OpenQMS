import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_refresh_token
from app.models.user import User
from app.models.user_refresh_session import UserRefreshSession


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def cleanup_expired_refresh_sessions(
    db: AsyncSession, user_id: uuid.UUID
) -> None:
    await db.execute(
        delete(UserRefreshSession).where(
            UserRefreshSession.user_id == user_id,
            UserRefreshSession.expires_at < datetime.now(UTC),
        )
    )


async def revoke_all_refresh_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    revoked_at: datetime | None = None,
) -> None:
    timestamp = revoked_at or datetime.now(UTC)
    await db.execute(
        update(UserRefreshSession)
        .where(
            UserRefreshSession.user_id == user_id,
            UserRefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=timestamp)
    )


async def issue_refresh_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    tenant_id: str | None = None,
) -> tuple[str, datetime]:
    await db.execute(
        select(User.user_id)
        .where(User.user_id == user_id)
        .with_for_update()
    )
    await cleanup_expired_refresh_sessions(db, user_id)
    session_id = uuid.uuid4()
    token, expires = create_refresh_token(
        str(user_id),
        tenant_id=tenant_id,
        session_id=str(session_id),
        token_id=str(uuid.uuid4()),
    )
    db.add(
        UserRefreshSession(
            session_id=session_id,
            user_id=user_id,
            token_hash=hash_refresh_token(token),
            expires_at=expires,
        )
    )
    await db.flush()
    return token, expires


async def rotate_refresh_session(
    db: AsyncSession,
    user: User,
    raw_token: str,
    payload: dict,
) -> tuple[str, datetime] | None:
    try:
        session_id = uuid.UUID(payload["sid"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return None

    result = await db.execute(
        select(UserRefreshSession)
        .where(
            UserRefreshSession.session_id == session_id,
            UserRefreshSession.user_id == user.user_id,
        )
        .with_for_update()
    )
    session = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at < now
        or session.token_hash != hash_refresh_token(raw_token)
    ):
        return None

    token, expires = create_refresh_token(
        str(user.user_id),
        tenant_id=payload.get("tenant_id"),
        session_id=str(session.session_id),
        token_id=str(uuid.uuid4()),
    )
    session.token_hash = hash_refresh_token(token)
    session.expires_at = expires
    session.rotated_at = now
    await db.flush()
    return token, expires


async def upgrade_legacy_refresh_token(
    db: AsyncSession,
    user: User,
    raw_token: str,
    tenant_id: str | None = None,
) -> tuple[str, datetime] | None:
    result = await db.execute(
        select(User)
        .where(User.user_id == user.user_id)
        .with_for_update(of=User)
        .execution_options(populate_existing=True)
    )
    locked_user = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if (
        locked_user is None
        or locked_user.refresh_token != raw_token
        or locked_user.refresh_token_expires is None
        or locked_user.refresh_token_expires < now
    ):
        return None

    locked_user.refresh_token = None
    locked_user.refresh_token_expires = None
    return await issue_refresh_session(
        db,
        locked_user.user_id,
        tenant_id=tenant_id,
    )
