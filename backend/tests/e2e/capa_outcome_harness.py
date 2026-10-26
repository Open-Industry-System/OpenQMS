"""Owned employee HTTP acceptance. No Agent enablement or business/auth doubles.

Terminal records below are protection fixtures ONLY. The live report is created
and progressed over HTTP; its state, gate and approval are never seeded.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
from secrets import token_urlsafe
import socket
import subprocess
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
import httpx
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.core.security import hash_password
from app.core.tenant_transaction import TenantBinding
from app.database import TenantSession
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.factory import UserFactory
from app.models.fmea import FMEADocument
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from app.schemas.platform import TenantCreateRequest

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / '.superpowers/sdd/2026-10-23-capa-outcome-review'
# Each is in our disposable tenant, never public or another harness tenant.
SNAPSHOT_TABLES = ('capa_eightd', 'capa_root_cause_verification', 'capa_ai_adoption',
    'capa_d7_node_action', 'audit_logs', 'document_embeddings', 'embedding_sync_outbox',
    'knowledge_entries', 'capa_lateral_diffusion_checks', 'mes_push_outbox',
    'capa_docg_analysis', 'capa_docg_audit', 'capa_docg_decision', 'capa_lessons_learned')


def verify_owned_database():
    """Registration + live container owner + DB identity, without emitting secrets."""
    from urllib.parse import urlsplit
    resources = json.loads((WORK / 'owned-resources.json').read_text())
    url = os.environ['TEST_DATABASE_URL']
    parsed = urlsplit(url)
    assert parsed.path[1:] == resources['test_database'] and parsed.path.endswith('_test')
    assert resources['test_database'] != resources['application_database']
    owner = subprocess.check_output(['docker', 'inspect', '--format',
        '{{.Id}} {{index .Config.Labels "openqms.owner"}}', resources['container']], text=True).strip()
    assert owner == resources['container_id'] + ' ' + resources['owner_nonce'], 'Owned container identity mismatch'
    assert parsed.hostname == resources['host'] == '127.0.0.1', 'Owned DB must use loopback'
    assert parsed.port == int(resources['port']), 'Owned DB port mismatch'
    return url


@dataclass
class OwnedOutcome:
    app: FastAPI
    base_url: str
    tenant_slug: str
    report_id: UUID
    editor_login: dict
    approver_login: dict
    session_factory: object
    binding: TenantBinding
    nonce: str
    terminal_report_id: UUID
    source_report_id: UUID
    verification_id: UUID
    fmea_id: UUID
    factory_id: UUID
    line: str
    editor_id: UUID
    approver_id: UUID
    approver_role_id: UUID
    other_binding: TenantBinding
    other_slug: str

    @asynccontextmanager
    async def client(self, identity='approver', *, other=False):
        login = ({**self.editor_login, 'username': 'bootstrap@outcome.example.test'} if identity == 'admin'
            else self.editor_login if identity == 'editor' else self.approver_login)
        async with httpx.AsyncClient(base_url=self.base_url, trust_env=False, timeout=120,
                headers={'X-Tenant-ID': self.other_slug if other else self.tenant_slug}) as client:
            response = await client.post('/api/auth/login', json=login)
            assert response.status_code == 200, f'Employee login HTTP {response.status_code}'
            client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
            yield client

    async def snapshot(self):
        async with self.session_factory() as db:
            result = {}
            for name in SNAPSHOT_TABLES:
                result[name] = await db.scalar(text(
                    f"SELECT coalesce(jsonb_agg(r ORDER BY r::text), '[]'::jsonb) FROM (SELECT to_jsonb(t) r FROM {name} t) q"))
            return result

    async def permission(self, module, level):
        async with self.session_factory() as db:
            await db.execute(update(RolePermission).where(RolePermission.role_id == self.approver_role_id,
                RolePermission.module == module).values(permission_level=level))
            await db.commit()


class OutcomeReadWindow:
    """Delay an actual authorized response, never its query/DTO/authority."""
    def __init__(self, app, window):
        self.app, self.window = app, window

    async def __call__(self, scope, receive, send):
        async def controlled_send(message):
            if (scope['type'] == 'http' and scope['path'].endswith('/outcome-review')
                    and message['type'] == 'http.response.start' and self.window['armed']):
                self.window['armed'] = False
                self.window['entered'].set()
                await self.window['release'].wait()
            await send(message)
        await self.app(scope, receive, controlled_send)


@pytest_asyncio.fixture
async def owned_outcome_server(monkeypatch):
    """Real migrations, TenantSession, auth and normal dependencies, allocated socket."""
    import app.database as database
    from app.core import tenant_context
    from app.services import tenant_migrator
    from app.api import auth, capa, product_line, fmea, control_plan, knowledge
    from app.api.capa_review_errors import register_capa_review_errors
    import uvicorn
    from collections import defaultdict
    # Isolate limiter storage; the production threshold/check remains unchanged.
    monkeypatch.setattr(auth, '_login_attempts', defaultdict(list))

    engine = create_async_engine(verify_owned_database(), poolclass=NullPool)
    platform = async_sessionmaker(engine, expire_on_commit=False)
    tenants = async_sessionmaker(engine, class_=AsyncSession,
        sync_session_class=TenantSession, expire_on_commit=False)
    for module, name, value in ((database, 'engine', engine), (database, 'async_session', platform),
            (database, 'tenant_async_session', tenants), (tenant_context, 'async_session', platform),
            (tenant_migrator, 'engine', engine)):
        monkeypatch.setattr(module, name, value)
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    assert not settings.E2E_MODE and not settings.AGENT_TASK_RUNTIME_ENABLED
    app = FastAPI()
    for router in (auth.router, capa.router, product_line.router, fmea.router, control_plan.router, knowledge.router):
        app.include_router(router)
    window = {'armed': False, 'entered': asyncio.Event(), 'release': asyncio.Event()}
    app.add_middleware(OutcomeReadWindow, window=window)
    app.add_middleware(tenant_context.TenantContextMiddleware)
    register_capa_review_errors(app)
    created = []
    allocated_slugs = []
    journal = WORK / ('task7-resources-' + uuid4().hex + '.json')
    cleaned = []
    sock, server, runner = None, None, None
    password = token_urlsafe(24)
    report_id, terminal_id, verification_id, fmea_id = uuid4(), uuid4(), uuid4(), uuid4()
    source_report_id = uuid4()
    try:
        async with platform() as db:
            assert await db.scalar(text('SELECT current_database()')) == json.loads(
                (WORK / 'owned-resources.json').read_text())['test_database']
            assert await db.scalar(text('SELECT current_user')) == os.environ['PGUSER']
        for _ in range(2):
            slug = 'outcome-' + uuid4().hex[:12]
            allocated_slugs.append(slug)
            tenant = await tenant_migrator.provision_new(TenantCreateRequest(
                name='Owned outcome acceptance', slug=slug,
                admin_email='bootstrap@outcome.example.test', admin_password=password))
            created.append(tenant)
            journal.write_text(json.dumps({'tenants': [{'id': str(t.id), 'slug': t.slug, 'schema': t.schema_name} for t in created], 'cleaned': []}, indent=2) + '\n')
        bindings = [TenantBinding(t.id, t.schema_name, t.generation, 'business') for t in created]
        ids = []
        # Duplicate UUID in genuinely distinct schemas proves tenant isolation.
        for index, binding in enumerate(bindings):
            async with tenants(binding=binding) as db:
                line = await db.scalar(select(ProductLine))
                db.add(ProductLine(code='OUTCOME-LIVE', name='Synthetic live progression', factory_id=line.factory_id))
                await db.flush()
                roles = {r.role_key: r.id for r in (await db.scalars(select(RoleDefinition))).all()}
                users = []
                for name, role in [('editor', 'field_qe'), ('approver', 'manager')]:
                    user = User(username='outcome-' + name, display_name='Outcome ' + name,
                        password_hash=hash_password(password), role_id=roles[role], legacy_role=role,
                        factory_id=line.factory_id, is_active=True)
                    db.add(user); await db.flush()
                    db.add_all([UserFactory(user_id=user.user_id, factory_id=line.factory_id),
                        UserProductLine(user_id=user.user_id, product_line_code=line.code),
                        UserProductLine(user_id=user.user_id, product_line_code='OUTCOME-LIVE')])
                    users.append(user)
                source = FMEADocument(fmea_id=fmea_id, document_no='PFMEA-OUTCOME-PROTECTION',
                    title='Synthetic source', factory_id=line.factory_id, product_line_code=line.code,
                    created_by=users[0].user_id, graph_data={'nodes': [], 'edges': []})
                db.add(source); await db.flush()
                from app.services.version_service import create_fmea_version
                await create_fmea_version(db, source, 'edit', 'Synthetic protection source', users[0].user_id)
                terminal = CAPAEightD(report_id=terminal_id, document_no='8D-OUTCOME-PROTECTION',
                    title='Protection fixture only', status='D8_CLOSURE', factory_id=line.factory_id,
                    product_line_code=line.code, created_by=users[0].user_id,
                    d4_root_cause='扭矩不足', d5_correction='已更换扭矩控制工具',
                    d6_verification='实施后复测合格' if index == 0 else 'OTHER TENANT MATERIAL',
                    d7_prevention='已更新点检要求')
                db.add(terminal)
                db.add(CAPAEightD(report_id=source_report_id, document_no='8D-OUTCOME-UNBOUND-SOURCE',
                    title='Unbound legacy source protection only', status='D8_CLOSURE',
                    factory_id=line.factory_id, product_line_code=line.code,
                    created_by=users[0].user_id, fmea_ref_id=fmea_id))
                await db.flush()
                db.add(CapaRootCauseVerification(verification_id=verification_id, capa_id=terminal_id,
                    factory_id=line.factory_id, root_cause_text='扭矩不足', result='复测合格',
                    method='measurement', conclusion='passed', is_verified=True,
                    verified_by=users[0].user_id, evidence_attachments=[]))
                await db.commit()
                ids.append((line.factory_id, line.code, users[0].user_id, users[1].user_id, roles['manager']))
        factory_id, line_code, editor_id, approver_id, approver_role_id = ids[0]
        binding = bindings[0]
        session_factory = lambda: tenants(binding=binding)
        owned = OwnedOutcome(app, '', created[0].slug, report_id,
            {'username': 'outcome-editor', 'password': password},
            {'username': 'outcome-approver', 'password': password}, session_factory,
            binding, token_urlsafe(32), terminal_id, source_report_id, verification_id, fmea_id,
            factory_id, line_code, editor_id, approver_id, approver_role_id, bindings[1], created[1].slug)

        @app.post('/__outcome_acceptance/{action}')
        async def command(action: str, request: Request):
            if request.headers.get('X-Acceptance-Nonce') != owned.nonce:
                raise HTTPException(404)
            if action == 'withdraw-source':
                await owned.permission('fmea', 0)
            elif action == 'restore-source':
                await owned.permission('fmea', 4)
            elif action == 'arm-read':
                window['entered'].clear(); window['release'].clear(); window['armed'] = True
            elif action == 'wait-read':
                await asyncio.wait_for(window['entered'].wait(), 10)
            elif action == 'release-read':
                window['release'].set()
            elif action == 'snapshot':
                return await owned.snapshot()
            else:
                raise HTTPException(404)
            return {'changed': True}

        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); sock.listen()
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False,
            lifespan='off', proxy_headers=False))
        runner = asyncio.create_task(server.serve(sockets=[sock]))
        for _ in range(300):
            if server.started: break
            if runner.done(): await runner
            await asyncio.sleep(.01)
        assert server.started, 'Owned outcome HTTP server did not start'
        owned.base_url = f'http://127.0.0.1:{sock.getsockname()[1]}'
        # Positive report starts at real D1 via business POST, never ORM state changes.
        async with owned.client('editor') as client:
            response = await client.post('/api/capa', json={'title': 'Synthetic outcome progression',
                'document_no': '8D-OUTCOME-LIVE', 'product_line_code': 'OUTCOME-LIVE'})
            assert response.status_code == 201, response.text
            owned.report_id = UUID(response.json()['report_id'])
        yield owned
    finally:
        window['release'].set()
        if server: server.should_exit = True
        if runner:
            try: await asyncio.wait_for(runner, 10)
            except asyncio.TimeoutError:
                runner.cancel(); await asyncio.gather(runner, return_exceptions=True)
        if sock: sock.close()
        # Include a failed provision's registered random slug, not other tenants.
        verify_owned_database()
        from app.core.tenant_utils import slug_to_schema_name
        async with engine.begin() as conn:
            for slug in reversed(allocated_slugs):
                row = (await conn.execute(text('SELECT id,schema_name FROM public.tenants WHERE slug=:slug'),
                    {'slug': slug})).one_or_none()
                if row is None:
                    continue
                assert row.schema_name == slug_to_schema_name(slug)
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{row.schema_name}" CASCADE'))
                await conn.execute(text('DELETE FROM public.tenant_migrations WHERE tenant_id=:id'), {'id': row.id})
                await conn.execute(text('DELETE FROM public.tenants WHERE id=:id'), {'id': row.id})
                cleaned.append(str(row.id))
        await engine.dispose()
        journal.write_text(json.dumps({'tenants': [{'id': str(t.id), 'slug': t.slug, 'schema': t.schema_name} for t in created],
            'cleaned': cleaned, 'socket_closed': sock is None or sock.fileno() == -1,
            'server_finished': runner is None or runner.done(), 'core_infrastructure_preserved': True}, indent=2) + '\n')
        print('OWNED_TEARDOWN: tenants=' + str(len(cleaned)) + '; socket closed; core preserved; journal=' + journal.name)
