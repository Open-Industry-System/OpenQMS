"""Database-atomic fixed-window limits shared by every platform worker."""
import hashlib

from sqlalchemy import text

ATTEMPT_LIMIT = 10
WINDOW_SECONDS = 300


def login_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def consume_login_attempt(db, email: str, client_ip: str) -> bool:
    # Bounded indexed cleanup in a separate transaction: never hold expiry locks
    # while waiting for a live limiter key in another request.
    await db.execute(text("""
        DELETE FROM public.platform_login_attempts
        WHERE (key_kind, key_hash) IN (
            SELECT key_kind, key_hash FROM public.platform_login_attempts
            WHERE expires_at <= statement_timestamp()
            ORDER BY expires_at, key_kind, key_hash LIMIT 100
            FOR UPDATE SKIP LOCKED
        )
    """))
    await db.commit()
    # Every request locks IP before account; blocked IPs cannot allocate account keys.
    for kind, value in (("ip", client_ip), ("account", email.strip().casefold())):
        result = await db.execute(text("""
            INSERT INTO public.platform_login_attempts (key_kind, key_hash, attempts, expires_at)
            VALUES (:kind, :key_hash, 1, statement_timestamp() + :window * interval '1 second')
            ON CONFLICT (key_kind, key_hash) DO UPDATE SET
                attempts = CASE WHEN platform_login_attempts.expires_at <= statement_timestamp()
                    THEN 1 ELSE least(platform_login_attempts.attempts + 1, :cap) END,
                expires_at = CASE WHEN platform_login_attempts.expires_at <= statement_timestamp()
                    THEN statement_timestamp() + :window * interval '1 second'
                    ELSE platform_login_attempts.expires_at END
            RETURNING attempts
        """), {"kind": kind, "key_hash": login_key(value), "window": WINDOW_SECONDS, "cap": ATTEMPT_LIMIT + 1})
        if result.scalar_one() > ATTEMPT_LIMIT:
            await db.commit()
            return False
    # Persist attempts before the endpoint raises and request teardown rolls back.
    await db.commit()
    return True
