"""Checkpoint requires current task control authority at its commit boundary."""
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.models.agent_d4_recovery import D4RecoveryCheckpoint
from app.models.agent_readonly_control import AgentTaskUpdate
from app.models.audit import AuditLog
from app.models.factory import UserFactory
from app.models.role import RolePermission, UserProductLine
from app.models.user import User
from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
from tests.e2e.d4_text_local_harness import d4_text_local_trial, d4_text_server, owned_local_trial

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]


@pytest.mark.parametrize('revocation', ['user', 'capa_permission', 'factory_scope', 'line_scope', 'fmea_permission'])
async def test_checkpoint_final_control_authority_change_before_commit(d4_text_server, monkeypatch, revocation):
    from app.services.agent_runtime import d4_recovery
    c = d4_text_server
    if revocation == 'factory_scope':
        async with c.session() as db:
            await db.execute(update(User).where(User.user_id == c.user_id).values(factory_id=None))
            await db.commit()
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
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
        async def snapshot():
            async with c.session() as db:
                cp = await db.scalar(select(func.count()).select_from(D4RecoveryCheckpoint).where(
                    D4RecoveryCheckpoint.task_id == task_id))
                pointers = await db.scalar(select(func.count()).select_from(AgentTaskUpdate).where(
                    AgentTaskUpdate.task_id == task_id, AgentTaskUpdate.kind == 'checkpoint'))
                audits = await db.scalar(select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == 'SAVE_AGENT_D4_RECOVERY_CHECKPOINT',
                    AuditLog.changed_fields['task_id'].astext == str(task_id)))
                return cp, pointers, audits
        before = await snapshot()
        original = d4_recovery._fresh_authority
        attempts = []
        async def mutate(other):
            if revocation == 'user':
                await other.execute(update(User).where(User.user_id == c.user_id).values(is_active=False))
            elif revocation in ('capa_permission', 'fmea_permission'):
                module = 'capa' if revocation == 'capa_permission' else 'fmea'
                await other.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                    RolePermission.module == module).values(permission_level=0))
            elif revocation == 'factory_scope':
                await other.execute(delete(UserFactory).where(UserFactory.user_id == c.user_id,
                    UserFactory.factory_id == c.factory_id))
            else:
                await other.execute(delete(UserProductLine).where(UserProductLine.user_id == c.user_id,
                    UserProductLine.product_line_code == c.line))
        async def revoke_after_final_check(db, scope, tid, task_binding, run_binding):
            value = await original(db, scope, tid, task_binding, run_binding)
            row = await db.scalar(select(D4RecoveryCheckpoint.checkpoint_id).where(
                D4RecoveryCheckpoint.task_id == task_id))
            if row is not None:
                async with c.session() as other:
                    await other.execute(text("SET LOCAL lock_timeout = '200ms'"))
                    try:
                        await mutate(other)
                        await other.commit()
                        attempts.append('committed')
                    except DBAPIError as exc:
                        attempts.append(getattr(exc.orig, 'sqlstate', None))
            return value
        monkeypatch.setattr(d4_recovery, '_fresh_authority', revoke_after_final_check)
        result = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=headers,
            json={'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        assert result.status_code == 200, result.text
        after = await snapshot()
        assert after == tuple(value + 1 for value in before)
        if revocation == 'fmea_permission':
            # No source authorization lock is allowed for a control checkpoint.
            assert attempts == ['committed']
        else:
            assert attempts == ['55P03']
            async with c.session() as other:
                await mutate(other)
                await other.commit()
        view = await client.get(f"/api/agent/tasks/{task_id}/d4-recovery-checkpoints/{result.json()['checkpoint_id']}",
                                headers=headers)
        if revocation == 'fmea_permission':
            assert view.status_code == 200, view.text
        else:
            assert view.status_code in (401, 403, 404), view.text


async def test_unrelated_admin_cannot_control_or_create_checkpoint_for_other_executor(d4_text_server):
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    task_id = UUID(created.json()['task_id'])
    async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        old = claim.json()
        admin_headers = {'Authorization': 'Bearer ' + c.admin_token, 'X-Tenant-ID': c.slug}
        denied = await client.post(f'/api/agent/tasks/{task_id}/control', headers=admin_headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert denied.status_code in (403, 404), denied.text
        denied_cp = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=admin_headers,
            json={'run_id': old['run_id'], 'expected_epoch': old['lease_epoch']})
        assert denied_cp.status_code in (403, 404), denied_cp.text
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(D4RecoveryCheckpoint).where(
                D4RecoveryCheckpoint.task_id == task_id)) == 0
            assert await db.scalar(select(func.count()).select_from(AgentTaskUpdate).where(
                AgentTaskUpdate.task_id == task_id, AgentTaskUpdate.kind == 'checkpoint')) == 0


@pytest.mark.parametrize('timing', ['writer_first', 'control_first'])
async def test_checkpoint_authority_insertion_is_serialized(d4_text_server, monkeypatch, timing):
    from app.models.factory import Factory
    from app.services.agent_runtime import d4_recovery
    c = d4_text_server
    factory_id = uuid4()
    async with c.session() as db:
        db.add(Factory(id=factory_id, code='D4-' + uuid4().hex[:12], name='owned ACL insertion fixture'))
        await db.commit()
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
        body = {'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']}
        path = f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints'
        if timing == 'writer_first':
            async with c.session() as writer:
                writer.add(UserFactory(user_id=c.user_id, factory_id=factory_id))
                await writer.flush()  # FK KEY SHARE precedes the control's NOWAIT parent lock.
                denied = await client.post(path, headers=headers, json=body)
                assert denied.status_code == 503 and denied.json() == {'detail': 'Recovery unavailable'}, denied.text
                async with c.session() as db:
                    assert await db.scalar(select(func.count()).select_from(D4RecoveryCheckpoint).where(
                        D4RecoveryCheckpoint.task_id == task_id)) == 0
                await writer.commit()
            result = await client.post(path, headers=headers, json=body)
            assert result.status_code == 200, result.text
        else:
            original, conflicts = d4_recovery._fresh_authority, []
            async def insert_after_final_check(db, scope, tid, task_binding, run_binding):
                result = await original(db, scope, tid, task_binding, run_binding)
                row = await db.scalar(select(D4RecoveryCheckpoint.checkpoint_id).where(
                    D4RecoveryCheckpoint.task_id == task_id))
                if row is not None:
                    async with c.session() as writer:
                        await writer.execute(text("SET LOCAL lock_timeout = '200ms'"))
                        try:
                            writer.add(UserFactory(user_id=c.user_id, factory_id=factory_id))
                            await writer.commit()
                        except DBAPIError as exc:
                            conflicts.append(getattr(exc.orig, 'sqlstate', None))
                return result
            monkeypatch.setattr(d4_recovery, '_fresh_authority', insert_after_final_check)
            result = await client.post(path, headers=headers, json=body)
            assert result.status_code == 200 and conflicts == ['55P03'], result.text
            async with c.session() as writer:
                writer.add(UserFactory(user_id=c.user_id, factory_id=factory_id))
                await writer.commit()
