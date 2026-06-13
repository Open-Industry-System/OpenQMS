import uuid
import hashlib
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text, Boolean, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CPValidationRun(Base):
    __tablename__ = "cp_validation_runs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_cpvrn_status",
        ),
        CheckConstraint(
            "trigger IN ('manual', 'auto_on_save', 'fmea_change')",
            name="ck_cpvrn_trigger",
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False
    )
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running")
    rule_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    info_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_rules: Mapped[list | None] = mapped_column(JSONB, default=list)
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )


class CPValidationFinding(Base):
    __tablename__ = "cp_validation_findings"

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'accepted', 'rejected', 'resolved')",
            name="ck_cvf_status",
        ),
        CheckConstraint(
            "severity IN ('error', 'warning', 'info')",
            name="ck_cvf_severity",
        ),
        CheckConstraint(
            "category IN ('coverage', 'consistency', 'completeness', 'risk', 'optimization')",
            name="ck_cvf_category",
        ),
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    finding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CPValidationOccurrence(Base):
    __tablename__ = "cp_validation_occurrences"

    __table_args__ = (
        CheckConstraint(
            "validation_type IN ('rule', 'llm', 'recommendation')",
            name="ck_cvo_validation_type",
        ),
    )

    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cp_validation_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cp_validation_findings.finding_id", ondelete="CASCADE"), nullable=False
    )
    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False
    )
    validation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_items: Mapped[list | None] = mapped_column(JSONB, default=list)
    fmea_node_ids: Mapped[list | None] = mapped_column(JSONB, default=list)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestion_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def compute_finding_hash(rule_id: str, stable_key: str, key_content: str) -> str:
    """Generate SHA256 hash using stable business keys (NOT volatile item UUIDs).

    stable_key: fmea_node_id|characteristic if available, else step_no|characteristic.
    This ensures the same business issue survives item UUID regeneration on CP save,
    and distinguishes different CP items that share the same FMEA ProcessStep.
    """
    payload = f"{rule_id}|{stable_key}|{key_content}"
    return hashlib.sha256(payload.encode()).hexdigest()
