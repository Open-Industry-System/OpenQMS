"""Add tenant-local, single-report Agent read tasks.

Revision ID: 20260929_agent_read_task
Revises: 20260727_warranty_factory_id
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260929_agent_read_task"
down_revision = "20260727_warranty_factory_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_read_tasks",
        sa.Column("task_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("initiator_user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tenant_schema", sa.String(63), nullable=False),
        sa.Column("capa_id", UUID(as_uuid=True), nullable=False),
        sa.Column("factory_id", UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_line_code", sa.String(20), nullable=False),
        sa.Column("capability_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["capa_id", "factory_id"],
            ["capa_eightd.report_id", "capa_eightd.factory_id"],
            ondelete="RESTRICT",
            name="fk_agent_read_task_capa_factory",
        ),
        sa.CheckConstraint("status IN ('active','revoked')", name="ck_agent_read_task_status"),
        sa.CheckConstraint(
            "capability_id = 'capa.d4.summary.masked.v1'",
            name="ck_agent_read_task_capability",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_agent_read_task_expiry"),
    )
    op.create_index("ix_agent_read_tasks_initiator_status", "agent_read_tasks", ["initiator_user_id", "status"])
    op.create_index("ix_agent_read_tasks_expires_at", "agent_read_tasks", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_read_tasks_expires_at", table_name="agent_read_tasks")
    op.drop_index("ix_agent_read_tasks_initiator_status", table_name="agent_read_tasks")
    op.drop_table("agent_read_tasks")
