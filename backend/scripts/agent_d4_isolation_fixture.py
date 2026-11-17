"""Trusted fixture CLI for one dedicated isolation_synthetic database.

Run inside the full application container, uid 2002, cwd /app. Only bootstrap
creates initial synthetic fixture rows. All subsequent authority/proof/task
mutations use the real numeric-loopback HTTP application. No receiver claims
or UUIDs are trusted as delivery evidence. Importing this file performs no I/O.
"""
import asyncio
from contextvars import ContextVar
from contextlib import asynccontextmanager, redirect_stdout, redirect_stderr
from dataclasses import replace
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from urllib.parse import urlsplit, parse_qs
from uuid import UUID, uuid4

PRIVATE = '/private/d4'
POLICY_DIRECTORY = '/private/text-policy'
ORIGIN = 'http://127.0.0.1:18777'
BODY = 'capa.d4.root_cause_candidate.masked.v1'
PLUGIN = 'openqms.local-d4-root-cause-text'
WORKER_SHA256 = '3a2dfa9712c2ffebc62c26da0c4c03192be4ec905d1ee83e3ae198bfab51fa21'
START_MESSAGE = 'deliver_d4_root_cause_candidate_v1'
ACTIONS = ('bootstrap', 'register', 'authorize', 'export-config', 'verify', 'dual-ready', 'revoke', 'scope-negative', 'source-swap', 'credential-epoch', 'serve')
FILES = frozenset(('state.json', 'auth.json', 'receiver-config.json', 'snapshot.json',
                   'diagnostic.json', 'verification.json', 'policy.json', 'witness.json'))


class FixtureFailure(Exception):
    pass


def require(value, code):
    if not value:
        raise FixtureFailure(code)


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate_json_key')
        value[key] = item
    return value


def canonical(value):
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    raise FixtureFailure('snapshot_value_unsupported')


def encoded(value):
    return json.dumps(value, default=canonical, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def validate_database_url(value, approved_host=None):
    """No default DSN, TCP localhost, multi-host fallback or production database."""
    require(type(value) is str, 'database_url_invalid')
    try:
        url = urlsplit(value)
        query = parse_qs(url.query, strict_parsing=True)
        require(url.scheme == 'postgresql+asyncpg' and url.path == '/isolation_synthetic'
                and not url.fragment and bool(url.username), 'database_target_denied')
        require(set(query) <= {'host', 'port'} and all(len(values) == 1 for values in query.values()),
                'database_options_denied')
        if url.hostname is None:
            require(query.get('host') == ['/pgsocket'] and query.get('port', ['5432']) == ['5432'],
                    'database_socket_denied')
        else:
            require(type(approved_host) is str and re.fullmatch('oqmsi9pg[0-9a-f]+', approved_host)
                    and url.hostname == approved_host and url.port in (None, 5432) and not query,
                    'database_host_denied')
    except (ValueError, TypeError):
        raise FixtureFailure('database_url_invalid') from None


class PrivateStore:
    """Fixed private directory, pinned components, atomic 0600 JSON writes."""
    def __init__(self, directory=PRIVATE):
        require(directory in (PRIVATE, POLICY_DIRECTORY), 'private_directory_denied')
        require(os.geteuid() == 2002, 'fixture_uid_denied')
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in Path(directory).parts[1:]:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            info = os.fstat(fd)
            require(info.st_uid == 2002 and stat.S_IMODE(info.st_mode) == 0o700, 'private_directory_invalid')
            self.fd, fd = fd, None
        finally:
            if fd is not None:
                os.close(fd)

    def read(self, name):
        require(name in FILES, 'private_file_denied')
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == 2002 and before.st_nlink == 1
                    and stat.S_IMODE(before.st_mode) in ((0o400, 0o600) if name == 'policy.json' else (0o600,))
                    and before.st_size <= 256 * 1024, 'private_file_invalid')
            parts, size = [], 0
            while True:
                part = os.read(fd, min(8192, 256 * 1024 + 1 - size))
                if not part:
                    break
                parts.append(part); size += len(part)
                require(size <= 256 * 1024, 'private_file_limit')
            after = os.fstat(fd)
            require(all(getattr(before, key) == getattr(after, key) for key in
                        ('st_dev', 'st_ino', 'st_uid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')),
                    'private_file_changed')
            return json.loads(b''.join(parts), object_pairs_hook=unique)
        finally:
            os.close(fd)

    def exists(self, name):
        require(name in FILES, 'private_file_denied')
        try:
            self.read(name)
            return True
        except FileNotFoundError:
            return False

    def write(self, name, value):
        require(name in FILES, 'private_file_denied')
        if self.exists(name):
            pass  # Validate an existing target before replacing it.
        temporary = '.fixture-' + secrets.token_hex(16)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            raw = encoded(value)
            require(len(raw) <= 256 * 1024, 'private_file_limit')
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                require(count > 0, 'private_write_failed')
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        os.fsync(self.fd)

    def close(self):
        os.close(self.fd)


def tenant_binding(state):
    from app.core.tenant_transaction import TenantBinding
    require(re.fullmatch(r'tenant_[a-z0-9_]+', state['schema_name']) is not None
            and state['schema_name'] != 'public', 'tenant_schema_denied')
    return TenantBinding(UUID(state['tenant_id']), state['schema_name'], state['tenant_generation'], 'business')


@asynccontextmanager
async def session(state, *, readonly=False):
    from app.database import tenant_async_session, engine
    if readonly:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.core.tenant_transaction import bind_business_transaction
        binding = tenant_binding(state)
        # Set read-only/isolation before canonical binding performs its registry
        # queries. A TenantSession after_begin hook would execute those first.
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
                await connection.run_sync(bind_business_transaction, binding)
                async with AsyncSession(bind=connection, expire_on_commit=False) as db:
                    db.info['tenant_binding'] = binding
                    yield db
        return
    async with tenant_async_session(binding=tenant_binding(state)) as db:
        try:
            yield db
        finally:
            if db.in_transaction():
                await db.rollback()


async def business_snapshot(state):
    from app.database import TenantBase
    import app.models  # Register the complete tenant metadata, not a route subset.
    from sqlalchemy import select
    tables = {}
    async with session(state, readonly=True) as db:
        for table in sorted(TenantBase.metadata.tables.values(), key=lambda item: item.name):
            if table.name.startswith('agent_') or table.name in ('users', 'audit_logs', 'system_logs'):
                continue
            digest = hashlib.sha256()
            result = await db.stream(select(table).order_by(*table.primary_key.columns))
            async for row in result.mappings():
                digest.update(encoded(dict(row)))
                digest.update(b'\n')
            tables[table.name] = digest.hexdigest()
    return {'schema_version': 1, 'tables': tables, 'sha256': hashlib.sha256(encoded(tables)).hexdigest()}


class Fixture:
    def __init__(self, store):
        self.store, self.step = store, 'guard'

    async def bootstrap(self):
        from sqlalchemy import select
        from app.database import async_session
        from app.models.capa import CAPAEightD
        from app.models.fmea import FMEADocument
        from app.models.user import User
        from app.models.factory import UserFactory
        from app.models.product_line import ProductLine
        from app.models.role import RoleDefinition, UserProductLine
        from app.core.security import hash_password
        from app.schemas.platform import TenantCreateRequest
        from app.services.tenant_migrator import provision_new
        require(not self.store.exists('state.json') and not self.store.exists('auth.json'), 'bootstrap_already_started')
        self.step = 'seed_template'
        async with async_session() as db:
            source = (await db.execute(select(CAPAEightD).where(CAPAEightD.document_no == '8D-2026-001'))).scalar_one()
            require(source.status == 'D4_ROOT_CAUSE' and bool(source.d4_root_cause), 'seed_d4_missing')
            fmea = await db.get(FMEADocument, source.fmea_ref_id)
            require(fmea is not None and fmea.document_no == 'PFMEA-2026-001' and fmea.fmea_type == 'PFMEA'
                    and type(fmea.graph_data) is dict and type(fmea.graph_data.get('nodes')) is list
                    and type(fmea.graph_data.get('edges')) is list,
                    'seed_fmea_missing')
            graph = json.loads(json.dumps(fmea.graph_data))
            require(any(node.get('id') == 'fc_1' and node.get('type') == 'FailureCause'
                        for node in graph.get('nodes', [])), 'seed_source_missing')
            cause_b = dict(next(node for node in graph['nodes'] if node.get('id') == 'fc_1'))
            cause_b.update(id='i9_fc_B', name='I9 synthetic alternate cause B')
            graph['nodes'].append(cause_b)
            graph['edges'].extend({**edge, 'source': 'i9_fc_B'} for edge in list(graph.get('edges', []))
                                  if edge.get('source') == 'fc_1' and edge.get('type') == 'CAUSE_OF')
            report_values = {key: getattr(source, key) for key in
                             ('title', 'severity', 'd2_description', 'd4_root_cause')}
        suffix = secrets.token_hex(8)
        auth = {'admin_username': 'i9-' + suffix + '@example.test',
                'admin_password': 'Aa1!' + secrets.token_urlsafe(24),
                'employee_username': 'i9-viewer-' + suffix,
                'employee_password': 'Aa1!' + secrets.token_urlsafe(24)}
        state = {'schema_version': 1, 'phase': 'bootstrap_pending', 'tenant_slug': 'i9-' + suffix}
        self.store.write('auth.json', auth)
        self.store.write('state.json', state)
        self.step = 'tenant_provision'
        tenant = await provision_new(TenantCreateRequest(name='Dedicated D4 isolation synthetic tenant',
            slug=state['tenant_slug'], admin_email=auth['admin_username'], admin_password=auth['admin_password']))
        require(tenant.status == 'active', 'tenant_not_active')
        state.update(tenant_id=str(tenant.id), schema_name=tenant.schema_name, tenant_generation=tenant.generation)
        self.store.write('state.json', state)
        self.step = 'initial_fixture'
        async with session(state) as db:
            admin_id = await db.scalar(select(User.user_id).where(User.username == auth['admin_username']))
            line = (await db.execute(select(ProductLine).order_by(ProductLine.code))).scalars().first()
            viewer_role = await db.scalar(select(RoleDefinition.id).where(RoleDefinition.role_key == 'viewer'))
            require(admin_id is not None and line is not None and viewer_role is not None, 'tenant_defaults_missing')
            employee = User(username=auth['employee_username'], display_name='I9 synthetic viewer',
                password_hash=hash_password(auth['employee_password']), role_id=viewer_role, legacy_role='viewer',
                factory_id=line.factory_id, is_active=True)
            db.add(employee)
            await db.flush()
            db.add(UserFactory(user_id=employee.user_id, factory_id=line.factory_id))
            db.add(UserProductLine(user_id=employee.user_id, product_line_code=line.code))
            # Authorized initial fixture only: no transition of an existing report,
            # no copied source proof, capability grant, task, run or receipt.
            target_fmea = FMEADocument(document_no='I9-PFMEA-' + suffix, title='I9 synthetic source',
                fmea_type='PFMEA', status='approved', graph_data=graph, product_line_code=line.code,
                factory_id=line.factory_id, created_by=admin_id, updated_by=admin_id,
                approved_by=admin_id, approved_at=datetime.now(timezone.utc))
            db.add(target_fmea)
            await db.flush()
            target = CAPAEightD(document_no='I9-8D-' + suffix, status='D4_ROOT_CAUSE',
                fmea_ref_id=target_fmea.fmea_id, factory_id=line.factory_id, product_line_code=line.code,
                created_by=admin_id, **report_values)
            db.add(target)
            await db.flush()
            outside = CAPAEightD(document_no='I9-OUTSIDE-' + suffix, status='D4_ROOT_CAUSE',
                fmea_ref_id=target_fmea.fmea_id, factory_id=line.factory_id, product_line_code=line.code,
                created_by=admin_id, **report_values)
            db.add(outside)
            await db.flush()
            state.update(outside_report_id=str(outside.report_id), alternate_cause_node_id='i9_fc_B', admin_user_id=str(admin_id), employee_user_id=str(employee.user_id),
                         factory_id=str(line.factory_id), product_line_code=line.code,
                         report_id=str(target.report_id), fmea_id=str(target_fmea.fmea_id), cause_node_id='fc_1')
            await db.commit()
        state['phase'] = 'bootstrapped'
        self.store.write('state.json', state)

    @asynccontextmanager
    async def clients(self, state, auth):
        import httpx
        headers = {'X-Tenant-ID': state['tenant_slug']}
        async with httpx.AsyncClient(base_url=ORIGIN, headers=headers, timeout=20,
                                     trust_env=False, follow_redirects=False) as admin, \
                httpx.AsyncClient(base_url=ORIGIN, headers=headers, timeout=20,
                                  trust_env=False, follow_redirects=False) as employee:
            for client, role in ((admin, 'admin'), (employee, 'employee')):
                token = auth.get(role + '_jwt')
                if token is None:
                    self.step = 'tcp_login_' + role
                    login = await self.request(client, 'POST', '/api/auth/login', 200,
                        {'username': auth[role + '_username'], 'password': auth[role + '_password']})
                    require(str(login['user']['user_id']) == state[role + '_user_id'], 'login_identity_mismatch')
                    token = login['access_token']
                    require(type(token) is str and bool(token), 'login_token_invalid')
                    auth[role + '_jwt'] = token
                    # Persist each successful login so a later role failure
                    # does not force a repeated login attempt on rerun.
                    self.store.write('auth.json', auth)
                else:
                    require(type(token) is str and bool(token), 'cached_login_token_invalid')
                    client.headers['Authorization'] = 'Bearer ' + token
                    self.step = 'tcp_cached_identity_' + role
                    user = await self.request(client, 'GET', '/api/auth/me', 200)
                    require(str(user['user_id']) == state[role + '_user_id'], 'cached_login_identity_mismatch')
                client.headers['Authorization'] = 'Bearer ' + token
            yield admin, employee

    async def runtime_claim(self, state, auth, *, status=200, secret=None):
        import httpx
        # A fresh installation-only client has exactly the receiver's claim
        # credential surface. Staff JWTs are never inherited here.
        async with httpx.AsyncClient(base_url=ORIGIN, headers={'X-Tenant-ID': state['tenant_slug']},
                timeout=20, trust_env=False, follow_redirects=False) as runtime:
            require('Authorization' not in runtime.headers, 'staff_credential_on_runtime_claim')
            return await self.request(runtime, 'POST', '/api/agent/runtime/claim', status, {
                'installation_id': state['installation_id'],
                'secret': auth['installation_secret'] if secret is None else secret,
                'request_key': secrets.token_hex(24)})

    @staticmethod
    def require_nonempty_candidate(value):
        require(type(value) is str and bool(value.strip()), 'candidate_body_empty')

    @staticmethod
    def require_no_body(response, previous_text):
        # Compare decoded/normalized JSON strings, including escaped Unicode;
        # neither response nor body is included in an assertion/diagnostic.
        require(type(previous_text) is str and bool(previous_text.strip()), 'candidate_body_empty')
        def strings(value):
            if type(value) is str:
                yield value
            elif type(value) is dict:
                for key, item in value.items():
                    yield from strings(key)
                    yield from strings(item)
            elif type(value) is list:
                for item in value:
                    yield from strings(item)
        import unicodedata
        needle = unicodedata.normalize('NFKC', previous_text)
        require(all(needle not in unicodedata.normalize('NFKC', item) for item in strings(response)),
                'denied_response_contains_body')

    async def request(self, client, method, path, status, payload=None):
        response = await client.request(method, path, json=payload)
        require(response.status_code == status, 'http_status_mismatch')
        require(len(response.content) <= 256 * 1024, 'http_response_limit')
        # Never put a response body into assertions, diagnostics or stdout.
        value = response.json()
        require(type(value) is dict, 'http_shape_invalid')
        return value

    async def register(self):
        state, auth = self.store.read('state.json'), self.store.read('auth.json')
        require(state['phase'] == 'bootstrapped', 'register_phase_denied')
        async with self.clients(state, auth) as (admin, _):
            self.step = 'tcp_register_installation'
            result = await self.request(admin, 'POST', '/api/admin/agent-plugins', 201, {
                'plugin_key': PLUGIN, 'plugin_version': '1.0.0', 'manifest': {
                    'protocol_versions': ['1'], 'required_capabilities': [BODY],
                    'optional_capabilities': [], 'supports_resume': False}})
            plugin = result['plugin']
            require(plugin['plugin_key'] == PLUGIN and plugin['credential_epoch'] == 0,
                    'installation_binding_invalid')
            state.update(installation_id=plugin['installation_id'], credential_epoch=plugin['credential_epoch'])
            auth['installation_secret'] = result['secret']
            self.store.write('auth.json', auth)
            self.store.write('state.json', state)
        expires = (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()
        entry = dict(tenant_id=state['tenant_id'], tenant_generation=state['tenant_generation'],
            installation_id=state['installation_id'], credential_epoch=state['credential_epoch'],
            plugin_key=PLUGIN, plugin_version='1.0.0', executor_user_id=state['employee_user_id'],
            report_id=state['report_id'], factory_id=state['factory_id'],
            product_line_code=state['product_line_code'], expires_at=expires,
            worker_sha256=WORKER_SHA256, redaction_terms=['I9-SYNTHETIC-PRIVATE-TERM'])
        policy = {'schema_version': 1, 'entries': [entry]}
        self.step = 'freeze_policy'
        directory = PrivateStore(POLICY_DIRECTORY)
        try:
            directory.write('policy.json', policy)
        finally:
            directory.close()
        state.update(phase='registered_restart_required', expires_at=expires,
                     policy_sha256=hashlib.sha256(encoded(policy)).hexdigest())
        self.store.write('state.json', state)

    def policy(self, state):
        from app.config import settings
        from app.services.agent_runtime.local_d4_text_policy import load_text_policy
        directory = PrivateStore(POLICY_DIRECTORY)
        try:
            raw = directory.read('policy.json')
        finally:
            directory.close()
        require(hashlib.sha256(encoded(raw)).hexdigest() == state['policy_sha256'], 'policy_changed')
        require(settings.AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE == POLICY_DIRECTORY + '/policy.json',
                'policy_setting_mismatch')
        policy = load_text_policy(settings.AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE, enabled=True,
            runtime_enabled=True, tenant_mode='dev', now=datetime.now(timezone.utc), key=settings.SECRET_KEY.encode())
        require(policy.diagnostic == 'TEXT_POLICY_READY' and len(policy.entries) == 1, 'frozen_policy_not_ready')
        row = policy.entries[0]
        require(str(row.tenant_id) == state['tenant_id'] and row.tenant_generation == state['tenant_generation']
                and str(row.installation_id) == state['installation_id']
                and str(row.executor_user_id) == state['employee_user_id'] and str(row.report_id) == state['report_id'],
                'policy_binding_mismatch')
        return policy

    async def authorize(self):
        from sqlalchemy import select
        from app.models.capa import CAPAEightD
        state, auth = self.store.read('state.json'), self.store.read('auth.json')
        require(state['phase'] == 'registered_restart_required', 'authorize_phase_denied')
        policy = self.policy(state)
        async with session(state, readonly=True) as db:
            root_cause = await db.scalar(select(CAPAEightD.d4_root_cause).where(CAPAEightD.report_id == UUID(state['report_id'])))
        async with self.clients(state, auth) as (admin, employee):
            self.step = 'tcp_source_declaration'
            proof = await self.request(admin, 'POST', '/api/capa/' + state['report_id'] + '/root-cause-verifications', 200, {
                'root_cause_text': root_cause, 'method': 'measurement', 'conclusion': 'passed',
                'source_ref': {'fmea_id': state['fmea_id'], 'cause_node_id': state['cause_node_id']},
                'source_declaration': {'declares_complete_coverage': True}})
            require(proof.get('source_proof_issued') is True, 'source_proof_not_issued')
            scope = {'target_report_id': state['report_id'], 'fmea_id': state['fmea_id'], 'cause_node_id': state['cause_node_id']}
            state['source_scope'] = scope
            self.step = 'tcp_parent_grant'
            grant = await self.request(admin, 'POST', '/api/admin/agent-plugins/' + state['installation_id'] + '/grants', 201, {
                'capability_id': BODY, 'factory_ids': [state['factory_id']], 'object_ids': [state['report_id']],
                'product_line_codes': [state['product_line_code']], 'expires_at': state['expires_at'],
                'enabled': True, 'derived_source_scope': scope})
            state['parent_grant_id'] = grant['grant_id']
            self.store.write('state.json', state)
            self.step = 'tcp_enable_installation'
            await self.request(admin, 'PATCH', '/api/admin/agent-plugins/' + state['installation_id'], 200, {'enabled': True})
            self.step = 'tcp_ready_task'
            created = await self.create_task(employee, state, secrets.token_hex(24))
            state['task_id'] = created['task_id']
            self.store.write('state.json', state)
            require(created.get('status') == 'ready', 'task_not_ready')
        self.step = 'trusted_parent_task_grants'
        await self.assert_grants(state, state['task_id'])
        witness = self.store.read('witness.json')
        require(witness.get('kind') == 'full_app_request_sql_witness.v1' and
                type(witness.get('next_sequence')) is int, 'full_app_witness_missing')
        state.update(phase='authorized', policy_binding=policy.entries[0].binding_sha256,
                     verification_id=proof['verification_id'], witness_generation=witness['generation'],
                     witness_start_sequence=witness['next_sequence'])
        self.store.write('state.json', state)
        self.step = 'business_snapshot_before'
        self.store.write('snapshot.json', await business_snapshot(state))

    async def create_task(self, client, state, key):
        value = await self.request(client, 'POST', '/api/agent/tasks', 201, {
            'report_id': state['report_id'], 'installation_id': state['installation_id'],
            'request_key': key, 'initial_text': START_MESSAGE, 'derived_source_scope': state['source_scope']})
        # Callers record the exact returned ID before validating readiness, so
        # even a rejected 201 response remains available to trusted cleanup.
        return value

    async def assert_grants(self, state, task_id):
        from sqlalchemy import select
        from app.models.agent_task import AgentTask, AgentRun, AgentTaskGrant
        from app.models.agent_plugin import AgentPluginGrant
        from app.models.agent_derived_source import AgentTaskDerivedSourceScope, AgentPluginDerivedSourceScope
        from app.models.agent_d4_recovery import D4TaskParentGrant
        from app.models.audit import AuditLog
        async with session(state, readonly=True) as db:
            task = await db.get(AgentTask, UUID(task_id))
            require(task is not None and task.target_capa_id == UUID(state['report_id']) and
                    task.executor_user_id == UUID(state['employee_user_id']) and task.initiator_id == UUID(state['employee_user_id']) and
                    task.preferred_installation_id == UUID(state['installation_id']), 'task_binding_invalid')
            grants = list((await db.scalars(select(AgentTaskGrant).where(AgentTaskGrant.task_id == task.task_id,
                           AgentTaskGrant.capability_id == BODY))).all())
            require(len(grants) == 1, 'task_grant_missing')
            task_grant = grants[0]
            parent = await db.get(D4TaskParentGrant, task_grant.grant_id)
            require(parent is not None and parent.plugin_grant_id == UUID(state['parent_grant_id']), 'parent_grant_missing')
            plugin_grant = await db.get(AgentPluginGrant, parent.plugin_grant_id)
            require(plugin_grant is not None and plugin_grant.enabled and plugin_grant.installation_id == UUID(state['installation_id']),
                    'plugin_grant_invalid')
            for grant in (task_grant, plugin_grant):
                require(grant.factory_ids == [state['factory_id']] and grant.object_ids == [state['report_id']]
                        and grant.product_line_codes == [state['product_line_code']] and grant.capability_id == BODY
                        and grant.expires_at is not None
                        and datetime.now(timezone.utc) < grant.expires_at <= datetime.fromisoformat(state['expires_at']),
                        'grant_scope_not_exact')
            require(task_grant.access_kind == 'read', 'task_grant_access_invalid')
            for model, column, identifier in ((AgentTaskDerivedSourceScope, AgentTaskDerivedSourceScope.task_grant_id, task_grant.grant_id),
                                              (AgentPluginDerivedSourceScope, AgentPluginDerivedSourceScope.plugin_grant_id, parent.plugin_grant_id)):
                scopes = list((await db.scalars(select(model).where(column == identifier))).all())
                require(len(scopes) == 1 and scopes[0].target_report_id == UUID(state['report_id']) and
                        scopes[0].fmea_id == UUID(state['fmea_id']) and scopes[0].cause_node_id == state['cause_node_id'],
                        'derived_scope_invalid')
            runs = list((await db.scalars(select(AgentRun).where(AgentRun.task_id == task.task_id))).all())
            require(len(runs) == 1, 'first_run_missing')
            audit = await db.scalar(select(AuditLog.log_id).where(AuditLog.action == 'CREATE_AGENT_TASK', AuditLog.record_id == task.task_id))
            require(audit is not None, 'task_audit_missing')

    async def export_config(self):
        state, auth = self.store.read('state.json'), self.store.read('auth.json')
        require(state['phase'] == 'authorized', 'config_phase_denied')
        self.policy(state)
        self.step = 'export_six_fields'
        config = dict(origin=ORIGIN, tenant_slug=state['tenant_slug'], installation_id=state['installation_id'],
                      secret=auth['installation_secret'], request_key=secrets.token_hex(24), expected_report_id=state['report_id'])
        self.store.write('receiver-config.json', config)

    async def verify(self):
        from sqlalchemy import select
        from app.models.agent_task import AgentTask, AgentRun, AgentTaskMessage
        from app.models.agent_plugin import AgentPluginInstallation
        from app.models.capa_d4_delivery import AgentRestrictedProjectionReceipt
        from app.models.audit import AuditLog
        from app.services.agent_runtime import d4_text_delivery as delivery
        from app.services.capa_d4_redaction import RULE_VERSION
        state = self.store.read('state.json')
        require(state['phase'] == 'authorized', 'verify_phase_denied')
        self.step = 'verify_frozen_policy'
        policy = self.policy(state)
        require(hmac.compare_digest(policy.entries[0].binding_sha256, state['policy_binding']), 'policy_binding_changed')
        await self.assert_grants(state, state['task_id'])
        self.step = 'trusted_delivery_facts'
        async with session(state, readonly=True) as db:
            task_id = UUID(state['task_id'])
            task = await db.get(AgentTask, task_id)
            runs = list((await db.scalars(select(AgentRun).where(AgentRun.task_id == task_id))).all())
            require(task.status == 'completed' and len(runs) == 1, 'task_not_completed')
            run = runs[0]
            require(run.status == 'completed' and run.installation_id == UUID(state['installation_id']) and
                    run.accepted_message_seq == 1, 'run_not_completed')
            messages = list((await db.scalars(select(AgentTaskMessage).where(AgentTaskMessage.task_id == task_id))).all())
            require(len(messages) == 1 and messages[0].state == 'accepted' and messages[0].sequence == 1 and
                    messages[0].content == START_MESSAGE, 'message_not_accepted')
            receipts = list((await db.scalars(select(AgentRestrictedProjectionReceipt).where(
                AgentRestrictedProjectionReceipt.task_id == task_id))).all())
            require(len(receipts) == 1, 'receipt_count_invalid')
            receipt = receipts[0]
            require(receipt.run_id == run.run_id and receipt.source_capa_id == UUID(state['report_id']) and
                    receipt.tenant_generation == state['tenant_generation'] and receipt.projection_id == BODY and receipt.data_class == 'restricted' and
                    receipt.lease_epoch == messages[0].delivery_epoch and receipt.lease_epoch < run.lease_epoch,
                    'receipt_binding_invalid')
            source = await delivery.load_current_source_state(db, report_id=UUID(state['report_id']))
            require(source.fmea_id == UUID(state['fmea_id']) and source.node_id == state['cause_node_id'] and str(source.verification_id) == state['verification_id'], 'receipt_source_invalid')
            source = replace(source, terms=policy.entries[0].redaction_terms, policy_binding=policy.entries[0].binding_sha256)
            candidate = await delivery.build_root_candidate(binding=tenant_binding(state), state=source)
            self.require_nonempty_candidate(candidate.text)
            installation = await db.get(AgentPluginInstallation, UUID(state['installation_id']))
            content = dict(protocol='1', run_id=run.run_id, task_id=task_id, report_id=UUID(state['report_id']),
                recipient_installation_id=installation.installation_id, plugin_version=installation.plugin_version,
                receipt_id=receipt.receipt_id, generated_at=receipt.created_at, projection_id=BODY,
                data_class='restricted', projection='masked', candidate_kind='redaction_candidate',
                declassification_status='not_approved', source_proof='employee_declared_complete_v1',
                source_authorization='current', model_delivery_allowed=False, delivery_scope='local_plugin_only',
                rule_version=RULE_VERSION, source_version=candidate.source_version, source_proof_digest=candidate.source_proof_digest,
                policy_binding=candidate.policy_binding, field='d4_root_cause', text=candidate.text)
            safe = {key: canonical(value) if isinstance(value, (UUID, datetime)) else value for key, value in content.items()}
            require(hmac.compare_digest(delivery._digest('openqms.d4.projection.v1', safe), receipt.projection_digest),
                    'receipt_projection_digest_mismatch')
            audits = list((await db.scalars(select(AuditLog).where(AuditLog.action == 'D4_TEXT_RELEASE_COMMITTED',
                            AuditLog.record_id == receipt.receipt_id))).all())
            require(len(audits) == 1 and audits[0].correlation_id == run.run_id and
                    audits[0].operated_by == UUID(state['employee_user_id']) and
                    audits[0].changed_fields.get('projection_digest') == receipt.projection_digest,
                    'receipt_audit_missing')
            report = {'schema_version': 1, 'task_id': str(task_id), 'run_id': str(run.run_id),
                      'receipt_id': str(receipt.receipt_id), 'projection_digest': receipt.projection_digest,
                      'policy_binding': state['policy_binding'], 'source_verified': True, 'audit_verified': True}
        self.step = 'full_app_six_routes'
        witness = self.store.read('witness.json')
        require(witness.get('generation') == state['witness_generation'], 'witness_generation_changed')
        observed = [row for row in witness.get('records', []) if row.get('sequence', -1) > state['witness_start_sequence']]
        require([(row.get('route'), row.get('status')) for row in observed] == [
            ('claim', 200), ('capabilities', 200), ('messages_claim', 200), ('body', 200),
            ('messages_ack', 200), ('finish', 200)], 'six_real_routes_not_observed')
        report['six_full_app_routes_verified'] = True
        self.step = 'business_snapshot_after'
        after = await business_snapshot(state)
        require(after == self.store.read('snapshot.json'), 'business_snapshot_changed')
        report['business_snapshot_sha256'] = after['sha256']
        self.store.write('verification.json', report)
        state['phase'] = 'verified'
        self.store.write('state.json', state)


    async def cancel_owned_tasks(self, employee, state, task_ids, field, *, preserve_failure):
        from sqlalchemy import select
        from app.models.agent_task import AgentTask, AgentRun
        failed = []
        for task_id in task_ids:
            try:
                payload = {'action': 'cancel', 'idempotency_key': secrets.token_hex(24)}
                async with session(state, readonly=True) as db:
                    task = await db.get(AgentTask, UUID(task_id))
                    require(task is not None, 'owned_task_missing')
                    if task.status == 'cancelled':
                        continue  # An earlier partial cleanup already committed.
                    runs = list((await db.scalars(select(AgentRun).where(
                        AgentRun.task_id == UUID(task_id),
                        AgentRun.status.in_(('pending', 'active', 'paused'))))).all())
                    require(len(runs) <= 1, 'owned_task_run_ambiguous')
                    if runs:
                        payload.update(run_id=str(runs[0].run_id), expected_epoch=runs[0].lease_epoch)
                result = await self.request(employee, 'POST', '/api/agent/tasks/' + task_id + '/control', 200,
                    payload)
                require(result['task_status'] == 'cancelled' and result['run_status'] in (None, 'stopped'),
                        'owned_task_cancel_failed')
                async with session(state, readonly=True) as db:
                    task = await db.get(AgentTask, UUID(task_id))
                    require(task is not None and task.status == 'cancelled', 'owned_task_cancel_not_confirmed')
            except Exception:
                failed.append(task_id)
        state[field] = failed
        try:
            self.store.write('state.json', state)
        except Exception:
            if not preserve_failure:
                raise FixtureFailure('owned_task_cleanup_record_failed') from None
            return False
        if failed and not preserve_failure:
            raise FixtureFailure('owned_task_cleanup_not_confirmed')
        return not failed

    async def dual_ready(self):
        from sqlalchemy import select
        from app.models.agent_task import AgentTask, AgentRun
        state, auth = self.store.read('state.json'), self.store.read('auth.json')
        require(state['phase'] == 'verified', 'dual_phase_denied')
        self.policy(state)
        created, claims = [], {}
        async with self.clients(state, auth) as (_, employee):
            # LoginAuditLog belongs to TenantBase and remains covered. Begin
            # the invariant after normal logins, before the witnessed actions.
            before = await business_snapshot(state)
            try:
                self.step = 'tcp_dual_ready'
                for _ in range(2):
                    task = await self.create_task(employee, state, secrets.token_hex(24))
                    created.append(task['task_id'])
                    state['dual_ready_task_ids'] = list(created)
                    self.store.write('state.json', state)
                    require(task.get('status') == 'ready', 'task_not_ready')
                    await self.assert_grants(state, task['task_id'])
                async with session(state, readonly=True) as db:
                    ready = set(str(value) for value in (await db.scalars(select(AgentTask.task_id).where(
                        AgentTask.status == 'ready', AgentTask.preferred_installation_id == UUID(state['installation_id'])))).all())
                    require(ready == set(created), 'unexpected_ready_tasks')
                self.step = 'tcp_two_distinct_claim_keys'
                for _ in range(2):
                    claim = await self.runtime_claim(state, auth)
                    require(claim['task_id'] in created and claim['task_id'] not in claims, 'claim_did_not_reach_second_task')
                    claims[claim['task_id']] = claim
                    # Run tokens remain secret even in the trusted witness result.
                    auth['dual_runtime_tokens'] = {value['run_id']: value['token'] for value in claims.values()}
                    self.store.write('auth.json', auth)
                require(len({value['run_id'] for value in claims.values()}) == 2, 'dual_runs_not_distinct')
                async with session(state, readonly=True) as db:
                    for task_id, claim in claims.items():
                        run = await db.get(AgentRun, UUID(claim['run_id']))
                        require(run is not None and run.task_id == UUID(task_id) and run.status == 'active' and
                                run.installation_id == UUID(state['installation_id']) and run.lease_epoch == claim['lease_epoch'],
                                'dual_platform_fact_missing')
            finally:
                failure_in_flight = sys.exc_info()[0] is not None
                cleanup_failed = []
                self.step = 'tcp_dual_cancel_owned_tasks'
                for task_id in created:
                    try:
                        claim = claims.get(task_id)
                        payload = {'action': 'cancel', 'idempotency_key': secrets.token_hex(24)}
                        if claim is not None:
                            payload.update(run_id=claim['run_id'], expected_epoch=claim['lease_epoch'])
                        result = await self.request(employee, 'POST', '/api/agent/tasks/' + task_id + '/control', 200, payload)
                        require(result['task_status'] == 'cancelled' and
                                result['run_status'] == ('stopped' if claim is not None else None), 'dual_cancel_failed')
                        async with session(state, readonly=True) as db:
                            task = await db.get(AgentTask, UUID(task_id))
                            require(task is not None and task.status == 'cancelled', 'dual_task_cleanup_not_confirmed')
                    except Exception:
                        # Attempt every known task, retaining exact private IDs
                        # without replacing the original failed witness.
                        cleanup_failed.append(task_id)
                if cleanup_failed:
                    state['dual_cleanup_unconfirmed_task_ids'] = cleanup_failed
                    try:
                        self.store.write('state.json', state)
                    except Exception:
                        if not failure_in_flight:
                            raise
                    if not failure_in_flight:
                        raise FixtureFailure('dual_cleanup_not_confirmed')
        require(len(claims) == 2 and len(created) == 2, 'dual_witness_incomplete')
        async with session(state, readonly=True) as db:
            for task_id, claim in claims.items():
                run = await db.get(AgentRun, UUID(claim['run_id']))
                require(run.status == 'stopped' and run.claim_key is None and run.lease_expires_at is None,
                        'dual_cleanup_not_confirmed')
        require(await business_snapshot(state) == before, 'dual_business_snapshot_changed')
        state.update(phase='dual_ready_verified', dual_ready_run_ids=[value['run_id'] for value in claims.values()],
                     installation_scope_wider_than_single_run=True)
        self.store.write('state.json', state)

    async def revoke(self):
        from sqlalchemy import select
        from app.models.agent_task import AgentRun, AgentTask
        state, auth = self.store.read('state.json'), self.store.read('auth.json')
        require(state['phase'] in ('verified', 'dual_ready_verified', 'scope_negative_verified', 'source_swap_verified'), 'revoke_phase_denied')
        self.policy(state)
        # The observer must live in the actual application process. Installing an
        # event listener in this separate client process would prove nothing.
        witness_before = self.store.read('witness.json')
        require(witness_before.get('kind') == 'full_app_request_sql_witness.v1', 'stop_sql_witness_not_configured')
        task_id = None
        cancelled = False
        async with self.clients(state, auth) as (admin, employee):
            before = await business_snapshot(state)
            try:
                self.step = 'tcp_revoke_prepare'
                created = await self.create_task(employee, state, secrets.token_hex(24))
                task_id = created['task_id']
                state['revocation_task_id'] = task_id
                self.store.write('state.json', state)
                require(created.get('status') == 'ready', 'task_not_ready')
                claim = await self.runtime_claim(state, auth)
                require(claim['task_id'] == task_id, 'revocation_claim_target_mismatch')
                auth['revocation_runtime_token'] = claim['token']
                self.store.write('auth.json', auth)
                import httpx
                async with httpx.AsyncClient(base_url=ORIGIN, headers={'X-Tenant-ID': state['tenant_slug'],
                    'Authorization': 'Bearer ' + claim['token']}, timeout=20, trust_env=False) as runtime:
                    body = await self.request(runtime, 'GET', '/api/agent/runtime/capa/d4/root-cause-text', 200)
                    require(body['report_id'] == state['report_id'] and body['recipient_installation_id'] == state['installation_id'],
                            'revocation_body_binding_invalid')
                    self.require_nonempty_candidate(body.get('text'))
                    self.step = 'tcp_revoke_parent_grant'
                    await self.request(admin, 'PATCH', '/api/admin/agent-plugins/' + state['installation_id'] +
                        '/grants/' + state['parent_grant_id'], 200, {'enabled': False})
                    denied = await self.request(runtime, 'GET', '/api/agent/runtime/capa/d4/root-cause-text', 401)
                    self.require_no_body(denied, body['text'])
                    epoch = claim['lease_epoch']
                    self.step = 'tcp_pause_after_revocation'
                    paused = await self.request(employee, 'POST', '/api/agent/tasks/' + task_id + '/control', 200,
                        {'action': 'pause', 'run_id': claim['run_id'], 'expected_epoch': epoch,
                         'idempotency_key': secrets.token_hex(24)})
                    require(paused['task_status'] == 'paused' and paused['lease_epoch'] > epoch, 'pause_epoch_not_fenced')
                    self.step = 'tcp_resume_denied_after_revocation'
                    await self.request(employee, 'POST', '/api/agent/tasks/' + task_id + '/control', 403,
                        {'action': 'resume', 'run_id': claim['run_id'], 'expected_epoch': paused['lease_epoch'],
                         'idempotency_key': secrets.token_hex(24)})
                    async with session(state, readonly=True) as db:
                        task = await db.get(AgentTask, UUID(task_id))
                        run = await db.get(AgentRun, UUID(claim['run_id']))
                        require(task.status == run.status == 'paused' and run.lease_epoch == paused['lease_epoch'],
                                'denied_resume_changed_state')
                    self.step = 'tcp_cancel_after_revocation'
                    stopped = await self.request(employee, 'POST', '/api/agent/tasks/' + task_id + '/control', 200,
                        {'action': 'cancel', 'run_id': claim['run_id'], 'expected_epoch': paused['lease_epoch'],
                         'idempotency_key': secrets.token_hex(24)})
                    require(stopped['task_status'] == 'cancelled' and stopped['run_status'] == 'stopped' and
                            stopped['lease_epoch'] > paused['lease_epoch'], 'cancel_epoch_not_fenced')
                    cancelled = True
                    denied = await self.request(runtime, 'GET', '/api/agent/runtime/capa/d4/root-cause-text', 401)
                    self.require_no_body(denied, body['text'])
            finally:
                if task_id is not None and not cancelled:
                    # Cancel-without-position is the normal employee stop path;
                    # never fabricate a finish or mutate rows as cleanup.
                    await self.cancel_owned_tasks(employee, state, [task_id],
                        'revocation_cleanup_unconfirmed_task_ids', preserve_failure=sys.exc_info()[0] is not None)
        self.step = 'trusted_revocation_facts'
        async with session(state, readonly=True) as db:
            run = await db.get(AgentRun, UUID(claim['run_id']))
            require(run.status == 'stopped' and run.claim_key is None and run.lease_expires_at is None,
                    'revoked_run_not_stopped')
        witness_after = self.store.read('witness.json')
        require(witness_after.get('generation') == witness_before.get('generation'), 'sql_witness_generation_changed')
        controls = [row for row in witness_after.get('records', []) if row.get('route') == 'control'
                    and row.get('sequence', -1) > witness_before['next_sequence']]
        require([row.get('status') for row in controls] == [200, 403, 200], 'control_witness_incomplete')
        require(all(type(row.get('statements')) is int and row['statements'] > 0 for row in controls),
                'control_sql_witness_empty')
        require(all(row.get('body_source_reads') == 0 for row in (controls[0], controls[2])),
                'stop_read_body_or_source')
        require(await business_snapshot(state) == before, 'revoke_business_snapshot_changed')
        state.update(phase='revocation_verified', revocation_run_id=claim['run_id'],
                     stop_sql_body_source_reads=0, revocation_statuses=[200, 401, 200, 403, 200, 401])
        self.store.write('state.json', state)


    async def declare_source(self, admin, state, node_id, *, report_id=None):
        from sqlalchemy import select
        from app.models.capa import CAPAEightD
        target = report_id or state['report_id']
        async with session(state, readonly=True) as db:
            text = await db.scalar(select(CAPAEightD.d4_root_cause).where(CAPAEightD.report_id == UUID(target)))
        self.require_nonempty_candidate(text)
        value = await self.request(admin, 'POST', '/api/capa/' + target + '/root-cause-verifications', 200, {
            'root_cause_text': text, 'method': 'measurement', 'conclusion': 'passed',
            'source_ref': {'fmea_id': state['fmea_id'], 'cause_node_id': node_id},
            'source_declaration': {'declares_complete_coverage': True}})
        require(value.get('source_proof_issued') is True, 'source_proof_not_issued')
        return value

    @asynccontextmanager
    async def run_client(self, state, token):
        import httpx
        async with httpx.AsyncClient(base_url=ORIGIN, headers={'X-Tenant-ID': state['tenant_slug'],
                'Authorization': 'Bearer ' + token}, timeout=20, trust_env=False,
                follow_redirects=False) as runtime:
            yield runtime

    async def denied_read(self, runtime, previous_text, *, receipt_id=None, allowed=(401, 403)):
        path = '/api/agent/runtime/capa/d4/root-cause-text'
        if receipt_id is not None:
            require(str(UUID(receipt_id)) == receipt_id, 'receipt_id_invalid')
            path += '?receipt_id=' + receipt_id
        response = await runtime.get(path)
        require(response.status_code in allowed and len(response.content) <= 256 * 1024,
                'old_authority_not_denied')
        value = response.json()
        self.require_no_body(value, previous_text)
        return response.status_code

    async def scope_negative(self):
        from sqlalchemy import select, func
        from app.models.agent_task import AgentTask, AgentRun, AgentTaskGrant
        state, auth = self.store.read('state.json'), self.store.read('auth.json')
        require(state['phase'] in ('verified', 'dual_ready_verified'), 'scope_negative_phase_denied')
        require('outside_report_id' in state, 'initial_outside_fixture_missing')
        self.policy(state)
        async with self.clients(state, auth) as (admin, employee):
            self.step = 'outside_normal_source_declaration'
            # Human access/source evidence are deliberately valid; the plugin's
            # frozen report/parent grant remains restricted to the original target.
            await self.declare_source(admin, state, state['cause_node_id'], report_id=state['outside_report_id'])
            before = await business_snapshot(state)
            task_id, cancelled = None, False
            try:
                self.step = 'outside_task_blocked'
                outside_scope = {**state['source_scope'], 'target_report_id': state['outside_report_id']}
                task = await self.request(employee, 'POST', '/api/agent/tasks', 201, {
                    'report_id': state['outside_report_id'], 'installation_id': state['installation_id'],
                    'request_key': secrets.token_hex(24), 'initial_text': START_MESSAGE,
                    'derived_source_scope': outside_scope})
                task_id = task['task_id']
                state['outside_task_id'] = task_id
                self.store.write('state.json', state)
                require(task['status'] == 'blocked_capability', 'outside_task_became_ready')
                self.step = 'outside_platform_no_run_or_body_grant'
                async with session(state, readonly=True) as db:
                    target = await db.get(AgentTask, UUID(task['task_id']))
                    require(target.target_capa_id == UUID(state['outside_report_id']) and target.status == 'blocked_capability',
                            'outside_task_binding_invalid')
                    require(await db.scalar(select(func.count()).select_from(AgentRun).where(
                        AgentRun.task_id == target.task_id)) == 0, 'outside_task_created_run')
                    require(await db.scalar(select(func.count()).select_from(AgentTaskGrant).where(
                        AgentTaskGrant.task_id == target.task_id, AgentTaskGrant.capability_id == BODY)) == 0,
                        'outside_task_created_body_grant')
                self.step = 'outside_anonymous_installation_claim_denied'
                await self.runtime_claim(state, auth, status=404)
                stopped = await self.request(employee, 'POST', '/api/agent/tasks/' + task['task_id'] + '/control', 200,
                    {'action': 'cancel', 'idempotency_key': secrets.token_hex(24)})
                require(stopped['task_status'] == 'cancelled' and stopped['run_id'] is None, 'outside_task_cleanup_failed')
                cancelled = True
            finally:
                if task_id is not None and not cancelled:
                    await self.cancel_owned_tasks(employee, state, [task_id],
                        'outside_cleanup_unconfirmed_task_ids', preserve_failure=sys.exc_info()[0] is not None)
        require(await business_snapshot(state) == before, 'outside_denial_changed_business')
        await self.assert_grants(state, state['task_id'])
        state.update(phase='scope_negative_verified', outside_policy_parent_task_scope_denied=True)
        self.store.write('state.json', state)

    async def source_swap(self):
        from sqlalchemy import select, func
        from app.models.agent_task import AgentTaskGrant, AgentRun
        from app.models.agent_derived_source import AgentPluginDerivedSourceScope
        from app.models.capa_d4_delivery import AgentRestrictedProjectionReceipt
        state, auth = self.store.read('state.json'), self.store.read('auth.json')
        require(state['phase'] in ('verified', 'dual_ready_verified', 'scope_negative_verified'), 'source_swap_phase_denied')
        require('alternate_cause_node_id' in state, 'initial_alternate_source_missing')
        self.policy(state)
        active, old_claim, old_body, fresh_body = [], None, None, None
        def remember(task_id):
            active.append(task_id)
            state.setdefault('source_swap_task_ids', []).append(task_id)
            self.store.write('state.json', state)
        async with self.clients(state, auth) as (admin, employee):
            try:
                self.step = 'source_a_same_authority_positive_control'
                first = await self.create_task(employee, state, secrets.token_hex(24)); remember(first['task_id'])
                require(first.get('status') == 'ready', 'task_not_ready')
                old_claim = await self.runtime_claim(state, auth)
                require(old_claim['task_id'] == first['task_id'], 'source_a_claim_mismatch')
                async with self.run_client(state, old_claim['token']) as runtime:
                    old_body = await self.request(runtime, 'GET', '/api/agent/runtime/capa/d4/root-cause-text', 200)
                    self.require_nonempty_candidate(old_body.get('text'))
                    require(old_body['report_id'] == state['report_id'], 'source_a_body_mismatch')
                    auth['source_a_runtime_token'] = old_claim['token']
                    self.store.write('auth.json', auth)
                    state['old_source_receipt_id'] = old_body['receipt_id']
                    self.store.write('state.json', state)
                    self.step = 'source_b_explicit_declaration'
                    await self.declare_source(admin, state, state['alternate_cause_node_id'])
                    before = await business_snapshot(state)
                    async with session(state, readonly=True) as db:
                        receipts_before = await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt))
                    self.step = 'source_b_old_run_and_receipt_cannot_reauthorize'
                    denied_plain = await self.denied_read(runtime, old_body['text'])
                    denied_receipt = await self.denied_read(runtime, old_body['text'], receipt_id=old_body['receipt_id'])
                    # Receipt UUIDs are observable metadata, never a replacement
                    # runtime credential; this does not invent a receipt replay API.
                    async with self.run_client(state, old_body['receipt_id']) as receipt_client:
                        await self.denied_read(receipt_client, old_body['text'], allowed=(401,))
                    blocked = await self.request(employee, 'POST', '/api/agent/tasks', 201, {
                        'report_id': state['report_id'], 'installation_id': state['installation_id'],
                        'request_key': secrets.token_hex(24), 'initial_text': START_MESSAGE,
                        'derived_source_scope': {**state['source_scope'], 'cause_node_id': state['alternate_cause_node_id']}})
                    remember(blocked['task_id'])
                    require(blocked['status'] == 'blocked_capability', 'source_b_implicitly_regranted')
                    async with session(state, readonly=True) as db:
                        parent = (await db.scalars(select(AgentPluginDerivedSourceScope).where(
                            AgentPluginDerivedSourceScope.plugin_grant_id == UUID(state['parent_grant_id'])))).one()
                        require(parent.cause_node_id == state['cause_node_id'], 'source_parent_scope_widened')
                        require(await db.scalar(select(func.count()).select_from(AgentTaskGrant).where(
                            AgentTaskGrant.task_id == UUID(blocked['task_id']), AgentTaskGrant.capability_id == BODY)) == 0,
                            'source_b_created_body_grant')
                        require(await db.scalar(select(func.count()).select_from(AgentRun).where(
                            AgentRun.task_id == UUID(blocked['task_id']))) == 0, 'source_b_created_run')
                        require(await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == receipts_before,
                                'denied_source_created_receipt')
                    require(await business_snapshot(state) == before, 'source_denial_changed_business')
                # Stop old A before restoration; no old token/receipt is renewed.
                require(await self.cancel_owned_tasks(employee, state, active,
                    'source_swap_cleanup_unconfirmed_task_ids', preserve_failure=False),
                    'source_swap_active_cancel_not_confirmed')
                active.clear()
                self.step = 'restore_a_by_new_normal_declaration'
                restored = await self.declare_source(admin, state, state['cause_node_id'])
                state['verification_id'] = restored['verification_id']
                self.store.write('state.json', state)
                self.step = 'restored_a_new_run_positive_control'
                ready = await self.create_task(employee, state, secrets.token_hex(24)); remember(ready['task_id'])
                require(ready.get('status') == 'ready', 'task_not_ready')
                current_claim = await self.runtime_claim(state, auth)
                require(current_claim['task_id'] == ready['task_id'], 'restored_a_claim_mismatch')
                async with self.run_client(state, current_claim['token']) as runtime:
                    fresh_body = await self.request(runtime, 'GET', '/api/agent/runtime/capa/d4/root-cause-text', 200)
                    self.require_nonempty_candidate(fresh_body.get('text'))
                require(fresh_body['source_proof_digest'] != old_body['source_proof_digest'] and
                        fresh_body['receipt_id'] != old_body['receipt_id'], 'old_source_proof_or_receipt_reused')
                async with self.run_client(state, old_claim['token']) as old_runtime:
                    await self.denied_read(old_runtime, old_body['text'], receipt_id=old_body['receipt_id'], allowed=(401,))
            finally:
                failure_in_flight = sys.exc_info()[0] is not None
                self.step = 'source_swap_restore_and_stop_cleanup'
                cleanup_ok = False
                try:
                    cleanup_ok = await self.cancel_owned_tasks(employee, state, active,
                        'source_swap_cleanup_unconfirmed_task_ids', preserve_failure=True)
                except Exception:
                    # Still run the independent source-restoration action.
                    pass
                finally:
                    # Source restoration is independent of every task cancellation.
                    # Preserve the original failed witness; only fixed failure facts
                    # and exact task IDs enter private state.
                    restore_ok = False
                    try:
                        restored = await self.declare_source(admin, state, state['cause_node_id'])
                        state['verification_id'] = restored['verification_id']
                        restore_ok = True
                    except Exception:
                        pass
                    state['source_swap_restore_unconfirmed'] = not restore_ok
                    try:
                        self.store.write('state.json', state)
                    except Exception:
                        restore_ok = False
                if not failure_in_flight and not (cleanup_ok and restore_ok):
                    raise FixtureFailure('source_swap_cleanup_not_confirmed')
        require(old_body is not None and fresh_body is not None, 'source_swap_witness_incomplete')
        state.update(phase='source_swap_verified', source_b_implicitly_regranted=False,
            source_swap_old_run_status=denied_plain, source_swap_receipt_query_status=denied_receipt,
            old_receipt_is_not_runtime_credential=True, restored_a_new_source_proof=True)
        self.store.write('state.json', state)

    async def credential_epoch(self):
        from sqlalchemy import select
        from types import SimpleNamespace
        from app.models.agent_plugin import AgentPluginInstallation
        from app.models.audit import AuditLog
        from app.services.agent_runtime.deployment_profiles import select_runtime_admission
        from app.core.security import verify_password
        state, auth = self.store.read('state.json'), self.store.read('auth.json')
        require(state['phase'] == 'revocation_verified', 'credential_epoch_phase_denied')
        frozen = self.policy(state)
        witness_generation = self.store.read('witness.json')['generation']
        old_secret = auth['installation_secret']
        self.step = 'credential_epoch_zero_positive_policy_control'
        async with session(state, readonly=True) as db:
            installation = await db.get(AgentPluginInstallation, UUID(state['installation_id']))
            db.info['agent_d4_text_policy'] = frozen
            coords = SimpleNamespace(report_id=UUID(state['report_id']), factory_id=UUID(state['factory_id']),
                                     product_line_code=state['product_line_code'])
            admitted = select_runtime_admission(db, installation, UUID(state['employee_user_id']), coords)
            require(admitted is not None and admitted.binding_sha256 == frozen.entries[0].binding_sha256,
                    'epoch_zero_policy_positive_control_failed')
        # With no ready task, 404 still demonstrates that this unchanged secret
        # passed authentication before rotation; the same key yields 403 after.
        await self.runtime_claim(state, auth, status=404)
        async with self.clients(state, auth) as (admin, _):
            self.step = 'tcp_rotate_installation_secret'
            rotated = await self.request(admin, 'POST', '/api/admin/agent-plugins/' + state['installation_id'] + '/rotate-secret', 200)
            epoch = rotated['plugin']['credential_epoch']
            require(epoch == state['credential_epoch'] + 1 and rotated['plugin']['enabled'] is True,
                    'installation_epoch_not_rotated')
            auth['installation_secret_before_rotation'] = old_secret
            auth['installation_secret'] = rotated['secret']
            self.store.write('auth.json', auth)
            self.step = 'old_installation_secret_authentication_denied'
            denied = await self.runtime_claim(state, auth, status=403, secret=old_secret)
            self.require_no_body(denied, old_secret)
            self.step = 'new_secret_has_no_pending_run_distinct_from_policy_proof'
            await self.runtime_claim(state, auth, status=404)
            self.step = 'canonical_frozen_policy_rejects_new_credential_epoch'
            async with session(state, readonly=True) as db:
                installation = await db.get(AgentPluginInstallation, UUID(state['installation_id']))
                require(installation.credential_epoch == epoch and verify_password(auth['installation_secret'], installation.secret_hash)
                        and not verify_password(old_secret, installation.secret_hash), 'rotated_credentials_not_persisted')
                db.info['agent_d4_text_policy'] = frozen
                coords = SimpleNamespace(report_id=UUID(state['report_id']), factory_id=UUID(state['factory_id']),
                                         product_line_code=state['product_line_code'])
                require(select_runtime_admission(db, installation, UUID(state['employee_user_id']), coords) is None,
                        'frozen_policy_admitted_new_epoch')
                require(await db.scalar(select(AuditLog.log_id).where(AuditLog.action == 'ROTATE_PLUGIN_SECRET',
                        AuditLog.record_id == installation.installation_id)) is not None, 'rotation_audit_missing')
            # An explicitly requested administrator revocation, wholly separate
            # from receiver teardown. It does not update policy or grant anew.
            self.step = 'tcp_explicit_installation_revocation'
            revoked = await self.request(admin, 'POST', '/api/admin/agent-plugins/' + state['installation_id'] +
                '/revoke-local-trial', 200, {'expected_credential_epoch': epoch})
            require(revoked['credential_epoch'] == epoch + 1 and revoked['enabled'] is False, 'installation_not_revoked')
            await self.runtime_claim(state, auth, status=403)
        async with session(state, readonly=True) as db:
            installation = await db.get(AgentPluginInstallation, UUID(state['installation_id']))
            require(not installation.enabled and installation.credential_epoch == epoch + 1, 'revocation_epoch_not_persisted')
            require(await db.scalar(select(AuditLog.log_id).where(AuditLog.action == 'REVOKE_LOCAL_TRIAL',
                    AuditLog.record_id == installation.installation_id)) is not None, 'installation_revocation_audit_missing')
        self.policy(state)
        require(self.store.read('witness.json')['generation'] == witness_generation, 'api_restarted_during_epoch_test')
        state.update(phase='credential_epoch_verified', frozen_policy_epoch=state['credential_epoch'],
            rotation_credential_epoch=epoch, revoked_credential_epoch=epoch + 1,
            old_secret_claim_status=403, new_secret_no_pending_claim_status=404,
            canonical_new_epoch_policy_denied=True, installation_revoked=True)
        self.store.write('state.json', state)


    async def serve(self):
        """Observe the complete app; do not replace routes, deps or lifespan."""
        from sqlalchemy import event
        from app.database import engine
        from app.main import app
        import uvicorn
        self.step = 'full_app_sql_witness'
        context = ContextVar('d4_fixture_request_sql_counts', default=None)
        generation = secrets.token_hex(16)
        witness = {'schema_version': 1, 'kind': 'full_app_request_sql_witness.v1',
                   'generation': generation, 'next_sequence': 0, 'dropped_records': 0, 'records': []}
        self.store.write('witness.json', witness)

        def count_sql(connection, cursor, statement, parameters, execution_context, many):
            counts = context.get()
            if counts is not None:
                counts['statements'] += 1
                lowered = statement.lower()
                if any(marker in lowered for marker in ('d4_root_cause', 'graph_data', 'jsonb_array_elements')):
                    counts['body_source_reads'] += 1

        routes = {
            ('POST', '/api/agent/runtime/claim'): 'claim',
            ('GET', '/api/agent/runtime/capabilities'): 'capabilities',
            ('POST', '/api/agent/runtime/messages/claim'): 'messages_claim',
            ('GET', '/api/agent/runtime/capa/d4/root-cause-text'): 'body',
            ('POST', '/api/agent/runtime/messages/ack'): 'messages_ack',
            ('POST', '/api/agent/runtime/finish'): 'finish'}
        store = self.store

        class Witness:
            async def __call__(self, scope, receive, send):
                if scope['type'] != 'http':
                    return await app(scope, receive, send)
                method = scope.get('method', '')
                path = scope.get('path', '')
                route = routes.get((method, path))
                if method == 'POST' and re.fullmatch(
                        r'/api/agent/tasks/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/control', path):
                    route = 'control'
                if route is None:
                    return await app(scope, receive, send)
                counts = {'statements': 0, 'body_source_reads': 0}
                token = context.set(counts)
                status = None

                async def observe(message):
                    nonlocal status
                    if message['type'] == 'http.response.start':
                        status = message['status']
                    await send(message)

                try:
                    await app(scope, receive, observe)
                finally:
                    context.reset(token)
                    # No await here: single-worker request completions update one
                    # bounded ledger serially. No path/UUID/header/body/SQL/params.
                    witness['next_sequence'] += 1
                    row = dict(sequence=witness['next_sequence'], route=route,
                               method=method if method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS') else 'unknown',
                               status=status, **counts)
                    witness['records'].append(row)
                    if len(witness['records']) > 128:
                        witness['records'].pop(0)
                        witness['dropped_records'] += 1
                    store.write('witness.json', witness)

        event.listen(engine.sync_engine, 'before_cursor_execute', count_sql)
        try:
            config = uvicorn.Config(Witness(), host='127.0.0.1', port=18777, workers=1,
                reload=False, proxy_headers=False, server_header=False, date_header=False,
                access_log=True, log_config=None, http='h11', lifespan='on')
            await uvicorn.Server(config).serve()
        finally:
            event.remove(engine.sync_engine, 'before_cursor_execute', count_sql)


async def execute(action, store):
    # The complete app configuration is imported only after uid/path/private-file
    # guards. Logging suppression precedes all database/application imports.
    from scripts.agent_d4_isolated_api import _install_policy
    _install_policy()
    from app.config import settings
    from dotenv import dotenv_values
    dotenv_path = Path('/app/.env')
    info = dotenv_path.lstat()
    require(stat.S_ISREG(info.st_mode) and not dotenv_path.is_symlink() and info.st_uid == 2002 and
            stat.S_IMODE(info.st_mode) in (0o400, 0o600) and info.st_nlink == 1, 'dotenv_file_invalid')
    explicit = dotenv_values(dotenv_path)
    require(type(explicit.get('DATABASE_URL')) is str and explicit['DATABASE_URL'] == settings.DATABASE_URL,
            'dotenv_database_mismatch')
    validate_database_url(settings.DATABASE_URL, os.environ.get('OPENQMS_ISOLATION_PG_HOST'))
    require(settings.TENANT_MODE == 'dev' and settings.AGENT_TASK_RUNTIME_ENABLED and
            settings.AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED and not settings.E2E_MODE and
            not settings.AGENT_TASK_ATTACHMENTS_ENABLED and settings.AGENT_LOCAL_TRIAL_MODE == 'disabled'
            and settings.GRAPH_REPOSITORY == 'jsonb', 'application_mode_denied')
    require(not settings.LLM_PROVIDER and not settings.LLM_API_KEY and not settings.EMBEDDING_PROVIDER
            and not settings.EMBEDDING_API_KEY, 'provider_configuration_denied')
    from app.database import engine
    import app.models
    from sqlalchemy import text
    try:
        async with engine.connect() as connection:
            require(await connection.scalar(text('SELECT current_database()')) == 'isolation_synthetic', 'database_identity_mismatch')
        fixture = Fixture(store)
        try:
            await getattr(fixture, action.replace('-', '_'))()
        except Exception as error:
            error.fixture_step = fixture.step
            store.write('diagnostic.json', {'schema_version': 1, 'phase': action, 'step': fixture.step,
                'exception_type': type(error).__name__,
                'code': str(error) if type(error) is FixtureFailure else 'fixture_operation_failed'})
            raise
    finally:
        await engine.dispose()


def main(argv=None):
    phase, store = None, None
    try:
        supplied = list(sys.argv[1:] if argv is None else argv)
        require(len(supplied) == 1 and supplied[0] in ACTIONS, 'fixture_action_denied')
        phase = supplied[0]
        require(os.geteuid() == 2002 and os.getcwd() == '/app', 'fixture_execution_denied')
        store = PrivateStore()
        sys.path.insert(0, '/app')
        if phase == 'serve':
            # The reviewed logging policy must bind real observable streams.
            # Silencing these would make a no-leak log test pass vacuously.
            asyncio.run(execute(phase, store))
        else:
            with open(os.devnull, 'w') as sink, redirect_stdout(sink), redirect_stderr(sink):
                asyncio.run(execute(phase, store))
        print('d4_fixture_' + phase.replace('-', '_') + '_ok', flush=True)
        return 0
    except Exception as error:
        if store is not None:
            try:
                store.write('diagnostic.json', {'schema_version': 1, 'phase': phase,
                    'step': getattr(error, 'fixture_step', 'entry_guard'), 'exception_type': type(error).__name__,
                    'code': str(error) if type(error) is FixtureFailure else 'fixture_operation_failed'})
            except Exception:
                pass
        print('d4_fixture_' + (phase.replace('-', '_') if phase in ACTIONS else 'action') + '_failed', flush=True)
        return 1
    finally:
        if store is not None:
            store.close()


if __name__ == '__main__':
    raise SystemExit(main())
