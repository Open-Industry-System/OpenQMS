"""FMEA linkage reverse-lookup indexes + widen audit_logs.action (US-E2E-01.4)

Revision ID: 20260715_fmea_linkage_indexes
Revises: 20260714_doc_gate_drop_capa_uq
Create Date: 2026-07-15

Adds partial/expression indexes for the three reverse-lookup sources (header
fmea_ref_id, D7 fmea_id+action, D4 source_ref JSONB paths) and widens
audit_logs.action to VARCHAR(32) to fit D4_VERIFICATION_UPDATED (23) and
FMEA_LINKAGE_CREATED (20).
"""
import sqlalchemy as sa
from alembic import op

revision = "20260715_fmea_linkage_indexes"
down_revision = "20260714_doc_gate_drop_capa_uq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widen audit action (was 20 after 20260710_widen_audit_action).
    op.alter_column("audit_logs", "action",
                     type_=sa.VARCHAR(32),
                     existing_type=sa.VARCHAR(20),
                     nullable=True)

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_capa_eightd_fmea_ref_id "
        "ON capa_eightd (fmea_ref_id) WHERE fmea_ref_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_capa_eightd_factory_fmea "
        "ON capa_eightd (factory_id, fmea_ref_id) WHERE fmea_ref_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_capa_d7_fmea_action "
        "ON capa_d7_node_action (fmea_id, action) WHERE fmea_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_capa_rcv_source_fmea "
        "ON capa_root_cause_verification ((source_ref->>'fmea_id')) "
        "WHERE source_ref IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_capa_rcv_source_cause "
        "ON capa_root_cause_verification ((source_ref->>'cause_node_id')) "
        "WHERE source_ref IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_capa_rcv_source_cause")
    op.execute("DROP INDEX IF EXISTS ix_capa_rcv_source_fmea")
    op.execute("DROP INDEX IF EXISTS ix_capa_d7_fmea_action")
    op.execute("DROP INDEX IF EXISTS ix_capa_eightd_factory_fmea")
    op.execute("DROP INDEX IF EXISTS ix_capa_eightd_fmea_ref_id")
    op.alter_column("audit_logs", "action",
                     type_=sa.VARCHAR(20),
                     existing_type=sa.VARCHAR(32),
                     nullable=True)
