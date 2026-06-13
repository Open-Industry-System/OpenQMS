import uuid
from sqlalchemy import String, Integer, Float, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from app.database import Base


class IqcInspectionItem(Base):
    __tablename__ = "iqc_inspection_items"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_inspections.inspection_id", ondelete="CASCADE"),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    template_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_template_items.item_id", ondelete="SET NULL"),
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    inspect_type: Mapped[str] = mapped_column(String(20), nullable=False, default="attribute")
    spec_upper: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    spec_lower: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sample_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    accept_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reject_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    defect_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    inspection: Mapped["IqcInspection"] = relationship(back_populates="items")
    measurements: Mapped[List["IqcItemMeasurement"]] = relationship(
        back_populates="item", lazy="selectin", cascade="all, delete-orphan"
    )


class IqcItemMeasurement(Base):
    __tablename__ = "iqc_item_measurements"

    measurement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_inspection_items.item_id", ondelete="CASCADE"),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    measured_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    attribute_result: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    item: Mapped["IqcInspectionItem"] = relationship(back_populates="measurements")
