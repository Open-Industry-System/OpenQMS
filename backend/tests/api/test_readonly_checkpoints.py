"""Checkpoint/history routes using actual middleware and both JWT domains."""
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.config import settings
from app.core.security import create_access_token
from app.main import app
from tests.services.agent_runtime.conftest import committed_runtime
from tests.services.agent_runtime.test_runtime_access import direct_caps, ready_owned
from tests.services.agent_runtime.test_runtime_messages import delivery, append, claim, ack
from tests.services.agent_runtime.test_readonly_delivery import context_delivery, context


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['single', 'dev', 'production'])
async def test_new_routes_off_before_any_tenant_auth_body_for_all_methods(monkeypatch, mode):
    monkeypatch.setattr(settings, 'TENANT_MODE', mode)
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', False)
    paths = ['/api/agent/runtime/checkpoints', '/api/agent/runtime/messages/history', '/api/agent/tasks/bad/checkpoints/bad']
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for path in paths:
            for method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'):
                result = await client.request(method, path, content='invalid', headers={'X-Tenant-ID': 'unknown', 'Authorization': 'Bearer invalid'})
                assert result.status_code == 404, result.text


@pytest.mark.asyncio
async def test_actual_checkpoint_history_http_strict_body_queries_and_domains(context_delivery, monkeypatch):
    import app.database as database
    owned = context_delivery
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(database, 'tenant_async_session', owned.factory)
    receipt = (await context(owned))['receipt_id']
    await append(owned, 'restricted original'); batch = await claim(owned); await ack(owned, batch.batch_id, 1)
    run_auth = {'Authorization': 'Bearer '+owned.token}
    user_auth = {'Authorization': 'Bearer '+create_access_token({'sub': str(owned.user_id), 'tenant_id': str(owned.binding.tenant_id)})}
    async with owned.engine.connect() as conn:
        slug = await conn.scalar(text('SELECT slug FROM public.tenants WHERE id=:id'), {'id': owned.binding.tenant_id})
    body = dict(idempotency_key='cp', receipt_ids=[receipt])
    assert not app.dependency_overrides
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for fields in ({'watermark': 1}, {'tenant_generation': 1}, {'digest': 'spoof'}, {'receipt_ids': []}, {'idempotency_key': True}):
            response = await client.post('/api/agent/runtime/checkpoints', json={**body, **fields}, headers=run_auth)
            assert response.status_code == 422, response.text
        cp = await client.post('/api/agent/runtime/checkpoints', json=body, headers=run_auth)
        assert cp.status_code == 200, cp.text
        assert cp.json()['accepted_message_seq'] == 1 and 'restricted original' not in cp.text
        path = '/api/agent/tasks/'+str(owned.task_id)+'/checkpoints/'+cp.json()['checkpoint_id']
        response = await client.get(path, headers=user_auth)
        assert response.status_code == 200, response.text
        assert response.json()['is_latest'] and response.json()['prefix_eligible']
        assert (await client.get(path, headers=run_auth)).status_code == 400
        response = await client.get('/api/agent/runtime/messages/history', params={'after_sequence': '0', 'limit': '1'}, headers=run_auth)
        assert response.status_code == 200, response.text
        assert [m['content'] for m in response.json()['messages']] == ['restricted original']
        for params in ({'after_sequence': 'true'}, {'after_sequence': '-1'}, {'after_sequence': '1.5'}, {'limit': '21'}, {'limit': 'false'}, {'schema': 'spoof'}):
            response = await client.get('/api/agent/runtime/messages/history', params=params, headers=run_auth)
            assert response.status_code == 422, response.text
        for path, method in (('/api/agent/runtime/checkpoints', 'POST'), ('/api/agent/runtime/messages/history', 'GET')):
            response = await client.request(method, path, json=body if method=='POST' else None, headers={**user_auth, 'X-Tenant-ID': slug})
            assert response.status_code == 401, response.text
            wrong = await client.request('GET' if method=='POST' else 'POST', path, headers=run_auth)
            assert wrong.status_code == 400, wrong.text
