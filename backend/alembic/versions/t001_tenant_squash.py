"""tenant squash — create all tenant business tables in one migration.

Revision ID: t001
Revises: t000
Branch labels: ('tenant',)
"""
from alembic import op
import sqlalchemy as sa

from app.database import TenantBase
import app.models  # noqa: F401 — ensure all tenant models register with TenantBase.metadata

revision = 't001_tenant_squash'
down_revision = 't000_tenant_baseline'
branch_labels = ('tenant',)
depends_on = None


def upgrade() -> None:
    """Create every table registered with TenantBase.metadata in the target schema."""
    # Alembic runs this inside a transaction on the tenant schema because
    # env.py set search_path before configuring the migration context.
    bind = op.get_bind()
    TenantBase.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Drop all tenant tables."""
    bind = op.get_bind()
    TenantBase.metadata.drop_all(bind=bind)
