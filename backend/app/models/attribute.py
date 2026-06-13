import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AttributeStudy(Base):
    __tablename__ = "attribute_studies"

    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    gauge_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gauges.gauge_id", ondelete="SET NULL"), nullable=True
    )
    characteristic_name: Mapped[str] = mapped_column(String(255), nullable=False)
    spc_characteristic_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspection_characteristics.ic_id", ondelete="SET NULL"), nullable=True
    )
    method: Mapped[str] = mapped_column(String(30), nullable=False, default="risk_analysis")
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    known_standard_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
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


class AttributeMeasurement(Base):
    __tablename__ = "attribute_measurements"

    measurement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attribute_studies.study_id", ondelete="CASCADE"), nullable=False
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    appraiser_name: Mapped[str] = mapped_column(String(100), nullable=False)
    part_no: Mapped[str] = mapped_column(String(100), nullable=False)
    known_standard: Mapped[str] = mapped_column(String(10), nullable=False)
    appraiser_decision: Mapped[str] = mapped_column(String(10), nullable=False)
    trial_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AttributeResult(Base):
    __tablename__ = "attribute_results"

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attribute_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    effectiveness: Mapped[float] = mapped_column(Float, nullable=False)
    miss_rate: Mapped[float] = mapped_column(Float, nullable=False)
    false_alarm_rate: Mapped[float] = mapped_column(Float, nullable=False)
    kappa_within: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kappa_vs_standard: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    kappa_between: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    conclusion: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
