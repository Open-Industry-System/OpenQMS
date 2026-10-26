"""Controlled Task7 runner; opt-in test profile, never ambient/provider passthrough.

Run from this worktree with the authorized Python interpreter. The existing
private runner supplies only its registered owned DB profile; no reset mode is
called. Node/browser children get child_environment(), never backend secrets.
"""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / '.superpowers/sdd/2026-10-23-capa-outcome-review'
PROVIDER_KEYS = frozenset({'LLM_PROVIDER', 'LLM_API_KEY', 'LLM_MODEL', 'LLM_BASE_URL', 'LLM_TIMEOUT'})
SYSTEM_KEYS = frozenset({'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL'})
OWNED_KEYS = frozenset({'OPENQMS_OUTCOME_ROOT', 'OPENQMS_OUTCOME_PYTHON', 'PGHOST', 'PGPORT',
    'PGUSER', 'PGPASSWORD', 'TEST_DB', 'DATABASE_URL', 'TEST_DATABASE_URL', 'SECRET_KEY',
    'PYTEST_SECRET_KEY', 'TENANT_MODE', 'PYTHONDONTWRITEBYTECODE', 'AGENT_TASK_RUNTIME_ENABLED',
    'AGENT_TASK_ATTACHMENTS_ENABLED', 'CAPA_D4_TEXT_PREVIEW_ENABLED'})


def child_environment(source=None):
    source = os.environ if source is None else source
    return {**{key: value for key, value in source.items() if key in SYSTEM_KEYS},
        'NO_PROXY': '*', 'no_proxy': '*'}


def provider_environment(profile):
    """Only an explicit test file; no shell evaluation or dotenv interpolation."""
    from dotenv import dotenv_values
    if not profile.is_file():
        return {}, 'missing_test_profile'
    values = dotenv_values(profile, interpolate=False)
    result = {key: value for key, value in values.items() if key in PROVIDER_KEYS and value is not None}
    if any('$' in value or '\n' in value or '\r' in value for value in result.values()):
        return {}, 'invalid_test_profile'
    timeout = result.get('LLM_TIMEOUT', '30')
    if not timeout.isdecimal() or not 1 <= int(timeout) <= 120:
        return {}, 'invalid_test_profile'
    provider = result.get('LLM_PROVIDER', '').lower()
    if provider not in {'openai', 'deepseek', 'ark', 'anthropic', 'claude', 'local', 'ollama'}:
        return {}, 'invalid_test_profile'
    if provider not in {'local', 'ollama'} and not result.get('LLM_API_KEY'):
        return {}, 'invalid_test_profile'
    if provider in {'local', 'ollama'} and not all(result.get(key) for key in ('LLM_BASE_URL', 'LLM_MODEL')):
        return {}, 'invalid_test_profile'
    return result, 'authorized_test_profile'


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {'api', 'browser', 'live', 'acceptance'}:
        raise SystemExit('Usage: capa_outcome_runner.py api|browser|live|acceptance')
    mode = sys.argv[1]
    spec = importlib.util.spec_from_file_location('private_owned_profile', WORK / 'run-owned.py')
    profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(profile)
    registered, resources = profile.load_env()
    owner = subprocess.check_output(['docker', 'inspect', '--format',
        '{{.Id}} {{index .Config.Labels "openqms.owner"}}', resources['container']], text=True).strip()
    if owner != resources['container_id'] + ' ' + resources['owner_nonce']:
        raise RuntimeError('Owned container identity mismatch')
    env = child_environment()
    env.update({key: value for key, value in registered.items() if key in OWNED_KEYS})
    # Explicit blanks defeat ambient settings, including app Settings .env fallback.
    for key in PROVIDER_KEYS | {'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'EMBEDDING_API_KEY',
            'EMBEDDING_PROVIDER', 'EMBEDDING_BASE_URL', 'EMBEDDING_MODEL'}:
        env[key] = ''
    env.update(PYTHONPATH=str(ROOT / 'backend'), E2E_MODE='false', LLM_TIMEOUT='30',
        OPENQMS_OUTCOME_LIVE_TEST='1' if mode in {'live', 'acceptance'} else '0')
    diagnostic = 'not_requested'
    if mode in {'live', 'acceptance'}:
        provider, diagnostic = provider_environment(ROOT / '.env.e2e')
        env.update(provider)
        # Missing config still exercises the actual production fail-closed path.
    env['OPENQMS_OUTCOME_PROVIDER_CONFIG'] = diagnostic
    targets = {
        'api': ['tests/capa/test_capa_review_concurrency.py', 'tests/capa/test_capa_outcome_api.py',
            'tests/e2e/test_capa_outcome_runner.py'],
        'browser': ['tests/e2e/test_capa_outcome_review_browser.py', '-k', 'not live'],
        'live': ['tests/e2e/test_capa_outcome_review_browser.py', '-k', 'live'],
        'acceptance': ['tests/e2e/test_capa_outcome_review_browser.py'],
    }[mode]
    command = [env['OPENQMS_OUTCOME_PYTHON'], '-m', 'pytest', *targets, '-q', '--tb=short', '-rA']
    stem = 'task7-' + mode + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    log_path, result_path = WORK / (stem + '.log'), WORK / (stem + '-result.json')
    hidden = sorted({env.get(key, '') for key in ('PGPASSWORD', 'DATABASE_URL', 'TEST_DATABASE_URL',
        'LLM_API_KEY', 'LLM_BASE_URL')} - {''}, key=len, reverse=True)

    def redact(value):
        for secret in hidden:
            value = value.replace(secret, '[REDACTED]')
        return value

    started = time.monotonic()
    with os.fdopen(os.open(log_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'w') as log:
        with subprocess.Popen(command, cwd=ROOT / 'backend', env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
            for line in process.stdout:
                log.write(redact(line)); log.flush()
            code = process.wait()
    result = {'mode': mode, 'command': command, 'exit_code': code,
        'provider_config': diagnostic, 'elapsed_seconds': round(time.monotonic() - started, 2),
        'log': str(log_path), 'finished_at': datetime.now(timezone.utc).isoformat()}
    result_path.write_text(json.dumps(result, indent=2) + '\n')
    print('TASK7_EXIT: mode=' + mode + '; code=' + str(code) + '; provider_config=' + diagnostic)
    print(''.join(log_path.read_text().splitlines(keepends=True)[-70:]), end='')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
