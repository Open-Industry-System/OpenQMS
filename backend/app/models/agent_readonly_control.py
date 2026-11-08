"""Tenant-local control requests, safe checkpoints and committed activity pointers."""
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentTaskControl(Base):
    __tablename__ = "agent_task_controls"
    __table_args__ = (
        sa.UniqueConstraint("task_id", "key", name="uq_agent_control_task_key"),
        sa.CheckConstraint("action IN ('pause','resume','cancel','restart')", name="ck_agent_control_action"),
    )
    control_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"))
    key: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    action: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    expected_epoch: Mapped[int | None] = mapped_column(sa.Integer)
    checkpoint_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_readonly_checkpoints.checkpoint_id"))
    resulting_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


class AgentReadonlyCheckpoint(Base):
    __tablename__ = "agent_readonly_checkpoints"
    __table_args__ = (
        sa.UniqueConstraint("run_id", "key", name="uq_agent_checkpoint_run_key"),
        sa.CheckConstraint("lease_epoch >= 0 AND tenant_generation >= 0 AND accepted_message_seq >= 0", name="ck_agent_checkpoint_positions"),
        sa.CheckConstraint("update_sequence > 0", name="ck_agent_checkpoint_update_sequence"),
    )
    checkpoint_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id"), nullable=False)
    key: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    lease_epoch: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    tenant_generation: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    accepted_message_seq: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    update_sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


class AgentCheckpointReceipt(Base):
    __tablename__ = "agent_checkpoint_receipts"
    checkpoint_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_readonly_checkpoints.checkpoint_id"), primary_key=True)
    receipt_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_projection_receipts.receipt_id"), primary_key=True)


class AgentTaskUpdate(Base):
    __tablename__ = "agent_task_updates"
    __table_args__ = (
        sa.UniqueConstraint("task_id", "sequence", name="uq_agent_update_task_sequence"),
        sa.CheckConstraint("sequence > 0", name="ck_agent_update_sequence"),
        sa.CheckConstraint("kind IN ('message','ack','claim','control','finish','event','result','checkpoint','run_created')", name="ck_agent_update_kind"),
    )
    update_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False)
    sequence: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    object_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
