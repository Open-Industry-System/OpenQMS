#!/usr/bin/env python3
"""Trusted initializer, mounted read-only and run ONLY inside isolated preview backend.

Only viewer/Viewer@2026 is public. Privileged credentials are random, never
emitted or persisted; operators may reset them through a reviewed private flow.
"""
import asyncio
import os
import re
import secrets
import subprocess
import sys
from urllib.parse import urlsplit


def validate_target(environ):
    if not re.fullmatch(r'[1-9][0-9]{0,8}', environ.get('PREVIEW_PR', '')):
        raise ValueError('numeric preview identity required')
    parsed=urlsplit(environ.get('DATABASE_URL',''))
    if parsed.scheme != 'postgresql+asyncpg' or parsed.hostname != 'db' or parsed.path != '/qms_preview':
        raise ValueError('initializer requires isolated preview database')


def seed_if_empty(user_count, runner=subprocess.run):
    if type(user_count) is not int or user_count < 0:
        raise ValueError('invalid user inventory')
    if user_count == 0:
        # Candidate application executes solely inside the restricted preview
        # container. No host interpreter imports candidate code; output suppressed
        # because candidate seed output cannot be trusted to redact credentials.
        runner([sys.executable,'-m','app.seed','--no-print-credentials'], check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)


async def initialize():
    validate_target(os.environ)
    import bcrypt
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    engine=create_async_engine(os.environ['DATABASE_URL'])
    try:
        async with engine.connect() as connection:
            if await connection.scalar(text('SELECT current_database()')) != 'qms_preview':
                raise ValueError('runtime preview database mismatch')
            # Session-level lock remains held while seed uses its own connection.
            await connection.execute(text('SELECT pg_advisory_lock(728913702)'))
            try:
                # Alembic creates a fixed FK-only system identity before seed.
                # Exclude only that exact identity; any real user prevents seeding.
                count=await connection.scalar(text("SELECT count(*) FROM users WHERE NOT (user_id='00000000-0000-0000-0000-000000000001' AND username='system')"))
                seed_if_empty(count)
                # Refresh the transaction snapshot after a separate seed process.
                await connection.commit()
                users=(await connection.execute(text("SELECT u.user_id,u.username FROM users u JOIN role_definitions r ON r.id=u.role_id WHERE u.username <> 'viewer'"))).all()
                if not {'admin','groupadmin','engineer','manager'} <= {row.username for row in users}:
                    raise ValueError('preview privileged account inventory incomplete')
                for row in users:
                    digest=bcrypt.hashpw(secrets.token_urlsafe(36).encode(),bcrypt.gensalt()).decode()
                    await connection.execute(text('UPDATE users SET password_hash=:digest,is_active=false,refresh_token=NULL,refresh_token_expires=NULL WHERE user_id=:identity'),dict(digest=digest,identity=row.user_id))
                    await connection.execute(text('UPDATE user_refresh_sessions SET revoked_at=COALESCE(revoked_at,now()) WHERE user_id=:identity'),dict(identity=row.user_id))
                viewer=(await connection.execute(text("SELECT u.password_hash,r.role_key FROM users u JOIN role_definitions r ON r.id=u.role_id WHERE u.username='viewer' AND u.is_active"))).one()
                if viewer.role_key != 'viewer' or not bcrypt.checkpw(b'Viewer@2026',viewer.password_hash.encode()):
                    raise ValueError('public readonly preview login unavailable')
                await connection.commit()
            finally:
                await connection.execute(text('SELECT pg_advisory_unlock(728913702)'))
                await connection.commit()
    finally:
        await engine.dispose()

if __name__=='__main__':
    asyncio.run(initialize())
