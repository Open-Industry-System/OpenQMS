"""audit enhancements — audit log detail fields, product_line isolation, AQL sampling

Revision ID: 016
Revises: 015_audit_compliance_fixes
Create Date: 2026-05-25

Adds:
- old_values, new_values, ip_address, user_agent to audit_logs
- product_line_code to supplier_ppap_submissions, supplier_scars
- aql_level, inspection_level, sampling_standard to iqc_inspections
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '016'
down_revision: Union[str, None] = '015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === audit_logs: expanded detail fields ===
    op.add_column('audit_logs', sa.Column('old_values', postgresql.JSONB(), nullable=True))
    op.add_column('audit_logs', sa.Column('new_values', postgresql.JSONB(), nullable=True))
    op.add_column('audit_logs', sa.Column('ip_address', sa.VARCHAR(50), nullable=True))
    op.add_column('audit_logs', sa.Column('user_agent', sa.Text(), nullable=True))

    # === supplier_ppap_submissions: product_line_code ===
    op.add_column('supplier_ppap_submissions', sa.Column('product_line_code', sa.VARCHAR(20), nullable=True))
    op.create_index('ix_ppap_product_line', 'supplier_ppap_submissions', ['product_line_code'])

    # === supplier_scars: product_line_code ===
    op.add_column('supplier_scars', sa.Column('product_line_code', sa.VARCHAR(20), nullable=True))
    op.create_index('ix_scar_product_line', 'supplier_scars', ['product_line_code'])

    # === iqc_inspections: AQL sampling fields ===
    op.add_column('iqc_inspections', sa.Column('aql_level', sa.VARCHAR(10), nullable=True))
    op.add_column('iqc_inspections', sa.Column('inspection_level', sa.VARCHAR(10), nullable=True))
    op.add_column('iqc_inspections', sa.Column('sampling_standard', sa.VARCHAR(50), nullable=True))


def downgrade() -> None:
    op.drop_column('iqc_inspections', 'sampling_standard')
    op.drop_column('iqc_inspections', 'inspection_level')
    op.drop_column('iqc_inspections', 'aql_level')

    op.drop_index('ix_scar_product_line', table_name='supplier_scars')
    op.drop_column('supplier_scars', 'product_line_code')

    op.drop_index('ix_ppap_product_line', table_name='supplier_ppap_submissions')
    op.drop_column('supplier_ppap_submissions', 'product_line_code')

    op.drop_column('audit_logs', 'user_agent')
    op.drop_column('audit_logs', 'ip_address')
    op.drop_column('audit_logs', 'new_values')
    op.drop_column('audit_logs', 'old_values')
