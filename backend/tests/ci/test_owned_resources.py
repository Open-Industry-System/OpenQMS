from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.ci import owned_resources


VALID_URL = 'postgresql+asyncpg://qms:qms@127.0.0.1:61935/qms_ci_layered_test'


def registration(tmp_path: Path) -> Path:
    path = tmp_path / 'resources.json'
    path.write_text(json.dumps({
        'container': 'owned-pg',
        'container_id': 'a' * 64,
        'owner_nonce': 'owner-nonce',
        'image': 'pgvector/pgvector:pg15',
        'host': '127.0.0.1',
        'port': 61935,
        'test_database': 'qms_ci_layered_test',
        'application_database': 'postgres',
    }))
    path.chmod(0o600)
    return path


def local_source(tmp_path: Path, **overrides: str) -> dict[str, str]:
    source = {
        'OPENQMS_TEST_RESOURCE_FILE': str(registration(tmp_path)),
        'TEST_DATABASE_URL': VALID_URL,
    }
    source.update(overrides)
    return source


def owned_inspection(**overrides: object) -> dict:
    result = {
        'id': 'a' * 64,
        'image': 'pgvector/pgvector:pg15',
        'labels': {'openqms.owner': 'owner-nonce'},
        'ports': {'5432/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '61935'}]},
    }
    result.update(overrides)
    return result


@pytest.mark.parametrize('url', [
    'postgresql+asyncpg://u:p@db.example.test:5432/qms_test',
    'postgresql+asyncpg://u:p@127.0.0.1:5432/qms',
])
def test_rejects_unowned_target_before_container_or_connection_io(url, monkeypatch):
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda *_: pytest.fail('must reject before inspect'))
    monkeypatch.setattr(owned_resources, '_connect', lambda *_: pytest.fail('must reject before connect'))
    with pytest.raises(ValueError):
        owned_resources.verify_owned_instance({'TEST_DATABASE_URL': url})


@pytest.mark.parametrize('query', [
    'host=remote',
    'hostaddr=198.51.100.7',
    'service=external',
    'servicefile=%2Ftmp%2Fservice',
    'port=5432',
    'application_name=unneeded',
])
def test_rejects_all_url_query_parameters_before_container_or_connection_io(tmp_path, monkeypatch, query):
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda *_: pytest.fail('must reject before inspect'))
    monkeypatch.setattr(owned_resources, '_connect', lambda *_: pytest.fail('must reject before connect'))
    source = local_source(tmp_path, TEST_DATABASE_URL=VALID_URL + '?' + query)
    with pytest.raises(ValueError, match='query'):
        owned_resources.verify_owned_instance(source)


@pytest.mark.parametrize('key, value', [
    ('PGHOST', '127.0.0.2'),
    ('PGPORT', '5432'),
    ('PGUSER', 'other'),
    ('PGPASSWORD', 'other'),
    ('TEST_DB', 'other_test'),
    ('PGADMIN_URL', 'postgresql://other:other@127.0.0.1:61935/postgres'),
])
def test_rejects_conflicting_legacy_values_before_inspection(tmp_path, monkeypatch, key, value):
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda *_: pytest.fail('must reject before inspect'))
    with pytest.raises(ValueError, match='legacy database setting conflicts'):
        owned_resources.verify_owned_instance(local_source(tmp_path, **{key: value}))


def test_accepts_url_as_only_connection_source(tmp_path, monkeypatch):
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection())
    target = owned_resources.verify_owned_instance(local_source(tmp_path))
    assert target.container_id == 'a' * 64
    assert target.host == '127.0.0.1'
    assert target.port == 61935
    assert target.username == 'qms'
    assert target.database == 'qms_ci_layered_test'
    assert target.async_url == VALID_URL
    assert target.admin_url.endswith('@127.0.0.1:61935/postgres')
    with pytest.raises(Exception):
        target.port = 5432


def test_accepts_exact_matching_legacy_values(tmp_path, monkeypatch):
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection())
    target = owned_resources.verify_owned_instance(local_source(
        tmp_path, PGHOST='127.0.0.1', PGPORT='61935', PGUSER='qms', PGPASSWORD='qms',
        TEST_DB='qms_ci_layered_test',
        PGADMIN_URL='postgresql+psycopg://qms:qms@127.0.0.1:61935/postgres',
    ))
    assert target.database == 'qms_ci_layered_test'


def test_rejects_spoofed_github_actions_without_ci_identity(monkeypatch):
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda *_: pytest.fail('must not inspect'))
    with pytest.raises(ValueError, match='resource registration is required'):
        owned_resources.verify_owned_instance({'GITHUB_ACTIONS': 'true', 'TEST_DATABASE_URL': VALID_URL})


def test_ci_requires_matching_labels_and_actual_port(monkeypatch):
    source = {
        'TEST_DATABASE_URL': VALID_URL,
        'PG15_CONTAINER': 'ci-pg',
        'GITHUB_RUN_ID': '17',
        'GITHUB_RUN_ATTEMPT': '2',
        'GITHUB_JOB': 'backend',
    }
    inspection = owned_inspection(labels={
        'openqms.ci.run': '17', 'openqms.ci.attempt': '2', 'openqms.ci.job': 'backend',
    })
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: inspection)
    assert owned_resources.verify_owned_instance(source).port == 61935
    inspection['ports']['5432/tcp'][0]['HostPort'] = '5432'
    with pytest.raises(ValueError, match='container port'):
        owned_resources.verify_owned_instance(source)


def test_rejects_incomplete_local_container_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection(id='a' * 12))
    with pytest.raises(ValueError, match='container id'):
        owned_resources.verify_owned_instance(local_source(tmp_path))


def test_rejects_local_owner_label_mismatch_before_database_connection(tmp_path, monkeypatch):
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection(
        labels={'openqms.owner': 'another-owner'},
    ))
    monkeypatch.setattr(owned_resources, '_connect', lambda *_: pytest.fail('must not connect'))
    with pytest.raises(ValueError, match='ownership labels'):
        owned_resources.verify_owned_instance(local_source(tmp_path))


class Cursor:
    def __init__(self, events, values):
        self.events, self.values = events, values

    def execute(self, statement, params=None):
        self.events.append(('sql', str(statement), params))

    def fetchone(self):
        return next(self.values)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Connection:
    def __init__(self, events, values):
        self.events, self.values = events, iter(values)
        self.autocommit = False

    def cursor(self):
        return Cursor(self.events, self.values)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_creates_only_verified_missing_database_then_verifies_target_identity(monkeypatch):
    target = owned_resources.VerifiedTestTarget(
        container_id='a' * 64, host='127.0.0.1', port=61935, username='qms', password='qms',
        database='qms_ci_layered_test', async_url=VALID_URL,
        admin_url='postgresql+psycopg://qms:qms@127.0.0.1:61935/postgres',
    )
    events = []
    connections = iter([
        Connection(events, [('postgres', 'qms'), None]),
        Connection(events, [('qms_ci_layered_test', 'qms')]),
    ])
    monkeypatch.setattr(owned_resources, '_connect', lambda _: next(connections))
    owned_resources.ensure_test_database(target)
    normalized = owned_resources.verify_owned_database(target)
    assert normalized == VALID_URL
    sql = [statement for kind, statement, _ in events if kind == 'sql']
    assert 'current_database()' in sql[0]
    assert 'pg_database' in sql[1]
    assert 'CREATE DATABASE "qms_ci_layered_test"' in sql[2]
    assert 'current_database()' in sql[3]


def test_existing_verified_database_never_emits_create(monkeypatch):
    target = owned_resources.VerifiedTestTarget(
        container_id='a' * 64, host='127.0.0.1', port=61935, username='qms', password='qms',
        database='qms_ci_layered_test', async_url=VALID_URL,
        admin_url='postgresql+psycopg://qms:qms@127.0.0.1:61935/postgres',
    )
    events = []
    monkeypatch.setattr(owned_resources, '_connect', lambda _: Connection(events, [('postgres', 'qms'), (1,)]))

    owned_resources.ensure_test_database(target)

    assert not any('CREATE DATABASE' in sql for kind, sql, _ in events if kind == 'sql')


    target = owned_resources.VerifiedTestTarget(
        container_id='a' * 64, host='127.0.0.1', port=61935, username='qms', password='qms',
        database='qms_ci_layered_test', async_url=VALID_URL,
        admin_url='postgresql+psycopg://qms:qms@127.0.0.1:61935/postgres',
    )
    events = []
    monkeypatch.setattr(owned_resources, '_connect', lambda _: Connection(events, [('postgres', 'other')]))
    with pytest.raises(ValueError, match='admin database identity'):
        owned_resources.ensure_test_database(target)
    assert not any('CREATE DATABASE' in sql for kind, sql, _ in events if kind == 'sql')

    monkeypatch.setattr(owned_resources, '_connect', lambda _: Connection(events, [('wrong', 'qms')]))
    with pytest.raises(ValueError, match='target database identity'):
        owned_resources.verify_owned_database(target)


def test_artifact_directory_is_private_and_unique(tmp_path):
    explicit = tmp_path / 'artifacts'
    assert owned_resources.artifact_directory({'OPENQMS_TEST_ARTIFACTS': str(explicit)}) == explicit
    assert explicit.stat().st_mode & 0o077 == 0
    first = owned_resources.artifact_directory({'RUNNER_TEMP': str(tmp_path)})
    second = owned_resources.artifact_directory({'RUNNER_TEMP': str(tmp_path)})
    assert first != second
    assert first.parent == second.parent == tmp_path


def test_prepare_database_orders_instance_create_target_identity_and_migration(monkeypatch):
    from tests.ci import prepare_database

    target = owned_resources.VerifiedTestTarget(
        container_id='a' * 64, host='127.0.0.1', port=61935, username='qms', password='qms',
        database='qms_ci_layered_test', async_url=VALID_URL,
        admin_url='postgresql+psycopg://qms:qms@127.0.0.1:61935/postgres',
    )
    calls = []
    monkeypatch.setattr(prepare_database, 'verify_owned_instance', lambda source: calls.append('inspect') or target)
    monkeypatch.setattr(prepare_database, 'ensure_test_database', lambda found: calls.append('create'))
    monkeypatch.setattr(prepare_database, 'verify_owned_database', lambda found: calls.append('target identity') or VALID_URL)
    monkeypatch.setattr(prepare_database, 'run_migrations', lambda found, url: calls.append(('migration', found, url)))
    assert prepare_database.prepare_database({'TEST_DATABASE_URL': VALID_URL}) == VALID_URL
    assert calls == ['inspect', 'create', 'target identity', ('migration', target, VALID_URL)]


def test_database_connector_converts_sqlalchemy_driver_url_for_psycopg(monkeypatch):
    captured = []
    monkeypatch.setitem(__import__('sys').modules, 'psycopg', SimpleNamespace(
        connect=lambda url, **kwargs: captured.append((url, kwargs)) or object(),
    ))
    owned_resources._connect('postgresql+psycopg://qms:qms@127.0.0.1:61935/postgres')
    assert captured == [('postgresql://qms:qms@127.0.0.1:61935/postgres', {'hostaddr': '127.0.0.1'})]


def test_database_creation_uses_admin_autocommit(monkeypatch):
    target = owned_resources.VerifiedTestTarget(
        container_id='a' * 64, host='127.0.0.1', port=61935, username='qms', password='qms',
        database='qms_ci_layered_test', async_url=VALID_URL,
        admin_url='postgresql+psycopg://qms:qms@127.0.0.1:61935/postgres',
    )
    events = []
    connection = Connection(events, [('postgres', 'qms'), (1,)])
    monkeypatch.setattr(owned_resources, '_connect', lambda _: connection)
    owned_resources.ensure_test_database(target)
    assert connection.autocommit is True


@pytest.mark.parametrize('field, value', [
    ('test_database', 'another_test'),
    ('application_database', 'qms_ci_layered_test'),
])
def test_rejects_registration_database_mismatch_before_container_inspection(tmp_path, monkeypatch, field, value):
    path = registration(tmp_path)
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda *_: pytest.fail('must reject before inspect'))
    with pytest.raises(ValueError, match='registration database'):
        owned_resources.verify_owned_instance({
            'OPENQMS_TEST_RESOURCE_FILE': str(path), 'TEST_DATABASE_URL': VALID_URL,
        })


def test_rejects_unexpected_ci_or_registered_image(tmp_path, monkeypatch):
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection(image='postgres:15'))
    with pytest.raises(ValueError, match='container image'):
        owned_resources.verify_owned_instance(local_source(tmp_path))


@pytest.mark.parametrize('target_host,binding', [
    ('localhost', '0.0.0.0'),
    ('127.0.0.1', '0.0.0.0'), ('::1', '::'),
    ('localhost', '127.0.0.1'),
    ('127.0.0.1', 'localhost'),
])
def test_ci_accepts_loopback_target_on_compatible_service_binding(monkeypatch, target_host, binding):
    source = {
        'TEST_DATABASE_URL': VALID_URL.replace('127.0.0.1', f'[{target_host}]' if ':' in target_host else target_host),
        'PG15_CONTAINER': 'ci-pg', 'GITHUB_RUN_ID': '17', 'GITHUB_RUN_ATTEMPT': '2', 'GITHUB_JOB': 'backend',
    }
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection(
        labels={'openqms.ci.run': '17', 'openqms.ci.attempt': '2', 'openqms.ci.job': 'backend'},
        ports={'5432/tcp': [{'HostIp': binding, 'HostPort': '61935'}]},
    ))
    assert owned_resources.verify_owned_instance(source).port == 61935


@pytest.mark.parametrize('target_host,binding,port', [
    ('127.0.0.1', '::', '61935'), ('::1', '0.0.0.0', '61935'),
    ('127.0.0.1', '::1', '61935'), ('::1', '127.0.0.1', '61935'),
    ('localhost', '198.51.100.7', '61935'), ('localhost', '0.0.0.0', '5432'),
    ('localhost', '', '61935'),
    ('localhost', '::', '61935'), ('localhost', '::1', '61935'),
    ('::1', 'localhost', '61935'),
])
def test_ci_rejects_incompatible_or_wrong_service_binding(monkeypatch, target_host, binding, port):
    source = {
        'TEST_DATABASE_URL': VALID_URL.replace('127.0.0.1', f'[{target_host}]' if ':' in target_host else target_host),
        'PG15_CONTAINER': 'ci-pg', 'GITHUB_RUN_ID': '17', 'GITHUB_RUN_ATTEMPT': '2', 'GITHUB_JOB': 'backend',
    }
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection(
        labels={'openqms.ci.run': '17', 'openqms.ci.attempt': '2', 'openqms.ci.job': 'backend'},
        ports={'5432/tcp': [{'HostIp': binding, 'HostPort': port}]},
    ))
    with pytest.raises(ValueError, match='container port'):
        owned_resources.verify_owned_instance(source)


@pytest.mark.parametrize('container', ['owned-pg', 'a' * 64])
def test_explicit_local_registration_allows_only_its_pgtool_container(tmp_path, monkeypatch, container):
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection())
    assert owned_resources.verify_owned_instance(local_source(tmp_path, PG15_CONTAINER=container)).container_id == 'a' * 64


@pytest.mark.parametrize('overrides', [
    {'PG15_CONTAINER': 'another-container'},
    {'PG15_CONTAINER': 'a' * 12},
    {'PG15_CONTAINER': 'owned-pg', 'GITHUB_RUN_ID': '17'},
])
def test_local_pgtool_rejects_mismatched_or_mixed_identity_before_inspection(tmp_path, monkeypatch, overrides):
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: pytest.fail('reject before inspect'))
    with pytest.raises(ValueError, match='container|mixed'):
        owned_resources.verify_owned_instance(local_source(tmp_path, **overrides))


def snapshot_environment(tmp_path, monkeypatch):
    source = local_source(tmp_path, PG15_CONTAINER='owned-pg')
    for key in (*owned_resources._CI_KEYS, 'DATABASE_URL', 'PGHOST', 'PGPORT', 'PGUSER', 'PGPASSWORD', 'TEST_DB', 'PGADMIN_URL', 'OPENQMS_MIGRATION_TEST_DATABASE_URL'):
        monkeypatch.delenv(key, raising=False)
    for key, value in source.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection())
    return source


@pytest.mark.parametrize('identity', ['local', 'ci'])
def test_snapshot_dump_uses_verified_full_container_id_and_created_migration_database(tmp_path, monkeypatch, identity):
    from scripts import generate_tenant_snapshot as generator
    snapshot_environment(tmp_path, monkeypatch)
    base_url = VALID_URL
    if identity == 'ci':
        base_url = VALID_URL.replace('127.0.0.1', 'localhost')
        monkeypatch.delenv('OPENQMS_TEST_RESOURCE_FILE')
        for key, value in {
            'TEST_DATABASE_URL': base_url, 'PG15_CONTAINER': 'a' * 64,
            'GITHUB_RUN_ID': '17', 'GITHUB_RUN_ATTEMPT': '2', 'GITHUB_JOB': 'backend',
        }.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection(
            labels={'openqms.ci.run': '17', 'openqms.ci.attempt': '2', 'openqms.ci.job': 'backend'},
            ports={'5432/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '61935'},
                                  {'HostIp': '::', 'HostPort': '61935'}]},
        ))
    migration_url = base_url.replace('qms_ci_layered_test', 'qms_migtest_created_test')
    monkeypatch.setenv('DATABASE_URL', migration_url)
    monkeypatch.setenv('OPENQMS_MIGRATION_TEST_DATABASE_URL', migration_url)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(stdout=b'pg_dump (PostgreSQL) 15.18' if '--version' in command else b'archive')

    monkeypatch.setattr(generator.subprocess, 'run', run)
    assert generator.pg_dump_custom(migration_url, 'public') == b'archive'
    assert all(command[:5] == ['docker', 'exec', '-i', 'a' * 64, 'pg_dump'] for command in commands)
    assert commands[-1][commands[-1].index('-d') + 1] == 'qms_migtest_created_test'
    assert '--schema-only' in commands[-1]
    commands.clear()
    assert generator._run('pg_restore', '--list', input=b'archive') == b'archive'
    assert all(command[:5] == ['docker', 'exec', '-i', 'a' * 64, 'pg_restore'] for command in commands)


@pytest.mark.parametrize('change', ['container', 'owner', 'host', 'port', 'user', 'password', 'database', 'query', 'schema', 'data'])
def test_snapshot_rejects_unverified_dump_before_pgtool_execution(tmp_path, monkeypatch, change):
    from scripts import generate_tenant_snapshot as generator
    snapshot_environment(tmp_path, monkeypatch)
    url, schema, schema_only = VALID_URL, 'public', True
    if change == 'container':
        monkeypatch.setenv('PG15_CONTAINER', 'other-container')
    elif change == 'owner':
        monkeypatch.setattr(owned_resources, 'inspect_container', lambda _: owned_inspection(labels={'openqms.owner': 'other'}))
    elif change == 'host':
        url = url.replace('127.0.0.1', '198.51.100.7')
    elif change == 'port':
        url = url.replace('61935', '5432')
    elif change == 'user':
        url = url.replace('//qms:', '//other:')
    elif change == 'password':
        url = url.replace(':qms@', ':other@')
    elif change == 'database':
        url = url.replace('qms_ci_layered_test', 'unrecorded_test')
    elif change == 'query':
        url += '?host=other'
    elif change == 'schema':
        schema = 'tenant_other'
    elif change == 'data':
        schema_only = False
    monkeypatch.setattr(generator.subprocess, 'run', lambda *a, **k: pytest.fail('must reject before pgtool execution'))
    with pytest.raises(ValueError):
        generator.pg_dump_custom(url, schema, schema_only)


def test_snapshot_restore_also_requires_registered_container(tmp_path, monkeypatch):
    from scripts import generate_tenant_snapshot as generator
    snapshot_environment(tmp_path, monkeypatch)
    monkeypatch.setenv('PG15_CONTAINER', 'other-container')
    monkeypatch.setattr(generator.subprocess, 'run', lambda *a, **k: pytest.fail('must reject before restore'))
    with pytest.raises(ValueError):
        generator.pg_restore_list(b'archive')
