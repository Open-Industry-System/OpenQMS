"""merge all heads — unifies main, factory, supply_chain_risk, platform, and tenant branches.

In single-tenant mode, t001_tenant_squash is a no-op because the main-line
migrations already create every business table.  In multi-tenant mode it would
run `TenantBase.metadata.create_all()` inside the tenant schema.

Revision ID: 999_merge_all
Revises: 036_factory_id_not_null_enforcement, 035_add_supply_chain_risk_snapshot, p001_platform_tables, t001_tenant_squash
"""

revision = '999_merge_all'
down_revision = (
    '036_factory_id_not_null_enforcement',
    '035_add_supply_chain_risk_snapshot',
    'p001_platform_tables',
    't001_tenant_squash',
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass