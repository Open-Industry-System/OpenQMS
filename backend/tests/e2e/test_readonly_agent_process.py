"""Automatic acceptance: independent stdlib plugin, real HTTP and complete PG tenant."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import socket
import sys
from types import MappingProxyType, SimpleNamespace
from urllib.parse import parse_qs
import uuid

from fastapi import FastAPI
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
import uvicorn

from app.api import agent_runtime
from app.config import settings
from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.tenant_context import TenantContextMiddleware
from app.core.tenant_transaction import TenantBinding
from app.database import TenantSession
from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.agent_runtime_event import AgentProjectionReceipt, AgentRunEvent, AgentResult, AgentEventReceipt, AgentResultReceipt
from app.models.agent_task import AgentRun, AgentTask, AgentTaskMessage
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.product_line import ProductLine
from app.models.role import RolePermission
from app.models.user import User
from app.schemas.agent_plugin import PluginGrantCreate
from app.schemas.platform import TenantCreateRequest
from app.services import tenant_migrator
from app.services.agent.permissions import catalog
from app.services.agent.permissions.types import ApprovalFloor
from app.services.agent_runtime import plugin_registry, task_service, message_queue, runtime_access

SUMMARY = 'capa.d4.summary.masked.v1'
PLUGIN = Path(__file__).resolve().parents[2] / 'examples' / 'readonly_8d_plugin.py'
MARKER = 'PROCESS_FORBIDDEN_FREE_TEXT'


def test_stdlib_readonly_plugin_entrypoint_exists():
    assert PLUGIN.is_file(), 'independent readonly plugin entrypoint missing'


@pytest_asyncio.fixture
async def process_tenant(monkeypatch):
    import app.database as database
    from app.core import tenant_context
    url = os.environ['TEST_DATABASE_URL']
    assert url.rsplit('/', 1)[-1].endswith('_test')
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, sync_session_class=TenantSession, expire_on_commit=False)
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    monkeypatch.setattr(database, 'engine', engine)
    monkeypatch.setattr(database, 'tenant_async_session', factory)
    monkeypatch.setattr(tenant_context, 'async_session', async_sessionmaker(engine, expire_on_commit=False))
    canonical = catalog.CAPA_CAPABILITIES
    monkeypatch.setattr(catalog, 'CAPA_CAPABILITIES', MappingProxyType({
        **canonical, SUMMARY: replace(canonical[SUMMARY], approval_floor=ApprovalFloor.DIRECT)}))
    tenants = []
    async def provision():
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(name='Process acceptance',
            slug='process-'+uuid.uuid4().hex[:12], admin_email='process@example.test',
            admin_password='process-bootstrap-password'))
        tenants.append(tenant)
        return tenant, TenantBinding(tenant.id, tenant.schema_name, tenant.generation, 'business')
    try:
        tenant, binding = await provision()
        async with factory(binding=binding) as db:
            user = await db.scalar(select(User).where(User.email == 'process@example.test'))
            line = await db.scalar(select(ProductLine))
            capa = CAPAEightD(document_no='8D-PROCESS', status='D4_ANALYSIS', title=MARKER,
                d1_team=[{'name': MARKER}], d2_description=MARKER, d4_root_cause=MARKER,
                factory_id=line.factory_id, product_line_code=line.code, created_by=user.user_id)
            db.add(capa)
            await db.flush()
            for conclusion, verified in [('passed', True), ('pending', False)]:
                db.add(CapaRootCauseVerification(capa_id=capa.report_id, factory_id=capa.factory_id,
                    root_cause_text=MARKER, result=MARKER, evidence_attachments=[MARKER],
                    conclusion=conclusion, is_verified=verified))
            plugin, secret = await plugin_registry.register_plugin(db, user, 'process-readonly', '1.0.0',
                {'protocol_versions': ['1'], 'required_capabilities': [SUMMARY]})
            await plugin_registry.set_plugin_enabled(db, user, plugin.installation_id, True)
            grant = await plugin_registry.create_plugin_grant(db, user, plugin.installation_id,
                PluginGrantCreate(capability_id=SUMMARY, factory_ids=[capa.factory_id],
                    product_line_codes=[line.code], object_ids=[capa.report_id], enabled=True))
            await db.commit()
            scope = RequestScope(FactoryScope([capa.factory_id], capa.factory_id), capa.factory_id,
                ProductLineScope('ALL', None), user)
            task = await task_service.create_task(db, scope, capa.report_id, plugin.installation_id,
                'process-task', MARKER+' initial instruction is not evaluated')
            await message_queue.append_task_message(db, task, scope, MARKER+' second instruction', 'second')
            run = await db.scalar(select(AgentRun).where(AgentRun.task_id == task.task_id))
            assert task.status == 'ready' and run.status == 'pending'
            owned = SimpleNamespace(engine=engine, factory=factory, binding=binding, slug=tenant.slug,
                report_id=capa.report_id, factory_id=capa.factory_id, line=line.code,
                plugin_id=plugin.installation_id, grant_id=grant.grant_id, secret=secret,
                task_id=task.task_id, run_id=run.run_id, user_id=user.user_id, role_id=user.role_id,
                provision=provision, canonical=canonical)
        monkeypatch.setattr(runtime_access, 'TRUSTED_DELIVERY_DEPLOYMENTS', frozenset({
            (str(binding.tenant_id), owned.plugin_id, '1.0.0')}))
        yield owned
    finally:
        async with engine.begin() as conn:
            for tenant in reversed(tenants):
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{tenant.schema_name}" CASCADE'))
                await conn.execute(text('DELETE FROM public.tenant_migrations WHERE tenant_id=:id'), {'id': tenant.id})
                await conn.execute(text('DELETE FROM public.tenants WHERE id=:id'), {'id': tenant.id})
        await engine.dispose()


class Witness:
    """Observe actual wire responses; optional committed revocation before round two."""
    def __init__(self, app, owned):
        self.app, self.owned = app, owned
        self.calls, self.tokens, self.after_first = [], [], None
        self.corrupt = None
        self.redirect_at = self.redirect_url = None

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        chunks, status = [], None
        async def capture(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            elif message['type'] == 'http.response.body':
                chunks.append(message.get('body', b''))
            # Buffer the actual response so revocation commits after receipt and
            # before the independent plugin can issue its dependent request.
        await self.app(scope, receive, capture)
        raw = b''.join(chunks)
        body = json.loads(raw) if raw else None
        path, query = scope['path'], parse_qs(scope['query_string'].decode())
        self.calls.append((scope['method'], path, query, status, body))
        if path.endswith('/claim') and path == '/api/agent/runtime/claim' and status == 200:
            self.tokens.append(body['token'])
        if path.endswith('/capa/context') and status == 200 and query.get('view') == ['report']:
            if self.after_first:
                await self.after_first()
            if self.corrupt:
                body = self.corrupt(body)
                raw = json.dumps(body).encode()
        if path == self.redirect_at:
            await send({'type': 'http.response.start', 'status': 307,
                'headers': [(b'location', self.redirect_url.encode()), (b'content-length', b'0')]})
            await send({'type': 'http.response.body', 'body': b''})
            return
        await send({'type': 'http.response.start', 'status': status,
            'headers': [(b'content-type', b'application/json'), (b'content-length', str(len(raw)).encode())]})
        await send({'type': 'http.response.body', 'body': raw})


@pytest_asyncio.fixture
async def process_server(process_tenant):
    owned = process_tenant
    app = FastAPI()
    app.include_router(agent_runtime.router)
    app.add_middleware(TenantContextMiddleware)
    assert not app.dependency_overrides
    witness = Witness(app, owned)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    server = uvicorn.Server(uvicorn.Config(witness, log_level='critical', access_log=False, lifespan='off'))
    runner = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(200):
            if server.started:
                break
            if runner.done():
                await runner
            await asyncio.sleep(.01)
        assert server.started
        yield SimpleNamespace(owned=owned, witness=witness, url=f'http://127.0.0.1:{sock.getsockname()[1]}')
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(runner, 10)
        finally:
            sock.close()


async def execute(server, **overrides):
    env = {key: value for key, value in os.environ.items() if key not in {
        'DATABASE_URL', 'TEST_DATABASE_URL', 'SECRET_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY'}}
    env.update(OPENQMS_API_BASE_URL=server.url, OPENQMS_INSTALLATION_ID=str(server.owned.plugin_id),
        OPENQMS_INSTALLATION_SECRET=server.owned.secret, OPENQMS_TENANT_SLUG=server.owned.slug,
        OPENQMS_CLAIM_KEY='process-claim')
    env.update(overrides)
    process = await asyncio.create_subprocess_exec(sys.executable, str(PLUGIN), env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    output = stdout.decode()+stderr.decode()
    assert server.owned.secret not in output
    assert all(token not in output for token in server.witness.tokens)
    assert MARKER not in output
    return process.returncode, stdout.decode(), stderr.decode()


async def business_snapshot(owned):
    async with owned.factory(binding=owned.binding) as db:
        return [list((await db.execute(select(table).order_by(*table.primary_key.columns))).mappings())
            for table in (CAPAEightD.__table__, CapaRootCauseVerification.__table__)]


async def outputs(owned):
    async with owned.factory(binding=owned.binding) as db:
        return [list((await db.scalars(select(model))).all()) for model in
            (AgentProjectionReceipt, AgentRunEvent, AgentResult, AgentEventReceipt, AgentResultReceipt)]


@pytest.mark.asyncio
async def test_independent_process_claims_acknowledges_queries_twice_and_saves_bound_sources(process_server):
    server, owned = process_server, process_server.owned
    before = await business_snapshot(owned)
    code, stdout, stderr = await execute(server)
    assert code == 0, stderr
    contexts = [call for call in server.witness.calls if call[1].endswith('/capa/context')]
    assert len(contexts) == 2
    assert contexts[0][2] == {'view': ['report']}
    assert contexts[1][2] == {'view': ['verifications'], 'report_id': [str(owned.report_id)]}
    assert all(call[3] == 200 for call in server.witness.calls)
    assert 'verifications' not in contexts[0][4]
    assert len(contexts[1][4]['verifications']) == 2
    for call in contexts:
        assert not {'body', 'attachments', 'customer', 'supplier', 'team', 'title', 'd4_root_cause'} & call[4].keys()
        assert MARKER not in json.dumps(call[4])
    receipts, events, results, event_links, result_links = await outputs(owned)
    assert [len(rows) for rows in (receipts, events, results, event_links, result_links)] == [2, 1, 1, 2, 2]
    assert {row.receipt_id for row in receipts} == {row.receipt_id for row in event_links} == {row.receipt_id for row in result_links}
    assert results[0].data_class == 'restricted' and events[0].event_type == 'query_completed'
    assert results[0].payload['missing_information'] and results[0].payload['conditional_recommendations']
    for receipt in receipts:
        assert (receipt.task_id, receipt.run_id, receipt.source_capa_id, receipt.lease_epoch,
            receipt.tenant_generation) == (owned.task_id, owned.run_id, owned.report_id, 1, owned.binding.generation)
    async with owned.factory(binding=owned.binding) as db:
        run = await db.get(AgentRun, owned.run_id)
        assert run.accepted_message_seq == 2
        messages = list((await db.scalars(select(AgentTaskMessage).order_by(AgentTaskMessage.sequence))).all())
        assert [(m.sequence, m.state) for m in messages] == [(1, 'accepted'), (2, 'accepted')]
        audits = list((await db.scalars(select(AuditLog))).all())
        safe = json.dumps([{c.name: str(getattr(row, c.name)) for c in AuditLog.__table__.columns} for row in audits])
        assert MARKER not in safe and owned.secret not in safe
        assert all(token not in safe for token in server.witness.tokens)
        query_audits = [a for a in audits if a.action == 'QUERY_AGENT_CAPA_CONTEXT']
        assert len(query_audits) == 2
        assert all(a.operated_by == owned.user_id and a.correlation_id == owned.run_id and
            a.changed_fields['task_id'] == str(owned.task_id) and a.changed_fields['source_capa_id'] == str(owned.report_id)
            for a in query_audits)
    assert await business_snapshot(owned) == before
    assert json.loads(stdout)['task_id'] == str(owned.task_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['pause', 'disable', 'permission', 'grant'])
async def test_real_committed_revocation_between_process_rounds_prevents_output(process_server, change):
    server, owned = process_server, process_server.owned
    before = await business_snapshot(owned)
    async def revoke():
        async with owned.factory(binding=owned.binding) as db:
            assert len(list((await db.scalars(select(AgentProjectionReceipt))).all())) == 1
            commands = {
                'pause': update(AgentTask).where(AgentTask.task_id == owned.task_id).values(status='paused'),
                'disable': update(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == owned.plugin_id).values(enabled=False),
                'permission': update(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == 'capa').values(permission_level=0),
                'grant': update(AgentPluginGrant).where(AgentPluginGrant.grant_id == owned.grant_id).values(enabled=False)}
            await db.execute(commands[change])
            await db.commit()
    server.witness.after_first = revoke
    code, _, _ = await execute(server)
    assert code != 0
    contexts = [c for c in server.witness.calls if c[1].endswith('/capa/context')]
    assert [c[3] for c in contexts] == [200, 401]
    assert [len(rows) for rows in await outputs(owned)] == [1, 0, 0, 0, 0]
    assert await business_snapshot(owned) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['receipt', 'receipt_uuid', 'projection', 'classification', 'digest', 'report', 'field_limit'])
async def test_plugin_refuses_invalid_projection_before_dependent_query(process_server, damage):
    server = process_server
    def corrupt(body):
        result = dict(body)
        if damage == 'receipt':
            del result['receipt_id']
        else:
            field, value = {'projection': ('projection_id', 'unexpected'),
                'classification': ('data_class', 'restricted'), 'digest': ('projection_digest', 'invalid'),
                'receipt_uuid': ('receipt_id', 'invalid'), 'field_limit': ('document_no', 'x'*51),
                'report': ('source_capa_id', str(uuid.uuid4()))}[damage]
            result[field] = value
        return result
    server.witness.corrupt = corrupt
    assert (await execute(server))[0] != 0
    assert len([c for c in server.witness.calls if c[1].endswith('/capa/context')]) == 1
    assert [len(rows) for rows in await outputs(server.owned)] == [1, 0, 0, 0, 0]


@pytest.mark.asyncio
async def test_actual_http_default_deny_off_strict_queries_and_cross_tenant_same_uuid(process_server, monkeypatch):
    server, owned = process_server, process_server.owned
    assert (await execute(server))[0] == 0
    token = server.witness.tokens[0]
    async with httpx.AsyncClient(base_url=server.url, follow_redirects=False) as client:
        headers = {'Authorization': 'Bearer '+token}
        assert (await client.get('/api/agent/runtime/capa/context', headers=headers, params={'arbitrary': 'selector'})).status_code == 422
        tenant, binding = await owned.provision()
        async with owned.factory(binding=binding) as db:
            line = await db.scalar(select(ProductLine))
            db.add(CAPAEightD(report_id=owned.report_id, document_no='OTHER-TENANT-METADATA', title=MARKER,
                factory_id=line.factory_id, product_line_code=line.code))
            await db.commit()
        response = await client.get('/api/agent/runtime/capa/context', params={'report_id': str(owned.report_id)},
            headers={**headers, 'X-Tenant-ID': tenant.slug})
        assert response.status_code == 401 and 'OTHER-TENANT' not in response.text and MARKER not in response.text
        monkeypatch.setattr(catalog, 'CAPA_CAPABILITIES', owned.canonical)
        assert (await client.get('/api/agent/runtime/capa/context', headers=headers)).status_code == 401
        monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', False)
        for path in ['/claim', '/capabilities', '/capa/context', '/events', '/results']:
            response = await client.post('/api/agent/runtime'+path, content='invalid', headers=headers)
            assert response.status_code == 404
    assert len((await outputs(owned))[0]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('url', ['http://example.com', 'http://127.0.0.1@evil.test', 'http://localhost/?x=1', 'http://localhost/#fragment'])
async def test_plugin_rejects_nonlocal_or_ambiguous_url_before_network(process_server, url):
    server = process_server
    assert (await execute(server, OPENQMS_API_BASE_URL=url))[0] != 0
    assert not server.witness.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['/claim', '/capa/context'])
async def test_plugin_never_follows_redirect_with_installation_secret_or_bearer(process_server, stage):
    requests = []
    async def target(reader, writer):
        requests.append(await reader.read(4096))
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}')
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    target_server = await asyncio.start_server(target, '127.0.0.1', 0)
    try:
        port = target_server.sockets[0].getsockname()[1]
        process_server.witness.redirect_at = '/api/agent/runtime'+stage
        process_server.witness.redirect_url = f'http://127.0.0.1:{port}/capture'
        assert (await execute(process_server))[0] != 0
        assert not requests
        assert not (await outputs(process_server.owned))[1]
        assert not (await outputs(process_server.owned))[2]
    finally:
        target_server.close()
        await target_server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize('response_kind', ['bad-status', 'deep-json'])
async def test_malformed_real_tcp_response_has_constant_content_free_cli_failure(process_server, response_kind):
    """Untrusted wire/decoder exceptions must never escape into a traceback."""
    async def peer(reader, writer):
        try:
            await reader.read(65536)
            if response_kind == 'bad-status':
                response = (MARKER+'\r\n\r\n').encode()
            else:
                body = b'{"nested":'+b'['*2000+b'0'+b']'*2000+b'}'
                response = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '
                    +str(len(body)).encode()+b'\r\nConnection: close\r\n\r\n'+body)
            writer.write(response)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    peer_server = await asyncio.start_server(peer, '127.0.0.1', 0)
    try:
        port = peer_server.sockets[0].getsockname()[1]
        code, stdout, stderr = await execute(process_server, OPENQMS_API_BASE_URL=f'http://127.0.0.1:{port}')
        assert code == 1 and stdout == '' and stderr == 'Readonly plugin stopped safely.\n'
        assert not process_server.witness.calls
        assert [len(rows) for rows in await outputs(process_server.owned)] == [0, 0, 0, 0, 0]
    finally:
        peer_server.close()
        await peer_server.wait_closed()
