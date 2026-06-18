"""recreate recommendation_cache partial unique indexes (drift fix)

Revision ID: 20260617_rec_cache_idx
Revises: 20260616_add_system_settings
Create Date: 2026-06-17

The recommendation_cache upsert in recommendation_service._cache_result uses
``ON CONFLICT (fmea_id, trigger_type, context_hash) WHERE fmea_id IS NOT NULL``
(for FMEA recommendations) and analogous targets for CAPA / global rows. Each
requires a matching partial unique index.

Migration 032_lessons_learned_cache was supposed to create uq_cache_fmea /
uq_cache_capa / uq_cache_global, but ``bfd90bb593fc`` is a branchpoint that also
spawns ``032_add_erp_tables`` (overlapping 032_* numbering). On databases
migrated along the 20260616_add_system_settings lineage those index creations
did not land, so the recommend endpoint 500s at the cache step with
``InvalidColumnReferenceError: there is no unique or exclusion constraint
matching the ON CONFLICT specification``.

This migration recreates the three partial unique indexes idempotently
(``IF NOT EXISTS``) so the recommend endpoint stops 500-ing, and so other
environments get the indexes regardless of which 032_* branch they took.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260617_rec_cache_idx"
down_revision: Union[str, None] = "20260616_add_system_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, columns, partial predicate) — matches migration 032's intent
# and the on_conflict_do_update targets in recommendation_service._cache_result.
_INDEXES = [
    ("uq_cache_fmea", "(fmea_id, trigger_type, context_hash)", "fmea_id IS NOT NULL"),
    ("uq_cache_capa", "(report_id, trigger_type, context_hash)", "report_id IS NOT NULL"),
    ("uq_cache_global", "(trigger_type, context_hash)", "fmea_id IS NULL AND report_id IS NULL"),
]


def upgrade() -> None:
    for name, cols, where in _INDEXES:
        op.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {name} "
            f"ON recommendation_cache {cols} WHERE {where}"
        )


def downgrade() -> None:
    for name, _, _ in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")