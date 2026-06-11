import uuid
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ChangeImpactAnalysis(Base):
    __tablename__ = "change_impact_analysis"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fmea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=False
    )
    product_line_code: Mapped[str] = mapped_column(String, nullable=False)
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    node_id: Mapped[str] = mapped_column(String, nullable=False)
    node_type: Mapped[str] = mapped_column(String, nullable=False)
    node_name: Mapped[str] = mapped_column(String, nullable=False)
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    field_name: Mapped[str | None] = mapped_column(String, nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String, nullable=False, default="single_fmea")
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    impact_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    impact_result: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    fmea = relationship("FMEADocument", foreign_keys=[fmea_id])
    creator = relationship("User", foreign_keys=[created_by])
