"""Fail-closed, single-tenant lifecycle for one CAPA read task."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import RequestScope
from app.core.factory_scope import check_product_line_access, is_factory_visible
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.models.agent_read_task import AgentReadTask
from app.models.capa import CAPAEightD
from app.services.agent.audit import write_audit_raw
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import Grant
from app.services.capa_agent_capabilities import CAPA_CAPABILITIES

_CAPABILITY_ID = "capa.d4.summary.masked.v1"
_TENANT_SCHEMA = "public"
_LIFETIME = timedelta(hours=24)


def _require_single_tenant() -> None:
    if settings.TENANT_MODE != "single":
        raise ValueError("Agent read tasks require single tenant mode")


def _require_report_scope(report: CAPAEightD, scope: RequestScope) -> None:
    if not is_factory_visible(report.factory_id, scope):
        raise ValueError("CAPA factory denied")
    try:
        check_product_line_access(report.product_line_code, scope)
    except HTTPException as exc:
        raise ValueError("CAPA product line denied") from exc
    if not report.product_line_code:
        raise ValueError("CAPA product line missing")


async def _audit(
    db: AsyncSession, scope: RequestScope, task: AgentReadTask,
    action: str, changed_fields: dict,
) -> None:
    await write_audit_raw(
        db, user_id=scope.user.user_id, factory_id=task.factory_id,
        tenant_schema=_TENANT_SCHEMA, table_name="agent_read_tasks",
        record_id=task.task_id, action=action, changed_fields=changed_fields,
    )


async def create_read_task(
    db: AsyncSession, scope: RequestScope, capa_id: UUID,
) -> AgentReadTask:
    _require_single_tenant()
    report = await db.get(CAPAEightD, capa_id)
    if report is None:
        raise ValueError("CAPA unavailable")
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.VIEW:
        raise ValueError("CAPA unavailable")
    try:
        _require_report_scope(report, scope)
    except ValueError:
        raise ValueError("CAPA unavailable") from None
    created_at = datetime.now(UTC)
    task = AgentReadTask(
        initiator_user_id=scope.user.user_id, tenant_schema=_TENANT_SCHEMA,
        capa_id=report.report_id, factory_id=report.factory_id,
        product_line_code=report.product_line_code,
        capability_id=_CAPABILITY_ID, status="active",
        created_at=created_at, expires_at=created_at + _LIFETIME,
    )
    db.add(task)
    await db.flush()
    await _audit(db, scope, task, "CREATE", {
        "capability_id": task.capability_id, "object_id": str(task.capa_id),
        "expires_at": task.expires_at.isoformat(), "status": task.status,
    })
    await db.commit()
    return task


async def check_read_task(
    db: AsyncSession, scope: RequestScope, task_id: UUID, now: datetime,
) -> Grant:
    _require_single_tenant()
    task = (await db.execute(select(AgentReadTask).where(
        AgentReadTask.task_id == task_id,
        AgentReadTask.initiator_user_id == scope.user.user_id,
    ))).scalar_one_or_none()
    if task is None:
        raise LookupError("Agent read task not found")

    reason = None
    if task.status == "revoked":
        reason = "revoked"
    elif task.status != "active":
        reason = "inactive"
    elif task.expires_at <= now:
        reason = "expired"
    elif task.tenant_schema != _TENANT_SCHEMA:
        reason = "tenant_mismatch"
    elif task.capability_id != _CAPABILITY_ID or get_capability(task.capability_id) != CAPA_CAPABILITIES[_CAPABILITY_ID]:
        reason = "capability_mismatch"
    else:
        report = await db.get(CAPAEightD, task.capa_id)
        if report is None:
            reason = "report_missing"
        elif report.report_id != task.capa_id or report.factory_id != task.factory_id or report.product_line_code != task.product_line_code:
            reason = "report_scope_changed"
        elif await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.VIEW:
            reason = "permission_denied"
        else:
            try:
                _require_report_scope(report, scope)
            except ValueError:
                reason = "scope_denied"

    if reason is not None:
        await _audit(db, scope, task, "CHECK_DENY", {"reason": reason})
        await db.commit()
        message = {
            "expired": "Agent read task expired",
            "revoked": "Agent read task revoked",
        }.get(reason, "Agent read task denied")
        raise ValueError(message)

    grant = Grant(
        capability_id=task.capability_id,
        factory_ids=frozenset({task.factory_id}),
        object_ids=frozenset({task.capa_id}),
        product_line_codes=frozenset({task.product_line_code}),
        expires_at=task.expires_at,
    )
    await _audit(db, scope, task, "CHECK_ALLOW", {
        "capability_id": task.capability_id, "object_id": str(task.capa_id),
        "expires_at": task.expires_at.isoformat(), "status": task.status,
    })
    await db.commit()
    return grant


async def revoke_read_task(
    db: AsyncSession, scope: RequestScope, task_id: UUID,
) -> None:
    _require_single_tenant()
    task = (await db.execute(select(AgentReadTask).where(
        AgentReadTask.task_id == task_id,
        AgentReadTask.initiator_user_id == scope.user.user_id,
    ))).scalar_one_or_none()
    if task is None:
        raise LookupError("Agent read task not found")
    if task.status == "revoked":
        return
    task.status = "revoked"
    task.revoked_at = datetime.now(UTC)
    await _audit(db, scope, task, "REVOKE", {
        "capability_id": task.capability_id, "object_id": str(task.capa_id),
        "expires_at": task.expires_at.isoformat(), "status": task.status,
    })
    await db.commit()
