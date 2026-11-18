"""R7 task admission. Run creation and dispatch belong to the controlled profile."""
from dataclasses import dataclass
import hmac
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.core.permissions import Module, PermissionLevel
from app.core.tenant_transaction import TenantBinding
from app.models.agent_model_deployment import AgentModelDeployment
from app.models.agent_pfmea_impact import AgentPfmeaImpactBinding
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_runtime_event import AgentResult
from app.models.agent_task import AgentTask
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument
from app.schemas.pfmea_impact import CapaImpactBinding
from app.services.agent_runtime.control_authority_fence import ControlFenceBusy, _no_wait, lock_employee_acl
from app.services.agent_runtime.d4_text_delivery import _digest
from app.services.capa_current_access import current_module_access, require_business_namespace
from app.services.capa_impact_material import authorize_history, read_material
from app.services.fmea_agent_sources import visible_fmea_source
from app.services.fmea_impact_projection import ApprovedImpactTarget, read_approved_snapshot, read_approved_target

R7_PROFILE = "model_pfmea_impact_v1"
R7_PLUGIN_KEY = "openqms.controlled-pfmea-impact"
_MAX_PICKER_CANDIDATES = 500
_BINDING_DOMAIN = "openqms.r7.pfmea-impact.task-binding.v1"


class ImpactTaskUnavailable(PermissionError):
    def __init__(self):
        super().__init__("PFMEA impact task unavailable")


class ImpactTaskConflict(ValueError):
    """An authorized replay has different target, material, or deployment."""


class _DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ImpactTaskRequest(_DTO):
    model_config = ConfigDict(protected_namespaces=())

    report_id: UUID
    fmea_id: UUID
    approved_version_id: UUID
    installation_id: UUID
    model_deployment_id: UUID
    request_key: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    previous_result_id: UUID | None = None


class ImpactActivation(_DTO):
    """Version pins supplied by the server-owned controlled deployment adapter."""
    profile: Literal["model_pfmea_impact_v1"]
    installation_id: UUID
    plugin_version: str
    credential_epoch: int = Field(ge=0)
    deployment_id: UUID
    deployment_version: str
    deployment_config_hmac: str = Field(pattern=r"^[0-9a-f]{64}$")


class ImpactTargetBinding(_DTO):
    fmea_id: UUID
    approved_version_id: UUID
    major_no: int = Field(ge=1)
    minor_no: Literal[0] = 0
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope_generation: UUID


class ImpactTaskBinding(_DTO):
    contract_version: Literal[1] = 1
    capa: CapaImpactBinding
    target: ImpactTargetBinding
    activation: ImpactActivation
    previous_result_id: UUID | None


@dataclass(frozen=True, slots=True)
class ImpactTaskReceipt:
    task_id: UUID
    replayed: bool


async def _controlled_activation(db, scope, request) -> ImpactActivation:
    from app.services.agent_runtime.pfmea_impact_activation import resolve_activation
    return await resolve_activation(db, scope, request)


async def list_impact_options(db, scope, report_id, fmea_id, approved_version_id) -> list[dict]:
    from app.services.agent_runtime.pfmea_impact_activation import list_impact_options as controlled_options
    return await controlled_options(db, scope, report_id, fmea_id, approved_version_id)


async def _authorize_previous_result(db, scope, request):
    if request.previous_result_id is None:
        return
    from app.services.agent_runtime import pfmea_impact_history as history

    predecessor_task = await db.scalar(select(AgentResult.task_id).join(
        AgentTask, AgentTask.task_id == AgentResult.task_id,
    ).where(AgentResult.result_id == request.previous_result_id, AgentTask.target_capa_id == request.report_id))
    if predecessor_task is None:
        raise ImpactTaskUnavailable()
    lookup = history.HistoryLookup(request.report_id, predecessor_task, request.previous_result_id)
    previous = await history.read_history_metadata(db, scope, lookup,
        authorize=history.authorize_history_projection_sources)
    if previous.fmea_id != request.fmea_id:
        raise ImpactTaskUnavailable()


def _namespace(db) -> TenantBinding:
    tenant = db.info.get("tenant_binding")
    if not isinstance(tenant, TenantBinding) or tenant.mode != "business":
        raise ImpactTaskUnavailable()
    return tenant


async def _report_scope(db, scope, report_id):
    from app.services.capa_current_access import current_capa_access, current_capa_target_metadata

    _, factories, lines = await current_capa_access(db, scope)
    return await current_capa_target_metadata(db, report_id, factories, lines)


async def list_targets(db, scope, report_id, *, page=1, page_size=20) -> dict:
    """Internal picker. Only approved metadata is visible; do not load graph bodies."""
    if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 50:
        raise ValueError("Invalid pagination")
    try:
        report = await _report_scope(db, scope, report_id)
        await current_module_access(db, scope, Module.FMEA, PermissionLevel.VIEW)
        doc = FMEADocument
        candidates = (await db.scalars(select(doc.fmea_id).where(
            doc.factory_id == report.factory_id, doc.product_line_code == report.product_line_code,
            doc.fmea_type == "PFMEA",
        ).order_by(doc.document_no, doc.fmea_id).limit(_MAX_PICKER_CANDIDATES + 1))).all()
        if len(candidates) > _MAX_PICKER_CANDIDATES:
            raise ImpactTaskUnavailable()
        options: list[ApprovedImpactTarget] = []
        for fmea_id in candidates:
            try:
                options.append(await read_approved_target(db, scope, fmea_id, factory_id=report.factory_id,
                    product_line_code=report.product_line_code))
            except LookupError:
                continue
        current = await _report_scope(db, scope, report_id)
        if (report.factory_id, report.product_line_code) != (current.factory_id, current.product_line_code):
            raise ImpactTaskUnavailable()
        await current_module_access(db, scope, Module.FMEA, PermissionLevel.VIEW)
        return {"items": options[(page - 1) * page_size:page * page_size], "total": len(options),
                "page": page, "page_size": page_size}
    except (PermissionError, LookupError):
        raise ImpactTaskUnavailable() from None


async def _lock_activation(db, request, activation):
    if (activation.installation_id != request.installation_id
            or activation.deployment_id != request.model_deployment_id):
        raise ImpactTaskUnavailable()
    tenant = _namespace(db)
    plugin = AgentPluginInstallation
    model = AgentModelDeployment
    # Serialize requests for the same installation before locking report or
    # employee rows. No current runtime can turn this blocked task into a run.
    installation_row = (await db.execute(select(plugin.plugin_key, plugin.plugin_version, plugin.credential_epoch,
        plugin.enabled).where(plugin.installation_id == activation.installation_id).with_for_update())).one_or_none()
    deployment_row = (await db.execute(select(model.version, model.config_hmac, model.tenant_generation,
        model.enabled, model.executor_pins["profile"].astext)
        .where(model.deployment_id == activation.deployment_id).with_for_update())).one_or_none()
    if (installation_row is None or tuple(installation_row) != (
            R7_PLUGIN_KEY, activation.plugin_version, activation.credential_epoch, True)
            or deployment_row is None or tuple(deployment_row) != (
                activation.deployment_version, activation.deployment_config_hmac, tenant.generation, True,
                R7_PROFILE)):
        raise ImpactTaskUnavailable()


async def _lock_business_sources(db, request, scope, capa):
    report = CAPAEightD
    target = await visible_fmea_source(db, scope, request.fmea_id)
    if (target.factory_id, target.product_line_code) != (capa.factory_id, capa.product_line_code):
        raise ImpactTaskUnavailable()
    if (await _no_wait(db, select(report.report_id).where(
            report.report_id == capa.report_id, report.factory_id == capa.factory_id,
            report.product_line_code == capa.product_line_code))).scalar_one_or_none() is None:
        raise ImpactTaskUnavailable()
    sources = {ref.object_id for ref in capa.sources if ref.module == "fmea"} | {request.fmea_id}
    for fmea_id in sorted(sources):
        if (await _no_wait(db, select(FMEADocument.fmea_id).where(
                FMEADocument.fmea_id == fmea_id))).scalar_one_or_none() is None:
            raise ImpactTaskUnavailable()
    await lock_employee_acl(db, (scope.user.user_id,))


async def _preflight_task(db, scope, request, activation):
    # CAPA owns both the formal material and its complete inherited source set.
    initial = (await read_material(db, scope, request.report_id)).binding
    await _lock_activation(db, request, activation)
    # Predecessor history locks its task/run before document and employee rows.
    await _authorize_previous_result(db, scope, request)
    await _lock_business_sources(db, request, scope, initial)
    current = (await read_material(db, scope, request.report_id, expected=initial)).binding
    target = await read_approved_target(db, scope, request.fmea_id, factory_id=current.factory_id,
        product_line_code=current.product_line_code, expected_version_id=request.approved_version_id)
    await read_approved_snapshot(db, scope, request.fmea_id, factory_id=current.factory_id,
        product_line_code=current.product_line_code, expected_version_id=target.version_id)
    if await _controlled_activation(db, scope, request) != activation:
        raise ImpactTaskUnavailable()
    return ImpactTaskBinding(capa=current, target=ImpactTargetBinding(fmea_id=target.fmea_id,
        approved_version_id=target.version_id, major_no=target.major_no, snapshot_hash=target.sha256_hash,
        scope_generation=target.scope_generation), activation=activation, previous_result_id=request.previous_result_id)


def _stamp(task_id, actor_id, request_key, payload):
    return _digest(_BINDING_DOMAIN, dict(task_id=str(task_id), actor_id=str(actor_id),
        request_key=request_key, binding=payload))


async def load_binding(db, task_id: UUID) -> ImpactTaskBinding:
    """Check stored immutable server bindings. Callers still owe live authorization."""
    await require_business_namespace(db)
    tenant = _namespace(db)
    row = await db.get(AgentPfmeaImpactBinding, task_id, populate_existing=True)
    task = await db.get(AgentTask, task_id, populate_existing=True)
    if row is None or task is None:
        raise ImpactTaskUnavailable()
    try:
        binding = ImpactTaskBinding.model_validate(row.binding)
    except ValidationError:
        raise ImpactTaskUnavailable() from None
    if (not hmac.compare_digest(row.binding_digest, _stamp(task_id, row.actor_id, row.request_key, row.binding))
            or (binding.capa.tenant_id, binding.capa.tenant_generation) != (tenant.tenant_id, tenant.generation)
            or (task.initiator_id, task.executor_user_id, task.request_key) !=
            (row.actor_id, row.actor_id, row.request_key)
            or (task.target_capa_id, task.factory_id, task.preferred_installation_id) !=
            (binding.capa.report_id, binding.capa.factory_id, binding.activation.installation_id)):
        raise ImpactTaskUnavailable()
    return binding


async def _existing(db, scope, request, binding):
    actor_id = scope.user.user_id
    task = await db.scalar(select(AgentTask).where(
        AgentTask.initiator_id == actor_id, AgentTask.request_key == request.request_key,
    ).execution_options(populate_existing=True))
    if task is None:
        return None
    # An older profile may share the generic task request-key namespace.
    previous = await load_binding(db, task.task_id)
    if previous != binding:
        # Current requested material was authorized above; also authorize the
        # old material before reporting that the same key was used for it.
        await authorize_history(db, scope, previous.capa)
        old_target = await visible_fmea_source(db, scope, previous.target.fmea_id)
        if (old_target.factory_id, old_target.product_line_code) != (
            previous.capa.factory_id, previous.capa.product_line_code,
        ):
            raise ImpactTaskUnavailable()
        old_generation = await db.scalar(select(FMEADocument.r7_scope_generation).where(
            FMEADocument.fmea_id == previous.target.fmea_id))
        if old_generation != previous.target.scope_generation:
            raise ImpactTaskUnavailable()
        raise ImpactTaskConflict("Request key already used")
    return ImpactTaskReceipt(task.task_id, replayed=True)


async def create_task(db: AsyncSession, scope: RequestScope, request: ImpactTaskRequest) -> ImpactTaskReceipt:
    """Create or replay an immutable binding without enabling the old runtime."""
    try:
        activation = await _controlled_activation(db, scope, request)
        with db.no_autoflush:
            binding = await _preflight_task(db, scope, request, activation)
            actor_id = scope.user.user_id
            existing = await _existing(db, scope, request, binding)
        if existing is not None:
            return existing
        task_id = uuid4()
        task = AgentTask(task_id=task_id, initiator_id=actor_id, executor_user_id=actor_id,
            preferred_installation_id=activation.installation_id, target_capa_id=binding.capa.report_id,
            factory_id=binding.capa.factory_id, request_key=request.request_key, status="blocked_capability")
        payload = binding.model_dump(mode="json")
        await db.flush()
        try:
            async with db.begin_nested():
                db.add(task)
                await db.flush()
                db.add(AgentPfmeaImpactBinding(task_id=task_id, actor_id=actor_id, request_key=request.request_key,
                    binding=payload, binding_digest=_stamp(task_id, actor_id, request.request_key, payload)))
                db.add(AuditLog(table_name="agent_tasks", record_id=task_id, action="CREATE_PFMEA_IMPACT_TASK",
                    operated_by=actor_id, factory_id=binding.capa.factory_id,
                    changed_fields={"report_id": str(binding.capa.report_id), "fmea_id": str(binding.target.fmea_id),
                                    "approved_version_id": str(binding.target.approved_version_id)}))
                await db.flush()
        except IntegrityError as exc:
            driver_error = exc.orig.__cause__
            if (getattr(exc.orig, "sqlstate", None) != "23505"
                    or getattr(driver_error, "constraint_name", None) != "uq_agent_task_initiator_request"):
                raise
            checked = await _preflight_task(db, scope, request, activation)
            existing = await _existing(db, scope, request, checked)
            if existing is None:
                raise
            return existing
        await db.commit()
        return ImpactTaskReceipt(task_id, replayed=False)
    except (PermissionError, LookupError, ControlFenceBusy):
        raise ImpactTaskUnavailable() from None
