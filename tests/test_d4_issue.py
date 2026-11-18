import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


SPEC = importlib.util.spec_from_file_location(
    'd4_issue', Path(__file__).resolve().parents[1] / 'deploy/d4-acceptance/issue.py',
)
issue = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(issue)
REPORT = '11111111-1111-4111-8111-111111111111'
FMEA = '22222222-2222-4222-8222-222222222222'
FACTORY = '33333333-3333-4333-8333-333333333333'
TENANT = '44444444-4444-4444-8444-444444444444'
INSTALLATION = '55555555-5555-4555-8555-555555555555'
USER = '66666666-6666-4666-8666-666666666666'
GRANT = '77777777-7777-4777-8777-777777777777'
TASK = '88888888-8888-4888-8888-888888888888'


@pytest.fixture
def config():
    binding = dict(pr=45, head='a' * 40, merge='b' * 40, plan='c' * 64, lease='d' * 32,
                   report_id=REPORT, issued_at=1000, expires_at=1600)
    return dict(binding=binding, db_host='postgres', db_system_identifier='7212520996867', api_port=8000)


@pytest.fixture
def env():
    return dict(TENANT_MODE='dev', AGENT_TASK_RUNTIME_ENABLED='true',
                AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED='true',
                AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE=str(issue.POLICY),
                DATABASE_URL='postgresql+asyncpg://issuer:instance-password@postgres/qms_d4_acceptance')


def test_requires_dedicated_database_and_live_lease(config, env):
    issue.input_config(config, env, 2002, 2002, 1500)
    with pytest.raises(ValueError, match='dedicated test'):
        issue.input_config(config, dict(env, DATABASE_URL=env['DATABASE_URL'].replace(
            'qms_d4_acceptance', 'qms_preview')), 2002, 2002, 1500)
    with pytest.raises(ValueError, match='dedicated test'):
        issue.input_config(config, env, 0, 0, 1500)
    with pytest.raises(ValueError, match='issuance window'):
        issue.input_config(config, env, 2002, 2002, 1600)


def test_real_application_routes_and_private_issuance_record(config, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'app.services.agent_runtime.local_d4_text_policy',
                        SimpleNamespace(TEXT_WORKER_SHA256='a' * 64))
    monkeypatch.setitem(sys.modules, 'app.services.agent_runtime.message_delivery_policy',
                        SimpleNamespace(START_MESSAGE='fixed D4 start message'))
    private_seed = {
        'tenant_id': TENANT, 'schema': 'tenant_d4_' + 'd' * 32, 'generation': 0,
        'admin_username': 'synthetic-admin', 'report_id': REPORT, 'fmea_id': FMEA,
        'factory_id': FACTORY, 'product_line_code': 'LINE', 'executor_user_id': USER,
    }
    passwords = []

    async def seed(binding, slug, admin, viewer):
        assert binding == config['binding'] and slug == 'd4-' + 'd' * 32
        assert admin != viewer and len(admin) >= 40 and len(viewer) >= 40
        passwords.extend((admin, viewer))
        return private_seed.copy()

    calls = []

    def request(port, slug, method, path, payload, expected, token=None):
        assert port == 8000 and slug == 'd4-' + 'd' * 32
        calls.append((method, path, expected))
        if path == 'auth/login':
            assert payload['password'] == passwords[payload['username'] == 'd4-executor']
            return {'access_token': f'owned-fixture-{payload["username"]}-token'}
        if path == 'admin/agent-plugins':
            assert payload['manifest']['required_capabilities'] == [issue.CAPABILITY]
            return {'plugin': {'installation_id': INSTALLATION}, 'secret': 'z' * 32}
        if path.endswith('root-cause-verifications'):
            assert payload['source_ref'] == {'fmea_id': FMEA, 'cause_node_id': 'cause-A'}
            return {'source_proof_issued': True}
        if path.endswith('/grants'):
            assert payload['factory_ids'] == [FACTORY] and payload['object_ids'] == [REPORT]
            assert payload['derived_source_scope']['fmea_id'] == FMEA
            return {'grant_id': GRANT}
        if path.endswith(INSTALLATION):
            assert payload == {'enabled': True}
            return {'enabled': True}
        assert path == 'agent/tasks' and token.endswith('d4-executor-token')
        assert payload['initial_text'] == 'fixed D4 start message'
        assert payload['report_id'] == REPORT and payload['installation_id'] == INSTALLATION
        return {'task_id': TASK, 'status': 'ready'}

    monkeypatch.setattr(issue, 'synthetic_tenant', seed)
    monkeypatch.setattr(issue, 'request', request)
    directory = os.open(tmp_path, os.O_DIRECTORY)
    try:
        metadata = asyncio.run(issue.prepare(config, directory))
        assert set(metadata) == {'tenant_id', 'schema', 'generation', 'report_id', 'installation_id',
                                 'executor_user_id'}
        for name in ('policy.json', 'receiver.json', 'private-state.json'):
            assert tmp_path.joinpath(name).stat().st_mode & 0o777 == 0o600
        receiver = json.loads(tmp_path.joinpath('receiver.json').read_text())
        assert receiver['secret'] == 'z' * 32 and receiver['expected_report_id'] == REPORT
        with pytest.raises(ValueError, match='changed'):
            issue.create_task(dict(config, api_port=8001), directory)
        issued = issue.create_task(config, directory)
        assert issued == dict(metadata, grant_id=GRANT, task_id=TASK)
        assert all(value not in json.dumps(issued) for value in (*passwords, receiver['secret']))
        assert calls == [
            ('POST', 'auth/login', 200), ('POST', 'admin/agent-plugins', 201),
            ('POST', 'auth/login', 200), ('POST', 'auth/login', 200),
            ('POST', f'capa/{REPORT}/root-cause-verifications', 200),
            ('POST', f'admin/agent-plugins/{INSTALLATION}/grants', 201),
            ('PATCH', f'admin/agent-plugins/{INSTALLATION}', 200), ('POST', 'agent/tasks', 201),
        ]
        with pytest.raises(FileExistsError):
            issue.create_task(config, directory)
    finally:
        os.close(directory)


def test_private_state_refuses_symlink(tmp_path):
    target = tmp_path / 'existing'
    target.write_text('{}')
    target.chmod(0o600)
    (tmp_path / 'private-state.json').symlink_to(target)
    directory = os.open(tmp_path, os.O_DIRECTORY)
    try:
        with pytest.raises(OSError):
            issue.read_private(directory, 'private-state.json')
        with pytest.raises(FileExistsError):
            issue.write_private(directory, 'private-state.json', {})
    finally:
        os.close(directory)


def test_witness_grant_is_limited_to_the_issued_schema_and_metadata_columns():
    slug = 'd4-' + 'd' * 32
    schema = 'tenant_' + slug.replace('-', '_')
    grants = issue.witness_grants(schema, slug)
    assert grants[0] == f'GRANT USAGE ON SCHEMA "{schema}" TO openqms_d4_witness'
    assert grants[1] == 'GRANT SELECT (id,schema_name,generation,status) ON public.tenants TO openqms_d4_witness'
    assert len(grants) == 11
    assert all(f'ON "{schema}".' in grant and 'SELECT (' in grant for grant in grants[2:])
    assert all('password' not in grant and 'secret' not in grant and 'GRANT ALL' not in grant for grant in grants)
    with pytest.raises(ValueError, match='witness schema'):
        issue.witness_grants('tenant_d4_other', slug)
