"""add supplier risk tables

Revision ID: 034_add_supplier_risk_tables
Revises: 033_add_iqc_aql_optimization
Create Date: 2026-06-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "034_add_supplier_risk_tables"
down_revision: Union[str, None] = "033_add_iqc_aql_optimization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RISK_PERMS = {
    "admin": 5,
    "manager": 4,
    "field_qe": 3,
    "viewer": 1,
    "customer_qe": 1,
    "supplier_qe": 3,
    "planning_qe": 1,
}


def upgrade() -> None:
    # ---- 1. supplier_risk_alerts ------------------------------------------------
    op.create_table(
        "supplier_risk_alerts",
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("risk_score", sa.Float, nullable=False),
        sa.Column("quality_score", sa.Float, nullable=False),
        sa.Column("delivery_score", sa.Float, nullable=False),
        sa.Column("compliance_score", sa.Float, nullable=False),
        sa.Column("rule_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("alert_type", sa.String(20), nullable=False, server_default="initial"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("handled_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handle_note", sa.Text, nullable=True),
        sa.Column("linked_scar_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("supplier_scars.scar_id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_capa_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("capa_eightd.report_id", ondelete="SET NULL"), nullable=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("product_line_code", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Partial unique indexes for alerts (PG14+ compatible, handles NULL product_line_code)
    op.execute("""
        CREATE UNIQUE INDEX idx_risk_alert_unique_pl
        ON supplier_risk_alerts (supplier_id, product_line_code, snapshot_date)
        WHERE product_line_code IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_risk_alert_unique_global
        ON supplier_risk_alerts (supplier_id, snapshot_date)
        WHERE product_line_code IS NULL;
    """)

    # ---- 2. supplier_risk_configs -----------------------------------------------
    op.create_table(
        "supplier_risk_configs",
        sa.Column("config_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("rule_id", sa.String(10), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("thresholds", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("product_line_code", sa.String(20), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # 4 partial unique indexes for configs
    op.execute("""
        CREATE UNIQUE INDEX idx_risk_config_global
        ON supplier_risk_configs (rule_id)
        WHERE supplier_id IS NULL AND product_line_code IS NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_risk_config_product_line
        ON supplier_risk_configs (rule_id, product_line_code)
        WHERE supplier_id IS NULL AND product_line_code IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_risk_config_supplier_pl
        ON supplier_risk_configs (rule_id, supplier_id, product_line_code)
        WHERE supplier_id IS NOT NULL AND product_line_code IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_risk_config_supplier_global
        ON supplier_risk_configs (rule_id, supplier_id)
        WHERE supplier_id IS NOT NULL AND product_line_code IS NULL;
    """)

    # ---- 3. supplier_risk_notification_channels ---------------------------------
    op.create_table(
        "supplier_risk_notification_channels",
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("min_risk_level", sa.String(10), nullable=False, server_default="high"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=True),
        sa.Column("product_line_code", sa.String(20), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ---- 4. Permission seed -----------------------------------------------------
    for role_key, level in RISK_PERMS.items():
        op.execute(f"""
            INSERT INTO role_permissions (role_id, module, permission_level)
            SELECT rd.id, 'supplier_risk', {level}
            FROM role_definitions rd
            WHERE rd.role_key = '{role_key}'
            ON CONFLICT DO NOTHING;
        """)


def downgrade() -> None:
    op.drop_table("supplier_risk_notification_channels")
    op.drop_table("supplier_risk_configs")
    op.drop_table("supplier_risk_alerts")
    op.execute("DELETE FROM role_permissions WHERE module = 'supplier_risk'")
