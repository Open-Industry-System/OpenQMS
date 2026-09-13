"""Add independent user refresh sessions.

Revision ID: 20260913_user_refresh_sessions
Revises: 20260727_warranty_factory_id
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "20260913_user_refresh_sessions"
down_revision = "20260727_warranty_factory_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("user_refresh_sessions"):
        return
    op.create_table(
        "user_refresh_sessions",
        sa.Column("session_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_user_refresh_sessions_user_id",
        "user_refresh_sessions",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_refresh_sessions_user_id",
        table_name="user_refresh_sessions",
    )
    op.drop_table("user_refresh_sessions")
