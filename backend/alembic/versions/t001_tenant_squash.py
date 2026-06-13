"""tenant squash — create all tenant business tables in one migration.

Creates all tables registered with TenantBase.metadata. In single-tenant
mode the main-line migrations already create these tables, so create_all()
is a no-op for existing tables (CHECKFIRST skips them). In multi-tenant
mode this creates every business table inside the tenant schema.

Revision ID: t001
Revises: t000
"""
import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

revision = 't001_tenant_squash'
down_revision = 't000_tenant_baseline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create every table registered with TenantBase.metadata in the target schema.

    Only runs when a tenant schema is active (i.e., the -x schema=xxx argument
    is passed to alembic). In single-tenant / public-schema mode, the main-line
    migrations already create these tables individually, so running create_all()
    here would race ahead and create tables that later migrations also try to
    create with op.create_table(), causing DuplicateTableError.
    """
    from alembic import context
    x_args = context.get_x_argument(as_dictionary=True)
    schema_name = x_args.get("schema")

    if not schema_name:
        # Single-tenant mode: main-line migrations handle table creation.
        # Skip to avoid creating tables that later migrations also create.
        logger.info("Skipping tenant squash — no -x schema= arg (single-tenant mode)")
        return

    from app.database import TenantBase
    import app.models  # noqa: F401

    bind = op.get_bind()
    TenantBase.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Drop all tenant tables (only in multi-tenant schema mode)."""
    from alembic import context
    x_args = context.get_x_argument(as_dictionary=True)
    schema_name = x_args.get("schema")

    if not schema_name:
        logger.info("Skipping tenant squash downgrade — single-tenant mode")
        return

    from app.database import TenantBase
    import app.models  # noqa: F401

    bind = op.get_bind()
    TenantBase.metadata.drop_all(bind=bind)