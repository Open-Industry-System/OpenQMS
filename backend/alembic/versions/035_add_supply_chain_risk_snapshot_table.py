"""add supply chain risk snapshot table + erp po actual_delivery_date

Revision ID: 035_add_supply_chain_risk_snapshot
Revises: 20260611_add_review_reports
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "035_add_supply_chain_risk_snapshot"
down_revision = "20260611_add_review_reports"


def upgrade() -> None:
    # 1. Add actual_delivery_date to erp_purchase_orders
    op.add_column(
        "erp_purchase_orders",
        sa.Column("actual_delivery_date", sa.Date(), nullable=True),
    )

    # 2. Create supply_chain_risk_snapshots table
    op.create_table(
        "supply_chain_risk_snapshots",
        sa.Column("snapshot_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_line_code", sa.String(20), sa.ForeignKey("product_lines.code", ondelete="CASCADE"), nullable=True),
        sa.Column("snapshot_period", sa.String(7), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("risk_level", sa.String(10), nullable=False, server_default="low"),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("delivery_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("compliance_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("erp_on_time_rate", sa.Float(), nullable=True),
        sa.Column("erp_on_time_rate_source", sa.String(30), nullable=True),
        sa.Column("purchase_amount_pct", sa.Float(), nullable=True),
        sa.Column("delivery_delay_days", sa.Float(), nullable=True),
        sa.Column("open_scar_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ppm_value", sa.Float(), nullable=True),
        sa.Column("dimensions", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 3. Unique constraint — NULLS NOT DISTINCT (PostgreSQL 15+)
    # NOTE: JSONB and NULLS NOT DISTINCT are both PostgreSQL-only.
    # SQLite tests must use a standard unique constraint and test NULL dedup
    # at the application layer, since SQLite unique constraints don't enforce
    # uniqueness on NULL columns.
    op.execute(
        "ALTER TABLE supply_chain_risk_snapshots "
        "ADD CONSTRAINT uq_supplier_pl_period "
        "UNIQUE NULLS NOT DISTINCT (supplier_id, product_line_code, snapshot_period)"
    )

    # 4. Indexes
    op.create_index("idx_scrs_period", "supply_chain_risk_snapshots", ["snapshot_period"])
    op.create_index("idx_scrs_supplier", "supply_chain_risk_snapshots", ["supplier_id"])

    # 5. Permission seeds for SUPPLY_CHAIN_RISK_MAP module
    PERMS = {
        "admin": 5,
        "manager": 5,
        "field_qe": 3,
        "supplier_qe": 3,
        "customer_qe": 3,
        "planning_qe": 3,
        "viewer": 1,
    }
    for role_key, level in PERMS.items():
        op.execute(
            f"INSERT INTO role_permissions (role_id, module, permission_level) "
            f"SELECT rd.id, 'supply_chain_risk_map', {level} "
            f"FROM role_definitions rd WHERE rd.role_key = '{role_key}' "
            f"ON CONFLICT DO NOTHING"
        )


def downgrade() -> None:
    op.drop_index("idx_scrs_supplier", table_name="supply_chain_risk_snapshots")
    op.drop_index("idx_scrs_period", table_name="supply_chain_risk_snapshots")
    op.execute("ALTER TABLE supply_chain_risk_snapshots DROP CONSTRAINT uq_supplier_pl_period")
    op.drop_table("supply_chain_risk_snapshots")
    op.drop_column("erp_purchase_orders", "actual_delivery_date")

    # Remove permission seeds
    op.execute("DELETE FROM role_permissions WHERE module = 'supply_chain_risk_map'")