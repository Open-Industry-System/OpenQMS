"""Explicit R5 recovery positions. Checkpoints never authorize source/model use.

R5 captures during an ACTIVE epoch; pause fences that epoch by incrementing it.
The original checkpoint and D5 ledger watermark remain immutable thereafter.
"""
from uuid import uuid4
from sqlalchemy import case, func, select
from app.models.agent_task import AgentRun, AgentTask, AgentTaskMessage
from app.models.agent_d4_recovery import D4RecoveryCheckpoint, D4RecoveryRestart
from app.models.agent_d5_command import AgentD5CheckpointPosition, AgentD5Command
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_readonly_control import AgentTaskUpdate
from app.services.agent_runtime import d4_recovery, task_controls, task_updates, model_egress
from app.services.agent_runtime.message_delivery_policy import START_MESSAGE


async def validate_message_position(db, task_id, watermark):
    m = AgentTaskMessage
    with db.no_autoflush:
        count, low, high, invalid = (await db.execute(select(func.count(), func.min(m.sequence), func.max(m.sequence),
            func.count().filter((m.sensitivity != 'restricted') | case(
                (m.sequence <= watermark, m.state != 'accepted'), else_=~m.state.in_(['queued','claimed']))))
            .where(m.task_id == task_id))).one()
        candidate = (await db.execute(select(m.message_id,m.sequence,m.state,m.delivery_batch_id,m.delivery_epoch)
            .where(m.task_id==task_id,m.sequence>watermark).order_by(m.sequence).limit(1))).first()
    if watermark < 0 or watermark > count or invalid or (count and (low != 1 or high != count)):
        raise ValueError('Recovery position unavailable')
    if candidate and ((candidate.state=='queued' and (candidate.delivery_batch_id is not None or candidate.delivery_epoch is not None))
            or (candidate.state=='claimed' and (candidate.delivery_batch_id is None or candidate.delivery_epoch is None))):
        raise ValueError('Recovery position unavailable')
    return tuple(candidate) if candidate else None


async def create_paused_checkpoint(db, scope, task_id, run_id, expected_epoch):
    task=await task_controls.task_service.get_task_for_view(db,scope,task_id)
    run=await task_controls._current_run(db,task_id)
    task_binding,run_binding=task_controls._task_binding(task),task_controls._run_binding(run)
    await db.scalar(select(AgentPluginInstallation.installation_id).where(
        AgentPluginInstallation.installation_id==task.preferred_installation_id).with_for_update())
    await db.scalar(select(AgentTask.task_id).where(AgentTask.task_id==task_id).with_for_update())
    if run is not None:
        await db.scalar(select(AgentRun.run_id).where(AgentRun.run_id==run.run_id).with_for_update())
    from app.services.agent_runtime.control_authority_fence import lock_control_target, lock_employee_acl
    await lock_control_target(db,task)
    await lock_employee_acl(db,(scope.user.user_id,),control_only=True)
    task,run=await task_controls._user_authority(db,scope,task_id,task_binding,run_binding)
    if (run is None or run.run_id!=run_id or task.status!='paused' or run.status!='paused'
            or run.lease_epoch!=expected_epoch):
        raise ValueError('Recovery position unavailable')
    grant=await d4_recovery.recovery_grant(db,task,run)
    await validate_message_position(db,task_id,run.accepted_message_seq)
    # Prefer the original ACTIVE checkpoint. Never recapture its ledger boundary
    # after later commands, never rewrite its epoch to satisfy legacy D4 rules.
    existing=await db.scalar(select(D4RecoveryCheckpoint).where(
        D4RecoveryCheckpoint.task_id==task_id,D4RecoveryCheckpoint.run_id==run_id,
        D4RecoveryCheckpoint.lease_epoch.in_([expected_epoch-1,expected_epoch]))
        .order_by(D4RecoveryCheckpoint.lease_epoch).limit(1).execution_options(populate_existing=True))
    if existing is None:
        key=uuid4()
        pointer=await task_updates.append_update(db,task_id=task_id,kind='checkpoint',object_id=key)
        existing=D4RecoveryCheckpoint(checkpoint_id=key,task_id=task_id,run_id=run_id,task_grant_id=grant.grant_id,
            tenant_generation=d4_recovery._generation(db),lease_epoch=expected_epoch,
            accepted_message_seq=run.accepted_message_seq,update_sequence=pointer.sequence,
            protocol='d4-recovery.v1',resume_position='restart_from_start',created_by=scope.user.user_id)
        db.add(existing); await db.flush()
        maximum=await db.scalar(select(func.max(AgentD5Command.sequence)).where(AgentD5Command.task_id==task_id)) or 0
        db.add(AgentD5CheckpointPosition(checkpoint_id=key,task_id=task_id,watermark=maximum))
        await db.flush()
    position=await db.get(AgentD5CheckpointPosition,existing.checkpoint_id,populate_existing=True)
    if (position is None or position.task_id!=task_id or existing.task_grant_id!=grant.grant_id
            or existing.tenant_generation!=d4_recovery._generation(db)
            or existing.accepted_message_seq>run.accepted_message_seq):
        raise PermissionError('Recovery unavailable')
    result=await d4_recovery.get_checkpoint(db,scope,task_id,existing.checkpoint_id)
    await db.commit()
    return result


async def require_restart_position(db, scope, task, run, checkpoint_id):
    await d4_recovery.get_checkpoint(db,scope,task.task_id,checkpoint_id)
    cp=await db.get(D4RecoveryCheckpoint,checkpoint_id,populate_existing=True)
    ledger=await db.get(AgentD5CheckpointPosition,checkpoint_id,populate_existing=True)
    grant=await d4_recovery.recovery_grant(db,task,run)
    if (cp is None or ledger is None or ledger.task_id!=task.task_id or run is None
            or cp.task_id!=task.task_id or cp.run_id!=run.run_id or cp.task_grant_id!=grant.grant_id
            or cp.lease_epoch > run.lease_epoch
            or cp.tenant_generation!=d4_recovery._generation(db) or cp.accepted_message_seq>run.accepted_message_seq):
        raise PermissionError('Recovery unavailable')
    return cp,await validate_message_position(db,task.task_id,run.accepted_message_seq)


async def restart_mapping(db, task, run):
    """Return a strictly associated recovery mapping for a new run, if any."""
    with db.no_autoflush:
        link = await db.scalar(select(D4RecoveryRestart).where(
            D4RecoveryRestart.new_run_id == run.run_id).execution_options(populate_existing=True))
        if link is None:
            return None
        checkpoint = await db.scalar(select(D4RecoveryCheckpoint).where(
            D4RecoveryCheckpoint.checkpoint_id == link.checkpoint_id).execution_options(populate_existing=True))
        from app.models.agent_readonly_control import AgentTaskControl
        control = await db.scalar(select(AgentTaskControl).where(
            AgentTaskControl.control_id == link.control_id).execution_options(populate_existing=True))
        old_run = await db.scalar(select(AgentRun).where(AgentRun.run_id == link.old_run_id)
            .execution_options(populate_existing=True))
        message = (await db.execute(select(AgentTaskMessage.task_id, AgentTaskMessage.sequence,
            (AgentTaskMessage.content == START_MESSAGE).label('fixed_content'), AgentTaskMessage.sensitivity,
            AgentTaskMessage.state).where(
            AgentTaskMessage.message_id == link.start_message_id))).one_or_none()
        accepted_count, accepted_min, accepted_max, later_accepted = (await db.execute(select(
            func.count().filter(AgentTaskMessage.sequence <= run.accepted_message_seq),
            func.min(AgentTaskMessage.sequence).filter(AgentTaskMessage.sequence <= run.accepted_message_seq),
            func.max(AgentTaskMessage.sequence).filter(AgentTaskMessage.sequence <= run.accepted_message_seq),
            func.count().filter(AgentTaskMessage.sequence > run.accepted_message_seq)).where(
            AgentTaskMessage.task_id == task.task_id, AgentTaskMessage.state == 'accepted'))).one()
        pointer = None if checkpoint is None else await db.scalar(select(AgentTaskUpdate.update_id).where(
            AgentTaskUpdate.task_id == task.task_id, AgentTaskUpdate.kind == 'checkpoint',
            AgentTaskUpdate.sequence == checkpoint.update_sequence,
            AgentTaskUpdate.object_id == checkpoint.checkpoint_id))
        controls = list((await db.scalars(select(AgentTaskUpdate.update_id).where(
            AgentTaskUpdate.task_id == task.task_id, AgentTaskUpdate.kind == 'control',
            AgentTaskUpdate.object_id == link.control_id).limit(2))).all())
    if (checkpoint is None or control is None or old_run is None or message is None or pointer is None
            or len(controls) != 1
            or run.resume_checkpoint_id is not None or link.task_id != task.task_id
            or run.task_id != task.task_id or old_run.task_id != task.task_id
            or old_run.installation_id != run.installation_id or run.installation_id != task.preferred_installation_id
            or old_run.plugin_version != run.plugin_version or old_run.status != 'stopped'
            or checkpoint.task_id != task.task_id or checkpoint.run_id != old_run.run_id
            or checkpoint.tenant_generation != d4_recovery._generation(db)
            or control.task_id != task.task_id or control.action != 'restart'
            or control.run_id != old_run.run_id or control.resulting_run_id != run.run_id
            or control.expected_epoch < checkpoint.lease_epoch or old_run.lease_epoch != control.expected_epoch + 1
            or control.checkpoint_id is not None or message.task_id != task.task_id
            or message.sequence != old_run.accepted_message_seq + 1
            or message.sensitivity != 'restricted'
            or checkpoint.accepted_message_seq > old_run.accepted_message_seq or run.accepted_message_seq < old_run.accepted_message_seq
            or accepted_count != run.accepted_message_seq
            or (accepted_count and (accepted_min != 1 or accepted_max != run.accepted_message_seq))
            or (run.status != 'stopped' and later_accepted != 0)
            or (message.state == 'accepted') != (message.sequence <= run.accepted_message_seq)
            or (await d4_recovery.recovery_grant(db, task, old_run)).grant_id != checkpoint.task_grant_id):
        raise PermissionError('Recovery unavailable')
    ledger = await db.get(AgentD5CheckpointPosition, checkpoint.checkpoint_id, populate_existing=True)
    if ledger is None or ledger.task_id != task.task_id:
        raise PermissionError('Recovery unavailable')
    return link
