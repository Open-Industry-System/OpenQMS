import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import ForeignKey, String, Numeric, Integer, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


DEFAULT_RULES_CONFIG = {
    "rule_1": True, "rule_2": True, "rule_3": True, "rule_4": True,
    "rule_5": True, "rule_6": True, "rule_7": True, "rule_8": True,
}


class InspectionCharacteristic(Base):
    __tablename__ = "inspection_characteristics"

    ic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ic_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    product_line: Mapped[str] = mapped_column(String(50), nullable=False, default="DC-DC-100")
    process_name: Mapped[str] = mapped_column(String(100), nullable=False)
    characteristic_name: Mapped[str] = mapped_column(String(100), nullable=False)
    spec_upper: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    spec_lower: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    target_value: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    chart_type: Mapped[str] = mapped_column(String(20), nullable=False)
    subgroup_size: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    control_limits_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rules_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: dict(DEFAULT_RULES_CONFIG))
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    batches: Mapped[List["SampleBatch"]] = relationship("SampleBatch", back_populates="characteristic", cascade="all, delete-orphan")
    alarms: Mapped[List["SPCAlarm"]] = relationship("SPCAlarm", back_populates="characteristic", cascade="all, delete-orphan")
    snapshots: Mapped[List["ControlLimitSnapshot"]] = relationship("ControlLimitSnapshot", back_populates="characteristic", cascade="all, delete-orphan")


class SampleBatch(Base):
    __tablename__ = "sample_batches"

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inspection_characteristics.ic_id", ondelete="CASCADE"), nullable=False)
    batch_no: Mapped[str] = mapped_column(String(50), nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subgroup_size: Mapped[int] = mapped_column(Integer, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    characteristic: Mapped["InspectionCharacteristic"] = relationship("InspectionCharacteristic", back_populates="batches")
    values: Mapped[List["SampleValue"]] = relationship("SampleValue", back_populates="batch", cascade="all, delete-orphan")


class SampleValue(Base):
    __tablename__ = "sample_values"

    value_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sample_batches.batch_id", ondelete="CASCADE"), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    alarm_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    batch: Mapped["SampleBatch"] = relationship("SampleBatch", back_populates="values")


class SPCAlarm(Base):
    __tablename__ = "spc_alarms"

    alarm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inspection_characteristics.ic_id", ondelete="CASCADE"), nullable=False)
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("sample_batches.batch_id", ondelete="SET NULL"), nullable=True)
    rule_no: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    linked_capa_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id"), nullable=True)
    acknowledged_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    characteristic: Mapped["InspectionCharacteristic"] = relationship("InspectionCharacteristic", back_populates="alarms")


class ControlLimitSnapshot(Base):
    __tablename__ = "control_limit_snapshots"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inspection_characteristics.ic_id", ondelete="CASCADE"), nullable=False)
    ucl: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    lcl: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    cl: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    r_ucl: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    r_lcl: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    r_cl: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    characteristic: Mapped["InspectionCharacteristic"] = relationship("InspectionCharacteristic", back_populates="snapshots")
