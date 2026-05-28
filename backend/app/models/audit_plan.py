import uuid
from datetime import date, datetime

from sqlalchemy import String, ForeignKey, Date, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditPlan(Base):
    __tablename__ = "audit_plans"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    program_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_programs.program_id"), nullable=False
    )
    audit_scope: Mapped[str] = mapped_column(Text, nullable=False)
    audit_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    planned_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lead_auditor: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    team_members: Mapped[list] = mapped_column(JSONB, default=list)
    checklist: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    product_line_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    audit_category: Mapped[str] = mapped_column(String(20), default="internal", nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    audit_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    customer_confirmation_doc: Mapped[list] = mapped_column(JSONB, default=list)
