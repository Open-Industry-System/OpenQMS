"""Add waiver_items JSONB for structured per-keypoint waiver (US-E2E-01.7 Round 23).

Revision ID: 20260715_waiver_items
Revises: 20260715_fmea_linkage_indexes
Create Date: 2026-07-15

waiver_items stores the exact blocked_modify keypoints a manager waived:
[{doc_type, doc_id, target_key, field, latest_version_id, latest_sha256}].
A waiver without items is invalid; C8 and preflight only skip exact matches.
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
