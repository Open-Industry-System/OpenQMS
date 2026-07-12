"""Create D3 containment 7 tables (US-E2E-01.1 Task 1)

Revision ID: 20260711_d3_containment_tables
Revises: 20260710_verification_check
Create Date: 2026-07-11

Tables:
- capa_d3_import_run (generation root)
- capa_d3_containment_snapshot (imported data)
- capa_d3_impact_report (LLM risk analysis)
- capa_d3_advice_generation (AI recommendations generation)
- capa_d3_ai_advice (individual advice items)
- capa_d3_advice_adoption (engineer decisions)
- capa_d3_execution (containment actions)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "20260711_d3_containment_tables"
down_revision = "20260710_verification_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0. Add unique constraint to capa_eightd for composite FK reference
    # This is required for the composite FK constraint on capa_d3_import_run
    op.create_unique_constraint("uq_capa_factory", "capa_eightd", ["report_id", "factory_id"])

    # 1. capa_d3_import_run
    op.create_table(
        "capa_d3_import_run",
        sa.Column("run_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("capa_id", UUID(as_uuid=True), sa.ForeignKey("capa_eightd.report_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("factory_id", UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("status", sa.String(12), nullable=False, server_default="'importing'"),
        sa.Column("imported_types", JSONB, server_default="[]"),
        sa.Column("analysis_context", JSONB, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("imported_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('importing', 'completed', 'failed')", name="chk_d3_run_status"),
        sa.CheckConstraint(
            "NOT (is_current = true AND (status != 'completed' OR completed_at IS NULL))",
            name="chk_d3_run_current_completed"
        ),
        sa.UniqueConstraint("run_id", "factory_id", name="uq_d3_run_factory"),
        sa.ForeignKeyConstraint(
            ["capa_id", "factory_id"],
            ["capa_eightd.report_id", "capa_eightd.factory_id"],
            ondelete="RESTRICT",
            name="fk_d3_run_capa_factory"
        ),
    )
    op.create_index("uq_d3_run_current", "capa_d3_import_run", ["capa_id"], unique=True, postgresql_where=sa.text("is_current = true"))
    op.create_index("ix_d3_run_factory", "capa_d3_import_run", ["factory_id"])

    # 2. capa_d3_containment_snapshot
    op.create_table(
        "capa_d3_containment_snapshot",
        sa.Column("snapshot_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("capa_d3_import_run.run_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("factory_id", UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot_type", sa.String(20), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("source_query", JSONB),
        sa.Column("record_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("imported_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("snapshot_type IN ('inventory', 'shipment', 'iqc', 'spc')", name="chk_d3_snapshot_type"),
        sa.UniqueConstraint("run_id", "snapshot_type", name="uq_d3_snapshot_run_type"),
        sa.ForeignKeyConstraint(
            ["run_id", "factory_id"],
            ["capa_d3_import_run.run_id", "capa_d3_import_run.factory_id"],
            ondelete="RESTRICT", name="fk_d3_snapshot_run_factory"
        ),
    )
    op.create_index("ix_d3_snapshot_run", "capa_d3_containment_snapshot", ["run_id"])
    op.create_index("ix_d3_snapshot_factory", "capa_d3_containment_snapshot", ["factory_id"])

    # 3. capa_d3_impact_report
    op.create_table(
        "capa_d3_impact_report",
        sa.Column("report_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("capa_d3_import_run.run_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("factory_id", UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("batches", JSONB),
        sa.Column("impact_qty", JSONB),
        sa.Column("customer_impact", JSONB),
        sa.Column("time_window", JSONB),
        sa.Column("risk_level", sa.String(8)),
        sa.Column("risk_floor", sa.String(8)),
        sa.Column("risk_explanation", sa.Text),
        sa.Column("status", sa.String(10), nullable=False, server_default="'running'"),
        sa.Column("attempt_token", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("stage_runs", JSONB),
        sa.Column("prompt_stats", JSONB),
        sa.Column("error", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("llm_available", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("model", sa.String(40)),
        sa.Column("generated_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('running', 'done', 'failed')", name="chk_d3_report_status"),
        sa.CheckConstraint("risk_level IS NULL OR risk_level IN ('high', 'medium', 'low')", name="chk_d3_report_risk_level"),
        sa.CheckConstraint(
            "(status='running' AND is_current=false AND completed_at IS NULL) "
            "OR (status='failed' AND is_current=false AND completed_at IS NOT NULL) "
            "OR (status='done' AND completed_at IS NOT NULL)",
            name="chk_d3_report_status_current"
        ),
        sa.CheckConstraint(
            "status != 'done' OR (batches IS NOT NULL AND impact_qty IS NOT NULL AND customer_impact IS NOT NULL "
            "AND time_window IS NOT NULL AND risk_level IS NOT NULL AND risk_floor IS NOT NULL "
            "AND NULLIF(btrim(risk_explanation), '') IS NOT NULL AND llm_available = true AND completed_at IS NOT NULL)",
            name="chk_d3_report_done_complete"
        ),
        sa.UniqueConstraint("report_id", "factory_id", name="uq_d3_report_factory"),
        sa.ForeignKeyConstraint(
            ["run_id", "factory_id"],
            ["capa_d3_import_run.run_id", "capa_d3_import_run.factory_id"],
            ondelete="RESTRICT", name="fk_d3_report_run_factory"
        ),
    )
    op.create_index("uq_d3_report_current", "capa_d3_impact_report", ["run_id"], unique=True, postgresql_where=sa.text("is_current = true"))
    op.create_index("uq_d3_report_running", "capa_d3_impact_report", ["run_id"], unique=True, postgresql_where=sa.text("status = 'running'"))
    op.create_index("ix_d3_report_factory", "capa_d3_impact_report", ["factory_id"])

    # 4. capa_d3_advice_generation
    op.create_table(
        "capa_d3_advice_generation",
        sa.Column("generation_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_id", UUID(as_uuid=True), sa.ForeignKey("capa_d3_impact_report.report_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("factory_id", UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("advice_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rejected_advice_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("stage_runs", JSONB, nullable=False, server_default="[]"),
        sa.Column("llm_available", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("model", sa.String(40)),
        sa.Column("status", sa.String(10), nullable=False, server_default="'running'"),
        sa.Column("attempt_token", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("error", sa.Text),
        sa.Column("generated_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('running', 'done', 'failed')", name="chk_d3_gen_status"),
        sa.CheckConstraint(
            "(status='running' AND is_current=false AND completed_at IS NULL) "
            "OR (status='failed' AND is_current=false AND completed_at IS NOT NULL) "
            "OR (status='done' AND completed_at IS NOT NULL)",
            name="chk_d3_gen_status_current"
        ),
        sa.CheckConstraint("status != 'done' OR advice_count > 0", name="chk_d3_gen_done_has_advice"),
        sa.CheckConstraint("status != 'done' OR llm_available = true", name="chk_d3_gen_done_has_llm"),
        sa.UniqueConstraint("generation_id", "factory_id", name="uq_d3_gen_factory"),
        # Unique constraint for composite FK target (execution references this 3-tuple)
        sa.UniqueConstraint("generation_id", "report_id", "factory_id", name="uq_d3_generation_report"),
        sa.ForeignKeyConstraint(
            ["report_id", "factory_id"],
            ["capa_d3_impact_report.report_id", "capa_d3_impact_report.factory_id"],
            ondelete="RESTRICT", name="fk_d3_gen_report_factory"
        ),
    )
    op.create_index("uq_d3_gen_current", "capa_d3_advice_generation", ["report_id"], unique=True, postgresql_where=sa.text("is_current = true"))
    op.create_index("uq_d3_gen_running", "capa_d3_advice_generation", ["report_id"], unique=True, postgresql_where=sa.text("status = 'running'"))
    op.create_index("ix_d3_gen_factory", "capa_d3_advice_generation", ["factory_id"])

    # 5. capa_d3_ai_advice
    op.create_table(
        "capa_d3_ai_advice",
        sa.Column("advice_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("generation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("factory_id", UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("advice_type", sa.String(24), nullable=False),
        sa.Column("advice_text", sa.Text, nullable=False),
        sa.Column("source_provenance", JSONB, nullable=False),
        sa.Column("target_batch_refs", JSONB),
        sa.Column("stage_runs", JSONB),
        sa.Column("llm_available", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("model", sa.String(40)),
        sa.Column("generated_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("advice_type IN ('recall', 'isolate', 'notify_customer', 'strict_inspection', 'alternative')", name="chk_d3_advice_type"),
        sa.UniqueConstraint("advice_id", "factory_id", name="uq_d3_advice_factory"),
        sa.UniqueConstraint("advice_id", "generation_id", "factory_id", name="uq_d3_advice_gen_factory"),
        sa.ForeignKeyConstraint(
            ["generation_id", "factory_id"],
            ["capa_d3_advice_generation.generation_id", "capa_d3_advice_generation.factory_id"],
            ondelete="RESTRICT", name="fk_d3_advice_gen_factory"
        ),
    )
    op.create_index("ix_d3_advice_gen", "capa_d3_ai_advice", ["generation_id"])
    op.create_index("ix_d3_advice_factory", "capa_d3_ai_advice", ["factory_id"])

    # 6. capa_d3_advice_adoption
    op.create_table(
        "capa_d3_advice_adoption",
        sa.Column("adoption_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("advice_id", UUID(as_uuid=True), nullable=False),
        sa.Column("factory_id", UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decision", sa.String(8), nullable=False),
        sa.Column("adopted_text", sa.Text),
        sa.Column("advice_type", sa.String(24)),
        sa.Column("source_provenance", JSONB),
        sa.Column("decided_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("decision IN ('adopted', 'rejected')", name="chk_d3_adoption_decision"),
        sa.CheckConstraint(
            "(decision='adopted' AND adopted_text IS NOT NULL) OR (decision='rejected' AND adopted_text IS NULL)",
            name="chk_d3_adoption_decision_text"
        ),
        sa.UniqueConstraint("advice_id", name="uq_d3_adoption_advice"),
        sa.ForeignKeyConstraint(
            ["advice_id", "factory_id"],
            ["capa_d3_ai_advice.advice_id", "capa_d3_ai_advice.factory_id"],
            ondelete="RESTRICT", name="fk_d3_adoption_advice_factory"
        ),
    )

    # 7. capa_d3_execution
    op.create_table(
        "capa_d3_execution",
        sa.Column("execution_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_id", UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", UUID(as_uuid=True)),
        sa.Column("factory_id", UUID(as_uuid=True), sa.ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("advice_id", UUID(as_uuid=True)),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("measure_text", sa.Text, nullable=False),
        sa.Column("result_status", sa.String(16), nullable=False, server_default="'in_progress'"),
        sa.Column("evidence_refs", JSONB, server_default="[]"),
        sa.Column("executed_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("source IN ('manual', 'adopted')", name="chk_d3_exec_source"),
        sa.CheckConstraint("result_status IN ('completed', 'in_progress', 'pending', 'failed')", name="chk_d3_exec_result_status"),
        sa.CheckConstraint(
            "(source = 'manual' AND generation_id IS NULL AND advice_id IS NULL) "
            "OR (source = 'adopted' AND generation_id IS NOT NULL AND advice_id IS NOT NULL)",
            name="chk_d3_exec_source_keys"
        ),
        sa.UniqueConstraint("execution_id", "factory_id", name="uq_d3_exec_factory"),
        sa.ForeignKeyConstraint(
            ["report_id", "factory_id"],
            ["capa_d3_impact_report.report_id", "capa_d3_impact_report.factory_id"],
            ondelete="RESTRICT", name="fk_d3_exec_report_factory"
        ),
        # Composite FK: (generation_id, report_id, factory_id) references advice_generation
        # MATCH SIMPLE: only enforced when all 3 columns non-null (manual execution has generation_id=NULL)
        sa.ForeignKeyConstraint(
            ["generation_id", "report_id", "factory_id"],
            ["capa_d3_advice_generation.generation_id", "capa_d3_advice_generation.report_id", "capa_d3_advice_generation.factory_id"],
            ondelete="RESTRICT", name="fk_d3_exec_gen_report_factory"
        ),
        # Composite FK: (advice_id, generation_id, factory_id) references ai_advice
        # MATCH SIMPLE: only enforced when all 3 columns non-null (manual execution has advice_id=NULL)
        sa.ForeignKeyConstraint(
            ["advice_id", "generation_id", "factory_id"],
            ["capa_d3_ai_advice.advice_id", "capa_d3_ai_advice.generation_id", "capa_d3_ai_advice.factory_id"],
            ondelete="RESTRICT", name="fk_d3_exec_advice_gen_factory"
        ),
    )
    op.create_index("ix_d3_exec_report", "capa_d3_execution", ["report_id"])
    op.create_index("ix_d3_exec_gen", "capa_d3_execution", ["generation_id"])
    op.create_index("ix_d3_exec_factory", "capa_d3_execution", ["factory_id"])


def downgrade() -> None:
    op.drop_table("capa_d3_execution")
    op.drop_table("capa_d3_advice_adoption")
    op.drop_table("capa_d3_ai_advice")
    op.drop_table("capa_d3_advice_generation")
    op.drop_table("capa_d3_impact_report")
    op.drop_table("capa_d3_containment_snapshot")
    op.drop_table("capa_d3_import_run")
    op.drop_constraint("uq_capa_factory", "capa_eightd", type_="unique")
