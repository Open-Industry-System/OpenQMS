"""Default-off plugin runtime endpoints; business admission belongs to services."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_tasks import require_task_runtime, runtime_error
from app.database import get_db
from app.schemas.agent_control import RuntimeFinish, RuntimeFinishOut
from app.schemas.agent_runtime import ReadonlyCheckpointCreate, ReadonlyCheckpointOut, MessageHistoryHTTPQuery, MessageHistoryOut
from app.schemas.agent_runtime import MessageAck, MessageAckOut, MessageBatch, MessageClaim, RunClaim, RunClaimOut, RuntimeCapabilities, CapaContextQuery, RuntimeEventCreate, RuntimeEventOut, RuntimeResultCreate, RuntimeResultOut
from app.services.agent_runtime import run_dispatch, runtime_access, runtime_messages, readonly_delivery, task_controls, checkpoint_service

router = APIRouter(prefix="/api/agent/runtime", tags=["agent-runtime"],
    dependencies=[Depends(require_task_runtime)])


async def get_runtime_identity(request: Request, db: AsyncSession = Depends(get_db)):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid run credential")
    try:
        return await runtime_access.verify_runtime_identity(db, header[7:],
            getattr(request.state, "tenant_binding", None))
    except PermissionError:
        raise HTTPException(status_code=401, detail="Invalid run credential") from None


@router.post("/claim", response_model=RunClaimOut)
async def claim(body: RunClaim, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        return await run_dispatch.claim_run(db, getattr(request.state, "tenant_binding", None),
            body.installation_id, body.secret, body.request_key)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get("/capabilities", response_model=RuntimeCapabilities)
async def capabilities(identity=Depends(get_runtime_identity), db: AsyncSession = Depends(get_db)):
    try:
        return await runtime_access.get_capabilities(db, identity)
    except PermissionError:
        raise HTTPException(status_code=401, detail="Invalid run credential") from None


@router.post("/messages/claim", response_model=MessageBatch)
async def claim_messages(body: MessageClaim, identity=Depends(get_runtime_identity),
                         db: AsyncSession = Depends(get_db)):
    try:
        return await runtime_messages.claim_messages(db, identity, body.limit)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.post("/messages/ack", response_model=MessageAckOut)
async def ack_messages(body: MessageAck, identity=Depends(get_runtime_identity),
                       db: AsyncSession = Depends(get_db)):
    try:
        return await runtime_messages.ack_messages(db, identity, body.batch_id, body.through_sequence)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get("/capa/context")
async def capa_context(query: CapaContextQuery = Query(), identity=Depends(get_runtime_identity),
                       db: AsyncSession = Depends(get_db)):
    try:
        return await readonly_delivery.get_capa_context(db, identity, query.report_id, query.view)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.post("/events", response_model=RuntimeEventOut)
async def record_event(body: RuntimeEventCreate, identity=Depends(get_runtime_identity),
                       db: AsyncSession = Depends(get_db)):
    try:
        return await readonly_delivery.record_event(db, identity, body)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.post("/results", response_model=RuntimeResultOut)
async def save_result(body: RuntimeResultCreate, identity=Depends(get_runtime_identity),
                      db: AsyncSession = Depends(get_db)):
    try:
        return await readonly_delivery.save_result(db, identity, body)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.post("/finish", response_model=RuntimeFinishOut)
async def finish(body: RuntimeFinish, identity=Depends(get_runtime_identity),
                  db: AsyncSession = Depends(get_db)):
    try:
        return await task_controls.finish_run(db, identity, body.status)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.post("/checkpoints", response_model=ReadonlyCheckpointOut)
async def save_checkpoint(body: ReadonlyCheckpointCreate, identity=Depends(get_runtime_identity),
                          db: AsyncSession = Depends(get_db)):
    try:
        return await checkpoint_service.save_checkpoint(db, identity, body)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None


@router.get("/messages/history", response_model=MessageHistoryOut)
async def message_history(query: MessageHistoryHTTPQuery = Query(), identity=Depends(get_runtime_identity),
                          db: AsyncSession = Depends(get_db)):
    try:
        return await runtime_messages.get_message_history(db, identity, query.after_sequence, query.limit)
    except (PermissionError, LookupError, ValueError) as exc:
        raise runtime_error(exc) from None
