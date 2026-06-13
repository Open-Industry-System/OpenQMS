"""CLI script for tenant migration orchestration.

Usage:
    python -m app.cli.tenant_migrate --all        # Migrate all active tenants
    python -m app.cli.tenant_migrate --slug acme    # Migrate specific tenant
"""
import argparse
import asyncio
import logging
import subprocess
import sys

from sqlalchemy import select, text

from app.database import async_session
from app.models.tenant import Tenant


logger = logging.getLogger(__name__)


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
        sys.executable, "-m", "alembic",
        "-x", f"schema={schema_name}",
        "upgrade", "tenant@head",
    ]
    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Alembic failed for %s:\n%s", schema_name, result.stderr)
        return False
    logger.info("Successfully migrated %s", schema_name)
    return True


async def main(all_tenants: bool = False, slug: str | None = None):
    tenants = await get_active_tenants(slug)
    if not tenants:
        logger.info("No active tenants found.")
        return

    for tenant in tenants:
        logger.info("Migrating tenant %s (schema: %s)...", tenant.slug, tenant.schema_name)
        success = run_alembic_upgrade(tenant.schema_name)
        # Update tenant_migrations table via the ORM
        async with async_session() as session:
            await session.execute(text('SET search_path TO "public"'))
            # Update status based on success/failure
            from app.models.tenant_migration import TenantMigration
            migration = TenantMigration(
                tenant_id=tenant.id,
                version="tenant@head",
                status="completed" if success else "failed",
            )
            session.add(migration)
            await session.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate tenant schemas")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Migrate all active tenants")
    group.add_argument("--slug", type=str, help="Migrate a specific tenant by slug")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(all_tenants=args.all, slug=args.slug))