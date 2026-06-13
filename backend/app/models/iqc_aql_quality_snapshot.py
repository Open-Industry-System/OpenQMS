import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IqcAqlQualitySnapshot(Base):
    __tablename__ = "iqc_aql_quality_snapshots"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    inspection_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("iqc_inspections.inspection_id"), nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_batches: Mapped[int] = mapped_column(Integer, nullable=False)
    consecutive_accepted: Mapped[int] = mapped_column(Integer, nullable=False)
    consecutive_rejected: Mapped[int] = mapped_column(Integer, nullable=False)
    last_30d_batch_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_30d_ppm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_90d_ppm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    open_scar_count: Mapped[int] = mapped_column(Integer, nullable=False)
    supplier_rating: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)
    has_safety_defect: Mapped[bool] = mapped_column(Boolean, nullable=False)
    linked_customer_complaint: Mapped[bool] = mapped_column(Boolean, nullable=False)
    calculated_state: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
