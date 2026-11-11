"""Tenant-local D4 delivery metadata, without body or implicit authorization."""
from datetime import datetime
from uuid import UUID as PyUUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import TenantBase


class AgentTaskSourceRequest(TenantBase):
    __tablename__ = 'agent_task_source_requests'
    __table_args__ = (
        sa.PrimaryKeyConstraint('task_id', name='pk_task_source_request'),
        sa.CheckConstraint("request_fingerprint ~ '^[0-9a-f]{64}$'", name='ck_task_source_request_request_fingerprint'),
        sa.CheckConstraint("fingerprint_format = 'd4-source-request.v1'", name='ck_task_source_request_format'),
    )
    task_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey('agent_tasks.task_id', ondelete="RESTRICT", name='fk_task_source_request_task_id'), primary_key=True, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    fingerprint_format: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
