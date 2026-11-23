"""Employee conversation and private Pi broker for the owned local pilot."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_local_trial import local_trial_peer_allowed
from app.core.deps import RequestScope, get_request_scope
from app.database import get_db
from app.services.workspace_agent import WorkspacePilot, denied

router = APIRouter(prefix="/api/agent/workspace", tags=["agent-workspace"])


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(Body):
    kind: Literal["capa"]
    report_id: UUID


class Turn(Body):
    page: Page
    request_id: UUID
    content: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None


class Decision(Body):
    page: Page
    conversation_id: UUID


class Infer(Body):
    turn: int = Field(ge=0, le=8, strict=True)


class ToolCall(Body):
    call_id: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]+$")


def local_pilot(request):
    pilot = getattr(request.app.state, "workspace_agent_pilot", None)
    if isinstance(pilot, WorkspacePilot) and local_trial_peer_allowed(request):
        return pilot
    return None


def require_pilot(request, db):
    pilot = local_pilot(request)
    if pilot is None or not pilot.permits(db):
        raise denied()
    return pilot


@router.get("/availability")
async def availability(request: Request, report_id: UUID | None = None,
        scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    pilot = local_pilot(request)
    if pilot is None or not pilot.permits(db, scope.user.user_id):
        return {"enabled": False}
    if report_id is None or report_id != pilot.approval.report_id:
        return {"enabled": True}
    source = await pilot.source(db, scope, report_id)
    await pilot.model(db)
    return {"enabled": True, "context": {"document_no": source.document_no}}


@router.get("/conversations/{conversation_id}")
async def restore(request: Request, conversation_id: UUID, report_id: UUID,
        scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    result = await require_pilot(request, db).restore(db, scope, conversation_id=conversation_id,
        report_id=report_id)
    return JSONResponse(jsonable_encoder(result), headers={"Cache-Control": "no-store"})


@router.post("/turn")
async def turn(request: Request, body: Turn, scope: RequestScope = Depends(get_request_scope),
        db: AsyncSession = Depends(get_db)):
    content = body.content.strip()
    if not content:
        raise HTTPException(422, "请输入要发送的内容")
    return await require_pilot(request, db).turn(db, scope, conversation_id=body.conversation_id,
        request_id=body.request_id, report_id=body.page.report_id, content=content)


@router.post("/actions/{action_id}/confirm")
async def confirm(request: Request, action_id: UUID, body: Decision,
        scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    return await require_pilot(request, db).action(db, scope, action_id=action_id,
        conversation_id=body.conversation_id, report_id=body.page.report_id, confirm=True)


@router.post("/actions/{action_id}/cancel")
async def cancel(request: Request, action_id: UUID, body: Decision,
        scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db)):
    return await require_pilot(request, db).action(db, scope, action_id=action_id,
        conversation_id=body.conversation_id, report_id=body.page.report_id, confirm=False)


@router.post("/runtime/infer", include_in_schema=False)
async def infer(request: Request, body: Infer, authorization: str = Header(default=""),
        db: AsyncSession = Depends(get_db)):
    pilot = require_pilot(request, db)
    return await pilot.infer(db, pilot.runtime(authorization), body.turn)


@router.post("/runtime/tools", include_in_schema=False)
async def execute_tool(request: Request, body: ToolCall, authorization: str = Header(default=""),
        db: AsyncSession = Depends(get_db)):
    pilot = require_pilot(request, db)
    return await pilot.execute_tool(db, pilot.runtime(authorization), body.call_id)
