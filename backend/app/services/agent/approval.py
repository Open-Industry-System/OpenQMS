"""agent_actions state machine: pending -> approved | rejected | modified."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentAction
from app.models.user import User
from app.services.agent import gateway, harness
from app.services.agent.registry import AgentContext


async def _get(db: AsyncSession, action_id: uuid.UUID) -> AgentAction:
    a = (await db.execute(select(AgentAction).where(AgentAction.action_id == action_id))).scalar_one()
    return a


async def list_pending(db: AsyncSession, factory_id: uuid.UUID) -> list[AgentAction]:
    result = await db.execute(
        select(AgentAction)
        .where(AgentAction.factory_id == factory_id)
        .where(AgentAction.status == "pending")
        .order_by(AgentAction.created_at)
    )
    return list(result.scalars().all())


async def approve(db: AsyncSession, action_id: uuid.UUID, user: User, reason: str) -> AgentAction:
    a = await _get(db, action_id)
    if a.status != "pending":
        raise ValueError(f"action {action_id} not pending (status={a.status})")
    session = (await db.execute(select_from_session(a.session_id))).scalar_one()
    ctx = await harness.build_context(db, session, user)
    # Force-execute the commit tool (approval IS the authorization): skips the
    # whitelist/pending branch but still enforces permission + writes tool_call + audit.
    res = await gateway.execute_approved_action(ctx, a)
    if res.status == "rejected":
        raise ValueError(f"approved action could not execute: {res.reason}")
    a.status = "approved"
    a.decision_source = "user"
    a.approver_id = user.user_id
    a.reason = reason
    a.post_values = res.result
    a.decided_at = datetime.now(UTC)
    await db.flush()
    return a


async def reject(db: AsyncSession, action_id: uuid.UUID, user: User, reason: str) -> AgentAction:
    a = await _get(db, action_id)
    if a.status != "pending":
        raise ValueError(f"action {action_id} not pending")
    a.status = "rejected"
    a.decision_source = "user"
    a.approver_id = user.user_id
    a.reason = reason
    a.decided_at = datetime.now(UTC)
    ctx = await _ctx_from_action(db, a, user)  # _ctx_from_action is async — must await
    await harness.write_audit(db, ctx, "agent_actions", a.action_id, "rejected", None)
    await db.flush()
    return a


async def modify(db: AsyncSession, action_id: uuid.UUID, user: User, new_payload: dict, reason: str) -> AgentAction:
    a = await _get(db, action_id)
    if a.status != "pending":
        raise ValueError(f"action {action_id} not pending")
    session = (await db.execute(select_from_session(a.session_id))).scalar_one()
    ctx = await harness.build_context(db, session, user)
    a.payload = new_payload  # execute_approved_action reads action.payload
    res = await gateway.execute_approved_action(ctx, a)
    if res.status == "rejected":
        raise ValueError(f"modified action could not execute: {res.reason}")
    a.status = "modified"
    a.decision_source = "user"
    a.approver_id = user.user_id
    a.reason = reason
    a.payload = new_payload
    a.post_values = res.result
    a.decided_at = datetime.now(UTC)
    await db.flush()
    return a


# ---- helpers ----

from app.models.agent import AgentSession


def select_from_session(session_id: uuid.UUID):
    return select(AgentSession).where(AgentSession.session_id == session_id)


async def _ctx_from_action(db: AsyncSession, a: AgentAction, user: User) -> AgentContext:
    session = (await db.execute(select_from_session(a.session_id))).scalar_one()
    return await harness.build_context(db, session, user)
