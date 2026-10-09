"""Tenant-local metadata for scan-gated private task attachments."""
from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import TenantBase


class AgentTaskAttachment(TenantBase):
    __tablename__ = "agent_task_attachments"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('scanning','promoting','available','rejected_malware',"
            "'rejected_scanner','failed_storage','purging','purged')",
            name="ck_agent_task_attachment_status",
        ),
        sa.CheckConstraint(
            "(tenant_id IS NULL AND origin_generation IS NULL) OR "
            "(tenant_id IS NOT NULL AND origin_generation IS NOT NULL)",
            name="ck_agent_task_attachment_generation_pair",
        ),
        sa.CheckConstraint(
            "byte_size IS NULL OR byte_size >= 0",
            name="ck_agent_task_attachment_size_nonnegative",
        ),
        sa.Index("ix_agent_task_attachment_task_status", "task_id", "status"),
        sa.Index("ix_agent_task_attachment_expires_status", "expires_at", "status"),
    )

    attachment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("agent_tasks.task_id"),
        nullable=False,
    )
    factory_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("factories.id"),
        nullable=False,
    )
    uploaded_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("users.user_id"),
        nullable=False,
    )
    tenant_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    origin_generation: Mapped[int | None] = mapped_column(sa.Integer)
    storage_namespace: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    storage_key: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(sa.String(255))
    extension: Mapped[str | None] = mapped_column(sa.String(16))
    declared_content_type: Mapped[str | None] = mapped_column(sa.String(255))
    byte_size: Mapped[int | None] = mapped_column(sa.BigInteger)
    sha256: Mapped[str | None] = mapped_column(sa.String(64))
    status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default="scanning"
    )
    failure_code: Mapped[str | None] = mapped_column(sa.String(64))
    reservation_expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    scanner_version: Mapped[str | None] = mapped_column(sa.String(255))
    scanned_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()
    )
