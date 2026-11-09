from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.config import settings
from app.core.tenant_context import TenantContextMiddleware

PATHS = ['/api/agent/tasks', '/api/admin/agent-plugins', '/api/agent/runtime/capa/context']


class NoTenantLookup(TenantContextMiddleware):
    async def _resolve_by_slug(self, slug):
        raise AssertionError('peer gate must precede tenant database lookup')


@pytest.mark.asyncio
@pytest.mark.parametrize('peer,headers', [
    ('203.0.113.1', {}), ('127.0.0.2', {}), ('localhost', {}),
    ('127.0.0.1', {'Forwarded': 'for=127.0.0.1'}),
    ('127.0.0.1', {'X-Forwarded-For': '127.0.0.1'}),
    ('::1', {'X-Forwarded-Proto': 'https'}),
    ('127.0.0.1', {'X-Forwarded-Unrecognized': 'anything'}),
])
async def test_nonliteral_peer_or_any_forwarded_header_denied_before_database(monkeypatch, peer, headers):
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(settings, 'AGENT_LOCAL_TRIAL_MODE', 'local_metadata')
    app = FastAPI()
    app.add_middleware(NoTenantLookup)
    async with AsyncClient(transport=ASGITransport(app=app, client=(peer, 1234)), base_url='http://127.0.0.1') as client:
        for path in PATHS:
            response = await client.post(path, content='invalid JSON', headers={'X-Tenant-ID': 'never-resolved', **headers})
            assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('peer', ['127.0.0.1', '::1'])
async def test_literal_loopback_can_enter_without_affecting_legacy_paths(monkeypatch, peer):
    monkeypatch.setattr(settings, 'TENANT_MODE', 'single')
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(settings, 'AGENT_LOCAL_TRIAL_MODE', 'local_metadata')
    app = FastAPI()
    app.add_middleware(TenantContextMiddleware)
    @app.get('/api/agent/tasks')
    async def entered(): return {'entered': True}
    @app.get('/api/agent/sessions')
    async def legacy(): return {'legacy': True}
    async with AsyncClient(transport=ASGITransport(app=app, client=(peer, 1234)), base_url='http://127.0.0.1') as client:
        assert (await client.get('/api/agent/tasks')).status_code == 200
    async with AsyncClient(transport=ASGITransport(app=app, client=('203.0.113.1', 1234)), base_url='http://127.0.0.1') as client:
        assert (await client.get('/api/agent/sessions')).status_code == 200


@pytest.mark.asyncio
async def test_global_off_wins_before_peer_headers_body_and_tenant(monkeypatch):
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', False)
    monkeypatch.setattr(settings, 'AGENT_LOCAL_TRIAL_MODE', 'local_metadata')
    app = FastAPI()
    app.add_middleware(NoTenantLookup)
    async with AsyncClient(transport=ASGITransport(app=app, client=('203.0.113.1', 1234)), base_url='http://127.0.0.1') as client:
        for path in PATHS:
            response = await client.post(path, content='invalid JSON', headers={'X-Tenant-ID': 'unresolved', 'Forwarded': 'for=127.0.0.1'})
            assert response.status_code == 404
