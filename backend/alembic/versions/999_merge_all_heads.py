"""merge all heads — unifies main, supply_chain_risk, platform, and tenant branches.

Revision ID: 999_merge_all
Revises: 041, 035_add_supply_chain_risk_snapshot, p001_platform_tables, t001_tenant_squash
"""

revision = '999_merge_all'
down_revision = (
    '041',
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