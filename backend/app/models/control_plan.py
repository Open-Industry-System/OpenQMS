import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ControlPlan(Base):
    __tablename__ = "control_plans"

    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    fmea_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id"), nullable=True
    )
    source_fmea_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fmea_versions.version_id", ondelete="SET NULL"),
        nullable=True,
    )
    product_line_code: Mapped[str] = mapped_column(String(20), default="DC-DC-100")
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    lock_version: Mapped[int] = mapped_column(Integer, default=0)
    phase: Mapped[str] = mapped_column(String(20), default="production")
    part_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    part_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_info: Mapped[str | None] = mapped_column(String(200), nullable=True)
    drawing_rev: Mapped[str | None] = mapped_column(String(100), nullable=True)
    org_factory: Mapped[str | None] = mapped_column(String(200), nullable=True)
    core_group: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sync_pending: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    customer_requirements: Mapped[list | None] = mapped_column(
        JSONB, default=list, nullable=True
    )

    items = relationship(
        "ControlPlanItem", back_populates="control_plan", cascade="all, delete-orphan"
    )


class ControlPlanItem(Base):
    __tablename__ = "control_plan_items"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_plans.cp_id"), nullable=False
    )
    step_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    process_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    equipment: Mapped[str | None] = mapped_column(String(200), nullable=True)
    characteristic_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    product_characteristic: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    process_characteristic: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    special_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
    specification_tolerance: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    evaluation_method: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sample_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sample_frequency: Mapped[str | None] = mapped_column(String(50), nullable=True)
    control_method: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reaction_plan: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_fmea_node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    item_source: Mapped[str] = mapped_column(String(20), default="fmea")
    sop_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    spc_chart_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspection_characteristics.ic_id", ondelete="SET NULL"), nullable=True
    )
    gauge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gauges.gauge_id", ondelete="SET NULL"), nullable=True
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    control_plan = relationship("ControlPlan", back_populates="items")
