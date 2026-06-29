"""Agent harness: session lifecycle, AgentContext construction, audit helper."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.models.agent import AgentSession
from app.models.audit import AuditLog
from app.models.user import User
from app.services.agent.registry import AgentContext


async def create_session(
    db: AsyncSession,
    user: User,
    factory_id: uuid.UUID,
    tenant_schema: str,
    scenario: str,
    related_entity_type: str | None = None,
    related_entity_id: uuid.UUID | None = None,
) -> AgentSession:
    s = AgentSession(
        session_id=uuid.uuid4(),
        user_id=user.user_id,
        factory_id=factory_id,
        tenant_schema=tenant_schema,
        scenario=scenario,
        status="active",
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        task_state={"todo": []},
    )
    db.add(s)
    await db.flush()
    return s


async def build_context(db: AsyncSession, session: AgentSession, user: User) -> AgentContext:
    levels: dict[Module, PermissionLevel] = {}
    for module in Module:
        levels[module] = await get_user_permission(user, module, db)
    return AgentContext(
        db=db,
        session_id=session.session_id,
        user_id=user.user_id,
        factory_id=session.factory_id,
        tenant_schema=session.tenant_schema,
        permission_levels=levels,
        session=session,
    )


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
