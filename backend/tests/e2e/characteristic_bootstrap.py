"""Opt-in task-owned browser accounts only; never seeds business documents.

Run from backend with both owned URLs set. Manifest contains throwaway credentials
and must stay in ignored frontend/e2e/.storage-state/.
"""
import asyncio
import json
import os
import re
from pathlib import Path
import secrets
from urllib.parse import urlsplit
import uuid


def require_owned_database(env: dict) -> str:
    url = env.get('DATABASE_URL')
    if not url or env.get('TEST_DATABASE_URL') != url:
        raise ValueError('Both owned database URLs must be explicit and identical')
    parsed = urlsplit(url)
    if ((parsed.scheme, parsed.hostname, parsed.path) != (
        'postgresql+asyncpg', '127.0.0.1', '/qms_test'
    ) or parsed.port not in {55432, 55433} or parsed.query or parsed.fragment):
        raise ValueError('Only the task-owned loopback qms_test endpoint is authorized')
    if parsed.port == 55433:
        from tests.ci.owned_resources import verify_owned_instance
        verify_owned_instance(env)
    return url


def require_enabled_version_guards(rows) -> None:
    if not rows or any((mode.decode() if isinstance(mode, bytes) else mode) not in {"O", "A"} for _, mode in rows):
        raise ValueError("Normal version protection triggers must be enabled")


def require_invocation_tag(env: dict) -> str:
    tag = env.get('CHARACTERISTIC_RUN_TAG', '')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', tag):
        raise ValueError('A new safe CHARACTERISTIC_RUN_TAG is required; prior evidence is immutable')
    return tag


async def bootstrap() -> None:
    require_owned_database(os.environ)
    tag = require_invocation_tag(os.environ)
    path = Path(__file__).resolve().parents[3] / f'frontend/e2e/.storage-state/characteristic-owned-{tag}.json'
    if path.exists():
        raise ValueError('Invocation manifest already exists; select a fresh tag')
    # No app imports/default config resolution before the endpoint guard.
    from sqlalchemy import text
    from app.database import async_session, engine
    from app.core.security import hash_password
    from app.models.factory import Factory, UserFactory
    from app.models.product_line import ProductLine
    from app.models.role import RoleDefinition, RolePermission, UserProductLine
    from app.models.user import User

    run = uuid.uuid4().hex[:8]
    password = secrets.token_urlsafe(24)
    async with async_session() as db:
        triggers = (await db.execute(text("SELECT tgname, tgenabled FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN ('fmea_versions'::regclass, 'control_plan_versions'::regclass)"))).all()
        require_enabled_version_guards(triggers)
        factory = Factory(id=uuid.uuid4(), code=f'T11-{run}', name=f'Task11 isolated {run}')
        db.add(factory)
        await db.flush()
        pl = ProductLine(code=f'T11-{run}', name='SIMULATED characteristic acceptance', factory_id=factory.id)
        db.add(pl)
        await db.flush()
        accounts = {}
        for label, level in [('editor', 3), ('approver', 4)]:
            role = RoleDefinition(id=uuid.uuid4(), role_key=f't11_{label}_{run}', name_zh=f'专项测试 {label}', name_en=f'Task11 {label}', is_system=False, bypass_row_level_security=False)
            db.add(role)
            await db.flush()
            for module, permission in [('fmea', level), ('planning', level), ('dashboard', 1), ('special_characteristic', level)]:
                db.add(RolePermission(role_id=role.id, module=module, permission_level=permission))
            user = User(user_id=uuid.uuid4(), username=f't11_{label}_{run}', display_name=f'SIMULATED {label}', password_hash=hash_password(password), role_id=role.id, legacy_role='quality_engineer', factory_id=factory.id)
            db.add(user)
            await db.flush()
            db.add(UserFactory(user_id=user.user_id, factory_id=factory.id))
            db.add(UserProductLine(user_id=user.user_id, product_line_code=pl.code))
            accounts[label] = {'username': user.username, 'id': str(user.user_id)}
        await db.commit()
    manifest = {'run': run, 'factory_id': str(factory.id), 'product_line': pl.code, 'password': password, 'accounts': accounts, 'triggers': [name for name, _ in triggers]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(json.dumps(manifest))
    path.chmod(0o600)
    print(f'Owned Task11 bootstrap ready: run={run}, factory={factory.id}, product_line={pl.code}; credentials saved to ignored manifest')
    await engine.dispose()


if __name__ == '__main__':
    require_owned_database(os.environ)
    asyncio.run(bootstrap())
