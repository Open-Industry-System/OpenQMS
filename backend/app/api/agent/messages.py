"""Agent message endpoint — synchronous agent loop."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_db, get_request_scope
from app.core.factory_scope import check_factory_access
from app.models.agent import AgentSession
from app.schemas.agent import MessageCreate, MessageOut
from app.services.agent import harness

router = APIRouter(prefix="/sessions", tags=["agent-messages"])


@router.post("/{session_id}/messages", response_model=MessageOut)
async def post_message(
    session_id: uuid.UUID,
    req: MessageCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    result = await db.execute(
        select(AgentSession).where(AgentSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    check_factory_access(session.factory_id, scope)
    if session.user_id != scope.user.user_id:
        raise HTTPException(status_code=403, detail="无权操作他人会话")
    run_result = await harness.run_message(
        db, session, scope.user, redis=None, user_message=req.content
    )
    return MessageOut(
        assistant_text=run_result.assistant_text,
        blocked=run_result.blocked,
        reason=run_result.reason,
    )
