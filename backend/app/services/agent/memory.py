"""Three-layer memory: Redis short-term, task_state working, embedding long-term (fallback retrieval only in P0)."""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentMemory, AgentSession
from app.services.agent.registry import AgentContext
from app.services.embedding_outbox import enqueue_embedding

_SHORT_TERM_LIMIT = 20


def _short_key(factory_id: uuid.UUID, user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return f"agent:st:{factory_id}:{user_id}:{session_id}"


async def get_short_term(redis, factory_id: uuid.UUID, user_id: uuid.UUID, session_id: uuid.UUID) -> list[dict]:
    if redis is None:
        return []
    raw = await redis.lrange(_short_key(factory_id, user_id, session_id), 0, -1)
    return [json.loads(x) for x in raw]


async def push_short_term(
    redis, factory_id: uuid.UUID, user_id: uuid.UUID, session_id: uuid.UUID, message: dict
) -> None:
    if redis is None:
        return
    key = _short_key(factory_id, user_id, session_id)
    await redis.rpush(key, json.dumps(message, ensure_ascii=False))
    await redis.ltrim(key, -_SHORT_TERM_LIMIT, -1)


async def get_task_state(db: AsyncSession, session: AgentSession) -> dict:
    fresh = (
        await db.execute(select(AgentSession).where(AgentSession.session_id == session.session_id))
    ).scalar_one()
    return fresh.task_state or {}


async def set_task_state(db: AsyncSession, session: AgentSession, state: dict) -> None:
    fresh = (
        await db.execute(select(AgentSession).where(AgentSession.session_id == session.session_id))
    ).scalar_one()
    fresh.task_state = state
    await db.flush()


async def remember(db: AsyncSession, ctx: AgentContext, *, kind: str, content: str) -> AgentMemory:
    m = AgentMemory(
        memory_id=uuid.uuid4(),
        user_id=ctx.user_id,
        factory_id=ctx.factory_id,
        kind=kind,
        content=content,
        source_session_id=ctx.session_id,
        embedding_status="queued",
    )
    db.add(m)
    await db.flush()
    await enqueue_embedding(
        db, entity_type="agent_memory", entity_id=m.memory_id, factory_id=ctx.factory_id
    )
    return m


async def recall_fallback(
    db: AsyncSession, factory_id: uuid.UUID, user_id: uuid.UUID, query: str
) -> list[AgentMemory]:
    """Non-vector fallback: SQL ILIKE on content, scoped by factory+user, excluding failed."""
    result = await db.execute(
        select(AgentMemory)
        .where(AgentMemory.factory_id == factory_id)
        .where(AgentMemory.user_id == user_id)
        .where(AgentMemory.embedding_status != "failed")
        .where(AgentMemory.content.ilike(f"%{query}%"))
        .order_by(AgentMemory.created_at.desc())
        .limit(10)
    )
    return list(result.scalars().all())
