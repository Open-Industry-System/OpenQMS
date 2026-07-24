"""capa_docg_* tables for US-E2E-01.7 D8 doc update gate.

Revision ID: 20260713_doc_gate
Revises: 20260713_d3_execution_fk_correct
Create Date: 2026-07-13

Creates 3 tables:
- capa_docg_analysis: LLM impact analysis generation root (running partial-UQ +
  status-state CHECK + done-completeness CHECK)
- capa_docg_audit: per-doc audit rows grouped by audit_run_id
- capa_docg_decision: append-only gate decisions with revision UQ
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260713_doc_gate"
down_revision = "20260713_d3_execution_fk_correct"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capa_docg_analysis",
        sa.Column("analysis_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("capa_id", UUID(as_uuid=True), sa.ForeignKey("capa_eightd.report_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("factory_id", UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(10), nullable=False, server_default="running"),
        sa.Column("affected_docs", JSONB),
        sa.Column("analysis_input_hash", sa.String(64)),
        sa.Column("llm_available", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("model", sa.String(40)),
        sa.Column("prompt_stats", JSONB),
        sa.Column("error", sa.Text),
        sa.Column("attempt_token", UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("generated_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("analysis_id", "factory_id", name="uq_docg_analysis_factory"),
        sa.ForeignKeyConstraint(
            ["capa_id", "factory_id"],
            ["capa_eightd.report_id", "capa_eightd.factory_id"],
            ondelete="RESTRICT",
            name="fk_docg_analysis_capa_factory",
        ),
        sa.CheckConstraint("status IN ('running','done','failed')", name="chk_docg_analysis_status"),
        sa.CheckConstraint(
            "(status='running' AND is_current=false AND completed_at IS NULL) "
            "OR (status='failed' AND is_current=false AND completed_at IS NOT NULL) "
            "OR (status='done' AND completed_at IS NOT NULL)",
            name="chk_docg_analysis_status_state",
        ),
        sa.CheckConstraint(
            "status!='done' OR (affected_docs IS NOT NULL AND analysis_input_hash IS NOT NULL "
            "AND llm_available=true AND completed_at IS NOT NULL)",
            name="chk_docg_analysis_done_complete",
        ),
    )
    op.create_index("uq_docg_analysis_current", "capa_docg_analysis", ["capa_id"],
                    unique=True, postgresql_where=sa.text("is_current = true"))
    op.create_index("uq_docg_analysis_running", "capa_docg_analysis", ["capa_id"],
                    unique=True, postgresql_where=sa.text("status = 'running'"))

    op.create_table(
        "capa_docg_audit",
        sa.Column("audit_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("capa_docg_analysis.analysis_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("audit_run_id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("factory_id", UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("doc_type", sa.String(16), nullable=False),
        sa.Column("doc_id", UUID(as_uuid=True), nullable=False),
        sa.Column("doc_name", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version_before", JSONB),
        sa.Column("version_after", JSONB),
        sa.Column("version_bump", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("coverage", JSONB, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("covered_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("audited_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("audited_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("doc_type IN ('control_plan','fmea','sop','inspection_sop','other')", name="chk_docg_audit_doctype"),
        sa.CheckConstraint("status IN ('passed','pending_update','incomplete')", name="chk_docg_audit_status"),
        sa.UniqueConstraint("audit_run_id", "doc_type", "doc_id", name="uq_docg_audit_run_doc"),
        sa.ForeignKeyConstraint(
            ["analysis_id", "factory_id"],
            ["capa_docg_analysis.analysis_id", "capa_docg_analysis.factory_id"],
            ondelete="RESTRICT",
            name="fk_docg_audit_analysis_factory",
        ),
    )

    op.create_table(
        "capa_docg_decision",
        sa.Column("decision_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("capa_docg_analysis.analysis_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("audit_run_id", UUID(as_uuid=True)),
        sa.Column("revision", sa.Integer, nullable=False, server_default="0"),
        sa.Column("factory_id", UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("no_affected_confirmed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("version_snapshot", JSONB, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("defer_reason", sa.Text),
        sa.Column("defer_owner", UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("defer_deadline", sa.Date),
        sa.Column("decided_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("decision IN ('passed','blocked','deferred')", name="chk_docg_decision"),
        sa.CheckConstraint(
            "(decision='deferred' AND defer_reason IS NOT NULL AND defer_owner IS NOT NULL AND defer_deadline IS NOT NULL) "
            "OR (decision IN ('passed','blocked') AND defer_reason IS NULL AND defer_owner IS NULL AND defer_deadline IS NULL)",
            name="chk_docg_decision_defer",
        ),
        sa.UniqueConstraint("analysis_id", "revision", name="uq_docg_decision_analysis_revision"),
        sa.ForeignKeyConstraint(
            ["analysis_id", "factory_id"],
            ["capa_docg_analysis.analysis_id", "capa_docg_analysis.factory_id"],
            ondelete="RESTRICT",
            name="fk_docg_decision_analysis_factory",
        ),
    )


def downgrade() -> None:
    op.drop_table("capa_docg_decision")
    op.drop_table("capa_docg_audit")
    op.drop_index("uq_docg_analysis_running", table_name="capa_docg_analysis")
    op.drop_index("uq_docg_analysis_current", table_name="capa_docg_analysis")
    op.drop_table("capa_docg_analysis")
