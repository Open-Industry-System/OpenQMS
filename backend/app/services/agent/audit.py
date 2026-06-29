"""Audit helper shared by agent harness and gateway."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.services.agent.registry import AgentContext


async def write_audit(
    db: AsyncSession,
    ctx: AgentContext,
    table_name: str,
    record_id: uuid.UUID,
    action: str,
    correlation_id: uuid.UUID | None = None,
    changed_fields: dict | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        log_id=uuid.uuid4(),
        table_name=table_name,
        record_id=record_id,
        action=action,
        changed_fields=changed_fields,
        old_values=old_values,
        new_values=new_values,
        operated_by=ctx.user_id,
        factory_id=ctx.factory_id,
        tenant_schema=ctx.tenant_schema,
        correlation_id=correlation_id,
    )
    db.add(log)
    await db.flush()
    return log
