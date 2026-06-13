"""add indexes on frequently-joined foreign key columns

Adds indexes on the most-queried FK columns that were missing indexes.
These columns are used in JOIN, WHERE, and ORDER BY clauses across
list/detail/dashboard queries.

Uses IF NOT EXISTS because migration 036_fid_not_null may have already
created some factory_id indexes.

Revision ID: 039
Revises: 038_ensure_pgcrypto_extension
"""
from alembic import op
import sqlalchemy as sa


revision = '039'
down_revision = '038'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    indexes = [
        ('ix_fmea_documents_factory_id', 'fmea_documents', ['factory_id']),
        ('ix_fmea_documents_created_by', 'fmea_documents', ['created_by']),
        ('ix_fmea_documents_product_line_code', 'fmea_documents', ['product_line_code']),
        ('ix_capa_eightd_factory_id', 'capa_eightd', ['factory_id']),
        ('ix_capa_eightd_created_by', 'capa_eightd', ['created_by']),
        ('ix_control_plans_factory_id', 'control_plans', ['factory_id']),
        ('ix_suppliers_factory_id', 'suppliers', ['factory_id']),
        ('ix_spc_charts_factory_id', 'spc_charts', ['factory_id']),
        ('ix_iqc_materials_factory_id', 'iqc_materials', ['factory_id']),
        ('ix_audit_programs_factory_id', 'audit_programs', ['factory_id']),
        ('ix_special_characteristics_source_fmea_id', 'special_characteristics', ['source_fmea_id']),
        ('ix_supplier_risk_alerts_supplier_id', 'supplier_risk_alerts', ['supplier_id']),
    ]
    for name, table, columns in indexes:
        cols = ', '.join(columns)
        conn.execute(sa.text(
            f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})'
        ))


def downgrade() -> None:
    conn = op.get_bind()
    indexes = [
        ('ix_supplier_risk_alerts_supplier_id', 'supplier_risk_alerts'),
        ('ix_special_characteristics_source_fmea_id', 'special_characteristics'),
        ('ix_audit_programs_factory_id', 'audit_programs'),
        ('ix_iqc_materials_factory_id', 'iqc_materials'),
        ('ix_spc_charts_factory_id', 'spc_charts'),
        ('ix_suppliers_factory_id', 'suppliers'),
        ('ix_control_plans_factory_id', 'control_plans'),
        ('ix_capa_eightd_created_by', 'capa_eightd'),
        ('ix_capa_eightd_factory_id', 'capa_eightd'),
        ('ix_fmea_documents_product_line_code', 'fmea_documents'),
        ('ix_fmea_documents_created_by', 'fmea_documents'),
        ('ix_fmea_documents_factory_id', 'fmea_documents'),
    ]
    for name, table in indexes:
        conn.execute(sa.text(f'DROP INDEX IF EXISTS {name}'))