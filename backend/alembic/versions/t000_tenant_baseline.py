"""tenant baseline — independent branch root for tenant migrations.

Revision ID: t000
Revises: None
Branch labels: ('tenant',)
"""
from alembic import op
import sqlalchemy as sa

revision = 't000_tenant_baseline'
down_revision = None
branch_labels = ('tenant',)
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass