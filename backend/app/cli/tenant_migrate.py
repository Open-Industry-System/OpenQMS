"""Owner-bound tenant migration CLI. Never invokes the historical tenant@head chain."""
import argparse
import asyncio
import getpass
import logging

from sqlalchemy import select, text

from app.database import async_session
from app.models.tenant import Tenant
from app.schemas.platform import TenantCreateRequest
from app.services.tenant_migrator import resume_tenant

logger = logging.getLogger(__name__)


async def get_tenants(slug: str | None = None):
    """Bulk maintenance targets active tenants; explicit slug may resume failed ones."""
    async with async_session() as session:
        await session.execute(text("SET LOCAL search_path TO public, pg_catalog"))
        query = select(Tenant)
        query = query.where(Tenant.slug == slug) if slug else query.where(Tenant.status == "active")
        return (await session.execute(query)).scalars().all()


async def main(all_tenants: bool = False, slug: str | None = None,
               admin_email: str | None = None):
    tenants = await get_tenants(None if all_tenants else slug)
    if not tenants:
        raise ValueError("Tenant not found")
    for tenant in tenants:
        bootstrap = None
        if admin_email:
            password = getpass.getpass("First admin bootstrap password: ")
            bootstrap = TenantCreateRequest(
                name=tenant.name, slug=tenant.slug, admin_email=admin_email,
                admin_password=password,
            )
        logger.info("Migrating tenant id=%s schema=%s", tenant.id, tenant.schema_name)
        await resume_tenant(tenant.id, bootstrap_request=bootstrap)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate tenant schemas via locked coordinator")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Migrate all active tenants")
    group.add_argument("--slug", type=str, help="Migrate or resume a specific tenant")
    parser.add_argument("--admin-email", help="Re-supply first-admin credentials via private prompt")
    args = parser.parse_args()
    if args.admin_email and not args.slug:
        parser.error("--admin-email requires --slug")
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(all_tenants=args.all, slug=args.slug, admin_email=args.admin_email))
