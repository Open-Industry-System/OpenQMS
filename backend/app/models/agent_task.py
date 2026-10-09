"""Tenant-local durable task records and fenced runtime leases."""
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentTask(Base):
    __tablename__ = "agent_tasks"
    __table_args__ = (
        sa.ForeignKeyConstraint(["target_capa_id", "factory_id"], ["capa_eightd.report_id", "capa_eightd.factory_id"], name="fk_agent_task_capa_factory"),
        sa.UniqueConstraint("initiator_id", "request_key", name="uq_agent_task_initiator_request"),
        sa.CheckConstraint("status IN ('blocked_capability','ready','paused','completed','failed','cancelled')", name="ck_agent_task_status"),
    )
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    initiator_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False)
    executor_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False)
    preferred_installation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_plugin_installations.installation_id"), nullable=False)
    target_capa_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    factory_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    request_key: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        sa.CheckConstraint("status IN ('pending','active','paused','stopped','completed','failed')", name="ck_agent_run_status"),
        sa.Index("uq_agent_run_installation_claim", "installation_id", "claim_key", unique=True, postgresql_where=sa.text("claim_key IS NOT NULL")),
        sa.CheckConstraint("lease_epoch >= 0", name="ck_agent_run_lease_epoch"),
        sa.CheckConstraint("accepted_message_seq >= 0", name="ck_agent_run_message_seq"),
        sa.Index("uq_agent_run_nonterminal_task", "task_id", unique=True, postgresql_where=sa.text("status IN ('pending','active','paused')")),
    )
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False)
    installation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_plugin_installations.installation_id"), nullable=False)
    plugin_version: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    resume_checkpoint_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_readonly_checkpoints.checkpoint_id", name="fk_agent_run_resume_checkpoint", use_alter=True))
    lease_epoch: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    claim_key: Mapped[str | None] = mapped_column(sa.String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    accepted_message_seq: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())


class AgentTaskGrant(Base):
    __tablename__ = "agent_task_grants"
    __table_args__ = (
        sa.CheckConstraint("jsonb_typeof(factory_ids) = 'array' AND jsonb_array_length(factory_ids) > 0", name="ck_agent_task_grant_factory_ids_nonempty"),
        sa.CheckConstraint("access_kind = 'read'", name="ck_agent_task_grant_access_kind"),
    )
    grant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False)
    capability_id: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    factory_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    product_line_codes: Mapped[list[str] | None] = mapped_column(JSONB)
    object_ids: Mapped[list[str] | None] = mapped_column(JSONB)
    access_kind: Mapped[str] = mapped_column(sa.String(8), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class AgentTaskMessage(Base):
    __tablename__ = "agent_task_messages"
    __table_args__ = (
        sa.UniqueConstraint("task_id", "sequence", name="uq_agent_task_message_sequence"),
        sa.UniqueConstraint("task_id", "author_id", "idempotency_key", name="uq_agent_task_message_idempotency"),
        sa.CheckConstraint("sequence > 0", name="ck_agent_task_message_sequence"),
        sa.CheckConstraint("sensitivity = 'restricted'", name="ck_agent_task_message_sensitivity"),
        sa.CheckConstraint("state IN ('queued','claimed','accepted')", name="ck_agent_task_message_state"),
    )
    message_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("agent_tasks.task_id"), nullable=False)
    sequence: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    author_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False)
    delivery_batch_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    delivery_epoch: Mapped[int | None] = mapped_column(sa.Integer)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    sensitivity: Mapped[str] = mapped_column(sa.String(20), nullable=False, server_default="restricted")
    idempotency_key: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    state: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="queued")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
