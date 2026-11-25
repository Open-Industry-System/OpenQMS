#!/usr/bin/env python3
"""Trusted initializer, mounted read-only and run ONLY inside isolated preview backend.

The ordinary preview enables only the public viewer. A shared lease may add
rotated acceptance credentials plus two public synthetic demonstration users.
"""
import asyncio
import json
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


SHARED_ROLES = {'engineer': 'field_qe', 'manager': 'manager'}
PUBLIC_VIEWER = {'username': 'viewer', 'password': 'Viewer@2026'}
# These fixture passwords are deliberately displayed only on the shared preview.
# D4 acceptance keeps the separate, randomly issued engineer and manager accounts.
PUBLIC_DEMO_USERS = {
    'demo-engineer': ('engineer', 'Quality Engineer (public demo)', 'DemoEngineer@2026'),
    'demo-manager': ('manager', 'Quality Manager (public demo)', 'DemoManager@2026'),
}
ISSUED_HASH = re.compile(r'\$2[aby]\$12\$[A-Za-z0-9./]{53}')


def read_account_hashes(argv, stdin):
    if not argv:
        return {}
    if argv != ['--shared-accounts']:
        raise ValueError('unsupported preview initializer invocation')
    raw = stdin.read(1025)
    if not raw or len(raw) > 1024:
        raise ValueError('invalid shared account hash input length')
    accounts = json.loads(raw)
    if (not isinstance(accounts, dict) or set(accounts) != set(SHARED_ROLES)
            or any(not isinstance(value, str) or not ISSUED_HASH.fullmatch(value)
                   for value in accounts.values())
            or len(set(accounts.values())) != len(accounts)):
        raise ValueError('invalid shared account hashes')
    return accounts


def account_role_is_expected(row):
    return SHARED_ROLES.get(row.username) == row.role_key


def public_demo_accounts():
    return [
        {'username': username, 'password': password}
        for username, (_, _, password) in PUBLIC_DEMO_USERS.items()
    ]


async def enable_public_demo_users(connection, text, hash_password, sources):
    for username, (source, display_name, password) in PUBLIC_DEMO_USERS.items():
        source_user = sources[source]
        role = SHARED_ROLES[source]
        digest = hash_password(password)
        await connection.execute(text("""
            INSERT INTO users (user_id, username, display_name, password_hash,
                               role_id, legacy_role, factory_id, is_active)
            SELECT gen_random_uuid(), :username, :display_name, :digest,
                   role_id, :role, factory_id, false
            FROM users WHERE user_id = :source_id
            ON CONFLICT (username) DO NOTHING
        """), dict(username=username, display_name=display_name, digest=digest, role=role, source_id=source_user.user_id))
        demo = (await connection.execute(text("""
            SELECT u.user_id, r.role_key FROM users u
            JOIN role_definitions r ON r.id=u.role_id WHERE u.username=:username
        """), {'username': username})).one()
        if demo.role_key != role:
            raise ValueError('shared demo account role mismatch')
        ids = dict(demo_id=demo.user_id, source_id=source_user.user_id)
        await connection.execute(text("""
            UPDATE users AS demo SET factory_id = source.factory_id, legacy_role = :role
            FROM users AS source WHERE demo.user_id=:demo_id AND source.user_id=:source_id
        """), dict(ids, role=role))
        # Keep direct scope assignments the same as the corresponding role fixture.
        for table, scope in (('user_factories', 'factory_id'), ('user_product_lines', 'product_line_code')):
            await connection.execute(text(f'DELETE FROM {table} WHERE user_id=:demo_id'), ids)
            await connection.execute(text(f"""
                INSERT INTO {table} (id, user_id, {scope})
                SELECT gen_random_uuid(), :demo_id, {scope} FROM {table} WHERE user_id=:source_id
            """), ids)
        yield demo.user_id, digest


async def initialize(accounts):
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
                users=(await connection.execute(text("SELECT u.user_id,u.username,r.role_key FROM users u JOIN role_definitions r ON r.id=u.role_id WHERE u.username <> 'viewer'"))).all()
                if not {'admin','groupadmin','engineer','manager'} <= {row.username for row in users}:
                    raise ValueError('preview privileged account inventory incomplete')

                def hash_password(password):
                    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

                enabled = {row.user_id: accounts[row.username] for row in users if row.username in accounts}
                if accounts:
                    sources = {row.username: row for row in users if account_role_is_expected(row)}
                    if sources.keys() != accounts.keys():
                        raise ValueError('synthetic business account role mismatch')
                    async for identity, digest in enable_public_demo_users(connection, text, hash_password, sources):
                        enabled[identity] = digest

                for identity in {row.user_id for row in users} | enabled.keys():
                    digest = enabled[identity] if identity in enabled else hash_password(secrets.token_urlsafe(36))
                    await connection.execute(
                        text('UPDATE users SET password_hash=:digest,is_active=:active,refresh_token=NULL,refresh_token_expires=NULL WHERE user_id=:identity'),
                        dict(digest=digest, active=identity in enabled, identity=identity),
                    )
                    await connection.execute(text('UPDATE user_refresh_sessions SET revoked_at=COALESCE(revoked_at,now()) WHERE user_id=:identity'),dict(identity=identity))
                viewer=(await connection.execute(text("SELECT u.password_hash,r.role_key FROM users u JOIN role_definitions r ON r.id=u.role_id WHERE u.username='viewer' AND u.is_active"))).one()
                if viewer.role_key != 'viewer' or not bcrypt.checkpw(PUBLIC_VIEWER['password'].encode(),viewer.password_hash.encode()):
                    raise ValueError('public readonly preview login unavailable')
                await connection.commit()
            finally:
                await connection.rollback()
                await connection.execute(text('SELECT pg_advisory_unlock(728913702)'))
                await connection.commit()
    finally:
        await engine.dispose()

if __name__=='__main__':
    asyncio.run(initialize(read_account_hashes(sys.argv[1:], sys.stdin.buffer)))
