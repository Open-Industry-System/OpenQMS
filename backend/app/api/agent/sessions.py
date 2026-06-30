"""Agent session endpoints — create + list."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_db, get_request_scope
from app.core.factory_scope import check_factory_access
from app.models.agent import AgentSession
from app.schemas.agent import SessionCreate, SessionOut
from app.services.agent import harness

router = APIRouter(prefix="/sessions", tags=["agent-sessions"])


def _tenant_schema(request: Request) -> str:
    tenant = getattr(request.state, "tenant", None)
    return tenant.schema_name if tenant else "public"


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    req: SessionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    factory_id = scope.effective_factory_id
    if factory_id is None:
        raise HTTPException(status_code=400, detail="无法确定工厂")
    check_factory_access(factory_id, scope)
    session = await harness.create_session(
        db,
        scope.user,
        factory_id,
        _tenant_schema(request),
        req.scenario,
        req.related_entity_type,
        req.related_entity_id,
    )
    return SessionOut.model_validate(session)


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    factory_id = scope.effective_factory_id
    tenant_schema = _tenant_schema(request)
    stmt = select(AgentSession).where(AgentSession.user_id == scope.user.user_id)
    if factory_id is not None:
        stmt = stmt.where(AgentSession.factory_id == factory_id)
    if tenant_schema:
        stmt = stmt.where(AgentSession.tenant_schema == tenant_schema)
    stmt = stmt.order_by(AgentSession.created_at.desc())
    result = await db.execute(stmt)
    return [SessionOut.model_validate(s) for s in result.scalars().all()]
