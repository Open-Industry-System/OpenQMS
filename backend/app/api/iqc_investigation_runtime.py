"""Local managed IQC worker ingress; no employee or generic plugin credentials."""

from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from starlette.requests import ClientDisconnect

from app.config import settings
from app.core.agent_local_trial import local_trial_peer_allowed
from app.database import get_db
from app.services.agent_runtime import iqc_investigation_inference as inference
from app.services.agent_runtime import iqc_investigation_runtime as runtime
from app.services.agent_runtime.iqc_investigation_pilot import (
    ASSOCIATIONS, HISTORY, MATERIAL, SUPPLIER, IqcRuntimeUnavailable,
)
from app.services.agent_runtime.iqc_investigation_results import IqcResultCard, publish_iqc_investigation_result

router = APIRouter(prefix=runtime.RUNTIME_PREFIX, tags=["iqc-investigation-runtime"], include_in_schema=False)
_HEADERS = {"Cache-Control": "no-store"}
_PIN_HEADERS = ("X-OpenQMS-Task", "X-OpenQMS-Run", "X-OpenQMS-Lease", "X-OpenQMS-Deployment")
_MAX_BODY = 64 * 1024


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Items(Empty):
    inspection_id: UUID | None = None
    item_id: UUID | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=4096)


class History(Empty):
    cursor: str | None = Field(default=None, min_length=1, max_length=4096)


class Result(Empty):
    operation_key: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
    card: IqcResultCard


async def _body(request, schema):
    buffer = bytearray()
    async for chunk in request.stream():
        if len(buffer) + len(chunk) > _MAX_BODY:
            raise ValueError("Runtime input too large")
        buffer.extend(chunk)
    return schema.model_validate_json(buffer)


async def _current(request, db, *, publishing=False):
    if (not settings.AGENT_TASK_RUNTIME_ENABLED
            or not getattr(settings, "AGENT_R7_IQC_INVESTIGATION_ENABLED", False)
            or settings.TENANT_MODE != "dev"):
        raise IqcRuntimeUnavailable()
    auth = request.headers.get("Authorization", "")
    if not local_trial_peer_allowed(request) or not auth.startswith("Bearer ") or len(auth) > 8199:
        raise IqcRuntimeUnavailable()
    current = await runtime.lock_runtime(
        db, auth[7:], getattr(request.state, "tenant_binding", None),
        terminal_replay=publishing, publishing=publishing,
    )
    expected = (str(current.task.task_id), str(current.run.run_id), str(current.epoch), current.binding["deployment_id"])
    if tuple(request.headers.get(name) for name in _PIN_HEADERS) != expected:
        raise IqcRuntimeUnavailable()
    return current


@asynccontextmanager
async def _operation(db):
    try:
        yield
    except (PermissionError, LookupError):
        await db.rollback()
        raise HTTPException(403, "IQC runtime unavailable", headers=_HEADERS) from None
    except (ValueError, ClientDisconnect):
        await db.rollback()
        raise HTTPException(409, "IQC runtime operation rejected", headers=_HEADERS) from None
    except Exception:
        await db.rollback()
        raise HTTPException(503, "IQC runtime operation unavailable", headers=_HEADERS) from None


def _reply(body):
    return JSONResponse(body, headers=_HEADERS)


@router.get("/context")
async def context(request: Request, db=Depends(get_db)):
    async with _operation(db):
        return _reply(await runtime.context_projection(db, await _current(request, db)))


@router.post("/items")
async def items(request: Request, db=Depends(get_db)):
    async with _operation(db):
        body = await _body(request, Items)
        current = await _current(request, db)
        return _reply(await runtime.item_projection(db, current, **body.model_dump()))


@router.post("/reinspections")
async def reinspections(request: Request, db=Depends(get_db)):
    async with _operation(db):
        await _body(request, Empty)
        return _reply(await runtime.context_projection(db, await _current(request, db), reinspection=True))


async def _optional(request, db, projection, body):
    async with _operation(db):
        params = await _body(request, body)
        return _reply(await runtime.optional_projection(db, await _current(request, db), projection, **params.model_dump()))


@router.post("/associations")
async def associations(request: Request, db=Depends(get_db)):
    return await _optional(request, db, ASSOCIATIONS, Empty)


@router.post("/history")
async def history(request: Request, db=Depends(get_db)):
    return await _optional(request, db, HISTORY, History)


@router.post("/material")
async def material(request: Request, db=Depends(get_db)):
    return await _optional(request, db, MATERIAL, Empty)


@router.post("/supplier")
async def supplier(request: Request, db=Depends(get_db)):
    return await _optional(request, db, SUPPLIER, Empty)


@router.post("/infer")
async def infer(request: Request, db=Depends(get_db)):
    async with _operation(db):
        await _body(request, Empty)

        async def recheck():
            return await _current(request, db)

        current, action = await inference.infer_action(db, await recheck(), recheck)
        response = _reply({**runtime.bindings(current), "action": action})
        await db.commit()
        return response


@router.post("/result")
async def result(request: Request, db=Depends(get_db)):
    async with _operation(db):
        body = await _body(request, Result)
        current = await _current(request, db, publishing=True)
        if body.operation_key != f"iqc-investigation:{current.run.run_id}:{current.epoch}":
            raise ValueError("Invalid operation key")
        identifier = await publish_iqc_investigation_result(db, current.scope, current.task.task_id,
            current.run.run_id, current.epoch, operation_key=body.operation_key, card=body.card)
        response = _reply({**runtime.bindings(current), "result_id": str(identifier)})
        await db.commit()
        return response
