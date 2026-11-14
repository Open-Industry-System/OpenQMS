"""Exercise revocation after the last restart authorization, before commit."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.models.agent_d4_recovery import D4RecoveryRestart
from app.models.agent_derived_source import AgentPluginDerivedSourceScope, AgentTaskDerivedSourceScope
from app.models.agent_readonly_control import AgentTaskControl, AgentTaskUpdate
from app.models.agent_task import AgentRun, AgentTask, AgentTaskGrant, AgentTaskMessage
from app.models.audit import AuditLog
from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
from app.models.role import RolePermission
from app.models.user import User
from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
from tests.e2e.d4_text_local_harness import d4_text_local_trial, d4_text_server, owned_local_trial

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]


@pytest.mark.parametrize('revocation', ['user', 'fmea_permission', 'task_scope', 'plugin_scope', 'proof'])
async def test_final_restart_authority_revocation_before_commit_rolls_back(d4_text_server, monkeypatch, revocation):
    from app.services.agent_runtime import task_controls
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
    task_id = UUID(created.json()['task_id'])
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claimed = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claimed.status_code == 200, claimed.text
        old = claimed.json()
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert pause.status_code == 200, pause.text
        cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        assert cp.status_code == 200, cp.text

        async def snapshot():
            async with c.session() as db:
                task = await db.get(AgentTask, task_id)
                run = await db.get(AgentRun, UUID(old['run_id']))
                counts = []
                for model in (AgentRun, AgentTaskControl, D4RecoveryRestart, AgentTaskUpdate, AgentTaskMessage):
                    counts.append(await db.scalar(select(func.count()).select_from(model).where(model.task_id == task_id)))
                audits = await db.scalar(select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == 'CONTROL_AGENT_TASK', AuditLog.changed_fields['task_id'].astext == str(task_id)))
                messages = (await db.execute(select(AgentTaskMessage.sequence, AgentTaskMessage.state,
                    AgentTaskMessage.delivery_batch_id, AgentTaskMessage.delivery_epoch).where(
                    AgentTaskMessage.task_id == task_id).order_by(AgentTaskMessage.sequence))).all()
                return (task.status, run.status, run.lease_epoch, run.claim_key,
                        tuple(counts), audits, tuple(tuple(row) for row in messages))
        before = await snapshot()
        assert before[0:2] == ('paused', 'paused')
        original = task_controls._resume_authority
        conflicts = []
        async def mutate(other):
            if revocation == 'user':
                await other.execute(update(User).where(User.user_id == c.user_id).values(is_active=False))
            elif revocation == 'fmea_permission':
                await other.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                    RolePermission.module == 'fmea').values(permission_level=0))
            elif revocation == 'task_scope':
                grants = select(AgentTaskGrant.grant_id).where(AgentTaskGrant.task_id == task_id)
                await other.execute(update(AgentTaskDerivedSourceScope).where(
                    AgentTaskDerivedSourceScope.task_grant_id.in_(grants)).values(cause_node_id='cause-B'))
            elif revocation == 'plugin_scope':
                await other.execute(update(AgentPluginDerivedSourceScope).where(
                    AgentPluginDerivedSourceScope.plugin_grant_id == c.text_grant_id).values(cause_node_id='cause-B'))
            else:
                await other.execute(update(CapaD4RootCauseSourceProof).where(
                    CapaD4RootCauseSourceProof.report_id == c.report_id,
                    CapaD4RootCauseSourceProof.status == 'active').values(invalidated_at=datetime.now(UTC)))
        async def revoke_after_final_check(db, task, run, installation):
            result = await original(db, task, run, installation)
            if run.status == 'pending':
                async with c.session() as other:
                    await other.execute(text("SET LOCAL lock_timeout = '200ms'"))
                    try:
                        await mutate(other)
                        await other.commit()
                    except DBAPIError as exc:
                        conflicts.append(getattr(exc.orig, 'sqlstate', None))
                assert conflicts == ['55P03']
            return result
        monkeypatch.setattr(task_controls, '_resume_authority', revoke_after_final_check)
        result = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
            'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex})
        assert result.status_code == 200 and conflicts == ['55P03'], result.text
        after = await snapshot()
        assert after[0:2] == ('ready', 'stopped')
        assert after[4][0] == before[4][0] + 1  # exactly one replacement run
        assert after[4][1] == before[4][1] + 1  # exactly one control
        assert after[4][2] == before[4][2] + 1  # exactly one restart mapping
        assert after[5] == before[5] + 1         # exactly one control audit
        async with c.session() as other:
            await mutate(other)
            await other.commit()
        denied = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert denied.status_code in (401, 403), denied.text
        assert await snapshot() == after


@pytest.mark.parametrize('operation', ['checkpoint', 'restart'])
async def test_control_acl_conflict_is_redacted_and_rolls_back_then_retries(d4_text_server, operation):
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = UUID(created.json()['task_id'])
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        old = claim.json()
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert pause.status_code == 200, pause.text
        position = {'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']}
        if operation == 'restart':
            cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers, json=position)
            assert cp.status_code == 200, cp.text
            path = f'/api/agent/tasks/{task_id}/control'
            body = dict(position, action='restart', checkpoint_id=cp.json()['checkpoint_id'], idempotency_key=uuid4().hex)
        else:
            path = f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints'
            body = position
        async def counts():
            async with c.session() as db:
                return tuple([await db.scalar(select(func.count()).select_from(model).where(model.task_id == task_id))
                    for model in (AgentRun, AgentTaskControl, D4RecoveryRestart, AgentTaskUpdate, AgentTaskMessage)])
        before = await counts()
        async with c.session() as writer:
            # Real concurrent writer holds an ACL row; no permission is actually changed.
            await writer.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                RolePermission.module == 'capa').values(permission_level=RolePermission.permission_level))
            blocked = await client.post(path, headers=headers, json=body)
            assert blocked.status_code == 503 and blocked.json() == {'detail': 'Recovery unavailable'}, blocked.text
            assert 'synthetic candidate' not in blocked.text
            assert await counts() == before
            await writer.commit()
        retry = await client.post(path, headers=headers, json=body)
        assert retry.status_code == 200, retry.text


async def test_restart_idempotent_replay_serializes_current_control_authority(d4_text_server, monkeypatch):
    from app.services.agent_runtime import d4_recovery
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = UUID(created.json()['task_id'])
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
        body = {'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
            'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex}
        first = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert first.status_code == 200, first.text
        original, conflicts = d4_recovery.restart_mapping, []
        async def revoke_after_mapping(*args, **kwargs):
            value = await original(*args, **kwargs)
            async with c.session() as other:
                await other.execute(text("SET LOCAL lock_timeout = '200ms'"))
                try:
                    await other.execute(update(User).where(User.user_id == c.user_id).values(is_active=False))
                    await other.commit()
                except DBAPIError as exc:
                    conflicts.append(getattr(exc.orig, 'sqlstate', None))
            return value
        monkeypatch.setattr(d4_recovery, 'restart_mapping', revoke_after_mapping)
        replay = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert replay.status_code == 200 and replay.json()['run_id'] == first.json()['run_id'], replay.text
        assert conflicts == ['55P03']
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.task_id == task_id)) == 2
            assert await db.scalar(select(func.count()).select_from(D4RecoveryRestart).where(
                D4RecoveryRestart.task_id == task_id)) == 1
            await db.execute(update(User).where(User.user_id == c.user_id).values(is_active=False))
            await db.commit()
        denied = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert denied.status_code in (401, 403), denied.text


async def test_acl_leaf_locks_both_users_in_stable_order(d4_text_server):
    from app.services.agent_runtime.control_authority_fence import lock_employee_acl
    c = d4_text_server
    async with c.session() as db:
        await lock_employee_acl(db, (c.admin_user_id, c.user_id))
        for user_id in (c.admin_user_id, c.user_id):
            async with c.session() as other:
                await other.execute(text("SET LOCAL lock_timeout = '200ms'"))
                try:
                    await other.execute(update(User).where(User.user_id == user_id).values(is_active=False))
                    pytest.fail('employee lock did not block concurrent write')
                except DBAPIError as exc:
                    assert getattr(exc.orig, 'sqlstate', None) == '55P03'


@pytest.mark.parametrize('busy', [False, True])
async def test_restart_source_swap_to_invisible_fmea_has_no_read_or_busy_oracle(d4_text_server, monkeypatch, busy):
    from sqlalchemy import event
    from app.models.capa import CAPAEightD
    from app.models.factory import Factory
    from app.models.fmea import FMEADocument
    from app.services.agent_runtime import control_authority_fence
    c = d4_text_server
    other_factory_id, other_fmea_id = uuid4(), uuid4()
    async with c.session() as db:
        db.add(Factory(id=other_factory_id, code='D4-' + uuid4().hex[:12], name='invisible factory'))
        db.add(FMEADocument(fmea_id=other_fmea_id, document_no='D4-' + uuid4().hex[:12],
            title='invisible source', factory_id=other_factory_id, product_line_code=c.line,
            graph_data={'nodes': [{'id': 'cause-B', 'type': 'FailureCause'}], 'edges': []}))
        await db.commit()
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = UUID(created.json()['task_id'])
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    statements, holder, collecting = [], [], False
    def witness(conn, cursor, statement, parameters, context, executemany):
        if collecting and 'fmea_documents' in statement.lower():
            statements.append(statement.lower())
    original = control_authority_fence.lock_control_target
    async def swap_before_target_lock(db, task):
        nonlocal collecting
        async with c.session() as writer:
            await writer.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report_id)
                                 .values(fmea_ref_id=other_fmea_id))
            await writer.commit()
        if busy:
            context = c.session()
            locked = await context.__aenter__()
            await locked.scalar(select(FMEADocument.fmea_id).where(
                FMEADocument.fmea_id == other_fmea_id).with_for_update())
            holder.append(context)
        collecting = True
        return await original(db, task)
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
        monkeypatch.setattr(control_authority_fence, 'lock_control_target', swap_before_target_lock)
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            result = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
                'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
                'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex})
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
            if holder:
                await holder[0].__aexit__(None, None, None)
        assert result.status_code == 403 and result.json() == {'detail': 'Access denied'}, result.text
        assert not statements, 'unauthorized FMEA was queried after source swap'
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.task_id == task_id)) == 1
            assert await db.scalar(select(func.count()).select_from(D4RecoveryRestart).where(
                D4RecoveryRestart.task_id == task_id)) == 0
            assert await db.scalar(select(func.count()).select_from(AgentTaskControl).where(
                AgentTaskControl.task_id == task_id, AgentTaskControl.action == 'restart')) == 0


async def test_restart_rechecks_fmea_acl_before_read_or_lock(d4_text_server, monkeypatch):
    from sqlalchemy import event
    from app.services.agent_runtime import control_authority_fence
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = UUID(created.json()['task_id'])
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    statements, collecting = [], False
    def witness(conn, cursor, statement, parameters, context, executemany):
        if collecting and ('fmea_documents' in statement.lower() or 'jsonb_array_elements' in statement.lower()):
            statements.append(statement.lower())
    original = control_authority_fence.lock_control_target
    async def revoke_after_target_lock(db, task):
        nonlocal collecting
        result = await original(db, task)
        async with c.session() as other:
            await other.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                RolePermission.module == 'fmea').values(permission_level=0))
            await other.commit()
        collecting = True
        return result
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        old = claim.json()
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        monkeypatch.setattr(control_authority_fence, 'lock_control_target', revoke_after_target_lock)
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            result = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
                'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
                'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex})
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
        assert result.status_code == 403, result.text
        assert not statements, 'FMEA was read or locked after access revocation'
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(D4RecoveryRestart).where(
                D4RecoveryRestart.task_id == task_id)) == 0


async def test_fmea_writer_audit_and_restart_do_not_form_lock_cycle(d4_text_server):
    import asyncio
    from sqlalchemy import event
    from app.models.fmea import FMEADocument
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = UUID(created.json()['task_id'])
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    entered = asyncio.Event()
    def witness(conn, cursor, statement, parameters, context, executemany):
        query = statement.lower()
        if 'from fmea_documents' in query and 'for update' in query:
            entered.set()
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        old = claim.json()
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        body = {'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
            'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex}
        async with c.session() as writer:
            await writer.execute(text("SET LOCAL lock_timeout = '2s'"))
            await writer.execute(update(FMEADocument).where(FMEADocument.fmea_id == c.fmea_id)
                                 .values(title=FMEADocument.title))
            event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
            try:
                pending = asyncio.create_task(client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body))
                await asyncio.wait_for(entered.wait(), timeout=10)
                writer.add(AuditLog(table_name='fmea_documents', record_id=c.fmea_id,
                    action='UPDATE', operated_by=c.user_id, factory_id=c.factory_id, changed_fields={}))
                await writer.commit()
                result = await asyncio.wait_for(pending, timeout=10)
            finally:
                event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
        assert result.status_code == 503 and result.json() == {'detail': 'Recovery unavailable'}, result.text
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(D4RecoveryRestart).where(
                D4RecoveryRestart.task_id == task_id)) == 0
        retry = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert retry.status_code == 200, retry.text


async def test_restart_and_text_delivery_contention_is_fail_closed_and_retryable(d4_text_server, monkeypatch):
    import asyncio
    from sqlalchemy import event
    from app.services.agent_runtime import d4_text_delivery
    c = d4_text_server
    async def create_task():
        response = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
            'installation_id': str(c.text_id), 'request_key': uuid4().hex,
            'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
        assert response.status_code == 201 and response.json()['status'] == 'ready', response.text
        return response.json()['task_id']
    first_task = await create_task()
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        async def claim():
            result = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
                'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
            assert result.status_code == 200, result.text
            return result.json()
        old = await claim()
        pause = await client.post(f'/api/agent/tasks/{first_task}/control', headers=headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        cp = await client.post(f'/api/agent/tasks/{first_task}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        body = {'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
            'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex}
        second_task = await create_task()
        active = await claim()
        assert active['task_id'] == second_task
        started, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
        original = d4_text_delivery.verify_release_is_current
        async def hold_after_check(*args, **kwargs):
            await original(*args, **kwargs)
            started.set()
            await asyncio.wait_for(release.wait(), timeout=10)
        monkeypatch.setattr(d4_text_delivery, 'verify_release_is_current', hold_after_check)
        pending = asyncio.create_task(client.get('/api/agent/runtime/capa/d4/root-cause-text', headers={
            'X-Tenant-ID': c.slug, 'Authorization': 'Bearer ' + active['token']}))
        def witness(conn, cursor, statement, parameters, context, executemany):
            query = statement.lower()
            if 'from agent_plugin_installations' in query and 'for update' in query:
                waiting.set()
        try:
            await asyncio.wait_for(started.wait(), timeout=10)
            event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
            restart = asyncio.create_task(client.post(f'/api/agent/tasks/{first_task}/control', headers=headers, json=body))
            await asyncio.wait_for(waiting.wait(), timeout=10)
            async with c.session() as db:
                assert await db.scalar(select(func.count()).select_from(D4RecoveryRestart).where(
                    D4RecoveryRestart.task_id == UUID(first_task))) == 0
        finally:
            release.set()
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
        delivery = await asyncio.wait_for(pending, timeout=10)
        assert delivery.status_code == 200, delivery.text
        result = await asyncio.wait_for(restart, timeout=10)
        assert result.status_code == 200, result.text
