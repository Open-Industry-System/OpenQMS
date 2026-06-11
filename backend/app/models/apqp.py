import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class APQPProject(Base):
    __tablename__ = "apqp_projects"
    __table_args__ = (
        UniqueConstraint("project_code", name="uq_apqp_projects_project_code"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_code: Mapped[str] = mapped_column(String(30), nullable=False)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_line_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("product_lines.code"), nullable=False
    )
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_sop_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    team_members: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Phase management
    current_phase: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    phase_status: Mapped[str | None] = mapped_column(String(20), default="in_progress", nullable=True)
    project_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    # Phase completion timestamps
    phase_1_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_2_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_3_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_4_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_5_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Gate info (latest approval)
    gate_approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    gate_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gate_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate_history: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Cross-module links
    dfmea_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id", ondelete="SET NULL"), nullable=True
    )
    pfmea_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id", ondelete="SET NULL"), nullable=True
    )
    control_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_plans.cp_id", ondelete="SET NULL"), nullable=True
    )
    ppap_submission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_ppap_submissions.submission_id", ondelete="SET NULL"), nullable=True
    )

    # Audit
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    gate_approver = relationship("User", foreign_keys=[gate_approved_by])
    dfmea = relationship("FMEADocument", foreign_keys=[dfmea_id])
    pfmea = relationship("FMEADocument", foreign_keys=[pfmea_id])
    control_plan = relationship("ControlPlan", foreign_keys=[control_plan_id])
    ppap_submission = relationship("SupplierPPAPSubmission", foreign_keys=[ppap_submission_id])
    product_line = relationship("ProductLine", foreign_keys=[product_line_code])
