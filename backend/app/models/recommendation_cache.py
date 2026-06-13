import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RecommendationCache(Base):
    __tablename__ = "recommendation_cache"

    cache_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fmea_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=True
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=True
    )
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False, default="fmea")
    fmea_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    suggestions: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    llm_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
