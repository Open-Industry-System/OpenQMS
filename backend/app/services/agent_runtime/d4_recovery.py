"""Control-only recovery positions; never derives delivery authority."""
from uuid import uuid4

from sqlalchemy import case, func, select

from app.core.tenant_transaction import TenantBinding
from app.models.agent_d4_recovery import D4RecoveryCheckpoint, D4RecoveryRestart
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_readonly_control import AgentTaskUpdate
from app.models.agent_task import AgentRun, AgentTask, AgentTaskGrant, AgentTaskMessage
from app.models.agent_task_request import AgentTaskSourceRequest
from app.models.audit import AuditLog
from app.schemas.agent_d4_recovery import D4RecoveryView
from app.services.agent_runtime import task_service, task_updates
from app.services.agent_runtime.deployment_profiles import TEXT_CAPABILITY
from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
from app.services.agent_runtime.task_controls import _current_run, _run_binding, _task_binding, _user_authority


def _generation(db):
    binding = db.info.get('tenant_binding')
    if not isinstance(binding, TenantBinding) or binding.mode != 'business':
        raise PermissionError('Recovery unavailable')
    return binding.generation


async def recovery_grant(db, task, run):
    """Classify an existing text task without using current plugin authority."""
    with db.no_autoflush:
        request = await db.scalar(select(AgentTaskSourceRequest).where(
            AgentTaskSourceRequest.task_id == task.task_id).execution_options(populate_existing=True))
        grants = list((await db.scalars(select(AgentTaskGrant).where(
            AgentTaskGrant.task_id == task.task_id,
            AgentTaskGrant.capability_id == TEXT_CAPABILITY).limit(2).execution_options(populate_existing=True))).all())
    if (request is None or request.fingerprint_format != 'd4-source-request.v1'
            or len(grants) != 1 or run is None or run.task_id != task.task_id
            or run.installation_id != task.preferred_installation_id):
        raise PermissionError('Recovery unavailable')
    return grants[0]


async def is_text_task(db, task):
    """Any persisted text identity is enough to forbid metadata fallback.

    A text task with a missing request row or grant is corrupt, not metadata.
    Full text classification and authorization remain in recovery_grant.
    """
    from app.services.agent_runtime.local_d4_text_policy import TEXT_PLUGIN_KEY
    with db.no_autoflush:
        request_id = await db.scalar(select(AgentTaskSourceRequest.task_id).where(
            AgentTaskSourceRequest.task_id == task.task_id))
        grant_id = await db.scalar(select(AgentTaskGrant.grant_id).where(
            AgentTaskGrant.task_id == task.task_id, AgentTaskGrant.capability_id == TEXT_CAPABILITY).limit(1))
        plugin_key = await db.scalar(select(AgentPluginInstallation.plugin_key).where(
            AgentPluginInstallation.installation_id == task.preferred_installation_id))
    if plugin_key is None:
        raise PermissionError('Recovery unavailable')
    return request_id is not None or grant_id is not None or plugin_key == TEXT_PLUGIN_KEY


async def validate_message_position(db, task_id, watermark):
    """Inspect only bounded aggregates and one candidate, never message content."""
    m = AgentTaskMessage
    bad = ((m.content != START_MESSAGE) | (m.sensitivity != 'restricted') |
        case((m.sequence <= watermark, m.state != 'accepted'),
             else_=~m.state.in_(['queued', 'claimed'])))
    with db.no_autoflush:
        count, low, high, invalid, after = (await db.execute(select(
            func.count(), func.min(m.sequence), func.max(m.sequence),
            func.count().filter(bad), func.count().filter(m.sequence > watermark)
        ).where(m.task_id == task_id))).one()
        candidate = (await db.execute(select(m.message_id, m.sequence, m.state,
            m.delivery_batch_id, m.delivery_epoch).where(m.task_id == task_id,
            m.sequence > watermark).limit(2))).all()
    if (watermark < 0 or invalid or count not in (watermark, watermark + 1)
            or after > 1 or (count and (low != 1 or high != count))
            or len(candidate) != after or (candidate and candidate[0].sequence != watermark + 1)):
        raise ValueError('Recovery position unavailable')
    if candidate:
        row = candidate[0]
        if ((row.state == 'queued' and (row.delivery_batch_id is not None or row.delivery_epoch is not None))
                or (row.state == 'claimed' and (row.delivery_batch_id is None or row.delivery_epoch is None))):
            raise ValueError('Recovery position unavailable')
    return tuple(candidate[0]) if candidate else None


def _view(row):
    return D4RecoveryView.model_validate(row).model_dump(mode='json')


async def _owned(db, scope, task_id):
    try:
        return await task_service.get_task_for_view(db, scope, task_id)
    except LookupError:
        raise PermissionError('Recovery unavailable') from None


async def _fresh_authority(db, scope, task_id, task_binding, run_binding):
    try:
        return await _user_authority(db, scope, task_id, task_binding, run_binding)
    except LookupError:
        raise PermissionError('Recovery unavailable') from None


async def create_checkpoint(db, scope, task_id, run_id, expected_epoch):
    task = await _owned(db, scope, task_id)
    run = await _current_run(db, task_id)
    task_binding, run_binding = _task_binding(task), _run_binding(run)
    generation = _generation(db)
    with db.no_autoflush:
        installation = await db.scalar(select(AgentPluginInstallation.installation_id).where(
            AgentPluginInstallation.installation_id == task.preferred_installation_id).with_for_update())
        await db.scalar(select(AgentTask).where(AgentTask.task_id == task_id).with_for_update())
        if run is not None:
            await db.scalar(select(AgentRun).where(AgentRun.run_id == run.run_id).with_for_update())
    if installation is None:
        raise PermissionError('Recovery unavailable')
    task, run = await _fresh_authority(db, scope, task_id, task_binding, run_binding)
    if (run is None or run.run_id != run_id or task.status != 'paused' or run.status != 'paused'
            or run.lease_epoch != expected_epoch):
        raise ValueError('Recovery position unavailable')
    grant = await recovery_grant(db, task, run)
    watermark = run.accepted_message_seq
    position = await validate_message_position(db, task_id, watermark)
    with db.no_autoflush:
        existing = await db.scalar(select(D4RecoveryCheckpoint).where(
            D4RecoveryCheckpoint.task_id == task_id, D4RecoveryCheckpoint.run_id == run_id,
            D4RecoveryCheckpoint.lease_epoch == expected_epoch).execution_options(populate_existing=True))
    task, run = await _fresh_authority(db, scope, task_id, task_binding, run_binding)
    if (run is None or task.status != 'paused' or run.status != 'paused'
            or run.lease_epoch != expected_epoch or run.accepted_message_seq != watermark
            or _generation(db) != generation or await validate_message_position(db, task_id, watermark) != position):
        raise ValueError('Recovery position unavailable')
    current_grant = await recovery_grant(db, task, run)
    if current_grant.grant_id != grant.grant_id:
        raise PermissionError('Recovery unavailable')
    task, run = await _fresh_authority(db, scope, task_id, task_binding, run_binding)
    if (run is None or task.status != 'paused' or run.status != 'paused'
            or run.lease_epoch != expected_epoch or run.accepted_message_seq != watermark
            or _generation(db) != generation):
        raise ValueError('Recovery position unavailable')
    if existing is not None:
        if (existing.task_grant_id != grant.grant_id or existing.tenant_generation != generation
                or existing.accepted_message_seq != watermark):
            raise PermissionError('Recovery unavailable')
        result = await get_checkpoint(db, scope, task_id, existing.checkpoint_id)
        await db.commit()
        return result
    identifier = uuid4()
    try:
        pointer = await task_updates.append_update(db, task_id=task_id, kind='checkpoint', object_id=identifier)
        row = D4RecoveryCheckpoint(checkpoint_id=identifier, task_id=task_id, run_id=run_id,
            task_grant_id=grant.grant_id, tenant_generation=generation, lease_epoch=expected_epoch,
            accepted_message_seq=watermark, update_sequence=pointer.sequence,
            protocol='d4-recovery.v1', resume_position='restart_from_start', created_by=scope.user.user_id)
        db.add(row)
        await db.flush()
        db.add(AuditLog(table_name='agent_d4_recovery_checkpoints', record_id=identifier,
            action='SAVE_AGENT_D4_RECOVERY_CHECKPOINT', operated_by=scope.user.user_id,
            factory_id=task.factory_id, correlation_id=run_id, changed_fields={
                'checkpoint_id': str(identifier), 'task_id': str(task_id), 'run_id': str(run_id),
                'lease_epoch': expected_epoch, 'accepted_message_seq': watermark}))
        await db.flush()
        if await validate_message_position(db, task_id, watermark) != position:
            raise ValueError('Recovery position unavailable')
        task, run = await _fresh_authority(db, scope, task_id, task_binding, run_binding)
        if (run is None or task.status != 'paused' or run.status != 'paused'
                or run.lease_epoch != expected_epoch or run.accepted_message_seq != watermark
                or _generation(db) != generation):
            raise ValueError('Recovery position unavailable')
        result = _view(row)
        await db.commit()
        return result
    except Exception:
        await db.rollback()
        raise


async def get_checkpoint(db, scope, task_id, checkpoint_id):
    task = await _owned(db, scope, task_id)
    binding = _task_binding(task)
    with db.no_autoflush:
        row = await db.scalar(select(D4RecoveryCheckpoint).where(
            D4RecoveryCheckpoint.task_id == task_id, D4RecoveryCheckpoint.checkpoint_id == checkpoint_id)
            .execution_options(populate_existing=True))
        if row is None:
            raise LookupError('Checkpoint not found')
        run = await db.scalar(select(AgentRun).where(AgentRun.run_id == row.run_id)
            .execution_options(populate_existing=True))
        pointer = await db.scalar(select(AgentTaskUpdate).where(AgentTaskUpdate.task_id == task_id,
            AgentTaskUpdate.kind == 'checkpoint', AgentTaskUpdate.sequence == row.update_sequence,
            AgentTaskUpdate.object_id == checkpoint_id))
    grant = await recovery_grant(db, task, run)
    if (pointer is None or grant.grant_id != row.task_grant_id or row.tenant_generation != _generation(db)):
        raise PermissionError('Recovery unavailable')
    result = _view(row)
    task = await _owned(db, scope, task_id)
    if _task_binding(task) != binding:
        raise PermissionError('Recovery unavailable')
    with db.no_autoflush:
        current = await db.scalar(select(D4RecoveryCheckpoint).where(
            D4RecoveryCheckpoint.task_id == task_id, D4RecoveryCheckpoint.checkpoint_id == checkpoint_id)
            .execution_options(populate_existing=True))
        pointer = await db.scalar(select(AgentTaskUpdate).where(AgentTaskUpdate.task_id == task_id,
            AgentTaskUpdate.kind == 'checkpoint', AgentTaskUpdate.sequence == row.update_sequence,
            AgentTaskUpdate.object_id == checkpoint_id))
        run = await db.scalar(select(AgentRun).where(AgentRun.run_id == row.run_id)
            .execution_options(populate_existing=True))
    if (current is None or pointer is None or _view(current) != result
            or (await recovery_grant(db, task, run)).grant_id != current.task_grant_id
            or current.tenant_generation != _generation(db)):
        raise PermissionError('Recovery unavailable')
    task = await _owned(db, scope, task_id)
    if _task_binding(task) != binding:
        raise PermissionError('Recovery unavailable')
    return result


async def require_restart_position(db, scope, task, run, checkpoint_id):
    """Validate the typed position against the currently paused run."""
    await get_checkpoint(db, scope, task.task_id, checkpoint_id)
    with db.no_autoflush:
        row = await db.scalar(select(D4RecoveryCheckpoint).where(
            D4RecoveryCheckpoint.checkpoint_id == checkpoint_id,
            D4RecoveryCheckpoint.task_id == task.task_id).execution_options(populate_existing=True))
    grant = await recovery_grant(db, task, run)
    if (row is None or run is None or row.run_id != run.run_id
            or row.lease_epoch != run.lease_epoch or row.tenant_generation != _generation(db)
            or row.task_grant_id != grant.grant_id or row.accepted_message_seq != run.accepted_message_seq):
        raise PermissionError('Recovery unavailable')
    position = await validate_message_position(db, task.task_id, row.accepted_message_seq)
    return row, position


async def authorization_snapshot(db, task, installation):
    """One PostgreSQL snapshot of proof, parent grants and derived scopes."""
    from sqlalchemy import text
    query = text("""
        SELECT
          COALESCE((SELECT jsonb_agg(to_jsonb(p) ORDER BY p.grant_id) FROM (
            SELECT g.grant_id, g.enabled, g.factory_ids, g.object_ids, g.product_line_codes,
              g.expires_at, s.scope_id, s.target_report_id, s.derived_projection_id,
              s.source_module, s.source_projection_id, s.fmea_id, s.cause_node_id
            FROM agent_plugin_grants g LEFT JOIN agent_plugin_derived_source_scopes s ON s.plugin_grant_id=g.grant_id
            WHERE g.installation_id=:installation AND g.capability_id=:capability) p), '[]'::jsonb),
          COALESCE((SELECT jsonb_agg(to_jsonb(t) ORDER BY t.grant_id) FROM (
            SELECT g.grant_id, g.factory_ids, g.object_ids, g.product_line_codes, g.expires_at, g.access_kind,
              s.scope_id, s.target_report_id, s.derived_projection_id, s.source_module,
              s.source_projection_id, s.fmea_id, s.cause_node_id, b.plugin_grant_id
            FROM agent_task_grants g LEFT JOIN agent_task_derived_source_scopes s ON s.task_grant_id=g.grant_id
              LEFT JOIN agent_d4_task_parent_grants b ON b.task_grant_id=g.grant_id
            WHERE g.task_id=:task AND g.capability_id=:capability) t), '[]'::jsonb),
          COALESCE((SELECT jsonb_agg(to_jsonb(r) ORDER BY r.proof_id) FROM (
            SELECT proof_id, revision_id, verification_id, verification_version, fmea_id, cause_node_id
            FROM capa_d4_root_cause_source_proofs WHERE report_id=:report AND status='active'
              AND invalidated_at IS NULL) r), '[]'::jsonb)
    """)
    with db.no_autoflush:
        return tuple((await db.execute(query, {'installation': installation.installation_id,
            'task': task.task_id, 'report': task.target_capa_id, 'capability': TEXT_CAPABILITY})).one())


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
            or checkpoint.tenant_generation != _generation(db)
            or control.task_id != task.task_id or control.action != 'restart'
            or control.run_id != old_run.run_id or control.resulting_run_id != run.run_id
            or control.expected_epoch != checkpoint.lease_epoch or old_run.lease_epoch != checkpoint.lease_epoch + 1
            or control.checkpoint_id is not None or message.task_id != task.task_id
            or message.sequence != checkpoint.accepted_message_seq + 1
            or not message.fixed_content or message.sensitivity != 'restricted'
            or run.accepted_message_seq < checkpoint.accepted_message_seq
            or accepted_count != run.accepted_message_seq
            or (accepted_count and (accepted_min != 1 or accepted_max != run.accepted_message_seq))
            or (run.status != 'stopped' and later_accepted != 0)
            or (message.state == 'accepted') != (message.sequence <= run.accepted_message_seq)
            or (await recovery_grant(db, task, old_run)).grant_id != checkpoint.task_grant_id):
        raise PermissionError('Recovery unavailable')
    return link
