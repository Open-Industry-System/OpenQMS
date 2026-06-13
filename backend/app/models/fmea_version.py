import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FMEAVersion(Base):
    __tablename__ = "fmea_versions"

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fmea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    major_no: Mapped[int] = mapped_column(Integer, nullable=False)
    minor_no: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    creator = relationship("User", foreign_keys=[created_by])
