import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RecommendationCache(Base):
    __tablename__ = "recommendation_cache"
    __table_args__ = (
        UniqueConstraint("fmea_id", "trigger_type", "context_hash", name="uq_recommendation_cache_lookup"),
    )

    cache_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fmea_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False)
    fmea_type: Mapped[str] = mapped_column(String(20), nullable=False)
    suggestions: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(15), nullable=False)
    llm_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
