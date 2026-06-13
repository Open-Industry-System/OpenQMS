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

    create_all() uses CHECKFIRST by default, so it safely skips tables
    that already exist (e.g., in single-tenant mode where main migrations
    already created them).
    """
    from app.database import TenantBase
    import app.models  # noqa: F401

    bind = op.get_bind()
    TenantBase.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Drop all tenant tables."""
    from app.database import TenantBase
    import app.models  # noqa: F401

    bind = op.get_bind()
    TenantBase.metadata.drop_all(bind=bind)