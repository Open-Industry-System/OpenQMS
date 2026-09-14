"""CLI script for tenant migration orchestration.

Usage:
    python -m app.cli.tenant_migrate --all        # Migrate all active tenants
    python -m app.cli.tenant_migrate --slug acme  # Migrate specific tenant
"""
import argparse
import asyncio
import logging
import subprocess
import sys
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from app.database import async_session
from app.models.tenant import Tenant
from app.models.tenant_migration import TenantMigration

logger = logging.getLogger(__name__)


class TenantMigrationError(RuntimeError):
    """One or more selected tenant migrations failed."""


async def get_active_tenants(slug: str | None = None):
    """Get all active tenants, or a specific one by slug."""
    async with async_session() as session:
        await session.execute(text('SET search_path TO "public"'))
        query = select(Tenant).where(Tenant.status == "active")
        if slug:
            query = query.where(Tenant.slug == slug)
        result = await session.execute(query)
        return result.scalars().all()


def run_alembic_upgrade(schema_name: str) -> bool:
    """Run alembic upgrade tenant@head for a specific tenant schema."""
    cmd = [
        sys.executable,
        "-m",
        "alembic",
        "-x",
        f"schema={schema_name}",
        "upgrade",
        "tenant@head",
    ]
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Alembic failed for tenant schema %s", schema_name)
        return False
    logger.info("Successfully migrated %s", schema_name)
    return True


async def record_migration_result(tenant_id: uuid.UUID, *, success: bool) -> None:
    """Race-safely create or update the tenant@head bookkeeping row."""
    status = "completed" if success else "failed"
    error_message = None if success else "tenant migration failed"
    statement = insert(TenantMigration).values(
        tenant_id=tenant_id,
        version="tenant@head",
        status=status,
        started_at=func.now(),
        completed_at=func.now(),
        applied_at=func.now() if success else None,
        error_message=error_message,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[TenantMigration.tenant_id, TenantMigration.version],
        set_={
            "status": statement.excluded.status,
            "started_at": statement.excluded.started_at,
            "completed_at": statement.excluded.completed_at,
            "applied_at": statement.excluded.applied_at,
            "error_message": statement.excluded.error_message,
        },
    )
    async with async_session() as session:
        await session.execute(text('SET search_path TO "public"'))
        await session.execute(statement)
        await session.commit()


async def main(all_tenants: bool = False, slug: str | None = None) -> None:
    tenants = await get_active_tenants(slug)
    if not tenants:
        logger.info("No active tenants found.")
        return

    failed_count = 0
    for tenant in tenants:
        logger.info("Migrating tenant %s (schema: %s)...", tenant.slug, tenant.schema_name)
        try:
            success = run_alembic_upgrade(tenant.schema_name)
        except Exception:
            logger.error("Alembic invocation failed for tenant schema %s", tenant.schema_name)
            success = False
        await record_migration_result(tenant.id, success=success)
        if not success:
            failed_count += 1

    if failed_count:
        raise TenantMigrationError(f"{failed_count} tenant migration(s) failed")


def run_cli(*, all_tenants: bool, slug: str | None) -> int:
    """Run migrations and convert all failures to non-secret exit categories."""
    try:
        asyncio.run(main(all_tenants=all_tenants, slug=slug))
    except TenantMigrationError as exc:
        logger.error("%s", exc)
        return 1
    except Exception:
        logger.error("tenant migration orchestration failed")
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate tenant schemas")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Migrate all active tenants")
    group.add_argument("--slug", type=str, help="Migrate a specific tenant by slug")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    raise SystemExit(run_cli(all_tenants=args.all, slug=args.slug))
