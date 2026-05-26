import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    segment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    csr_list: Mapped[list | None] = mapped_column(JSONB, default=list, nullable=True)
    ppm_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    annual_shipment_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    complaints = relationship("CustomerComplaint", back_populates="customer")
    rma_records = relationship("RMARecord", back_populates="customer")


class CustomerComplaint(Base):
    __tablename__ = "customer_complaints"

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    complaint_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    product_line_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("product_lines.code"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.customer_id"), nullable=False
    )
    product_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    batch_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    defect_desc: Mapped[str] = mapped_column(Text, nullable=False)
    impact_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    occurred_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    fmea_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id"), nullable=True
    )
    capa_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capa_eightd.report_id"), nullable=True
    )
    has_rma: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preliminary_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments: Mapped[list | None] = mapped_column(JSONB, default=list, nullable=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    supplier_responsibility: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scar_ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer = relationship("Customer", back_populates="complaints")
    rma_records = relationship("RMARecord", back_populates="complaint")
    product_line = relationship("ProductLine")


class RMARecord(Base):
    __tablename__ = "rma_records"

    rma_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rma_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    product_line_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("product_lines.code"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.customer_id"), nullable=False
    )
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_complaints.complaint_id"), nullable=True
    )
    product_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    batch_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    return_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    defect_type: Mapped[str] = mapped_column(String(50), nullable=False)
    responsibility: Mapped[str | None] = mapped_column(String(50), nullable=True)
    analysis_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    fmea_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id"), nullable=True
    )
    capa_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capa_eightd.report_id"), nullable=True
    )
    scar_ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    attachments: Mapped[list | None] = mapped_column(JSONB, default=list, nullable=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    customer = relationship("Customer", back_populates="rma_records")
    complaint = relationship("CustomerComplaint", back_populates="rma_records")
    product_line = relationship("ProductLine")
