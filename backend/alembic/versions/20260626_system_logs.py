"""add system_logs table (tenant-level).

Revision ID: 20260626_system_logs
Revises: 20260626_login_audit_logs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260626_system_logs"
down_revision = "20260626_login_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_logs",
        sa.Column("log_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("logger_name", sa.String(100), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("module", sa.String(200), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_system_logs_level", "system_logs", ["level"])
    op.create_index("ix_system_logs_occurred_at", "system_logs", [sa.text("occurred_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_system_logs_occurred_at", table_name="system_logs")
    op.drop_index("ix_system_logs_level", table_name="system_logs")
    op.drop_table("system_logs")
