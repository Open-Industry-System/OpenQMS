"""tenant squash — create all tenant business tables in one migration.

In single-tenant mode (TENANT_MODE=single), the main-line migrations already
create every business table, so this migration is a no-op.  In multi-tenant
mode it runs `TenantBase.metadata.create_all()` inside the tenant schema.

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

    In single-tenant mode the main-line migrations already create the tables,
    so we skip create_all() to avoid duplicate-table errors.
    """
    import os
    tenant_mode = os.getenv("TENANT_MODE", "single")
    if tenant_mode == "single":
        logger.info("tenant squash: TENANT_MODE=single, skipping create_all (main migrations already create tables)")
        return

    from app.database import TenantBase
    import app.models  # noqa: F401

    bind = op.get_bind()
    TenantBase.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Drop all tenant tables."""
    import os
    tenant_mode = os.getenv("TENANT_MODE", "single")
    if tenant_mode == "single":
        return

    from app.database import TenantBase
    import app.models  # noqa: F401

    bind = op.get_bind()
    TenantBase.metadata.drop_all(bind=bind)