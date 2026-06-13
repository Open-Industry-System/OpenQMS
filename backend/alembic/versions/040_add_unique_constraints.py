"""add unique constraints for supplier risk config scope and snapshot period

Adds:
- uq_risk_config_scope: UNIQUE NULLS NOT DISTINCT (rule_id, supplier_id, product_line_code)
  on supplier_risk_configs — prevents duplicate risk configs for the same scope.
- uq_supplier_pl_period: UNIQUE NULLS NOT DISTINCT (supplier_id, product_line_code, snapshot_period)
  on supply_chain_risk_snapshots — prevents duplicate snapshots for the same scope.

Both use NULLS NOT DISTINCT so that NULL values in nullable columns are treated
as equal for uniqueness purposes (matching the application's upsert logic).

Revision ID: 040
Revises: 999_merge_all
"""
from alembic import op


revision = '040'
down_revision = '039'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_risk_config_scope "
        "ON supplier_risk_configs (rule_id, supplier_id, product_line_code) NULLS NOT DISTINCT"
    )
    op.execute(
        "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_supplier_pl_period "
        "ON supply_chain_risk_snapshots (supplier_id, product_line_code, snapshot_period) NULLS NOT DISTINCT"
    )


def downgrade() -> None:
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS uq_risk_config_scope")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS uq_supplier_pl_period")