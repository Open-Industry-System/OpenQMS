"""No-backend-dependency tests for the documentation routing and final check."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/ci/backend_route.py'


def load_route():
    spec = importlib.util.spec_from_file_location('backend_route', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('raw, expected', [
    (b'M\0docs/superpowers/specs/r6.md\0A\0docs/superpowers/plans/r6.md\0M\0PROGRESS.md\0', True),
    (b'M\0PROGRESS.md\0M\0backend/app/main.py\0', False),
    (b'D\0backend/app/main.py\0', False),
    (b'R100\0backend/app/main.py\0docs/superpowers/specs/code.md\0', False),
    (b'M\0.github/workflows/test.yml\0', False),
    (b'M\0scripts/ci/backend_route.py\0', False),
    (b'M\0tests/ci/test_backend_fast_path.py\0', False),
    (b'M\0docs/e2e.md\0', False),
    (b'M\0README.md\0M\0README_EN.md\0', True),
    (b'M\0README_EN.md\0M\0backend/app/main.py\0', False),
    (b'M\0backend/README.md\0', False),
    (b'M\0docs/superpowers/specs/nested/a.md\0', False),
    (b'D\0docs/superpowers/plans/old.md\0', True),
    (b'R087\0docs/superpowers/specs/old.md\0docs/superpowers/plans/new.md\0', True),
    (b'', False),
])
def test_complete_change_classification(raw, expected):
    assert load_route().classify_diff(raw)['docs_only'] is expected


@pytest.mark.parametrize('raw', [b'M\0PROGRESS.md', b'R100\0PROGRESS.md\0', b'X\0PROGRESS.md\0', b'M\0\0'])
def test_incomplete_diff_is_an_error(raw):
    with pytest.raises(ValueError):
        load_route().classify_diff(raw)


@pytest.mark.parametrize('route_result, docs_only, worker, expected', [
    ('success', 'true', 'skipped', True),
    ('success', 'false', 'success', True),
    ('failure', 'false', 'success', False),
    ('cancelled', 'false', 'success', False),
    ('success', 'false', 'failure', False),
    ('success', 'false', 'cancelled', False),
    ('success', 'false', 'skipped', False),
    ('success', '', 'success', False),
    ('success', 'true', 'success', False),
])
def test_final_backend_check(route_result, docs_only, worker, expected):
    final = workflow()['backend-tests']
    script = final['steps'][-1]['run']
    import tempfile
    with tempfile.NamedTemporaryFile() as summary:
        result = subprocess.run(['bash', '-c', script], env={
            **os.environ, 'ROUTE_RESULT': route_result, 'DOCS_ONLY': docs_only,
            'BACKEND_RESULT': worker, 'GITHUB_STEP_SUMMARY': summary.name,
        }, capture_output=True, text=True)
    assert (result.returncode == 0) is expected


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args]).decode().strip()


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.email', 'ci-test@example.invalid')
    git(tmp_path, 'config', 'user.name', 'CI test')
    (tmp_path / 'PROGRESS.md').write_text('base')
    git(tmp_path, 'add', '.')
    git(tmp_path, 'commit', '-qm', 'base')
    return tmp_path


def event(base, head):
    return {'pull_request': {'base': {'ref': 'main', 'sha': base}, 'head': {'sha': head}}}


def test_all_commits_and_real_rename_are_included(repository):
    base = git(repository, 'rev-parse', 'HEAD')
    code = repository / 'source.py'
    code.write_text('print(1)')
    git(repository, 'add', '.')
    git(repository, 'commit', '-qm', 'code')
    (repository / 'PROGRESS.md').write_text('updated')
    git(repository, 'commit', '-qam', 'docs')
    head = git(repository, 'rev-parse', 'HEAD')
    assert not load_route().classify_pr(repository, 'pull_request', event(base, head))['docs_only']
    base = head
    dest = repository / 'docs/superpowers/specs/code.md'
    dest.parent.mkdir(parents=True)
    git(repository, 'mv', 'source.py', str(dest))
    git(repository, 'commit', '-qm', 'rename')
    head = git(repository, 'rev-parse', 'HEAD')
    result = load_route().classify_pr(repository, 'pull_request', event(base, head))
    assert result['paths'] == ['source.py', 'docs/superpowers/specs/code.md']
    assert not result['docs_only']


def test_read_failure_routes_full_and_fails_classification(repository, tmp_path):
    payload = tmp_path / 'event.json'
    payload.write_text(json.dumps(event('a' * 40, 'b' * 40)))
    output, summary = tmp_path / 'output', tmp_path / 'summary'
    result = subprocess.run([sys.executable, str(SCRIPT), 'classify'], cwd=repository, env={
        **os.environ, 'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_EVENT_PATH': str(payload),
        'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(summary),
    }, capture_output=True, text=True)
    assert result.returncode == 1
    assert 'docs_only=false' in output.read_text()
    assert 'classification_error' in summary.read_text()


def test_main_push_and_other_base_never_shortcut(repository):
    route = load_route()
    assert not route.classify_pr(repository, 'push', {})['docs_only']
    assert not route.classify_pr(repository, 'pull_request', {'pull_request': {'base': {'ref': 'develop'}}})['docs_only']


def workflow():
    return yaml.safe_load((ROOT / '.github/workflows/test.yml').read_text())['jobs']


def test_docs_route_does_not_start_backend_services():
    jobs = workflow()
    assert 'services' not in jobs['backend-route']
    assert 'services' not in jobs['backend-tests']
    worker = jobs['backend-full']
    assert worker['needs'] == ['backend-route']
    assert worker['if'] == "${{ always() && !cancelled() && needs.backend-route.outputs.docs_only != 'true' }}"
    assert 'postgres' in worker['services']
    final = jobs['backend-tests']
    assert final['if'] == 'always()'
    assert final['needs'] == ['backend-route', 'backend-full']
    assert final.get('name', 'backend-tests') == 'backend-tests'


def test_classifier_is_loaded_from_trusted_base_not_merge_candidate():
    job = workflow()['backend-route']
    checkout = next(s for s in job['steps'] if s.get('uses', '').startswith('actions/checkout@'))
    assert checkout['with']['fetch-depth'] == 0
    assert 'ref' not in checkout['with']
    script = job['steps'][-1]['run']
    assert 'git show "$BASE_SHA:scripts/ci/backend_route.py"' in script
    assert 'python "$RUNNER_TEMP/backend-route.py" classify' in script
    assert 'python scripts/ci/backend_route.py classify' not in script


@pytest.mark.parametrize('scenario, docs_only, classification_ok', [
    ('r6', True, True), ('readmes', True, True), ('preview-enabled', False, True), ('mixed', False, True), ('delete-code', False, True),
    ('rename-code', False, True), ('ci-self', False, True), ('read-failure', False, False),
])
def test_real_workflow_scenarios(repository, tmp_path, scenario, docs_only, classification_ok):
    """Run the exact routing and final shell steps against real Git histories."""
    policy = repository / 'scripts/ci/backend_route.py'
    policy.parent.mkdir(parents=True)
    policy.write_text(SCRIPT.read_text())
    (repository / 'source.py').write_text('print(1)')
    git(repository, 'add', '.')
    git(repository, 'commit', '-qm', 'trusted base policy')
    base = git(repository, 'rev-parse', 'HEAD')
    if scenario in {'readmes', 'preview-enabled'}:
        for name in ('README.md', 'README_EN.md'):
            (repository / name).write_text('Project overview')
    else:
        for area in ('specs', 'plans'):
            path = repository / f'docs/superpowers/{area}/r6.md'
            path.parent.mkdir(parents=True)
            path.write_text('R6 explanatory markdown')
        (repository / 'PROGRESS.md').write_text('R6 progress')
    if scenario == 'mixed':
        (repository / 'source.py').write_text('print(2)')
    elif scenario == 'delete-code':
        git(repository, 'rm', 'source.py')
    elif scenario == 'rename-code':
        git(repository, 'mv', 'source.py', 'docs/superpowers/specs/code.md')
    elif scenario == 'ci-self':
        # A PR cannot widen its own allowlist using the candidate version.
        policy.write_text('raise SystemExit("candidate policy must not execute")')
    git(repository, 'add', '.')
    git(repository, 'commit', '-qm', scenario)
    head = git(repository, 'rev-parse', 'HEAD') if scenario != 'read-failure' else 'b' * 40
    payload = tmp_path / 'payload.json'
    payload.write_text(json.dumps(event(base, head)))
    output, summary = tmp_path / 'route-output', tmp_path / 'route-summary'
    jobs = workflow()
    route = jobs['backend-route']['steps'][-1]['run']
    result = subprocess.run(['bash', '-c', route], cwd=repository, env={
        **os.environ, 'BASE_SHA': base, 'GITHUB_EVENT_NAME': 'pull_request',
        'GITHUB_EVENT_PATH': str(payload), 'GITHUB_OUTPUT': str(output),
        'GITHUB_STEP_SUMMARY': str(summary), 'RUNNER_TEMP': str(tmp_path),
        'REQUIRE_PREVIEW_RECEIPTS': 'true' if scenario == 'preview-enabled' else 'false',
    }, capture_output=True, text=True)
    assert (result.returncode == 0) is classification_ok
    assert output.read_text() == f'docs_only={str(docs_only).lower()}\n'
    # Contract test above binds the Actions job-level predicate exactly. Services
    # are allocated only when that predicate admits the worker.
    started = [] if docs_only else ['backend-full']
    assert started == ([] if scenario in {'r6', 'readmes'} else ['backend-full'])
    final = subprocess.run(['bash', '-c', jobs['backend-tests']['steps'][-1]['run']], env={
        **os.environ, 'ROUTE_RESULT': 'success' if classification_ok else 'failure',
        'DOCS_ONLY': str(docs_only).lower(), 'BACKEND_RESULT': 'skipped' if docs_only else 'success',
        'GITHUB_STEP_SUMMARY': str(summary),
    }, capture_output=True, text=True)
    assert (final.returncode == 0) is classification_ok


def test_symlink_markdown_is_not_explanatory_document(repository):
    base = git(repository, 'rev-parse', 'HEAD')
    link = repository / 'docs/superpowers/specs/link.md'
    link.parent.mkdir(parents=True)
    link.symlink_to('../../../source.py')
    git(repository, 'add', '.')
    git(repository, 'commit', '-qm', 'symlink')
    head = git(repository, 'rev-parse', 'HEAD')
    assert not load_route().classify_pr(repository, 'pull_request', event(base, head))['docs_only']
