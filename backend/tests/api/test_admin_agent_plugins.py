"""Safe, current-admin plugin configuration APIs."""
import asyncio
import uuid
from dataclasses import replace
from types import MappingProxyType

import pytest
from sqlalchemy import select, update

from app.config import settings
from app.core.deps import get_current_user
from app.main import app
from app.models.agent_plugin import AgentPluginGrant
from app.models.audit import AuditLog
from app.models.role import RoleDefinition, RolePermission
from app.models.user import User
from app.services.agent.permissions import catalog
from app.services.agent.permissions.types import ApprovalFloor
from app.services.agent_runtime.plugin_registry import verify_plugin_secret
from tests.services.agent_runtime.conftest import committed_runtime

SUMMARY = 'capa.d4.summary.masked.v1'


@pytest.fixture(autouse=True)
def runtime_enabled(monkeypatch):
    monkeypatch.setitem(settings.__dict__, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(settings, 'TENANT_MODE', 'single')


async def register(client):
    response = await client.post('/api/admin/agent-plugins', json=dict(plugin_key='test', plugin_version='1',
        manifest=dict(protocol_versions=['1'], required_capabilities=[SUMMARY])))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_register_rotate_list_detail_patch_keep_secrets_private(admin_client, db):
    registered = await register(admin_client)
    plugin, old_secret = registered['plugin'], registered['secret']
    assert plugin['enabled'] is False and plugin['credential_epoch'] == 0
    url = '/api/admin/agent-plugins/' + plugin['installation_id']
    detail = await admin_client.get(url)
    listed = await admin_client.get('/api/admin/agent-plugins')
    assert detail.status_code == listed.status_code == 200
    assert detail.json() == plugin and listed.json()['items'] == [plugin]
    assert listed.json()['total'] == 1
    assert 'secret' not in detail.text and 'secret' not in listed.text
    enabled = await admin_client.patch(url, json={'enabled': True})
    assert enabled.status_code == 200 and enabled.json()['enabled'] is True
    rotated = await admin_client.post(url + '/rotate-secret')
    assert rotated.status_code == 200
    assert rotated.json()['plugin']['credential_epoch'] == 1
    assert rotated.json()['secret'] != old_secret
    with pytest.raises(PermissionError):
        await verify_plugin_secret(db, uuid.UUID(plugin['installation_id']), old_secret)
    await verify_plugin_secret(db, uuid.UUID(plugin['installation_id']), rotated.json()['secret'])
    audits = list((await db.scalars(select(AuditLog))).all())
    assert old_secret not in str([a.changed_fields for a in audits])
    assert rotated.json()['secret'] not in str([a.changed_fields for a in audits])
    assert 'hash' not in str([a.changed_fields for a in audits])
    assert (await admin_client.post('/api/admin/agent-plugins', json=dict(plugin_key='test', plugin_version='1',
        manifest=dict(protocol_versions=['1'])))).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('revoke', ['permission', 'role', 'user', 'viewer'])
async def test_every_admin_endpoint_requires_fresh_active_admin(admin_client, admin_user, viewer_user, db, revoke):
    plugin = (await register(admin_client))['plugin']
    url = '/api/admin/agent-plugins/' + plugin['installation_id']
    if revoke == 'permission':
        await db.execute(update(RolePermission).where(RolePermission.role_id == admin_user.role_id,
            RolePermission.module == 'permission_mgmt').values(permission_level=0))
    elif revoke == 'role':
        await db.execute(update(RoleDefinition).where(RoleDefinition.id == admin_user.role_id).values(is_active=False))
    elif revoke == 'user':
        await db.execute(update(User).where(User.user_id == admin_user.user_id).values(is_active=False))
    else:
        app.dependency_overrides[get_current_user] = lambda: viewer_user
    calls = [('GET', '/api/admin/agent-plugins', None), ('GET', url, None),
        ('POST', '/api/admin/agent-plugins', dict(plugin_key='other', plugin_version='1', manifest=dict(protocol_versions=['1']))),
        ('PATCH', url, {'enabled': True}), ('POST', url+'/rotate-secret', None),
        ('GET', url+'/grants', None), ('POST', url+'/grants', dict(capability_id=SUMMARY, factory_ids=[str(uuid.uuid4())])),
        ('PATCH', url+'/grants/'+str(uuid.uuid4()), {'enabled': False})]
    for method, path, payload in calls:
        assert (await admin_client.request(method, path, json=payload)).status_code == 403, path


@pytest.mark.asyncio
async def test_strict_typed_grants_default_disabled_and_catalog_cannot_be_enabled(admin_client, db, default_factory):
    plugin = (await register(admin_client))['plugin']
    url = '/api/admin/agent-plugins/' + plugin['installation_id']
    body = dict(capability_id=SUMMARY, factory_ids=[str(default_factory.id)])
    response = await admin_client.post(url + '/grants', json=body)
    assert response.status_code == 201, response.text
    grant = response.json()
    assert grant['enabled'] is False
    assert grant['factory_ids'] == body['factory_ids']
    assert set(grant) == {'grant_id', 'installation_id', 'capability_id', 'factory_ids',
        'product_line_codes', 'object_ids', 'expires_at', 'enabled', 'granted_by'}
    assert (await admin_client.get(url+'/grants')).json()['items'] == [grant]
    grant_url = url + '/grants/' + grant['grant_id']
    assert (await admin_client.patch(grant_url, json={'enabled': True})).status_code == 409
    assert (await admin_client.patch(url, json={'enabled': True})).status_code == 200
    persisted = await db.get(AgentPluginGrant, uuid.UUID(grant['grant_id']))
    assert persisted.enabled is False
    assert catalog.get_capability(SUMMARY).approval_floor == ApprovalFloor.DENY
    for bad in [dict(enabled=True), dict(factory_ids=[]), dict(factory_ids=['not-a-uuid']),
        dict(product_line_codes=[]), dict(object_ids=[]), dict(expires_at='2026-10-01T00:00:00'),
        dict(granted_by=str(uuid.uuid4())), dict(credential='unsafe'), dict(approval_floor='DIRECT')]:
        status = 409 if bad == {'enabled': True} else 422
        assert (await admin_client.post(url+'/grants', json={**body, **bad})).status_code == status
    for path in [url, grant_url]:
        assert (await admin_client.patch(path, json=dict(enabled=True, capability_id='unknown'))).status_code == 422
        assert (await admin_client.patch(path, json=dict(enabled='true'))).status_code == 422
    for query in ['page=0', 'page_size=101']:
        assert (await admin_client.get('/api/admin/agent-plugins?' + query)).status_code == 422
        assert (await admin_client.get(url+'/grants?' + query)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,floor', [('context', ApprovalFloor.DIRECT), ('context', ApprovalFloor.HUMAN),
    ('context', ApprovalFloor.MODEL_REVIEW), ('command', ApprovalFloor.DIRECT)])
async def test_only_canonical_direct_context_grants_can_be_enabled(admin_client, default_factory, monkeypatch, kind, floor):
    plugin = (await register(admin_client))['plugin']
    spec = replace(catalog.get_capability(SUMMARY), kind=kind, approval_floor=floor)
    monkeypatch.setattr(catalog, 'CAPA_CAPABILITIES', MappingProxyType({**catalog.CAPA_CAPABILITIES, SUMMARY: spec}))
    url = '/api/admin/agent-plugins/' + plugin['installation_id'] + '/grants'
    body = dict(capability_id=SUMMARY, factory_ids=[str(default_factory.id)], enabled=True)
    response = await admin_client.post(url, json=body)
    if kind == 'context' and floor == ApprovalFloor.DIRECT:
        assert response.status_code == 201
        grant_url = url + '/' + response.json()['grant_id']
        assert (await admin_client.patch(grant_url, json={'enabled': False})).status_code == 200
        monkeypatch.setattr(catalog, 'CAPA_CAPABILITIES', MappingProxyType({}))
        assert (await admin_client.patch(grant_url, json={'enabled': True})).status_code == 409
        assert (await admin_client.patch(grant_url, json={'enabled': False})).status_code == 200
    else:
        assert response.status_code == 409


@pytest.mark.asyncio
async def test_enable_audit_records_boolean_configuration(admin_client, db):
    registered = await register(admin_client)
    plugin_id = uuid.UUID(registered['plugin']['installation_id'])
    url = '/api/admin/agent-plugins/' + str(plugin_id)
    assert (await admin_client.patch(url, json={'enabled': True})).status_code == 200
    audit = await db.scalar(select(AuditLog).where(AuditLog.record_id == plugin_id,
        AuditLog.action == 'SET_PLUGIN_ENABLED'))
    assert audit.changed_fields['enabled'] is True


@pytest.mark.asyncio
async def test_admin_multi_namespace_denied_before_business_sql(db, admin_user, monkeypatch):
    from sqlalchemy import event
    from app.services.agent_runtime import plugin_registry as registry
    from app.schemas.agent_plugin import PluginGrantCreate
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    statements = []
    connection = await db.connection()
    event.listen(connection.sync_connection, 'before_cursor_execute',
        lambda conn, cursor, statement, parameters, context, executemany: statements.append(statement))
    plugin_id, grant_id = uuid.uuid4(), uuid.uuid4()
    request = PluginGrantCreate(capability_id=SUMMARY, factory_ids=[uuid.uuid4()])
    operations = [registry.register_plugin(db, admin_user, 'test', '1', {'protocol_versions': ['1']}),
        registry.rotate_plugin_secret(db, admin_user, plugin_id), registry.list_plugins(db, admin_user, 1, 20),
        registry.get_plugin(db, admin_user, plugin_id), registry.set_plugin_enabled(db, admin_user, plugin_id, True),
        registry.list_plugin_grants(db, admin_user, plugin_id, 1, 20),
        registry.create_plugin_grant(db, admin_user, plugin_id, request),
        registry.set_plugin_grant_enabled(db, admin_user, plugin_id, grant_id, False)]
    for operation in operations:
        with pytest.raises(PermissionError):
            await operation
    assert not statements


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['enable', 'rotate', 'create_grant', 'disable_grant'])
async def test_mutations_recheck_admin_after_installation_lock_wait(committed_runtime, mutation):
    from sqlalchemy import event
    from app.models.agent_plugin import AgentPluginInstallation
    from app.schemas.agent_plugin import PluginGrantCreate
    from app.services.agent_runtime import plugin_registry as registry
    owned = committed_runtime
    grant_id = uuid.uuid4()
    async with owned.factory(binding=owned.binding) as setup:
        existing = await setup.get(AgentPluginInstallation, owned.plugin_id)
        from app.models.agent_task import AgentTask
        task = await setup.get(AgentTask, owned.task_id)
        factory_id = task.factory_id
        setup.add(AgentPluginGrant(grant_id=grant_id, installation_id=owned.plugin_id, capability_id=SUMMARY,
            factory_ids=[str(factory_id)], enabled=False, granted_by=owned.user_id))
        await setup.commit()
    lock_attempted = asyncio.Event()
    def notice_lock(conn, cursor, statement, parameters, context, executemany):
        if 'agent_plugin_installations' in statement and 'FOR UPDATE' in statement:
            lock_attempted.set()
    async with owned.factory(binding=owned.binding) as holder:
        await holder.scalar(select(AgentPluginInstallation).where(
            AgentPluginInstallation.installation_id == owned.plugin_id).with_for_update())
        event.listen(owned.engine.sync_engine, 'before_cursor_execute', notice_lock)
        async def rival():
            async with owned.factory(binding=owned.binding) as writer:
                actor = await writer.get(User, owned.user_id)
                # Cache the pre-lock installation as well; mutations must reload it.
                await writer.get(AgentPluginInstallation, owned.plugin_id)
                if mutation == 'enable':
                    await registry.set_plugin_enabled(writer, actor, owned.plugin_id, False)
                elif mutation == 'rotate':
                    await registry.rotate_plugin_secret(writer, actor, owned.plugin_id)
                elif mutation == 'create_grant':
                    await registry.create_plugin_grant(writer, actor, owned.plugin_id,
                        PluginGrantCreate(capability_id=SUMMARY, factory_ids=[factory_id]))
                else:
                    await registry.set_plugin_grant_enabled(writer, actor, owned.plugin_id, grant_id, False)
                await writer.commit()
        pending = asyncio.create_task(rival())
        try:
            await asyncio.wait_for(lock_attempted.wait(), timeout=10)
            assert not pending.done()
            await holder.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id,
                RolePermission.module == 'permission_mgmt').values(permission_level=0))
            await holder.commit()
            with pytest.raises(PermissionError):
                await asyncio.wait_for(pending, timeout=10)
        finally:
            event.remove(owned.engine.sync_engine, 'before_cursor_execute', notice_lock)
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
