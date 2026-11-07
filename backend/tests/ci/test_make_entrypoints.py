"""Execute Make recipes with a fake Python, never a real database or app."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]


def invoke(tmp_path, target, **settings):
    output = tmp_path / 'calls.jsonl'
    executable = tmp_path / 'probe-python'
    executable.write_text(f'#!{sys.executable}\n' + '''import json, os, sys
with open(os.environ['PROBE_OUTPUT'], 'a') as stream:
    stream.write(json.dumps({'args': sys.argv[1:], 'secret': os.environ.get('SECRET_KEY'),
                             'wheel': os.environ.get('OPENQMS_SDK_WHEEL')}) + '\\n')
''')
    executable.chmod(0o700)
    sdk_output = tmp_path / 'sdk-calls.jsonl'
    sdk_executable = tmp_path / 'probe-sdk-python'
    sdk_executable.write_text(f'#!{sys.executable}\n' + '''import hashlib, json, os, pathlib, sys
with open(os.environ['PROBE_SDK_OUTPUT'], 'a') as stream:
    stream.write(json.dumps({'args': sys.argv[1:], 'secret': os.environ.get('SECRET_KEY')}) + '\\n')
if sys.argv[1] == '-c':
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
assert pathlib.Path(sys.argv[1]) == pathlib.Path(os.environ['PROBE_SDK_BUILDER'])
artifacts = pathlib.Path(sys.argv[sys.argv.index('--artifacts') + 1])
# This is only a fixture payload for Make's path/hash handoff, not a valid wheel.
wheel = artifacts / 'fixture-sdk.whl'
wheel.write_bytes(b'fixture SDK handoff payload')
print(json.dumps({'wheel_path': str(wheel),
                  'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()}))
''')
    sdk_executable.chmod(0o700)
    sdk_artifact_root = tmp_path / 'sdk-artifacts'
    sdk_artifact_root.mkdir(mode=0o700)
    environment = {
        'PATH': os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1',
        'PROBE_OUTPUT': str(output),
        'PROBE_SDK_OUTPUT': str(sdk_output),
        'PROBE_SDK_BUILDER': str(ROOT / 'sdk/python/scripts/build-wheel.py'),
        'DATABASE_URL': 'postgresql+asyncpg://fake:fake@127.0.0.1:1/unused_test',
        **settings,
    }
    result = subprocess.run(
        ['make', '-s', '-f', str(ROOT / 'Makefile'), target, f'PYTHON_BIN={executable}',
         f'SDK_PYTHON_BIN={sdk_executable}', f'SDK_ARTIFACT_ROOT={sdk_artifact_root}'],
        cwd=ROOT, env=environment, capture_output=True, text=True,
    )
    calls = [json.loads(line) for line in output.read_text().splitlines()] if output.exists() else []
    return result, calls


@pytest.mark.parametrize('target', ['check-test-db', 'check-backend', 'check-browser'])
def test_fresh_test_entry_has_secret_before_database_preparation(tmp_path, target):
    result, calls = invoke(tmp_path, target)
    assert result.returncode == 0, result.stderr
    assert calls
    assert calls[0]['args'] == ['-m', 'tests.ci.prepare_database']
    assert all(call['secret'] == 'test-secret-key-for-ci-only' for call in calls)


def test_backend_entry_passes_fixture_wheel_without_sdk_secret(tmp_path):
    result, calls = invoke(tmp_path, 'check-backend')
    assert result.returncode == 0, result.stderr
    sdk_calls = [json.loads(line) for line in (tmp_path / 'sdk-calls.jsonl').read_text().splitlines()]
    assert len(sdk_calls) == 2
    builder_args = sdk_calls[0]['args']
    assert builder_args[0] == str(ROOT / 'sdk/python/scripts/build-wheel.py')
    artifacts = Path(builder_args[builder_args.index('--artifacts') + 1])
    assert artifacts.parent == (tmp_path / 'sdk-artifacts').resolve()
    wheel = artifacts / 'fixture-sdk.whl'
    assert wheel.is_file()
    assert sdk_calls[1]['args'][0] == '-c'
    assert all(call['secret'] is None for call in sdk_calls)
    assert calls[-1]['args'][:2] == ['tests/e2e/capa_outcome_runner.py', 'api']
    assert calls[-1]['wheel'] == str(wheel)


@pytest.mark.parametrize('target', ['doc-gate-preflight', 'deploy-migrate'])
def test_operational_entry_preserves_explicit_secret(tmp_path, target):
    result, calls = invoke(tmp_path, target, SECRET_KEY='explicit-operational-test-value')
    assert result.returncode == 0, result.stderr
    assert len(calls) == 1
    assert calls[0]['secret'] == 'explicit-operational-test-value'


@pytest.mark.parametrize('target', ['doc-gate-preflight', 'deploy-migrate'])
def test_operational_entry_without_secret_fails_before_python(tmp_path, target):
    result, calls = invoke(tmp_path, target)
    assert result.returncode != 0
    assert 'SECRET_KEY' in result.stderr
    assert calls == []


def test_test_preparation_preserves_explicit_secret(tmp_path):
    result, calls = invoke(tmp_path, 'check-test-db', SECRET_KEY='explicit-test-value')
    assert result.returncode == 0, result.stderr
    assert calls[0]['secret'] == 'explicit-test-value'
