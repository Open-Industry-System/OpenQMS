import uuid
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ControlPlanVersion(Base):
    __tablename__ = "control_plan_versions"

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("control_plans.cp_id", ondelete="CASCADE"),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    major_no: Mapped[int] = mapped_column(Integer, nullable=False)
    minor_no: Mapped[int] = mapped_column(Integer, nullable=False)
    header_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    items_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_fmea_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fmea_versions.version_id", ondelete="SET NULL"),
        nullable=True,
    )
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    creator = relationship("User", foreign_keys=[created_by])
    source_fmea_version = relationship("FMEAVersion", foreign_keys=[source_fmea_version_id])
