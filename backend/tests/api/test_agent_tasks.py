"""Default-off routes and current target admission, through the real ASGI app."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

from app.config import settings
from app.core.deps import get_current_user, get_request_scope
from app.main import app
from app.models.agent_task import AgentTaskMessage
from app.models.factory import UserFactory
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from tests.services.agent_runtime.conftest import committed_runtime, enabled_plugin, sample_capa


@pytest.fixture(autouse=True)
def runtime_enabled(monkeypatch):
    monkeypatch.setitem(settings.__dict__, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(settings, 'TENANT_MODE', 'single')


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['single', 'dev', 'production'])
async def test_disabled_paths_404_before_auth_body_or_tenant_resolution(monkeypatch, mode):
    monkeypatch.setitem(settings.__dict__, 'AGENT_TASK_RUNTIME_ENABLED', False)
    monkeypatch.setattr(settings, 'TENANT_MODE', mode)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for method, path in [('GET', '/api/agent/tasks'), ('POST', '/api/agent/tasks'),
            ('GET', '/api/agent/tasks/bad-id'), ('POST', '/api/agent/tasks/bad-id/messages'),
            ('GET', '/api/admin/agent-plugins'), ('POST', '/api/admin/agent-plugins'),
            ('PATCH', '/api/admin/agent-plugins/bad-id'),
            ('POST', '/api/admin/agent-plugins/bad-id/rotate-secret'),
            ('GET', '/api/admin/agent-plugins/bad-id/grants'),
            ('POST', '/api/admin/agent-plugins/bad-id/grants'),
            ('PATCH', '/api/admin/agent-plugins/bad-id/grants/bad-id')]:
            response = await client.request(method, path, content='invalid json',
                headers={'X-Tenant-ID': 'invalid-tenant', 'Authorization': 'Bearer invalid'})
            assert response.status_code == 404, (mode, path, response.text)
            unauthenticated = await client.request(method, path, content='invalid json')
            assert unauthenticated.status_code == 404, (mode, path, unauthenticated.text)
        # Exact prefixes: unrelated routes still follow ordinary tenant/auth admission.
        response = await client.get('/api/agent/sessions')
        assert response.status_code in ([401] if mode == 'single' else [400])
        response = await client.get('/api/agent/tasks-extra')
        assert response.status_code == (404 if mode == 'single' else 400)


@pytest.mark.asyncio
async def test_create_list_detail_append_are_safe_and_idempotent(admin_client, sample_capa,
                                                               enabled_plugin, db):
    request = dict(report_id=str(sample_capa.report_id), installation_id=str(enabled_plugin.installation_id),
        request_key='create-key', initial_text='private investigation')
    created = await admin_client.post('/api/agent/tasks', json=request)
    assert created.status_code == 201, created.text
    task = created.json()
    assert task['status'] == 'blocked_capability'
    assert set(task) == {'task_id', 'target_capa_id', 'factory_id', 'preferred_installation_id',
        'status', 'created_at', 'updated_at'}
    task_url = '/api/agent/tasks/' + task['task_id']
    assert (await admin_client.get(task_url)).json() == task
    listed = (await admin_client.get('/api/agent/tasks')).json()
    assert listed['total'] == 1 and listed['items'] == [task]
    repeated = await admin_client.post('/api/agent/tasks', json=request)
    assert repeated.status_code == 201 and repeated.json()['task_id'] == task['task_id']
    conflict = await admin_client.post('/api/agent/tasks', json={**request, 'initial_text': 'different'})
    assert conflict.status_code == 409
    message = dict(content='private follow-up', idempotency_key='message-key')
    accepted = await admin_client.post(task_url + '/messages', json=message)
    assert accepted.status_code == 202, accepted.text
    assert set(accepted.json()) == {'message_id', 'sequence', 'state'}
    assert accepted.json()['sequence'] == 2 and accepted.json()['state'] == 'queued'
    retry = await admin_client.post(task_url + '/messages', json=message)
    assert retry.status_code == 202 and retry.json() == accepted.json()
    conflict = await admin_client.post(task_url + '/messages', json={**message, 'content': 'changed'})
    assert conflict.status_code == 409
    persisted = await db.scalar(select(AgentTaskMessage).where(
        AgentTaskMessage.message_id == uuid.UUID(accepted.json()['message_id'])))
    assert persisted.content == message['content']
    assert 'private' not in str(listed)


@pytest.mark.asyncio
async def test_routes_reject_identity_fields_and_invalid_pagination(admin_client, sample_capa, enabled_plugin):
    request = dict(report_id=str(sample_capa.report_id), installation_id=str(enabled_plugin.installation_id),
        request_key='key', initial_text='text')
    for key in ['user', 'actor', 'scope', 'factory_id', 'executor_user_id', 'schema', 'grant']:
        response = await admin_client.post('/api/agent/tasks', json={**request, key: 'untrusted'})
        assert response.status_code == 422
    created = await admin_client.post('/api/agent/tasks', json=request)
    url = '/api/agent/tasks/' + created.json()['task_id'] + '/messages'
    assert (await admin_client.post(url, json=dict(content='text', idempotency_key='key', author_id=str(uuid.uuid4())))).status_code == 422
    for query in ['page=0', 'page_size=101', 'page_size=0']:
        assert (await admin_client.get('/api/agent/tasks?' + query)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize('revoke', ['permission', 'user', 'role'])
async def test_current_rights_rechecked_even_with_cached_scope(admin_client, sample_capa, enabled_plugin,
                                                             admin_user, db, revoke):
    request = dict(report_id=str(sample_capa.report_id), installation_id=str(enabled_plugin.installation_id),
        request_key='key', initial_text='text')
    created = await admin_client.post('/api/agent/tasks', json=request)
    assert created.status_code == 201
    url = '/api/agent/tasks/' + created.json()['task_id']
    if revoke == 'permission':
        await db.execute(update(RolePermission).where(RolePermission.role_id == admin_user.role_id,
            RolePermission.module == 'capa').values(permission_level=0))
    elif revoke == 'user':
        await db.execute(update(User).where(User.user_id == admin_user.user_id).values(is_active=False))
    else:
        await db.execute(update(RoleDefinition).where(RoleDefinition.id == admin_user.role_id).values(is_active=False))
    responses = [await admin_client.get(url), await admin_client.get('/api/agent/tasks'),
        await admin_client.post('/api/agent/tasks', json=request),
        await admin_client.post(url + '/messages', json=dict(content='text', idempotency_key='new'))]
    assert [r.status_code for r in responses] == [403]*4


@pytest.mark.asyncio
async def test_foreign_and_missing_tasks_hide_existence(admin_client, sample_capa, enabled_plugin,
                                                      other_admin_user, default_factory):
    from app.core.deps import RequestScope
    from app.core.factory_scope import FactoryScope, ProductLineScope
    created = await admin_client.post('/api/agent/tasks', json=dict(report_id=str(sample_capa.report_id),
        installation_id=str(enabled_plugin.installation_id), request_key='key', initial_text='text'))
    assert created.status_code == 201
    app.dependency_overrides[get_current_user] = lambda: other_admin_user
    app.dependency_overrides[get_request_scope] = lambda: RequestScope(FactoryScope(None, default_factory.id),
        default_factory.id, ProductLineScope('ALL', None), other_admin_user)
    for task_id in [created.json()['task_id'], str(uuid.uuid4())]:
        url = '/api/agent/tasks/' + task_id
        assert (await admin_client.get(url)).status_code == 404
        assert (await admin_client.post(url + '/messages', json=dict(content='text', idempotency_key='new'))).status_code == 404
    assert (await admin_client.get('/api/agent/tasks')).json()['total'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('membership', ['factory', 'line'])
async def test_membership_revoke_filters_items_and_total(admin_client, sample_capa, enabled_plugin,
                                                        admin_user, db, membership):
    await db.execute(update(RoleDefinition).where(RoleDefinition.id == admin_user.role_id)
        .values(bypass_row_level_security=False))
    await db.execute(update(RolePermission).where(RolePermission.role_id == admin_user.role_id,
        RolePermission.module == 'group').values(permission_level=0))
    await db.execute(update(User).where(User.user_id == admin_user.user_id).values(factory_id=None))
    db.add(UserFactory(user_id=admin_user.user_id, factory_id=sample_capa.factory_id))
    db.add(UserProductLine(user_id=admin_user.user_id, product_line_code=sample_capa.product_line_code))
    await db.flush()
    created = await admin_client.post('/api/agent/tasks', json=dict(report_id=str(sample_capa.report_id),
        installation_id=str(enabled_plugin.installation_id), request_key='key', initial_text='text'))
    assert created.status_code == 201
    model = UserFactory if membership == 'factory' else UserProductLine
    await db.execute(delete(model).where(model.user_id == admin_user.user_id))
    url = '/api/agent/tasks/' + created.json()['task_id']
    assert (await admin_client.get(url)).status_code == 404
    assert (await admin_client.post(url + '/messages', json=dict(content='text', idempotency_key='new'))).status_code == 404
    assert (await admin_client.get('/api/agent/tasks')).json() == dict(items=[], total=0, page=1, page_size=20)


@pytest.mark.asyncio
async def test_complete_tenant_jwt_api_commits_survive_new_sessions(committed_runtime, monkeypatch):
    """No dependency overrides: real middleware, JWT, scope and TenantSession."""
    import app.database as database
    from app.core.security import create_access_token
    from app.models.agent_plugin import AgentPluginInstallation
    from app.models.agent_task import AgentTask
    from app.services.agent_runtime.plugin_registry import verify_plugin_secret

    owned = committed_runtime
    monkeypatch.setattr(database, 'tenant_async_session', owned.factory)
    token = create_access_token({'sub': str(owned.user_id), 'tenant_id': str(owned.binding.tenant_id)})
    assert not app.dependency_overrides
    async with owned.factory(binding=owned.binding) as observer:
        existing = await observer.get(AgentTask, owned.task_id)
        target_id = existing.target_capa_id
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test',
                           headers={'Authorization': 'Bearer ' + token}) as client:
        registered = await client.post('/api/admin/agent-plugins', json=dict(plugin_key='api-committed',
            plugin_version='1', manifest={'protocol_versions': ['1']}))
        assert registered.status_code == 201, registered.text
        plugin_id = uuid.UUID(registered.json()['plugin']['installation_id'])
        plugin_url = '/api/admin/agent-plugins/' + str(plugin_id)
        old_secret = registered.json()['secret']
        assert (await client.patch(plugin_url, json={'enabled': True})).status_code == 200
        rotated = await client.post(plugin_url + '/rotate-secret')
        assert rotated.status_code == 200
        new_secret = rotated.json()['secret']
        request = dict(report_id=str(target_id), installation_id=str(plugin_id),
            request_key=uuid.uuid4().hex, initial_text='durable initial instruction')
        created = await client.post('/api/agent/tasks', json=request)
        assert created.status_code == 201, created.text
        task_id = uuid.UUID(created.json()['task_id'])
        message = await client.post('/api/agent/tasks/' + str(task_id) + '/messages',
            json=dict(content='durable follow-up', idempotency_key='follow-up'))
        assert message.status_code == 202, message.text
        # Every request has already closed its writer session before observation.
        async with owned.factory(binding=owned.binding) as observer:
            persisted = await observer.get(AgentTask, task_id)
            assert persisted.initiator_id == owned.user_id and persisted.status == 'blocked_capability'
            instructions = list((await observer.scalars(select(AgentTaskMessage).where(
                AgentTaskMessage.task_id == task_id).order_by(AgentTaskMessage.sequence))).all())
            assert [m.content for m in instructions] == ['durable initial instruction', 'durable follow-up']
            assert (await observer.get(AgentPluginInstallation, plugin_id)).credential_epoch == 1
            with pytest.raises(PermissionError):
                await verify_plugin_secret(observer, plugin_id, old_secret)
            await verify_plugin_secret(observer, plugin_id, new_secret)
        assert (await client.get('/api/agent/tasks/' + str(task_id))).status_code == 200
        async with owned.factory(binding=owned.binding) as revoker:
            await revoker.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id,
                RolePermission.module == 'capa').values(permission_level=0))
            await revoker.commit()
        assert (await client.get('/api/agent/tasks/' + str(task_id))).status_code == 403


@pytest.mark.asyncio
async def test_synthetic_direct_admin_grant_can_prepare_pending_run(admin_client, db, sample_capa, monkeypatch):
    """DIRECT is test-only; production catalog remains DENY."""
    from dataclasses import replace
    from types import MappingProxyType
    from app.models.agent_task import AgentRun, AgentTaskGrant
    from app.services.agent.permissions import catalog
    from app.services.agent.permissions.types import ApprovalFloor
    summary = 'capa.d4.summary.masked.v1'
    spec = replace(catalog.get_capability(summary), approval_floor=ApprovalFloor.DIRECT)
    monkeypatch.setattr(catalog, 'CAPA_CAPABILITIES', MappingProxyType({**catalog.CAPA_CAPABILITIES, summary: spec}))
    registered = await admin_client.post('/api/admin/agent-plugins', json=dict(plugin_key='direct-test',
        plugin_version='1', manifest=dict(protocol_versions=['1'], required_capabilities=[summary])))
    assert registered.status_code == 201
    plugin_id = registered.json()['plugin']['installation_id']
    url = '/api/admin/agent-plugins/' + plugin_id
    assert (await admin_client.patch(url, json={'enabled': True})).status_code == 200
    grant = await admin_client.post(url+'/grants', json=dict(capability_id=summary,
        factory_ids=[str(sample_capa.factory_id)], product_line_codes=[sample_capa.product_line_code],
        object_ids=[str(sample_capa.report_id)], expires_at='2099-01-01T00:00:00+00:00', enabled=True))
    assert grant.status_code == 201, grant.text
    created = await admin_client.post('/api/agent/tasks', json=dict(report_id=str(sample_capa.report_id),
        installation_id=plugin_id, request_key='direct-test', initial_text='text'))
    assert created.status_code == 201 and created.json()['status'] == 'ready'
    task_id = uuid.UUID(created.json()['task_id'])
    run = await db.scalar(select(AgentRun).where(AgentRun.task_id == task_id))
    assert run.status == 'pending'
    fixed = await db.scalar(select(AgentTaskGrant).where(AgentTaskGrant.task_id == task_id))
    assert fixed.factory_ids == [str(sample_capa.factory_id)] and fixed.object_ids == [str(sample_capa.report_id)]


def test_runtime_flag_defaults_off(monkeypatch):
    from app.config import Settings
    monkeypatch.delenv('AGENT_TASK_RUNTIME_ENABLED', raising=False)
    assert Settings(_env_file=None, SECRET_KEY='test-only').AGENT_TASK_RUNTIME_ENABLED is False


@pytest.mark.asyncio
async def test_append_hides_task_changed_during_row_lock_wait(committed_runtime, monkeypatch):
    """The post-lock LookupError must become 404, not a server error."""
    import asyncio
    import app.database as database
    from sqlalchemy import event
    from app.core.security import create_access_token
    from app.models.agent_task import AgentTask
    owned = committed_runtime
    monkeypatch.setattr(database, 'tenant_async_session', owned.factory)
    token = create_access_token({'sub': str(owned.user_id), 'tenant_id': str(owned.binding.tenant_id)})
    attempted = asyncio.Event()
    def notice_lock(conn, cursor, statement, parameters, context, executemany):
        if 'agent_tasks' in statement and 'FOR UPDATE' in statement:
            attempted.set()
    async with owned.factory(binding=owned.binding) as holder:
        locked = await holder.scalar(select(AgentTask).where(AgentTask.task_id == owned.task_id).with_for_update())
        other = User(user_id=uuid.uuid4(), username=uuid.uuid4().hex, password_hash='fixture',
            role_id=owned.role_id, legacy_role='admin', is_active=True)
        holder.add(other)
        await holder.flush()
        event.listen(owned.engine.sync_engine, 'before_cursor_execute', notice_lock)
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test',
                               headers={'Authorization': 'Bearer ' + token}) as client:
            pending = asyncio.create_task(client.post('/api/agent/tasks/' + str(owned.task_id) + '/messages',
                json=dict(content='private message', idempotency_key='race')))
            lock_notice = asyncio.create_task(attempted.wait())
            try:
                done, _ = await asyncio.wait({pending, lock_notice}, timeout=10,
                    return_when=asyncio.FIRST_COMPLETED)
                if pending in done:
                    response = pending.result()
                    pytest.fail(f"Append completed before the lock: {response.status_code} {response.text}; "
                        f"mode={settings.TENANT_MODE}, runtime={settings.AGENT_TASK_RUNTIME_ENABLED}, "
                        f"overrides={[dependency.__name__ for dependency in app.dependency_overrides]}")
                assert lock_notice in done, "Append neither reached the lock nor completed within 10 seconds"
                assert not pending.done()
                locked.executor_user_id = other.user_id
                await holder.commit()
                response = await asyncio.wait_for(pending, timeout=10)
                assert response.status_code == 404, response.text
            finally:
                event.remove(owned.engine.sync_engine, 'before_cursor_execute', notice_lock)
                if not lock_notice.done():
                    lock_notice.cancel()
                    await asyncio.gather(lock_notice, return_exceptions=True)
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
    async with owned.factory(binding=owned.binding) as observer:
        assert await observer.scalar(select(AgentTaskMessage).where(
            AgentTaskMessage.task_id == owned.task_id, AgentTaskMessage.idempotency_key == 'race')) is None
