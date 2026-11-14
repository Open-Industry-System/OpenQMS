"""Durable target-bound task creation; this service never dispatches a run."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.config import settings
from app.core.tenant_transaction import TenantBinding
from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.agent_task import AgentRun, AgentTask, AgentTaskGrant, AgentTaskMessage
from app.models.agent_task_request import AgentTaskSourceRequest
from app.models.agent_d4_recovery import D4TaskParentGrant
from app.models.agent_derived_source import AgentPluginDerivedSourceScope, AgentTaskDerivedSourceScope
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.schemas.agent_plugin import PluginManifest
from app.schemas.agent_task import TaskCreate
from app.services.agent.permissions.access import authorize
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import AccessAttempt, ApprovalFloor, Grant
from app.services.capa_current_access import require_business_namespace, current_capa_access, capa_target_filters
from app.services.agent_runtime import task_updates
from app.services.agent_runtime.deployment_profiles import select_runtime_admission
from app.services.agent_runtime.deployment_profiles import PROFILES
from app.services.agent_runtime.local_d4_text_policy import TEXT_PLUGIN_KEY
from app.services.agent_runtime.derived_source_grants import (matches_request_fingerprint,
    request_source_fingerprint, validate_explicit_source, current_source_for_target, scope_from_row)

TARGET_SUMMARY = "capa.d4.summary.masked.v1"


async def _require_namespace(db: AsyncSession) -> None:
    await require_business_namespace(db)


async def _current_access(db: AsyncSession, scope: RequestScope):
    return await current_capa_access(db, scope)


def _target_filters(query, factories, lines):
    # Fixed targets use the current full scope, not the UI-selected factory.
    return capa_target_filters(query, factories, lines)


async def _target(db, report_id, factories, lines):
    with db.no_autoflush:
        capa = (await db.execute(_target_filters(select(CAPAEightD.report_id, CAPAEightD.factory_id,
            CAPAEightD.product_line_code, CAPAEightD.fmea_ref_id)
            .where(CAPAEightD.report_id == report_id), factories, lines))).one_or_none()
    if capa is None:
        raise LookupError("8D report not found")
    return capa


async def require_current_capa_view(db: AsyncSession, scope: RequestScope,
                                    report_id: UUID):
    _, factories, lines = await _current_access(db, scope)
    return await _target(db, report_id, factories, lines)


async def get_task_for_view(db: AsyncSession, scope: RequestScope, task_id: UUID) -> AgentTask:
    _, factories, lines = await _current_access(db, scope)
    with db.no_autoflush:
        task = await db.scalar(select(AgentTask).where(AgentTask.task_id == task_id,
            AgentTask.initiator_id == scope.user.user_id,
            AgentTask.executor_user_id == scope.user.user_id).execution_options(populate_existing=True))
    if task is None:
        raise LookupError("Task not found")
    capa = await _target(db, task.target_capa_id, factories, lines)
    if task.factory_id != capa.factory_id:
        raise LookupError("Task not found")
    return task


async def list_for_initiator(db: AsyncSession, scope: RequestScope, page: int,
                              page_size: int) -> dict:
    if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError("Invalid pagination")
    _, factories, lines = await _current_access(db, scope)
    query = _target_filters(select(AgentTask).join(CAPAEightD,
        (CAPAEightD.report_id == AgentTask.target_capa_id) &
        (CAPAEightD.factory_id == AgentTask.factory_id))
        .where(AgentTask.initiator_id == scope.user.user_id,
            AgentTask.executor_user_id == scope.user.user_id), factories, lines)
    with db.no_autoflush:
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        items = list((await db.scalars(query.order_by(AgentTask.created_at.desc(), AgentTask.task_id)
            .offset((page - 1) * page_size).limit(page_size)
            .execution_options(populate_existing=True))).all())
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def trial_for_target(db, installation, executor_user_id, target):
    return select_runtime_admission(db, installation, executor_user_id, target, now=datetime.now(UTC))


def _read_grants(task_id, capa, manifest, levels, factories, lines, plugin_grants, *, trial=None,
                 current_source=None, requested_source=None, plugin_source_scopes=None):
    """The catalog kernel authorizes each grant against the fixed target."""
    now = datetime.now(UTC)
    profile = "baseline" if trial is None or trial.expires_at <= now else trial.profile
    derived = []
    covered = set()
    declared = set(manifest.required_capabilities + manifest.optional_capabilities)
    for plugin_grant in sorted(plugin_grants, key=lambda grant: str(grant.grant_id)):
        if (profile == "local_d4_root_cause_text_v1"
                and plugin_grant.capability_id == "capa.d4.root_cause_candidate.masked.v1"
                and plugin_grant.capability_id in covered):
            continue
        spec = get_capability(plugin_grant.capability_id, profile=profile)
        if (plugin_grant.capability_id not in declared or not plugin_grant.enabled
                or spec is None or spec.kind != "context"
                or spec.approval_floor != ApprovalFloor.DIRECT):
            continue
        try:
            grant = Grant(spec.id, frozenset(UUID(value) for value in plugin_grant.factory_ids),
                None if plugin_grant.object_ids is None else frozenset(UUID(value) for value in plugin_grant.object_ids),
                None if plugin_grant.product_line_codes is None else frozenset(plugin_grant.product_line_codes),
                plugin_grant.expires_at)
        except (ValueError, TypeError, AttributeError):
            continue  # malformed persisted metadata is never an effective grant
        pinned = Grant(spec.id, frozenset([capa.factory_id]), frozenset([capa.report_id]),
            frozenset([capa.product_line_code]), plugin_grant.expires_at)
        decision = authorize(AccessAttempt(spec, levels,
            None if factories.accessible_factory_ids is None else frozenset(factories.accessible_factory_ids),
            None if lines.mode == "ALL" else frozenset(lines.codes or []),
            grant, pinned, capa.factory_id, capa.report_id, capa.product_line_code, now,
            identity_bypass_row_level_security=lines.mode == "ALL", catalog_profile=profile,
            current_source=current_source, plugin_source_scope=(plugin_source_scopes or {}).get(plugin_grant.grant_id),
            task_source_scope=requested_source))
        if not decision.allowed or decision.approval_floor != ApprovalFloor.DIRECT:
            continue
        # A task is about one report. Even broad plugin grants produce only the
        # minimum fixed-target read authority; commands are never derived here.
        row = AgentTaskGrant(task_id=task_id, capability_id=spec.id,
            factory_ids=[str(capa.factory_id)], product_line_codes=[capa.product_line_code],
            object_ids=[str(capa.report_id)], access_kind="read", expires_at=plugin_grant.expires_at)
        row._source_scope = requested_source if spec.id == 'capa.d4.root_cause_candidate.masked.v1' else None
        row._parent_grant_id = plugin_grant.grant_id if row._source_scope is not None else None
        derived.append(row)
        covered.add(spec.id)
    required = set(manifest.required_capabilities)
    minimum = PROFILES[profile].required if profile in PROFILES else frozenset({TARGET_SUMMARY})
    ready = minimum <= required and required <= covered
    return derived, ready


async def _installation(db, installation_id):
    with db.no_autoflush:
        plugin = await db.scalar(select(AgentPluginInstallation)
            .where(AgentPluginInstallation.installation_id == installation_id)
            .execution_options(populate_existing=True))
    if plugin is None or not plugin.enabled:
        raise PermissionError("Plugin installation unavailable")
    return plugin, PluginManifest.model_validate(plugin.manifest)


async def _existing(db, user_id, request_key, report_id, installation_id, initial_text, fingerprint=None):
    with db.no_autoflush:
        task = await db.scalar(select(AgentTask).where(AgentTask.initiator_id == user_id,
            AgentTask.request_key == request_key).execution_options(populate_existing=True))
        if task is None:
            return None
        message = await db.scalar(select(AgentTaskMessage.content).where(
            AgentTaskMessage.task_id == task.task_id, AgentTaskMessage.sequence == 1))
        source_request = await db.get(AgentTaskSourceRequest, task.task_id) if fingerprint is not None else None
    if (task.executor_user_id != user_id or task.target_capa_id != report_id
            or task.preferred_installation_id != installation_id or message != initial_text
            or fingerprint is not None and not matches_request_fingerprint(source_request, fingerprint)):
        raise ValueError("Request key reused with different arguments")
    return task


async def create_task(db: AsyncSession, scope: RequestScope, report_id: UUID,
                       installation_id: UUID, request_key: str, initial_text: str,
                       *, derived_source_scope=None) -> AgentTask:
    request = TaskCreate(report_id=report_id, installation_id=installation_id,
        request_key=request_key, initial_text=initial_text, derived_source_scope=derived_source_scope)
    levels, factories, lines = await _current_access(db, scope)
    capa = await _target(db, request.report_id, factories, lines)
    plugin, manifest = await _installation(db, request.installation_id)
    is_text = plugin.plugin_key == TEXT_PLUGIN_KEY
    fingerprint = None
    requested_source = None
    if is_text:
        binding = db.info.get('tenant_binding')
        if not isinstance(binding, TenantBinding) or binding.mode != 'business':
            raise PermissionError('Business namespace unavailable')
        fingerprint = request_source_fingerprint(settings.SECRET_KEY.encode(), binding.tenant_id,
                                                 scope.user.user_id, request)
    elif request.derived_source_scope is not None:
        raise ValueError('Source scope unsupported')
    existing = await _existing(db, scope.user.user_id, request.request_key,
        request.report_id, request.installation_id, request.initial_text, fingerprint)
    if existing is not None:
        return existing
    if is_text and request.derived_source_scope is not None:
        requested_source = await validate_explicit_source(db, scope, capa, request.derived_source_scope)
    with db.no_autoflush:
        plugin_grants = list((await db.scalars(select(AgentPluginGrant)
            .where(AgentPluginGrant.installation_id == plugin.installation_id)
            .execution_options(populate_existing=True))).all())
        source_rows = list((await db.scalars(select(AgentPluginDerivedSourceScope).where(
            AgentPluginDerivedSourceScope.plugin_grant_id.in_([row.grant_id for row in plugin_grants]))
            .execution_options(populate_existing=True))).all()) if is_text else []
    task_id = uuid4()
    trial = trial_for_target(db, plugin, scope.user.user_id, capa)
    current_source = await current_source_for_target(db, scope, capa) if is_text else None
    grants, ready = _read_grants(task_id, capa, manifest, levels, factories, lines, plugin_grants, trial=trial,
        current_source=current_source, requested_source=requested_source,
        plugin_source_scopes={row.plugin_grant_id: scope_from_row(row) for row in source_rows})
    if is_text and not ready:
        grants = [grant for grant in grants if grant.capability_id != 'capa.d4.root_cause_candidate.masked.v1']
    task = AgentTask(task_id=task_id, initiator_id=scope.user.user_id,
        executor_user_id=scope.user.user_id, preferred_installation_id=plugin.installation_id,
        target_capa_id=capa.report_id, factory_id=capa.factory_id,
        request_key=request.request_key, status="ready" if ready else "blocked_capability")
    # Savepoint entry flushes caller writes: unrelated failures must not be
    # mistaken for our idempotency-key race.
    await db.flush()
    try:
        async with db.begin_nested():
            db.add(task)
            await db.flush()
            if fingerprint is not None:
                db.add(AgentTaskSourceRequest(task_id=task_id, request_fingerprint=fingerprint,
                    fingerprint_format='d4-source-request.v1'))
            message = AgentTaskMessage(task_id=task_id, author_id=scope.user.user_id,
                sequence=1, content=request.initial_text, sensitivity="restricted",
                state="queued", idempotency_key=request.request_key)
            db.add(message)
            db.add_all(grants)
            await db.flush()
            for grant in grants:
                source = grant._source_scope
                if source is not None:
                    db.add(D4TaskParentGrant(task_grant_id=grant.grant_id, plugin_grant_id=grant._parent_grant_id))
                    db.add(AgentTaskDerivedSourceScope(task_grant_id=grant.grant_id,
                        target_report_id=source.target_report_id, derived_projection_id=source.derived_projection_id,
                        source_module=source.source_module.value, source_projection_id=source.source_projection_id,
                        fmea_id=source.fmea_id, cause_node_id=source.cause_node_id, actor_id=scope.user.user_id))
            run = None
            if ready:
                run = AgentRun(task_id=task_id, installation_id=plugin.installation_id,
                    plugin_version=plugin.plugin_version, status="pending",
                    lease_epoch=0, accepted_message_seq=0)
                db.add(run)
            db.add(AuditLog(table_name="agent_tasks", record_id=task_id,
                action="CREATE_AGENT_TASK", operated_by=scope.user.user_id,
                factory_id=capa.factory_id, changed_fields={
                    "task_id": str(task_id), "target_capa_id": str(capa.report_id),
                    "installation_id": str(plugin.installation_id), "status": task.status}))
            await db.flush()
            # The inserted Task is exclusively ours until this transaction ends.
            await task_updates.append_update(db, task_id=task_id, kind="message", object_id=message.message_id)
            if run is not None:
                await task_updates.append_update(db, task_id=task_id, kind="run_created", object_id=run.run_id)
    except IntegrityError as exc:
        driver_error = exc.orig.__cause__
        if (getattr(exc.orig, "sqlstate", None) != "23505"
                or getattr(driver_error, "constraint_name", None) != "uq_agent_task_initiator_request"):
            raise
        # The competing transaction has committed by the time its unique insert
        # unblocks ours. Recheck admission after that wait before returning it.
        await require_current_capa_view(db, scope, request.report_id)
        await _installation(db, request.installation_id)
        existing = await _existing(db, scope.user.user_id, request.request_key,
            request.report_id, request.installation_id, request.initial_text, fingerprint)
        if existing is None:
            raise
        return existing
    if trial is not None:
        levels, factories, lines = await _current_access(db, scope)
        current_target = await _target(db, request.report_id, factories, lines)
        current_plugin, _ = await _installation(db, request.installation_id)
        if trial_for_target(db, current_plugin, scope.user.user_id, current_target) != trial:
            raise PermissionError("Trial admission changed")
        if is_text and ready:
            # Re-read the actual P/T rows, current proof and source-owner ACL
            # after every intervening write/await, before publishing ready.
            from app.services.agent_runtime.runtime_access import authorize_task
            await authorize_task(db, task, current_plugin)
    await db.commit()
    return task
