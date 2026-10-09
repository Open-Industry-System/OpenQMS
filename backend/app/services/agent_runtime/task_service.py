"""Durable target-bound task creation; this service never dispatches a run."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.agent_task import AgentRun, AgentTask, AgentTaskGrant, AgentTaskMessage
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.schemas.agent_plugin import PluginManifest
from app.schemas.agent_task import TaskCreate
from app.services.agent.permissions.access import authorize
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import AccessAttempt, ApprovalFloor, Grant
from app.services.capa_current_access import require_business_namespace, current_capa_access, capa_target_filters
from app.services.agent_runtime import task_updates
from app.services.agent_runtime.trial_policy import EMPTY_POLICY, select_admission

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
        capa = await db.scalar(_target_filters(select(CAPAEightD)
            .where(CAPAEightD.report_id == report_id), factories, lines)
            .execution_options(populate_existing=True))
    if capa is None:
        raise LookupError("8D report not found")
    return capa


async def require_current_capa_view(db: AsyncSession, scope: RequestScope,
                                    report_id: UUID) -> CAPAEightD:
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
    return select_admission(db.info.get("agent_local_trial_policy", EMPTY_POLICY),
        binding=db.info.get("tenant_binding"), installation=installation,
        executor_user_id=executor_user_id, report_id=target.report_id,
        factory_id=target.factory_id, product_line_code=target.product_line_code, now=datetime.now(UTC))


def _read_grants(task_id, capa, manifest, levels, factories, lines, plugin_grants, *, trial=None):
    """The catalog kernel authorizes each grant against the fixed target."""
    now = datetime.now(UTC)
    profile = "baseline" if trial is None or trial.expires_at <= now else trial.profile
    derived = []
    covered = set()
    declared = set(manifest.required_capabilities + manifest.optional_capabilities)
    for plugin_grant in plugin_grants:
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
            catalog_profile=profile))
        if not decision.allowed or decision.approval_floor != ApprovalFloor.DIRECT:
            continue
        # A task is about one report. Even broad plugin grants produce only the
        # minimum fixed-target read authority; commands are never derived here.
        derived.append(AgentTaskGrant(task_id=task_id, capability_id=spec.id,
            factory_ids=[str(capa.factory_id)], product_line_codes=[capa.product_line_code],
            object_ids=[str(capa.report_id)], access_kind="read", expires_at=plugin_grant.expires_at))
        covered.add(spec.id)
    required = set(manifest.required_capabilities)
    ready = TARGET_SUMMARY in required and required <= covered
    return derived, ready


async def _installation(db, installation_id):
    with db.no_autoflush:
        plugin = await db.scalar(select(AgentPluginInstallation)
            .where(AgentPluginInstallation.installation_id == installation_id)
            .execution_options(populate_existing=True))
    if plugin is None or not plugin.enabled:
        raise PermissionError("Plugin installation unavailable")
    return plugin, PluginManifest.model_validate(plugin.manifest)


async def _existing(db, user_id, request_key, report_id, installation_id, initial_text):
    with db.no_autoflush:
        task = await db.scalar(select(AgentTask).where(AgentTask.initiator_id == user_id,
            AgentTask.request_key == request_key).execution_options(populate_existing=True))
        if task is None:
            return None
        message = await db.scalar(select(AgentTaskMessage.content).where(
            AgentTaskMessage.task_id == task.task_id, AgentTaskMessage.sequence == 1))
    if (task.executor_user_id != user_id or task.target_capa_id != report_id
            or task.preferred_installation_id != installation_id or message != initial_text):
        raise ValueError("Request key reused with different arguments")
    return task


async def create_task(db: AsyncSession, scope: RequestScope, report_id: UUID,
                       installation_id: UUID, request_key: str, initial_text: str) -> AgentTask:
    request = TaskCreate(report_id=report_id, installation_id=installation_id,
        request_key=request_key, initial_text=initial_text)
    levels, factories, lines = await _current_access(db, scope)
    capa = await _target(db, request.report_id, factories, lines)
    plugin, manifest = await _installation(db, request.installation_id)
    existing = await _existing(db, scope.user.user_id, request.request_key,
        request.report_id, request.installation_id, request.initial_text)
    if existing is not None:
        return existing
    with db.no_autoflush:
        plugin_grants = list((await db.scalars(select(AgentPluginGrant)
            .where(AgentPluginGrant.installation_id == plugin.installation_id)
            .execution_options(populate_existing=True))).all())
    task_id = uuid4()
    trial = trial_for_target(db, plugin, scope.user.user_id, capa)
    grants, ready = _read_grants(task_id, capa, manifest, levels, factories, lines, plugin_grants, trial=trial)
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
            message = AgentTaskMessage(task_id=task_id, author_id=scope.user.user_id,
                sequence=1, content=request.initial_text, sensitivity="restricted",
                state="queued", idempotency_key=request.request_key)
            db.add(message)
            db.add_all(grants)
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
            request.report_id, request.installation_id, request.initial_text)
        if existing is None:
            raise
        return existing
    if trial is not None:
        levels, factories, lines = await _current_access(db, scope)
        current_target = await _target(db, request.report_id, factories, lines)
        current_plugin, _ = await _installation(db, request.installation_id)
        if trial_for_target(db, current_plugin, scope.user.user_id, current_target) != trial:
            raise PermissionError("Trial admission changed")
    await db.commit()
    return task
