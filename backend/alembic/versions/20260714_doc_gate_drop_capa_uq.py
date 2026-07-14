"""Drop uq_docg_analysis_capa_factory full UNIQUE (终审第七轮 P0#1)

Revision ID: 20260714_doc_gate_drop_capa_uq
Revises: 20260713_doc_gate
Create Date: 2026-07-14

The original doc-gate migration (20260713_doc_gate) created a full
UNIQUE(capa_id, factory_id) on capa_docg_analysis. This blocked retry /
regeneration: a second analysis row for the same capa (is_current=false,
status=failed/done) violates the constraint with a 500. Retry/regeneration
concurrency is already guarded by the partial unique indexes
uq_docg_analysis_current (is_current=true) and uq_docg_analysis_running
(status='running'). This migration drops the redundant full UQ on already-
upgraded databases. Idempotent via IF EXISTS.
"""
from alembic import op


revision = "20260714_doc_gate_drop_capa_uq"
down_revision = "20260713_doc_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE capa_docg_analysis "
        "DROP CONSTRAINT IF EXISTS uq_docg_analysis_capa_factory"
    )


def downgrade() -> None:
    # Irreversible once retry/regeneration history exists: re-adding the full UQ
    # would either fail on duplicates or leave schema/revision inconsistent if
    # we skip. Raise so operators must handle data before rolling back.
    raise NotImplementedError(
        "20260714_doc_gate_drop_capa_uq is irreversible: retry history may "
        "contain multiple rows per (capa_id, factory_id). Clean those rows "
        "manually before re-adding uq_docg_analysis_capa_factory."
    )
