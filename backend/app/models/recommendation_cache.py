import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import text

from app.database import Base


class RecommendationCache(Base):
    __tablename__ = "recommendation_cache"

    # Partial unique indexes backing the ON CONFLICT upserts in
    # recommendation_service._cache_result and lessons_learned.service._cache_result.
    # Declared on the model so Base.metadata.create_all() (used by a few destructive
    # test fixtures) reproduces them — otherwise those tests strip the migration-only
    # indexes and the upsert 500s with InvalidColumnReferenceError.
    __table_args__ = (
        Index(
            "uq_cache_fmea", "fmea_id", "trigger_type", "context_hash",
            unique=True, postgresql_where=text("fmea_id IS NOT NULL"),
        ),
        Index(
            "uq_cache_capa", "report_id", "trigger_type", "context_hash",
            unique=True, postgresql_where=text("report_id IS NOT NULL"),
        ),
        Index(
            "uq_cache_global", "trigger_type", "context_hash",
            unique=True, postgresql_where=text("fmea_id IS NULL AND report_id IS NULL"),
        ),
    )

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
