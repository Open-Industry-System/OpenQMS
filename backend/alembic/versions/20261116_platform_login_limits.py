"""Persist platform login throttle state in public only."""
from alembic import context, op
import sqlalchemy as sa

revision = "20261116_platform_login_limits"
down_revision = "20261114_production_merge"
branch_labels = None
depends_on = None


def upgrade():
    if context.get_x_argument(as_dictionary=True).get("schema"):
        return
    op.create_table("platform_login_attempts",
                    sa.Column("key_kind", sa.String(10), primary_key=True),
                    sa.Column("key_hash", sa.String(64), primary_key=True),
                    sa.Column("attempts", sa.Integer(), nullable=False),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), schema="public")
    op.create_index("ix_public_platform_login_attempts_expires_at", "platform_login_attempts", ["expires_at"], schema="public")


def downgrade():
    if context.get_x_argument(as_dictionary=True).get("schema"):
        return
    op.drop_index("ix_public_platform_login_attempts_expires_at", table_name="platform_login_attempts", schema="public")
    op.drop_table("platform_login_attempts", schema="public")
