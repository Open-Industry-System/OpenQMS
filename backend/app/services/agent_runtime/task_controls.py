"""User-owned controls and lease-fenced runtime completion, committed atomically."""
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_readonly_control import AgentTaskControl
from app.models.agent_task import AgentRun, AgentTask, AgentTaskMessage
from app.models.audit import AuditLog
from app.schemas.agent_control import RuntimeFinish, RuntimeFinishOut, TaskControl, TaskControlOut
from app.services.agent_runtime import runtime_access, task_service, task_updates
from app.services.agent_runtime.runtime_access import RuntimeIdentity


async def _current_run(db: AsyncSession, task_id: UUID) -> AgentRun | None:
    with db.no_autoflush:
        return await db.scalar(select(AgentRun).where(AgentRun.task_id == task_id)
            .order_by(AgentRun.created_at.desc(), AgentRun.run_id.desc()).limit(1)
            .execution_options(populate_existing=True))


def _task_binding(task: AgentTask) -> tuple:
    return (task.initiator_id, task.executor_user_id, task.preferred_installation_id,
            task.target_capa_id, task.factory_id)


def _run_binding(run: AgentRun | None) -> tuple | None:
    return None if run is None else (run.run_id, run.task_id, run.installation_id)


async def _user_authority(db, scope, task_id, task_binding, run_binding):
    run = await _current_run(db, task_id)
    task = await task_service.get_task_for_view(db, scope, task_id)
    if _task_binding(task) != task_binding or _run_binding(run) != run_binding:
        # Never acquire another INSTALL or TASK after waiting on this Task/Run.
        raise ValueError("Task association changed")
    return task, run


async def _resume_authority(db, task, run, installation):
    if (not installation.enabled or run is None
            or run.installation_id != installation.installation_id
            or run.plugin_version != installation.plugin_version):
        raise PermissionError("Plugin installation unavailable")
    authority = await runtime_access.authorize_task(db, task, installation)
    runtime_access.require_installation_delivery(db.info.get("tenant_binding"), installation,
        "restricted", "raw", controlled_egress=True, trial=authority.trial, delivery_kind='message')
    return authority


def _control_result(operation, task, run):
    return TaskControlOut(control_id=operation.control_id, task_id=task.task_id,
        task_status=task.status, run_id=None if run is None else run.run_id,
        run_status=None if run is None else run.status,
        lease_epoch=None if run is None else run.lease_epoch)


async def _same_control(db, task, previous, request):
    if (previous.action != request.action or previous.run_id != request.run_id
            or previous.expected_epoch != request.expected_epoch):
        return False
    if previous.action == 'restart' and previous.checkpoint_id is None:
        from app.models.agent_d4_recovery import D4RecoveryRestart
        link = await db.scalar(select(D4RecoveryRestart).where(
            D4RecoveryRestart.control_id == previous.control_id,
            D4RecoveryRestart.task_id == task.task_id).execution_options(populate_existing=True))
        return link is not None and link.checkpoint_id == request.checkpoint_id
    return previous.checkpoint_id == request.checkpoint_id


async def control_task(db: AsyncSession, scope: RequestScope, task_id: UUID,
                       body: TaskControl) -> TaskControlOut:
    request = TaskControl.model_validate(body)
    # Namespace and user business access precede any business lock. Identity and
    # relationship snapshots come from fresh rows, never caller-owned ORM facts.
    task = await task_service.get_task_for_view(db, scope, task_id)
    run = await _current_run(db, task_id)
    task_binding, run_binding = _task_binding(task), _run_binding(run)
    installation_id = task.preferred_installation_id
    if run is not None and run.installation_id != installation_id:
        raise ValueError("Run association conflicts")
    with db.no_autoflush:
        installation = await db.scalar(select(AgentPluginInstallation).where(
            AgentPluginInstallation.installation_id == installation_id).with_for_update()
            .execution_options(populate_existing=True))
        if installation is None:
            raise LookupError("Plugin installation not found")
        await db.scalar(select(AgentTask).where(AgentTask.task_id == task_id).with_for_update()
            .execution_options(populate_existing=True))
    # An exact already-committed operation can legitimately have replaced the
    # initial current Run while we waited. Re-admit the current user first, then
    # use the durable original request as retry proof before rebasing that Run.
    task = await task_service.get_task_for_view(db, scope, task_id)
    if _task_binding(task) != task_binding:
        raise ValueError("Task association changed")
    with db.no_autoflush:
        previous = await db.scalar(select(AgentTaskControl).where(
            AgentTaskControl.task_id == task_id, AgentTaskControl.key == request.idempotency_key)
            .execution_options(populate_existing=True))
    if previous is not None:
        if not await _same_control(db, task, previous, request):
            raise ValueError("Control key reused with different arguments")
        run_binding = _run_binding(await _current_run(db, task_id))
    task, run = await _user_authority(db, scope, task_id, task_binding, run_binding)
    if run is not None:
        with db.no_autoflush:
            await db.scalar(select(AgentRun).where(AgentRun.run_id == run.run_id).with_for_update()
                .execution_options(populate_existing=True))
        task, run = await _user_authority(db, scope, task_id, task_binding, run_binding)
    with db.no_autoflush:
        previous = await db.scalar(select(AgentTaskControl).where(
            AgentTaskControl.task_id == task_id, AgentTaskControl.key == request.idempotency_key)
            .execution_options(populate_existing=True))
    # Current user authority is required even on retries. Compare the original
    # request before checking present state/epoch; retries cannot repeat effects.
    if previous is not None:
        if not await _same_control(db, task, previous, request):
            raise ValueError("Control key reused with different arguments")
        task, run = await _user_authority(db, scope, task_id, task_binding, run_binding)
        if previous.action == 'restart' and previous.checkpoint_id is None:
            from app.services.agent_runtime import d4_recovery
            original = await db.scalar(select(AgentRun).where(
                AgentRun.run_id == previous.resulting_run_id).execution_options(populate_existing=True))
            if original is None or await d4_recovery.restart_mapping(db, task, original) is None:
                raise PermissionError('Recovery unavailable')
            task, _ = await _user_authority(db, scope, task_id, task_binding, run_binding)
            result = _control_result(previous, task, original)
        else:
            result = _control_result(previous, task, run)
        await db.commit()
        return result
    if task.status in {"completed", "failed", "cancelled"}:
        raise ValueError("Task closed")
    if run is None:
        if (task.status != "blocked_capability" or request.action != "cancel"
                or request.run_id is not None or request.expected_epoch is not None):
            raise ValueError("Run required")
    elif request.run_id != run.run_id or request.expected_epoch != run.lease_epoch:
        raise ValueError("Run position changed")
    transitions = {
        "pause": ({"ready"}, {"pending", "active"}, "paused", "paused"),
        "resume": ({"paused"}, {"paused"}, "ready", "pending"),
        "restart": ({"paused"}, {"paused"}, "ready", "stopped"),
        "cancel": ({"ready", "paused", "blocked_capability"}, {"pending", "active", "paused"}, "cancelled", "stopped"),
    }
    task_before, run_before, task_after, run_after = transitions[request.action]
    if task.status not in task_before or (run is not None and run.status not in run_before):
        raise ValueError("Control conflicts with current state")
    if task.status == "blocked_capability" and run is not None:
        raise ValueError("Blocked task has a run")
    # Final authority follows all reads, before dirty ORM mutations. Resume adds
    # full canonical grants and actual deployment egress; pause/cancel need only
    # the user's current business authority and work with disabled plugins.
    task, run = await _user_authority(db, scope, task_id, task_binding, run_binding)
    if request.action in {"resume", "restart"}:
        restart_authority = await _resume_authority(db, task, run, installation)
        task, run = await _user_authority(db, scope, task_id, task_binding, run_binding)
        await _resume_authority(db, task, run, installation)
        task, run = await _user_authority(db, scope, task_id, task_binding, run_binding)
    text_restart = False
    position = None
    checkpoint = None
    if request.action == "restart":
        from app.services.agent_runtime import checkpoint_service, d4_recovery
        text_restart = await d4_recovery.is_text_task(db, task)
        if text_restart:
            checkpoint, position = await d4_recovery.require_restart_position(db, scope, task, run, request.checkpoint_id)
        else:
            await checkpoint_service.require_restart_checkpoint(db, scope, task, run, request.checkpoint_id)
        task, run = await _user_authority(db, scope, task_id, task_binding, run_binding)
        await _resume_authority(db, task, run, installation)
        task, run = await _user_authority(db, scope, task_id, task_binding, run_binding)
        if text_restart:
            original_source_authority = await d4_recovery.authorization_snapshot(db, task, installation)
            verified = await _resume_authority(db, task, run, installation)
            if (verified.trial != restart_authority.trial
                    or verified.current_source != restart_authority.current_source
                    or verified.source_grant_pairs != restart_authority.source_grant_pairs
                    or await d4_recovery.authorization_snapshot(db, task, installation) != original_source_authority):
                raise PermissionError('Recovery unavailable')
    operation = AgentTaskControl(control_id=uuid4(), task_id=task_id,
        run_id=request.run_id, expected_epoch=request.expected_epoch,
        key=request.idempotency_key, action=request.action, checkpoint_id=None if text_restart else request.checkpoint_id,
        resulting_run_id=None if run is None else run.run_id)
    try:
        task.status = task_after
        if run is not None:
            run.status = run_after
            run.lease_epoch += 1
            run.lease_expires_at = None
            run.claim_key = None
        if request.action == "restart":
            old_run = run
            # Release the old nonterminal unique-index position before inserting
            # its replacement. Both remain in this single task transaction.
            await db.flush()
            run = AgentRun(run_id=uuid4(), task_id=task_id, installation_id=installation.installation_id,
                plugin_version=installation.plugin_version, status="pending", lease_epoch=0,
                claim_key=None, lease_expires_at=None, accepted_message_seq=run.accepted_message_seq,
                resume_checkpoint_id=None if text_restart else request.checkpoint_id)
            db.add(run)
            operation.resulting_run_id = run.run_id
            if text_restart:
                from app.models.agent_d4_recovery import D4RecoveryRestart
                from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
                if await d4_recovery.validate_message_position(db, task_id, checkpoint.accepted_message_seq) != position:
                    raise ValueError('Recovery position unavailable')
                if position:
                    message_id = position[0]
                else:
                    message_id = uuid4()
                    db.add(AgentTaskMessage(message_id=message_id, task_id=task_id,
                        sequence=checkpoint.accepted_message_seq + 1, author_id=scope.user.user_id,
                        content=START_MESSAGE, sensitivity='restricted', state='queued',
                        idempotency_key='d4-restart:' + str(operation.control_id)))
                    await db.flush()
                    await task_updates.append_update(db, task_id=task_id, kind='message', object_id=message_id)
                # The control's resulting_run_id FK must reference an inserted run.
                await db.flush()
                db.add(operation)
                await db.flush()
                db.add(D4RecoveryRestart(control_id=operation.control_id, checkpoint_id=checkpoint.checkpoint_id,
                    task_id=task_id, old_run_id=old_run.run_id, new_run_id=run.run_id, start_message_id=message_id))
        # Redelivery clears only unaccepted proof. Terminal cancellation preserves
        # queued/claimed distinctions and original batch/epoch evidence.
        if request.action in {"pause", "resume", "restart"}:
            await db.execute(update(AgentTaskMessage).where(
                AgentTaskMessage.task_id == task_id, AgentTaskMessage.state != "accepted")
                .values(state="queued", delivery_batch_id=None, delivery_epoch=None))
        db.add(operation)
        db.add(AuditLog(table_name="agent_task_controls", record_id=operation.control_id,
            action="CONTROL_AGENT_TASK", operated_by=scope.user.user_id, factory_id=task.factory_id,
            changed_fields={"control_id": str(operation.control_id), "task_id": str(task_id),
                "run_id": None if request.run_id is None else str(request.run_id),
                "action": request.action,
                "lease_epoch": None if run is None else run.lease_epoch,
                **({"resulting_run_id": str(run.run_id)} if request.action == "restart" else {})}))
        await task_updates.append_update(db, task_id=task_id, kind="control", object_id=operation.control_id)
        if text_restart:
            # Flush all side effects before the last fresh authorization. The
            # caller owns installation/task/run locks; failure rolls all back.
            await db.flush()
            task = await task_service.get_task_for_view(db, scope, task_id)
            if _task_binding(task) != task_binding:
                raise PermissionError('Recovery unavailable')
            installation = await db.scalar(select(AgentPluginInstallation).where(
                AgentPluginInstallation.installation_id == installation_id).execution_options(populate_existing=True))
            if installation is None or not installation.enabled or installation.plugin_version != run.plugin_version:
                raise PermissionError('Recovery unavailable')
            authority = await runtime_access.authorize_task(db, task, installation)
            if authority.trial != restart_authority.trial:
                raise PermissionError('Recovery unavailable')
            if await d4_recovery.restart_mapping(db, task, run) is None:
                raise PermissionError('Recovery unavailable')
            position_now = await d4_recovery.validate_message_position(db, task_id, checkpoint.accepted_message_seq)
            if position_now is None or position_now[0] != message_id:
                raise PermissionError('Recovery unavailable')
            # Re-admit both the user and runtime after the final message read.
            task = await task_service.get_task_for_view(db, scope, task_id)
            if _task_binding(task) != task_binding:
                raise PermissionError('Recovery unavailable')
            final = await runtime_access.authorize_task(db, task, installation)
            if (final.trial != restart_authority.trial or final.current_source != restart_authority.current_source
                    or final.source_grant_pairs != restart_authority.source_grant_pairs):
                raise PermissionError('Recovery unavailable')
            if await d4_recovery.authorization_snapshot(db, task, installation) != original_source_authority:
                raise PermissionError('Recovery unavailable')
            # Roles and business memberships do not share our task lock. A
            # revocation during the final source snapshot must still fail.
            task, current_run = await _user_authority(db, scope, task_id, task_binding, _run_binding(run))
            final = await _resume_authority(db, task, current_run, installation)
            if (final.trial != restart_authority.trial or final.current_source != restart_authority.current_source
                    or final.source_grant_pairs != restart_authority.source_grant_pairs):
                raise PermissionError('Recovery unavailable')
        result = _control_result(operation, task, run)
        await db.commit()
    except Exception:
        # Propagate unknown database/driver failures; never classify them as an
        # idempotency race. Object, pointer, lease and audit share this transaction.
        await db.rollback()
        raise
    return result


async def _require_confirmed_inputs(db: AsyncSession, task_id: UUID, accepted: int) -> None:
    with db.no_autoflush:
        count, first, last, unconfirmed = (await db.execute(select(
            func.count(), func.min(AgentTaskMessage.sequence), func.max(AgentTaskMessage.sequence),
            func.count().filter(AgentTaskMessage.state != "accepted"))
            .where(AgentTaskMessage.task_id == task_id))).one()
    # Task sequence uniqueness plus count/min/max proves the entire contiguous
    # accepted prefix, without reading input content or trusting a cached watermark.
    if (unconfirmed or count != accepted
            or (count and (first != 1 or last != accepted))):
        raise ValueError("Task has unconfirmed or inconsistent inputs")


async def finish_run(db: AsyncSession, identity: RuntimeIdentity, status: str) -> RuntimeFinishOut:
    request = RuntimeFinish(status=status)
    current = await runtime_access.lock_runtime_identity(db, identity)
    # The lock helper refreshes the full runtime identity: active Run, ready Task,
    # actual executor/target/grants, lease and generation. Recheck after reads.
    if request.status == "completed":
        await _require_confirmed_inputs(db, current.task.task_id, current.run.accepted_message_seq)
    current = await runtime_access.refresh_runtime_identity(db, current)
    if request.status == "completed":
        # This last actual-message query occurs after final authority and under
        # TASK FOR UPDATE. ACK means received, and never proves plugin execution.
        await _require_confirmed_inputs(db, current.task.task_id, current.run.accepted_message_seq)
        # User/role/grants do not share TASK's lock. A revocation committed during
        # the last input query must be observed before any terminal writes.
        current = await runtime_access.refresh_runtime_identity(db, current)
    try:
        current.task.status = request.status
        current.run.status = request.status
        current.run.lease_epoch += 1
        current.run.lease_expires_at = None
        current.run.claim_key = None
        fields = {"task_id": str(current.task.task_id), "run_id": str(current.run.run_id),
            "status": request.status, "lease_epoch": current.run.lease_epoch}
        if request.status == "failed":
            fields["failure_code"] = "plugin_failure"
        db.add(AuditLog(table_name="agent_runs", record_id=current.run.run_id,
            action="FINISH_AGENT_RUN", operated_by=current.task.executor_user_id,
            factory_id=current.task.factory_id, changed_fields=fields))
        await task_updates.append_update(db, task_id=current.task.task_id, kind="finish", object_id=current.run.run_id)
        result = RuntimeFinishOut(task_id=current.task.task_id, task_status=current.task.status,
            run_id=current.run.run_id, run_status=current.run.status, lease_epoch=current.run.lease_epoch)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return result
