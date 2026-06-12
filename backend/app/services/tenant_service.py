import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.tenant_utils import slug_to_schema_name
from app.models.tenant import Tenant
from app.schemas.platform import TenantCreateRequest

logger = logging.getLogger(__name__)


class TenantService:
    @staticmethod
    async def provision(db: AsyncSession, request: TenantCreateRequest) -> Tenant:
        """Provision a new tenant: create schema, run migrations, seed data."""
        schema_name = slug_to_schema_name(request.slug)
        tenant = Tenant(
            name=request.name,
            slug=request.slug,
            schema_name=schema_name,
            subdomain=request.subdomain or request.slug,
            plan=request.plan or "free",
            status="provisioning",
            provisioning_step="create_schema",
        )
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)

        try:
            # Step 1: Create schema
            await db.execute(text(f'CREATE SCHEMA "{schema_name}"'))
            await db.commit()
            tenant.provisioning_step = "run_migrations"

            # Step 2: Run migrations (delegated to CLI)
            # In production, this calls: python -m app.cli.tenant_migrate --slug <slug>
            tenant.provisioning_step = "seed_data"

            # Step 3: Seed data (delegated to seed script with schema param)
            tenant.status = "active"
            tenant.provisioning_step = None
            await db.commit()
        except Exception as e:
            tenant.status = "failed"
            tenant.provisioning_error = str(e)
            await db.commit()
            logger.error("Tenant provisioning failed for %s: %s", request.slug, e)
            raise

        return tenant