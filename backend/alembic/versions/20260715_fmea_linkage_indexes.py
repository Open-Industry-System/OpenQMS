"""FMEA linkage reverse-lookup indexes (US-E2E-01.4)

Revision ID: 20260715_fmea_linkage_indexes
Revises: 20260715_cp_version_trigger
Create Date: 2026-07-15

Adds partial/expression indexes for the three reverse-lookup sources (header
fmea_ref_id, D7 fmea_id+action, D4 source_ref JSONB paths).

Note: audit_logs.action is already VARCHAR(50) via 20260710_widen_audit_action
(model String(50)); this revision must not re-narrow/re-widen that column.

down_revision chains after 20260715_cp_version_trigger (parent branch head)
so merge into feature/us-e2e-01-spec-a does not create dual alembic heads.
"""
from alembic import op

revision = "20260715_fmea_linkage_indexes"
down_revision = "20260715_cp_version_trigger"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
