"""capa lateral diffusion tables

Revision ID: 20260721_capa_lateral_diffusion
Revises: 20260717_merge_knowledge_and_doc_gate, 20260716_seed_r11_config
Create Date: 2026-07-21
"""
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260721_capa_lateral_diffusion"
down_revision: Union[str, tuple[str, ...], None] = (
    "20260717_merge_knowledge_and_doc_gate",
    "20260716_seed_r11_config",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capa_lateral_diffusion_checks",
        sa.Column("check_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("capa_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False),
        sa.Column("factory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_product_line_code", sa.String(20), nullable=False),
        sa.Column("source_product_type_code", sa.String(20), nullable=True),
        sa.Column("similar_products", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("llm_status", sa.String(16), nullable=False),
        sa.Column("truncated", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("capa_id", name="uq_lateral_check_capa"),
    )
    op.create_index("ix_lateral_check_capa", "capa_lateral_diffusion_checks", ["capa_id"])

    op.create_table(
        "capa_lateral_notifications",
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("check_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("capa_lateral_diffusion_checks.check_id", ondelete="CASCADE"), nullable=False),
        sa.Column("capa_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_type_code", sa.String(20), nullable=False),
        sa.Column("product_line_code", sa.String(20), nullable=True),
        sa.Column("factory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("recipient_label", sa.String(120), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("skip_reason", sa.Text, nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    # notify 行：同 (check,type,pl,recipient) 唯一；NULLS NOT DISTINCT 保证无人行不重复
    op.execute(
        "CREATE UNIQUE INDEX uq_lateral_notif_notify "
        "ON capa_lateral_notifications (check_id, product_type_code, product_line_code, recipient_user_id) "
        "NULLS NOT DISTINCT WHERE decision = 'notified'"
    )
    # skip 行：每 (check,type) 一行
    op.execute(
        "CREATE UNIQUE INDEX uq_lateral_notif_skip "
        "ON capa_lateral_notifications (check_id, product_type_code) "
        "WHERE decision = 'skipped'"
    )
    op.create_index("ix_lateral_notif_capa", "capa_lateral_notifications", ["capa_id"])


def downgrade() -> None:
    op.drop_index("ix_lateral_notif_capa", table_name="capa_lateral_notifications")
    op.execute("DROP INDEX IF EXISTS uq_lateral_notif_skip")
    op.execute("DROP INDEX IF EXISTS uq_lateral_notif_notify")
    op.drop_table("capa_lateral_notifications")
    op.drop_index("ix_lateral_check_capa", table_name="capa_lateral_diffusion_checks")
    op.drop_table("capa_lateral_diffusion_checks")
