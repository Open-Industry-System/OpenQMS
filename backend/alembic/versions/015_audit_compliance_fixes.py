"""audit compliance fixes — product_line isolation, cross-module linkages, new tables

Revision ID: 015
Revises: 014_add_version_tables
Create Date: 2026-05-25

Adds:
- product_line_code to audit_programs, audit_plans, gauges, GRR/bias/linearity/stability/attribute studies
- Rename quality_goals.product_line → product_line_code
- sop_ref, spc_chart_id, gauge_id to control_plan_items
- linked_fmea_node_id to spc_alarms
- data_source_formula to quality_goals
- New tables: supplier_ppap_submissions, supplier_ppap_elements, iqc_inspections, supplier_scars, audit_checklist_templates
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '015'
down_revision: Union[str, None] = '014_add_version_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === product_line_code additions ===
    for table in ['audit_programs', 'audit_plans', 'gauges', 'grr_studies',
                   'bias_studies', 'linearity_studies', 'stability_studies', 'attribute_studies']:
        op.add_column(table, sa.Column('product_line_code', sa.VARCHAR(20), nullable=True))
        op.create_index(f'ix_{table}_product_line', table, ['product_line_code'])

    # === quality_goals: rename product_line → product_line_code ===
    op.alter_column('quality_goals', 'product_line', new_column_name='product_line_code')

    # === control_plan_items: cross-module linkage fields ===
    op.add_column('control_plan_items', sa.Column('sop_ref', sa.VARCHAR(100), nullable=True))
    op.add_column('control_plan_items', sa.Column('spc_chart_id', postgresql.UUID(), nullable=True))
    op.add_column('control_plan_items', sa.Column('gauge_id', postgresql.UUID(), nullable=True))
    op.create_foreign_key('fk_cpi_gauge', 'control_plan_items', 'gauges', ['gauge_id'], ['gauge_id'], ondelete='SET NULL')
    op.create_foreign_key('fk_cpi_spc_chart', 'control_plan_items', 'inspection_characteristics', ['spc_chart_id'], ['ic_id'], ondelete='SET NULL')

    # === spc_alarms: FMEA traceability ===
    op.add_column('spc_alarms', sa.Column('linked_fmea_node_id', postgresql.UUID(), nullable=True))

    # === quality_goals: data_source_formula ===
    op.add_column('quality_goals', sa.Column('data_source_formula', sa.VARCHAR(200), nullable=True))

    # === New table: audit_checklist_templates ===
    op.create_table('audit_checklist_templates',
        sa.Column('template_id', postgresql.UUID(), primary_key=True),
        sa.Column('name', sa.VARCHAR(100), nullable=False),
        sa.Column('audit_type', sa.VARCHAR(20), nullable=False),
        sa.Column('items', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('is_default', sa.BOOLEAN(), nullable=False, server_default='false'),
        sa.Column('created_by', postgresql.UUID(), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_act_audit_type', 'audit_checklist_templates', ['audit_type'])

    # === New table: supplier_ppap_submissions ===
    op.create_table('supplier_ppap_submissions',
        sa.Column('submission_id', postgresql.UUID(), primary_key=True),
        sa.Column('supplier_id', postgresql.UUID(), sa.ForeignKey('suppliers.supplier_id', ondelete='CASCADE'), nullable=False),
        sa.Column('part_no', sa.VARCHAR(100), nullable=False),
        sa.Column('part_name', sa.VARCHAR(200), nullable=False),
        sa.Column('submission_level', sa.Integer(), nullable=False),
        sa.Column('submission_date', sa.Date(), nullable=True),
        sa.Column('status', sa.VARCHAR(20), nullable=False, server_default='draft'),
        sa.Column('approved_by', postgresql.UUID(), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', postgresql.UUID(), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_ppap_supplier', 'supplier_ppap_submissions', ['supplier_id'])

    # === New table: supplier_ppap_elements ===
    op.create_table('supplier_ppap_elements',
        sa.Column('element_id', postgresql.UUID(), primary_key=True),
        sa.Column('submission_id', postgresql.UUID(), sa.ForeignKey('supplier_ppap_submissions.submission_id', ondelete='CASCADE'), nullable=False),
        sa.Column('element_no', sa.Integer(), nullable=False),
        sa.Column('element_name', sa.VARCHAR(200), nullable=False),
        sa.Column('status', sa.VARCHAR(20), nullable=False, server_default='pending'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_ppap_elements_submission', 'supplier_ppap_elements', ['submission_id'])

    # === New table: iqc_inspections ===
    op.create_table('iqc_inspections',
        sa.Column('inspection_id', postgresql.UUID(), primary_key=True),
        sa.Column('inspection_no', sa.VARCHAR(50), unique=True, nullable=False),
        sa.Column('supplier_id', postgresql.UUID(), sa.ForeignKey('suppliers.supplier_id', ondelete='CASCADE'), nullable=False),
        sa.Column('part_no', sa.VARCHAR(100), nullable=True),
        sa.Column('part_name', sa.VARCHAR(200), nullable=True),
        sa.Column('lot_no', sa.VARCHAR(50), nullable=True),
        sa.Column('lot_qty', sa.Integer(), nullable=True),
        sa.Column('sample_qty', sa.Integer(), nullable=True),
        sa.Column('inspection_result', sa.VARCHAR(20), nullable=False, server_default='pending'),
        sa.Column('defect_qty', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('defect_description', sa.Text(), nullable=True),
        sa.Column('linked_capa_id', postgresql.UUID(), sa.ForeignKey('capa_eightd.report_id', ondelete='SET NULL'), nullable=True),
        sa.Column('inspection_date', sa.Date(), nullable=True),
        sa.Column('inspected_by', postgresql.UUID(), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_iqc_supplier', 'iqc_inspections', ['supplier_id'])
    op.create_index('ix_iqc_result', 'iqc_inspections', ['inspection_result'])

    # === New table: supplier_scars ===
    op.create_table('supplier_scars',
        sa.Column('scar_id', postgresql.UUID(), primary_key=True),
        sa.Column('scar_no', sa.VARCHAR(50), unique=True, nullable=False),
        sa.Column('supplier_id', postgresql.UUID(), sa.ForeignKey('suppliers.supplier_id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_type', sa.VARCHAR(20), nullable=False),
        sa.Column('source_id', postgresql.UUID(), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('requested_action', sa.Text(), nullable=True),
        sa.Column('supplier_response', sa.Text(), nullable=True),
        sa.Column('status', sa.VARCHAR(20), nullable=False, server_default='open'),
        sa.Column('issued_by', postgresql.UUID(), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('issued_date', sa.Date(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('closed_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_scar_supplier', 'supplier_scars', ['supplier_id'])
    op.create_index('ix_scar_status', 'supplier_scars', ['status'])


def downgrade() -> None:
    op.drop_table('supplier_scars')
    op.drop_table('iqc_inspections')
    op.drop_table('supplier_ppap_elements')
    op.drop_table('supplier_ppap_submissions')
    op.drop_table('audit_checklist_templates')

    op.drop_column('quality_goals', 'data_source_formula')
    op.drop_column('spc_alarms', 'linked_fmea_node_id')
    op.drop_constraint('fk_cpi_spc_chart', 'control_plan_items', type_='foreignkey')
    op.drop_constraint('fk_cpi_gauge', 'control_plan_items', type_='foreignkey')
    op.drop_column('control_plan_items', 'gauge_id')
    op.drop_column('control_plan_items', 'spc_chart_id')
    op.drop_column('control_plan_items', 'sop_ref')

    op.alter_column('quality_goals', 'product_line_code', new_column_name='product_line')

    for table in ['attribute_studies', 'stability_studies', 'linearity_studies',
                   'bias_studies', 'grr_studies', 'gauges', 'audit_plans', 'audit_programs']:
        op.drop_index(f'ix_{table}_product_line', table_name=table)
        op.drop_column(table, 'product_line_code')
