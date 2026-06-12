import uuid
from datetime import date, datetime

from sqlalchemy import String, ForeignKey, DateTime, func, Date, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CAPAEightD(Base):
    __tablename__ = "capa_eightd"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(20), default="DC-DC-100")
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="D1_TEAM")
    severity: Mapped[str] = mapped_column(String(20), default="一般")
    d1_team: Mapped[dict] = mapped_column(JSONB, default=lambda: [])
    d2_description: Mapped[str | None] = mapped_column(Text)
    d3_interim: Mapped[str | None] = mapped_column(Text)
    d4_root_cause: Mapped[str | None] = mapped_column(Text)
    d5_correction: Mapped[str | None] = mapped_column(Text)
    d6_verification: Mapped[str | None] = mapped_column(Text)
    d7_prevention: Mapped[str | None] = mapped_column(Text)
    d8_closure: Mapped[str | None] = mapped_column(Text)
    fmea_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id")
    )
    fmea_node_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
