import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PLMConnection(Base):
    __tablename__ = "plm_connections"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    product_line_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=False
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

    parts: Mapped[list["PLMPart"]] = relationship(back_populates="connection", passive_deletes=True)
    boms: Mapped[list["PLMBOM"]] = relationship(back_populates="connection", passive_deletes=True)
    change_orders: Mapped[list["PLMChangeOrder"]] = relationship(back_populates="connection", passive_deletes=True)
    sync_jobs: Mapped[list["PLMSyncJob"]] = relationship(back_populates="connection", passive_deletes=True)
    outbox: Mapped[list["PLMPushOutbox"]] = relationship(back_populates="connection", passive_deletes=True)


class PLMPart(Base):
    __tablename__ = "plm_parts"
    __table_args__ = (
        UniqueConstraint("connection_id", "part_number", "revision", name="uq_plm_part_conn_pn_rev"),
    )

    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    part_number: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    revision: Mapped[str] = mapped_column(String(20), nullable=False, default="A", server_default=text("'A'"))
    material: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    specification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default=text("'active'"))
    is_safety_related: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    is_key_characteristic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )  # Nullable because source may omit; services should fill or filter via connection product line.
    plm_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    connection: Mapped["PLMConnection"] = relationship(back_populates="parts")
    fmea_links: Mapped[list["PLMPartFMEALink"]] = relationship(back_populates="part", cascade="all, delete-orphan", passive_deletes=True)
    sc_links: Mapped[list["PLMPartSCLink"]] = relationship(back_populates="part", cascade="all, delete-orphan", passive_deletes=True)


class PLMBOM(Base):
    __tablename__ = "plm_boms"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "parent_part_number",
            "parent_revision",
            "child_part_number",
            "child_revision",
            "bom_revision",
            name="uq_plm_bom_conn_parent_child_rev",
        ),
    )

    bom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_part_number: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_revision: Mapped[str] = mapped_column(String(20), nullable=False, default="A", server_default=text("'A'"))
    child_part_number: Mapped[str] = mapped_column(String(100), nullable=False)
    child_revision: Mapped[str] = mapped_column(String(20), nullable=False, default="A", server_default=text("'A'"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("1.0"), server_default=text("1.0"))
    bom_revision: Mapped[str] = mapped_column(String(20), nullable=False, default="A", server_default=text("'A'"))
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )  # Nullable because source may omit; services should fill or filter via connection product line.
    plm_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    connection: Mapped["PLMConnection"] = relationship(back_populates="boms")


class PLMChangeOrder(Base):
    __tablename__ = "plm_change_orders"
    __table_args__ = (
        UniqueConstraint("connection_id", "change_number", name="uq_plm_co_conn_num"),
    )

    change_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    change_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default=text("'draft'"))
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal", server_default=text("'normal'"))
    affected_part_numbers: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    proposed_changes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    planned_implementation_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_implementation_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=True
    )  # Nullable because source may omit; services should fill or filter via connection product line.
    plm_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    connection: Mapped["PLMConnection"] = relationship(back_populates="change_orders")
    impact_task: Mapped[Optional["PLMChangeImpactTask"]] = relationship(
        back_populates="change_order", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )


class PLMSyncJob(Base):
    __tablename__ = "plm_sync_jobs"
    __table_args__ = (
        UniqueConstraint("connection_id", "data_type", name="uq_plm_sync_job_conn_type"),
        Index("ix_plm_sync_jobs_status_next_run", "status", "next_run_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"),
        nullable=False,
    )
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default=text("'pending'"))
    checkpoint: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    connection: Mapped[PLMConnection] = relationship(back_populates="sync_jobs")


class PLMPushOutbox(Base):
    __tablename__ = "plm_push_outbox"
    __table_args__ = (
        Index("ix_plm_push_outbox_status_next_retry", "status", "next_retry_at"),
    )

    outbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default=text("'pending'"))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default=text("3"))
    next_retry_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    connection: Mapped[PLMConnection] = relationship(back_populates="outbox")


class PLMChangeImpactTask(Base):
    __tablename__ = "plm_change_impact_tasks"
    __table_args__ = (
        UniqueConstraint("change_id", name="uq_plm_impact_task_change"),
        Index("ix_plm_change_impact_tasks_status_next_retry", "status", "next_retry_at"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    change_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plm_change_orders.change_id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default=text("'pending'"))
    claim_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default=text("3"))
    next_retry_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    change_order: Mapped["PLMChangeOrder"] = relationship(back_populates="impact_task", uselist=False)


class PLMPartFMEALink(Base):
    __tablename__ = "plm_part_fmea_links"
    __table_args__ = (
        UniqueConstraint("part_id", "fmea_id", "node_id", name="uq_plm_part_fmea_link"),
    )

    link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plm_parts.part_id", ondelete="CASCADE"),
        nullable=False,
    )
    fmea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    link_type: Mapped[str] = mapped_column(String(20), nullable=False, default="auto_import", server_default=text("'auto_import'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    part: Mapped["PLMPart"] = relationship(back_populates="fmea_links")


class PLMPartSCLink(Base):
    __tablename__ = "plm_part_sc_links"
    __table_args__ = (
        UniqueConstraint("part_id", "characteristic_type", name="uq_plm_part_sc"),
        Index("ix_plm_part_sc_links_sc_id", "sc_id"),
    )

    link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plm_parts.part_id", ondelete="CASCADE"),
        nullable=False,
    )
    sc_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("special_characteristics.sc_id", ondelete="SET NULL"),
        nullable=True,
    )
    characteristic_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default=text("'pending'"))
    confirmed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    part: Mapped["PLMPart"] = relationship(back_populates="sc_links")
