import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.iqc_inspection_item import IqcInspectionItem


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

    # ─── New fields for Phase 2 IQC ───
    inspection_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="quick")
    material_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_materials.material_id", ondelete="SET NULL"), nullable=True
    )
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_inspection_templates.template_id", ondelete="SET NULL"),
        nullable=True,
    )
    code_letter: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    accept_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reject_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    re_inspection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parent_inspection_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_inspections.inspection_id", ondelete="SET NULL"),
        nullable=True,
    )
    product_line_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    linked_scar_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_scars.scar_id", ondelete="SET NULL"), nullable=True
    )
    judged_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    judged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    has_safety_defect: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    linked_customer_complaint_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_complaints.complaint_id", ondelete="SET NULL"), nullable=True
    )

    items: Mapped[List["IqcInspectionItem"]] = relationship(
        back_populates="inspection", lazy="selectin", cascade="all, delete-orphan"
    )
