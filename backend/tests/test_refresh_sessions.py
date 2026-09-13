import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.user_refresh_session import UserRefreshSession

pytestmark = pytest.mark.requires_db


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
