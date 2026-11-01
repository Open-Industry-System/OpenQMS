"""Single-report, tenant-local authorization for an internal Agent read task."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentReadTask(Base):
    __tablename__ = "agent_read_tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["capa_id", "factory_id"],
            ["capa_eightd.report_id", "capa_eightd.factory_id"],
            ondelete="RESTRICT",
            name="fk_agent_read_task_capa_factory",
        ),
        CheckConstraint("status IN ('active','revoked')", name="ck_agent_read_task_status"),
        CheckConstraint(
            "capability_id = 'capa.d4.summary.masked.v1'",
            name="ck_agent_read_task_capability",
        ),
        CheckConstraint("expires_at > created_at", name="ck_agent_read_task_expiry"),
        Index("ix_agent_read_tasks_initiator_status", "initiator_user_id", "status"),
        Index("ix_agent_read_tasks_expires_at", "expires_at"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    initiator_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    tenant_schema: Mapped[str] = mapped_column(String(63), nullable=False)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False
    )
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False)
    capability_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
