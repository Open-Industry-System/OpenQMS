"""Employee admission and immutable input binding for an IQC investigation."""
from datetime import UTC, datetime
from hmac import compare_digest
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import RequestScope
from app.core.permissions import Module, PermissionLevel
from app.core.tenant_transaction import TenantBinding
from app.models.agent_iqc_investigation import IqcInvestigationBinding
from app.models.agent_model_deployment import AgentModelDeployment
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_runtime_event import AgentResult
from app.models.agent_task import AgentRun, AgentTask
from app.models.audit import AuditLog
from app.models.iqc_inspection import IqcInspection
from app.models.user import User
from app.schemas.agent_task import IqcInvestigationCreate
from app.services.agent_runtime.control_authority_fence import ControlFenceBusy, _no_wait, lock_employee_acl
from app.services.agent_runtime.d4_text_delivery import _digest
from app.services.capa_current_access import current_module_access, require_business_namespace
from app.services.iqc_investigation_facts import InvestigationNotReadable, read_inspection_facts

TASK_TYPE = "iqc_investigation_advice.v1"
_BINDING_DOMAIN = "openqms.r7.iqc-investigation.task-binding.v1"


class IqcInvestigationUnavailable(LookupError):
    pass


class IqcInvestigationConflict(ValueError):
    pass


def namespace(db: AsyncSession) -> TenantBinding:
    tenant = db.info.get("tenant_binding")
    if not isinstance(tenant, TenantBinding) or tenant.mode != "business":
        raise IqcInvestigationUnavailable()
    return tenant


def _stamp(task: AgentTask, binding: dict) -> str:
    return _digest(_BINDING_DOMAIN, {
        "task_id": str(task.task_id), "actor_id": str(task.initiator_id),
        "request_key": task.request_key, "binding": binding,
    })


async def load_iqc_binding(db: AsyncSession, task_id: UUID) -> tuple[AgentTask, IqcInvestigationBinding]:
    await require_business_namespace(db)
    tenant = namespace(db)
    with db.no_autoflush:
        task = await db.get(AgentTask, task_id, populate_existing=True)
        row = await db.get(IqcInvestigationBinding, task_id, populate_existing=True)
    if task is None or row is None or task.task_type != TASK_TYPE:
        raise IqcInvestigationUnavailable()
    data = row.binding
    if (
        not isinstance(data, dict)
        or not compare_digest(row.binding_digest, _stamp(task, data))
        or task.executor_user_id != task.initiator_id
        or (data.get("inspection_id"), data.get("factory_id"), data.get("installation_id"))
        != (str(task.target_iqc_inspection_id), str(task.factory_id), str(task.preferred_installation_id))
        or (data.get("tenant_id"), data.get("tenant_generation")) != (str(tenant.tenant_id), tenant.generation)
    ):
        raise IqcInvestigationUnavailable()
    return task, row


async def try_lock_iqc_associations(db: AsyncSession) -> bool:
    """Try to exclude relation writes until publication commits."""
    tenant = namespace(db)
    with db.no_autoflush:
        return await db.scalar(text(
            "SELECT pg_try_advisory_xact_lock(hashtextextended(:domain || :schema, 0))"
        ), {"domain": "openqms.iqc-associations.v1:", "schema": tenant.schema_name})


async def lock_iqc_associations(db: AsyncSession) -> None:
    if not await try_lock_iqc_associations(db):
        raise ControlFenceBusy()


async def current_iqc_scope(db: AsyncSession, scope: RequestScope) -> RequestScope:
    _, factories, lines = await current_module_access(db, scope, Module.IQC, PermissionLevel.VIEW)
    with db.no_autoflush:
        user = await db.get(User, scope.user.user_id, populate_existing=True)
    if user is None or not user.is_active:
        raise IqcInvestigationUnavailable()
    if (
        scope.effective_factory_id is not None and factories.accessible_factory_ids is not None
        and scope.effective_factory_id not in factories.accessible_factory_ids
    ):
        raise IqcInvestigationUnavailable()
    return RequestScope(factories, scope.effective_factory_id, lines, user)


async def current_facts(db, scope, inspection_id, *, allow_unassigned_line=False):
    try:
        fresh = await current_iqc_scope(db, scope)
        return await read_inspection_facts(
            db, fresh, inspection_id, allow_unassigned_line=allow_unassigned_line,
        )
    except (PermissionError, InvestigationNotReadable):
        raise IqcInvestigationUnavailable() from None


async def _existing(db, actor, request, facts, installation):
    task = await db.scalar(select(AgentTask).where(
        AgentTask.initiator_id == actor, AgentTask.request_key == request.request_key,
    ))
    if task is None:
        return None
    task, row = await load_iqc_binding(db, task.task_id)
    if (
        task.preferred_installation_id != installation.installation_id
        or row.binding.get("inspection_id") != facts.payload["inspection_id"]
        or row.binding.get("facts_version") != request.expected_version
        or row.binding.get("deployment_id") != str(request.model_deployment_id)
        or row.binding.get("previous_result_id") != (
            str(request.previous_result_id) if request.previous_result_id else None
        )
    ):
        raise IqcInvestigationConflict()
    return task


async def _require_previous_result(db, scope, inspection_id, result_id):
    if result_id is None:
        return
    from app.services.agent_runtime.iqc_investigation_results import get_iqc_investigation_result

    task_id = await db.scalar(select(AgentResult.task_id).join(
        AgentTask, AgentTask.task_id == AgentResult.task_id,
    ).where(AgentResult.result_id == result_id, AgentTask.target_iqc_inspection_id == inspection_id,
            AgentTask.task_type == TASK_TYPE))
    if task_id is None:
        raise IqcInvestigationUnavailable()
    await get_iqc_investigation_result(db, scope, task_id, result_id)


async def create_iqc_task(
    db: AsyncSession, scope: RequestScope, inspection_id: UUID, request: IqcInvestigationCreate,
) -> AgentTask:
    from app.services.agent_runtime.iqc_investigation_runtime import resolve_iqc_activation
    from app.services.agent_runtime.iqc_investigation_pilot import fresh_iqc_scope, granted_capabilities

    await require_business_namespace(db)
    tenant = namespace(db)
    initial = await current_facts(db, scope, inspection_id, allow_unassigned_line=True)
    installation, deployment, _ = await resolve_iqc_activation(
        db, scope, initial, request.model_deployment_id,
    )
    # Serialize admission with administrative changes. Recheck after acquiring the fences.
    await _no_wait(db, select(AgentPluginInstallation.installation_id).where(
        AgentPluginInstallation.installation_id == installation.installation_id,
    ), read=True)
    await _no_wait(db, select(AgentModelDeployment.deployment_id).where(
        AgentModelDeployment.deployment_id == deployment.deployment_id,
    ), read=True)
    await _require_previous_result(db, scope, inspection_id, request.previous_result_id)
    await _no_wait(db, select(IqcInspection.inspection_id).where(
        IqcInspection.inspection_id.in_(initial.family_ids),
    ).order_by(IqcInspection.inspection_id), read=True)
    actor = scope.user.user_id
    await lock_employee_acl(db, (actor,), read=True)
    facts = await current_facts(db, scope, inspection_id, allow_unassigned_line=True)
    installation, deployment, pilot = await resolve_iqc_activation(
        db, scope, facts, request.model_deployment_id,
    )
    if (
        not facts.eligible or facts.version != request.expected_version
        or initial.version != facts.version
    ):
        raise IqcInvestigationConflict()
    existing = await _existing(db, actor, request, facts, installation)
    if existing is not None:
        return existing

    factory_id = UUID(facts.payload["factory_id"])
    task = AgentTask(
        task_id=uuid4(), task_type=TASK_TYPE, initiator_id=actor, executor_user_id=actor,
        preferred_installation_id=installation.installation_id, target_iqc_inspection_id=inspection_id,
        factory_id=factory_id, request_key=request.request_key, status="blocked_capability",
    )
    line = facts.payload["product_line_code"]
    employee = await fresh_iqc_scope(db, actor)
    association_lines = None if employee.pl_scope.mode == "ALL" else sorted(employee.pl_scope.codes or ())
    binding = {
        "inspection_id": str(inspection_id), "factory_id": str(factory_id), "product_line_code": line,
        "facts_version": facts.version, "tenant_id": str(tenant.tenant_id),
        "tenant_generation": tenant.generation, "installation_id": str(installation.installation_id),
        "installation_epoch": installation.credential_epoch, "plugin_version": installation.plugin_version,
        "deployment_id": str(deployment.deployment_id), "deployment_hmac": deployment.config_hmac,
        "deployment_name": deployment.name, "deployment_version": deployment.version,
        "capabilities": sorted(await granted_capabilities(db, installation, pilot, facts)),
        "association_product_lines": association_lines,
        "previous_result_id": str(request.previous_result_id) if request.previous_result_id else None,
        "allow_unassigned_line": line is None, "identity_generation": facts.payload["identity_generation"],
        "task_date": datetime.now(UTC).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
    }
    try:
        async with db.begin_nested():
            db.add(task)
            await db.flush()
            db.add(IqcInvestigationBinding(task_id=task.task_id, binding=binding, binding_digest=_stamp(task, binding)))
            db.add(AuditLog(
                table_name="agent_tasks", record_id=task.task_id, action="CREATE_IQC_INVESTIGATION_TASK",
                operated_by=actor, factory_id=factory_id,
                changed_fields={"inspection_id": str(inspection_id), "facts_version": facts.version},
            ))
            await db.flush()
    except IntegrityError as exc:
        if getattr(exc.orig.__cause__, "constraint_name", None) != "uq_agent_task_initiator_request":
            raise
        replay = await _existing(db, actor, request, facts, installation)
        if replay is None:
            raise
        return replay
    return task

async def control_iqc_task(db, scope, inspection_id: UUID, task_id: UUID, operation: str) -> AgentTask:
    """Fence the old lease before responding to a fixed employee control operation."""
    from app.services.agent_runtime import task_updates

    if operation not in {"pause", "resume", "cancel"}:
        raise IqcInvestigationConflict()
    task, initial = await load_iqc_binding(db, task_id)
    actor = scope.user.user_id
    if task.target_iqc_inspection_id != inspection_id or task.initiator_id != actor:
        raise IqcInvestigationUnavailable()
    await _no_wait(db, select(AgentPluginInstallation.installation_id).where(
        AgentPluginInstallation.installation_id == task.preferred_installation_id,
    ))
    await _no_wait(db, select(AgentTask.task_id).where(AgentTask.task_id == task_id))
    task, bound = await load_iqc_binding(db, task_id)
    if task.initiator_id != actor or bound.binding_digest != initial.binding_digest:
        raise IqcInvestigationUnavailable()
    run = (await _no_wait(db, select(AgentRun).where(
        AgentRun.task_id == task_id, AgentRun.status.in_(("pending", "active", "paused")),
    ).execution_options(populate_existing=True))).scalar_one_or_none()
    await lock_employee_acl(db, (actor,), read=True)
    facts = await current_facts(db, scope, inspection_id, allow_unassigned_line=bound.binding["allow_unassigned_line"])
    if (
        facts.payload["factory_id"] != bound.binding["factory_id"]
        or facts.payload["product_line_code"] != bound.binding["product_line_code"]
        or facts.payload["identity_generation"] != bound.binding["identity_generation"]
    ):
        raise IqcInvestigationUnavailable()

    target_status = {"pause": "paused", "resume": "blocked_capability", "cancel": "cancelled"}[operation]
    if task.status == target_status:
        return task
    allowed = {"pause": {"ready"}, "resume": {"paused"}, "cancel": {"blocked_capability", "ready", "paused"}}
    if task.status not in allowed[operation]:
        raise IqcInvestigationConflict()
    if operation == "resume" and (facts.version != bound.binding["facts_version"] or not facts.eligible):
        raise IqcInvestigationConflict()
    if operation == "pause" and (run is None or run.status != "active"):
        raise IqcInvestigationConflict()
    if run is not None:
        run.status = "paused" if operation == "pause" else "stopped"
        run.lease_epoch += 1
        run.lease_expires_at = None
        run.claim_key = None
    task.status = target_status
    db.add(AuditLog(
        table_name="agent_tasks", record_id=task_id, action="CONTROL_IQC_INVESTIGATION",
        operated_by=actor, factory_id=task.factory_id,
        changed_fields={"operation": operation, "status": target_status},
    ))
    await task_updates.append_update(db, task_id=task_id,
        kind="finish" if operation == "cancel" else "control", object_id=task_id)
    await db.flush()
    return task
