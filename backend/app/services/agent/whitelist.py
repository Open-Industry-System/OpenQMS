"""CRUD helpers for the agent commit whitelist (admin-only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentCommitWhitelist
from app.models.audit import AuditLog
from app.models.user import User


def _audit_log(
    table_name: str,
    record_id: uuid.UUID,
    action: str,
    operated_by: uuid.UUID,
    factory_id: uuid.UUID | None,
    tenant_schema: str | None,
    changed_fields: dict | None = None,
) -> AuditLog:
    return AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        operated_by=operated_by,
        factory_id=factory_id,
        tenant_schema=tenant_schema,
        changed_fields=changed_fields,
    )


async def create(
    db: AsyncSession,
    user: User,
    tool_name: str,
    action: str,
    entity_type: str,
    max_scope: dict,
    required_permission: dict,
    enabled: bool = True,
    factory_id: uuid.UUID | None = None,
    tenant_schema: str | None = None,
) -> AgentCommitWhitelist:
    row = AgentCommitWhitelist(
        id=uuid.uuid4(),
        tool_name=tool_name,
        action=action,
        entity_type=entity_type,
        max_scope=max_scope,
        required_permission=required_permission,
        enabled=enabled,
        created_by=user.user_id,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    db.add(
        _audit_log(
            table_name="agent_commit_whitelist",
            record_id=row.id,
            action="create",
            operated_by=user.user_id,
            factory_id=factory_id,
            tenant_schema=tenant_schema,
        )
    )
    await db.flush()
    return row


async def list_all(db: AsyncSession) -> list[AgentCommitWhitelist]:
    result = await db.execute(
        select(AgentCommitWhitelist).order_by(AgentCommitWhitelist.created_at.desc())
    )
    return list(result.scalars().all())


async def get(db: AsyncSession, whitelist_id: uuid.UUID) -> AgentCommitWhitelist | None:
    result = await db.execute(
        select(AgentCommitWhitelist).where(AgentCommitWhitelist.id == whitelist_id)
    )
    return result.scalar_one_or_none()


async def update(
    db: AsyncSession,
    row: AgentCommitWhitelist,
    user: User,
    tool_name: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    max_scope: dict | None = None,
    required_permission: dict | None = None,
    enabled: bool | None = None,
    factory_id: uuid.UUID | None = None,
    tenant_schema: str | None = None,
) -> AgentCommitWhitelist:
    changed_fields: dict[str, dict] = {}
    if tool_name is not None and row.tool_name != tool_name:
        changed_fields["tool_name"] = {"old": row.tool_name, "new": tool_name}
        row.tool_name = tool_name
    if action is not None and row.action != action:
        changed_fields["action"] = {"old": row.action, "new": action}
        row.action = action
    if entity_type is not None and row.entity_type != entity_type:
        changed_fields["entity_type"] = {"old": row.entity_type, "new": entity_type}
        row.entity_type = entity_type
    if max_scope is not None and row.max_scope != max_scope:
        changed_fields["max_scope"] = {"old": row.max_scope, "new": max_scope}
        row.max_scope = max_scope
    if required_permission is not None and row.required_permission != required_permission:
        changed_fields["required_permission"] = {"old": row.required_permission, "new": required_permission}
        row.required_permission = required_permission
    if enabled is not None and row.enabled != enabled:
        changed_fields["enabled"] = {"old": row.enabled, "new": enabled}
        row.enabled = enabled
    await db.flush()
    await db.refresh(row)
    db.add(
        _audit_log(
            table_name="agent_commit_whitelist",
            record_id=row.id,
            action="update",
            operated_by=user.user_id,
            factory_id=factory_id,
            tenant_schema=tenant_schema,
            changed_fields=changed_fields or None,
        )
    )
    await db.flush()
    return row


async def delete(
    db: AsyncSession,
    row: AgentCommitWhitelist,
    user: User,
    factory_id: uuid.UUID | None = None,
    tenant_schema: str | None = None,
) -> None:
    await db.delete(row)
    await db.flush()
    db.add(
        _audit_log(
            table_name="agent_commit_whitelist",
            record_id=row.id,
            action="delete",
            operated_by=user.user_id,
            factory_id=factory_id,
            tenant_schema=tenant_schema,
        )
    )
    await db.flush()
