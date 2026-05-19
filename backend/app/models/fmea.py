import uuid
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FMEADocument(Base):
    __tablename__ = "fmea_documents"

    fmea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    fmea_type: Mapped[str] = mapped_column(String(20), default="PFMEA")
    product_line_code: Mapped[str] = mapped_column(String(20), default="DC-DC-100")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    graph_data: Mapped[dict] = mapped_column(JSONB, default=lambda: {"nodes": [], "edges": []})
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    approver = relationship("User", foreign_keys=[approved_by])
