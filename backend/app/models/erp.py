"""ERP integration models."""
import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    String, Boolean, Integer, Numeric, Text, ForeignKey, UniqueConstraint, DateTime, Date, func, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ERPConnection(Base):
    __tablename__ = "erp_connections"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ERPSyncJob(Base):
    __tablename__ = "erp_sync_jobs"
    __table_args__ = (
        UniqueConstraint("connection_id", "data_type", name="uq_erp_sync_jobs_conn_type"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    checkpoint: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ERPPushOutbox(Base):
    __tablename__ = "erp_push_outbox"

    outbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.connection_id", ondelete="CASCADE"), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ERPSupplier(Base):
    __tablename__ = "erp_suppliers"
    __table_args__ = (
        UniqueConstraint("connection_id", "supplier_code", name="uq_erp_suppliers_conn_code"),
    )

    erp_supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    supplier_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    payment_terms: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    tax_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bank_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    openqms_supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="SET NULL"), nullable=True
    )
    link_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    erp_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ERPCustomer(Base):
    __tablename__ = "erp_customers"
    __table_args__ = (
        UniqueConstraint("connection_id", "customer_code", name="uq_erp_customers_conn_code"),
    )

    erp_customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    customer_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tax_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    openqms_customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.customer_id", ondelete="SET NULL"), nullable=True
    )
    link_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    erp_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ERPMaterial(Base):
    __tablename__ = "erp_materials"
    __table_args__ = (
        UniqueConstraint("connection_id", "material_code", name="uq_erp_materials_conn_code"),
    )

    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    material_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    specification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    material_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_purchased: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_manufactured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_supplier_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    erp_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ERPLocation(Base):
    __tablename__ = "erp_locations"
    __table_args__ = (
        UniqueConstraint("connection_id", "location_code", name="uq_erp_locations_conn_code"),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    location_code: Mapped[str] = mapped_column(String(100), nullable=False)
    warehouse_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    zone_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location_type: Mapped[str] = mapped_column(String(50), nullable=False, default="normal")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    erp_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ERPPurchaseOrder(Base):
    __tablename__ = "erp_purchase_orders"
    __table_args__ = (
        UniqueConstraint("connection_id", "po_number", "line_number", name="uq_erp_po_conn_num_line"),
    )

    po_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    po_number: Mapped[str] = mapped_column(String(100), nullable=False)
    line_number: Mapped[str] = mapped_column(String(20), nullable=False, default="1")
    supplier_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    material_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quantity: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    received_quantity: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    actual_delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    lot_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    erp_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ERPSalesOrder(Base):
    __tablename__ = "erp_sales_orders"
    __table_args__ = (
        UniqueConstraint("connection_id", "so_number", "line_number", name="uq_erp_so_conn_num_line"),
    )

    so_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    so_number: Mapped[str] = mapped_column(String(100), nullable=False)
    line_number: Mapped[str] = mapped_column(String(20), nullable=False, default="1")
    customer_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    material_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quantity: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    erp_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ERPInventoryBalance(Base):
    __tablename__ = "erp_inventory_balances"
    __table_args__ = (
        UniqueConstraint("connection_id", "material_code", "location_code", "lot_no", name="uq_erp_inv_conn_mat_loc_lot"),
    )

    balance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    material_code: Mapped[str] = mapped_column(String(100), nullable=False)
    location_code: Mapped[str] = mapped_column(String(100), nullable=False)
    lot_no: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    supplier_lot_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quantity: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    inventory_status: Mapped[str] = mapped_column(String(20), nullable=False, default="available")
    manufacture_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    snapshot_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    erp_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ERPShipment(Base):
    __tablename__ = "erp_shipments"
    __table_args__ = (
        UniqueConstraint("connection_id", "shipment_number", "line_number", name="uq_erp_shipments_conn_num_line"),
    )

    erp_shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    shipment_number: Mapped[str] = mapped_column(String(100), nullable=False)
    line_number: Mapped[str] = mapped_column(String(20), nullable=False, default="1")
    so_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    customer_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    material_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lot_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shipment_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    openqms_shipment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipment_records.shipment_id", ondelete="SET NULL"), nullable=True
    )
    link_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    erp_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class ERPCostRecord(Base):
    __tablename__ = "erp_cost_records"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_id", name="uq_erp_cost_conn_ext"),
    )

    cost_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    record_type: Mapped[str] = mapped_column(String(20), nullable=False)
    cost_category: Mapped[str] = mapped_column(String(50), nullable=False)
    cost_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    period_month: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    source_document_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    material_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    supplier_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cost_center: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cost_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )
    erp_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
