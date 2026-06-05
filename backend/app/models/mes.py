import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Boolean, Integer, Text, Numeric,
    ForeignKey, UniqueConstraint, DateTime, func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MESConnection(Base):
    __tablename__ = "mes_connections"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    product_line_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MESProductionOrder(Base):
    __tablename__ = "mes_production_orders"
    __table_args__ = (
        UniqueConstraint("connection_id", "order_no", name="uq_mes_production_orders_conn_order"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
        nullable=False,
    )
    order_no: Mapped[str] = mapped_column(String(50), nullable=False)
    product_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    process_route: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    planned_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="planned"
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    mes_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class MESEquipmentStatus(Base):
    __tablename__ = "mes_equipment_status"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_id", name="uq_mes_equipment_status_conn_ext"),
    )

    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    equipment_code: Mapped[str] = mapped_column(String(50), nullable=False)
    equipment_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    availability: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    performance: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    quality: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    oee: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    downtime_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    mes_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class MESScrapRecord(Base):
    __tablename__ = "mes_scrap_records"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_id", name="uq_mes_scrap_records_conn_ext"),
    )

    scrap_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    order_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mes_production_orders.order_id", ondelete="SET NULL"),
        nullable=True,
    )
    equipment_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    defect_type: Mapped[str] = mapped_column(String(50), nullable=False)
    defect_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    defect_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    total_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    defect_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    mes_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class MESMeasurementIngestion(Base):
    __tablename__ = "mes_measurement_ingestions"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "external_id",
            name="uq_mes_measurement_ingestions_conn_ext",
        ),
    )

    ingestion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    order_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ic_code: Mapped[str] = mapped_column(String(100), nullable=False)
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sample_batches.batch_id", ondelete="SET NULL"),
        nullable=True,
    )
    mes_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    source_sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )


class MESSyncJob(Base):
    __tablename__ = "mes_sync_jobs"
    __table_args__ = (
        UniqueConstraint("connection_id", "data_type", name="uq_mes_sync_jobs_conn_type"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
        nullable=False,
    )
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    checkpoint: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MESPushOutbox(Base):
    __tablename__ = "mes_push_outbox"

    outbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class MESScrapMonthlySummary(Base):
    __tablename__ = "mes_scrap_monthly_summary"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "product_line_code", "year_month", "defect_category",
            name="uq_mes_scrap_monthly_summary_conn_pl_ym_cat",
        ),
    )

    summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mes_connections.connection_id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_line_code: Mapped[str] = mapped_column(
        String(50), nullable=False, default="__none__"
    )
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    defect_category: Mapped[str] = mapped_column(String(100), nullable=False)
    total_defect_qty: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    total_total_qty: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    record_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MESProductionOrderArchive(Base):
    __tablename__ = "mes_production_orders_archive"

    archive_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    order_no: Mapped[str] = mapped_column(String(50), nullable=False)
    product_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    process_route: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    planned_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
