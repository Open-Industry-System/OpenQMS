from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CapaLateralDiffusionCheck(Base):
    __tablename__ = "capa_lateral_diffusion_checks"
    __table_args__ = (UniqueConstraint("capa_id", name="uq_lateral_check_capa"),)

    check_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    capa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    source_product_line_code: Mapped[str] = mapped_column(String(20), nullable=False)
    source_product_type_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    similar_products: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # done | empty
    llm_status: Mapped[str] = mapped_column(String(16), nullable=False)  # done | skipped
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CapaLateralNotification(Base):
    __tablename__ = "capa_lateral_notifications"

    notification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    check_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capa_lateral_diffusion_checks.check_id", ondelete="CASCADE"),
        nullable=False,
    )
    capa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="CASCADE"), nullable=False
    )
    product_type_code: Mapped[str] = mapped_column(String(20), nullable=False)
    product_line_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    recipient_label: Mapped[str] = mapped_column(String(120), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # notified | skipped
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # notified | pending | processed
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
