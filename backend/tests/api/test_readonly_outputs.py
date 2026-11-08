"""Real tenant middleware separates bounded runtime writes from user history."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text, update

from app.config import settings
from app.core.security import create_access_token
from app.main import app
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_task import AgentRun
from app.models.role import RolePermission
from tests.services.agent_runtime.conftest import committed_runtime
from tests.services.agent_runtime.test_runtime_access import direct_caps, ready_owned
from tests.services.agent_runtime.test_runtime_messages import delivery
from tests.services.agent_runtime.test_readonly_delivery import context_delivery
from tests.services.agent_runtime.test_readonly_outputs import result_body, event_body


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['single', 'dev', 'production'])
async def test_output_paths_default_off_before_auth_and_validation(monkeypatch, mode):
    monkeypatch.setattr(settings, 'TENANT_MODE', mode)
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', False)
    paths = ['/api/agent/runtime/events', '/api/agent/runtime/results',
        f'/api/agent/tasks/{uuid.uuid4()}/results/{uuid.uuid4()}']
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for path in paths:
            for method in ('GET', 'POST', 'DELETE', 'PUT'):
                result = await client.request(method, path, content='invalid-json',
                    headers={'X-Tenant-ID': 'invalid', 'Authorization': 'Bearer invalid'})
                assert result.status_code == 404, result.text


@pytest.mark.asyncio
async def test_real_http_receipt_writes_user_history_token_domains_and_revocation(context_delivery, monkeypatch):
    import app.database as database
    owned = context_delivery
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(database, 'tenant_async_session', owned.factory)
    assert not app.dependency_overrides
    async with owned.engine.connect() as db:
        slug = await db.scalar(text('SELECT slug FROM public.tenants WHERE id=:id'), {'id': owned.binding.tenant_id})
    runtime = {'Authorization': 'Bearer '+owned.token}
    user = {'Authorization': 'Bearer '+create_access_token({'sub': str(owned.user_id), 'tenant_id': str(owned.binding.tenant_id)}),
        'X-Tenant-ID': slug}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        receipts = []
        for view in ('report', 'verifications'):
            response = await client.get('/api/agent/runtime/capa/context', params={'view': view}, headers=runtime)
            assert response.status_code == 200, response.text
            receipts.append(response.json()['receipt_id'])
        for path, body, id_field in (('/api/agent/runtime/events', event_body(receipts), 'event_id'),
                                    ('/api/agent/runtime/results', result_body(receipts), 'result_id')):
            response = await client.post(path, json=body, headers=runtime)
            assert response.status_code == 200, response.text
            saved = response.json()
            assert (await client.post(path, json={**body, 'receipt_ids': receipts[::-1]}, headers=runtime)).json() == saved
            assert (await client.post(path, json={**body, 'actor_id': 'spoof'}, headers=runtime)).status_code == 422
            assert (await client.post(path, json={**body, 'receipt_ids': [str(uuid.uuid4())]}, headers=runtime)).status_code == 403
            assert (await client.post(path, json=body, headers=user)).status_code == 401
            assert (await client.get(path, headers=runtime)).status_code == 400
        history = f"/api/agent/tasks/{owned.task_id}/results/{saved['result_id']}"
        assert (await client.get(history, headers={**runtime, "X-Tenant-ID": slug})).status_code == 401
        response = await client.get(history, headers=user)
        assert response.status_code == 200 and response.json() == saved
        async with owned.factory(binding=owned.binding) as db:
            await db.execute(update(AgentRun).values(status='completed'))
            await db.execute(update(AgentPluginInstallation).values(enabled=False))
            await db.commit()
        assert (await client.get(history, headers=user)).json() == saved
        async with owned.factory(binding=owned.binding) as db:
            await db.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == 'capa').values(permission_level=0))
            await db.commit()
        denied = await client.get(history, headers=user)
        assert denied.status_code == 403
        assert 'RESTRICTED' not in denied.text and 'payload' not in denied.text and 'sources' not in denied.text
