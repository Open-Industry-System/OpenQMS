import uuid
from datetime import date, datetime

from sqlalchemy import String, ForeignKey, Date, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditFinding(Base):
    __tablename__ = "audit_findings"

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_plans.audit_id"), nullable=False
    )
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    clause_ref: Mapped[str | None] = mapped_column(String(50), nullable=True)
    finding_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    capa_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capa_eightd.report_id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    customer_confirmed: Mapped[bool] = mapped_column(default=False, nullable=False)
    customer_confirmation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer_confirmation_attachments: Mapped[list] = mapped_column(JSONB, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
