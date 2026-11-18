"""Internal loopback R7 worker routes with bounded, non-reflecting input."""

from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.requests import ClientDisconnect

from app.core.agent_local_trial import local_trial_peer_allowed
from app.database import get_db
from app.schemas import pfmea_impact_runtime as protocol
from app.services.agent_runtime import pfmea_impact_inference as inference
from app.services.agent_runtime import pfmea_impact_projections as projection
from app.services.agent_runtime.pfmea_impact_release import ProjectionBudgetExceeded
from app.services.agent_runtime.pfmea_impact_results import PublicationScope, publish_pfmea_impact_result
from app.services.agent_runtime.pfmea_impact_runtime import ImpactRuntimeUnavailable, lock_runtime
from app.services.agent_runtime.routes import PFMEA_IMPACT_RUNTIME
from app.services.fmea_impact_projection import IncompleteImpactScope

router = APIRouter(prefix=PFMEA_IMPACT_RUNTIME, tags=["pfmea-impact-runtime"], include_in_schema=False)
_HEADERS = {"Cache-Control": "no-store"}
_PIN_HEADERS = ("X-OpenQMS-Task", "X-OpenQMS-Run", "X-OpenQMS-Lease", "X-OpenQMS-Deployment")
_MAX_BODY = 512 * 1024


async def _body(request, schema):
    buffer = bytearray()
    async for chunk in request.stream():
        if len(buffer) + len(chunk) > _MAX_BODY:
            raise ValueError("Runtime input too large")
        buffer.extend(chunk)
    return schema.model_validate_json(buffer)


def _bindings(current):
    return dict(task_id=str(current.task.task_id), run_id=str(current.run.run_id), lease_epoch=current.epoch)


async def _current(request, db, *, replay=False):
    auth = request.headers.get("Authorization", "")
    if not local_trial_peer_allowed(request) or not auth.startswith("Bearer ") or len(auth) > 8199:
        raise ImpactRuntimeUnavailable()
    current = await lock_runtime(db, auth[7:], getattr(request.state, "tenant_binding", None), terminal_replay=replay)
    expected = (str(current.task.task_id), str(current.run.run_id), str(current.epoch),
                str(current.binding.activation.deployment_id))
    if tuple(request.headers.get(name) for name in _PIN_HEADERS) != expected:
        raise ImpactRuntimeUnavailable()
    return current


@asynccontextmanager
async def _operation(db):
    try:
        yield
    except (PermissionError, LookupError):
        await db.rollback()
        raise HTTPException(403, "Impact runtime unavailable", headers=_HEADERS) from None
    except (ValueError, ClientDisconnect):
        await db.rollback()
        raise HTTPException(409, "Impact operation rejected", headers=_HEADERS) from None
    except Exception:
        await db.rollback()
        raise HTTPException(503, "Impact operation unavailable", headers=_HEADERS) from None


def _reply(body):
    return JSONResponse(body, headers=_HEADERS)


@router.get("/material")
async def material(request: Request, db=Depends(get_db)):
    async with _operation(db):
        current = await _current(request, db)
        return _reply(await projection.material_projection(db, current))


@router.post("/search")
async def search(request: Request, db=Depends(get_db)):
    async with _operation(db):
        body = await _body(request, protocol.Search)
        current = await _current(request, db)
        try:
            result = await projection.search_projection(db, current, term=body.term, cursor=body.cursor)
        except IncompleteImpactScope:
            result = await projection.query_gap(db, current, "scope_incomplete")
        except ProjectionBudgetExceeded:
            result = await projection.query_gap(db, current, "budget_exhausted")
        return _reply(result)


@router.post("/page")
async def page(request: Request, db=Depends(get_db)):
    async with _operation(db):
        body = await _body(request, protocol.Page)
        current = await _current(request, db)
        try:
            result = await projection.page_projection(db, current, scope_ref=body.scope_ref, cursor=body.cursor)
        except IncompleteImpactScope:
            result = await projection.query_gap(db, current, "scope_incomplete", scope_ref=body.scope_ref)
        except ProjectionBudgetExceeded:
            result = await projection.query_gap(db, current, "budget_exhausted", scope_ref=body.scope_ref)
        return _reply(result)


@router.post("/confirm")
async def confirm(request: Request, db=Depends(get_db)):
    async with _operation(db):
        body = await _body(request, protocol.Confirm)
        current = await _current(request, db)
        return _reply(await projection.confirm_projection(db, current, **body.model_dump()))


@router.post("/infer")
async def infer(request: Request, db=Depends(get_db)):
    async with _operation(db):
        await _body(request, protocol.Empty)

        async def recheck():
            return await _current(request, db)

        current, action = await inference.infer_action(db, await recheck(), recheck)
        response = _reply({**_bindings(current), "action": action})
        await db.commit()
        return response


@router.post("/result")
async def result(request: Request, db=Depends(get_db)):
    from app.services.agent_runtime.pfmea_impact_fence import authorize_runtime_publication
    async with _operation(db):
        body = await _body(request, protocol.Result)
        current = await _current(request, db, replay=True)
        scope = PublicationScope(current.task.task_id, current.run.run_id, current.run.installation_id,
                                 current.epoch, current.binding_digest)
        if body.operation_key != f"pfmea-impact:{scope.run_id}:{scope.lease_epoch}":
            raise ValueError("Invalid operation key")

        async def authorize(session, context):
            verified = await _current(request, session, replay=True)
            return await authorize_runtime_publication(session, context, current=verified)

        result_id = await publish_pfmea_impact_result(db, scope, body.submission(), authorize=authorize)
        response = _reply({**_bindings(current), "result_id": str(result_id)})
        await db.commit()
        return response
