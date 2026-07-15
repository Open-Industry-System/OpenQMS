"""Add waiver_items JSONB for structured per-keypoint waiver (US-E2E-01.7 Round 23/24).

Revision ID: 20260715_waiver_items
Revises: 20260715_fmea_linkage_indexes
Create Date: 2026-07-15

waiver_items stores the exact blocked_modify keypoints a manager waived:
[{doc_type, doc_id, target_key, field, latest_version_id, latest_sha256, audit_run_id}].
A waiver without items is invalid; C8 and preflight only skip exact matches
when the bound version_id/sha still equals live latest.

Legacy Round-21/22 rows may have waiver_reason set with waiver_items NULL.
Those are unconditional C8 bypasses and must be invalidated before the CHECK
is applied, otherwise upgrade fails (and worse: leaves a generic bypass).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260715_waiver_items"
down_revision = "20260715_fmea_linkage_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "capa_docg_decision",
        sa.Column("waiver_items", JSONB(), nullable=True),
    )
    # Invalidate legacy unstructured waivers (reason set, no items). They were
    # a full C8 bypass; force re-audit + structured re-waiver after upgrade.
    op.execute("""
        UPDATE capa_docg_decision
        SET decision = 'blocked',
            waiver_reason = NULL,
            version_snapshot = '[]'::jsonb
        WHERE waiver_reason IS NOT NULL
          AND (waiver_items IS NULL
               OR jsonb_typeof(waiver_items) <> 'array'
               OR jsonb_array_length(waiver_items) = 0)
    """)
    # When waiver_reason is set, waiver_items must be a non-empty array.
    op.create_check_constraint(
        "chk_docg_waiver_items",
        "capa_docg_decision",
        "waiver_reason IS NULL OR ("
        "waiver_items IS NOT NULL AND jsonb_typeof(waiver_items)='array' "
        "AND jsonb_array_length(waiver_items) > 0)",
    )


def downgrade() -> None:
    op.drop_constraint("chk_docg_waiver_items", "capa_docg_decision", type_="check")
    op.drop_column("capa_docg_decision", "waiver_items")
