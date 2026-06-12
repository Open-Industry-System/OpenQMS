import logging
import subprocess
import sys

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.tenant_utils import slug_to_schema_name
from app.models.tenant import Tenant
from app.schemas.platform import TenantCreateRequest

logger = logging.getLogger(__name__)


def _run_alembic_upgrade(schema_name: str) -> bool:
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

            # Step 2: Run tenant migrations to create business tables
            migrations_ok = _run_alembic_upgrade(schema_name)
            if not migrations_ok:
                raise RuntimeError(f"Alembic migration failed for schema {schema_name}")
            tenant.provisioning_step = "seed_data"

            # Step 3: Seed data (delegated to seed script with schema param)
            # TODO: implement per-tenant seed script; for now the tenant is
            # created with empty tables and the platform admin can invite users.
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