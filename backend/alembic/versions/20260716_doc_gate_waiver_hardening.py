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
        WITH candidates AS (
            SELECT
                d.decision_id,
                d.analysis_id,
                d.audit_run_id,
                d.revision,
                d.factory_id,
                d.decided_by,
                a.capa_id,
                COALESCE(d.waiver_reason, legacy.changed_fields->>'reason')
                    AS old_waiver_reason,
                COALESCE(d.waiver_items, legacy.changed_fields->'waiver_items')
                    AS old_waiver_items,
                CASE
                    WHEN d.waiver_reason IS NOT NULL OR d.waiver_items IS NOT NULL
                        THEN d.decision
                    ELSE COALESCE(legacy.changed_fields->>'decision_to', d.decision)
                END AS old_decision,
                d.version_snapshot AS old_version_snapshot,
                d.no_affected_confirmed AS old_no_affected_confirmed,
                CASE
                    WHEN d.waiver_reason IS NOT NULL OR d.waiver_items IS NOT NULL
                        THEN 'persisted_waiver_fields'
                    ELSE 'historical_doc_gate_waiver_event'
                END AS evidence_source
            FROM capa_docg_decision AS d
            JOIN capa_docg_analysis AS a
              ON a.analysis_id = d.analysis_id
             AND a.factory_id = d.factory_id
            LEFT JOIN LATERAL (
                SELECT l.changed_fields
                FROM audit_logs AS l
                WHERE l.action = 'DOC_GATE_WAIVER'
                  AND l.table_name = 'capa_eightd'
                  AND l.record_id = a.capa_id
                  AND l.factory_id = d.factory_id
                  AND l.operated_by = d.decided_by
                  AND d.audit_run_id IS NOT NULL
                  AND l.changed_fields->>'audit_run_id' = d.audit_run_id::text
                  AND l.operated_at BETWEEN d.decided_at - interval '5 minutes'
                                        AND d.decided_at + interval '5 minutes'
                ORDER BY l.operated_at DESC, l.log_id DESC
                LIMIT 1
            ) AS legacy ON true
            WHERE d.waiver_reason IS NOT NULL
               OR d.waiver_items IS NOT NULL
               OR (
                    d.decision = 'blocked'
                    AND d.waiver_reason IS NULL
                    AND d.waiver_items IS NULL
                    AND d.version_snapshot = '[]'::jsonb
                    AND legacy.changed_fields IS NOT NULL
               )
        )
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
            'capa_eightd',
            c.capa_id,
            '{_ACTION}',
            jsonb_build_object(
                'analysis_id', c.analysis_id,
                'decision_id', c.decision_id,
                'revision', c.revision,
                'audit_run_id', c.audit_run_id,
                'waiver_reason', c.old_waiver_reason,
                'waiver_items', c.old_waiver_items,
                'old_decision', c.old_decision,
                'old_version_snapshot', c.old_version_snapshot,
                'old_no_affected_confirmed', c.old_no_affected_confirmed,
                'evidence_source', c.evidence_source,
                'invalidation_reason', 'Round25 waiver contract hardening'
            ),
            c.decided_by,
            c.factory_id,
            now()
        FROM candidates AS c
    """)

    op.execute("""
        UPDATE capa_docg_decision AS d
        SET decision = 'blocked',
            defer_reason = NULL,
            defer_owner = NULL,
            defer_deadline = NULL,
            waiver_reason = NULL,
            waiver_items = NULL,
            version_snapshot = '[]'::jsonb
        WHERE EXISTS (
            SELECT 1
            FROM audit_logs AS l
            WHERE l.action = 'DOC_GATE_WAIVER_INVALIDATED'
              AND l.changed_fields->>'decision_id' = d.decision_id::text
        )
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
