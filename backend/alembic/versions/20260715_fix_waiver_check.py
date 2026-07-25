"""Fix waiver CHECK constraint to correctly restrict waiver_reason (US-E2E-01.7 Round 22).

Revision ID: 20260715_fix_waiver_check
Revises: 20260715_doc_gate_waiver
Create Date: 2026-07-15

The old constraint (decision!='passed' OR waiver_reason IS NULL OR …) allowed
blocked/deferred rows to carry a non-null waiver_reason. The corrected form
requires: waiver_reason IS NULL OR (decision='passed' AND no_affected_confirmed=false).
"""
from alembic import op


revision = "20260715_fix_waiver_check"
down_revision = "20260715_doc_gate_waiver"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("chk_docg_waiver_only_passed", "capa_docg_decision", type_="check")
    op.create_check_constraint(
        "chk_docg_waiver_only_passed",
        "capa_docg_decision",
        "waiver_reason IS NULL OR (decision='passed' AND no_affected_confirmed=false)",
    )


def downgrade() -> None:
    op.drop_constraint("chk_docg_waiver_only_passed", "capa_docg_decision", type_="check")
    op.create_check_constraint(
        "chk_docg_waiver_only_passed",
        "capa_docg_decision",
        "decision!='passed' OR waiver_reason IS NULL OR no_affected_confirmed=false",
    )