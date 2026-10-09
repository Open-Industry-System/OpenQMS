import dataclasses
import json
import os
from datetime import UTC, datetime

import pytest

from tests.services.agent_runtime.trial_support import UNIT_ENTRY, write_policy

NOW = datetime(2030, 1, 1, tzinfo=UTC)


def load(path, **overrides):
    from app.services.agent_runtime.trial_policy import load_policy
    return load_policy(path, **{'mode': 'local_metadata', 'tenant_mode': 'dev', 'now': NOW, **overrides})


def test_strict_policy_loads_immutable_normalized_snapshot(tmp_path):
    path = write_policy(tmp_path / 'policy.json')
    result = load(path)
    assert result.diagnostic == 'TRIAL_READY'
    assert len(result.entries) == 1
    entry = result.entries[0]
    assert str(entry.report_id) == UNIT_ENTRY['report_id']
    assert entry.expires_at == datetime(2030, 1, 1, 0, 20, tzinfo=UTC)
    assert len(entry.binding_sha256) == 64
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.credential_epoch = 2
    path.write_text('{"schema_version":1,"entries":[]}')
    assert len(result.entries) == 1
    assert load(path).entries == ()


@pytest.mark.parametrize('mode,tenant,present,diagnostic', [
    ('disabled', 'dev', True, 'TRIAL_DISABLED'), ('local_metadata', 'dev', False, 'TRIAL_DISABLED'),
    ('local_metadata', 'single', True, 'TRIAL_MODE_DENIED'),
    ('local_metadata', 'production', True, 'TRIAL_MODE_DENIED'),
    ('unknown', 'dev', True, 'TRIAL_POLICY_INVALID'),
])
def test_only_explicit_dev_policy_is_admitted(tmp_path, mode, tenant, present, diagnostic):
    path = write_policy(tmp_path / 'policy.json') if present else None
    result = load(path, mode=mode, tenant_mode=tenant)
    assert result.entries == ()
    assert result.diagnostic == diagnostic


@pytest.mark.parametrize('field,value', [
    ('tenant_generation', True), ('tenant_generation', -1), ('tenant_generation', 2147483648),
    ('credential_epoch', True), ('credential_epoch', -1), ('credential_epoch', 2147483647),
    ('tenant_generation', '1'), ('credential_epoch', 1.0), ('tenant_id', '1'),
    ('installation_id', None), ('executor_user_id', '*'), ('factory_id', []),
    ('report_id', UNIT_ENTRY['report_id'].replace('-', '')),
    ('plugin_key', 'other'), ('plugin_version', '1.0.1'), ('product_line_code', ''),
    ('product_line_code', 'x' * 51), ('product_line_code', 12), ('product_line_code', '*'),
    ('product_line_code', 'LINE?'),
    ('expires_at', '2030-01-01T00:20:00'), ('expires_at', '2029-12-31T23:59:00Z'),
    ('expires_at', '2030-01-02T00:00:01Z'), ('expires_at', NOW.isoformat()),
    ('expires_at', 1893457200), ('worker_sha256', 'f' * 64),
    ('worker_sha256', UNIT_ENTRY['worker_sha256'].upper()), ('unexpected', 'sensitive'),
])
def test_invalid_declaration_fails_closed(tmp_path, field, value):
    result = load(write_policy(tmp_path / 'policy.json', {**UNIT_ENTRY, field: value}))
    assert result.entries == ()
    assert result.diagnostic == 'TRIAL_POLICY_INVALID'


@pytest.mark.parametrize('payload', [
    '{"schema_version":1,"schema_version":1,"entries":[]}',
    '{"schema_version":true,"entries":[]}', '{"schema_version":2,"entries":[]}',
    '{"schema_version":1,"entries":[],"extra":1}', '{"schema_version":1}',
    '{"schema_version":1,"entries":null}', '[]', '{',
])
def test_envelope_and_duplicate_keys_are_strict(tmp_path, payload):
    path = tmp_path / 'policy.json'
    path.write_text(payload)
    path.chmod(0o600)
    assert load(path).diagnostic == 'TRIAL_POLICY_INVALID'


@pytest.mark.parametrize('damage', ['duplicate', 'too-many', 'inconsistent-install'])
def test_duplicate_or_inconsistent_entries_denied(tmp_path, damage):
    entries = [dict(UNIT_ENTRY), dict(UNIT_ENTRY)]
    if damage == 'too-many':
        entries *= 11
    if damage == 'inconsistent-install':
        entries[1]['report_id'] = '00000000-0000-0000-0000-000000000099'
        entries[1]['credential_epoch'] = 1
    path = tmp_path / 'policy.json'
    path.write_text(json.dumps({'schema_version': 1, 'entries': entries}))
    path.chmod(0o600)
    assert load(path).diagnostic == 'TRIAL_POLICY_INVALID'


@pytest.mark.parametrize('damage', ['missing', 'symlink', 'directory', 'fifo', 'readable', 'oversize'])
def test_unsafe_files_fail_closed_without_blocking(tmp_path, damage):
    path = tmp_path / 'policy.json'
    if damage == 'directory':
        path.mkdir()
    elif damage == 'fifo':
        os.mkfifo(path, 0o600)
    elif damage == 'symlink':
        path.symlink_to(write_policy(tmp_path / 'real.json'))
    elif damage != 'missing':
        write_policy(path)
        if damage == 'readable':
            path.chmod(0o644)
        else:
            path.write_bytes(b' ' * (128 * 1024 + 1))
    assert load(path).diagnostic == 'TRIAL_POLICY_INVALID'


def test_wrong_owner_and_worker_bytes_denied(tmp_path, monkeypatch):
    from app.services.agent_runtime import trial_policy
    path = write_policy(tmp_path / 'policy.json')
    monkeypatch.setattr(os, 'getuid', lambda: path.stat().st_uid + 1)
    assert load(path).diagnostic == 'TRIAL_POLICY_INVALID'
    monkeypatch.undo()
    worker = tmp_path / 'worker.py'
    worker.write_text('print("untrusted")')
    monkeypatch.setattr(trial_policy, 'WORKER_PATH', worker)
    assert load(path).diagnostic == 'TRIAL_POLICY_INVALID'


def test_equivalent_timezone_normalizes_binding_but_epoch_changes_it(tmp_path):
    first = load(write_policy(tmp_path / 'first.json')).entries[0]
    second = load(write_policy(tmp_path / 'second.json', {**UNIT_ENTRY,
        'expires_at': '2030-01-01T01:20:00+01:00'})).entries[0]
    changed = load(write_policy(tmp_path / 'third.json', {**UNIT_ENTRY, 'credential_epoch': 1})).entries[0]
    assert first.binding_sha256 == second.binding_sha256
    assert first.binding_sha256 != changed.binding_sha256


@pytest.mark.asyncio
async def test_request_session_gets_only_startup_snapshot(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from starlette.requests import Request
    from app.config import settings
    from app.database import get_db
    from app.services.agent_runtime.trial_policy import EMPTY_POLICY
    monkeypatch.setattr(settings, 'TENANT_MODE', 'single')
    app = FastAPI()
    request = Request({'type': 'http', 'app': app, 'headers': [], 'state': {}})
    async for db in get_db(request):
        assert db.info.get('agent_local_trial_policy') is EMPTY_POLICY
    snapshot = load(write_policy(tmp_path / 'policy.json'))
    app.state.agent_local_trial_policy = snapshot
    async for db in get_db(request):
        assert db.info.get('agent_local_trial_policy') is snapshot


@pytest.mark.asyncio
async def test_actual_lifespan_loads_once_and_does_not_reload_file(tmp_path, monkeypatch):
    from datetime import timedelta
    from app.config import settings
    from app.main import app, lifespan
    path = write_policy(tmp_path / 'policy.json', {**UNIT_ENTRY,
        'expires_at': (datetime.now(UTC) + timedelta(minutes=20)).isoformat()})
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    monkeypatch.setattr(settings, 'AGENT_LOCAL_TRIAL_MODE', 'local_metadata')
    monkeypatch.setattr(settings, 'AGENT_LOCAL_TRIAL_POLICY_PATH', str(path))
    async with lifespan(app):
        snapshot = app.state.agent_local_trial_policy
        assert snapshot.diagnostic == 'TRIAL_READY'
        assert len(snapshot.entries) == 1
        path.write_text('{"schema_version":1,"entries":[]}')
        assert app.state.agent_local_trial_policy is snapshot
        assert len(snapshot.entries) == 1
