from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import subprocess

import pytest
import yaml

BACKEND = 'not ci_browser and not ci_r5_native and not live_provider and not real_scanner'
BROWSER = 'ci_browser and not ci_r5_native and not live_provider and not real_scanner'
LIVE = 'live_provider'
SCANNER = 'real_scanner and not live_provider'

TARGETS = (
    'tests/e2e/test_agent_readonly_resume_process.py',
    'tests/e2e/test_agent_local_trial_browser.py',
    'tests/e2e/test_agent_local_trial_process.py',
    'tests/e2e/test_agent_sdk_process.py',
    'tests/e2e/test_d4_text_local_process.py',
    'tests/e2e/test_d4_text_preview_browser.py',
    'tests/e2e/test_capa_outcome_review_browser.py',
    'tests/e2e/test_agent_task_attachment_browser.py',
    'tests/e2e/test_agent_task_attachment_process.py',
    'tests/e2e/test_r5_model_agent.py',
    'tests/e2e/test_r5_responses_agent.py',
    'tests/e2e/test_r5_d5_process.py',
    'tests/services/agent_runtime/test_r5_model_binding.py',
    'tests/migrations/test_r5_d5_delta.py',
    'tests/migrations/test_r5_d5_basis_delta.py',
    'tests/migrations/test_r5_model_delta.py',
    'tests/migrations/test_r5_responses_delta.py',
    'tests/e2e/test_r5_d5_ui.py',
    'tests/e2e/test_r5_d5_browser.py',

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
SDK_PROCESS_BACKEND_NODES = (
    'tests/e2e/test_agent_sdk_process.py::test_installed_sdk_claim_crosses_real_tcp',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_ten_operations_sources_idempotency_and_terminal_fence',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_finish_committed_but_confirmation_unknown[oversize]',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_finish_committed_but_confirmation_unknown[bad_json]',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_finish_committed_but_confirmation_unknown[wrong_run]',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_finish_committed_but_confirmation_unknown[wrong_task]',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_finish_committed_but_confirmation_unknown[wrong_status]',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_finish_committed_but_confirmation_unknown[schema]',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_finish_committed_but_confirmation_unknown[disconnect]',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_finish_committed_but_confirmation_unknown[server_error]',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_finish_committed_but_confirmation_unknown[timeout]',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_report_pause_restart_and_old_receipt_fences',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_credentials_cannot_claim_in_another_real_tenant',
    'tests/e2e/test_agent_sdk_process.py::test_sdk_admin_grant_withdrawal_and_permanent_revoke',
)
D4_TEXT_BACKEND_NAMES = (
    'test_fixed_text_receiver_normal_http',
    'test_source_swap_never_widens_old_grants',
    'test_declaration_denials_hide_node_existence[no-view]',
    'test_declaration_denials_hide_node_existence[outside-line]',
    'test_revision_and_verification_changes_fence_old_proofs',
    'test_text_scope_idempotency_and_restart_do_not_regrant',
    'test_blocked_task_source_request_replay',
    'test_revoked_text_grant_does_not_block_stop_controls',
    'test_first_claimable_text_profile_has_message_gate',
    'test_text_budget_and_response_faults_fail_closed',
    'test_text_finish_commit_without_confirmation_is_unknown',
    'test_text_current_authority_and_tenant_boundaries[cross-tenant]',
    'test_text_current_authority_and_tenant_boundaries[generation]',
    'test_text_current_authority_and_tenant_boundaries[fmea-acl]',
    'test_text_current_authority_and_tenant_boundaries[role]',
    'test_text_current_authority_and_tenant_boundaries[source-factory]',
    'test_text_current_authority_and_tenant_boundaries[source-line]',
    'test_text_current_authority_and_tenant_boundaries[paused-epoch]',
    'test_text_current_authority_and_tenant_boundaries[policy]',
    'test_text_current_authority_and_tenant_boundaries[permanent]',
    'test_metadata_sdk_and_worker_contracts_remain_unchanged',
)
D4_TEXT_BACKEND_NODES = tuple('tests/e2e/test_d4_text_local_process.py::' + name for name in D4_TEXT_BACKEND_NAMES)
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
    if 'ci_r5_native' in marks:return 'r5-browser' if 'ci_browser' in marks else 'r5-api'
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

    from tests.e2e.capa_outcome_runner import SDK_PROCESS_NAMES, SDK_PROCESS_TARGET

    assert {f'{SDK_PROCESS_TARGET}::{name}' for name in SDK_PROCESS_NAMES} == set(SDK_PROCESS_BACKEND_NODES)
    assert len(SDK_PROCESS_BACKEND_NODES) == 14
    assert _nodeids(collected_items, 'tests/e2e/test_agent_sdk_process.py::') == set(SDK_PROCESS_BACKEND_NODES)
    for node in SDK_PROCESS_BACKEND_NODES:
        _assert_layer(collected_items, 'backend', node)

    from tests.e2e.capa_outcome_runner import D4_TEXT_PROCESS_NAMES
    assert set(D4_TEXT_BACKEND_NAMES) == D4_TEXT_PROCESS_NAMES
    assert _nodeids(collected_items, 'tests/e2e/test_d4_text_local_process.py::') == set(D4_TEXT_BACKEND_NODES)
    for node in D4_TEXT_BACKEND_NODES:
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
        for name in ('backend', 'browser', 'r5-api', 'r5-browser', 'live', 'scanner')
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
        'ci_r5_native and not ci_browser and not live_provider and not real_scanner':'r5-api',
        'ci_r5_native and ci_browser and not live_provider and not real_scanner':'r5-browser',
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


def test_sdk_make_targets_are_backend_independent_and_allocate_private_artifact_children() -> None:
    for target, layer_name in (
        ('check-sdk-unit', 'unit'), ('check-sdk-loopback', 'loopback'),
        ('check-sdk-wheel', 'wheel'), ('check-sdk', 'all'),
    ):
        output = _make_dry_run(target)
        assert 'sdk/python/scripts/check-sdk.py' in output
        assert f'--layer {layer_name}' in output and '--artifacts' in output
        assert 'mktemp -d' in output
        assert 'tests.ci.prepare_database' not in output
        assert 'requirements.txt' not in output and 'pip install' not in output
    aggregate = _make_dry_run('check')
    assert '--layer all' in aggregate


def test_backend_make_builds_current_sdk_wheel_and_extracts_resource_from_json() -> None:
    output = _make_dry_run('check-backend')
    assert 'sdk/python/scripts/build-wheel.py' in output
    assert '--source' in output and 'sdk/python' in output and '--artifacts' in output
    assert 'mktemp -d' in output
    assert 'json.load' in output and 'wheel_path' in output and 'wheel_sha256' in output
    assert 'OPENQMS_SDK_WHEEL=' in output
    assert output.index('build-wheel.py') < output.index('capa_outcome_runner.py api')
    assert 'glob' not in output and 'pip install' not in output


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
    backend = workflow['jobs']['backend-full']
    options = backend['services']['postgres']['options']
    for label in (
        '--label openqms.ci.run=${{ github.run_id }}',
        '--label openqms.ci.attempt=${{ github.run_attempt }}',
        '--label openqms.ci.job=backend-full',
    ):
        assert label in options

    steps = {step['name']: step for step in backend['steps'] if 'name' in step}
    required_env = {
        'PG15_CONTAINER': '${{ job.services.postgres.id }}',
        'GITHUB_RUN_ID': '${{ github.run_id }}',
        'GITHUB_RUN_ATTEMPT': '${{ github.run_attempt }}',
        'GITHUB_JOB': 'backend-full',
        "TEST_DATABASE_URL": "postgresql+asyncpg://qms:qms_dev_2026@localhost:${{ job.services.postgres.ports['5432'] }}/qms_test",
    }
    assert 'Prepare verified test database' not in steps
    assert 'check-backend: check-test-db' in (root / 'Makefile').read_text()
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


def test_default_api_acceptance_selects_all_fourteen_sdk_nodes_without_optional_markers(tmp_path):
    from tests.e2e.capa_outcome_runner import DEFAULT_TARGETS, build_pytest_command

    command = build_pytest_command(
        'api', DEFAULT_TARGETS['api'], tmp_path / 'collection.xml', tmp_path / 'hooks.json',
    )
    collector = ItemCollector()
    mark_index = command.index('-m', 3)
    result = pytest.main(['--collect-only', '-q', *command[3:mark_index + 2]], plugins=[collector])
    assert result == pytest.ExitCode.OK
    assert _nodeids(collector.items, 'tests/e2e/test_agent_sdk_process.py::') == set(SDK_PROCESS_BACKEND_NODES)
    for node in SDK_PROCESS_BACKEND_NODES:
        _assert_layer(collector.items, 'backend', node)


def test_r5_required_execution_checks_reject_missing_skipped_and_duplicate_nodes(tmp_path):
    from tests.e2e import capa_outcome_runner as runner
    assert hasattr(runner, '_require_r5_success'), 'R5 has no mandatory execution receipt contract'
    from xml.etree import ElementTree as ET
    assert runner.R5_REQUIRED['r5-browser']
    for mode in ('api','r5-api','r5-browser'):
        expected=runner.R5_REQUIRED[mode]
        assert expected
        root=ET.Element('testsuite')
        for classname,names in expected.items():
            for name in names:
                ET.SubElement(root,'testcase',classname=classname,name=name)
        path=tmp_path/'r5.xml'
        ET.ElementTree(root).write(path)
        runner._require_r5_success(path,{'xpassed':0},mode,('tests',))
        first=list(root)[0]
        ET.SubElement(first,'skipped')
        ET.ElementTree(root).write(path)
        with pytest.raises(ValueError):runner._require_r5_success(path,{'xpassed':0},mode,('tests',))
        first.remove(list(first)[0]);root.remove(first)
        ET.ElementTree(root).write(path)
        with pytest.raises(ValueError):runner._require_r5_success(path,{'xpassed':0},mode,('tests',))
        root.append(first);root.append(first)
        ET.ElementTree(root).write(path)
        with pytest.raises(ValueError):runner._require_r5_success(path,{'xpassed':0},mode,('tests',))


def test_r5_default_targets_and_marker_contract_cover_actual_process_browser_and_migrations():
    from tests.e2e import capa_outcome_runner as runner
    assert hasattr(runner,'R5_REQUIRED'), 'R5 missing required node catalog'
    for mode in ('api','r5-api','r5-browser'):
        for classname in runner.R5_REQUIRED[mode]:
            target=classname.replace('.','/')+'.py'
            assert target in runner.DEFAULT_TARGETS[mode]
    assert 'tests.e2e.test_r5_d5_ui' in runner.R5_REQUIRED['r5-browser']
    assert 'tests.e2e.test_r5_d5_browser' in runner.R5_REQUIRED['r5-browser']
    for name in ('test_r5_d5_process','test_r5_model_agent','test_r5_responses_agent'):
        assert 'tests.e2e.'+name in runner.R5_REQUIRED['r5-api']


def test_fixed_r5_catalog_matches_collection_and_required_layer(collected_items):
    from tests.ci.r5_required import R5_REQUIRED
    for mode,classes in R5_REQUIRED.items():
        for classname,names in classes.items():
            prefix=classname.replace('.','/')+'.py::'
            assert _nodeids(collected_items,prefix)=={prefix+name for name in names}
            for name in names:_assert_layer(collected_items,'backend' if mode=='api' else mode,prefix+name)


def test_r5_platform_credentials_and_pilot_configuration_never_enter_ordinary_children():
    from tests.e2e.capa_outcome_runner import build_layer_environment
    from tests.ci.browser_runtime import browser_environment
    private={'R5_MODEL_CREDENTIAL_SYNTHETIC':'private-key-sentinel',
             'AGENT_R5_MODEL_PILOT_FILE':'private-policy-sentinel',
             'AGENT_R5_MODEL_PILOT_ENABLED':'true','OPENAI_API_KEY':'provider-sentinel'}
    for layer in ('api','browser','r5-api','r5-browser'):
        env=build_layer_environment(private,'postgresql+asyncpg://u:p@127.0.0.1:1/r5_test',layer)
        assert not any('sentinel' in value for value in env.values())
        assert not any(key.startswith(('R5_MODEL_CREDENTIAL_','AGENT_R5_')) for key in env)
        assert not any('sentinel' in value for value in browser_environment(private,{}).values())


def test_r5_manual_workflow_keeps_supported_host_and_explicit_job_bundle():
    root=Path(__file__).resolve().parents[3]
    job=yaml.safe_load((root/'.github/workflows/r5-native.yml').read_text())['jobs']['r5-native']
    assert job['runs-on']==['self-hosted','macOS','openqms-r5-sandbox']
    command=next(step['run'] for step in job['steps'] if step.get('name','').startswith('Run mandatory R5'))
    assert 'tests.ci.r5_native_gate' in command and '$RUNNER_TEMP/openqms-r5-native-job.json' in command
    assert 'continue-on-error' not in job
    native=_make_dry_run('check-r5-native')
    assert 'r5-api' in native and 'r5-browser' in native
