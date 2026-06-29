"""CRUD helpers for the agent commit whitelist (admin-only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentCommitWhitelist
from app.models.user import User


async def create(
    db: AsyncSession,
    user: User,
    tool_name: str,
    action: str,
    entity_type: str,
    max_scope: dict,
    required_permission: dict,
    enabled: bool = True,
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
    tool_name: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    max_scope: dict | None = None,
    required_permission: dict | None = None,
    enabled: bool | None = None,
) -> AgentCommitWhitelist:
    if tool_name is not None:
        row.tool_name = tool_name
    if action is not None:
        row.action = action
    if entity_type is not None:
        row.entity_type = entity_type
    if max_scope is not None:
        row.max_scope = max_scope
    if required_permission is not None:
        row.required_permission = required_permission
    if enabled is not None:
        row.enabled = enabled
    await db.flush()
    await db.refresh(row)
    return row


async def delete(db: AsyncSession, row: AgentCommitWhitelist) -> None:
    await db.delete(row)
    await db.flush()
