"""Backfill version sha256_hash to PG jsonb::text digest (content integrity).

Revision ID: 20260715_version_hash_backfill
Revises: 20260715_cp_version_trigger
Create Date: 2026-07-15

Historical rows may still store compact-JSON hashes from the old app algorithm.
New inserts (after 20260715_cp_version_trigger) store PG jsonb::text digests.
This migration rewrites all existing hashes to the PG form so verify_* and C8/C9
comparisons share one representation going forward.

Temporarily disables immutability triggers (trg_*_version_no_update) for the
UPDATE, then re-enables them. Idempotent: re-running produces the same digests.
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


def downgrade() -> None:
    # Cannot restore previous compact-JSON hashes (not retained). No-op with notice.
    # App dual-algorithm verify still accepts PG digests after downgrade of this
    # data migration; rolling back the app to compact-only verify without this
    # backfill's inverse is unsupported — keep app dual-verify when rolling back.
    pass
