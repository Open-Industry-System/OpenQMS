"""supplier evaluation: add premium freight and customer disruption fields

Revision ID: 010_supplier_eval_iatf_fields
Revises: 009_add_msa_tables
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa

revision = '010_supplier_eval_iatf_fields'
down_revision = '009_add_msa_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('supplier_evaluations', sa.Column('premium_freight_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('supplier_evaluations', sa.Column('customer_disruption_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('supplier_evaluations', sa.Column('premium_freight_penalty', sa.Float(), nullable=False, server_default='0'))
    op.add_column('supplier_evaluations', sa.Column('customer_disruption_penalty', sa.Float(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('supplier_evaluations', 'customer_disruption_penalty')
    op.drop_column('supplier_evaluations', 'premium_freight_penalty')
    op.drop_column('supplier_evaluations', 'customer_disruption_count')
    op.drop_column('supplier_evaluations', 'premium_freight_count')