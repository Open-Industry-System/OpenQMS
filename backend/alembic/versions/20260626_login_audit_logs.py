"""add login_audit_logs table (tenant-level).

Revision ID: 20260626_login_audit_logs
Revises: 20260624_add_product_types
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260626_login_audit_logs"
down_revision = "20260624_add_product_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_audit_logs",
        sa.Column("log_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.String(200), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
    )
    op.create_index("ix_login_audit_logs_username", "login_audit_logs", ["username"])
    op.create_index("ix_login_audit_logs_occurred_at", "login_audit_logs", [sa.text("occurred_at DESC")])
    # pgcrypto extension is already ensured by 038_ensure_pgcrypto_extension; gen_random_uuid() available.


def downgrade() -> None:
    op.drop_index("ix_login_audit_logs_occurred_at", table_name="login_audit_logs")
    op.drop_index("ix_login_audit_logs_username", table_name="login_audit_logs")
    op.drop_table("login_audit_logs")
