"""supplier risk capa inputs + capa supplier_id + rule_results normalize

Revision ID: 20260716_supplier_risk_capa_inputs
Revises: 20260716_merge_scar_and_doc_gate
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260716_supplier_risk_capa_inputs"
down_revision = "20260716_merge_scar_and_doc_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. capa_eightd.supplier_id
    op.add_column(
        "capa_eightd",
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.supplier_id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )

    # 2. input fact table
    op.create_table(
        "supplier_risk_capa_inputs",
        sa.Column("input_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "capa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("capa_eightd.report_id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.supplier_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "factory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("factories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("product_line_code", sa.String(20), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("disposition", sa.Text(), nullable=True),
        sa.Column("repeat_suggested", sa.Boolean(), nullable=True),
        sa.Column("repeat_detection_status", sa.String(20), nullable=False),
        sa.Column("repeat_confirmed", sa.Boolean(), nullable=True),
        sa.Column(
            "matched_capa_nos",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("evaluated_risk_level", sa.String(10), nullable=True),
        sa.Column("evaluated_risk_score", sa.Float(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "linked_alert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("supplier_risk_alerts.alert_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_risk_input_status_retry",
        "supplier_risk_capa_inputs",
        ["status", "next_retry_at"],
    )

    # 3. normalize legacy empty rule_results dict/null → list
    op.execute(
        "UPDATE supplier_risk_alerts "
        "SET rule_results='[]'::jsonb "
        "WHERE rule_results='{}'::jsonb OR rule_results IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_risk_input_status_retry", table_name="supplier_risk_capa_inputs")
    op.drop_table("supplier_risk_capa_inputs")
    op.drop_column("capa_eightd", "supplier_id")
