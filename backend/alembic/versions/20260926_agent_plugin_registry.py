"""Register tenant-local agent plugin installations and grants.

Revision ID: 20260926_agent_plugin_registry
Revises: 20260727_warranty_factory_id
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260926_agent_plugin_registry"
down_revision = "20260727_warranty_factory_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_plugin_installations",
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plugin_key", sa.String(100), nullable=False),
        sa.Column("plugin_version", sa.String(40), nullable=False),
        sa.Column("manifest", postgresql.JSONB, nullable=False),
        sa.Column("secret_hash", sa.String(255), nullable=False),
        sa.Column(
            "enabled", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("credential_epoch", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "plugin_key",
            "plugin_version",
            name="uq_agent_plugin_installation_key_version",
        ),
    )
    op.create_table(
        "agent_plugin_grants",
        sa.Column("grant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "installation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_plugin_installations.installation_id"),
            nullable=False,
        ),
        sa.Column("capability_id", sa.String(160), nullable=False),
        sa.Column("factory_ids", postgresql.JSONB, nullable=False),
        sa.Column("product_line_codes", postgresql.JSONB),
        sa.Column("object_ids", postgresql.JSONB),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "enabled", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "granted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "jsonb_typeof(factory_ids) = 'array' AND jsonb_array_length(factory_ids) > 0",
            name="ck_agent_plugin_grant_factory_ids_nonempty",
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_plugin_grants")
    op.drop_table("agent_plugin_installations")
