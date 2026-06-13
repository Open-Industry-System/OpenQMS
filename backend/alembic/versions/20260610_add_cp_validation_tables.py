"""Add cp validation tables.

Revision ID: 20260610_add_cp_validation
Revises: 032_lessons_learned_cache
Create Date: 2026-06-10
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260610_add_cp_validation"
down_revision: Union[str, None] = "032_lessons_learned_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cp_validation_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("rule_count", sa.Integer, server_default="0"),
        sa.Column("error_count", sa.Integer, server_default="0"),
        sa.Column("warning_count", sa.Integer, server_default="0"),
        sa.Column("info_count", sa.Integer, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_rules", postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_cpvrn_status"),
        sa.CheckConstraint("trigger IN ('manual', 'auto_on_save', 'fmea_change')", name="ck_cpvrn_trigger"),
    )
    op.create_index("idx_cpvrn_cp_id", "cp_validation_runs", ["cp_id"])
    op.create_index("idx_cpvrn_status", "cp_validation_runs", ["status"])
    op.create_index(
        "idx_cpvrn_running", "cp_validation_runs", ["cp_id"],
        unique=True, postgresql_where=sa.text("status = 'running'")
    )

    op.create_table(
        "cp_validation_findings",
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_hash", sa.String(64), nullable=False),
        sa.Column("rule_id", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('open', 'accepted', 'rejected', 'resolved')", name="ck_cvf_status"),
        sa.CheckConstraint("severity IN ('error', 'warning', 'info')", name="ck_cvf_severity"),
        sa.CheckConstraint("category IN ('coverage', 'consistency', 'completeness', 'risk', 'optimization')", name="ck_cvf_category"),
    )
    op.create_index("idx_cvf_cp_id", "cp_validation_findings", ["cp_id"])
    op.create_index("idx_cvf_status", "cp_validation_findings", ["status"])
    op.create_index(
        "idx_cvf_hash", "cp_validation_findings", ["cp_id", "finding_hash"], unique=True
    )

    op.create_table(
        "cp_validation_occurrences",
        sa.Column("occurrence_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cp_validation_runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cp_validation_findings.finding_id", ondelete="CASCADE"), nullable=False),
        sa.Column("cp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False),
        sa.Column("validation_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("affected_items", postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("fmea_node_ids", postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("suggestion", sa.Text, nullable=True),
        sa.Column("suggestion_data", postgresql.JSONB, nullable=True),
        sa.Column("present", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("validation_type IN ('rule', 'llm', 'recommendation')", name="ck_cvo_validation_type"),
    )
    op.create_index("idx_cvo_run_id", "cp_validation_occurrences", ["run_id"])
    op.create_index("idx_cvo_finding_id", "cp_validation_occurrences", ["finding_id"])
    op.create_index("idx_cvo_cp_id", "cp_validation_occurrences", ["cp_id"])
    op.create_index(
        "idx_cvo_run_finding", "cp_validation_occurrences", ["run_id", "finding_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("idx_cvo_run_finding", table_name="cp_validation_occurrences")
    op.drop_index("idx_cvo_cp_id", table_name="cp_validation_occurrences")
    op.drop_index("idx_cvo_finding_id", table_name="cp_validation_occurrences")
    op.drop_index("idx_cvo_run_id", table_name="cp_validation_occurrences")
    op.drop_table("cp_validation_occurrences")

    op.drop_index("idx_cvf_hash", table_name="cp_validation_findings")
    op.drop_index("idx_cvf_status", table_name="cp_validation_findings")
    op.drop_index("idx_cvf_cp_id", table_name="cp_validation_findings")
    op.drop_table("cp_validation_findings")

    op.drop_index("idx_cpvrn_running", table_name="cp_validation_runs")
    op.drop_index("idx_cpvrn_status", table_name="cp_validation_runs")
    op.drop_index("idx_cpvrn_cp_id", table_name="cp_validation_runs")
    op.drop_table("cp_validation_runs")
