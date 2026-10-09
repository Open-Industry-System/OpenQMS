"""Create tenant-local scan-gated task attachment metadata."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision = "tv005_agent_task_attachments"
down_revision = "tv004_agent_readonly_controls"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_task_attachments",
        sa.Column("attachment_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("agent_tasks.task_id"),
            nullable=False,
        ),
        sa.Column(
            "factory_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("factories.id"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column("tenant_id", pg.UUID(as_uuid=True)),
        sa.Column("origin_generation", sa.Integer),
        sa.Column("storage_namespace", sa.String(160), nullable=False),
        sa.Column("storage_key", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("extension", sa.String(16)),
        sa.Column("declared_content_type", sa.String(255)),
        sa.Column("byte_size", sa.BigInteger),
        sa.Column("sha256", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False, server_default="scanning"),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True)),
        sa.Column("scanner_version", sa.String(255)),
        sa.Column("scanned_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('scanning','promoting','available','rejected_malware',"
            "'rejected_scanner','failed_storage','purging','purged')",
            name="ck_agent_task_attachment_status",
        ),
        sa.CheckConstraint(
            "(tenant_id IS NULL AND origin_generation IS NULL) OR "
            "(tenant_id IS NOT NULL AND origin_generation IS NOT NULL)",
            name="ck_agent_task_attachment_generation_pair",
        ),
        sa.CheckConstraint(
            "byte_size IS NULL OR byte_size >= 0",
            name="ck_agent_task_attachment_size_nonnegative",
        ),
    )
    op.create_index(
        "ix_agent_task_attachment_task_status",
        "agent_task_attachments",
        ["task_id", "status"],
    )
    op.create_index(
        "ix_agent_task_attachment_expires_status",
        "agent_task_attachments",
        ["expires_at", "status"],
    )


def downgrade():
    op.drop_index(
        "ix_agent_task_attachment_expires_status",
        table_name="agent_task_attachments",
    )
    op.drop_index(
        "ix_agent_task_attachment_task_status",
        table_name="agent_task_attachments",
    )
    op.drop_table("agent_task_attachments")
