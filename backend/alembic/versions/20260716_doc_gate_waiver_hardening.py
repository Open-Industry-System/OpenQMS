"""Invalidate all historical doc-gate waivers after Round25 hardening.

Revision ID: 20260716_doc_gate_waiver_hardening
Revises: 20260715_waiver_items
Create Date: 2026-07-16

Round25 added binding, freshness, and decision-identity guarantees that older
persisted waivers did not enforce when they were written.  Every historical
waiver is therefore invalidated fail-closed and must be re-audited/re-approved.

This is an irreversible data invalidation.  Downgrade intentionally does not
restore waiver data because doing so would recreate approvals that no longer
satisfy the hardened contract.
"""
from alembic import op


revision = "20260716_doc_gate_waiver_hardening"
down_revision = "20260715_waiver_items"
branch_labels = None
depends_on = None


_ACTION = "DOC_GATE_WAIVER_INVALIDATED"
_ANALYSIS_MARKER = (
    "[ROUND25_WAIVER_INVALIDATED] Historical doc-gate waiver invalidated by "
    "migration 20260716; re-run the audit and record a new waiver."
)


def upgrade() -> None:
    # This mandated descriptive revision id exceeds Alembic's legacy
    # VARCHAR(32) bootstrap default.  Widen before Alembic records the new head.
    op.execute("""
        ALTER TABLE alembic_version
        ALTER COLUMN version_num TYPE VARCHAR(64)
    """)

    # Audit first: decision UPDATE below deliberately destroys the old waiver
    # payload, so the immutable event must capture it before invalidation.
    op.execute(f"""
        INSERT INTO audit_logs (
            log_id,
            table_name,
            record_id,
            action,
            changed_fields,
            operated_by,
            factory_id,
            operated_at
        )
        SELECT
            gen_random_uuid(),
            'capa_docg_decision',
            a.capa_id,
            '{_ACTION}',
            jsonb_build_object(
                'analysis_id', d.analysis_id,
                'decision_id', d.decision_id,
                'revision', d.revision,
                'audit_run_id', d.audit_run_id,
                'waiver_reason', d.waiver_reason,
                'waiver_items', d.waiver_items,
                'invalidation_reason', 'Round25 waiver contract hardening'
            ),
            d.decided_by,
            d.factory_id,
            now()
        FROM capa_docg_decision AS d
        JOIN capa_docg_analysis AS a
          ON a.analysis_id = d.analysis_id
         AND a.factory_id = d.factory_id
        WHERE d.waiver_reason IS NOT NULL
           OR d.waiver_items IS NOT NULL
    """)

    op.execute("""
        UPDATE capa_docg_decision
        SET decision = 'blocked',
            defer_reason = NULL,
            defer_owner = NULL,
            defer_deadline = NULL,
            waiver_reason = NULL,
            waiver_items = NULL,
            version_snapshot = '[]'::jsonb
        WHERE waiver_reason IS NOT NULL
           OR waiver_items IS NOT NULL
    """)

    # The audit rows retain the affected analysis ids after the decision
    # payload is cleared.  Mark current analyses only; unrelated analyses are
    # deliberately untouched.
    op.execute(f"""
        UPDATE capa_docg_analysis AS a
        SET error = CASE
            WHEN NULLIF(a.error, '') IS NULL THEN '{_ANALYSIS_MARKER}'
            ELSE a.error || E'\\n' || '{_ANALYSIS_MARKER}'
        END
        WHERE a.is_current = true
          AND EXISTS (
              SELECT 1
              FROM audit_logs AS l
              WHERE l.action = '{_ACTION}'
                AND l.changed_fields->>'analysis_id' = a.analysis_id::text
          )
    """)


def downgrade() -> None:
    """Do not restore invalidated approvals; this data migration is irreversible."""
    pass
