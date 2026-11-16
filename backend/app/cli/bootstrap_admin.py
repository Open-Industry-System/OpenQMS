"""Operator-only single-tenant account setup using a private password prompt.

No bootstrap secret exists in HTTP, environment defaults or process arguments.
"""
import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select, text

from app.config import settings
from app.core.security import PUBLISHED_DEMO_PASSWORDS, hash_password
from app.database import async_session
from app.models.audit import AuditLog
from app.models.role import RoleDefinition
from app.models.user import User
from app.schemas.auth import validate_password_complexity
from app.services.refresh_session_service import revoke_all_refresh_sessions


async def bootstrap_admin(db, *, username: str, password: str, replace_existing: bool = False):
    if settings.TENANT_MODE != "single":
        raise ValueError("Use tenant provisioning for multi-tenant administrators")
    if not username or len(username) > 50 or username != username.strip():
        raise ValueError("Invalid username")
    if password in PUBLISHED_DEMO_PASSWORDS or len(password) < 14 or len(password.encode("utf-8")) > 72:
        raise ValueError("Installation password must be unique and 14-72 bytes")
    validate_password_complexity(password)
    # Serialize host bootstrap/reset invocations with one short transaction lock.
    await db.execute(text("SELECT pg_advisory_xact_lock(728913716)"))
    role = (await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))).scalar_one_or_none()
    if role is None:
        raise ValueError("Run database migrations before account setup")
    user = (await db.execute(select(User).where(User.username == username).with_for_update(of=User))).scalar_one_or_none()
    if user is not None and not replace_existing:
        raise ValueError("Account exists; explicit --replace-existing is required")
    if user is None:
        user = User(username=username, display_name="系统管理员", role_id=role.id,
                    legacy_role="admin", password_hash=hash_password(password), is_active=True)
        db.add(user)
        await db.flush()
    else:
        await revoke_all_refresh_sessions(db, user.user_id)
        user.password_hash = hash_password(password)
        user.is_active = True
        user.role_id = role.id
        user.legacy_role = "admin"
        user.refresh_token = None
        user.refresh_token_expires = None
    db.add(AuditLog(table_name="users", record_id=user.user_id,
                    action="ADMIN_PRIVATE_BOOTSTRAP", operated_by=user.user_id,
                    factory_id=user.factory_id, changed_fields={"password": "[reset]"}))
    await db.commit()
    return user


async def _run(username: str, replace_existing: bool, password: str):
    async with async_session() as db:
        await bootstrap_admin(db, username=username, password=password, replace_existing=replace_existing)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private single-tenant administrator setup")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not sys.stdin.isatty():
            raise ValueError("Interactive private terminal required")
        password = getpass.getpass("New installation-specific admin password: ")
        if password != getpass.getpass("Confirm password: "):
            raise ValueError("Password confirmation failed")
        asyncio.run(_run(args.username, args.replace_existing, password))
    except Exception:
        # Never echo a password, DSN or database exception to the operator log.
        print("Administrator setup failed; verify private input, account flags and migrations.", file=sys.stderr)
        return 1
    print("Administrator password initialized; previous refresh sessions revoked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
