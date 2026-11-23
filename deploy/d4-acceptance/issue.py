#!/usr/bin/env python3
"""Issue a synthetic D4 fixture inside an isolated candidate API container."""
import argparse
import asyncio
from datetime import UTC, datetime
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID, uuid4


PRIVATE = Path('/run/openqms-d4-issue')
POLICY = PRIVATE / 'policy.json'
DB_SOCKET = '/run/openqms-d4-db'
CAPABILITY = 'capa.d4.root_cause_candidate.masked.v1'
PLUGIN = 'openqms.local-d4-root-cause-text'
SOURCE_NODE = 'cause-A'
SYNTHETIC_CAUSE = 'Synthetic candidate for D4 acceptance'
MAX_RESPONSE = 256 * 1024
WITNESS_COLUMNS = {
    'agent_tasks': 'task_id,status,executor_user_id,preferred_installation_id,target_capa_id',
    'agent_plugin_installations': 'installation_id,plugin_key',
    'agent_plugin_grants': 'enabled,expires_at,grant_id,installation_id,capability_id',
    'agent_plugin_derived_source_scopes': 'plugin_grant_id,target_report_id',
    'agent_task_grants': 'grant_id,task_id,capability_id',
    'agent_d4_task_parent_grants': 'task_grant_id,plugin_grant_id',
    'agent_runs': 'task_id,run_id,installation_id,status,lease_epoch,accepted_message_seq,lease_expires_at',
    'agent_restricted_projection_receipts': (
        'task_id,receipt_id,run_id,source_capa_id,tenant_generation,projection_id,'
        'projection_digest,data_class,lease_epoch'
    ),
    'audit_logs': 'record_id,correlation_id,operated_by,table_name,action,changed_fields',
}



def checked_uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError('invalid fixture identifier')
    return value


def input_config(config, env, uid, gid, now):
    if not isinstance(config, dict) or set(config) != {'binding', 'db_host', 'db_system_identifier', 'api_port'}:
        raise ValueError('invalid D4 issuer request')
    binding = config['binding']
    if not isinstance(binding, dict) or set(binding) != {
            'pr', 'head', 'merge', 'plan', 'lease', 'report_id', 'issued_at', 'expires_at'}:
        raise ValueError('invalid D4 lease binding')
    for key, size in (('head', 40), ('merge', 40), ('plan', 64), ('lease', 32)):
        value = binding[key]
        if not isinstance(value, str) or not re.fullmatch(f'[0-9a-f]{{{size}}}', value):
            raise ValueError('invalid D4 lease identity')
    checked_uuid(binding['report_id'])
    if (type(binding['pr']) is not int or not 0 < binding['pr'] < 10**9
            or type(binding['issued_at']) is not int or type(binding['expires_at']) is not int
            or not binding['issued_at'] <= now < binding['expires_at']
            or not 0 < binding['expires_at'] - binding['issued_at'] <= 3600):
        raise ValueError('invalid D4 issuance window')
    host, cluster, port = (config[key] for key in ('db_host', 'db_system_identifier', 'api_port'))
    if (not isinstance(host, str) or (host != DB_SOCKET and not re.fullmatch(r'[a-z][a-z0-9-]{0,62}', host))
            or not isinstance(cluster, str) or not re.fullmatch(r'[1-9][0-9]{0,19}', cluster)
            or type(port) is not int or not 1024 <= port <= 65535):
        raise ValueError('invalid isolated D4 target')
    url = urlsplit(env.get('DATABASE_URL', ''))
    if host == DB_SOCKET:
        # SQLAlchemy takes the asyncpg Unix socket directory from the host query field.
        matches_database_endpoint = (
            url.hostname is None and url.port is None
            and parse_qsl(url.query, keep_blank_values=True) == [('host', DB_SOCKET)]
        )
    else:
        matches_database_endpoint = url.hostname == host and not url.query
    if (uid != 2002 or gid != 2002 or env.get('TENANT_MODE') != 'dev'
            or env.get('AGENT_TASK_RUNTIME_ENABLED') != 'true'
            or env.get('AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED') != 'true'
            or env.get('AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE') != str(POLICY)
            or url.scheme != 'postgresql+asyncpg' or not matches_database_endpoint
            or url.path != '/qms_d4_acceptance' or url.fragment):
        raise ValueError('D4 fixture issuer requires the dedicated test API and database')


def private_dir():
    fd = os.open(PRIVATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise ValueError('invalid private issuance directory')
    return fd


def write_private(directory, filename, payload):
    flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_CREAT | os.O_EXCL
    with os.fdopen(os.open(filename, flags, 0o600, dir_fd=directory), 'w') as stream:
        json.dump(payload, stream, separators=(',', ':'))
        stream.flush()
        os.fsync(stream.fileno())


def read_private(directory, filename):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(filename, flags, dir_fd=directory), 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError('invalid private issue state')
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise ValueError('oversize issue state')
    return json.loads(raw)


def request(port, slug, method, path, payload, expected, token=None):
    # The fixed numeric loopback destination cannot follow redirects or honor proxy variables.
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=8)
    headers = {'X-Tenant-ID': slug, 'Content-Type': 'application/json', 'Accept': 'application/json'}
    if token is not None:
        headers['Authorization'] = 'Bearer ' + token
    try:
        connection.request(method, '/api/' + path, json.dumps(payload).encode(), headers)
        response = connection.getresponse()
        if response.status != expected:
            raise ValueError('D4 application issuance step rejected')
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError('oversize D4 issuance response')
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('invalid D4 issuance response')
        return result
    finally:
        connection.close()


def login(port, slug, username, password):
    result = request(port, slug, 'POST', 'auth/login',
                     {'username': username, 'password': password}, 200)
    token = result['access_token']
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9._-]{20,4096}', token):
        raise ValueError('invalid D4 fixture login token')
    return token


async def database_identity(config):
    from app.database import engine
    from sqlalchemy import text

    async with engine.connect() as connection:
        identity = (await connection.execute(text(
            'SELECT current_database(), system_identifier::text FROM pg_control_system()'
        ))).one()
    if tuple(identity) != ('qms_d4_acceptance', config['db_system_identifier']):
        raise ValueError('D4 fixture SQL database identity mismatch')


def witness_grants(schema, slug):
    if not re.fullmatch(r'd4-[0-9a-f]{32}', slug) or schema != 'tenant_' + slug.replace('-', '_'):
        raise ValueError('invalid D4 witness schema')
    namespace = '"' + schema + '"'
    recipient = ' TO openqms_d4_witness'
    return [
        'GRANT USAGE ON SCHEMA ' + namespace + recipient,
        'GRANT SELECT (id,schema_name,generation,status) ON public.tenants' + recipient,
        *(f'GRANT SELECT ({columns}) ON {namespace}.{table}' + recipient
          for table, columns in WITNESS_COLUMNS.items()),
    ]


async def synthetic_tenant(binding, slug, admin_password, user_password):
    from app.core.security import hash_password
    from app.core.tenant_transaction import TenantBinding
    from app.database import tenant_async_session
    from app.models.capa import CAPAEightD
    from app.models.factory import UserFactory
    from app.models.fmea import FMEADocument
    from app.models.product_line import ProductLine
    from app.models.role import RoleDefinition, UserProductLine
    from app.models.user import User
    from app.schemas.platform import TenantCreateRequest
    from app.services.tenant_migrator import provision_new
    from sqlalchemy import select, text

    tenant = await provision_new(TenantCreateRequest(
        name='Synthetic D4 acceptance', slug=slug, admin_email='d4-admin@example.test',
        admin_password=admin_password,
    ))
    scope = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, 'business')
    async with tenant_async_session(binding=scope) as db:
        admin = (await db.scalars(select(User).where(User.email == 'd4-admin@example.test'))).one()
        line = await db.scalar(select(ProductLine).order_by(ProductLine.code).limit(1))
        role = (await db.scalars(select(RoleDefinition).where(RoleDefinition.role_key == 'viewer'))).one()
        user = User(username='d4-executor', display_name='Synthetic D4 executor',
                    password_hash=hash_password(user_password), role_id=role.id, legacy_role='viewer',
                    factory_id=line.factory_id, is_active=True)
        fmea = FMEADocument(document_no='D4-SYNTHETIC-SOURCE', title='Synthetic FMEA',
                            factory_id=line.factory_id, product_line_code=line.code,
                            graph_data={'nodes': [{'id': SOURCE_NODE, 'type': 'FailureCause'}], 'edges': []})
        db.add_all((user, fmea))
        await db.flush()
        report = CAPAEightD(report_id=UUID(binding['report_id']), document_no='8D-D4-ACCEPTANCE',
                            title='Synthetic D4 acceptance report', status='D4_ROOT_CAUSE',
                            d2_description='Synthetic description', d4_root_cause=SYNTHETIC_CAUSE,
                            factory_id=line.factory_id, product_line_code=line.code,
                            created_by=admin.user_id, fmea_ref_id=fmea.fmea_id)
        db.add_all((report, UserFactory(user_id=user.user_id, factory_id=line.factory_id),
                    UserProductLine(user_id=user.user_id, product_line_code=line.code)))
        ids = {'tenant_id': str(tenant.id), 'schema': tenant.schema_name, 'generation': tenant.generation,
               'admin_username': admin.username, 'report_id': binding['report_id'], 'fmea_id': str(fmea.fmea_id),
               'factory_id': str(line.factory_id), 'product_line_code': line.code,
               'executor_user_id': str(user.user_id)}
        for statement in witness_grants(tenant.schema_name, slug):
            await db.execute(text(statement))
        await db.commit()
    return ids


def safe_metadata(state):
    return {key: state[key] for key in ('tenant_id', 'schema', 'generation', 'report_id',
                                      'installation_id', 'executor_user_id')}


async def prepare(config, directory):
    from app.services.agent_runtime.local_d4_text_policy import TEXT_WORKER_SHA256

    # An interrupted allocation is cleaned by the host, then issued in a fresh lease.
    write_private(directory, 'started.json', {'binding': config['binding']})
    binding = config['binding']
    slug = 'd4-' + binding['lease']
    admin_password, user_password = (secrets.token_urlsafe(36) for _ in range(2))
    state = await synthetic_tenant(binding, slug, admin_password, user_password)
    port = config['api_port']
    token = login(port, slug, state['admin_username'], admin_password)
    registration = request(port, slug, 'POST', 'admin/agent-plugins', {
        'plugin_key': PLUGIN, 'plugin_version': '1.0.0',
        'manifest': {'protocol_versions': ['1'], 'required_capabilities': [CAPABILITY],
                     'optional_capabilities': [], 'supports_resume': False},
    }, 201, token)
    installation = checked_uuid(registration['plugin']['installation_id'])
    secret = registration['secret']
    if not isinstance(secret, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,256}', secret):
        raise ValueError('invalid D4 installation credential')
    state.update(config=config, slug=slug, installation_id=installation,
                 admin_password=admin_password, user_password=user_password)
    expiry = datetime.fromtimestamp(binding['expires_at'], UTC).isoformat()
    entry = {key: state[key] for key in (
        'tenant_id', 'installation_id', 'executor_user_id', 'report_id', 'factory_id', 'product_line_code',
    )}
    entry.update(tenant_generation=state['generation'], credential_epoch=0, plugin_key=PLUGIN,
                 plugin_version='1.0.0', expires_at=expiry, worker_sha256=TEXT_WORKER_SHA256,
                 redaction_terms=[])
    write_private(directory, 'policy.json', {'schema_version': 1, 'entries': [entry]})
    write_private(directory, 'receiver.json', {
        'origin': f'http://127.0.0.1:{port}', 'tenant_slug': slug,
        'installation_id': installation, 'secret': secret, 'request_key': uuid4().hex,
        'expected_report_id': binding['report_id'],
    })
    write_private(directory, 'private-state.json', state)
    return safe_metadata(state)


def create_task(config, directory):
    from app.services.agent_runtime.message_delivery_policy import START_MESSAGE

    state = read_private(directory, 'private-state.json')
    if state['config'] != config or state['report_id'] != config['binding']['report_id']:
        raise ValueError('D4 fixture changed between preparation and task issuance')
    write_private(directory, 'task-started.json', {'binding': config['binding']})
    port, slug = config['api_port'], state['slug']
    token = login(port, slug, state['admin_username'], state['admin_password'])
    user = login(port, slug, 'd4-executor', state['user_password'])
    report_id = checked_uuid(state['report_id'])
    fmea_id = checked_uuid(state['fmea_id'])
    installation = checked_uuid(state['installation_id'])
    plugin_path = 'admin/agent-plugins/' + installation
    proof = request(port, slug, 'POST', f'capa/{report_id}/root-cause-verifications', {
        'root_cause_text': SYNTHETIC_CAUSE, 'method': 'measurement', 'conclusion': 'passed',
        'source_ref': {'fmea_id': fmea_id, 'cause_node_id': SOURCE_NODE},
        'source_declaration': {'declares_complete_coverage': True},
    }, 200, token)
    if proof.get('source_proof_issued') is not True:
        raise ValueError('D4 synthetic source proof unavailable')
    source_scope = {'target_report_id': report_id, 'fmea_id': fmea_id, 'cause_node_id': SOURCE_NODE}
    grant = request(port, slug, 'POST', plugin_path + '/grants', {
        'capability_id': CAPABILITY, 'object_ids': [report_id],
        'factory_ids': [checked_uuid(state['factory_id'])], 'product_line_codes': [state['product_line_code']],
        'expires_at': datetime.fromtimestamp(config['binding']['expires_at'], UTC).isoformat(),
        'enabled': True, 'derived_source_scope': source_scope,
    }, 201, token)
    grant_id = checked_uuid(grant['grant_id'])
    enabled = request(port, slug, 'PATCH', plugin_path, {'enabled': True}, 200, token)
    if enabled.get('enabled') is not True:
        raise ValueError('D4 synthetic installation remains disabled')
    task = request(port, slug, 'POST', 'agent/tasks', {
        'report_id': report_id, 'installation_id': installation, 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': source_scope,
    }, 201, user)
    if task.get('status') != 'ready':
        raise ValueError('D4 synthetic task is not claimable')
    return dict(safe_metadata(state), grant_id=grant_id, task_id=checked_uuid(task['task_id']))


async def issue(stage, config):
    input_config(config, os.environ, os.getuid(), os.getgid(), int(time.time()))
    directory = private_dir()
    try:
        await database_identity(config)
        return await prepare(config, directory) if stage == 'prepare' else create_task(config, directory)
    finally:
        os.close(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'task'])
    args = parser.parse_args()
    os.umask(0o077)
    try:
        raw = sys.stdin.buffer.read(8193)
        if len(raw) > 8192:
            raise ValueError('oversize issuer request')
        result = asyncio.run(issue(args.stage, json.loads(raw)))
    except Exception:
        print('D4_ISSUANCE_BLOCKED', file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
