import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Integer, Float, Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GrrStudy(Base):
    __tablename__ = "grr_studies"

    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False, default="average_range")
    gauge_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gauges.gauge_id", ondelete="RESTRICT"), nullable=True
    )
    characteristic_name: Mapped[str] = mapped_column(String(255), nullable=False)
    spc_characteristic_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspection_characteristics.ic_id", ondelete="SET NULL"), nullable=True
    )
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tolerance_upper: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tolerance_lower: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reference_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    appraiser_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    part_count: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    trial_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
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


class GrrMeasurement(Base):
    __tablename__ = "grr_measurements"

    measurement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grr_studies.study_id", ondelete="CASCADE"), nullable=False
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    appraiser_name: Mapped[str] = mapped_column(String(100), nullable=False)
    part_no: Mapped[str] = mapped_column(String(100), nullable=False)
    trial_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GrrResult(Base):
    __tablename__ = "grr_results"

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grr_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    ev: Mapped[float] = mapped_column(Float, nullable=False)
    av: Mapped[float] = mapped_column(Float, nullable=False)
    grr: Mapped[float] = mapped_column(Float, nullable=False)
    pv: Mapped[float] = mapped_column(Float, nullable=False)
    tv: Mapped[float] = mapped_column(Float, nullable=False)
    ndc: Mapped[float] = mapped_column(Float, nullable=False)
    grr_percent_tol: Mapped[float] = mapped_column(Float, nullable=False)
    grr_percent_tv: Mapped[float] = mapped_column(Float, nullable=False)
    ev_percent: Mapped[float] = mapped_column(Float, nullable=False)
    av_percent: Mapped[float] = mapped_column(Float, nullable=False)
    pv_percent: Mapped[float] = mapped_column(Float, nullable=False)
    conclusion: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
