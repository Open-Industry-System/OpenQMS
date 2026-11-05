"""Server-owned evidence and readonly runtime outputs; no business write authority."""
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentProjectionReceipt(Base):
    __tablename__ = "agent_projection_receipts"
    __table_args__ = (
        sa.CheckConstraint("lease_epoch >= 0 AND tenant_generation >= 0", name="ck_agent_receipt_epochs"),
        sa.CheckConstraint("data_class = 'internal'", name="ck_agent_receipt_data_class"),
    )
    receipt_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"), nullable=False)
    lease_epoch: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tenant_generation: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    source_capa_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("capa_eightd.report_id"), nullable=False)
    projection_id: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    projection_digest: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    data_class: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


class AgentRunEvent(Base):
    __tablename__ = "agent_run_events"
    __table_args__ = (sa.UniqueConstraint("run_id", "idempotency_key", name="uq_agent_event_run_key"),)
    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


class AgentResult(Base):
    __tablename__ = "agent_results"
    __table_args__ = (
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_agent_result_run_key"),
        sa.CheckConstraint("data_class = 'restricted'", name="ck_agent_result_data_class"),
    )
    result_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    data_class: Mapped[str] = mapped_column(sa.String(20), nullable=False, server_default="restricted")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


class AgentEventReceipt(Base):
    __tablename__ = "agent_event_receipts"
    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_run_events.event_id"), primary_key=True)
    receipt_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_projection_receipts.receipt_id"), primary_key=True)


class AgentResultReceipt(Base):
    __tablename__ = "agent_result_receipts"
    result_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_results.result_id"), primary_key=True)
    receipt_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_projection_receipts.receipt_id"), primary_key=True)
