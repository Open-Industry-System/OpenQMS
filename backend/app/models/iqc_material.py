import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.iqc_inspection_template import IqcInspectionTemplate


class IqcMaterial(Base):
    __tablename__ = "iqc_materials"

    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    part_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    part_name: Mapped[str] = mapped_column(String(200), nullable=False)
    part_spec: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    material_type: Mapped[str] = mapped_column(String(20), nullable=False, default="raw")
    default_aql: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    default_inspection_level: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False, default="DC-DC-100")
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    templates: Mapped[List["IqcInspectionTemplate"]] = relationship(
        back_populates="material", lazy="selectin", cascade="all, delete-orphan"
    )
