"""Backfill version sha256_hash to PG jsonb::text digest (content integrity).

Revision ID: 20260715_version_hash_backfill
Revises: 20260715_cp_version_trigger
Create Date: 2026-07-15

Historical rows may still store compact-JSON hashes from the old app algorithm.
New inserts (after 20260715_cp_version_trigger) store PG jsonb::text digests.
This migration rewrites all existing hashes to the PG form so verify_* and C8/C9
comparisons share one representation going forward.

Side effect: current doc-gate analyses store the OLD baseline hash inside
affected_docs[].baseline_version.sha256 and inside analysis_input_hash (C9).
After this rewrite, those embedded hashes no longer match the version rows → C9
will force regeneration for the affected CAPAs. To avoid a silent surprise, this
migration also demotes is_current=true doc-gate analyses whose baseline hash
changed, so engineers see "analysis input changed, regenerate" rather than an
inconsistent gate. The preflight will then report those CAPAs for re-analysis.

Irreversible: downgrade raises — old compact hashes are not retained, so
returning the app to compact-only verify is unsupported.
"""
from alembic import op


revision = "20260715_version_hash_backfill"
down_revision = "20260715_cp_version_trigger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Disable immutability so we can rewrite hashes
    op.execute("ALTER TABLE fmea_versions DISABLE TRIGGER trg_fmea_version_no_update")
    op.execute("ALTER TABLE control_plan_versions DISABLE TRIGGER trg_cp_version_no_update")

    # FMEA: hash = digest(snapshot::text)
    op.execute("""
        UPDATE fmea_versions
        SET sha256_hash = encode(digest(snapshot::text, 'sha256'), 'hex')
        WHERE snapshot IS NOT NULL
    """)

    # CP: hash = digest(jsonb_build_object('header', header, 'items', items)::text)
    op.execute("""
        UPDATE control_plan_versions
        SET sha256_hash = encode(
            digest(
                jsonb_build_object(
                    'header', header_snapshot,
                    'items', items_snapshot
                )::text,
                'sha256'
            ),
            'hex'
        )
        WHERE header_snapshot IS NOT NULL AND items_snapshot IS NOT NULL
    """)

    op.execute("ALTER TABLE fmea_versions ENABLE TRIGGER trg_fmea_version_no_update")
    op.execute("ALTER TABLE control_plan_versions ENABLE TRIGGER trg_cp_version_no_update")

    # Demote current doc-gate analyses whose embedded baseline sha256 no longer
    # matches the rewritten version row hash. The analysis row is kept (history)
    # but is_current=false; the next /impact generation creates a fresh current
    # analysis with the correct PG hash. This is fail-closed: the gate will
    # block until the engineer regenerates.
    op.execute("""
        UPDATE capa_docg_analysis a
        SET is_current = false,
            error = COALESCE(error || ' | ', '') || 'demoted by hash backfill migration'
        WHERE a.is_current = true
          AND EXISTS (
            SELECT 1 FROM jsonb_array_elements(a.affected_docs) AS d
            WHERE (d->>'doc_type') = 'control_plan'
              AND d->'baseline_version'->>'sha256' IS NOT NULL
              AND d->'baseline_version'->>'sha256' <> (
                SELECT v.sha256_hash FROM control_plan_versions v
                WHERE v.version_id::text = d->>'baseline_version_id'
              )
          )
    """)
    op.execute("""
        UPDATE capa_docg_analysis a
        SET is_current = false,
            error = COALESCE(error || ' | ', '') || 'demoted by hash backfill migration'
        WHERE a.is_current = true
          AND EXISTS (
            SELECT 1 FROM jsonb_array_elements(a.affected_docs) AS d
            WHERE (d->>'doc_type') = 'fmea'
              AND d->'baseline_version'->>'sha256' IS NOT NULL
              AND d->'baseline_version'->>'sha256' <> (
                SELECT v.sha256_hash FROM fmea_versions v
                WHERE v.version_id::text = d->>'baseline_version_id'
              )
          )
    """)


def downgrade() -> None:
    # Irreversible: compact hashes are not retained, so the app cannot safely
    # return to compact-only verify. Block the rollback explicitly.
    raise NotImplementedError(
        "20260715_version_hash_backfill is irreversible: old compact-JSON hashes "
        "are not retained. Do not roll back to a compact-only verify app."
    )

