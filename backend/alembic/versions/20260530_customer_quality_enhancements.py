"""Customer quality enhancements: shipments, warranty, satisfaction, csr sync, scar fk

Revision ID: 20260530
Revises: 026
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '20260530'
down_revision = '026'
branch_labels = None
depends_on = None


def upgrade():
    # 1. customers: satisfaction fields
    op.add_column('customers', sa.Column('satisfaction_score', sa.Float(), nullable=True))
    op.add_column('customers', sa.Column('satisfaction_survey_date', sa.Date(), nullable=True))

    # 2. control_plans: customer_requirements JSONB
    op.add_column('control_plans', sa.Column('customer_requirements', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # 3. shipment_records table
    op.create_table(
        'shipment_records',
        sa.Column('shipment_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('customers.customer_id'), nullable=False),
        sa.Column('product_line_code', sa.String(), sa.ForeignKey('product_lines.code'), nullable=True),
        sa.Column('shipment_date', sa.Date(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('batch_no', sa.String(), nullable=True),
        sa.Column('destination', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.CheckConstraint('quantity > 0', name='ck_shipment_quantity_positive'),
    )
    op.create_index('ix_shipment_records_customer_date', 'shipment_records', ['customer_id', 'shipment_date'])
    op.create_index('ix_shipment_records_batch_no', 'shipment_records', ['batch_no'])
    op.create_index('ix_shipment_records_date_line', 'shipment_records', ['shipment_date', 'product_line_code'])

    # 4. warranty_records table
    op.create_table(
        'warranty_records',
        sa.Column('warranty_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('customers.customer_id'), nullable=False),
        sa.Column('product_line_code', sa.String(), nullable=True),
        sa.Column('claim_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('failure_mode', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
    )

    # 5. scar_ref_id FK constraints (clean dirty refs first)
    op.execute("UPDATE customer_complaints SET scar_ref_id = NULL WHERE scar_ref_id NOT IN (SELECT scar_id FROM supplier_scars)")
    op.execute("UPDATE rma_records SET scar_ref_id = NULL WHERE scar_ref_id NOT IN (SELECT scar_id FROM supplier_scars)")
    op.create_foreign_key('fk_customer_complaints_scar_ref_id', 'customer_complaints', 'supplier_scars', ['scar_ref_id'], ['scar_id'], ondelete='SET NULL')
    op.create_foreign_key('fk_rma_records_scar_ref_id', 'rma_records', 'supplier_scars', ['scar_ref_id'], ['scar_id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('fk_rma_records_scar_ref_id', 'rma_records', type_='foreignkey')
    op.drop_constraint('fk_customer_complaints_scar_ref_id', 'customer_complaints', type_='foreignkey')
    op.drop_table('warranty_records')
    op.drop_index('ix_shipment_records_date_line', table_name='shipment_records')
    op.drop_index('ix_shipment_records_batch_no', table_name='shipment_records')
    op.drop_index('ix_shipment_records_customer_date', table_name='shipment_records')
    op.drop_table('shipment_records')
    op.drop_column('control_plans', 'customer_requirements')
    op.drop_column('customers', 'satisfaction_survey_date')
    op.drop_column('customers', 'satisfaction_score')
