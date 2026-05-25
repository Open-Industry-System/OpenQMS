import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Integer, Date, DateTime, Text, ForeignKey, Float, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IqcInspection(Base):
    __tablename__ = "iqc_inspections"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inspection_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False
    )
    part_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    part_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    lot_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    lot_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sample_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    aql_level: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    inspection_level: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    sampling_standard: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    inspection_result: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    defect_qty: Mapped[int] = mapped_column(Integer, default=0)
    defect_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    linked_capa_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="SET NULL"), nullable=True
    )
    inspection_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    inspected_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
