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
    # Safe path: no multi-row history → restore UQ.
    # Unsafe path: retry history exists → abort (do not leave revision/schema drift).
    from alembic import op
    conn = op.get_bind()
    n = conn.exec_driver_sql(
        "SELECT COUNT(*) FROM ("
        "  SELECT 1 FROM capa_docg_analysis GROUP BY capa_id, factory_id HAVING COUNT(*) > 1"
        ") d"
    ).scalar()
    if n and int(n) > 0:
        raise RuntimeError(
            "Cannot downgrade 20260714_doc_gate_drop_capa_uq: "
            f"{n} (capa_id, factory_id) groups have multiple analysis rows "
            "(retry history). Clean them before restoring uq_docg_analysis_capa_factory."
        )
    op.create_unique_constraint(
        "uq_docg_analysis_capa_factory",
        "capa_docg_analysis",
        ["capa_id", "factory_id"],
    )
