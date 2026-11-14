"""Task stop and idempotent replay require current control authority at commit."""
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.models.agent_readonly_control import AgentTaskControl, AgentTaskUpdate
from app.models.agent_task import AgentRun, AgentTask, AgentTaskMessage
from app.models.audit import AuditLog
from app.models.factory import UserFactory
from app.models.role import RolePermission, UserProductLine
from app.models.user import User
from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
from tests.e2e.d4_text_local_harness import d4_text_local_trial, d4_text_server, owned_local_trial

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]


@pytest.mark.parametrize('mode', ['pause', 'cancel', 'blocked_cancel', 'pause_replay', 'cancel_replay'])
@pytest.mark.parametrize('revocation', ['user', 'capa', 'factory', 'line'])
async def test_stop_final_control_authority_revocation_fails_closed(d4_text_server, monkeypatch, mode, revocation):
    from app.services.agent_runtime import task_controls
    c = d4_text_server
    if revocation == 'factory':
        async with c.session() as db:
            await db.execute(update(User).where(User.user_id == c.user_id).values(factory_id=None))
            await db.commit()
    if mode == 'blocked_cancel':
        revoked = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}',
                                      json={'enabled': False})
        assert revoked.status_code == 200, revoked.text
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert created.status_code == 201, created.text
    assert created.json()['status'] == ('blocked_capability' if mode == 'blocked_cancel' else 'ready')
    task_id = UUID(created.json()['task_id'])
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        if mode == 'blocked_cancel':
            run_id, epoch = None, None
        else:
            claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
                'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
            assert claim.status_code == 200, claim.text
            run_id, epoch = claim.json()['run_id'], claim.json()['lease_epoch']
        action = 'cancel' if mode in ('cancel', 'cancel_replay', 'blocked_cancel') else 'pause'
        body = {'action': action, 'run_id': run_id, 'expected_epoch': epoch, 'idempotency_key': uuid4().hex}
        if mode.endswith('_replay'):
            first = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
            assert first.status_code == 200, first.text

        async def snapshot():
            async with c.session() as db:
                task = await db.get(AgentTask, task_id)
                runs = (await db.execute(select(AgentRun.run_id, AgentRun.status, AgentRun.lease_epoch,
                    AgentRun.lease_expires_at, AgentRun.claim_key, AgentRun.accepted_message_seq).where(
                    AgentRun.task_id == task_id).order_by(AgentRun.run_id))).all()
                controls = await db.scalar(select(func.count()).select_from(AgentTaskControl).where(
                    AgentTaskControl.task_id == task_id))
                pointers = await db.scalar(select(func.count()).select_from(AgentTaskUpdate).where(
                    AgentTaskUpdate.task_id == task_id))
                audits = await db.scalar(select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == 'CONTROL_AGENT_TASK', AuditLog.changed_fields['task_id'].astext == str(task_id)))
                messages = (await db.execute(select(AgentTaskMessage.message_id, AgentTaskMessage.sequence,
                    AgentTaskMessage.state, AgentTaskMessage.delivery_batch_id, AgentTaskMessage.delivery_epoch).where(
                    AgentTaskMessage.task_id == task_id).order_by(AgentTaskMessage.sequence))).all()
                return (task.status, tuple(tuple(row) for row in runs), controls, pointers, audits,
                        tuple(tuple(row) for row in messages))
        before = await snapshot()
        original, calls, conflicts = task_controls._user_authority, 0, []
        async def mutate(other):
            if revocation == 'user':
                await other.execute(update(User).where(User.user_id == c.user_id).values(is_active=False))
            elif revocation == 'capa':
                await other.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                    RolePermission.module == 'capa').values(permission_level=0))
            elif revocation == 'factory':
                await other.execute(delete(UserFactory).where(UserFactory.user_id == c.user_id,
                    UserFactory.factory_id == c.factory_id))
            else:
                await other.execute(delete(UserProductLine).where(UserProductLine.user_id == c.user_id,
                    UserProductLine.product_line_code == c.line))
        async def revoke_after_final_check(*args, **kwargs):
            nonlocal calls
            value = await original(*args, **kwargs)
            calls += 1
            # An active/paused run has four user checks; blocked cancel has three.
            if calls == (3 if mode == 'blocked_cancel' else 4):
                async with c.session() as other:
                    await other.execute(text("SET LOCAL lock_timeout = '200ms'"))
                    try:
                        await mutate(other)
                        await other.commit()
                    except DBAPIError as exc:
                        conflicts.append(getattr(exc.orig, 'sqlstate', None))
                assert conflicts == ['55P03']
            return value
        monkeypatch.setattr(task_controls, '_user_authority', revoke_after_final_check)
        result = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert result.status_code == 200 and conflicts == ['55P03'], result.text
        after = await snapshot()
        if mode.endswith('_replay'):
            assert after == before
        else:
            assert after[0] == ('paused' if action == 'pause' else 'cancelled')
            assert after[2:5] == tuple(value + 1 for value in before[2:5])
        async with c.session() as other:
            await mutate(other)
            await other.commit()
        denied = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert denied.status_code in (401, 403, 404), denied.text
        assert await snapshot() == after


@pytest.mark.parametrize('mode', ['pause', 'cancel', 'blocked_cancel', 'pause_replay', 'cancel_replay'])
async def test_stop_conflicting_control_acl_writer_fails_closed_then_retries(d4_text_server, mode):
    from sqlalchemy import event
    c = d4_text_server
    if mode == 'blocked_cancel':
        revoked = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}',
                                      json={'enabled': False})
        assert revoked.status_code == 200, revoked.text
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = UUID(created.json()['task_id'])
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        if mode == 'blocked_cancel':
            run_id, epoch = None, None
        else:
            claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
                'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
            assert claim.status_code == 200, claim.text
            run_id, epoch = claim.json()['run_id'], claim.json()['lease_epoch']
        action = 'cancel' if mode in ('cancel', 'blocked_cancel', 'cancel_replay') else 'pause'
        body = {'action': action, 'run_id': run_id, 'expected_epoch': epoch, 'idempotency_key': uuid4().hex}
        if mode.endswith('_replay'):
            first = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
            assert first.status_code == 200, first.text
        async def snapshot():
            async with c.session() as db:
                task = await db.get(AgentTask, task_id)
                runs = (await db.execute(select(AgentRun.status, AgentRun.lease_epoch, AgentRun.claim_key,
                    AgentRun.lease_expires_at).where(AgentRun.task_id == task_id))).all()
                controls = await db.scalar(select(func.count()).select_from(AgentTaskControl).where(
                    AgentTaskControl.task_id == task_id))
                pointers = await db.scalar(select(func.count()).select_from(AgentTaskUpdate).where(
                    AgentTaskUpdate.task_id == task_id))
                audits = await db.scalar(select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == 'CONTROL_AGENT_TASK', AuditLog.changed_fields['task_id'].astext == str(task_id)))
                messages = (await db.execute(select(AgentTaskMessage.message_id, AgentTaskMessage.state,
                    AgentTaskMessage.delivery_batch_id, AgentTaskMessage.delivery_epoch).where(
                    AgentTaskMessage.task_id == task_id).order_by(AgentTaskMessage.sequence))).all()
                return task.status, tuple(tuple(row) for row in runs), controls, pointers, audits, tuple(messages)
        before = await snapshot()
        statements = []
        def witness(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())
        async with c.session() as writer:
            await writer.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                RolePermission.module == 'capa').values(permission_level=RolePermission.permission_level))
            event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
            try:
                blocked = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
            finally:
                event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
            assert blocked.status_code == 503 and blocked.json() == {'detail': 'Recovery unavailable'}, blocked.text
            assert not any('capa_eightd.d4_root_cause' in sql or 'from fmea_documents' in sql
                           or 'jsonb_array_elements' in sql for sql in statements)
            assert await snapshot() == before
            await writer.commit()
        retry = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert retry.status_code == 200, retry.text
        if mode.endswith('_replay'):
            assert await snapshot() == before


@pytest.mark.parametrize('mode', ['pause', 'blocked_cancel', 'pause_replay'])
async def test_stop_fences_new_factory_assignment_until_commit(d4_text_server, monkeypatch, mode):
    from app.models.factory import Factory
    from app.services.agent_runtime import task_controls
    c = d4_text_server
    other_factory = uuid4()
    async with c.session() as db:
        db.add(Factory(id=other_factory, code='STOP-' + uuid4().hex[:10], name='owned stop test'))
        await db.commit()
    if mode == 'blocked_cancel':
        disabled = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}', json={'enabled': False})
        assert disabled.status_code == 200
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = UUID(created.json()['task_id'])
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        if mode == 'blocked_cancel':
            run_id, epoch = None, None
        else:
            claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
                'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
            run_id, epoch = claim.json()['run_id'], claim.json()['lease_epoch']
        body = {'action': 'cancel' if mode == 'blocked_cancel' else 'pause', 'run_id': run_id,
                'expected_epoch': epoch, 'idempotency_key': uuid4().hex}
        if mode == 'pause_replay':
            first = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
            assert first.status_code == 200, first.text
        original, calls, conflicts = task_controls._user_authority, 0, []
        async def insert_after_check(*args, **kwargs):
            nonlocal calls
            result = await original(*args, **kwargs)
            calls += 1
            if calls == (3 if mode == 'blocked_cancel' else 4):
                async with c.session() as writer:
                    await writer.execute(text("SET LOCAL lock_timeout = '200ms'"))
                    try:
                        writer.add(UserFactory(user_id=c.user_id, factory_id=other_factory))
                        await writer.commit()
                    except DBAPIError as exc:
                        conflicts.append(getattr(exc.orig, 'sqlstate', None))
                assert conflicts == ['55P03']
            return result
        monkeypatch.setattr(task_controls, '_user_authority', insert_after_check)
        result = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert result.status_code == 200 and conflicts == ['55P03'], result.text
        async with c.session() as writer:
            writer.add(UserFactory(user_id=c.user_id, factory_id=other_factory))
            await writer.commit()


@pytest.mark.parametrize('writer_kind', ['factory_replace', 'mixed_user_update', 'capa_audit'])
async def test_stop_conflicts_do_not_deadlock_business_writers(d4_text_server, writer_kind):
    import asyncio
    from sqlalchemy.sql.dml import Delete
    from app.models.capa import CAPAEightD
    from app.services.user_service import update_user
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
        body = {'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
                'idempotency_key': uuid4().hex}
        async with c.session() as writer:
            await writer.execute(text("SET LOCAL lock_timeout = '2s'"))
            pending_writer = None
            allow_writer = asyncio.Event()
            try:
                if writer_kind == 'factory_replace':
                    await writer.execute(delete(UserFactory).where(UserFactory.user_id == c.user_id,
                        UserFactory.factory_id == c.factory_id))
                elif writer_kind == 'capa_audit':
                    await writer.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report_id)
                                         .values(status=CAPAEightD.status))
                else:
                    initial_user_update = asyncio.Event()
                    execute = writer.execute
                    async def gated_execute(statement, *args, **kwargs):
                        if isinstance(statement, Delete) and statement.table.name == 'user_factories':
                            await writer.flush()  # same autoflush as the real service
                            initial_user_update.set()
                            await asyncio.wait_for(allow_writer.wait(), timeout=10)
                        return await execute(statement, *args, **kwargs)
                    writer.execute = gated_execute
                    async def update_employee():
                        await update_user(writer, c.user_id, {'display_name': 'updated stop user',
                            'factory_ids': [c.factory_id]}, c.admin_user_id)
                        await writer.commit()
                    pending_writer = asyncio.create_task(update_employee())
                    await asyncio.wait_for(initial_user_update.wait(), timeout=10)
                blocked = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
                assert blocked.status_code == 503 and blocked.json() == {'detail': 'Recovery unavailable'}, blocked.text
                async with c.session() as db:
                    assert await db.scalar(select(func.count()).select_from(AgentTaskControl).where(
                        AgentTaskControl.task_id == task_id)) == 0
                    assert await db.scalar(select(func.count()).select_from(AuditLog).where(
                        AuditLog.action == 'CONTROL_AGENT_TASK', AuditLog.changed_fields['task_id'].astext == str(task_id))) == 0
                if writer_kind == 'factory_replace':
                    writer.add(UserFactory(user_id=c.user_id, factory_id=c.factory_id))
                    await writer.commit()
                elif writer_kind == 'capa_audit':
                    writer.add(AuditLog(table_name='capa_eightd', record_id=c.report_id, action='UPDATE',
                        operated_by=c.user_id, factory_id=c.factory_id, changed_fields={}))
                    await writer.commit()
                else:
                    allow_writer.set()
                    await asyncio.wait_for(pending_writer, timeout=10)
            finally:
                allow_writer.set()
                if pending_writer is not None and not pending_writer.done():
                    pending_writer.cancel()
                    await asyncio.gather(pending_writer, return_exceptions=True)
        retry = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json=body)
        assert retry.status_code == 200 and retry.json()['task_status'] == 'paused', retry.text


async def test_legacy_metadata_pause_conflict_and_normal_controls(owned_local_trial):
    c = owned_local_trial
    await c.enable()
    task = await c.create()
    assert task['status'] == 'ready'
    task_id = UUID(task['task_id'])
    claimed = await c.claim(uuid4().hex)
    assert claimed.status_code == 200, claimed.text
    run = claimed.json()
    body = {'action': 'pause', 'run_id': run['run_id'], 'expected_epoch': run['lease_epoch'],
            'idempotency_key': uuid4().hex}
    async with c.session() as writer:
        await writer.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
            RolePermission.module == 'capa').values(permission_level=RolePermission.permission_level))
        blocked = await c.client.post(f'/api/agent/tasks/{task_id}/control', json=body)
        assert blocked.status_code == 503 and blocked.json() == {'detail': 'Recovery unavailable'}, blocked.text
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(AgentTaskControl).where(
                AgentTaskControl.task_id == task_id)) == 0
        await writer.commit()
    pause = await c.client.post(f'/api/agent/tasks/{task_id}/control', json=body)
    assert pause.status_code == 200 and pause.json()['task_status'] == 'paused', pause.text
    resume = await c.client.post(f'/api/agent/tasks/{task_id}/control', json={'action': 'resume',
        'run_id': run['run_id'], 'expected_epoch': pause.json()['lease_epoch'], 'idempotency_key': uuid4().hex})
    assert resume.status_code == 200 and resume.json()['task_status'] == 'ready', resume.text
    cancel = await c.client.post(f'/api/agent/tasks/{task_id}/control', json={'action': 'cancel',
        'run_id': run['run_id'], 'expected_epoch': resume.json()['lease_epoch'], 'idempotency_key': uuid4().hex})
    assert cancel.status_code == 200 and cancel.json()['task_status'] == 'cancelled', cancel.text


@pytest.mark.parametrize('withdrawal', ['fmea', 'grant', 'plugin'])
async def test_stop_never_requires_current_fmea_or_plugin_authority(d4_text_server, withdrawal):
    from sqlalchemy import event
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = created.json()['task_id']
    headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        run = claim.json()
        if withdrawal == 'fmea':
            async with c.session() as db:
                await db.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                    RolePermission.module == 'fmea').values(permission_level=0))
                await db.commit()
        elif withdrawal == 'grant':
            result = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}',
                                         json={'enabled': False})
            assert result.status_code == 200, result.text
        else:
            result = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}', json={'enabled': False})
            assert result.status_code == 200, result.text
        statements = []
        def witness(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
                'action': 'pause', 'run_id': run['run_id'], 'expected_epoch': run['lease_epoch'],
                'idempotency_key': uuid4().hex})
            assert pause.status_code == 200 and pause.json()['task_status'] == 'paused', pause.text
            cancel = await client.post(f'/api/agent/tasks/{task_id}/control', headers=headers, json={
                'action': 'cancel', 'run_id': run['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
                'idempotency_key': uuid4().hex})
            assert cancel.status_code == 200 and cancel.json()['task_status'] == 'cancelled', cancel.text
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
        assert not any('capa_eightd.d4_root_cause' in sql or 'from fmea_documents' in sql
                       or 'jsonb_array_elements' in sql or 'agent_plugin_grants' in sql
                       or 'agent_task_grants' in sql for sql in statements)
