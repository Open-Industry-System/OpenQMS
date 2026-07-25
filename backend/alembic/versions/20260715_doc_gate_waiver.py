"""Add waiver_reason column to capa_docg_decision (US-E2E-01.7 disposition).

Revision ID: 20260715_doc_gate_waiver
Revises: 20260715_version_hash_backfill
Create Date: 2026-07-15

Adds an audited waiver path for blocked_modify lineage breaks where the only
other remediation is re-authoring the CP under a new CAPA (the state machine
forbids archiving D8_GATE_PENDING directly). A manager-authorized waiver
records a reason and forces decision=passed so the CAPA can advance.

Downgrade drops the column and the associated CHECK. Waiver rows are lost.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260715_doc_gate_waiver"
down_revision = "20260715_version_hash_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "capa_docg_decision",
        sa.Column("waiver_reason", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "chk_docg_waiver_only_passed",
        "capa_docg_decision",
        "decision!='passed' OR waiver_reason IS NULL OR no_affected_confirmed=false",
    )


def downgrade() -> None:
    op.drop_constraint("chk_docg_waiver_only_passed", "capa_docg_decision", type_="check")
    op.drop_column("capa_docg_decision", "waiver_reason")
