"""D3 Containment ORM models (US-E2E-01.1).

7 tables for D3 containment workflow:
- Import run (generation root)
- Containment snapshot (4 data sources)
- Impact report (LLM-enhanced risk analysis)
- Advice generation (AI recommendations)
- AI advice (individual recommendation)
- Advice adoption (engineer decision)
- Execution record (containment action)

Key constraints:
- All tables: factory_id NOT NULL + composite FK for parent-child consistency
- Immutable generation pattern: run→report→advice_generation→advice
- Partial unique indexes for is_current + status='running'
- Comprehensive CHECK constraints for state integrity
- attempt_token CAS (Compare-And-Swap) for atomic transitions
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Index

from app.database import Base


class CapaD3ImportRun(Base):
    """Import generation root - contains analysis context for deterministic reports."""

    __tablename__ = "capa_d3_import_run"
    __table_args__ = (
        # Partial UQ: at most one current run per CAPA
        Index(
            "uq_d3_run_current",
            "capa_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
        # CHECK: is_current=true requires completed state
        CheckConstraint(
            "NOT (is_current = true AND (status != 'completed' OR completed_at IS NULL))",
            name="chk_d3_run_current_completed",
        ),
        # CHECK: status enum
        CheckConstraint(
            "status IN ('importing', 'completed', 'failed')",
            name="chk_d3_run_status",
        ),
        # Unique constraint for composite FK child tables
        UniqueConstraint("run_id", "factory_id", name="uq_d3_run_factory"),
        # Composite FK: (capa_id, factory_id) references capa_eightd
        ForeignKeyConstraint(
            ["capa_id", "factory_id"],
            ["capa_eightd.report_id", "capa_eightd.factory_id"],
            ondelete="RESTRICT",
            name="fk_d3_run_capa_factory",
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    capa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capa_eightd.report_id", ondelete="RESTRICT"),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("factories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="importing"
    )
    imported_types: Mapped[list] = mapped_column(JSONB, default=list)
    analysis_context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CapaD3ContainmentSnapshot(Base):
    """Import snapshot - raw data from 4 sources (inventory/shipment/iqc/spc)."""

    __tablename__ = "capa_d3_containment_snapshot"
    __table_args__ = (
        # CHECK: snapshot_type enum
        CheckConstraint(
            "snapshot_type IN ('inventory', 'shipment', 'iqc', 'spc')",
            name="chk_d3_snapshot_type",
        ),
        # UQ: one snapshot per type per run
        UniqueConstraint("run_id", "snapshot_type", name="uq_d3_snapshot_run_type"),
        # Composite FK: (run_id, factory_id) references import_run
        ForeignKeyConstraint(
            ["run_id", "factory_id"],
            ["capa_d3_import_run.run_id", "capa_d3_import_run.factory_id"],
            ondelete="RESTRICT",
            name="fk_d3_snapshot_run_factory",
        ),
        Index("ix_d3_snapshot_run_id", "run_id"),
        Index("ix_d3_snapshot_factory_id", "factory_id"),
    )

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capa_d3_import_run.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("factories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_type: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[list] = mapped_column(JSONB, nullable=False)
    source_query: Mapped[dict | None] = mapped_column(JSONB)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CapaD3ImpactReport(Base):
    """Impact report - deterministic analysis + LLM risk assessment."""

    __tablename__ = "capa_d3_impact_report"
    __table_args__ = (
        # CHECK: status enum
        CheckConstraint("status IN ('running', 'done', 'failed')", name="chk_d3_report_status"),
        # Partial UQ: at most one current report per run
        Index(
            "uq_d3_report_current",
            "run_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
        # Partial UQ: at most one running report per run
        Index(
            "uq_d3_report_running",
            "run_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        # CHECK: state machine constraints
        CheckConstraint(
            """
            (status = 'running' AND is_current = false AND completed_at IS NULL)
            OR (status = 'failed' AND is_current = false AND completed_at IS NOT NULL)
            OR (status = 'done' AND completed_at IS NOT NULL)
            """,
            name="chk_d3_report_status_state",
        ),
        # CHECK: done requires all results + LLM
        CheckConstraint(
            """
            status != 'done' OR (
                batches IS NOT NULL
                AND impact_qty IS NOT NULL
                AND customer_impact IS NOT NULL
                AND time_window IS NOT NULL
                AND risk_level IS NOT NULL
                AND risk_floor IS NOT NULL
                AND NULLIF(btrim(risk_explanation), '') IS NOT NULL
                AND llm_available = true
                AND completed_at IS NOT NULL
            )
            """,
            name="chk_d3_report_done_complete",
        ),
        # CHECK: risk_level/risk_floor enum
        CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('high', 'medium', 'low')",
            name="chk_d3_report_risk_level",
        ),
        CheckConstraint(
            "risk_floor IS NULL OR risk_floor IN ('high', 'medium', 'low')",
            name="chk_d3_report_risk_floor",
        ),
        # Unique constraint for composite FK
        UniqueConstraint("report_id", "factory_id", name="uq_d3_report_factory"),
        # Composite FK: (run_id, factory_id) references import_run
        ForeignKeyConstraint(
            ["run_id", "factory_id"],
            ["capa_d3_import_run.run_id", "capa_d3_import_run.factory_id"],
            ondelete="RESTRICT",
            name="fk_d3_report_run_factory",
        ),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capa_d3_import_run.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("factories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    batches: Mapped[list | None] = mapped_column(JSONB)
    impact_qty: Mapped[dict | None] = mapped_column(JSONB)
    customer_impact: Mapped[list | None] = mapped_column(JSONB)
    time_window: Mapped[dict | None] = mapped_column(JSONB)
    risk_level: Mapped[str | None] = mapped_column(String(8))
    risk_floor: Mapped[str | None] = mapped_column(String(8))
    risk_explanation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="running")
    attempt_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    stage_runs: Mapped[list | None] = mapped_column(JSONB)
    prompt_stats: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    llm_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    model: Mapped[str | None] = mapped_column(String(40))
    generated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CapaD3AdviceGeneration(Base):
    """Advice generation - container for AI recommendations."""

    __tablename__ = "capa_d3_advice_generation"
    __table_args__ = (
        # CHECK: status enum
        CheckConstraint("status IN ('running', 'done', 'failed')", name="chk_d3_gen_status"),
        # Partial UQ: at most one current generation per report
        Index(
            "uq_d3_generation_current",
            "report_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
        # Partial UQ: at most one running generation per report
        Index(
            "uq_d3_generation_running",
            "report_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
        # CHECK: state machine constraints
        CheckConstraint(
            """
            (status = 'running' AND is_current = false AND completed_at IS NULL)
            OR (status = 'failed' AND is_current = false AND completed_at IS NOT NULL)
            OR (status = 'done' AND completed_at IS NOT NULL)
            """,
            name="chk_d3_generation_status_state",
        ),
        # CHECK: done requires advice_count > 0
        CheckConstraint(
            "status != 'done' OR advice_count > 0",
            name="chk_d3_generation_done_has_advice",
        ),
        # CHECK: done requires LLM
        CheckConstraint(
            "status != 'done' OR llm_available = true",
            name="chk_d3_generation_done_llm",
        ),
        # Unique constraint for composite FK
        UniqueConstraint(
            "generation_id", "report_id", "factory_id", name="uq_d3_generation_report"
        ),
        # Composite FK: (report_id, factory_id) references impact_report
        ForeignKeyConstraint(
            ["report_id", "factory_id"],
            ["capa_d3_impact_report.report_id", "capa_d3_impact_report.factory_id"],
            ondelete="RESTRICT",
            name="fk_d3_gen_report_factory",
        ),
    )

    generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capa_d3_impact_report.report_id", ondelete="RESTRICT"),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("factories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    advice_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_advice_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    stage_runs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    llm_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    model: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="running")
    attempt_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    error: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CapaD3AiAdvice(Base):
    """AI advice - individual containment recommendation."""

    __tablename__ = "capa_d3_ai_advice"
    __table_args__ = (
        # CHECK: advice_type enum
        CheckConstraint(
            "advice_type IN ('recall', 'isolate', 'notify_customer', 'strict_inspection', 'alternative')",
            name="chk_d3_advice_type",
        ),
        # Unique constraint for composite FK (execution uses this)
        UniqueConstraint(
            "advice_id", "generation_id", "factory_id", name="uq_d3_advice_generation"
        ),
        # Composite FK: (generation_id, factory_id) references advice_generation
        ForeignKeyConstraint(
            ["generation_id", "factory_id"],
            ["capa_d3_advice_generation.generation_id", "capa_d3_advice_generation.factory_id"],
            ondelete="RESTRICT",
            name="fk_d3_advice_gen_factory",
        ),
        Index("ix_d3_advice_generation_id", "generation_id"),
        Index("ix_d3_advice_factory_id", "factory_id"),
    )

    advice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "capa_d3_advice_generation.generation_id", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("factories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    advice_type: Mapped[str] = mapped_column(String(24), nullable=False)
    advice_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_provenance: Mapped[list] = mapped_column(JSONB, nullable=False)
    target_batch_refs: Mapped[list | None] = mapped_column(JSONB)
    stage_runs: Mapped[list | None] = mapped_column(JSONB)
    llm_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    model: Mapped[str | None] = mapped_column(String(40))
    generated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CapaD3AdviceAdoption(Base):
    """Advice adoption - engineer's decision to adopt or reject."""

    __tablename__ = "capa_d3_advice_adoption"
    __table_args__ = (
        # CHECK: decision enum
        CheckConstraint("decision IN ('adopted', 'rejected')", name="chk_d3_adoption_decision"),
        # CHECK: adopted requires text, rejected requires NULL
        CheckConstraint(
            "(decision = 'adopted' AND adopted_text IS NOT NULL) "
            "OR (decision = 'rejected' AND adopted_text IS NULL)",
            name="chk_d3_adoption_decision_text",
        ),
        # CHECK: advice_type enum (redundant from advice, but validate)
        CheckConstraint(
            "advice_type IN ('recall', 'isolate', 'notify_customer', 'strict_inspection', 'alternative')",
            name="chk_d3_adoption_advice_type",
        ),
        # UQ: single decision per advice
        UniqueConstraint("advice_id", name="uq_d3_adoption_advice"),
        # Composite FK: (advice_id, factory_id) references advice
        ForeignKeyConstraint(
            ["advice_id", "factory_id"],
            ["capa_d3_ai_advice.advice_id", "capa_d3_ai_advice.factory_id"],
            ondelete="RESTRICT",
            name="fk_d3_adoption_advice_factory",
        ),
    )

    adoption_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    advice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capa_d3_ai_advice.advice_id", ondelete="RESTRICT"),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("factories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    adopted_text: Mapped[str | None] = mapped_column(Text)
    advice_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_provenance: Mapped[list] = mapped_column(JSONB, nullable=False)
    decided_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CapaD3Execution(Base):
    """Execution record - containment action taken."""

    __tablename__ = "capa_d3_execution"
    __table_args__ = (
        # CHECK: source enum
        CheckConstraint("source IN ('manual', 'adopted')", name="chk_d3_exec_source"),
        # CHECK: result_status enum
        CheckConstraint(
            "result_status IN ('completed', 'in_progress', 'pending', 'failed')",
            name="chk_d3_exec_result_status",
        ),
        # CHECK: manual vs adopted
        CheckConstraint(
            "(source = 'manual' AND generation_id IS NULL AND advice_id IS NULL) "
            "OR (source = 'adopted' AND generation_id IS NOT NULL AND advice_id IS NOT NULL)",
            name="chk_d3_execution_source",
        ),
        # Composite FK: (report_id, factory_id) references impact_report
        ForeignKeyConstraint(
            ["report_id", "factory_id"],
            ["capa_d3_impact_report.report_id", "capa_d3_impact_report.factory_id"],
            ondelete="RESTRICT",
            name="fk_d3_exec_report_factory",
        ),
        # Composite FK: (generation_id, report_id, factory_id) references advice_generation
        # Note: nullable columns, MATCH SIMPLE (only enforced when all columns non-null)
        ForeignKeyConstraint(
            ["generation_id", "report_id", "factory_id"],
            ["capa_d3_advice_generation.generation_id", "capa_d3_advice_generation.report_id", "capa_d3_advice_generation.factory_id"],
            ondelete="RESTRICT",
            name="fk_d3_exec_gen_report_factory",
        ),
        # Composite FK: (advice_id, generation_id, factory_id) references advice (v7 F3)
        ForeignKeyConstraint(
            ["advice_id", "generation_id", "factory_id"],
            ["capa_d3_ai_advice.advice_id", "capa_d3_ai_advice.generation_id", "capa_d3_ai_advice.factory_id"],
            ondelete="RESTRICT",
            name="fk_d3_exec_advice_gen_factory",
        ),
        Index("ix_d3_exec_report_id", "report_id"),
        Index("ix_d3_exec_generation_id", "generation_id"),
        Index("ix_d3_exec_factory_id", "factory_id"),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capa_d3_impact_report.report_id", ondelete="RESTRICT"),
        nullable=False,
    )
    generation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "capa_d3_advice_generation.generation_id", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("factories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    advice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capa_d3_ai_advice.advice_id", ondelete="RESTRICT"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    measure_text: Mapped[str] = mapped_column(Text, nullable=False)
    result_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="in_progress"
    )
    evidence_refs: Mapped[list] = mapped_column(JSONB, default=list)
    executed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )