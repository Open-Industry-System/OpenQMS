import dataclasses
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from tests.services.agent_runtime.trial_support import UNIT_ENTRY

NOW = datetime(2030, 1, 1, tzinfo=UTC)
HASH = '3a2dfa9712c2ffebc62c26da0c4c03192be4ec905d1ee83e3ae198bfab51fa21'
ENTRY = {**UNIT_ENTRY, 'plugin_key': 'openqms.local-d4-root-cause-text',
         'worker_sha256': HASH, 'redaction_terms': ['秘密词']}


def write(path, value=None):
    path.write_text(json.dumps({'schema_version': 1, 'entries': [ENTRY if value is None else value]}))
    path.chmod(0o600)
    return path


def load(path, **kw):
    from app.services.agent_runtime.local_d4_text_policy import load_text_policy
    return load_text_policy(path, enabled=True, runtime_enabled=True, tenant_mode='dev',
                            now=NOW, key=b'secret', **kw)


def test_fixed_policy_is_frozen_and_hides_terms(tmp_path):
    policy = load(write(tmp_path / 'p'))
    assert policy.diagnostic == 'TEXT_POLICY_READY'
    assert '秘密词' not in repr(policy)
    assert len(policy.entries) == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.entries[0].credential_epoch = 3
    assert len(policy.entries[0].binding_sha256) == 64


@pytest.mark.parametrize('field,value', [
    ('worker_sha256','f'*64), ('plugin_key','x'), ('tenant_generation', True),
    ('expires_at', '2030-01-01T01:00:01Z'), ('redaction_terms', ['same', 'SAME']),
    ('redaction_terms', 'wrong'), ('redaction_terms', ['\x00']), ('unexpected', True),
])
def test_invalid_text_entry_fails_closed(tmp_path, field, value):
    policy = load(write(tmp_path / 'p', {**ENTRY, field: value}))
    assert not policy.entries and policy.diagnostic == 'TEXT_POLICY_INVALID'
    assert '秘密词' not in repr(policy)


def test_binding_changes_with_terms_and_key_without_leaking(tmp_path):
    first = load(write(tmp_path / 'p')).entries[0]
    second = load(write(tmp_path / 'q', {**ENTRY, 'redaction_terms': ['different']})).entries[0]
    assert first.binding_sha256 != second.binding_sha256
    assert '秘密词' not in repr(first)


def test_text_profile_only_upgrades_own_capability():
    from app.services.agent.permissions.catalog import get_capability
    from app.services.agent.permissions.types import ApprovalFloor
    from app.services.agent_runtime.message_delivery_policy import TEXT_PROFILE
    cap = 'capa.d4.root_cause_candidate.masked.v1'
    assert get_capability(cap).approval_floor == ApprovalFloor.DENY
    assert get_capability(cap, profile=TEXT_PROFILE).approval_floor == ApprovalFloor.DIRECT
    assert get_capability(cap, profile='local_metadata_v1') is None
    assert get_capability('capa.d4.summary.masked.v1', profile=TEXT_PROFILE) is None


def test_server_owned_slot_selection_and_revocation(tmp_path, monkeypatch):
    from app.config import settings
    from app.core.tenant_transaction import TenantBinding
    from app.services.agent_runtime.deployment_profiles import select_runtime_admission
    from app.services.agent_runtime.trial_policy import EMPTY_POLICY
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', True)
    policy = load(write(tmp_path / 'p'))
    binding = TenantBinding(tenant_id=UUID(ENTRY['tenant_id']), schema_name='tenant_one', generation=1, mode='business')
    db = SimpleNamespace(info={'tenant_binding': binding, 'agent_local_trial_policy': EMPTY_POLICY,
                               'agent_d4_text_policy': policy})
    plugin = SimpleNamespace(installation_id=UUID(ENTRY['installation_id']), credential_epoch=0,
                             plugin_key=ENTRY['plugin_key'], plugin_version='1.0.0')
    coords = SimpleNamespace(report_id=UUID(ENTRY['report_id']), factory_id=UUID(ENTRY['factory_id']), product_line_code=ENTRY['product_line_code'])
    admission = select_runtime_admission(db, plugin, UUID(ENTRY['executor_user_id']), coords, now=NOW)
    assert admission.profile == 'local_d4_root_cause_text_v1'
    plugin.credential_epoch = 1
    assert select_runtime_admission(db, plugin, UUID(ENTRY['executor_user_id']), coords, now=NOW) is None

@pytest.mark.parametrize('mode', ['symlink', 'permissions', 'duplicate', 'too_many', 'directory'])
def test_unsafe_policy_files_fail_closed(tmp_path, mode):
    path = tmp_path / 'policy'
    if mode == 'symlink':
        path.symlink_to(write(tmp_path / 'real'))
    elif mode == 'directory':
        path.mkdir()
    elif mode == 'duplicate':
        path.write_text('{"schema_version":1,"schema_version":1,"entries":[]}')
        path.chmod(0o600)
    elif mode == 'too_many':
        path.write_text(json.dumps({'schema_version':1,'entries':[ENTRY, ENTRY]}))
        path.chmod(0o600)
    else:
        write(path)
        path.chmod(0o644)
    assert not load(path).entries


def test_worker_bytes_and_enable_modes_fail_closed(tmp_path, monkeypatch):
    from app.services.agent_runtime import local_d4_text_policy as module
    path = write(tmp_path / 'p')
    assert not module.load_text_policy(path, enabled=False, runtime_enabled=True, tenant_mode='dev', now=NOW, key=b'x').entries
    assert not module.load_text_policy(path, enabled=True, runtime_enabled=False, tenant_mode='dev', now=NOW, key=b'x').entries
    assert not module.load_text_policy(path, enabled=True, runtime_enabled=True, tenant_mode='single', now=NOW, key=b'x').entries
    fake = tmp_path / 'worker'
    fake.write_bytes(b'untrusted')
    monkeypatch.setattr(module, 'TEXT_WORKER_PATH', fake)
    assert not load(path).entries


@pytest.mark.asyncio
async def test_db_uses_only_actual_app_state_snapshot(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from starlette.requests import Request
    from app.config import settings
    from app.database import get_db
    from app.services.agent_runtime.local_d4_text_policy import EMPTY_TEXT_POLICY
    monkeypatch.setattr(settings, 'TENANT_MODE', 'single')
    app = FastAPI()
    request = Request({'type':'http', 'app':app, 'headers':[], 'state':{}})
    async for db in get_db(request):
        assert db.info['agent_d4_text_policy'] is EMPTY_TEXT_POLICY
    policy = load(write(tmp_path / 'policy'))
    app.state.agent_d4_text_policy = policy
    async for db in get_db(request):
        assert db.info['agent_d4_text_policy'] is policy


@pytest.mark.asyncio
async def test_text_flag_drives_peer_gate_without_metadata(monkeypatch):
    from starlette.requests import Request
    from starlette.responses import Response
    from app.config import settings
    from app.core.tenant_context import TenantContextMiddleware
    monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', True)
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(settings, 'AGENT_LOCAL_TRIAL_MODE', 'disabled')
    monkeypatch.setattr(settings, 'TENANT_MODE', 'single')
    req = Request({'type':'http', 'path':'/api/agent/runtime/claim', 'method':'POST',
                   'headers':[], 'client':('192.0.2.1', 99), 'server':('127.0.0.1',80),
                   'scheme':'http', 'query_string':b'', 'state':{}})
    async def next_handler(request):
        return Response(status_code=204)
    response = await TenantContextMiddleware(None).dispatch(req, next_handler)
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_lifespan_loads_text_once_independently(tmp_path, monkeypatch):
    from datetime import timedelta
    from app.config import settings
    from app.main import app, lifespan
    value = {**ENTRY, 'expires_at': (datetime.now(UTC) + timedelta(minutes=20)).isoformat()}
    path = write(tmp_path / 'p', value)
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', True)
    monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE', str(path))
    monkeypatch.setattr(settings, 'AGENT_LOCAL_TRIAL_MODE', 'disabled')
    async with lifespan(app):
        policy = app.state.agent_d4_text_policy
        assert policy.diagnostic == 'TEXT_POLICY_READY'
        path.write_text('{}')
        assert app.state.agent_d4_text_policy is policy and len(policy.entries) == 1
        assert app.state.agent_local_trial_policy.entries == ()


def test_expired_admission_and_wrong_coordinates_fail_closed(tmp_path, monkeypatch):
    from datetime import timedelta
    from app.config import settings
    from app.core.tenant_transaction import TenantBinding
    from app.services.agent_runtime.deployment_profiles import select_runtime_admission
    from app.services.agent_runtime.trial_policy import EMPTY_POLICY
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', True)
    policy = load(write(tmp_path / 'p'))
    binding = TenantBinding(tenant_id=UUID(ENTRY['tenant_id']), schema_name='tenant_one', generation=1, mode='business')
    db = SimpleNamespace(info={'tenant_binding':binding, 'agent_local_trial_policy':EMPTY_POLICY, 'agent_d4_text_policy':policy})
    plugin = SimpleNamespace(installation_id=UUID(ENTRY['installation_id']), credential_epoch=0, plugin_key=ENTRY['plugin_key'], plugin_version='1.0.0')
    coords = SimpleNamespace(report_id=UUID(ENTRY['report_id']), factory_id=UUID(ENTRY['factory_id']), product_line_code=ENTRY['product_line_code'])
    assert select_runtime_admission(db, plugin, UUID(ENTRY['executor_user_id']), coords, now=NOW + timedelta(minutes=21)) is None
    coords.product_line_code = 'OTHER'
    assert select_runtime_admission(db, plugin, UUID(ENTRY['executor_user_id']), coords, now=NOW) is None


def test_runtime_target_selection_uses_text_slot_but_body_task_remains_blocked(tmp_path, monkeypatch):
    from app.config import settings
    from app.core.tenant_transaction import TenantBinding
    from app.services.agent_runtime.task_service import trial_for_target, _read_grants
    from app.services.agent_runtime.trial_policy import EMPTY_POLICY
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', True)
    policy = load(write(tmp_path / 'p'))
    binding = TenantBinding(tenant_id=UUID(ENTRY['tenant_id']), schema_name='tenant_one', generation=1, mode='business')
    db = SimpleNamespace(info={'tenant_binding':binding, 'agent_local_trial_policy':EMPTY_POLICY, 'agent_d4_text_policy':policy})
    plugin = SimpleNamespace(installation_id=UUID(ENTRY['installation_id']), credential_epoch=0, plugin_key=ENTRY['plugin_key'], plugin_version='1.0.0')
    coords = SimpleNamespace(report_id=UUID(ENTRY['report_id']), factory_id=UUID(ENTRY['factory_id']), product_line_code=ENTRY['product_line_code'])
    admission = trial_for_target(db, plugin, UUID(ENTRY['executor_user_id']), coords)
    assert admission is not None and admission.profile == 'local_d4_root_cause_text_v1'
    manifest = SimpleNamespace(required_capabilities=['capa.d4.root_cause_candidate.masked.v1'], optional_capabilities=[])
    grants, ready = _read_grants(UUID(ENTRY['report_id']), coords, manifest, {}, None, None, [], trial=admission)
    assert not ready and grants == []


def test_loaded_text_slot_cannot_be_selected_after_disable(tmp_path, monkeypatch):
    from app.config import settings
    from app.core.tenant_transaction import TenantBinding
    from app.services.agent_runtime.deployment_profiles import select_runtime_admission
    from app.services.agent_runtime.trial_policy import EMPTY_POLICY
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', False)
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    binding = TenantBinding(tenant_id=UUID(ENTRY['tenant_id']), schema_name='tenant_one', generation=1, mode='business')
    db = SimpleNamespace(info={'tenant_binding':binding, 'agent_local_trial_policy':EMPTY_POLICY, 'agent_d4_text_policy':load(write(tmp_path / 'p'))})
    plugin = SimpleNamespace(installation_id=UUID(ENTRY['installation_id']), credential_epoch=0, plugin_key=ENTRY['plugin_key'], plugin_version='1.0.0')
    coords = SimpleNamespace(report_id=UUID(ENTRY['report_id']), factory_id=UUID(ENTRY['factory_id']), product_line_code=ENTRY['product_line_code'])
    assert select_runtime_admission(db, plugin, UUID(ENTRY['executor_user_id']), coords, now=NOW) is None


def test_policy_rejects_symlinked_ancestor(tmp_path):
    real = tmp_path / 'real'
    real.mkdir(mode=0o700)
    child = real / 'child'
    child.mkdir(mode=0o700)
    write(child / 'p')
    alias = tmp_path / 'alias'
    alias.symlink_to(real, target_is_directory=True)
    assert not load(alias / 'child' / 'p').entries


def test_both_slots_never_cross_bind(tmp_path, monkeypatch):
    from app.config import settings
    from app.core.tenant_transaction import TenantBinding
    from app.services.agent_runtime.deployment_profiles import select_runtime_admission
    from app.services.agent_runtime.trial_policy import load_policy
    from tests.services.agent_runtime.trial_support import write_policy
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    monkeypatch.setattr(settings, 'AGENT_TASK_RUNTIME_ENABLED', True)
    monkeypatch.setattr(settings, 'AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED', True)
    metadata = load_policy(write_policy(tmp_path / 'metadata'), mode='local_metadata', tenant_mode='dev', now=NOW)
    text = load(write(tmp_path / 'text'))
    binding = TenantBinding(tenant_id=UUID(ENTRY['tenant_id']), schema_name='tenant_one', generation=1, mode='business')
    db = SimpleNamespace(info={'tenant_binding':binding, 'agent_local_trial_policy':metadata, 'agent_d4_text_policy':text})
    plugin = SimpleNamespace(installation_id=UUID(ENTRY['installation_id']), credential_epoch=0, plugin_key=ENTRY['plugin_key'], plugin_version='1.0.0')
    coords = SimpleNamespace(report_id=UUID(ENTRY['report_id']), factory_id=UUID(ENTRY['factory_id']), product_line_code=ENTRY['product_line_code'])
    identity = UUID(ENTRY['executor_user_id'])
    assert select_runtime_admission(db, plugin, identity, coords, now=NOW).profile == 'local_d4_root_cause_text_v1'
    plugin.plugin_key = UNIT_ENTRY['plugin_key']
    assert select_runtime_admission(db, plugin, identity, coords, now=NOW).profile == 'local_metadata_v1'
    plugin.plugin_key = 'unknown'
    assert select_runtime_admission(db, plugin, identity, coords, now=NOW) is None


def test_binding_is_keyed_and_normalized(tmp_path):
    from app.services.agent_runtime.local_d4_text_policy import load_text_policy
    path = write(tmp_path / 'p')
    policy = load(path)
    changed = load_text_policy(path, enabled=True, runtime_enabled=True, tenant_mode='dev', now=NOW, key=b'another')
    assert policy.entries[0].binding_sha256 != changed.entries[0].binding_sha256
    assert '秘密词' not in repr(policy) and '秘密词' not in repr(changed)


def test_platform_profiles_bind_distinct_context_and_message_deliveries():
    from app.services.agent_runtime.deployment_profiles import PROFILES
    text = PROFILES['local_d4_root_cause_text_v1']
    metadata = PROFILES['local_metadata_v1']
    assert text.deliveries == frozenset({('context', 'restricted', 'masked'), ('message', 'restricted', 'raw')})
    assert metadata.deliveries == frozenset({('context', 'internal', 'masked'), ('message', 'restricted', 'raw')})
    assert text.required == frozenset({'capa.d4.root_cause_candidate.masked.v1'})
    assert metadata.required == frozenset({'capa.d4.summary.masked.v1'})


def test_text_admission_token_is_clipped_and_contains_no_private_terms():
    from datetime import timedelta
    from app.services.agent_runtime import run_auth
    from app.services.agent_runtime.trial_policy import TrialAdmission
    now = datetime.now(UTC)
    installation = SimpleNamespace(installation_id=UUID(ENTRY['installation_id']), credential_epoch=0)
    run = SimpleNamespace(run_id=UUID(ENTRY['report_id']), plugin_version='1.0.0', lease_epoch=1,
                          lease_expires_at=now + timedelta(minutes=3))
    trial = TrialAdmission('local_d4_root_cause_text_v1', 'a' * 64, now + timedelta(seconds=40), installation.installation_id)
    token = run_auth.issue_run_token(run, installation, ENTRY['tenant_id'], 1, trial=trial)
    claims = run_auth._claims(token)
    assert claims['exp'] <= int(trial.expires_at.timestamp())
    assert claims['trial_binding_sha256'] == trial.binding_sha256
    assert '秘密词' not in repr(claims)


@pytest.mark.asyncio
async def test_runtime_rejects_old_text_token_after_policy_binding_changes(monkeypatch):
    from contextlib import nullcontext
    from datetime import timedelta
    from unittest.mock import AsyncMock
    from app.services.agent_runtime import run_auth, runtime_access
    from app.services.agent_runtime.trial_policy import TrialAdmission
    now = datetime.now(UTC)
    installation = SimpleNamespace(installation_id=UUID(ENTRY['installation_id']), credential_epoch=0)
    task = SimpleNamespace()
    run = SimpleNamespace(run_id=UUID(ENTRY['report_id']), task_id=UUID(ENTRY['factory_id']),
                          installation_id=installation.installation_id, plugin_version='1.0.0', lease_epoch=1,
                          lease_expires_at=now + timedelta(minutes=3))
    original = TrialAdmission('local_d4_root_cause_text_v1', 'a' * 64, now + timedelta(minutes=1), installation.installation_id)
    replacement = TrialAdmission(original.profile, 'b' * 64, original.expires_at, original.installation_id)
    token = run_auth.issue_run_token(run, installation, ENTRY['tenant_id'], 1, trial=original)
    monkeypatch.setattr(run_auth, 'verify_run_token', AsyncMock(return_value=run))
    monkeypatch.setattr(runtime_access, 'authorize_task', AsyncMock(return_value=runtime_access.TaskAuthority(None, (), 'line', replacement)))
    db = SimpleNamespace(no_autoflush=nullcontext(), scalar=AsyncMock(side_effect=[task, installation]))
    with pytest.raises(PermissionError, match='Invalid run credential'):
        await runtime_access.verify_runtime_identity(db, token, None)
