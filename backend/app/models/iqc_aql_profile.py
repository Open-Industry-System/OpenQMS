import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Float, Date, DateTime, ForeignKey, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IqcAqlProfile(Base):
    __tablename__ = "iqc_aql_profiles"

    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iqc_materials.material_id", ondelete="CASCADE"), nullable=False)
    base_aql: Mapped[float] = mapped_column(Float, nullable=False)
    current_aql: Mapped[float] = mapped_column(Float, nullable=False)
    min_aql: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_aql: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inspection_level: Mapped[str] = mapped_column(String(10), nullable=False, default="II")
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    frozen_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    frozen_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    state_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    baseline_inspection_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("iqc_inspections.inspection_id"), nullable=True)
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False)
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
