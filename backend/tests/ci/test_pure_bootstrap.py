"""Regression checks for supported Python test-process isolation."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[2]
URL = 'postgresql+asyncpg://ci:ci@127.0.0.1:1/ci_isolation_test'


def run_python(code, tmp_path, *, pure=False):
    env = {'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': str(BACKEND),
           'SECRET_KEY': 'synthetic-isolation-test-key', 'TEST_DATABASE_URL': URL,
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}
    if pure:
        env['OPENQMS_CI_PURE'] = '1'
    prefix = ('import socket\n'
              'def forbidden(*a, **kw): raise AssertionError("unexpected_network")\n'
              'socket.socket.connect = socket.socket.connect_ex = forbidden\n'
              'socket.create_connection = socket.getaddrinfo = forbidden\n')
    return subprocess.run([sys.executable, '-c', prefix + code], cwd=tmp_path,
                          env=env, capture_output=True, text=True)


def test_clean_default_pure_entrypoint_has_deterministic_plugins_and_asyncio(tmp_path):
    import json

    sample = tmp_path / 'test_async_sample.py'
    sample.write_text(
        'import os, pytest\n'
        '@pytest.mark.asyncio\n'
        'async def test_async_sample():\n'
        '    assert os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"\n'
        '    assert os.environ["PYTEST_PLUGINS"] == "pytest_asyncio.plugin"\n')
    hooks = tmp_path / 'hooks.json'
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'LANG') if key in os.environ}
    env.update(PYTHONDONTWRITEBYTECODE='1', OPENQMS_GATE_HOOKS=str(hooks))
    result = subprocess.run(
        [sys.executable, str(BACKEND.parent / 'scripts' / 'check-ci-pure.py'),
         str(sample), '-q', '-p', 'no:cacheprovider', '-p', 'tests.ci.gate_results'],
        cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(hooks.read_text())
    assert summary['passed'] == summary['selected'] == 1
    assert summary['warnings'] == summary['skipped'] == 0


@pytest.mark.parametrize('event', [
    'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.getnameinfo', 'socket.bind',
])
@pytest.mark.parametrize('pure', [False, True])
def test_dns_and_bind_audit_events_guarded_only_in_pure_lane(tmp_path, pure, event):
    result = run_python(
        'import asyncio, sys\n'
        'from tests.ci.python_isolation import bootstrap\n'
        'bootstrap()\n'
        'loop = asyncio.new_event_loop()\n'
        'loop.close()\n'
        'try:\n'
        f'    sys.audit({event!r}, "synthetic-no-network")\n'
        'except RuntimeError as exc:\n'
        f'    assert {pure!r} and str(exc) == "pure_test_network_forbidden"\n'
        'else:\n'
        f'    assert not {pure!r}, "audit event escaped pure guard"\n', tmp_path, pure=pure)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('pure', [False, True])
def test_libpq_entrypoints_guarded_only_in_pure_lane(tmp_path, pure):
    result = run_python(
        'import asyncio, psycopg\n'
        'def stub(*args, **kwargs): return "ordinary-db-stub"\n'
        'async def async_stub(*args, **kwargs): return "ordinary-db-stub"\n'
        'psycopg.connect = stub\n'
        'psycopg.Connection.connect = classmethod(stub)\n'
        'psycopg.AsyncConnection.connect = classmethod(async_stub)\n'
        'from tests.ci.python_isolation import bootstrap\n'
        'bootstrap()\n'
        'def check(call):\n'
        '    try:\n'
        '        value = call()\n'
        '    except RuntimeError as exc:\n'
        f'        assert {pure!r} and "pure_test_database_forbidden" in str(exc)\n'
        '    else:\n'
        f'        assert not {pure!r} and value == "ordinary-db-stub"\n'
        'check(lambda: psycopg.connect("synthetic-not-a-url"))\n'
        'check(lambda: psycopg.Connection.connect("synthetic-not-a-url"))\n'
        'check(lambda: asyncio.run(psycopg.AsyncConnection.connect("synthetic-not-a-url")))\n',
        tmp_path, pure=pure)
    assert result.returncode == 0, result.stdout + result.stderr


def test_implicit_dotenv_never_opened_and_explicit_file_preserved(tmp_path):
    fake = tmp_path / '.env'
    fake.write_text('E2E_MODE=true\nLLM_PROVIDER=private-marker\nLLM_API_KEY=private-marker\n')
    explicit = tmp_path / 'explicit.env'
    explicit.write_text('E2E_MODE=true\nLLM_PROVIDER=explicit-marker\n')
    result = run_python(
        'from tests.ci.python_isolation import disable_implicit_dotenv\n'
        'disable_implicit_dotenv()\n'
        'import sys\n'
        f'fake = {str(fake)!r}\n'
        'def audit(event, args):\n'
        '    if event == "open" and str(args[0]) == fake: raise AssertionError("dotenv_read")\n'
        'sys.addaudithook(audit)\n'
        'from app.config import Settings\n'
        'settings = Settings()\n'
        'assert settings.E2E_MODE is False\n'
        'assert not settings.LLM_PROVIDER and not settings.LLM_API_KEY\n'
        f'explicit = Settings(_env_file={str(explicit)!r})\n'
        'assert explicit.E2E_MODE is True and explicit.LLM_PROVIDER == "explicit-marker"\n', tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert fake.read_text().startswith('E2E_MODE=true')


@pytest.mark.parametrize('pure', [False, True])
def test_migration_child_disables_dotenv_and_only_pure_installs_guard(tmp_path, pure):
    (tmp_path / '.env').write_text('E2E_MODE=true\nLLM_PROVIDER=private-marker\n')
    (tmp_path / 'alembic.py').write_text(
        'import os, sys\n'
        f'os.chdir({str(tmp_path)!r})\n'
        'def audit(event, args):\n'
        '    if event == "open" and str(args[0]).endswith(".env"):\n'
        '        raise AssertionError("implicit_dotenv_read")\n'
        'sys.addaudithook(audit)\n'
        'from app.config import Settings\n'
        'assert Settings().E2E_MODE is False\n'
        'assert not Settings().LLM_PROVIDER\n'
        'try:\n'
        '    sys.audit("socket.connect", object(), ("stub.invalid", 1))\n'
        'except RuntimeError as exc:\n'
        '    assert os.environ.get("OPENQMS_CI_PURE") == "1"\n'
        '    assert str(exc) == "pure_test_network_forbidden"\n'
        'else:\n'
        '    assert os.environ.get("OPENQMS_CI_PURE") != "1"\n')
    result = run_python(
        'import os\n'
        f'os.environ["PYTHONPATH"] = {str(tmp_path)!r} + os.pathsep + os.environ["PYTHONPATH"]\n'
        'from tests.ci.prepare_database import run_migrations\n'
        f'run_migrations(None, {URL!r})\n', tmp_path, pure=pure)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('pure', [False, True])
def test_known_pytest_child_inherits_pure_guard(tmp_path, pure):
    (tmp_path / '.env').write_text('E2E_MODE=true\nLLM_PROVIDER=private-marker\n')
    sample = tmp_path / 'test_child.py'
    sample.write_text(
        'import os, sys\n'
        f'os.chdir({str(tmp_path)!r})\n'
        'def audit(event, args):\n'
        '    if event == "open" and str(args[0]).endswith(".env"):\n'
        '        raise AssertionError("implicit_dotenv_read")\n'
        'sys.addaudithook(audit)\n'
        'from app.config import Settings\n'
        'def test_guard():\n'
        '    assert Settings().E2E_MODE is False\n'
        '    assert not Settings().LLM_PROVIDER and not Settings().LLM_API_KEY\n'
        '    for event in ("socket.connect", "socket.gethostbyname", "socket.gethostbyaddr",\n'
        '                  "socket.getnameinfo", "socket.bind"):\n'
        '        try:\n'
        '            sys.audit(event, "synthetic-no-network")\n'
        '        except RuntimeError as exc:\n'
        f'            assert {pure!r} and str(exc) == "pure_test_network_forbidden"\n'
        '        else:\n'
        f'            assert not {pure!r}, "pytest child escaped pure guard: " + event\n')
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    result = run_python(
        'import os\n'
        'from pathlib import Path\n'
        'from tests.e2e.capa_outcome_runner import run_pytest_layer\n'
        f'receipt = run_pytest_layer(layer="api", targets=[{str(sample)!r}], '
        f'source=dict(os.environ), database_url={URL!r}, artifacts=Path({str(artifacts)!r}))\n'
        'assert receipt["status"] == "PASSED"\n', tmp_path, pure=pure)
    assert result.returncode == 0, result.stdout + result.stderr


def test_pure_collection_zero_db_probes_and_db_fixture_errors_not_skip(tmp_path):
    result = run_python(
        'from tests.ci.python_isolation import bootstrap\n'
        'bootstrap()\n'
        'import asyncio\n'
        'from tests import conftest\n'
        'probes = []\n'
        'async def probe():\n'
        '    probes.append(1)\n'
        '    return False\n'
        'conftest._check_db_available = probe\n'
        'conftest.pytest_collection_modifyitems(None, [])\n'
        'assert probes == [], "pure collection probed database"\n'
        'async def misuse():\n'
        '    try:\n'
        '        await anext(conftest.db.__wrapped__())\n'
        '    except RuntimeError as exc:\n'
        '        assert "pure_test_database_forbidden" in str(exc)\n'
        '    else:\n'
        '        raise AssertionError("DB fixture did not error")\n'
        'asyncio.run(misuse())\n'
        'assert probes == []\n', tmp_path, pure=True)
    assert result.returncode == 0, result.stdout + result.stderr
