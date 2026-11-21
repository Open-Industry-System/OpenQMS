"""Backend routing, independent workers and the stable required check fail closed."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / '.github/workflows/test.yml'
spec = importlib.util.spec_from_file_location('backend_gate', ROOT / 'scripts/ci/backend_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def jobs():
    return yaml.safe_load(WORKFLOW.read_text())['jobs']


def test_matrix_keeps_two_independent_postgres_workers_and_one_required_check():
    workflow = jobs()
    worker = workflow['backend-full']
    assert worker['name'] == 'backend-full (${{ matrix.shard }})'
    assert worker['strategy'] == {'fail-fast': False, 'matrix': {'include': [
        {'shard': 'runtime', 'index': 0}, {'shard': 'remainder', 'index': 1}]}}
    assert worker['needs'] == ['backend-route']
    assert worker['services']['postgres']['ports'] == ['5432/tcp']
    assert 'openqms.ci.job=backend-full' in worker['services']['postgres']['options']
    assert 'openqms.ci.shard=${{ matrix.shard }}' in worker['services']['postgres']['options']
    assert worker['env']['OPENQMS_TEST_ARTIFACTS'].endswith('backend-shard-${{ matrix.shard }}')
    steps = {step['name']: step for step in worker['steps'] if 'name' in step}
    assert 'BACKEND_SHARD=${{ matrix.index }}' in steps['Run deterministic backend acceptance']['run']
    assert steps['Run deterministic backend acceptance']['env']['GITHUB_JOB'] == 'backend-full'
    for name in ('Run manual tests', 'D8 doc-gate preflight (against migrated test DB)',
                 'Run engine import checks', 'Install SDK developer build tools'):
        assert steps[name]['if'] == "matrix.shard == 'remainder'"
    assert steps['Upload actual safe receipts and logs']['with']['name'] == 'backend-shard-${{ matrix.shard }}-evidence'
    required = workflow['backend-tests']
    assert required['needs'] == ['backend-route', 'backend-full'] and required['if'] == 'always()'
    steps = {step['name']: step for step in required['steps'] if 'name' in step}
    assert steps['Require the selected backend result']['run'] == 'python scripts/ci/backend_gate.py'
    assert steps['Download both backend shard receipts']['with']['pattern'] == 'backend-shard-*-evidence'
    assert 'tests.ci.backend_shards' in steps['Verify actual complete and disjoint execution']['run']
    assert steps['Upload combined compatible API receipt']['with']['name'] == 'backend-tests-evidence'
    assert 'pip install' not in str(required)


@pytest.mark.parametrize('reason', sorted(gate.FAST_REASONS))
def test_explicit_successful_shortcut_requires_skipped_workers(reason):
    docs = str(reason == 'allowlisted_markdown_only').lower()
    assert gate.require_backend_result('success', 'false', reason, docs, 'skipped') is False
    for result in ('success', 'failure', 'cancelled', ''):
        with pytest.raises(ValueError):
            gate.require_backend_result('success', 'false', reason, docs, result)


@pytest.mark.parametrize('route', ('failure', 'cancelled', 'skipped', ''))
@pytest.mark.parametrize('required', ('true', 'false', ''))
def test_bad_route_never_passes(route, required):
    with pytest.raises(ValueError):
        gate.require_backend_result(route, required, 'allowlisted_markdown_only', 'true', 'skipped')


@pytest.mark.parametrize('required,reason,docs,result', [
    ('', '', '', ''), ('', 'legacy_policy_full', 'true', 'success'),
    ('false', '', 'true', 'skipped'), ('false', 'unknown', 'true', 'skipped'),
    ('false', 'allowlisted_markdown_only', 'false', 'skipped'),
    ('false', 'presentation_only', 'true', 'skipped'),
    ('true', 'main_push', 'false', 'skipped'), ('true', 'main_push', 'false', 'failure'),
    ('true', 'main_push', 'false', 'cancelled'), ('true', 'main_push', 'false', ''),
])
def test_missing_inconsistent_and_failed_results_never_pass(required, reason, docs, result):
    with pytest.raises(ValueError):
        gate.require_backend_result('success', required, reason, docs, result)


def test_required_success_still_requires_actual_receipt_verification():
    assert gate.require_backend_result('success', 'true', 'main_push', 'false', 'success') is True
    assert gate.require_backend_result('success', 'true', 'legacy_policy_full', 'true', 'success') is True
    step = next(step for step in jobs()['backend-tests']['steps'] if step.get('name') == 'Verify actual complete and disjoint execution')
    assert step['if'] == "needs.backend-route.outputs.backend_required != 'false'"


@pytest.mark.parametrize('event,preview,policy,expected', [
    ('push', False, 'new', ('false', 'true', 'main_push')),
    ('pull_request', True, 'new', ('false', 'true', 'preview_receipts_required')),
    ('pull_request', False, 'missing', ('false', 'true', 'trusted_base_policy_unavailable')),
    ('pull_request', False, 'old', ('true', 'true', 'legacy_policy_full')),
    ('pull_request', False, 'new', ('false', 'false', 'presentation_only')),
])
def test_real_routing_shell_uses_trusted_base_and_old_policy_falls_back_to_full(tmp_path, event, preview, policy, expected):
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.run(['git', *args], cwd=repo, check=True, text=True, capture_output=True).stdout.strip()
    git('init', '-q')
    git('config', 'user.email', 'ci-test@example.invalid')
    git('config', 'user.name', 'CI test')
    (repo / 'README.md').write_text('base\n')
    path = repo / 'scripts/ci/backend_route.py'
    if policy != 'missing':
        path.parent.mkdir(parents=True)
        output = 'docs_only=true\\n' if policy == 'old' else 'docs_only=false\\nbackend_required=false\\nroute_reason=presentation_only\\n'
        path.write_text('import os\nwith open(os.environ["GITHUB_OUTPUT"], "a") as output:\n    output.write(' + repr(output.replace('\\n', '\n')) + ')\n')
    git('add', '.')
    git('commit', '-qm', 'trusted policy')
    sha = git('rev-parse', 'HEAD')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('raise RuntimeError("untrusted PR policy must not run")\n')
    outputs = tmp_path / 'outputs'
    summary = tmp_path / 'summary'
    script = next(step['run'] for step in jobs()['backend-route']['steps'] if step.get('id') == 'route')
    result = subprocess.run(['bash', '-c', script], cwd=repo, text=True, capture_output=True, env={
        'PATH': os.environ['PATH'], 'BASE_SHA': sha, 'GITHUB_EVENT_NAME': event,
        'REQUIRE_PREVIEW_RECEIPTS': str(preview).lower(), 'GITHUB_OUTPUT': str(outputs),
        'GITHUB_STEP_SUMMARY': str(summary), 'RUNNER_TEMP': str(tmp_path),
    })
    assert result.returncode == 0, result.stderr
    fields = dict(line.split('=', 1) for line in outputs.read_text().splitlines())
    assert (fields['docs_only'], fields['backend_required'], fields['route_reason']) == expected


@pytest.mark.parametrize('required,reason,docs,result,exit_code', [
    ('true', 'main_push', 'false', 'success', 0),
    ('false', 'allowlisted_markdown_only', 'true', 'skipped', 0),
    ('true', 'main_push', 'false', 'cancelled', 1),
])
def test_real_gate_cli_uses_workflow_environment(tmp_path, required, reason, docs, result, exit_code):
    summary = tmp_path / 'summary'
    completed = subprocess.run([sys.executable, str(ROOT / 'scripts/ci/backend_gate.py')],
        capture_output=True, text=True, env={'PATH': os.environ['PATH'], 'ROUTE_RESULT': 'success',
            'BACKEND_REQUIRED': required, 'ROUTE_REASON': reason, 'DOCS_ONLY': docs,
            'BACKEND_RESULT': result, 'GITHUB_STEP_SUMMARY': str(summary)})
    assert completed.returncode == exit_code
    assert summary.exists() is (exit_code == 0)
