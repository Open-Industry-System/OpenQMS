"""Owned normal-policy infrastructure; no catalog/authority/delivery replacements."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
import struct
from types import SimpleNamespace
from uuid import uuid4
import zlib

from fastapi import FastAPI
import httpx
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.core.tenant_transaction import TenantBinding
from app.database import TenantSession
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.factory import UserFactory
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, UserProductLine
from app.models.user import User
from app.schemas.platform import TenantCreateRequest
from tests.services.agent_runtime.trial_support import WORKER_SHA256

SUMMARY = 'capa.d4.summary.masked.v1'
MARKER = 'BODY-MUST-NOT-LEAVE-D4-TRIAL'
PASSWORD = 'owned-trial-bootstrap-password'


@dataclass(frozen=True)
class AttachmentE2ESamples:
    eicar: bytes
    encrypted_pdf: bytes
    expansion_docx: bytes
    clean_text: bytes


def _zipcrypto_encrypt(payload: bytes, password: bytes) -> bytes:
    """Build one deterministic encrypted DEFLATE member without test dependencies."""
    key0, key1, key2 = 0x12345678, 0x23456789, 0x34567890

    def crc32_byte(value: int, crc: int) -> int:
        value = (crc ^ value) & 0xFF
        for _ in range(8):
            value = (value >> 1) ^ (0xEDB88320 if value & 1 else 0)
        return ((crc >> 8) ^ value) & 0xFFFFFFFF

    def update_keys(value: int) -> None:
        nonlocal key0, key1, key2
        key0 = crc32_byte(value, key0)
        key1 = (key1 + (key0 & 0xFF)) * 134775813 + 1 & 0xFFFFFFFF
        key2 = crc32_byte(key1 >> 24, key2)

    def encrypt(value: int) -> int:
        temp = key2 | 2
        encrypted = value ^ ((temp * (temp ^ 1)) >> 8 & 0xFF)
        update_keys(value)
        return encrypted

    for value in password:
        update_keys(value)
    compressed = zlib.compress(payload)[2:-4]
    check_byte = zlib.crc32(payload).to_bytes(4, 'little')[-1]
    encrypted = bytes(encrypt(value) for value in bytes(range(1, 12)) + bytes((check_byte,)) + compressed)
    name = b'evidence.pdf'
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    local = struct.pack('<IHHHHHIIIHH', 0x04034B50, 20, 1, 8, 0, 0, crc, len(encrypted), len(payload), len(name), 0)
    central = struct.pack('<IHHHHHHIIIHHHHHII', 0x02014B50, 20, 20, 1, 8, 0, 0, crc, len(encrypted), len(payload),
        len(name), 0, 0, 0, 0, 0, 0)
    offset = len(local) + len(name) + len(encrypted)
    end = struct.pack('<IHHHHIIH', 0x06054B50, 0, 0, 1, 1, len(central) + len(name), offset, 0)
    return local + name + encrypted + central + name + end


def attachment_e2e_samples() -> AttachmentE2ESamples:
    """Return deterministic samples that a real ClamAV daemon must reject or allow."""
    eicar = (
        b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
    )
    encrypted_pdf = _zipcrypto_encrypt(b'%PDF-1.7\n% encrypted evidence fixture\n', b'openqms-e2e')
    document = b'<w:document xmlns:w="urn:openqms">' + b'A' * (2 * 1024 * 1024) + b'</w:document>'
    import io
    import zipfile
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('word/document.xml', document)
    return AttachmentE2ESamples(
        eicar=eicar,
        encrypted_pdf=encrypted_pdf,
        expansion_docx=stream.getvalue(),
        clean_text=b'OpenQMS controlled attachment E2E clean fixture.\n',
    )


class OwnedTrial(SimpleNamespace):
    @property
    def policy(self):
        return self.app.state.agent_local_trial_policy

    @asynccontextmanager
    async def session(self):
        async with self.factory(binding=self.binding) as db:
            db.info['agent_local_trial_policy'] = self.policy
            try:
                yield db
            finally:
                if db.in_transaction():
                    await db.rollback()

    async def restart(self, entries=None):
        if self.lifecycle is not None:
            await self.lifecycle.__aexit__(None, None, None)
        self.policy_path.write_text(json.dumps({'schema_version': 1,
            'entries': [self.entry] if entries is None else entries}))
        self.lifecycle = self.app.router.lifespan_context(self.app)
        await self.lifecycle.__aenter__()

    def grant_body(self, **changes):
        return {'capability_id': SUMMARY, 'factory_ids': [str(self.factory_id)],
            'object_ids': [str(self.report_id)], 'product_line_codes': [self.line],
            'expires_at': self.entry['expires_at'], 'enabled': True, **changes}

    async def enable(self):
        response = await self.admin.post(f'/api/admin/agent-plugins/{self.installation_id}/grants',
            json=self.grant_body())
        assert response.status_code == 201, 'normal grant bootstrap: '+response.text
        self.grant_id = response.json()['grant_id']
        response = await self.admin.patch(f'/api/admin/agent-plugins/{self.installation_id}', json={'enabled': True})
        assert response.status_code == 200, response.text

    async def create(self, key=None):
        response = await self.client.post('/api/agent/tasks', json={'report_id': str(self.report_id),
            'installation_id': str(self.installation_id), 'request_key': key or uuid4().hex,
            'initial_text': MARKER+' instruction is acknowledged, never executed'})
        assert response.status_code == 201, response.text
        return response.json()

    async def claim(self, key='owned-claim'):
        response = await self.client.post('/api/agent/runtime/claim', json={
            'installation_id': str(self.installation_id), 'secret': self.secret, 'request_key': key})
        return response


@pytest_asyncio.fixture
async def owned_local_trial(monkeypatch, tmp_path):
    import app.database as database
    import app.main as main
    from app.api import auth, agent_tasks, agent_runtime, capa
    from collections import defaultdict
    monkeypatch.setattr(auth, '_login_attempts', defaultdict(list))
    from app.api.admin import agent_plugins
    from app.core import tenant_context
    from app.services import tenant_migrator
    from app.core.security import hash_password

    url = os.environ['TEST_DATABASE_URL']
    assert url.rsplit('/', 1)[-1].startswith('openqms_r4a_') and url.endswith('_test')
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, sync_session_class=TenantSession, expire_on_commit=False)
    platform = async_sessionmaker(engine, expire_on_commit=False)
    for module, name, value in ((database, 'engine', engine), (database, 'async_session', platform),
            (database, 'tenant_async_session', factory), (tenant_context, 'async_session', platform),
            (tenant_migrator, 'engine', engine), (main, 'async_session', platform),
            (main, 'tenant_async_session', factory)):
        monkeypatch.setattr(module, name, value)
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(settings, 'AGENT_LOCAL_TRIAL_MODE', 'local_metadata')
    policy_path = tmp_path / 'trial-policy.json'
    with policy_path.open('x') as stream:
        policy_path.chmod(0o600)
        json.dump({'schema_version': 1, 'entries': []}, stream)
    monkeypatch.setattr(settings, 'AGENT_LOCAL_TRIAL_POLICY_PATH', str(policy_path))
    app = FastAPI(lifespan=main.lifespan)
    for router in (auth.router, agent_plugins.router, agent_tasks.router, agent_runtime.router, capa.router):
        app.include_router(router)
    app.add_middleware(tenant_context.TenantContextMiddleware)
    owned = None
    tenant = None
    slug = 'localtrial-'+uuid4().hex[:12]
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(name='Owned local metadata trial',
            slug=slug, admin_email='trial@example.test', admin_password=PASSWORD))
        binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, 'business')
        async with factory(binding=binding) as db:
            admin = await db.scalar(select(User).where(User.email == 'trial@example.test'))
            line = await db.scalar(select(ProductLine))
            role = await db.scalar(select(RoleDefinition).where(RoleDefinition.role_key == 'viewer'))
            executor = User(username='trial-executor', display_name='Trial executor',
                password_hash=hash_password(PASSWORD), role_id=role.id, legacy_role='viewer',
                factory_id=line.factory_id, is_active=True)
            db.add(executor)
            await db.flush()
            db.add(UserFactory(user_id=executor.user_id, factory_id=line.factory_id))
            db.add(UserProductLine(user_id=executor.user_id, product_line_code=line.code))
            report = CAPAEightD(document_no='8D-OWNED-TRIAL', title=MARKER, status='D4_ROOT_CAUSE',
                d2_description=MARKER, d4_root_cause=MARKER, factory_id=line.factory_id,
                product_line_code=line.code, created_by=admin.user_id)
            db.add(report)
            await db.flush()
            for conclusion, verified in [('passed', True), ('pending', False)]:
                db.add(CapaRootCauseVerification(capa_id=report.report_id, factory_id=report.factory_id,
                    root_cause_text=MARKER, result=MARKER,
                    evidence_attachments=[{'name': MARKER, 'url': '/synthetic-evidence'}],
                    conclusion=conclusion, is_verified=verified))
            await db.commit()
            owned = OwnedTrial(app=app, lifecycle=None, engine=engine, factory=factory, binding=binding,
                slug=slug, policy_path=policy_path, user_id=executor.user_id, admin_user_id=admin.user_id,
                admin_username=admin.username, role_id=executor.role_id, report_id=report.report_id,
                factory_id=line.factory_id, line=line.code, installation_id=None)
        await owned.restart([])
        transport = httpx.ASGITransport(app=app, client=('127.0.0.1', 31000))
        async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1',
                headers={'X-Tenant-ID': slug}, timeout=15) as admin_client, httpx.AsyncClient(
                transport=transport, base_url='http://127.0.0.1', headers={'X-Tenant-ID': slug}, timeout=15) as user_client:
            owned.admin, owned.client = admin_client, user_client
            for client, username, token_name in ((admin_client, owned.admin_username, 'admin_token'),
                    (user_client, 'trial-executor', 'user_token')):
                response = await client.post('/api/auth/login', json={'username': username, 'password': PASSWORD})
                assert response.status_code == 200, response.text
                login = response.json()
                setattr(owned, token_name, login['access_token'])
                client.headers['Authorization'] = 'Bearer '+login['access_token']
                if client is user_client:
                    owned.login = login
            response = await admin_client.post('/api/admin/agent-plugins', json={
                'plugin_key': 'openqms.local-d4-metadata', 'plugin_version': '1.0.0', 'manifest': {
                    'protocol_versions': ['1'], 'required_capabilities': [SUMMARY],
                    'optional_capabilities': [], 'supports_resume': False}})
            assert response.status_code == 201, response.text
            registered = response.json()
            owned.installation_id = registered['plugin']['installation_id']
            from uuid import UUID
            owned.installation_id = UUID(owned.installation_id)
            owned.plugin_id = owned.installation_id
            owned.secret = registered['secret']
            owned.entry = {'tenant_id': str(tenant.id), 'tenant_generation': tenant.generation,
                'installation_id': str(owned.installation_id), 'credential_epoch': 0,
                'plugin_key': 'openqms.local-d4-metadata', 'plugin_version': '1.0.0',
                'executor_user_id': str(owned.user_id), 'report_id': str(owned.report_id),
                'factory_id': str(owned.factory_id), 'product_line_code': owned.line,
                'expires_at': (datetime.now(UTC)+timedelta(minutes=20)).isoformat(), 'worker_sha256': WORKER_SHA256}
            await owned.restart()
            assert owned.policy.diagnostic == 'TRIAL_READY'
            yield owned
    finally:
        if owned is not None and owned.lifecycle is not None:
            await owned.lifecycle.__aexit__(None, None, None)
        async with engine.begin() as conn:
            row = (await conn.execute(text('SELECT id,schema_name FROM public.tenants WHERE slug=:slug'), {'slug': slug})).one_or_none()
            if row:
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{row.schema_name}" CASCADE'))
                await conn.execute(text('DELETE FROM public.tenant_migrations WHERE tenant_id=:id'), {'id': row.id})
                await conn.execute(text('DELETE FROM public.tenants WHERE id=:id'), {'id': row.id})
        await engine.dispose()


@pytest_asyncio.fixture
async def local_trial_server(owned_local_trial):
    import socket
    import uvicorn
    from tests.e2e.test_readonly_agent_process import Witness
    owned = owned_local_trial
    witness = Witness(owned.app, owned)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    server = uvicorn.Server(uvicorn.Config(witness, log_level='critical', access_log=False,
        lifespan='off', proxy_headers=False))
    runner = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(300):
            if server.started: break
            if runner.done(): await runner
            await asyncio.sleep(.01)
        assert server.started
        owned.base_url = f'http://127.0.0.1:{sock.getsockname()[1]}'
        owned.witness = witness
        yield owned
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(runner, 10)
        finally:
            sock.close()


async def execute_cli(owned, tmp_path, *, checkpoint='off', finish='off', key='local-trial'):
    import sys
    path = tmp_path / 'installation.secret'
    if not path.exists():
        with path.open('x') as stream:
            path.chmod(0o600)
            stream.write(owned.secret)
    process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'app.cli.agent_local_trial', 'run',
        '--installation-id', str(owned.installation_id), '--installation-secret-file', str(path),
        '--tenant-slug', owned.slug, '--api-base-url', owned.base_url, '--claim-key', key,
        '--checkpoint', checkpoint, '--finish', finish, env={'LANG': 'C', 'LC_ALL': 'C'},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    combined = stdout.decode()+stderr.decode()
    assert owned.secret not in combined and owned.admin_token not in combined and MARKER not in combined
    assert all(token not in combined for token in owned.witness.tokens)
    return process.returncode, stdout.decode(), stderr.decode()


async def business_snapshot(owned):
    from app.database import TenantBase
    # Authentication refresh and operational logs are not business facts.
    excluded = {'users', 'audit_logs', 'system_logs'}
    async with owned.session() as db:
        return {table.name: list((await db.execute(select(table).order_by(*table.primary_key.columns))).mappings())
            for table in sorted(TenantBase.metadata.tables.values(), key=lambda item: item.name)
            if not table.name.startswith('agent_') and table.name not in excluded}
