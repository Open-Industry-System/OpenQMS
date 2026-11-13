"""Restricted restart never uses the legacy checkpoint chain."""
from uuid import uuid4

import httpx
import pytest

from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
from tests.e2e.d4_text_local_harness import d4_text_local_trial, d4_text_server, owned_local_trial

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]


async def test_second_restart_ack_preserves_first_restart_activity_and_replay(d4_text_server):
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={
        'report_id': str(c.report_id), 'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert created.status_code == 201 and created.json()['status'] == 'ready'
    task_id = created.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        async def claim():
            result = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
                'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
            assert result.status_code == 200
            return result.json()
        async def pause_checkpoint_restart(run):
            pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
                'action': 'pause', 'run_id': run['run_id'], 'expected_epoch': run['lease_epoch'],
                'idempotency_key': uuid4().hex})
            assert pause.status_code == 200
            cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
                json={'run_id': run['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
            assert cp.status_code == 200
            body = {'action': 'restart', 'run_id': run['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
                'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex}
            result = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
            assert result.status_code == 200
            return body, result.json()
        async def ack_start(run):
            rh = {'Authorization': 'Bearer ' + run['token'], 'X-Tenant-ID': c.slug}
            batch = await client.post('/api/agent/runtime/messages/claim', headers=rh, json={'limit': 1})
            assert batch.status_code == 200 and len(batch.json()['messages']) == 1
            seq = batch.json()['messages'][0]['sequence']
            ack = await client.post('/api/agent/runtime/messages/ack', headers=rh,
                json={'batch_id': batch.json()['batch_id'], 'through_sequence': seq})
            assert ack.status_code == 200
        first = await claim()
        await ack_start(first)
        original_body, original_result = await pause_checkpoint_restart(first)
        second = await claim()
        await ack_start(second)
        await pause_checkpoint_restart(second)
        third = await claim()
        await ack_start(third)
        activity = await client.get(f'/api/agent/tasks/{task_id}/activity', headers=headers)
        assert activity.status_code == 200, activity.text
        assert any(item['kind'] == 'control' and item['data']['control_id'] == original_result['control_id']
                   for item in activity.json()['items'])
        replay = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=original_body)
        assert replay.status_code == 200
        assert replay.json()['control_id'] == original_result['control_id']
        assert replay.json()['run_id'] == original_result['run_id']


@pytest.mark.parametrize('acknowledged', [False, True])
async def test_restart_reuses_unaccepted_start_and_replays_same_control(d4_text_server, acknowledged):
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={
        'report_id': str(c.report_id), 'installation_id': str(c.text_id),
        'request_key': uuid4().hex, 'initial_text': START_MESSAGE,
        'derived_source_scope': c.source_scope})
    assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
    task_id = created.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        old = claim.json()
        token_headers = {'Authorization': 'Bearer ' + old['token']}
        batch = await client.post('/api/agent/runtime/messages/claim', headers=token_headers, json={'limit': 1})
        assert batch.status_code == 200, batch.text
        old_message = batch.json()['messages'][0]
        if acknowledged:
            ack = await client.post('/api/agent/runtime/messages/ack', headers=token_headers,
                json={'batch_id': batch.json()['batch_id'], 'through_sequence': 1})
            assert ack.status_code == 200, ack.text
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert pause.status_code == 200, pause.text
        assert (await client.get('/api/agent/runtime/capabilities', headers=token_headers)).status_code == 401
        cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        assert cp.status_code == 200, cp.text
        assert (await client.get(f'/api/agent/tasks/{task_id}/checkpoints/{cp.json()["checkpoint_id"]}',
            headers=headers)).status_code == 404
        body = {'action': 'restart', 'run_id': old['run_id'],
            'expected_epoch': pause.json()['lease_epoch'], 'checkpoint_id': cp.json()['checkpoint_id'],
            'idempotency_key': uuid4().hex}
        restarted = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert restarted.status_code == 200, restarted.text
        new = restarted.json()
        assert new['run_id'] != old['run_id'] and new['run_status'] == 'pending'
        assert (await client.get('/api/agent/runtime/capabilities', headers=token_headers)).status_code == 401
        replay = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert replay.status_code == 200 and replay.json()['run_id'] == new['run_id']
        different = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers,
            json=dict(body, checkpoint_id=str(uuid4())))
        assert different.status_code == 409
        new_claim_request = {'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex}
        new_claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json=new_claim_request)
        assert new_claim.status_code == 200, new_claim.text
        assert new_claim.json()['run_id'] == new['run_id']
        assert new_claim.json()['has_resume_checkpoint'] is True
        assert (await client.get('/api/agent/runtime/capabilities', headers=token_headers)).status_code == 401
        assert new_claim.json()['accepted_message_seq'] == int(acknowledged)
        new_headers = {'Authorization': 'Bearer ' + new_claim.json()['token']}
        assert (await client.post('/api/agent/runtime/messages/ack', headers=new_headers,
            json={'batch_id': batch.json()['batch_id'], 'through_sequence': 1})).status_code in (403, 409)
        next_batch = await client.post('/api/agent/runtime/messages/claim', headers=new_headers, json={'limit': 1})
        assert next_batch.status_code == 200, next_batch.text
        message = next_batch.json()['messages'][0]
        assert message['content'] == START_MESSAGE and message['sequence'] == 1 + int(acknowledged)
        assert (message['message_id'] != old_message['message_id']) is acknowledged
        ack = await client.post('/api/agent/runtime/messages/ack', headers=new_headers,
            json={'batch_id': next_batch.json()['batch_id'], 'through_sequence': message['sequence']})
        assert ack.status_code == 200
        reclaimed = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json=new_claim_request)
        assert reclaimed.status_code == 200 and reclaimed.json()['accepted_message_seq'] == message['sequence']
        activity = await client.get(f'/api/agent/tasks/{task_id}/activity', headers=headers)
        assert activity.status_code == 200, activity.text


@pytest.mark.parametrize('same_key', [True, False])
async def test_concurrent_restart_consumes_checkpoint_once(d4_text_server, same_key):
    import asyncio
    from sqlalchemy import func, select
    from app.models.agent_d4_recovery import D4RecoveryRestart
    from app.models.agent_task import AgentRun, AgentTaskMessage
    from uuid import UUID
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={
        'report_id': str(c.report_id), 'installation_id': str(c.text_id),
        'request_key': uuid4().hex, 'initial_text': START_MESSAGE,
        'derived_source_scope': c.source_scope})
    assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
    task_id = created.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        old = claim.json()
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        assert cp.status_code == 200, cp.text
        body = {'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
            'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex}
        second = dict(body, idempotency_key=body['idempotency_key'] if same_key else uuid4().hex)
        a, b = await asyncio.gather(*[client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=data)
                                     for data in (body, second)])
        if same_key:
            assert a.status_code == b.status_code == 200, (a.text, b.text)
            assert a.json()['run_id'] == b.json()['run_id']
        else:
            assert sorted([a.status_code, b.status_code]) == [200, 409], (a.text, b.text)
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.task_id == UUID(task_id))) == 2
            assert await db.scalar(select(func.count()).select_from(D4RecoveryRestart).where(D4RecoveryRestart.task_id == UUID(task_id))) == 1
            assert await db.scalar(select(func.count()).select_from(AgentTaskMessage).where(AgentTaskMessage.task_id == UUID(task_id))) == 1


@pytest.mark.parametrize('failure', ['revoked_grant', 'rollback', 'during_commit', 'source_swap',
    'plugin', 'fmea', 'plugin_scope', 'task_scope', 'policy', 'user', 'generation',
    'swap_scope_during_commit', 'swap_scope_before_snapshot'])
async def test_restart_refusal_or_fault_leaves_original_position(d4_text_server, monkeypatch, failure):
    from sqlalchemy import func, select
    from app.models.agent_d4_recovery import D4RecoveryRestart
    from app.models.agent_readonly_control import AgentTaskControl
    from app.models.agent_task import AgentRun, AgentTask
    from app.services.agent_runtime import task_updates
    from uuid import UUID
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={
        'report_id': str(c.report_id), 'installation_id': str(c.text_id),
        'request_key': uuid4().hex, 'initial_text': START_MESSAGE,
        'derived_source_scope': c.source_scope})
    assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
    task_id = created.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        old = claim.json()
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        assert cp.status_code == 200, cp.text
        if failure == 'revoked_grant':
            revoked = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}',
                json={'enabled': False})
            assert revoked.status_code == 200, revoked.text
        elif failure == 'rollback':
            original = task_updates.append_update
            async def fail_control(db, *, task_id, kind, object_id):
                if kind == 'control':
                    raise RuntimeError('synthetic restart rollback')
                return await original(db, task_id=task_id, kind=kind, object_id=object_id)
            monkeypatch.setattr(task_updates, 'append_update', fail_control)
        elif failure == 'during_commit':
            original = task_updates.append_update
            async def revoke_after_control(db, *, task_id, kind, object_id):
                result = await original(db, task_id=task_id, kind=kind, object_id=object_id)
                if kind == 'control':
                    from sqlalchemy import update
                    from app.models.agent_plugin import AgentPluginGrant
                    async with c.session() as other:
                        await other.execute(update(AgentPluginGrant).where(
                            AgentPluginGrant.grant_id == c.text_grant_id).values(enabled=False))
                        await other.commit()
                return result
            monkeypatch.setattr(task_updates, 'append_update', revoke_after_control)
        elif failure == 'source_swap':
            from app.models.fmea import FMEADocument
            async with c.session() as db:
                source = await db.get(FMEADocument, c.fmea_id)
                source.graph_data = {'nodes': [{'id': 'cause-A', 'type': 'FailureCause'},
                                               {'id': 'cause-B', 'type': 'FailureCause'}], 'edges': []}
                await db.commit()
            proof = await c.admin.post(f'/api/capa/{c.report_id}/root-cause-verifications', json={
                'root_cause_text': 'synthetic candidate', 'method': 'measurement', 'conclusion': 'passed',
                'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-B'},
                'source_declaration': {'declares_complete_coverage': True}})
            assert proof.status_code == 200 and proof.json()['source_proof_issued'], proof.text
        elif failure == 'plugin':
            changed = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}', json={'enabled': False})
            assert changed.status_code == 200
        elif failure == 'policy':
            from app.services.agent_runtime.local_d4_text_policy import EMPTY_TEXT_POLICY
            monkeypatch.setattr(c.app.state, 'agent_d4_text_policy', EMPTY_TEXT_POLICY)
        elif failure == 'generation':
            # Apply the external change only after recording the baseline below.
            pass
        elif failure in ('swap_scope_during_commit', 'swap_scope_before_snapshot'):
            from app.models.fmea import FMEADocument
            from app.models.agent_derived_source import AgentPluginDerivedSourceScope, AgentTaskDerivedSourceScope
            from app.services.agent_runtime import d4_recovery
            from sqlalchemy import update
            async with c.session() as other:
                source = await other.get(FMEADocument, c.fmea_id)
                source.graph_data = {'nodes': [{'id': 'cause-A', 'type': 'FailureCause'},
                                               {'id': 'cause-B', 'type': 'FailureCause'}], 'edges': []}
                await other.commit()
            changed = False
            async def change_authority():
                nonlocal changed
                if not changed:
                    changed = True
                    proof = await c.admin.post(f'/api/capa/{c.report_id}/root-cause-verifications', json={
                        'root_cause_text': 'synthetic candidate', 'method': 'measurement', 'conclusion': 'passed',
                        'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-B'},
                        'source_declaration': {'declares_complete_coverage': True}})
                    assert proof.status_code == 200 and proof.json()['source_proof_issued']
                    async with c.session() as other:
                        await other.execute(update(AgentPluginDerivedSourceScope).where(
                            AgentPluginDerivedSourceScope.plugin_grant_id == c.text_grant_id).values(cause_node_id='cause-B'))
                        await other.execute(update(AgentTaskDerivedSourceScope).where(
                            AgentTaskDerivedSourceScope.target_report_id == c.report_id).values(cause_node_id='cause-B'))
                        await other.commit()
            if failure == 'swap_scope_during_commit':
                original = task_updates.append_update
                async def swap_after_control(db, *, task_id, kind, object_id):
                    result = await original(db, task_id=task_id, kind=kind, object_id=object_id)
                    if kind == 'control':
                        await change_authority()
                    return result
                monkeypatch.setattr(task_updates, 'append_update', swap_after_control)
            else:
                original = d4_recovery.authorization_snapshot
                async def swap_before_snapshot(*args, **kwargs):
                    await change_authority()
                    return await original(*args, **kwargs)
                monkeypatch.setattr(d4_recovery, 'authorization_snapshot', swap_before_snapshot)
        else:
            from sqlalchemy import update
            from app.models.role import RolePermission
            from app.models.agent_derived_source import AgentPluginDerivedSourceScope, AgentTaskDerivedSourceScope
            async with c.session() as other:
                if failure in ('fmea', 'user'):
                    await other.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                        RolePermission.module == ('fmea' if failure == 'fmea' else 'capa')).values(permission_level=0))
                elif failure == 'plugin_scope':
                    await other.execute(update(AgentPluginDerivedSourceScope).where(
                        AgentPluginDerivedSourceScope.plugin_grant_id == c.text_grant_id).values(cause_node_id='other'))
                else:
                    await other.execute(update(AgentTaskDerivedSourceScope).where(
                        AgentTaskDerivedSourceScope.target_report_id == c.report_id).values(cause_node_id='other'))
                await other.commit()
        async def snapshot():
            from app.models.agent_task import AgentTaskGrant, AgentTaskMessage
            from app.models.agent_plugin import AgentPluginGrant
            from app.models.agent_readonly_control import AgentTaskUpdate
            from app.models.agent_derived_source import AgentPluginDerivedSourceScope, AgentTaskDerivedSourceScope
            from app.models.audit import AuditLog
            async with c.session() as db:
                async def rows(model, predicate):
                    result = await db.execute(select(*model.__table__.columns).where(predicate)
                        .order_by(*model.__table__.primary_key.columns))
                    return [dict(row) for row in result.mappings().all()]
                messages = (await db.execute(select(AgentTaskMessage.message_id, AgentTaskMessage.sequence,
                    AgentTaskMessage.state, AgentTaskMessage.delivery_batch_id, AgentTaskMessage.delivery_epoch)
                    .where(AgentTaskMessage.task_id == UUID(task_id)).order_by(AgentTaskMessage.sequence))).all()
                plugin_scopes = await rows(AgentPluginDerivedSourceScope,
                    AgentPluginDerivedSourceScope.plugin_grant_id == c.text_grant_id)
                task_scopes = await rows(AgentTaskDerivedSourceScope,
                    AgentTaskDerivedSourceScope.target_report_id == c.report_id)
                parent = await rows(AgentPluginGrant, AgentPluginGrant.grant_id == c.text_grant_id)
                grants = await rows(AgentTaskGrant, AgentTaskGrant.task_id == UUID(task_id))
                updates = await rows(AgentTaskUpdate, AgentTaskUpdate.task_id == UUID(task_id))
                watermark = await db.scalar(select(AgentRun.accepted_message_seq).where(
                    AgentRun.run_id == UUID(old['run_id'])))
                audits = await db.scalar(select(func.count()).select_from(AuditLog).where(
                    AuditLog.table_name == 'agent_task_controls', AuditLog.record_id.in_(select(
                        AgentTaskControl.control_id).where(AgentTaskControl.task_id == UUID(task_id)))))
                return {'messages': messages, 'plugin_scopes': plugin_scopes, 'task_scopes': task_scopes,
                        'parent': parent, 'grants': grants, 'updates': updates,
                        'watermark': watermark, 'audits': audits}
        before = await snapshot()
        if failure == 'generation':
            from sqlalchemy import text
            async with c.engine.begin() as conn:
                changed = await conn.execute(text('UPDATE public.tenants SET generation=generation+1 WHERE id=:id AND generation=:generation'),
                    {'id': c.binding.tenant_id, 'generation': c.binding.generation})
                assert changed.rowcount == 1
        try:
            result = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
                'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
                'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex})
        finally:
            if failure == 'generation':
                from sqlalchemy import text
                async with c.engine.begin() as conn:
                    restored = await conn.execute(text('UPDATE public.tenants SET generation=:generation WHERE id=:id AND generation=:next'),
                        {'id': c.binding.tenant_id, 'generation': c.binding.generation, 'next': c.binding.generation + 1})
                    assert restored.rowcount == 1
        assert result.status_code in ((500,) if failure == 'rollback' else (403, 404)), result.text
        # Only changes made by the independent concurrent actor are allowed;
        # restart itself must leave every other scope field, grant field, message,
        # watermark and control audit untouched.
        if failure == 'during_commit':
            assert len(before['parent']) == 1
            before['parent'][0]['enabled'] = False
        if failure in ('swap_scope_during_commit', 'swap_scope_before_snapshot'):
            assert len(before['plugin_scopes']) == len(before['task_scopes']) == 1
            before['plugin_scopes'][0]['cause_node_id'] = 'cause-B'
            before['task_scopes'][0]['cause_node_id'] = 'cause-B'
        assert await snapshot() == before
        async with c.session() as db:
            task = await db.get(AgentTask, UUID(task_id))
            run = await db.get(AgentRun, UUID(old['run_id']))
            assert task.status == run.status == 'paused' and run.lease_epoch == pause.json()['lease_epoch']
            assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.task_id == task.task_id)) == 1
            assert await db.scalar(select(func.count()).select_from(D4RecoveryRestart).where(D4RecoveryRestart.task_id == task.task_id)) == 0
            assert await db.scalar(select(func.count()).select_from(AgentTaskControl).where(
                AgentTaskControl.task_id == task.task_id, AgentTaskControl.action == 'restart')) == 0


@pytest.mark.parametrize('corruption', ['old_run', 'expected_epoch', 'pointer', 'message_content', 'missing_mapping', 'control_pointer', 'watermark'])
async def test_corrupt_restart_association_cannot_claim_new_run(d4_text_server, corruption):
    from sqlalchemy import select
    from app.models.agent_d4_recovery import D4RecoveryRestart
    from uuid import UUID
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = created.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        old = (await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})).json()
        paused = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': paused.json()['lease_epoch']})
        body = {
            'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': paused.json()['lease_epoch'],
            'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex}
        restarted = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert restarted.status_code == 200, restarted.text
        async with c.session() as db:
            mapping = await db.scalar(select(D4RecoveryRestart).where(D4RecoveryRestart.task_id == UUID(task_id)))
            if corruption == 'old_run':
                mapping.old_run_id = mapping.new_run_id
            elif corruption == 'expected_epoch':
                from app.models.agent_readonly_control import AgentTaskControl
                control = await db.get(AgentTaskControl, mapping.control_id)
                control.expected_epoch += 1
            elif corruption == 'pointer':
                from app.models.agent_d4_recovery import D4RecoveryCheckpoint
                from app.models.agent_readonly_control import AgentTaskUpdate
                cp_row = await db.get(D4RecoveryCheckpoint, mapping.checkpoint_id)
                pointer = await db.scalar(select(AgentTaskUpdate).where(
                    AgentTaskUpdate.task_id == UUID(task_id), AgentTaskUpdate.sequence == cp_row.update_sequence))
                pointer.object_id = uuid4()
            elif corruption == 'message_content':
                from app.models.agent_task import AgentTaskMessage
                message = await db.get(AgentTaskMessage, mapping.start_message_id)
                message.content = 'synthetic-invalid-input'
            elif corruption == 'missing_mapping':
                await db.delete(mapping)
            elif corruption == 'control_pointer':
                from app.models.agent_readonly_control import AgentTaskUpdate
                pointer = await db.scalar(select(AgentTaskUpdate).where(
                    AgentTaskUpdate.task_id == UUID(task_id), AgentTaskUpdate.kind == 'control',
                    AgentTaskUpdate.object_id == mapping.control_id))
                pointer.object_id = uuid4()
            else:
                from app.models.agent_task import AgentRun
                run = await db.get(AgentRun, mapping.new_run_id)
                run.accepted_message_seq = 42
            await db.commit()
        denied = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert denied.status_code in (401, 403)
        if corruption == 'control_pointer':
            assert (await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)).status_code == 403
            assert (await client.get(f'/api/agent/tasks/{task_id}/activity', headers=headers)).status_code == 403


@pytest.mark.parametrize('statement_fragment', [
    'update agent_runs set', 'insert into agent_runs', 'insert into agent_task_messages',
    'insert into agent_task_controls', 'insert into audit_logs',
])
async def test_restart_write_fault_rolls_back_all_effects(d4_text_server, statement_fragment):
    from sqlalchemy import event, func, select
    from app.models.agent_d4_recovery import D4RecoveryRestart
    from app.models.agent_task import AgentRun, AgentTaskMessage
    from uuid import UUID
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = created.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        old = (await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})).json()
        runtime_headers = {'Authorization': 'Bearer ' + old['token'], 'X-Tenant-ID': c.slug}
        batch = await client.post('/api/agent/runtime/messages/claim', headers=runtime_headers, json={'limit': 1})
        ack = await client.post('/api/agent/runtime/messages/ack', headers=runtime_headers,
            json={'batch_id': batch.json()['batch_id'], 'through_sequence': 1})
        assert ack.status_code == 200
        paused = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': paused.json()['lease_epoch']})
        assert cp.status_code == 200
        hit = False
        def fail_at_write(conn, cursor, statement, parameters, context, executemany):
            nonlocal hit
            if not hit and statement_fragment in statement.lower():
                hit = True
                raise RuntimeError('synthetic recovery write fault')
        event.listen(c.engine.sync_engine, 'before_cursor_execute', fail_at_write)
        try:
            result = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
                'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': paused.json()['lease_epoch'],
                'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex})
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', fail_at_write)
        assert hit and result.status_code == 500
        async with c.session() as db:
            run = await db.get(AgentRun, UUID(old['run_id']))
            assert run.status == 'paused' and run.lease_epoch == paused.json()['lease_epoch']
            assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.task_id == UUID(task_id))) == 1
            assert await db.scalar(select(func.count()).select_from(D4RecoveryRestart).where(D4RecoveryRestart.task_id == UUID(task_id))) == 0
            assert await db.scalar(select(func.count()).select_from(AgentTaskMessage).where(AgentTaskMessage.task_id == UUID(task_id))) == 1


@pytest.mark.parametrize('path', ['claim', 'replay'])
async def test_final_restart_mapping_read_rechecks_authority(d4_text_server, monkeypatch, path):
    from sqlalchemy import update
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.role import RolePermission
    from app.services.agent_runtime import d4_recovery
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = created.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        old = (await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})).json()
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        body = {'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
            'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex}
        result = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert result.status_code == 200
        original = d4_recovery.restart_mapping
        revoked = False
        async def revoke_after_mapping(*args, **kwargs):
            nonlocal revoked
            value = await original(*args, **kwargs)
            if not revoked and value is not None:
                revoked = True
                async with c.session() as other:
                    if path == 'claim':
                        await other.execute(update(AgentPluginGrant).where(
                            AgentPluginGrant.grant_id == c.text_grant_id).values(enabled=False))
                    else:
                        await other.execute(update(RolePermission).where(
                            RolePermission.role_id == c.role_id, RolePermission.module == 'capa').values(permission_level=0))
                    await other.commit()
            return value
        monkeypatch.setattr(d4_recovery, 'restart_mapping', revoke_after_mapping)
        if path == 'claim':
            denied = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
                'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
            # Claim maps authorization PermissionError to 403 via runtime_error;
            # 401 is reserved for an already-issued run credential.
            assert denied.status_code == 403
        else:
            denied = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
            assert denied.status_code in (403, 404)
        assert revoked


@pytest.mark.parametrize('module', ['capa', 'fmea'])
async def test_restart_rechecks_user_permissions_after_last_snapshot(d4_text_server, monkeypatch, module):
    from sqlalchemy import func, select, update
    from app.models.agent_d4_recovery import D4RecoveryRestart
    from app.models.agent_task import AgentRun
    from app.models.role import RolePermission
    from app.services.agent_runtime import d4_recovery
    from uuid import UUID
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = created.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        old = (await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})).json()
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        original = d4_recovery.authorization_snapshot
        calls = 0
        async def revoke_after_snapshot(*args, **kwargs):
            nonlocal calls
            value = await original(*args, **kwargs)
            calls += 1
            if calls == 3:
                async with c.session() as other:
                    await other.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                        RolePermission.module == module).values(permission_level=0))
                    await other.commit()
            return value
        monkeypatch.setattr(d4_recovery, 'authorization_snapshot', revoke_after_snapshot)
        denied = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
            'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex})
        assert calls == 3
        assert denied.status_code in (403, 404)
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.task_id == UUID(task_id))) == 1
            assert await db.scalar(select(func.count()).select_from(D4RecoveryRestart).where(D4RecoveryRestart.task_id == UUID(task_id))) == 0


@pytest.mark.parametrize('parent_state', ['active', 'revoked', 'missing-binding'])
async def test_two_matching_parent_grants_produce_one_recoverable_task_grant(d4_text_server, parent_state):
    """Two independently valid parents must not make a text task unrecoverable."""
    from sqlalchemy import select
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.agent_task import AgentTaskGrant
    from app.models.agent_derived_source import AgentTaskDerivedSourceScope
    from app.models.agent_d4_recovery import D4TaskParentGrant
    from uuid import UUID

    c = d4_text_server
    async with c.session() as db:
        parent = await db.get(AgentPluginGrant, c.text_grant_id)
        expiry = parent.expires_at.isoformat()
    extra = await c.admin.post(f'/api/admin/agent-plugins/{c.text_id}/grants', json={
        'capability_id': 'capa.d4.root_cause_candidate.masked.v1',
        'factory_ids': [str(c.factory_id)], 'object_ids': [str(c.report_id)],
        'product_line_codes': [c.line], 'expires_at': expiry, 'enabled': True,
        'derived_source_scope': c.source_scope})
    assert extra.status_code == 201, extra.text
    assert extra.json()['grant_id'] != str(c.text_grant_id)
    created = await c.client.post('/api/agent/tasks', json={
        'report_id': str(c.report_id), 'installation_id': str(c.text_id),
        'request_key': uuid4().hex, 'initial_text': START_MESSAGE,
        'derived_source_scope': c.source_scope})
    assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
    task_id = UUID(created.json()['task_id'])
    async with c.session() as db:
        grants = (await db.scalars(select(AgentTaskGrant).where(AgentTaskGrant.task_id == task_id,
            AgentTaskGrant.capability_id == 'capa.d4.root_cause_candidate.masked.v1'))).all()
        assert len(grants) == 1
        task_grant_id = grants[0].grant_id
        binding = await db.get(D4TaskParentGrant, task_grant_id)
        assert binding is not None
        assert str(binding.plugin_grant_id) == min(str(c.text_grant_id), extra.json()['grant_id'])
        scope = await db.scalar(select(AgentTaskDerivedSourceScope).where(
            AgentTaskDerivedSourceScope.task_grant_id == grants[0].grant_id))
        assert scope is not None and scope.cause_node_id == c.source_scope['cause_node_id']
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200
        old = claim.json()
        headers = {'Authorization': 'Bearer ' + c.user_token}
        paused = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert paused.status_code == 200
        checkpoint = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': paused.json()['lease_epoch']})
        assert checkpoint.status_code == 200
        if parent_state == 'revoked':
            selected_parent = min(str(c.text_grant_id), extra.json()['grant_id'])
            revoked = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{selected_parent}',
                json={'enabled': False})
            assert revoked.status_code == 200
        if parent_state == 'missing-binding':
            async with c.session() as db:
                await db.delete(await db.get(D4TaskParentGrant, task_grant_id))
                await db.commit()
        restarted = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': paused.json()['lease_epoch'],
            'checkpoint_id': checkpoint.json()['checkpoint_id'], 'idempotency_key': uuid4().hex})
        assert restarted.status_code == (200 if parent_state == 'active' else 403)


@pytest.mark.parametrize('parent_state', ['revoked', 'missing-binding'])
async def test_two_parent_grants_runtime_claim_cannot_switch_parent(d4_text_server, parent_state):
    from sqlalchemy import select
    from app.models.agent_d4_recovery import D4TaskParentGrant
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.agent_task import AgentTaskGrant
    from uuid import UUID

    c = d4_text_server
    async with c.session() as db:
        parent = await db.get(AgentPluginGrant, c.text_grant_id)
        expiry = parent.expires_at.isoformat()
    extra = await c.admin.post(f'/api/admin/agent-plugins/{c.text_id}/grants', json={
        'capability_id': 'capa.d4.root_cause_candidate.masked.v1',
        'factory_ids': [str(c.factory_id)], 'object_ids': [str(c.report_id)],
        'product_line_codes': [c.line], 'expires_at': expiry, 'enabled': True,
        'derived_source_scope': c.source_scope})
    assert extra.status_code == 201, extra.text
    created = await c.client.post('/api/agent/tasks', json={
        'report_id': str(c.report_id), 'installation_id': str(c.text_id),
        'request_key': uuid4().hex, 'initial_text': START_MESSAGE,
        'derived_source_scope': c.source_scope})
    assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
    task_id = UUID(created.json()['task_id'])
    async with c.session() as db:
        task_grant_id = await db.scalar(select(AgentTaskGrant.grant_id).where(
            AgentTaskGrant.task_id == task_id,
            AgentTaskGrant.capability_id == 'capa.d4.root_cause_candidate.masked.v1'))
        binding = await db.get(D4TaskParentGrant, task_grant_id)
        selected = binding.plugin_grant_id
        assert str(selected) == min(str(c.text_grant_id), extra.json()['grant_id'])
        if parent_state == 'missing-binding':
            await db.delete(binding)
            await db.commit()
    if parent_state == 'revoked':
        revoked = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{selected}',
            json={'enabled': False})
        assert revoked.status_code == 200
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        denied = await client.post('/api/agent/runtime/claim', json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert denied.status_code in (401, 403)
    async with c.session() as db:
        binding = await db.get(D4TaskParentGrant, task_grant_id)
        assert (binding is None if parent_state == 'missing-binding'
                else binding is not None and binding.plugin_grant_id == selected)
