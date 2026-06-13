import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Integer, Float, Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StabilityStudy(Base):
    __tablename__ = "stability_studies"

    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    gauge_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gauges.gauge_id", ondelete="RESTRICT"), nullable=True
    )
    characteristic_name: Mapped[str] = mapped_column(String(255), nullable=False)
    spc_characteristic_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspection_characteristics.ic_id", ondelete="SET NULL"), nullable=True
    )
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reference_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    subgroup_size: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    study_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    accepted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    product_line_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StabilityMeasurement(Base):
    __tablename__ = "stability_measurements"

    measurement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stability_studies.study_id", ondelete="CASCADE"), nullable=False
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    measurement_date: Mapped[date] = mapped_column(Date, nullable=False)
    sample_mean: Mapped[float] = mapped_column(Float, nullable=False)
    sample_range: Mapped[float] = mapped_column(Float, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StabilityResult(Base):
    __tablename__ = "stability_results"

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stability_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    ucl_mean: Mapped[float] = mapped_column(Float, nullable=False)
    lcl_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cl_mean: Mapped[float] = mapped_column(Float, nullable=False)
    ucl_range: Mapped[float] = mapped_column(Float, nullable=False)
    lcl_range: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cl_range: Mapped[float] = mapped_column(Float, nullable=False)
    cpk: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    conclusion: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
