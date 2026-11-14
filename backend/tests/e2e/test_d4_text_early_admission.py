"""First claimable text profile must already enforce message egress policy."""
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.models.agent_task import AgentRun, AgentTaskMessage
from app.models.audit import AuditLog
from tests.e2e.d4_text_local_harness import d4_text_local_trial, d4_text_server, owned_local_trial

pytestmark = pytest.mark.requires_db
SENTINEL = 'T8-RESTRICTED-MESSAGE-MUST-NEVER-LEAVE'


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['first', 'retry', 'old_epoch', 'history', 'ack'])
async def test_first_claimable_text_profile_has_message_gate(d4_text_server, case):
    c = d4_text_server
    response = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': SENTINEL, 'derived_source_scope': c.source_scope})
    assert response.status_code == 201 and response.json()['status'] == 'ready', response.text
    task_id = UUID(response.json()['task_id'])
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as runtime:
        claim = await runtime.post('/api/agent/runtime/claim', json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        assert claim.json()['task_id'] == str(task_id)
        token = claim.json()['token']
        run_id, epoch = UUID(claim.json()['run_id']), claim.json()['lease_epoch']
        batch_id = uuid4()
        async with c.session() as db:
            message = await db.scalar(select(AgentTaskMessage).where(AgentTaskMessage.task_id == task_id))
            run = await db.get(AgentRun, run_id)
            if case in {'retry', 'old_epoch', 'ack'}:
                message.state = 'claimed'
                message.delivery_batch_id = batch_id
                message.delivery_epoch = epoch - 1 if case == 'old_epoch' else epoch
            elif case == 'history':
                message.state = 'accepted'
                message.delivery_batch_id = batch_id
                message.delivery_epoch = epoch
                run.accepted_message_seq = 1
            await db.commit()
        async def snapshot():
            async with c.session() as db:
                msg = await db.scalar(select(AgentTaskMessage).where(AgentTaskMessage.task_id == task_id))
                run = await db.get(AgentRun, run_id)
                audits = await db.scalar(select(func.count()).select_from(AuditLog))
                return msg.state, msg.delivery_batch_id, msg.delivery_epoch, run.accepted_message_seq, audits
        before = await snapshot()
        headers = {'Authorization': 'Bearer ' + token}
        if case == 'history':
            result = await runtime.get('/api/agent/runtime/messages/history', params={'after_sequence': 0, 'limit': 20}, headers=headers)
        elif case == 'ack':
            result = await runtime.post('/api/agent/runtime/messages/ack', json={'batch_id': str(batch_id), 'through_sequence': 1}, headers=headers)
        else:
            result = await runtime.post('/api/agent/runtime/messages/claim', json={'limit': 20}, headers=headers)
        assert result.status_code in (401, 403, 409), result.text
        assert SENTINEL not in result.text
        assert await snapshot() == before


@pytest.mark.asyncio
async def test_revoked_text_grant_allows_stop_but_not_resume(d4_text_server):
    from sqlalchemy import event
    from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
    c = d4_text_server
    response = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert response.status_code == 201 and response.json()['status'] == 'ready', response.text
    task_id = response.json()['task_id']
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        token, run_id, epoch = claim.json()['token'], claim.json()['run_id'], claim.json()['lease_epoch']
        runtime_headers = {'Authorization': 'Bearer ' + token}
        assert (await client.get('/api/agent/runtime/capabilities', headers=runtime_headers)).status_code == 200
        revoked = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}', json={'enabled': False})
        assert revoked.status_code == 200, revoked.text
        denied = await client.get('/api/agent/runtime/capabilities', headers=runtime_headers)
        assert denied.status_code == 401
        statements = []
        def witness(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())
        async def control(action, position):
            return await client.post(f'/api/agent/tasks/{task_id}/control',
                headers={'Authorization': 'Bearer ' + c.user_token}, json={'action': action,
                    'run_id': run_id, 'expected_epoch': position, 'idempotency_key': uuid4().hex})
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            pause = await control('pause', epoch)
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
        assert pause.status_code == 200 and pause.json()['task_status'] == 'paused', pause.text
        assert not any('d4_root_cause' in s or 'graph_data' in s or 'jsonb_array_elements' in s for s in statements)
        paused_epoch = pause.json()['lease_epoch']
        resume = await control('resume', paused_epoch)
        assert resume.status_code == 403, resume.text
        statements.clear()
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            cancel = await control('cancel', paused_epoch)
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
        assert cancel.status_code == 200 and cancel.json()['task_status'] == 'cancelled', cancel.text
        assert cancel.json()['run_status'] == 'stopped'
        assert not any('d4_root_cause' in s or 'graph_data' in s or 'jsonb_array_elements' in s for s in statements)
        async with c.session() as db:
            run = await db.get(AgentRun, UUID(run_id))
            assert run.status == 'stopped' and run.lease_expires_at is None and run.claim_key is None
