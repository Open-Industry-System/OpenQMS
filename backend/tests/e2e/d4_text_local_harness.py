"""Normal-policy owned D4 text admission fixture for the first claimable gate."""
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import json
import socket
from uuid import UUID, uuid4

import httpx
import pytest_asyncio
import uvicorn

from app.config import settings
from app.models.fmea import FMEADocument
from app.services.agent_runtime.local_d4_text_policy import TEXT_PLUGIN_KEY, TEXT_WORKER_SHA256
from tests.e2e.agent_local_trial_harness import owned_local_trial

BODY = 'capa.d4.root_cause_candidate.masked.v1'


@asynccontextmanager
async def d4_text_tcp_trial(owned_local_trial):
    """Use a real numeric-loopback listener for setup and employee/admin requests."""
    owned = owned_local_trial
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    server = uvicorn.Server(uvicorn.Config(owned.app, log_level='critical', access_log=False,
        lifespan='off', proxy_headers=False))
    runner = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(300):
            if server.started:
                break
            if runner.done():
                await runner
            await asyncio.sleep(.01)
        assert server.started
        origin = f'http://127.0.0.1:{sock.getsockname()[1]}'
        old_admin, old_client = owned.admin, owned.client
        async with httpx.AsyncClient(base_url=origin, headers={'X-Tenant-ID': owned.slug,
                'Authorization': 'Bearer ' + owned.admin_token}, timeout=15, trust_env=False) as admin, \
                httpx.AsyncClient(base_url=origin, headers={'X-Tenant-ID': owned.slug,
                'Authorization': 'Bearer ' + owned.user_token}, timeout=15, trust_env=False) as client:
            owned.admin, owned.client = admin, client
            try:
                yield owned
            finally:
                owned.admin, owned.client = old_admin, old_client
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(runner, 10)
        finally:
            sock.close()


@pytest_asyncio.fixture
async def d4_text_local_trial(owned_local_trial, monkeypatch, tmp_path):
    async with d4_text_tcp_trial(owned_local_trial) as owned:
        async with owned.session() as db:
            fmea = FMEADocument(document_no='T8-' + uuid4().hex[:12], title='synthetic source',
                factory_id=owned.factory_id, product_line_code=owned.line,
                graph_data={'nodes': [{'id':'cause-A', 'type':'FailureCause'},
                                      {'id':'cause-B', 'type':'FailureCause'}], 'edges': []})
            db.add(fmea)
            await db.flush()
            owned.fmea_id = fmea.fmea_id
            await db.commit()
        result = await owned.admin.put(f'/api/capa/{owned.report_id}', json={
            'fmea_ref_id': str(owned.fmea_id), 'd4_root_cause': 'synthetic candidate'})
        assert result.status_code == 200, result.text
        monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', True)
        path = tmp_path / 'text-policy' / 'policy.json'
        path.parent.mkdir(mode=0o700)
        path.write_text(json.dumps({'schema_version': 1, 'entries': []}))
        path.chmod(0o600)
        monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE', str(path))
        result = await owned.admin.post('/api/admin/agent-plugins', json={
            'plugin_key': TEXT_PLUGIN_KEY, 'plugin_version': '1.0.0', 'manifest': {
                'protocol_versions': ['1'], 'required_capabilities': [BODY],
                'optional_capabilities': [], 'supports_resume': False}})
        assert result.status_code == 201, result.text
        payload = result.json()
        owned.text_id = UUID(payload['plugin']['installation_id'])
        owned.text_secret = payload['secret']
        entry = {'tenant_id': str(owned.binding.tenant_id), 'tenant_generation': owned.binding.generation,
            'installation_id': str(owned.text_id), 'credential_epoch': 0, 'plugin_key': TEXT_PLUGIN_KEY,
            'plugin_version': '1.0.0', 'executor_user_id': str(owned.user_id), 'report_id': str(owned.report_id),
            'factory_id': str(owned.factory_id), 'product_line_code': owned.line,
            'expires_at': (datetime.now(UTC) + timedelta(minutes=20)).isoformat(),
            'worker_sha256': TEXT_WORKER_SHA256, 'redaction_terms': ['synthetic-private-term']}
        path.write_text(json.dumps({'schema_version': 1, 'entries': [entry]}))
        await owned.restart()
        assert owned.app.state.agent_d4_text_policy.diagnostic == 'TEXT_POLICY_READY'
        proof = await owned.admin.post(f'/api/capa/{owned.report_id}/root-cause-verifications', json={
            'root_cause_text': 'synthetic candidate', 'method': 'measurement', 'conclusion': 'passed',
            'source_ref': {'fmea_id': str(owned.fmea_id), 'cause_node_id': 'cause-A'},
            'source_declaration': {'declares_complete_coverage': True}})
        assert proof.status_code == 200 and proof.json()['source_proof_issued'] is True, proof.text
        owned.source_scope = {'target_report_id': str(owned.report_id), 'fmea_id': str(owned.fmea_id),
                              'cause_node_id': 'cause-A'}
        grant = await owned.admin.post(f'/api/admin/agent-plugins/{owned.text_id}/grants', json={
            'capability_id': BODY, 'factory_ids': [str(owned.factory_id)], 'object_ids': [str(owned.report_id)],
            'product_line_codes': [owned.line], 'expires_at': entry['expires_at'], 'enabled': True,
            'derived_source_scope': owned.source_scope})
        assert grant.status_code == 201, grant.text
        owned.text_grant_id = UUID(grant.json()['grant_id'])
        enabled = await owned.admin.patch(f'/api/admin/agent-plugins/{owned.text_id}', json={'enabled': True})
        assert enabled.status_code == 200, enabled.text
        yield owned


@pytest_asyncio.fixture
async def d4_text_server(d4_text_local_trial):
    owned = d4_text_local_trial
    calls = []
    async def witness(scope, receive, send):
        if scope['type'] != 'http':
            return await owned.app(scope, receive, send)
        status = None
        async def track(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                calls.append((scope['method'], scope['path'], status))
            await send(message)
        await owned.app(scope, receive, track)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    server = uvicorn.Server(uvicorn.Config(witness, log_level='critical', access_log=False,
        lifespan='off', proxy_headers=False))
    runner = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(300):
            if server.started:
                break
            if runner.done():
                await runner
            await asyncio.sleep(.01)
        assert server.started
        owned.text_base_url = f'http://127.0.0.1:{sock.getsockname()[1]}'
        owned.text_calls = calls
        yield owned
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(runner, 10)
        finally:
            sock.close()
