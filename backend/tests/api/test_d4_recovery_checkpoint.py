"""Employee recovery checkpoints use a separate control-only contract."""
from uuid import uuid4

import httpx
import pytest

from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
from tests.e2e.d4_text_local_harness import d4_text_local_trial, d4_text_server, owned_local_trial

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]


async def test_paused_text_checkpoint_is_idempotent_and_activity_visible(d4_text_server):
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    task_id = task.json()['task_id']
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as runtime:
        claim = await runtime.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        run_id, epoch = claim.json()['run_id'], claim.json()['lease_epoch']
        headers = {'Authorization': 'Bearer ' + c.user_token}
        pause = await runtime.post(f'/api/agent/tasks/{task_id}/control', headers=headers,
            json={'action': 'pause', 'run_id': run_id, 'expected_epoch': epoch, 'idempotency_key': uuid4().hex})
        assert pause.status_code == 200, pause.text
        path = f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints'
        body = {'run_id': run_id, 'expected_epoch': pause.json()['lease_epoch']}
        first = await runtime.post(path, headers=headers, json=body)
        assert first.status_code == 200, first.text
        saved = first.json()
        assert saved['checkpoint_type'] == 'd4_recovery_v1'
        assert saved['resume_position'] == 'restart_from_start'
        assert saved['accepted_message_seq'] == 0
        assert 'task_grant_id' not in saved
        replay = await runtime.post(path, headers=headers, json=body)
        assert replay.status_code == 200 and replay.json() == saved
        read = await runtime.get(path + '/' + saved['checkpoint_id'], headers=headers)
        assert read.status_code == 200 and read.json() == saved
        activity = await runtime.get(f'/api/agent/tasks/{task_id}/activity', headers=headers)
        assert activity.status_code == 200, activity.text
        assert any(item['kind'] == 'checkpoint' and item['data']['checkpoint_id'] == saved['checkpoint_id']
            for item in activity.json()['items'])
        page = await runtime.get(f'/api/agent/tasks/{task_id}/activity', headers=headers, params={'page_size': 1})
        assert page.status_code == 200 and page.json()['items'][0]['kind'] == 'checkpoint'
        previous = await runtime.get(f'/api/agent/tasks/{task_id}/activity', headers=headers, params={
            'page_size': 1, 'before_sequence': page.json()['next_before_sequence'],
            'window_end_sequence': page.json()['window_end_sequence']})
        assert previous.status_code == 200 and previous.json()['items'][0]['sequence'] < page.json()['items'][0]['sequence']
        wrong_epoch = await runtime.post(path, headers=headers,
            json={'run_id': run_id, 'expected_epoch': body['expected_epoch'] + 1})
        assert wrong_epoch.status_code == 409
        wrong_run = await runtime.post(path, headers=headers,
            json={'run_id': str(uuid4()), 'expected_epoch': body['expected_epoch']})
        assert wrong_run.status_code == 409
        assert (await runtime.get(path + '/' + str(uuid4()), headers=headers)).status_code == 404
        assert (await runtime.get(f'/api/agent/tasks/{uuid4()}/d4-recovery-checkpoints/' + saved['checkpoint_id'],
            headers=headers)).status_code == 403
        from sqlalchemy import select
        from app.models.agent_d4_recovery import D4RecoveryCheckpoint
        from app.models.agent_readonly_control import AgentTaskUpdate
        from uuid import UUID
        async with c.session() as db:
            row = await db.get(D4RecoveryCheckpoint, UUID(saved['checkpoint_id']))
            row.tenant_generation += 1
            await db.commit()
        assert (await runtime.get(path + '/' + saved['checkpoint_id'], headers=headers)).status_code == 403
        async with c.session() as db:
            row = await db.get(D4RecoveryCheckpoint, UUID(saved['checkpoint_id']))
            row.tenant_generation -= 1
            pointer = await db.scalar(select(AgentTaskUpdate).where(
                AgentTaskUpdate.object_id == UUID(saved['checkpoint_id']), AgentTaskUpdate.kind == 'checkpoint'))
            pointer.object_id = uuid4()
            await db.commit()
        assert (await runtime.get(f'/api/agent/tasks/{task_id}/activity', headers=headers)).status_code == 403
        # An idempotent POST is still a read of the original position and must
        # not acknowledge a checkpoint with a broken activity association.
        corrupted_retry = await runtime.post(path, headers=headers, json=body)
        assert corrupted_retry.status_code == 403


@pytest.mark.parametrize('task_id,checkpoint_id,body', [
    ('sensitive-task', None, {'run_id': str(uuid4()), 'expected_epoch': 1}),
    (str(uuid4()), None, {'run_id': 'sensitive-run', 'expected_epoch': 1}),
    (str(uuid4()), None, {'run_id': str(uuid4()), 'expected_epoch': 'sensitive-epoch'}),
    (str(uuid4()), None, {'run_id': str(uuid4()), 'expected_epoch': True}),
    (str(uuid4()), None, {'run_id': str(uuid4()), 'expected_epoch': 1, 'sensitive-key': 'sensitive-value'}),
    (str(uuid4()), None, ['sensitive-value']),
    (str(uuid4()), 'sensitive-checkpoint', None),
], ids=['invalid-task', 'invalid-run', 'invalid-epoch', 'boolean-epoch',
        'extra-field', 'invalid-body', 'invalid-checkpoint'])
async def test_recovery_validation_is_locally_redacted(d4_text_server, task_id, checkpoint_id, body):
    c = d4_text_server
    path = f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints'
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        response = (await client.get(path + '/' + checkpoint_id, headers=headers) if checkpoint_id
                    else await client.post(path, headers=headers, json=body))
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid request'}
    assert 'sensitive' not in response.text


@pytest.mark.parametrize('revoked_kind', ['grant', 'plugin', 'policy'])
async def test_checkpoint_after_grant_revocation_is_control_only(d4_text_server, monkeypatch, revoked_kind):
    from sqlalchemy import event
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    task_id = task.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        paused = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': claim.json()['run_id'], 'expected_epoch': claim.json()['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert paused.status_code == 200, paused.text
        if revoked_kind == 'grant':
            revoked = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}', json={'enabled': False})
            assert revoked.status_code == 200, revoked.text
        elif revoked_kind == 'plugin':
            revoked = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}', json={'enabled': False})
            assert revoked.status_code == 200, revoked.text
        else:
            from app.services.agent_runtime.local_d4_text_policy import EMPTY_TEXT_POLICY
            monkeypatch.setattr(c.app.state, 'agent_d4_text_policy', EMPTY_TEXT_POLICY)
        statements = []
        def witness(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            result = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
                json={'run_id': claim.json()['run_id'], 'expected_epoch': paused.json()['lease_epoch']})
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
        assert result.status_code == 200, result.text
        assert not any('d4_root_cause' in s or 'graph_data' in s or 'jsonb_array_elements' in s for s in statements)
        assert all('select agent_task_messages.content' not in s for s in statements if 'select ' in s and ' from agent_task_messages' in s)


async def test_checkpoint_rechecks_control_after_position_read(d4_text_server, monkeypatch):
    from sqlalchemy import func, select, text, update
    from sqlalchemy.exc import DBAPIError
    from app.models.agent_d4_recovery import D4RecoveryCheckpoint
    from app.models.role import RolePermission
    from app.services.agent_runtime import d4_recovery
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    task_id = task.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    original = d4_recovery.validate_message_position
    calls = 0
    async def revoke_after_last_position(*args, **kwargs):
        nonlocal calls
        result = await original(*args, **kwargs)
        calls += 1
        if calls == 2:
            async with c.session() as other:
                await other.execute(text("SET LOCAL lock_timeout = '200ms'"))
                try:
                    await other.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                        RolePermission.module == 'capa').values(permission_level=0))
                    await other.commit()
                except DBAPIError as exc:
                    assert getattr(exc.orig, 'sqlstate', None) == '55P03'
                else:
                    raise AssertionError('concurrent control revocation unexpectedly committed')
            raise RuntimeError('synthetic checkpoint rollback after permission lock conflict')
        return result
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': claim.json()['run_id'], 'expected_epoch': claim.json()['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert pause.status_code == 200, pause.text
        monkeypatch.setattr(d4_recovery, 'validate_message_position', revoke_after_last_position)
        response = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': claim.json()['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        assert response.status_code == 500, response.text
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(D4RecoveryCheckpoint)) == 0


@pytest.mark.parametrize('damage', ['content', 'gap', 'extra'])
async def test_invalid_message_position_rejected_without_loading_content(d4_text_server, damage):
    from uuid import UUID
    from sqlalchemy import event, func, select
    from app.models.agent_d4_recovery import D4RecoveryCheckpoint
    from app.models.agent_task import AgentTaskMessage
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    task_id = task.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': claim.json()['run_id'], 'expected_epoch': claim.json()['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert pause.status_code == 200, pause.text
        async with c.session() as db:
            msg = await db.scalar(select(AgentTaskMessage).where(AgentTaskMessage.task_id == UUID(task_id)))
            if damage == 'content':
                msg.content = 'PRIVATE-MESSAGE-SENTINEL' + 'x' * (512 * 1024)
            elif damage == 'gap':
                msg.sequence = 2
            else:
                db.add(AgentTaskMessage(task_id=UUID(task_id), sequence=2, author_id=c.user_id,
                    content=START_MESSAGE, sensitivity='restricted', state='queued', idempotency_key=uuid4().hex))
            await db.commit()
        statements = []
        def witness(conn, cursor, statement, parameters, context, executemany):
            if 'agent_task_messages' in statement.lower() and statement.lstrip().lower().startswith('select'):
                statements.append(statement.lower())
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            response = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
                json={'run_id': claim.json()['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
        assert response.status_code == 409, response.text
        assert 'PRIVATE-MESSAGE-SENTINEL' not in response.text
        assert statements and all('select agent_task_messages.content' not in s for s in statements)
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(D4RecoveryCheckpoint)) == 0


async def test_large_history_uses_scalar_queries_and_never_falls_back_to_old_checkpoint(d4_text_server):
    from uuid import UUID
    from sqlalchemy import event, select
    from app.models.agent_readonly_control import AgentReadonlyCheckpoint
    from app.models.agent_task import AgentRun, AgentTaskMessage
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    task_id = task.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': claim.json()['run_id'], 'expected_epoch': claim.json()['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert pause.status_code == 200, pause.text
        run_id = UUID(claim.json()['run_id'])
        old_id = uuid4()
        async with c.session() as db:
            first = await db.scalar(select(AgentTaskMessage).where(AgentTaskMessage.task_id == UUID(task_id)))
            first.state, first.delivery_batch_id, first.delivery_epoch = 'accepted', uuid4(), 1
            db.add_all([AgentTaskMessage(task_id=UUID(task_id), sequence=i, author_id=c.user_id,
                content=START_MESSAGE, sensitivity='restricted', state='accepted', delivery_batch_id=uuid4(),
                delivery_epoch=1, idempotency_key=uuid4().hex) for i in range(2, 1001)])
            run = await db.get(AgentRun, run_id)
            run.accepted_message_seq = 1000
            db.add(AgentReadonlyCheckpoint(checkpoint_id=old_id, task_id=UUID(task_id), run_id=run_id,
                key=uuid4().hex, lease_epoch=pause.json()['lease_epoch'], tenant_generation=c.binding.generation,
                accepted_message_seq=1000, update_sequence=99999))
            await db.commit()
        path = f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints'
        missing = await client.get(path + '/' + str(old_id), headers=headers)
        assert missing.status_code == 404
        legacy_reads = []
        def old_witness(conn, cursor, statement, parameters, context, executemany):
            if 'agent_readonly_checkpoints' in statement.lower():
                legacy_reads.append(statement)
        event.listen(c.engine.sync_engine, 'before_cursor_execute', old_witness)
        try:
            legacy = await client.get(f'/api/agent/tasks/{task_id}/checkpoints/{old_id}', headers=headers)
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', old_witness)
        assert legacy.status_code in (403, 404)
        assert not legacy_reads
        statements = []
        def witness(conn, cursor, statement, parameters, context, executemany):
            if 'agent_task_messages' in statement.lower() and statement.lstrip().lower().startswith('select'):
                statements.append(statement.lower())
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            result = await client.post(path, headers=headers,
                json={'run_id': str(run_id), 'expected_epoch': pause.json()['lease_epoch']})
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
        assert result.status_code == 200, result.text
        assert result.json()['accepted_message_seq'] == 1000
        assert statements and all('select agent_task_messages.content' not in s for s in statements)
        assert any('count(' in s and 'max(' in s for s in statements)
        # Even when both types share the same UUID, the server selects the
        # table by trusted task identity rather than trying the other table.
        async with c.session() as db:
            db.add(AgentReadonlyCheckpoint(checkpoint_id=UUID(result.json()['checkpoint_id']),
                task_id=UUID(task_id), run_id=run_id, key=uuid4().hex,
                lease_epoch=pause.json()['lease_epoch'], tenant_generation=c.binding.generation,
                accepted_message_seq=1000, update_sequence=99998))
            await db.commit()
        same_id = await client.get(path + '/' + result.json()['checkpoint_id'], headers=headers)
        assert same_id.status_code == 200 and same_id.json() == result.json()
        from app.models.agent_task_request import AgentTaskSourceRequest
        async with c.session() as db:
            request = await db.get(AgentTaskSourceRequest, UUID(task_id))
            await db.delete(request)
            await db.commit()
        legacy_reads.clear()
        event.listen(c.engine.sync_engine, 'before_cursor_execute', old_witness)
        try:
            corrupt = await client.get(f'/api/agent/tasks/{task_id}/checkpoints/{old_id}', headers=headers)
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', old_witness)
        assert corrupt.status_code in (403, 404)
        assert not legacy_reads


async def test_checkpoint_rechecks_control_after_pointer_flush(d4_text_server, monkeypatch):
    from sqlalchemy import func, select, text, update
    from sqlalchemy.exc import DBAPIError
    from app.models.agent_d4_recovery import D4RecoveryCheckpoint
    from app.models.agent_readonly_control import AgentTaskUpdate
    from app.models.audit import AuditLog
    from app.models.role import RolePermission
    from app.services.agent_runtime import d4_recovery
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    task_id = task.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    original = d4_recovery.task_updates.append_update
    async def revoke_after_pointer(*args, **kwargs):
        result = await original(*args, **kwargs)
        async with c.session() as other:
            await other.execute(text("SET LOCAL lock_timeout = '200ms'"))
            try:
                await other.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                    RolePermission.module == 'capa').values(permission_level=0))
                await other.commit()
            except DBAPIError as exc:
                assert getattr(exc.orig, 'sqlstate', None) == '55P03'
            else:
                raise AssertionError('concurrent control revocation unexpectedly committed')
        raise RuntimeError('synthetic checkpoint rollback after permission lock conflict')
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': claim.json()['run_id'], 'expected_epoch': claim.json()['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert pause.status_code == 200, pause.text
        async with c.session() as db:
            before = (await db.scalar(select(func.count()).select_from(AgentTaskUpdate)),
                      await db.scalar(select(func.count()).select_from(AuditLog)))
        monkeypatch.setattr(d4_recovery.task_updates, 'append_update', revoke_after_pointer)
        response = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': claim.json()['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        assert response.status_code == 500, response.text
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(D4RecoveryCheckpoint)) == 0
            assert (await db.scalar(select(func.count()).select_from(AgentTaskUpdate)),
                    await db.scalar(select(func.count()).select_from(AuditLog))) == before


async def test_blocked_text_task_cancel_does_not_require_checkpoint_type(d4_text_server):
    from uuid import UUID
    from sqlalchemy import func, select
    from app.models.agent_derived_source import AgentTaskDerivedSourceScope
    from app.models.agent_task import AgentRun, AgentTaskGrant
    c = d4_text_server
    revoked = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}', json={'enabled': False})
    assert revoked.status_code == 200, revoked.text
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'blocked_capability', task.text
    task_id = task.json()['task_id']
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        result = await client.post(f'/api/agent/tasks/{task_id}/control',
            headers={'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug},
            json={'action': 'cancel', 'run_id': None, 'expected_epoch': None, 'idempotency_key': uuid4().hex})
    assert result.status_code == 200 and result.json()['task_status'] == 'cancelled', result.text
    async with c.session() as db:
        grants = select(AgentTaskGrant.grant_id).where(AgentTaskGrant.task_id == UUID(task_id))
        assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.task_id == UUID(task_id))) == 0
        assert await db.scalar(select(func.count()).select_from(AgentTaskGrant).where(AgentTaskGrant.task_id == UUID(task_id))) == 0
        assert await db.scalar(select(func.count()).select_from(AgentTaskDerivedSourceScope).where(
            AgentTaskDerivedSourceScope.task_grant_id.in_(grants))) == 0


async def test_activity_checkpoint_rechecks_user_after_materialization(d4_text_server, monkeypatch):
    from sqlalchemy import update
    from app.models.role import RolePermission
    from app.services.agent_runtime import task_reads
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    task_id = task.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': claim.json()['run_id'], 'expected_epoch': claim.json()['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert pause.status_code == 200, pause.text
        checkpoint = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': claim.json()['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        assert checkpoint.status_code == 200, checkpoint.text
        original = task_reads._final_sources
        async def revoke_after_materialization(*args, **kwargs):
            await original(*args, **kwargs)
            async with c.session() as other:
                await other.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                    RolePermission.module == 'capa').values(permission_level=0))
                await other.commit()
        monkeypatch.setattr(task_reads, '_final_sources', revoke_after_materialization)
        result = await client.get(f'/api/agent/tasks/{task_id}/activity', headers=headers)
        assert result.status_code == 403, result.text
        assert checkpoint.json()['checkpoint_id'] not in result.text


async def test_checkpoint_ids_do_not_cross_tenants(d4_text_server):
    import re
    from sqlalchemy import select, text
    from app.core.tenant_transaction import TenantBinding
    from app.models.user import User
    from app.schemas.platform import TenantCreateRequest
    from app.services import tenant_migrator
    from tests.e2e.agent_local_trial_harness import PASSWORD
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    task_id = task.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': claim.json()['run_id'], 'expected_epoch': claim.json()['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert pause.status_code == 200, pause.text
        checkpoint = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': claim.json()['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        assert checkpoint.status_code == 200, checkpoint.text
        slug = 'recovery-isolation-' + uuid4().hex[:12]
        tenant = None
        try:
            tenant = await tenant_migrator.provision_new(TenantCreateRequest(name='Recovery isolation test',
                slug=slug, admin_email='recovery-isolation@example.test', admin_password=PASSWORD))
            binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, 'business')
            async with c.factory(binding=binding) as db:
                admin = await db.scalar(select(User).where(User.email == 'recovery-isolation@example.test'))
                username = admin.username
            login = await client.post('/api/auth/login', headers={'X-Tenant-ID': slug},
                json={'username': username, 'password': PASSWORD})
            assert login.status_code == 200, login.text
            other_headers = {'Authorization': 'Bearer ' + login.json()['access_token'], 'X-Tenant-ID': slug}
            result = await client.get(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints/' +
                checkpoint.json()['checkpoint_id'], headers=other_headers)
            assert result.status_code == 403
            assert checkpoint.json()['checkpoint_id'] not in result.text
        finally:
            if tenant is not None:
                # The only removed schema is the randomly named fixture tenant,
                # after matching both exact generated id and schema from registry.
                assert re.fullmatch(r'tenant_[a-z0-9_]+', tenant.schema_name)
                async with c.engine.begin() as conn:
                    row = (await conn.execute(text('SELECT id, schema_name FROM public.tenants WHERE id=:id AND slug=:slug'),
                        {'id': tenant.id, 'slug': slug})).one_or_none()
                    assert row is not None and row.schema_name == tenant.schema_name
                    await conn.execute(text(f'DROP SCHEMA "{tenant.schema_name}" CASCADE'))
                    await conn.execute(text('DELETE FROM public.tenant_migrations WHERE tenant_id=:id'), {'id': tenant.id})
                    await conn.execute(text('DELETE FROM public.tenants WHERE id=:id'), {'id': tenant.id})


async def test_recovery_validation_does_not_leak_into_real_access_log(d4_text_local_trial):
    import asyncio
    import logging
    import socket
    import uvicorn
    c = d4_text_local_trial
    lines = []
    class Capture(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())
    logger = logging.getLogger('uvicorn.access')
    handler = Capture()
    old_level, old_disabled = logger.level, logger.disabled
    # pytest's logging bootstrap can leave this logger disabled; enable the
    # real server logger explicitly so a silent logger cannot satisfy the test.
    logger.disabled = False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    assert not logger.disabled and logger.isEnabledFor(logging.INFO) and logger.hasHandlers()
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    server = uvicorn.Server(uvicorn.Config(c.app, log_level='info', log_config=None,
        access_log=True, lifespan='off', proxy_headers=False))
    runner = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(300):
            if server.started:
                break
            if runner.done():
                await runner
            await asyncio.sleep(.01)
        assert server.started
        headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}', timeout=15) as client:
            path = '/api/agent/tasks/%53ECRET-PATH-SENTINEL/d4-recovery-checkpoints?token=SECRET-QUERY-SENTINEL'
            first = await client.post(path, headers=headers, json={'run_id': str(uuid4()), 'expected_epoch': 1})
            second = await client.post(f'/api/agent/tasks/{uuid4()}/d4-recovery-checkpoints', headers=headers,
                json={'run_id': str(uuid4()), 'expected_epoch': 1, 'SECRET-KEY-SENTINEL': 'SECRET-VALUE-SENTINEL'})
            third = await client.get('/api/agent/tasks/%53ECRET-ENCODED-SENTINEL/d4-recovery-checkpoints/' + str(uuid4()),
                headers=headers)
            await client.get('/api/health', headers=headers)
            assert first.status_code == second.status_code == third.status_code == 422
            assert first.json() == second.json() == third.json() == {'detail': 'Invalid request'}
        assert lines
        assert not any('SECRET-' in line for line in lines)
        assert not any('%53ECRET' in line for line in lines)
        assert any('/api/health' in line for line in lines)
    finally:
        server.should_exit = True
        await asyncio.wait_for(runner, 10)
        sock.close()
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.disabled = old_disabled
