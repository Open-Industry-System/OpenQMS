"""Audit helpers shared by agent harness, gateway, and non-agent consumers."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def write_audit_raw(
    db: AsyncSession, *, user_id: uuid.UUID, factory_id: uuid.UUID | None,
    tenant_schema: str, table_name: str, record_id: uuid.UUID, action: str,
    correlation_id: uuid.UUID | None = None, changed_fields: dict | None = None,
    old_values: dict | None = None, new_values: dict | None = None,
) -> AuditLog:
    """Write an audit log without an AgentContext (for non-agent-session callers).

    flushes only; the caller decides commit timing.
    """
    log = AuditLog(
        log_id=uuid.uuid4(),
        table_name=table_name,
        record_id=record_id,
        action=action,
        changed_fields=changed_fields,
        old_values=old_values,
        new_values=new_values,
        operated_by=user_id,
        factory_id=factory_id,
        tenant_schema=tenant_schema,
        correlation_id=correlation_id,
    )
    db.add(log)
    await db.flush()
    return log


async def write_audit(
    db: AsyncSession, ctx, table_name: str, record_id: uuid.UUID, action: str,
    correlation_id: uuid.UUID | None = None, changed_fields: dict | None = None,
    old_values: dict | None = None, new_values: dict | None = None,
) -> AuditLog:
    """Write an audit log using an AgentContext for scope. Delegates to write_audit_raw."""
    return await write_audit_raw(
        db, user_id=ctx.user_id, factory_id=ctx.factory_id,
        tenant_schema=ctx.tenant_schema, table_name=table_name, record_id=record_id,
        action=action, correlation_id=correlation_id, changed_fields=changed_fields,
        old_values=old_values, new_values=new_values,
    )
