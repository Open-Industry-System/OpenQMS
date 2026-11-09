"""Record the owner-bound provisioning attempt in the platform registry.

Revision ID: 20260927_tenant_attempt
Revises: 20260927_tenant_generation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260927_tenant_attempt"
down_revision = "20260927_tenant_generation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("provisioning_attempt_id", UUID(as_uuid=True), nullable=True),
                  schema="public")


def downgrade() -> None:
    op.drop_column("tenants", "provisioning_attempt_id", schema="public")
