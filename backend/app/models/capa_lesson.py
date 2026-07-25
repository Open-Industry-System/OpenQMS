import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CapaLessonLearned(Base):
    __tablename__ = "capa_lessons_learned"
    lesson_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    capa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capa_eightd.report_id", ondelete="CASCADE"),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("factories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False)
    lesson_text: Mapped[str] = mapped_column(Text, nullable=False)
    lesson_text_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    source_d_step: Mapped[str] = mapped_column(String(8), nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, default=lambda: [])
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
