"""Employee endpoints scoped to a single IQC inspection."""
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import RequestScope, get_request_scope
from app.database import get_db
from app.models.agent_runtime_event import AgentResult
from app.models.agent_task import AgentTask
from app.schemas.agent_task import IqcInvestigationCreate
from app.services.agent_runtime import iqc_investigation_tasks as tasks
from app.services.agent_runtime.control_authority_fence import ControlFenceBusy, lock_employee_acl

_NO_STORE = {"Cache-Control": "no-store"}


def _unavailable():
    return HTTPException(404, "调查建议不可用", headers=_NO_STORE)


def require_enabled():
    if not (
        settings.AGENT_TASK_RUNTIME_ENABLED and settings.AGENT_R7_IQC_INVESTIGATION_ENABLED
        and settings.TENANT_MODE == "dev"
    ):
        raise _unavailable()


router = APIRouter(
    prefix="/api/iqc/inspections/{inspection_id}", tags=["iqc-investigations"],
    dependencies=[Depends(require_enabled)],
)


@asynccontextmanager
async def _operation(db: AsyncSession):
    try:
        tasks.namespace(db)
        yield
    except ControlFenceBusy:
        await db.rollback()
        raise HTTPException(503, "调查资料正在变化，请重试", headers=_NO_STORE) from None
    except (PermissionError, LookupError):
        await db.rollback()
        raise _unavailable() from None
    except tasks.IqcInvestigationConflict:
        await db.rollback()
        raise HTTPException(409, "调查资料或请求已变化，请刷新后重试", headers=_NO_STORE) from None


async def _reply(db, payload, *, status_code=200):
    response = JSONResponse(jsonable_encoder(payload), status_code=status_code, headers=_NO_STORE)
    await db.commit()
    return response


async def _owned_task(db, scope, inspection_id, task_id):
    task, row = await tasks.load_iqc_binding(db, task_id)
    if task.target_iqc_inspection_id != inspection_id or task.initiator_id != scope.user.user_id:
        raise tasks.IqcInvestigationUnavailable()
    facts = await tasks.current_facts(
        db, scope, inspection_id, allow_unassigned_line=row.binding["allow_unassigned_line"],
    )
    if (
        facts.payload["factory_id"] != row.binding["factory_id"]
        or facts.payload["product_line_code"] != row.binding["product_line_code"]
        or facts.payload["identity_generation"] != row.binding["identity_generation"]
    ):
        raise tasks.IqcInvestigationUnavailable()
    return task


def _task_payload(task, result_id=None):
    status = {"blocked_capability": "ready", "ready": "running"}.get(task.status, task.status)
    return {
        "task_id": task.task_id, "status": status, "result_id": result_id,
        "created_at": task.created_at,
    }


@router.get("/investigation-context")
async def read_context(
    inspection_id: UUID, scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    from app.services.agent_runtime.iqc_investigation_runtime import list_iqc_deployments

    async with _operation(db):
        await lock_employee_acl(db, (scope.user.user_id,), read=True)
        facts = await tasks.current_facts(db, scope, inspection_id, allow_unassigned_line=True)
        deployments = await list_iqc_deployments(db, scope, facts) if facts.eligible else []
        return await _reply(db, {
            "inspection_id": inspection_id, "expected_version": facts.version,
            "eligible": facts.eligible, "eligibility_reason": facts.eligibility_reason,
            "deployments": deployments, "facts": facts.payload,
        })


@router.post("/investigations", status_code=201)
async def create_task(
    inspection_id: UUID, body: IqcInvestigationCreate,
    scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db),
):
    async with _operation(db):
        task = await tasks.create_iqc_task(db, scope, inspection_id, body)
        return await _reply(db, _task_payload(task), status_code=201)


@router.post("/investigations/{task_id}/launch")
async def launch_task(
    inspection_id: UUID, task_id: UUID,
    scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db),
):
    from app.services.agent_runtime.iqc_investigation_runtime import launch_iqc_task

    async with _operation(db):
        await _owned_task(db, scope, inspection_id, task_id)
        tenant = tasks.namespace(db)
        pilot = db.info.get("iqc_investigation_pilot")
        if pilot is None:
            raise tasks.IqcInvestigationUnavailable()
        slug = await db.scalar(text("""
            SELECT slug FROM public.tenants WHERE id=:tenant_id AND status='active' AND generation=:generation
        """), {"tenant_id": tenant.tenant_id, "generation": tenant.generation})
        if not slug:
            raise tasks.IqcInvestigationUnavailable()
        await launch_iqc_task(
            db, scope, task_id, platform_origin=f"http://127.0.0.1:{pilot.platform_port}", tenant_slug=slug,
        )
        task = await _owned_task(db, scope, inspection_id, task_id)
        return await _reply(db, _task_payload(task))


class IqcControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["pause", "resume", "cancel"]


@router.post("/investigations/{task_id}/control")
async def control_task(
    inspection_id: UUID, task_id: UUID, body: IqcControl,
    scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db),
):
    async with _operation(db):
        task = await tasks.control_iqc_task(db, scope, inspection_id, task_id, body.operation)
        return await _reply(db, _task_payload(task))


@router.get("/investigations")
async def list_tasks(
    inspection_id: UUID, limit: int = Query(20, ge=1, le=50),
    scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db),
):
    from app.services.agent_runtime.iqc_investigation_results import get_iqc_investigation_result

    async with _operation(db):
        await tasks.current_facts(db, scope, inspection_id, allow_unassigned_line=True)
        listing = (
            select(AgentTask, AgentResult.result_id)
            .outerjoin(AgentResult, AgentResult.task_id == AgentTask.task_id)
            .where(
                AgentTask.task_type == tasks.TASK_TYPE, AgentTask.target_iqc_inspection_id == inspection_id,
                (AgentTask.initiator_id == scope.user.user_id) | (AgentTask.status == "completed"),
            ).order_by(AgentTask.created_at.desc(), AgentTask.task_id).limit(100)
        )
        items = []
        query = listing
        while len(items) < limit:
            candidates = (await db.execute(query)).all()
            if not candidates:
                break
            for task, result_id in candidates:
                try:
                    if result_id is None:
                        if task.status == "completed":
                            continue
                        await _owned_task(db, scope, inspection_id, task.task_id)
                    else:
                        await get_iqc_investigation_result(db, scope, task.task_id, result_id)
                except (LookupError, PermissionError):
                    continue
                items.append(_task_payload(task, result_id))
                if len(items) == limit:
                    break
            last_task, _ = candidates[-1]
            query = listing.where(or_(
                AgentTask.created_at < last_task.created_at,
                and_(AgentTask.created_at == last_task.created_at, AgentTask.task_id > last_task.task_id),
            ))
        return await _reply(db, {"items": items})


@router.get("/investigations/{task_id}/results/{result_id}")
async def read_result(
    inspection_id: UUID, task_id: UUID, result_id: UUID,
    scope: RequestScope = Depends(get_request_scope), db: AsyncSession = Depends(get_db),
):
    from app.services.agent_runtime.iqc_investigation_results import get_iqc_investigation_result

    async with _operation(db):
        task, _ = await tasks.load_iqc_binding(db, task_id)
        if task.target_iqc_inspection_id != inspection_id:
            raise tasks.IqcInvestigationUnavailable()
        result = await get_iqc_investigation_result(db, scope, task_id, result_id)
        return await _reply(db, result)
