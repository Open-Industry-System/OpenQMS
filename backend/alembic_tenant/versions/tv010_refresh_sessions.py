"""Add browser refresh sessions on the locked tenant connection."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "tv010_refresh_sessions"
down_revision = "tv009_r4b_main_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_refresh_sessions",
        sa.Column("session_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_user_refresh_sessions_user_id", "user_refresh_sessions", ["user_id"])
    op.create_index("ix_user_refresh_sessions_user_id_expires_at", "user_refresh_sessions", ["user_id", "expires_at"])


def downgrade() -> None:
    op.drop_table("user_refresh_sessions")
