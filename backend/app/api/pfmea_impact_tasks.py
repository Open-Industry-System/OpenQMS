"""Dedicated, report-bound R7 employee task and result endpoints."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import RequestScope, get_request_scope
from app.core.tenant_transaction import TenantBinding
from app.database import get_db
from app.models.agent_pfmea_impact import AgentPfmeaImpactBinding
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_runtime_event import AgentResult
from app.models.agent_task import AgentRun, AgentTask
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.services.agent_runtime import pfmea_impact_history as history
from app.services.agent_runtime import pfmea_impact_tasks as tasks
from app.services.agent_runtime.control_authority_fence import ControlFenceBusy, _no_wait, lock_employee_acl
from app.services.agent_runtime.pfmea_impact_pilot import ImpactPilot
from app.services.capa_impact_material import ImpactMaterialNotReady, authorize_history
from app.services.fmea_agent_sources import visible_fmea_source

_NO_STORE = {"Cache-Control": "no-store"}


def _unavailable() -> HTTPException:
    return HTTPException(404, "Impact assessment unavailable", headers=_NO_STORE)


def require_r7_enabled():
    if not (settings.AGENT_TASK_RUNTIME_ENABLED and settings.AGENT_R7_PFMEA_IMPACT_ENABLED):
        raise _unavailable()


router = APIRouter(
    prefix="/api/capa/{report_id}/pfmea-impact", tags=["pfmea-impact"],
    dependencies=[Depends(require_r7_enabled)],
)


class ImpactTaskStart(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    fmea_id: UUID
    approved_version_id: UUID
    installation_id: UUID
    model_deployment_id: UUID
    request_key: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    previous_result_id: UUID | None = None


@asynccontextmanager
async def _operation(db: AsyncSession, *, require_pilot: bool = True):
    try:
        binding = tasks._namespace(db)
        if require_pilot and _active_pilot(db, binding) is None:
            raise _unavailable()
        yield binding
    except ControlFenceBusy:
        await db.rollback()
        raise HTTPException(503, "Impact assessment unavailable", headers=_NO_STORE) from None
    except (PermissionError, LookupError):
        await db.rollback()
        raise _unavailable() from None
    except ImpactMaterialNotReady as exc:
        await db.rollback()
        raise HTTPException(409, exc.reason, headers=_NO_STORE) from None
    except ValueError:
        await db.rollback()
        raise HTTPException(409, "Impact inputs changed", headers=_NO_STORE) from None


def _active_pilot(db: AsyncSession, binding: TenantBinding) -> ImpactPilot | None:
    pilot = db.info.get("r7_impact_pilot")
    if (
        not isinstance(pilot, ImpactPilot)
        or (pilot.tenant_id, pilot.tenant_generation) != (binding.tenant_id, binding.generation)
        or pilot.expires_at <= datetime.now(UTC)
    ):
        return None
    return pilot


async def _reply(db: AsyncSession, body, status_code=200) -> JSONResponse:
    # Materialize and encode under the authorization fence. Nothing leaves the
    # endpoint until the lock-owning transaction successfully commits.
    response = JSONResponse(jsonable_encoder(body), status_code=status_code, headers=_NO_STORE)
    await db.commit()
    return response


def _task_payload(task_id: UUID, status: str, result_id: UUID | None = None):
    return {"taskId": task_id, "status": status, "resultId": result_id}


async def _owned_task(
    db: AsyncSession, reader: RequestScope, report_id: UUID, task_id: UUID, *, lock=False,
) -> AgentTask:
    current = await tasks._report_scope(db, reader, report_id)
    query = select(AgentTask).where(
        AgentTask.task_id == task_id, AgentTask.target_capa_id == report_id,
        AgentTask.factory_id == current.factory_id, AgentTask.initiator_id == reader.user.user_id,
        AgentTask.executor_user_id == reader.user.user_id,
    ).execution_options(populate_existing=True)
    task = (await _no_wait(db, query)).scalar_one_or_none() if lock else await db.scalar(query)
    if task is None:
        raise tasks.ImpactTaskUnavailable()
    return task


@router.get("/availability")
async def availability(
    report_id: UUID, scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db),
):
    async with _operation(db, require_pilot=False) as tenant:
        report = await tasks._report_scope(db, scope, report_id)
        can_generate = _active_pilot(db, tenant) is not None
        available = can_generate
        if not can_generate:
            page = await _history_page(db, scope, report_id, report.factory_id, page=1, page_size=1)
            available = bool(page["items"])
        return await _reply(db, {"available": available, "canGenerate": can_generate})


@router.get("/targets")
async def list_targets(
    report_id: UUID, page: int = Query(1, ge=1, le=500), page_size: int = Query(20, ge=1, le=50),
    scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db),
):
    async with _operation(db):
        targets = await tasks.list_targets(db, scope, report_id, page=page, page_size=page_size)
        return await _reply(db, {
            "items": [{
                "fmeaId": target.fmea_id, "documentNo": target.document_no, "title": target.title,
                "approvedVersionId": target.version_id, "approvedVersionLabel": f"v{target.major_no}.0",
                "hasUnapprovedRevision": target.has_unapproved_revision,
            } for target in targets["items"]],
            "total": targets["total"],
        })


@router.get("/options")
async def list_options(
    report_id: UUID, fmea_id: UUID, approved_version_id: UUID,
    scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db),
):
    async with _operation(db):
        choices = await tasks.list_impact_options(db, scope, report_id, fmea_id, approved_version_id)
        return await _reply(db, {"items": choices["items"] if isinstance(choices, dict) else choices})


@router.post("/tasks", status_code=201)
async def create_task(
    report_id: UUID, body: ImpactTaskStart,
    scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db),
):
    async with _operation(db):
        outcome = await tasks.create_task(db, scope, tasks.ImpactTaskRequest(report_id=report_id, **body.model_dump()))
        if outcome.replayed:
            return await _reply(db, await _current_task_payload(db, scope, report_id, outcome.task_id))
        return await _reply(db, _task_payload(outcome.task_id, "blocked_capability"), 201)


@router.post("/tasks/{task_id}/launch")
async def launch_task(
    report_id: UUID, task_id: UUID,
    scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db),
):
    from app.services.agent_runtime.pfmea_impact_runtime import launch_impact_task

    async with _operation(db):
        await _owned_task(db, scope, report_id, task_id)
        await tasks.load_binding(db, task_id)
        pilot = db.info.get("r7_impact_pilot")
        if not isinstance(pilot, ImpactPilot):
            raise tasks.ImpactTaskUnavailable()
        tenant = tasks._namespace(db)
        slug = await db.scalar(text("""
            SELECT slug FROM public.tenants WHERE id=:tenant_id AND status='active' AND generation=:generation
        """), {"tenant_id": tenant.tenant_id, "generation": tenant.generation})
        if not isinstance(slug, str) or not slug:
            raise tasks.ImpactTaskUnavailable()
        await launch_impact_task(
            db, scope, task_id, platform_origin=f"http://127.0.0.1:{pilot.platform_port}", tenant_slug=slug,
        )
        return await _reply(db, await _current_task_payload(db, scope, report_id, task_id))


async def _current_task_payload(db, scope, report_id, task_id):
    task = await _owned_task(db, scope, report_id, task_id)
    binding = await tasks.load_binding(db, task_id)
    await authorize_history(db, scope, binding.capa)
    target_access = await visible_fmea_source(db, scope, binding.target.fmea_id)
    if (target_access.factory_id, target_access.product_line_code) != (
        binding.capa.factory_id, binding.capa.product_line_code,
    ):
        raise tasks.ImpactTaskUnavailable()
    status, result_id = task.status, None
    if status == "completed":
        result = (await db.scalars(select(AgentResult.result_id).where(
            AgentResult.task_id == task_id,
        ).limit(2))).all()
        if len(result) != 1:
            raise tasks.ImpactTaskUnavailable()
        result_id = result[0]
        await history.read_history_metadata(
            db, scope, history.HistoryLookup(report_id, task_id, result_id),
            authorize=history.authorize_history_projection_sources,
        )
    elif status == "ready":
        active_run = await db.scalar(select(AgentRun.status).where(
            AgentRun.task_id == task_id, AgentRun.status.in_(("pending", "active")),
        ))
        status = {"pending": "queued", "active": "running"}.get(active_run, status)
    return _task_payload(task_id, status, result_id)


@router.get("/tasks/{task_id}")
async def read_task(
    report_id: UUID, task_id: UUID, scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    async with _operation(db):
        return await _reply(db, await _current_task_payload(db, scope, report_id, task_id))


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    report_id: UUID, task_id: UUID, scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    async with _operation(db):
        actor = scope.user.user_id
        prior = await _owned_task(db, scope, report_id, task_id)
        installation_id = prior.preferred_installation_id
        await tasks.load_binding(db, task_id)
        if (await _no_wait(db, select(AgentPluginInstallation.installation_id).where(
            AgentPluginInstallation.installation_id == installation_id,
        ))).scalar_one_or_none() is None:
            raise tasks.ImpactTaskUnavailable()
        task = await _owned_task(db, scope, report_id, task_id, lock=True)
        if task.preferred_installation_id != installation_id:
            raise tasks.ImpactTaskUnavailable()
        run = (await _no_wait(db, select(AgentRun).where(
            AgentRun.task_id == task_id, AgentRun.installation_id == installation_id,
            AgentRun.status.in_(("pending", "active", "paused")),
        ).execution_options(populate_existing=True))).scalar_one_or_none()
        if (await _no_wait(db, select(CAPAEightD.report_id).where(
            CAPAEightD.report_id == report_id, CAPAEightD.factory_id == task.factory_id,
        ))).scalar_one_or_none() is None:
            raise tasks.ImpactTaskUnavailable()
        await lock_employee_acl(db, (actor,), control_only=True)
        await _owned_task(db, scope, report_id, task_id)
        if task.status in {"completed", "failed"}:
            raise tasks.ImpactTaskConflict("Task is terminal")
        if task.status != "cancelled":
            task.status = "cancelled"
            if run is not None:
                run.status = "stopped"
                run.lease_expires_at = None
                run.lease_epoch += 1
                run.claim_key = None
            db.add(AuditLog(
                table_name="agent_tasks", record_id=task_id, action="CANCEL_AGENT_PFMEA_IMPACT",
                operated_by=actor, factory_id=task.factory_id, changed_fields={"status": "cancelled"},
            ))
        return await _reply(db, _task_payload(task_id, task.status))


@router.get("/tasks/{task_id}/results/{result_id}")
async def read_result(
    report_id: UUID, task_id: UUID, result_id: UUID, scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    async with _operation(db, require_pilot=False):
        dto = await history.read_history_review(
            db, scope, history.HistoryLookup(report_id, task_id, result_id),
            authorize=history.authorize_history_projection_sources,
        )
        return await _reply(db, dto)


@router.get("/tasks/{task_id}/results/{result_id}/sources/{source_id}")
async def read_evidence(
    report_id: UUID, task_id: UUID, result_id: UUID, source_id: UUID,
    scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db),
):
    async with _operation(db, require_pilot=False):
        dto = await history.read_history_evidence(
            db, scope, history.HistoryLookup(report_id, task_id, result_id), source_id,
            authorize=history.authorize_history_projection_sources,
        )
        return await _reply(db, dto)


@router.get("/results")
async def list_results(
    report_id: UUID, page: int = Query(1, ge=1, le=50), page_size: int = Query(20, ge=1, le=20),
    scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db),
):
    async with _operation(db, require_pilot=False):
        report = await tasks._report_scope(db, scope, report_id)
        items = await _history_page(db, scope, report_id, report.factory_id, page=page, page_size=page_size)
        return await _reply(db, items)


async def _history_page(db, scope, report_id, factory_id, *, page, page_size):
    candidate_query = select(AgentResult.task_id, AgentResult.result_id, AgentResult.created_at).join(
        AgentTask, AgentTask.task_id == AgentResult.task_id,
    ).join(AgentPfmeaImpactBinding, AgentPfmeaImpactBinding.task_id == AgentTask.task_id).where(
        AgentTask.target_capa_id == report_id, AgentTask.factory_id == factory_id,
        AgentTask.status == "completed",
    ).order_by(AgentResult.created_at.desc(), AgentResult.result_id.desc()).limit(50)
    offset = (page - 1) * page_size
    cursor, visible_count, items = None, 0, []
    while True:
        if cursor is None:
            statement = candidate_query
        else:
            statement = candidate_query.where(tuple_(AgentResult.created_at, AgentResult.result_id)
                < tuple_(*cursor))
        candidates = (await db.execute(statement)).all()
        if not candidates:
            return {"items": items, "hasMore": False}
        for task_id, result_id, created_at in candidates:
            cursor = (created_at, result_id)
            try:
                entry = await history.read_history_metadata(
                    db, scope, history.HistoryLookup(report_id, task_id, result_id),
                    authorize=history.authorize_history_projection_sources,
                )
            except history.ImpactHistoryUnavailable:
                # A NOWAIT rollback also releases earlier authorization
                # locks. Suppress the whole page in that case.
                if not db.in_transaction():
                    raise
                continue
            if visible_count >= offset:
                if len(items) == page_size:
                    return {"items": items, "hasMore": True}
                items.append({
                    "taskId": task_id, "resultId": result_id, "approvedVersionLabel": f"v{entry.major_no}.0",
                    "freshness": "stale" if entry.stale else "current", "createdAt": entry.created_at.isoformat(),
                })
            visible_count += 1
