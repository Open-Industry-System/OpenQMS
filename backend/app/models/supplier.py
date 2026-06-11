import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, DateTime, Date, Text, Float, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("factory_id", "supplier_no", name="uq_supplier_no_per_factory"),
    )

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    supplier_no: Mapped[str] = mapped_column(String(50), nullable=False)
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    shared_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_shared_profiles.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    product_scope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_review")
    audit_plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audit_plans.audit_id", ondelete="SET NULL"), nullable=True
    )
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    ppap_submissions = relationship("SupplierPPAPSubmission", back_populates="supplier", cascade="all, delete-orphan")
    scars = relationship("SupplierSCAR", back_populates="supplier", cascade="all, delete-orphan")


class SupplierCertification(Base):
    __tablename__ = "supplier_certifications"

    cert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False
    )
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    cert_type: Mapped[str] = mapped_column(String(100), nullable=False)
    cert_no: Mapped[str] = mapped_column(String(100), nullable=False)
    issued_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    file_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SupplierEvaluation(Base):
    __tablename__ = "supplier_evaluations"

    eval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False
    )
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    eval_period: Mapped[str] = mapped_column(String(20), nullable=False)
    eval_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    delivery_score: Mapped[float] = mapped_column(Float, nullable=False)
    service_score: Mapped[float] = mapped_column(Float, nullable=False)
    capa_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    premium_freight_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    customer_disruption_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    capa_penalty: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    finding_penalty: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    premium_freight_penalty: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    customer_disruption_penalty: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    grade: Mapped[str] = mapped_column(String(1), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evaluated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SupplierPPAPSubmission(Base):
    __tablename__ = "supplier_ppap_submissions"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False
    )
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    part_no: Mapped[str] = mapped_column(String(100), nullable=False)
    part_name: Mapped[str] = mapped_column(String(200), nullable=False)
    submission_level: Mapped[int] = mapped_column(Integer, nullable=False)
    submission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ppap_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    supplier = relationship("Supplier", back_populates="ppap_submissions")
    elements = relationship("SupplierPPAPElement", back_populates="submission", cascade="all, delete-orphan", order_by="SupplierPPAPElement.sort_order")


class SupplierPPAPElement(Base):
    __tablename__ = "supplier_ppap_elements"

    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_ppap_submissions.submission_id", ondelete="CASCADE"), nullable=False
    )
    element_no: Mapped[int] = mapped_column(Integer, nullable=False)
    element_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    submission = relationship("SupplierPPAPSubmission", back_populates="elements")


class SupplierSCAR(Base):
    __tablename__ = "supplier_scars"

    scar_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scar_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False
    )
    factory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    requested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    issued_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    capa_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="SET NULL"), nullable=True
    )
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    supplier = relationship("Supplier", back_populates="scars")
    capa = relationship("CAPAEightD", foreign_keys=[capa_ref_id])
