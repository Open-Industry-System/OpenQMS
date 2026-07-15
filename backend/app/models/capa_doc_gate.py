"""D8 doc update gate ORM models (US-E2E-01.7). 3 tables mirroring D3 pattern."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Index

from app.database import Base


class CapaDocgAnalysis(Base):
    __tablename__ = "capa_docg_analysis"
    __table_args__ = (
        # NOTE: full UNIQUE(capa_id, factory_id) removed (终审第七轮 P0#1) — it blocked
        # retry/regeneration. Concurrency is guarded by partial-UQs below (is_current / running).
        UniqueConstraint("analysis_id", "factory_id", name="uq_docg_analysis_factory"),
        CheckConstraint("status IN ('running','done','failed')", name="chk_docg_analysis_status"),
        CheckConstraint(
            "(status='running' AND is_current=false AND completed_at IS NULL) "
            "OR (status='failed' AND is_current=false AND completed_at IS NOT NULL) "
            "OR (status='done' AND completed_at IS NOT NULL)",
            name="chk_docg_analysis_status_state",
        ),
        CheckConstraint(
            "status!='done' OR (affected_docs IS NOT NULL AND analysis_input_hash IS NOT NULL "
            "AND llm_available=true AND completed_at IS NOT NULL)",
            name="chk_docg_analysis_done_complete",
        ),
        Index("uq_docg_analysis_current", "capa_id", unique=True, postgresql_where=text("is_current = true")),
        Index("uq_docg_analysis_running", "capa_id", unique=True, postgresql_where=text("status = 'running'")),
        ForeignKeyConstraint(
            ["capa_id", "factory_id"],
            ["capa_eightd.report_id", "capa_eightd.factory_id"],
            ondelete="RESTRICT",
            name="fk_docg_analysis_capa_factory",
        ),
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="RESTRICT"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="running")
    affected_docs: Mapped[list | None] = mapped_column(JSONB)
    analysis_input_hash: Mapped[str | None] = mapped_column(String(64))
    llm_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model: Mapped[str | None] = mapped_column(String(40))
    prompt_stats: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    attempt_token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CapaDocgAudit(Base):
    __tablename__ = "capa_docg_audit"
    __table_args__ = (
        CheckConstraint("doc_type IN ('control_plan','fmea','sop','inspection_sop','other')", name="chk_docg_audit_doctype"),
        CheckConstraint("status IN ('passed','pending_update','incomplete')", name="chk_docg_audit_status"),
        UniqueConstraint("audit_run_id", "doc_type", "doc_id", name="uq_docg_audit_run_doc"),
        ForeignKeyConstraint(
            ["analysis_id", "factory_id"],
            ["capa_docg_analysis.analysis_id", "capa_docg_analysis.factory_id"],
            ondelete="RESTRICT",
            name="fk_docg_audit_analysis_factory",
        ),
    )
    audit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_docg_analysis.analysis_id", ondelete="RESTRICT"), nullable=False)
    audit_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False)
    doc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    doc_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    version_before: Mapped[dict | None] = mapped_column(JSONB)
    version_after: Mapped[dict | None] = mapped_column(JSONB)
    version_bump: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    coverage: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    covered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audited_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    audited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CapaDocgDecision(Base):
    __tablename__ = "capa_docg_decision"
    __table_args__ = (
        CheckConstraint("decision IN ('passed','blocked','deferred')", name="chk_docg_decision"),
        CheckConstraint(
            "(decision='deferred' AND defer_reason IS NOT NULL AND defer_owner IS NOT NULL AND defer_deadline IS NOT NULL) "
            "OR (decision IN ('passed','blocked') AND defer_reason IS NULL AND defer_owner IS NULL AND defer_deadline IS NULL)",
            name="chk_docg_decision_defer",
        ),
        CheckConstraint(
            "waiver_reason IS NULL OR (decision='passed' AND no_affected_confirmed=false)",
            name="chk_docg_waiver_only_passed",
        ),
        CheckConstraint(
            "waiver_reason IS NULL OR ("
            "waiver_items IS NOT NULL AND jsonb_typeof(waiver_items)='array' "
            "AND jsonb_array_length(waiver_items) > 0)",
            name="chk_docg_waiver_items",
        ),
        UniqueConstraint("analysis_id", "revision", name="uq_docg_decision_analysis_revision"),
        ForeignKeyConstraint(
            ["analysis_id", "factory_id"],
            ["capa_docg_analysis.analysis_id", "capa_docg_analysis.factory_id"],
            ondelete="RESTRICT",
            name="fk_docg_decision_analysis_factory",
        ),
    )
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_docg_analysis.analysis_id", ondelete="RESTRICT"), nullable=False)
    audit_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    no_affected_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    defer_reason: Mapped[str | None] = mapped_column(Text)
    defer_owner: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    defer_deadline: Mapped[date | None] = mapped_column(Date)
    waiver_reason: Mapped[str | None] = mapped_column(Text)
    waiver_items: Mapped[list | None] = mapped_column(JSONB)
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
