import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class SpecialCharacteristic(Base):
    __tablename__ = "special_characteristics"
    __table_args__ = (
        CheckConstraint("sc_type IN ('CC', 'SC')", name="ck_sc_type"),
        CheckConstraint("source_type IN ('DFMEA', 'PFMEA')", name="ck_source_type"),
        CheckConstraint(
            "safety_approval_status IN ('pending', 'submitted', 'approved', 'rejected') OR safety_approval_status IS NULL",
            name="ck_safety_approval_status",
        ),
    )

    sc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sc_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    sc_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sc_type: Mapped[str] = mapped_column(String(4), nullable=False)
    customer_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sc_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    spec_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_sc_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("special_characteristics.sc_id"), nullable=True)
    source_fmea_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id"), nullable=True)
    source_node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(String(10), nullable=False)
    cp_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("control_plan_items.item_id"), nullable=True)
    msa_study_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    msa_status: Mapped[str] = mapped_column(String(20), nullable=True, default="PENDING")
    sop_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False)
    is_supplier_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    supplier_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_safety_related: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_safety_suggested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    safety_approval_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    safety_submitted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    safety_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    safety_approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    safety_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    safety_approval_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_regulation_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    safety_verification_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source_fmea = relationship("FMEADocument", foreign_keys=[source_fmea_id], lazy="selectin")
    cp_item = relationship("ControlPlanItem", foreign_keys=[cp_item_id], lazy="selectin")
    parent_sc = relationship("SpecialCharacteristic", remote_side=[sc_id], lazy="selectin")
