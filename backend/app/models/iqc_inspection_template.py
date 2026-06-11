import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Float, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from app.database import Base


class IqcInspectionTemplate(Base):
    __tablename__ = "iqc_inspection_templates"

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_name: Mapped[str] = mapped_column(String(200), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_materials.material_id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    material: Mapped["IqcMaterial"] = relationship(back_populates="templates")
    items: Mapped[List["IqcTemplateItem"]] = relationship(
        back_populates="template", lazy="selectin", cascade="all, delete-orphan"
    )


class IqcTemplateItem(Base):
    __tablename__ = "iqc_template_items"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_inspection_templates.template_id", ondelete="CASCADE"),
        nullable=False,
    )
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    inspection_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    inspect_type: Mapped[str] = mapped_column(String(20), nullable=False, default="attribute")
    spec_upper: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    spec_lower: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sample_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    aql_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    template: Mapped["IqcInspectionTemplate"] = relationship(back_populates="items")
