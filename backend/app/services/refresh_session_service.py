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
    *, expires_at: datetime | None = None, session_id: uuid.UUID | None = None,
) -> tuple[str, datetime]:
    await db.execute(
        select(User.user_id)
        .where(User.user_id == user_id)
        .with_for_update()
    )
    await cleanup_expired_refresh_sessions(db, user_id)
    session_id = session_id or uuid.uuid4()
    token, expires = create_refresh_token(
        str(user_id),
        tenant_id=tenant_id,
        session_id=str(session_id),
        token_id=str(uuid.uuid4()),
        expires_at=expires_at,
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
    ):
        return None
    if session.token_hash != hash_refresh_token(raw_token):
        # The caller has verified the JWT signature. A predecessor of this
        # locked session is a replay: revoke the whole token family.
        session.revoked_at = now
        await db.flush()
        return None

    token, expires = create_refresh_token(
        str(user.user_id),
        tenant_id=payload.get("tenant_id"),
        session_id=str(session.session_id),
        token_id=str(uuid.uuid4()),
        expires_at=session.expires_at,
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
    if (locked_user is None or locked_user.refresh_token != raw_token
            or locked_user.refresh_token_expires is None or locked_user.refresh_token_expires < now):
        # Legacy JWTs have no sid; derive their upgraded family deterministically
        # without persisting plaintext or a second credential history table.
        await db.execute(update(UserRefreshSession).where(
            UserRefreshSession.session_id == _legacy_session_id(raw_token),
            UserRefreshSession.user_id == user.user_id,
            UserRefreshSession.revoked_at.is_(None),
        ).values(revoked_at=now))
        return None

    absolute_expiry = locked_user.refresh_token_expires
    locked_user.refresh_token = None
    locked_user.refresh_token_expires = None
    return await issue_refresh_session(
        db, locked_user.user_id, tenant_id=tenant_id,
        expires_at=absolute_expiry, session_id=_legacy_session_id(raw_token),
    )


def _legacy_session_id(raw_token: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "openqms:legacy-refresh:" + hash_refresh_token(raw_token))



async def revoke_refresh_session(db: AsyncSession, raw_token: str, payload: dict) -> None:
    """Revoke the family identified by an already signature-verified token."""
    try:
        user_id = uuid.UUID(payload["sub"])
        session_id = uuid.UUID(payload["sid"]) if "sid" in payload else None
    except (KeyError, TypeError, ValueError, AttributeError):
        return
    if session_id is not None:
        await db.execute(update(UserRefreshSession).where(
            UserRefreshSession.session_id == session_id,
            UserRefreshSession.user_id == user_id,
            UserRefreshSession.revoked_at.is_(None),
        ).values(revoked_at=datetime.now(UTC)))
    else:
        await db.execute(update(User).where(
            User.user_id == user_id, User.refresh_token == raw_token,
        ).values(refresh_token=None, refresh_token_expires=None))
        await db.execute(update(UserRefreshSession).where(
            UserRefreshSession.session_id == _legacy_session_id(raw_token),
            UserRefreshSession.user_id == user_id,
            UserRefreshSession.revoked_at.is_(None),
        ).values(revoked_at=datetime.now(UTC)))
