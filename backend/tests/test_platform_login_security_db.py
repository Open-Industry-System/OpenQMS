"""Real shared-session/concurrency guarantees for platform rate limiting."""
import asyncio
import uuid

import pytest
from sqlalchemy import delete, select, text

from app.models.platform_login_attempt import PlatformLoginAttempt
from app.services.platform_login_limiter import consume_login_attempt, login_key


@pytest.mark.asyncio
async def test_platform_login_atomic_shared_limit_and_expiry(sessionmaker):
    email = "security-" + uuid.uuid4().hex + "@example.com"
    client_ip = "test-" + uuid.uuid4().hex
    unknown_email = "rotating-" + uuid.uuid4().hex + "@example.com"
    hashes = [login_key(email), login_key(client_ip), login_key(unknown_email)]

    async def attempt():
        async with sessionmaker() as session:
            return await consume_login_attempt(session, email, client_ip)

    try:
        results = await asyncio.gather(*(attempt() for _ in range(12)))
        assert results.count(True) == 10
        assert results.count(False) == 2
        # A different worker/session must still reject, even after request rollback.
        async with sessionmaker() as session:
            assert not await consume_login_attempt(session, email.upper(), client_ip)
            await session.rollback()
        async with sessionmaker() as session:
            assert not await consume_login_attempt(session, unknown_email, client_ip)
            assert (await session.execute(select(PlatformLoginAttempt).where(PlatformLoginAttempt.key_hash == login_key(unknown_email)))).scalar_one_or_none() is None
        async with sessionmaker() as session:
            rows = (await session.execute(select(PlatformLoginAttempt).where(PlatformLoginAttempt.key_hash.in_(hashes)))).scalars().all()
            assert len(rows) == 2
            assert {row.key_kind: row.attempts for row in rows} == {"ip": 11, "account": 10}
            await session.execute(text("UPDATE public.platform_login_attempts SET expires_at = statement_timestamp() - interval '1 second' WHERE key_hash = ANY(:hashes)"), {"hashes": hashes})
            await session.commit()
        assert await attempt()
    finally:
        async with sessionmaker() as session:
            await session.execute(delete(PlatformLoginAttempt).where(PlatformLoginAttempt.key_hash.in_(hashes)))
            await session.commit()
