"""Validation of disposable, explicitly owned PostgreSQL test targets."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from typing import Mapping

from sqlalchemy.engine import URL, make_url


_LOOPBACK_HOSTS = frozenset({'127.0.0.1', '::1', 'localhost'})
_CI_KEYS = ('PG15_CONTAINER', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB')
_CI_PG15_IMAGE = 'pgvector/pgvector:pg15'


@dataclass(frozen=True)
class VerifiedTestTarget:
    container_id: str
    host: str
    port: int
    username: str
    password: str = field(repr=False)
    database: str
    async_url: str = field(repr=False)
    admin_url: str = field(repr=False)


def inspect_container(container: str) -> dict:
    """Return only the immutable Docker facts used by ownership validation."""
    try:
        completed = subprocess.run(
            ['docker', 'inspect', container], check=True, capture_output=True, text=True,
        )
        payload = json.loads(completed.stdout)
        raw = payload[0]
        return {
            'id': raw['Id'],
            'image': raw['Config']['Image'],
            'labels': raw['Config'].get('Labels') or {},
            'ports': raw['NetworkSettings'].get('Ports') or {},
        }
    except (KeyError, IndexError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        raise ValueError('container inspection failed') from exc


def _validated_url(source: Mapping[str, str]) -> tuple[URL, str]:
    raw_url = source.get('TEST_DATABASE_URL')
    if not raw_url:
        raise ValueError('TEST_DATABASE_URL is required')
    try:
        url = make_url(raw_url)
    except Exception as exc:
        raise ValueError('invalid test database URL') from exc
    if not url.drivername.startswith('postgresql'):
        raise ValueError('test database must use PostgreSQL')
    if url.host not in _LOOPBACK_HOSTS or url.port is None:
        raise ValueError('test database must use a loopback host and explicit port')
    if not url.database or not url.database.endswith('_test'):
        raise ValueError('test database name must end in _test')
    if not url.username or url.password is None:
        raise ValueError('test database URL must contain explicit credentials')
    if url.query:
        raise ValueError('test database URL may not contain query parameters')
    async_url = url.set(drivername='postgresql+asyncpg').render_as_string(hide_password=False)
    return url, async_url


def _reject_libpq_overrides(source: Mapping[str, str]) -> None:
    keys = ('PGHOSTADDR', 'PGSERVICE', 'PGSERVICEFILE', 'PGSYSCONFDIR', 'PGOPTIONS')
    supplied = [key for key in keys if source.get(key)]
    if supplied:
        raise ValueError('unverified libpq settings are not allowed: ' + ', '.join(supplied))


def _validate_legacy_settings(source: Mapping[str, str], url: URL, async_url: str) -> None:
    _reject_libpq_overrides(source)
    _reject_libpq_overrides(os.environ)
    expected = {
        'PGHOST': url.host,
        'PGPORT': str(url.port),
        'PGUSER': url.username,
        'PGPASSWORD': url.password,
        'TEST_DB': url.database,
        'DATABASE_URL': async_url,
    }
    for key, value in expected.items():
        supplied = source.get(key)
        if supplied not in (None, '') and supplied != value:
            raise ValueError('legacy database setting conflicts with TEST_DATABASE_URL')

    admin = source.get('PGADMIN_URL')
    if admin in (None, ''):
        return
    try:
        admin_url = make_url(admin)
    except Exception as exc:
        raise ValueError('legacy database setting conflicts with TEST_DATABASE_URL') from exc
    if (
        not admin_url.drivername.startswith('postgresql')
        or admin_url.host != url.host
        or admin_url.port != url.port
        or admin_url.username != url.username
        or admin_url.password != url.password
        or admin_url.database != 'postgres'
        or admin_url.query
    ):
        raise ValueError('legacy database setting conflicts with TEST_DATABASE_URL')


def _registration(source: Mapping[str, str]) -> tuple[str, dict, bool]:
    container = source.get('PG15_CONTAINER')
    filename = source.get('OPENQMS_TEST_RESOURCE_FILE')
    if filename and any(source.get(key) for key in _CI_KEYS[1:]):
        raise ValueError('mixed local and CI resource identity')
    if container and not filename:
        missing = [key for key in _CI_KEYS if not source.get(key)]
        if missing:
            raise ValueError('incomplete CI resource identity')
        return container, {
            'run': source['GITHUB_RUN_ID'],
            'attempt': source['GITHUB_RUN_ATTEMPT'],
            'job': source['GITHUB_JOB'],
        }, True

    if not filename:
        raise ValueError('resource registration is required')
    path = Path(filename)
    try:
        mode = path.stat().st_mode
        # Ownership means no group/world write access; an owner-writable 0600
        # registration remains valid for the local resource launcher.
        if not stat.S_ISREG(mode) or mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ValueError('resource registration must be an owner-only regular file')
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError('resource registration is invalid') from exc
    required = ('container', 'container_id', 'owner_nonce', 'image', 'host', 'port',
                'test_database', 'application_database')
    if not isinstance(data, dict) or any(not data.get(key) for key in required):
        raise ValueError('resource registration is invalid')
    if container and container not in (data['container'], data['container_id']):
        raise ValueError('PG15_CONTAINER container does not match local registration')
    return str(data['container']), data, False


def canonical_loopback_host(host: str) -> str:
    """Use one numeric address for inspect, both drivers and migration tools."""
    addresses = {'127.0.0.1': '127.0.0.1', 'localhost': '127.0.0.1', '::1': '::1'}
    if host not in addresses:
        raise ValueError('verified loopback database host required')
    return addresses[host]


def _compatible_binding(target_host: str, binding_host: str) -> bool:
    # localhost is IPv4. An IPv6-only published endpoint requires explicit ::1.
    allowed = {
        '127.0.0.1': {'127.0.0.1', 'localhost', '0.0.0.0'},
        '::1': {'::1', '::'},
    }
    return binding_host in allowed[canonical_loopback_host(target_host)]


def _verify_container(container: str, registration: dict, is_ci: bool, url: URL) -> str:
    inspected = inspect_container(container)
    actual_id = inspected.get('id', '')
    if len(actual_id) != 64:
        raise ValueError('container id is not a complete Docker id')
    if not is_ci and actual_id != registration['container_id']:
        raise ValueError('container id does not match registration')
    expected_image = _CI_PG15_IMAGE if is_ci else registration['image']
    if inspected.get('image') != expected_image:
        raise ValueError('container image does not match registration')

    labels = inspected.get('labels', {})
    if is_ci:
        expected = {
            'openqms.ci.run': registration['run'],
            'openqms.ci.attempt': registration['attempt'],
            'openqms.ci.job': registration['job'],
        }
    else:
        expected = {'openqms.owner': registration['owner_nonce']}
    if any(labels.get(key) != value for key, value in expected.items()):
        raise ValueError('container ownership labels do not match')

    if not is_ci and (canonical_loopback_host(str(registration['host'])) != canonical_loopback_host(url.host)
                      or int(registration['port']) != url.port):
        raise ValueError('registration endpoint does not match test database URL')
    mappings = inspected.get('ports', {}).get('5432/tcp') or []
    if not any(_compatible_binding(url.host, entry.get('HostIp')) and entry.get('HostPort') == str(url.port) for entry in mappings):
        raise ValueError('container port does not match test database URL')
    return actual_id


def verify_owned_instance(source: Mapping[str, str]) -> VerifiedTestTarget:
    """Verify URL, explicit legacy consistency, and registered container ownership."""
    url, async_url = _validated_url(source)
    _validate_legacy_settings(source, url, async_url)
    container, registration, is_ci = _registration(source)
    if not is_ci and (
        registration['test_database'] != url.database
        or registration['application_database'] == url.database
    ):
        raise ValueError('registration database does not match test database URL')
    container_id = _verify_container(container, registration, is_ci, url)
    url = url.set(host=canonical_loopback_host(url.host))
    async_url = url.set(drivername='postgresql+asyncpg').render_as_string(hide_password=False)
    admin_url = url.set(drivername='postgresql+psycopg', database='postgres').render_as_string(hide_password=False)
    return VerifiedTestTarget(
        container_id=container_id,
        host=url.host,
        port=url.port,
        username=url.username,
        password=url.password,
        database=url.database,
        async_url=async_url,
        admin_url=admin_url,
    )


def _connect(url: str):
    _reject_libpq_overrides(os.environ)
    parsed = make_url(url).set(drivername='postgresql')
    address = canonical_loopback_host(parsed.host)
    import psycopg

    # URI and libpq hostaddr agree with the numeric endpoint verified above.
    connection_url = parsed.set(host=address).render_as_string(hide_password=False)
    return psycopg.connect(connection_url, hostaddr=address)


def _check_identity(connection, expected_database: str, expected_username: str, description: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database(), current_user')
        actual_database, actual_username = cursor.fetchone()
    if actual_database != expected_database or actual_username != expected_username:
        raise ValueError(f'{description} database identity mismatch')


def _quoted_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def ensure_test_database(target: VerifiedTestTarget) -> None:
    """Create precisely the verified target database after read-only admin checks."""
    with _connect(target.admin_url) as connection:
        connection.autocommit = True
        _check_identity(connection, 'postgres', target.username, 'admin')
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', (target.database,))
            exists = cursor.fetchone() is not None
            if not exists:
                cursor.execute(f'CREATE DATABASE {_quoted_identifier(target.database)}')


def verify_owned_database(target: VerifiedTestTarget) -> str:
    """Verify the created target resolves to the intended database identity."""
    with _connect(target.async_url) as connection:
        _check_identity(connection, target.database, target.username, 'target')
    return target.async_url


def artifact_directory(source: Mapping[str, str]) -> Path:
    """Allocate a private per-run directory without relying on legacy WORK paths."""
    explicit = source.get('OPENQMS_TEST_ARTIFACTS')
    if explicit:
        path = Path(explicit)
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.chmod(0o700)
        return path
    runner_temp = source.get('RUNNER_TEMP')
    if runner_temp:
        return Path(tempfile.mkdtemp(prefix='openqms-ci-', dir=runner_temp))
    return Path(tempfile.mkdtemp(prefix='openqms-ci-'))
