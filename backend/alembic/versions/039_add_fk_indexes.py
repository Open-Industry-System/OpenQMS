"""add indexes on frequently-joined foreign key columns

Adds indexes on the most-queried FK columns that were missing indexes.
These columns are used in JOIN, WHERE, and ORDER BY clauses across
list/detail/dashboard queries.

Revision ID: 039
Revises: 038_ensure_pgcrypto_extension
"""
from alembic import op


revision = '039'
down_revision = '038'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # fmea_documents
    op.create_index('ix_fmea_documents_factory_id', 'fmea_documents', ['factory_id'])
    op.create_index('ix_fmea_documents_created_by', 'fmea_documents', ['created_by'])
    op.create_index('ix_fmea_documents_product_line_code', 'fmea_documents', ['product_line_code'])

    # capa_eightd
    op.create_index('ix_capa_eightd_factory_id', 'capa_eightd', ['factory_id'])
    op.create_index('ix_capa_eightd_created_by', 'capa_eightd', ['created_by'])

    # control_plans
    op.create_index('ix_control_plans_factory_id', 'control_plans', ['factory_id'])

    # suppliers
    op.create_index('ix_suppliers_factory_id', 'suppliers', ['factory_id'])

    # spc_charts
    op.create_index('ix_spc_charts_factory_id', 'spc_charts', ['factory_id'])

    # iqc_materials
    op.create_index('ix_iqc_materials_factory_id', 'iqc_materials', ['factory_id'])

    # audit_programs
    op.create_index('ix_audit_programs_factory_id', 'audit_programs', ['factory_id'])

    # special_characteristics
    op.create_index('ix_special_characteristics_source_fmea_id', 'special_characteristics', ['source_fmea_id'])

    # supplier_risk_alerts
    op.create_index('ix_supplier_risk_alerts_supplier_id', 'supplier_risk_alerts', ['supplier_id'])


def downgrade() -> None:
    op.drop_index('ix_supplier_risk_alerts_supplier_id', table_name='supplier_risk_alerts')
    op.drop_index('ix_special_characteristics_source_fmea_id', table_name='special_characteristics')
    op.drop_index('ix_audit_programs_factory_id', table_name='audit_programs')
    op.drop_index('ix_iqc_materials_factory_id', table_name='iqc_materials')
    op.drop_index('ix_spc_charts_factory_id', table_name='spc_charts')
    op.drop_index('ix_suppliers_factory_id', table_name='suppliers')
    op.drop_index('ix_control_plans_factory_id', table_name='control_plans')
    op.drop_index('ix_capa_eightd_created_by', table_name='capa_eightd')
    op.drop_index('ix_capa_eightd_factory_id', table_name='capa_eightd')
    op.drop_index('ix_fmea_documents_product_line_code', table_name='fmea_documents')
    op.drop_index('ix_fmea_documents_created_by', table_name='fmea_documents')
    op.drop_index('ix_fmea_documents_factory_id', table_name='fmea_documents')