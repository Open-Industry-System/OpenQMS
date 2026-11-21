"""Default-off plugin runtime endpoints; business admission belongs to services."""
from app.schemas.capa_d5_staff import D5CheckpointCreate
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from app.services.agent_runtime import d5_commands
from app.schemas.agent_d5_command import D5Command
from app.services.capa_review_guard import ReviewedContentLocked

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_tasks import require_task_runtime, runtime_error
from app.database import get_db
from app.schemas.agent_control import RuntimeFinish, RuntimeFinishOut
from app.schemas.agent_runtime import ReadonlyCheckpointCreate, ReadonlyCheckpointOut, MessageHistoryHTTPQuery, MessageHistoryOut
from app.schemas.agent_runtime import MessageAck, MessageAckOut, MessageBatch, MessageClaim, RunClaim, RunClaimOut, RuntimeCapabilities, CapaContextQuery, RuntimeEventCreate, RuntimeEventOut, RuntimeResultCreate, RuntimeResultOut
from app.services.agent_runtime import run_dispatch, runtime_access, runtime_messages, readonly_delivery, task_controls, checkpoint_service, d4_text_delivery

from app.services.agent_runtime import model_egress

router = APIRouter(prefix="/api/agent/runtime", tags=["agent-runtime"],
    dependencies=[Depends(require_task_runtime)])


async def get_runtime_identity(request: Request, db: AsyncSession = Depends(get_db)):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid run credential")
    try:
        names=('X-OpenQMS-Task','X-OpenQMS-Run','X-OpenQMS-Lease','X-OpenQMS-Deployment')
        pins=tuple(request.headers.get(name) for name in names)
        namespace=getattr(request.state,'tenant_binding',None)
        if any(value is not None for value in pins):
            from app.models.agent_task import AgentTask
            from app.models.agent_model_deployment import AgentTaskModelBinding,AgentModelDeployment
            from app.services.agent_runtime import model_egress,run_auth
            # Signature/namespace/lease and actual bound receiver are verified
            # before metadata expectations; source projections are not read yet.
            run=await run_auth.verify_run_token(db,header[7:],namespace)
            task=await db.get(AgentTask,run.task_id,populate_existing=True)
            binding=None if task is None else await db.get(AgentTaskModelBinding,task.task_id,populate_existing=True)
            recipient=None if binding is None else await db.get(AgentModelDeployment,binding.deployment_id,populate_existing=True)
            if (task is None or recipient is None or model_egress.deployment_profile(recipient)!=model_egress.D4_PROFILE
                    or binding.config_hmac!=recipient.config_hmac
                    or pins!=(str(task.task_id),str(run.run_id),str(run.lease_epoch),str(binding.deployment_id))):
                raise PermissionError('Invalid managed binding')
        return await runtime_access.verify_runtime_identity(db,header[7:],namespace)
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


@router.get("/capa/d4/root-cause-text")
async def d4_root_cause_text(identity=Depends(get_runtime_identity), db: AsyncSession = Depends(get_db)):
    try:
        return await d4_text_delivery.get_d4_root_cause_text(db, identity)
    except (PermissionError, LookupError, ValueError):
        await db.rollback()
        raise HTTPException(status_code=403, detail="Source unavailable") from None
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Delivery unavailable") from None


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


@router.post("/capa/d5/proposals")
async def d5_proposal_command(body: D5Command, identity=Depends(get_runtime_identity),
                              db: AsyncSession = Depends(get_db)):
    try:
        result = await d5_commands.save_proposal(db, identity, body)
        return JSONResponse(jsonable_encoder(result), headers={'Cache-Control': 'no-store'})
    except PermissionError:
        await db.rollback()
        raise HTTPException(status_code=403, detail='D5 command unavailable', headers={'Cache-Control': 'no-store'}) from None
    except (ValueError, ReviewedContentLocked):
        await db.rollback()
        raise HTTPException(status_code=409, detail='D5 command conflict', headers={'Cache-Control': 'no-store'}) from None
    except DBAPIError:
        await db.rollback()
        raise HTTPException(status_code=409, detail='D5 command retry required', headers={'Cache-Control': 'no-store'}) from None




@router.post('/capa/d5/checkpoints')
async def save_d5_checkpoint(body: D5CheckpointCreate, identity=Depends(get_runtime_identity),
        db: AsyncSession = Depends(get_db)):
    headers = {'Cache-Control': 'no-store'}
    try:
        result = await checkpoint_service.save_d5_checkpoint(db, identity)
        return JSONResponse(jsonable_encoder(result), headers=headers)
    except (PermissionError, LookupError):
        await db.rollback()
        raise HTTPException(status_code=403, detail='D5 checkpoint unavailable', headers=headers) from None
    except (ValueError, DBAPIError):
        await db.rollback()
        raise HTTPException(status_code=409, detail='D5 checkpoint conflict', headers=headers) from None


@router.post('/model/infer')
async def model_inference(body: model_egress.InferenceRequest, identity=Depends(get_runtime_identity), db: AsyncSession = Depends(get_db)):
    try:
        return await model_egress.infer(db, identity, body)
    except (PermissionError, LookupError, ValueError):
        await db.rollback()
        raise HTTPException(status_code=403, detail='Model deployment unavailable') from None


from app.services.agent_runtime import model_workflow


@router.post('/model/tools')
async def model_tool(body: model_workflow.ToolRequest, identity=Depends(get_runtime_identity), db: AsyncSession=Depends(get_db)):
    try:
        result = await model_workflow.execute_tool(db, identity, body)
        return JSONResponse(jsonable_encoder(result), headers={'Cache-Control':'no-store'})
    except (PermissionError, LookupError, ValueError, ReviewedContentLocked):
        await db.rollback()
        raise HTTPException(status_code=403, detail='Model tool unavailable', headers={'Cache-Control':'no-store'}) from None
    except (DBAPIError, OSError):
        await db.rollback()
        raise HTTPException(status_code=409, detail='Retry original issued tool ID', headers={'Cache-Control':'no-store'}) from None


from app.schemas.agent_d4_candidate import D4CandidateCommand

@router.post('/capa/d4/candidates')
async def d4_candidate_command(body: D4CandidateCommand, identity=Depends(get_runtime_identity), db: AsyncSession=Depends(get_db)):
    from app.services.capa_d4_candidates import save_candidate
    try:
        result = await save_candidate(db, identity, body)
        return JSONResponse(jsonable_encoder(result), headers={'Cache-Control':'no-store'})
    except PermissionError:
        await db.rollback()
        raise HTTPException(status_code=403, detail='D4 candidate unavailable', headers={'Cache-Control':'no-store'}) from None
    except (ValueError, ReviewedContentLocked, DBAPIError):
        await db.rollback()
        raise HTTPException(status_code=409, detail='D4 candidate conflict', headers={'Cache-Control':'no-store'}) from None


@router.post('/capa/d4/checkpoints')
async def d4_candidate_checkpoint(body: D5CheckpointCreate, identity=Depends(get_runtime_identity), db: AsyncSession=Depends(get_db)):
    from app.services.agent_runtime.d4_candidate_checkpoints import save_checkpoint
    try:
        result=await save_checkpoint(db,identity)
        return JSONResponse(jsonable_encoder(result),headers={'Cache-Control':'no-store'})
    except PermissionError:
        await db.rollback()
        raise HTTPException(status_code=403,detail='D4 checkpoint unavailable',headers={'Cache-Control':'no-store'}) from None
    except (ValueError,ReviewedContentLocked,DBAPIError):
        await db.rollback()
        raise HTTPException(status_code=409,detail='D4 checkpoint conflict',headers={'Cache-Control':'no-store'}) from None
