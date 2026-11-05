from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import subprocess

import pytest
import yaml

BACKEND = 'not ci_browser and not live_provider and not real_scanner'
BROWSER = 'ci_browser and not live_provider and not real_scanner'
LIVE = 'live_provider'
SCANNER = 'real_scanner and not live_provider'

TARGETS = (
    'tests/e2e/test_agent_readonly_resume_process.py',
    'tests/e2e/test_agent_local_trial_browser.py',
    'tests/e2e/test_agent_local_trial_process.py',
    'tests/e2e/test_d4_text_preview_browser.py',
    'tests/e2e/test_capa_outcome_review_browser.py',
    'tests/e2e/test_agent_task_attachment_browser.py',
    'tests/e2e/test_agent_task_attachment_process.py',
)

BROWSER_NODES = (
    'tests/e2e/test_agent_readonly_resume_process.py::test_actual_local_browser_sidebar_acceptance',
    'tests/e2e/test_agent_local_trial_browser.py::test_normal_policy_local_browser_lifecycle_revoke_and_current_source_withdrawal',
    'tests/e2e/test_d4_text_preview_browser.py::test_actual_employee_preview_masks_text_and_withdraws_changed_or_denied_sources',
    'tests/e2e/test_capa_outcome_review_browser.py::test_employee_chromium_terminal_protection',
)
LIVE_NODES = (
    'tests/e2e/test_capa_outcome_review_browser.py::test_live_employee_http_provider_chromium_outcome_review',
)
BACKEND_NODES = (
    'tests/e2e/test_capa_outcome_review_browser.py::test_employee_controlled_source_modules_fail_closed',
    'tests/e2e/test_agent_task_attachment_process.py::test_actual_attachment_stack_requires_compose_opt_in',
)
LOCAL_TRIAL_PROCESS_BACKEND_NODES = (
    'tests/e2e/test_agent_local_trial_process.py::test_normal_policy_real_cli_rounds_same_run_resume_and_checkpoint_new_run',
    'tests/e2e/test_agent_local_trial_process.py::test_cli_permanent_revoke_between_actual_rounds_prevents_later_delivery',
    'tests/e2e/test_agent_local_trial_process.py::test_actual_tcp_forwarded_identity_is_rejected_before_invalid_tenant_or_body',
)
SCANNER_NODES = (
    'tests/e2e/test_agent_task_attachment_browser.py::test_actual_clamav_attachment_browser_acceptance',
    'tests/e2e/test_agent_task_attachment_process.py::test_actual_clamav_advertises_version_and_instream',
    'tests/e2e/test_agent_task_attachment_process.py::test_actual_clamav_reports_found_for_newline_instream',
    'tests/e2e/test_agent_task_attachment_process.py::test_actual_scan_stream_reaches_found_with_safe_parse_stage_trace',
    'tests/e2e/test_agent_task_attachment_process.py::test_actual_clamav_rejects_eicar_and_never_promotes_clean_file',
    'tests/e2e/test_agent_task_attachment_process.py::test_actual_clamav_rejects_encrypted_and_expansion_limit_samples',
    'tests/e2e/test_agent_task_attachment_process.py::test_actual_clamav_allows_only_clean_fixture_to_download',
)


def layer(item: pytest.Item) -> str:
    marks = {m.name for m in item.iter_markers()}
    if 'live_provider' in marks:
        return 'live'
    if 'real_scanner' in marks:
        return 'scanner'
    return 'browser' if 'ci_browser' in marks else 'backend'


class ItemCollector:
    def __init__(self) -> None:
        self.items: list[pytest.Item] = []

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        self.items = list(session.items)


@pytest.fixture(scope='module')
def collected_items() -> list[pytest.Item]:
    collector = ItemCollector()
    result = pytest.main(['--collect-only', '-q', *TARGETS], plugins=[collector])
    assert result == pytest.ExitCode.OK
    return collector.items


def _nodeids(items: Iterable[pytest.Item], node_prefix: str) -> set[str]:
    return {item.nodeid for item in items if item.nodeid.startswith(node_prefix)}


def _assert_layer(items: Iterable[pytest.Item], expected: str, node_prefix: str) -> None:
    nodeids = _nodeids(items, node_prefix)
    assert nodeids, f'missing collected node {node_prefix}'
    assert {layer(item) for item in items if item.nodeid in nodeids} == {expected}


def test_fixed_nodes_have_the_expected_ci_layer(collected_items: list[pytest.Item]) -> None:
    for node in BROWSER_NODES:
        _assert_layer(collected_items, 'browser', node)
    for node in LIVE_NODES:
        _assert_layer(collected_items, 'live', node)
    for node in SCANNER_NODES:
        _assert_layer(collected_items, 'scanner', node)
    for node in BACKEND_NODES:
        _assert_layer(collected_items, 'backend', node)
    for node in LOCAL_TRIAL_PROCESS_BACKEND_NODES:
        _assert_layer(collected_items, 'backend', node)

    readonly_non_browser = [
        item
        for item in collected_items
        if item.nodeid.startswith('tests/e2e/test_agent_readonly_resume_process.py::')
        and not item.nodeid.startswith(BROWSER_NODES[0])
    ]
    assert readonly_non_browser
    assert {layer(item) for item in readonly_non_browser} == {'backend'}


def test_layers_partition_the_fixed_collected_suite(collected_items: list[pytest.Item]) -> None:
    layers = {
        name: {item.nodeid for item in collected_items if layer(item) == name}
        for name in ('backend', 'browser', 'live', 'scanner')
    }
    all_nodeids = {item.nodeid for item in collected_items}

    assert all_nodeids == set().union(*layers.values())
    assert sum(len(nodes) for nodes in layers.values()) == len(all_nodeids)

    for item in collected_items:
        marks = {marker.name for marker in item.iter_markers()}
        assert not {'live_provider', 'real_scanner'} <= marks


def test_marker_selection_expressions_match_the_fixed_layers(collected_items: list[pytest.Item]) -> None:
    expected = {
        BACKEND: 'backend',
        BROWSER: 'browser',
        LIVE: 'live',
        SCANNER: 'scanner',
    }
    for expression, expected_layer in expected.items():
        collector = ItemCollector()
        result = pytest.main(['--collect-only', '-q', '-m', expression, *TARGETS], plugins=[collector])
        assert result == pytest.ExitCode.OK
        assert {item.nodeid for item in collector.items} == {
            item.nodeid for item in collected_items if layer(item) == expected_layer
        }


def _make_dry_run(target: str) -> str:
    root = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        ['make', '--dry-run', target], cwd=root, text=True, capture_output=True, check=True,
    )
    return completed.stdout


def test_make_layered_targets_use_receipted_runner_and_verified_single_database_target() -> None:
    backend = _make_dry_run('check-backend')
    browser = _make_dry_run('check-browser')
    live = _make_dry_run('check-live')
    database = _make_dry_run('check-test-db')
    scanner = _make_dry_run('agent-attachment-e2e')

    assert 'tests.ci.prepare_database' in database
    assert " -c " not in database
    assert 'docker compose --env-file /dev/null' in scanner
    assert f'-f "{Path(__file__).resolve().parents[3] / "docker-compose.yml"}"' in scanner
    assert 'docker compose config' not in scanner
    for output, mode in ((backend, 'api'), (browser, 'browser')):
        assert f'capa_outcome_runner.py {mode} --pytest-target tests' in output
        assert '--pytest-arg=--ignore=tests/test_graph_sync_worker.py' in output
        assert '--pytest-arg=--ignore=tests/test_graph_projection.py' in output
    assert 'capa_outcome_runner.py live' in live
    assert '--pytest-target tests' not in live


def test_make_marker_constants_match_the_receipted_runner_contract() -> None:
    from tests.e2e.capa_outcome_runner import MARKS

    root = Path(__file__).resolve().parents[3]
    database = subprocess.run(
        ['make', '--print-data-base', '--no-builtin-rules', '--dry-run'],
        cwd=root, text=True, capture_output=True, check=True,
    ).stdout
    values = {
        line.split(' := ', 1)[0]: line.split(' := ', 1)[1]
        for line in database.splitlines()
        if line.startswith('PYTEST_') and ' := ' in line
    }

    assert values['PYTEST_BACKEND_MARKS'] == MARKS['api']
    assert values['PYTEST_BROWSER_MARKS'] == MARKS['browser']
    assert values['PYTEST_LIVE_MARKS'] == MARKS['live']


def test_backend_workflow_uses_verified_prepare_and_deterministic_make_path() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = yaml.safe_load((root / '.github/workflows/test.yml').read_text())
    backend = workflow['jobs']['backend-tests']
    options = backend['services']['postgres']['options']
    for label in (
        '--label openqms.ci.run=${{ github.run_id }}',
        '--label openqms.ci.attempt=${{ github.run_attempt }}',
        '--label openqms.ci.job=backend-tests',
    ):
        assert label in options

    steps = {step['name']: step for step in backend['steps'] if 'name' in step}
    required_env = {
        'PG15_CONTAINER': '${{ job.services.postgres.id }}',
        'GITHUB_RUN_ID': '${{ github.run_id }}',
        'GITHUB_RUN_ATTEMPT': '${{ github.run_attempt }}',
        'GITHUB_JOB': 'backend-tests',
        "TEST_DATABASE_URL": "postgresql+asyncpg://qms:qms_dev_2026@localhost:${{ job.services.postgres.ports['5432'] }}/qms_test",
    }
    assert {key: steps['Prepare verified test database']['env'][key] for key in required_env} == required_env
    assert 'python -m tests.ci.prepare_database' in steps['Prepare verified test database']['run']
    assert {key: steps['Run deterministic backend acceptance']['env'][key] for key in required_env} == required_env
    assert 'make check-backend' in steps['Run deterministic backend acceptance']['run']
    assert all('alembic upgrade head' not in step.get('run', '') for step in backend['steps'])
    assert all('pytest tests/' not in step.get('run', '') for step in backend['steps'])


def test_default_api_acceptance_command_collects_mandatory_source_denial_only_in_backend_layer(tmp_path):
    from tests.e2e.capa_outcome_runner import DEFAULT_TARGETS, MARKS, build_pytest_command

    command = build_pytest_command(
        'api', DEFAULT_TARGETS['api'], tmp_path / 'collection.xml', tmp_path / 'hooks.json',
    )
    assert command[command.index('-m', 3) + 1] == BACKEND == MARKS['api']
    collector = ItemCollector()
    # Inspect the actual command's targets/marker without loading execution-only
    # receipt hooks a second time into this in-process collection session.
    mark_index = command.index('-m', 3)
    result = pytest.main(['--collect-only', '-q', *command[3:mark_index + 2]], plugins=[collector])
    assert result == pytest.ExitCode.OK
    nodeids = {item.nodeid for item in collector.items}
    assert 'tests/e2e/test_capa_outcome_review_browser.py::test_employee_controlled_source_modules_fail_closed' in nodeids
    assert collector.items and {layer(item) for item in collector.items} == {'backend'}
    assert not any(_nodeids(collector.items, prefix) for prefix in (*BROWSER_NODES, *LIVE_NODES, *SCANNER_NODES))
