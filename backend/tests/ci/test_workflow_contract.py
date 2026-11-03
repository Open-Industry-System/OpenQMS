from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
import copy
import re

import yaml


ROOT = Path(__file__).resolve().parents[3]
AUTOMATIC_PATH = ROOT / '.github/workflows/test.yml'
ACCEPTANCE_PATH = ROOT / '.github/workflows/acceptance.yml'
PG_IMAGE = 'pgvector/pgvector:pg15'
CLAMAV_IMAGE = (
    'clamav/clamav:1.4.3_base@sha256:'
    'be37f82c9cccf6c2559a44b8fb537e6f11e8547b37988650b169c4540c2f298c'
)


class GitHubActionsLoader(yaml.SafeLoader):
    """SafeLoader with YAML 1.2-style booleans so `on` remains a key."""


GitHubActionsLoader.yaml_implicit_resolvers = {
    key: [entry for entry in value if entry[0] != 'tag:yaml.org,2002:bool']
    for key, value in copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers).items()
}
GitHubActionsLoader.add_implicit_resolver(
    'tag:yaml.org,2002:bool', re.compile(r'^(?:true|false)$', re.IGNORECASE), list('tTfF'),
)


def _load_workflow(path: Path) -> dict[str, object]:
    assert path.is_file(), f'missing workflow: {path.relative_to(ROOT)}'
    data = yaml.load(path.read_text(), Loader=GitHubActionsLoader)
    assert isinstance(data, dict)
    assert 'on' in data, 'YAML parser must preserve the Actions `on` key'
    return data


def _jobs(workflow: Mapping[str, object]) -> Mapping[str, Mapping[str, object]]:
    jobs = workflow.get('jobs')
    assert isinstance(jobs, Mapping)
    return jobs  # type: ignore[return-value]


def _steps(job: Mapping[str, object]) -> list[Mapping[str, object]]:
    steps = job.get('steps')
    assert isinstance(steps, list)
    return [step for step in steps if isinstance(step, Mapping)]


def _named_steps(job: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    return {str(step['name']): step for step in _steps(job) if 'name' in step}


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from _strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _strings(nested)


def _assert_secretless(job: Mapping[str, object]) -> None:
    assert not any('secrets.' in text for text in _strings(job))


def _assert_checkouts_do_not_persist_credentials(workflow: Mapping[str, object]) -> None:
    checkout_steps = [
        step
        for job in _jobs(workflow).values()
        for step in _steps(job)
        if str(step.get('uses', '')).startswith('actions/checkout@')
    ]
    assert checkout_steps
    for checkout in checkout_steps:
        options = checkout.get('with')
        assert isinstance(options, Mapping)
        assert options.get('persist-credentials') is False


def _postgres_environment(job: Mapping[str, object], job_name: str) -> dict[str, object]:
    services = job.get('services')
    assert isinstance(services, Mapping)
    postgres = services.get('postgres')
    assert isinstance(postgres, Mapping)
    assert postgres.get('image') == PG_IMAGE
    assert postgres.get('ports') == ['5432/tcp']
    options = str(postgres.get('options', ''))
    assert '--health-cmd pg_isready' in options
    for label in (
        '--label openqms.ci.run=${{ github.run_id }}',
        '--label openqms.ci.attempt=${{ github.run_attempt }}',
        f'--label openqms.ci.job={job_name}',
    ):
        assert label in options
    return dict(postgres)


def _assert_disabled_provider_environment(step: Mapping[str, object]) -> None:
    env = step.get('env')
    assert isinstance(env, Mapping)
    for key in ('LLM_PROVIDER', 'LLM_API_KEY', 'LLM_BASE_URL', 'EMBEDDING_PROVIDER', 'EMBEDDING_API_KEY'):
        assert env.get(key) == ''
    assert 'E2E_MODE' not in env


def test_automatic_workflow_is_secretless_on_branch_pushes_and_main_pull_requests() -> None:
    workflow = _load_workflow(AUTOMATIC_PATH)
    triggers = workflow['on']
    assert isinstance(triggers, Mapping)
    push = triggers.get('push')
    pull_request = triggers.get('pull_request')
    assert isinstance(push, Mapping) and push.get('branches') == ['**']
    assert 'tags' not in push
    assert isinstance(pull_request, Mapping) and pull_request.get('branches') == ['main']
    assert workflow.get('permissions') == {'contents': 'read'}
    assert workflow.get('concurrency') == {
        'group': 'ci-${{ github.workflow }}-${{ github.ref }}',
        'cancel-in-progress': True,
    }
    assert 'pull_request_target' not in triggers
    _assert_checkouts_do_not_persist_credentials(workflow)
    for job in _jobs(workflow).values():
        _assert_secretless(job)
        env = job.get('env')
        assert isinstance(env, Mapping)
        for key in ('LLM_PROVIDER', 'LLM_API_KEY', 'LLM_BASE_URL', 'EMBEDDING_PROVIDER', 'EMBEDDING_API_KEY'):
            assert env.get(key) == ''


def test_backend_uses_a_verified_random_port_database_before_every_database_consumer() -> None:
    backend = _jobs(_load_workflow(AUTOMATIC_PATH))['backend-tests']
    _postgres_environment(backend, 'backend-tests')
    steps = _named_steps(backend)
    prepare = steps['Prepare verified test database']
    required_env = {
        'PG15_CONTAINER': '${{ job.services.postgres.id }}',
        'GITHUB_RUN_ID': '${{ github.run_id }}',
        'GITHUB_RUN_ATTEMPT': '${{ github.run_attempt }}',
        'GITHUB_JOB': 'backend-tests',
        "TEST_DATABASE_URL": "postgresql+asyncpg://qms:qms_dev_2026@localhost:${{ job.services.postgres.ports['5432'] }}/qms_test",
    }
    assert isinstance(prepare.get('env'), Mapping)
    assert {key: prepare['env'].get(key) for key in required_env} == required_env
    assert 'python -m tests.ci.prepare_database' in str(prepare.get('run', ''))
    _assert_disabled_provider_environment(prepare)
    prepare_index = _steps(backend).index(prepare)
    for step in _steps(backend)[prepare_index + 1:]:
        run = str(step.get('run', ''))
        if 'make check-backend' in run or 'capa_doc_gate_preflight' in run:
            assert isinstance(step.get('env'), Mapping)
            assert step['env'].get('TEST_DATABASE_URL') == required_env['TEST_DATABASE_URL']
            _assert_disabled_provider_environment(step)
    assert 'make check-backend' in str(steps['Run deterministic backend acceptance'].get('run', ''))
    doc_gate = steps['D8 doc-gate preflight (against migrated test DB)']
    assert isinstance(doc_gate.get('env'), Mapping)
    assert {key: doc_gate['env'].get(key) for key in required_env} == required_env


def test_frontend_uses_its_lockfile_without_falling_back_to_npm_install() -> None:
    frontend = _jobs(_load_workflow(AUTOMATIC_PATH))['frontend-checks']
    steps = _named_steps(frontend)
    install = steps['Validate lockfile and install dependencies']
    script = str(install.get('run', ''))
    assert 'package-lock.json' in script
    assert 'npm ci' in script
    assert 'npm install' not in script
    assert 'lockfile' in script.lower()


def test_browser_protection_is_a_separate_secretless_postgres_and_chromium_job() -> None:
    browser = _jobs(_load_workflow(AUTOMATIC_PATH))['browser-protection']
    _postgres_environment(browser, 'browser-protection')
    _assert_secretless(browser)
    steps = _named_steps(browser)
    prepare = steps['Prepare verified browser database']
    assert isinstance(prepare.get('env'), Mapping)
    assert prepare['env'].get('PG15_CONTAINER') == '${{ job.services.postgres.id }}'
    assert prepare['env'].get('GITHUB_JOB') == 'browser-protection'
    assert prepare['env'].get('TEST_DATABASE_URL') == (
        "postgresql+asyncpg://qms:qms_dev_2026@localhost:${{ job.services.postgres.ports['5432'] }}/qms_test"
    )
    _assert_disabled_provider_environment(prepare)
    assert 'npm ci' in str(steps['Install frontend dependencies'].get('run', ''))
    assert 'npx --no-install playwright install --with-deps chromium' in str(steps['Install Chromium'].get('run', ''))
    check = steps['Run deterministic browser protection']
    assert 'make check-browser' in str(check.get('run', ''))
    _assert_disabled_provider_environment(check)


def test_docs_check_covers_test_infrastructure_and_keeps_the_pr_exception() -> None:
    docs = _jobs(_load_workflow(AUTOMATIC_PATH))['docs-check']
    assert docs.get('if') == "github.event_name == 'pull_request'"
    script = str(_named_steps(docs)['Verify docs updated alongside code changes'].get('run', ''))
    assert 'docs-not-needed' in script
    for infrastructure in ('.github/workflows/', 'Makefile', 'backend/tests/', 'frontend/e2e/', 'playwright'):
        assert infrastructure in script
    assert 'AGENTS.md' in script
    assert 'CLAUDE.md' not in script
    assert 'docs/' in script and 'README.md' in script


def test_manual_workflow_is_main_only_fixed_choice_and_has_no_cancellation_policy() -> None:
    workflow = _load_workflow(ACCEPTANCE_PATH)
    assert workflow['on'] == {
        'workflow_dispatch': {
            'inputs': {
                'gate': {
                    'description': 'Acceptance gate to run',
                    'required': True,
                    'type': 'choice',
                    'options': ['live-capa', 'scanner', 'all'],
                },
            },
        },
    }
    assert workflow.get('permissions') == {'contents': 'read'}
    assert 'concurrency' not in workflow
    _assert_checkouts_do_not_persist_credentials(workflow)
    preflight = _jobs(workflow)['preflight']
    assert 'runs-on' in preflight
    steps = _named_steps(preflight)
    checkout = steps['Checkout main at preflight']
    assert isinstance(checkout.get('with'), Mapping) and checkout['with'].get('ref') == 'main'
    script = str(steps['Verify dispatch and freeze main SHA'].get('run', ''))
    for required in (
        'set -euo pipefail',
        '[ "$GITHUB_EVENT_NAME" = workflow_dispatch ]',
        '[ "$GITHUB_REF" = refs/heads/main ]',
        'case "$GATE" in live-capa|scanner|all)',
        'git rev-parse HEAD',
        'frozen_sha',
    ):
        assert required in script


def test_manual_live_and_scanner_gates_are_independent_and_only_live_receives_provider_values() -> None:
    workflow = _load_workflow(ACCEPTANCE_PATH)
    jobs = _jobs(workflow)
    preflight = jobs['preflight']
    assert 'environment' not in preflight
    live = jobs['live-capa']
    scanner = jobs['scanner']
    assert live.get('needs') == ['preflight']
    assert scanner.get('needs') == ['preflight']
    assert "inputs.gate == 'live-capa' || inputs.gate == 'all'" in str(live.get('if', ''))
    assert "inputs.gate == 'scanner' || inputs.gate == 'all'" in str(scanner.get('if', ''))
    assert live.get('environment') == 'ci-acceptance'
    _postgres_environment(live, 'live-capa')
    live_steps = _named_steps(live)
    assert live_steps['Checkout frozen main SHA'].get('with', {}).get('ref') == '${{ needs.preflight.outputs.frozen_sha }}'
    live_env_steps = [step for step in _steps(live) if any('secrets.' in text for text in _strings(step))]
    assert len(live_env_steps) == 1
    live_execution = live_env_steps[0]
    assert live_execution.get('name') == 'Run live CAPA acceptance'
    assert isinstance(live_execution.get('env'), Mapping)
    for key in ('LLM_PROVIDER', 'LLM_MODEL', 'LLM_TIMEOUT', 'LLM_API_KEY', 'LLM_BASE_URL'):
        assert key in live_execution['env']
    assert 'make check-live' in str(live_execution.get('run', ''))
    assert 'npx --no-install playwright install --with-deps chromium' in str(live_steps['Install Chromium'].get('run', ''))
    for step in _steps(live):
        if step is not live_execution:
            assert not any('secrets.' in text for text in _strings(step))
    _assert_secretless(scanner)
    scanner_steps = _named_steps(scanner)
    assert scanner_steps['Checkout frozen main SHA'].get('with', {}).get('ref') == '${{ needs.preflight.outputs.frozen_sha }}'
    assert 'npx --no-install playwright install --with-deps chromium' in str(scanner_steps['Install Chromium'].get('run', ''))
    assert 'make agent-attachment-e2e' in str(scanner_steps['Run scanner acceptance'].get('run', ''))
    assert CLAMAV_IMAGE in (ROOT / 'docker-compose.yml').read_text()


def test_manual_summary_requires_requested_successful_receipts_and_marks_other_gate_not_requested() -> None:
    summary = _jobs(_load_workflow(ACCEPTANCE_PATH))['summary']
    assert summary.get('if') == 'always()'
    assert summary.get('needs') == ['preflight', 'live-capa', 'scanner']
    script = str(_named_steps(summary)['Require requested gate receipts'].get('run', ''))
    for required in ('NOT_REQUESTED', 'cancelled', 'blocked', 'receipt', 'exit 1'):
        assert required in script
    assert 'continue-on-error' not in '\n'.join(_strings(summary))


def test_workflow_expressions_and_artifacts_remain_safe_and_sanitized() -> None:
    for workflow in (_load_workflow(AUTOMATIC_PATH), _load_workflow(ACCEPTANCE_PATH)):
        serialized = '\n'.join(_strings(workflow))
        assert '/Users/' not in serialized
        expressions = re.findall(r'\$\{\{\s*([^}]+?)\s*}}', serialized)
        assert expressions
        for expression in expressions:
            assert expression.startswith(('github.', 'inputs.', 'needs.', 'steps.', 'vars.', 'secrets.', 'job.', 'env.')) or expression.startswith('toJson(github.')
        assert '${{' not in re.sub(r'\$\{\{\s*(?:github\.|inputs\.|needs\.|steps\.|vars\.|secrets\.|job\.|env\.|toJson\(github\.)[^}]+}}', '', serialized)
        for job in _jobs(workflow).values():
            for step in _steps(job):
                if str(step.get('uses', '')).startswith('actions/upload-artifact@'):
                    assert 'failure()' in str(step.get('if', '')) or 'receipt' in str(step.get('name', '')).lower()
                    path = str(step.get('with', {}).get('path', ''))
                    assert path
                    assert not re.search(r'(?i)(raw.*\.xml|\.env|profile|registry)', path)


def test_real_evidence_has_explicit_roots_always_uploads_and_sha_binding():
    for path, names in ((AUTOMATIC_PATH, ('backend-tests', 'browser-protection', 'frontend-checks')),
                        (ACCEPTANCE_PATH, ('live-capa', 'scanner'))):
        jobs = _jobs(_load_workflow(path))
        for name in names:
            job = jobs[name]
            env = job.get('env', {})
            assert env.get('OPENQMS_TEST_ARTIFACTS') == '${{ github.workspace }}/ci-safe/' + name
            assert env.get('OPENQMS_CI_SHA') == ('${{ github.sha }}' if path == AUTOMATIC_PATH
                                                else '${{ needs.preflight.outputs.frozen_sha }}')
            uploads = [s for s in _steps(job) if str(s.get('uses', '')).startswith('actions/upload-artifact@')]
            assert len(uploads) == 1
            assert uploads[0].get('if') == 'always()'
            assert uploads[0]['with']['if-no-files-found'] == 'error'
            assert '${{ env.OPENQMS_TEST_ARTIFACTS }}' in uploads[0]['with']['path']
            script = '\n'.join(str(s.get('run', '')) for s in _steps(job))
            assert "printf '{\"gate\":\"live-capa\",\"status\":\"PASSED\"}" not in script
            assert "printf '{\"gate\":\"scanner\",\"status\":\"PASSED\"}" not in script
    jobs = _jobs(_load_workflow(ACCEPTANCE_PATH))
    summary = _named_steps(jobs['summary'])
    assert any(str(s.get('uses', '')).startswith('actions/checkout@') for s in summary.values())
    assert 'tests.ci.acceptance_evidence summary' in summary['Require requested gate receipts']['run']
    assert 'FROZEN_SHA' in summary['Require requested gate receipts']['env']
    makefile = (ROOT / 'Makefile').read_text()
    assert 'docker cp "$$project-process:/var/run/openqms/agent-attachment-e2e/receipts/." -' in makefile
    assert makefile.index('export-scanner') < makefile.index('dc down --volumes', makefile.index('agent-attachment-e2e:'))
    assert 'tests.ci.acceptance_evidence cleanup' in makefile
    assert '--name "$$project-process"' in makefile
    assert 'run --rm --no-deps agent-attachment-e2e' not in makefile
