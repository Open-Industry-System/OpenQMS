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
    stream.write(json.dumps({'args': sys.argv[1:], 'secret': os.environ.get('SECRET_KEY')}) + '\\n')
''')
    executable.chmod(0o700)
    environment = {
        'PATH': os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1',
        'PROBE_OUTPUT': str(output),
        'DATABASE_URL': 'postgresql+asyncpg://fake:fake@127.0.0.1:1/unused_test',
        **settings,
    }
    result = subprocess.run(
        ['make', '-s', '-f', str(ROOT / 'Makefile'), target, f'PYTHON_BIN={executable}'],
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
