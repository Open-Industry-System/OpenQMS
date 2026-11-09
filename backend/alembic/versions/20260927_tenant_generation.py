"""Add the captured transaction generation to the platform tenant registry.

Revision ID: 20260927_tenant_generation
Revises: 20260926_agent_plugin_registry
"""
from alembic import op
import sqlalchemy as sa

revision = "20260927_tenant_generation"
down_revision = "20260926_agent_plugin_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("tenants", "generation", schema="public")
