"""No credentials or provider authority may leak into ordinary/browser children."""
from contextlib import asynccontextmanager
import os
from pathlib import Path
import sys

import pytest

from tests.e2e.capa_outcome_runner import provider_environment, child_environment


def test_ordinary_child_rejects_ambient_provider_and_proxy_authority():
    env = child_environment({'PATH': '/safe', 'HOME': '/owned', 'LLM_API_KEY': 'ambient',
        'ANTHROPIC_AUTH_TOKEN': 'ambient', 'HTTPS_PROXY': 'unapproved', 'NODE_OPTIONS': '--require unsafe'})
    assert env == {'PATH': '/safe', 'HOME': '/owned', 'NO_PROXY': '*', 'no_proxy': '*'}


@pytest.mark.parametrize('wheel_mode', ['present', 'missing', 'fakepath'])
def test_sdk_wheel_resource_crosses_only_explicit_pytest_child_environment(tmp_path, wheel_mode):
    from tests.e2e.capa_outcome_runner import run_pytest_layer

    root = Path(__file__).resolve().parents[3]
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    wheel = tmp_path / 'resource.whl'
    if wheel_mode == 'present':
        wheel.write_bytes(b'synthetic resource, not installed')
    source = {'PATH': os.environ['PATH'], 'HOME': str(tmp_path),
              'OPENQMS_SDK_UNRELATED': 'must-not-pass', 'LLM_API_KEY': 'must-not-pass',
              'AWS_SECRET_ACCESS_KEY': 'must-not-pass'}
    if wheel_mode != 'missing':
        source['OPENQMS_SDK_WHEEL'] = str(wheel)
    expected = source.get('OPENQMS_SDK_WHEEL')
    sample = tmp_path / 'test_sdk_resource.py'
    sample.write_text(
        'import os, pytest\n'
        'def test_resource():\n'
        f'    assert os.environ.get("OPENQMS_SDK_WHEEL") == {expected!r}\n'
        '    assert "OPENQMS_SDK_UNRELATED" not in os.environ\n'
        '    assert "AWS_SECRET_ACCESS_KEY" not in os.environ\n'
        '    assert not os.environ.get("LLM_API_KEY")\n'
        + ('    from tests.e2e.sdk_process_support import sdk_runtime\n'
           '    with pytest.raises(AssertionError, match="explicit SDK wheel required"):\n'
           '        next(sdk_runtime.__wrapped__())\n' if wheel_mode != 'present' else '')
    )
    receipt = run_pytest_layer(
        layer='api', targets=[str(sample)], source=source,
        database_url='postgresql+asyncpg://ci:ci@127.0.0.1:1/ci_resource_test',
        artifacts=artifacts, python=sys.executable,
        pytest_entrypoint=(str(root / 'scripts/check-ci-pure.py'),),
    )
    assert receipt['status'] == 'PASSED'
    assert receipt['selected'] == receipt['passed'] == 1
    assert receipt['skipped'] == receipt['xfailed'] == receipt['xpassed'] == 0
    assert 'must-not-pass' not in ''.join(path.read_text() for path in artifacts.iterdir())


@pytest.mark.parametrize('result, expected', [
    ('pass', 'PASSED'), ('skip', 'FAILED'), ('missing', 'FAILED'),
    ('substituted', 'FAILED'), ('duplicate', 'FAILED'),
    ('xfail', 'FAILED'), ('xpass', 'FAILED'), ('ordinary_skip', 'PASSED'),
])
@pytest.mark.parametrize('targets', [('tests',), None])
def test_api_requires_exact_sdk_junit_nodes_but_preserves_ordinary_skips(
    tmp_path, monkeypatch, result, expected, targets,
):
    import json
    from xml.etree import ElementTree as ET
    from tests.ci.gate_results import COUNTS
    from tests.ci.test_layer_selection import SDK_PROCESS_BACKEND_NODES
    from tests.e2e.capa_outcome_runner import DEFAULT_TARGETS, D4_TEXT_PROCESS_NAMES, run_pytest_layer

    cases = ET.Element('testsuite')
    names = [node.split('::')[1] for node in SDK_PROCESS_BACKEND_NODES]
    if result == 'missing':
        names.pop()
    elif result == 'substituted':
        names[-1] = 'test_unrelated_replacement'
    elif result == 'duplicate':
        names[-1] = names[0]
    for name in names:
        ET.SubElement(cases, 'testcase', classname='tests.e2e.test_agent_sdk_process', name=name)
    summary = {key: 0 for key in COUNTS}
    summary.update(selected=len(names), passed=len(names))
    for name in D4_TEXT_PROCESS_NAMES:
        ET.SubElement(cases, 'testcase', classname='tests.e2e.test_d4_text_local_process', name=name)
    summary['selected'] += len(D4_TEXT_PROCESS_NAMES)
    summary['passed'] += len(D4_TEXT_PROCESS_NAMES)
    if result in {'skip', 'xfail'}:
        ET.SubElement(cases[0], 'skipped', type='pytest.xfail' if result == 'xfail' else 'pytest.skip')
        summary['passed'] -= 1
        summary['xfailed' if result == 'xfail' else 'skipped'] = 1
    elif result == 'xpass':
        summary['passed'] -= 1
        summary['xpassed'] = 1
    elif result == 'ordinary_skip':
        ordinary = ET.SubElement(cases, 'testcase', classname='tests.test_legacy', name='test_optional')
        ET.SubElement(ordinary, 'skipped', type='pytest.skip')
        summary['selected'] += 1
        summary['skipped'] = 1

    class CompletedChild:
        stdout = ()

        def __init__(self, command, **kwargs):
            junit = next(arg.split('=', 1)[1] for arg in command if arg.startswith('--junitxml='))
            ET.ElementTree(cases).write(junit)
            Path(kwargs['env']['OPENQMS_GATE_HOOKS']).write_text(json.dumps(summary))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def wait(self):
            return 0

    monkeypatch.setattr('tests.e2e.capa_outcome_runner.subprocess.Popen', CompletedChild)
    receipt = run_pytest_layer(
        layer='api', targets=targets or DEFAULT_TARGETS['api'], source={},
        database_url='postgresql+asyncpg://ci:ci@127.0.0.1:1/ci_test', artifacts=tmp_path,
    )
    assert receipt['status'] == expected


@pytest.mark.parametrize('targets, expected', [
    (['tests'], True), (['tests/e2e'], True),
    (['tests/e2e/test_agent_sdk_process.py'], True),
    (['tests/e2e/test_agent_sdk_process.py::test_installed_sdk_claim_crosses_real_tcp'], True),
    (['tests/ci'], False), (['tests/e2e/test_capa_outcome_runner.py'], False),
])
def test_sdk_mandatory_target_detection(targets, expected):
    from tests.e2e.capa_outcome_runner import _includes_sdk_process

    assert _includes_sdk_process(targets) is expected


@pytest.mark.parametrize('fault', ['empty', 'missing', 'duplicate', 'substituted', 'skip', 'xfail', 'xpass', 'failure', 'error'])
def test_d4_text_required_junit_rejects_missing_or_nonpassing_nodes(tmp_path, fault):
    from xml.etree import ElementTree as ET
    from tests.e2e.capa_outcome_runner import D4_TEXT_PROCESS_NAMES, _require_d4_text_process_success

    suite = ET.Element('testsuite')
    names = sorted(D4_TEXT_PROCESS_NAMES)
    if fault == 'empty':
        names.clear()
    elif fault == 'missing':
        names.pop()
    elif fault == 'duplicate':
        names[-1] = names[0]
    elif fault == 'substituted':
        names[-1] = 'test_unrelated'
    for name in names:
        ET.SubElement(suite, 'testcase', classname='tests.e2e.test_d4_text_local_process', name=name)
    if fault in {'skip', 'xfail'}:
        ET.SubElement(suite[0], 'skipped', type='pytest.xfail' if fault == 'xfail' else 'pytest.skip')
    elif fault in {'failure', 'error'}:
        ET.SubElement(suite[0], fault)
    junit = tmp_path / 'd4.xml'
    ET.ElementTree(suite).write(junit)
    with pytest.raises(ValueError):
        _require_d4_text_process_success(junit, {'xpassed': int(fault == 'xpass')})


def test_d4_text_required_junit_accepts_exact_passing_nodes(tmp_path):
    from xml.etree import ElementTree as ET
    from tests.e2e.capa_outcome_runner import D4_TEXT_PROCESS_NAMES, _require_d4_text_process_success

    suite = ET.Element('testsuite')
    for name in sorted(D4_TEXT_PROCESS_NAMES):
        ET.SubElement(suite, 'testcase', classname='tests.e2e.test_d4_text_local_process', name=name)
    junit = tmp_path / 'd4.xml'
    ET.ElementTree(suite).write(junit)
    _require_d4_text_process_success(junit, {'xpassed': 0})


@pytest.mark.parametrize('targets, expected', [
    (['tests'], True), (['tests/e2e'], True),
    (['tests/e2e/test_d4_text_local_process.py'], True),
    (['tests/e2e/test_d4_text_local_process.py::test_fixed_text_receiver_normal_http'], True),
    (['tests/ci'], False), (['tests/e2e/test_agent_sdk_process.py'], False),
])
def test_d4_text_mandatory_target_detection(targets, expected):
    from tests.e2e.capa_outcome_runner import _includes_d4_text_process
    assert _includes_d4_text_process(targets) is expected


@pytest.mark.parametrize('missing, expected', [(False, 'PASSED'), (True, 'FAILED')])
def test_api_runner_rejects_missing_d4_text_node(tmp_path, monkeypatch, missing, expected):
    import json
    from xml.etree import ElementTree as ET
    from tests.ci.gate_results import COUNTS
    from tests.e2e.capa_outcome_runner import D4_TEXT_PROCESS_NAMES, D4_TEXT_PROCESS_TARGET, run_pytest_layer

    names = sorted(D4_TEXT_PROCESS_NAMES)
    if missing:
        names.pop()
    suite = ET.Element('testsuite')
    for name in names:
        ET.SubElement(suite, 'testcase', classname='tests.e2e.test_d4_text_local_process', name=name)
    summary = {key: 0 for key in COUNTS}
    summary.update(selected=len(names), passed=len(names))

    class Child:
        stdout = ()
        def __init__(self, command, **kwargs):
            junit = next(arg.split('=', 1)[1] for arg in command if arg.startswith('--junitxml='))
            ET.ElementTree(suite).write(junit)
            Path(kwargs['env']['OPENQMS_GATE_HOOKS']).write_text(json.dumps(summary))
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def wait(self): return 0

    monkeypatch.setattr('tests.e2e.capa_outcome_runner.subprocess.Popen', Child)
    receipt = run_pytest_layer(layer='api', targets=[D4_TEXT_PROCESS_TARGET], source={},
        database_url='postgresql+asyncpg://ci:ci@127.0.0.1:1/ci_test', artifacts=tmp_path)
    assert receipt['status'] == expected


def test_focused_api_without_sdk_preserves_legal_skip(tmp_path):
    from tests.e2e.capa_outcome_runner import run_pytest_layer

    root = Path(__file__).resolve().parents[3]
    sample = tmp_path / 'test_optional_backend.py'
    sample.write_text('import pytest\ndef test_optional():\n    pytest.skip("legal legacy skip")\n')
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    receipt = run_pytest_layer(
        layer='api', targets=[str(sample)], source={'PATH': os.environ['PATH']},
        database_url='postgresql+asyncpg://ci_user:synthetic_password@127.0.0.1:1/ci_test',
        artifacts=artifacts, python=sys.executable,
        pytest_entrypoint=(str(root / 'scripts/check-ci-pure.py'),),
    )
    assert receipt['status'] == 'PASSED'
    assert receipt['selected'] == receipt['skipped'] == 1
    assert receipt['passed'] == 0


def test_live_profile_never_expands_or_passes_arbitrary_environment(tmp_path):
    profile = tmp_path / '.env.e2e'
    profile.write_text('LLM_PROVIDER=openai\nLLM_API_KEY=test-secret\nLLM_MODEL=test-model\n'
        'LLM_BASE_URL=https://test.invalid\nLLM_TIMEOUT=30\nDATABASE_URL=do-not-use\n'
        'ANTHROPIC_AUTH_TOKEN=do-not-use\nNODE_OPTIONS=do-not-use\n')
    env, diagnostic = provider_environment(profile)
    assert diagnostic == 'authorized_test_profile'
    assert set(env) == {'LLM_PROVIDER', 'LLM_API_KEY', 'LLM_MODEL', 'LLM_BASE_URL', 'LLM_TIMEOUT'}
    assert env['LLM_API_KEY'] == 'test-secret'
    profile.write_text('LLM_PROVIDER=openai\nLLM_API_KEY=${AMBIENT_SECRET}\n')
    env, diagnostic = provider_environment(profile)
    assert diagnostic == 'invalid_test_profile' and env == {}


def test_missing_profile_is_not_a_skip_or_ambient_fallback(tmp_path):
    env, diagnostic = provider_environment(tmp_path / '.env.e2e')
    assert env == {} and diagnostic == 'missing_test_profile'


def test_live_profile_rejects_invalid_timeout_without_ambient_fallback(tmp_path):
    profile = tmp_path / '.env.e2e'
    profile.write_text('LLM_PROVIDER=openai\nLLM_API_KEY=test-secret\nLLM_TIMEOUT=not-an-integer\n')
    env, diagnostic = provider_environment(profile)
    assert diagnostic == 'invalid_test_profile' and env == {}


@pytest.mark.asyncio
async def test_real_progression_submits_d3_fixture_reference_accepted_by_production_contract(monkeypatch):
    """Catch a fixture reference that omits the URL required by D3 execution."""
    from app.services.capa_d3_containment_service import _validate_evidence_refs
    from tests.e2e import capa_outcome_progression

    class StopAtD3Execution(Exception):
        pass

    class Owned:
        report_id = 'fixture-report'

        @asynccontextmanager
        async def client(self, *_args, **_kwargs):
            yield object()

    async def controlled_business_response(_client, _method, path, payload=None, expected=200):
        if path.endswith('/d3/import'):
            return {'report_status': 'done'}
        if path.endswith('/d3/execution'):
            _validate_evidence_refs(payload['evidence_refs'])
            assert payload['evidence_refs'] == [{
                'name': 'synthetic containment fixture data',
                'url': './fixtures/capa-outcome-containment.txt',
            }]
            raise StopAtD3Execution
        return {}

    monkeypatch.setenv('OPENQMS_OUTCOME_LIVE_TEST', '1')
    monkeypatch.setattr(capa_outcome_progression, 'business_response', controlled_business_response)

    with pytest.raises(StopAtD3Execution):
        await capa_outcome_progression.progress_real_outcome(Owned())


def test_layer_environment_blanks_provider_credentials_for_ordinary_and_browser_children():
    from tests.e2e.capa_outcome_runner import build_layer_environment

    source = {
        'PATH': '/safe', 'HOME': '/owned', 'E2E_MODE': '1',
        'LLM_PROVIDER': 'openai', 'LLM_API_KEY': 'ambient-key', 'LLM_MODEL': 'ambient-model',
        'LLM_BASE_URL': 'https://ambient.invalid', 'LLM_TIMEOUT': '99',
        'OPENAI_API_KEY': 'ambient-openai', 'ANTHROPIC_API_KEY': 'ambient-anthropic',
        'EMBEDDING_API_KEY': 'ambient-embedding',
    }

    for mode in ('api', 'browser'):
        environment = build_layer_environment(source, 'postgresql+asyncpg://test:secret@127.0.0.1:1/qms_test', mode)
        assert 'E2E_MODE' not in environment
        assert environment['OPENQMS_OUTCOME_LIVE_TEST'] == '0'
        assert {key: environment[key] for key in (
            'LLM_PROVIDER', 'LLM_API_KEY', 'LLM_MODEL', 'LLM_BASE_URL',
            'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'EMBEDDING_API_KEY',
        )} == {
            'LLM_PROVIDER': '', 'LLM_API_KEY': '', 'LLM_MODEL': '', 'LLM_BASE_URL': '',
            'OPENAI_API_KEY': '', 'ANTHROPIC_API_KEY': '', 'EMBEDDING_API_KEY': '',
        }
        assert 'LLM_TIMEOUT' not in environment


def test_layer_environment_adds_validated_config_only_to_live_child():
    from tests.e2e.capa_outcome_runner import build_layer_environment

    live = {
        'LLM_PROVIDER': 'openai', 'LLM_API_KEY': 'test-live-key', 'LLM_MODEL': 'test-live-model',
        'LLM_BASE_URL': 'https://provider.invalid/v1', 'LLM_TIMEOUT': '30',
    }
    environment = build_layer_environment({'PATH': '/safe', 'HOME': '/owned', 'E2E_MODE': '1'}, 'postgresql+asyncpg://test:secret@127.0.0.1:1/qms_test', 'live', live)

    assert 'E2E_MODE' not in environment
    assert environment['OPENQMS_OUTCOME_LIVE_TEST'] == '1'
    assert {key: environment[key] for key in live} == live


def test_runner_uses_source_backend_directory_when_packaged_without_repo_root() -> None:
    from tests.e2e.capa_outcome_runner import backend_directory

    assert backend_directory(Path('/app/tests/e2e/capa_outcome_runner.py')) == Path('/app')


def test_layer_environment_retains_only_explicit_ci_ownership_identity() -> None:
    from tests.e2e.capa_outcome_runner import build_layer_environment

    environment = build_layer_environment({
        'PATH': '/safe', 'HOME': '/owned', 'SECRET_KEY': 'test-secret',
        'PG15_CONTAINER': 'owned-pg', 'GITHUB_RUN_ID': '17',
        'GITHUB_RUN_ATTEMPT': '2', 'GITHUB_JOB': 'backend',
        'UNRELATED_AMBIENT_VALUE': 'must-not-pass',
    }, 'postgresql+asyncpg://qms:qms@127.0.0.1:61935/qms_ci_layered_test', 'api')

    assert {key: environment[key] for key in (
        'PG15_CONTAINER', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB',
    )} == {
        'PG15_CONTAINER': 'owned-pg', 'GITHUB_RUN_ID': '17',
        'GITHUB_RUN_ATTEMPT': '2', 'GITHUB_JOB': 'backend',
    }
    assert 'UNRELATED_AMBIENT_VALUE' not in environment


def test_ordinary_layer_removes_provider_timeout_instead_of_setting_invalid_blank() -> None:
    from tests.e2e.capa_outcome_runner import build_layer_environment

    environment = build_layer_environment(
        {'PATH': '/safe', 'HOME': '/owned', 'LLM_TIMEOUT': '60'},
        'postgresql+asyncpg://qms:qms@127.0.0.1:61935/qms_ci_layered_test', 'scanner',
    )

    assert environment['LLM_PROVIDER'] == environment['LLM_API_KEY'] == ''
    assert 'LLM_TIMEOUT' not in environment


def test_scanner_layer_retains_only_its_declared_runtime_inputs() -> None:
    from tests.e2e.capa_outcome_runner import build_layer_environment

    environment = build_layer_environment({
        'PATH': '/safe', 'HOME': '/owned', 'SECRET_KEY': 'test-secret',
        'AGENT_ATTACHMENT_E2E_STORAGE_ROOT': '/owned/storage',
        'AGENT_ATTACHMENT_E2E_CLAMAV_HOST': 'clamav',
        'AGENT_ATTACHMENT_E2E_CLAMAV_PORT': '3310',
        'AGENT_ATTACHMENT_BROWSER_BACKEND': 'http://127.0.0.1:8008',
        'AGENT_ATTACHMENT_BROWSER_NONCE': 'nonce',
        'UNRELATED_AMBIENT_VALUE': 'must-not-pass',
    }, 'postgresql+asyncpg://qms:qms@127.0.0.1:61935/qms_ci_layered_test', 'scanner')

    assert {key: environment[key] for key in (
        'AGENT_ATTACHMENT_E2E_STORAGE_ROOT', 'AGENT_ATTACHMENT_E2E_CLAMAV_HOST',
        'AGENT_ATTACHMENT_E2E_CLAMAV_PORT', 'AGENT_ATTACHMENT_BROWSER_BACKEND',
        'AGENT_ATTACHMENT_BROWSER_NONCE',
    )} == {
        'AGENT_ATTACHMENT_E2E_STORAGE_ROOT': '/owned/storage',
        'AGENT_ATTACHMENT_E2E_CLAMAV_HOST': 'clamav',
        'AGENT_ATTACHMENT_E2E_CLAMAV_PORT': '3310',
        'AGENT_ATTACHMENT_BROWSER_BACKEND': 'http://127.0.0.1:8008',
        'AGENT_ATTACHMENT_BROWSER_NONCE': 'nonce',
    }
    assert 'UNRELATED_AMBIENT_VALUE' not in environment


def test_pytest_command_supports_reusable_marked_target_selection(tmp_path):
    from tests.e2e.capa_outcome_runner import build_pytest_command

    command = build_pytest_command(
        'browser', ['tests/e2e'], tmp_path / 'private.xml', tmp_path / 'hooks.json',
        python='/test/python',
    )

    assert command[:4] == ['/test/python', '-m', 'tests.ci.pytest_bootstrap', 'tests/e2e']
    mark_index = [index for index, value in enumerate(command) if value == '-m'][1]
    assert command[mark_index + 1] == 'ci_browser and not live_provider and not real_scanner'
    assert '-rA' in command
    assert '-p' in command and command[command.index('-p') + 1] == 'tests.ci.gate_results'
    assert f'--junitxml={tmp_path / "private.xml"}' in command


def test_private_result_directory_keeps_raw_junit_outside_uploadable_artifacts(tmp_path):
    from tests.e2e.capa_outcome_runner import private_result_directory

    with private_result_directory() as raw:
        directory = Path(raw)
        assert directory.is_dir()
        assert directory != tmp_path
        assert directory.stat().st_mode & 0o077 == 0


def test_default_provider_preflight_uses_isolated_environment_before_browser_or_tests(monkeypatch):
    from tests.e2e.capa_outcome_runner import preflight_default_provider_settings

    seen = {}

    def no_provider_process(command, **kwargs):
        seen['command'] = command
        seen['environment'] = kwargs['env']
        return type('Completed', (), {'returncode': 0})()

    monkeypatch.setattr('tests.e2e.capa_outcome_runner.subprocess.run', no_provider_process)
    preflight_default_provider_settings({'LLM_PROVIDER': '', 'LLM_API_KEY': '', 'E2E_MODE': ''}, python='/test/python')

    assert seen['command'][:2] == ['/test/python', '-c']
    assert 'bootstrap()' in seen['command'][2]
    assert 'settings.E2E_MODE is False' in seen['command'][2]
    assert seen['environment']['LLM_PROVIDER'] == ''
    assert seen['environment']['LLM_API_KEY'] == ''
    assert 'E2E_MODE' not in seen['environment']


def test_pytest_command_keeps_layer_marker_when_task5_passes_graph_exclusions(tmp_path):
    from tests.e2e.capa_outcome_runner import build_pytest_command

    command = build_pytest_command(
        'api', ['tests'], tmp_path / 'private.xml', tmp_path / 'hooks.json', python='/test/python',
        pytest_args=('--ignore=tests/test_graph_sync_worker.py', '--ignore=tests/test_graph_projection.py'),
    )

    assert '--ignore=tests/test_graph_sync_worker.py' in command
    assert '--ignore=tests/test_graph_projection.py' in command
    mark_index = [index for index, value in enumerate(command) if value == '-m'][1]
    assert command[mark_index + 1] == 'not ci_browser and not live_provider and not real_scanner'


def test_run_pytest_layer_consumes_hook_receipt_and_redacts_full_database_url(tmp_path):
    from tests.e2e.capa_outcome_runner import run_pytest_layer

    root = Path(__file__).resolve().parents[3]
    sample = tmp_path / 'test_guarded_sample.py'
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    database_url = 'postgresql+asyncpg://ci_user:db/password@127.0.0.1:61935/qms_ci_layered_test'
    sample.write_text(
        'def test_guarded_sample():\n'
        f"    print({database_url!r})\n"
        "    print('postgresql+asyncpg://ci_user:db%2Fpassword@127.0.0.1:61935/qms_ci_layered_test')\n"
    )

    receipt = run_pytest_layer(
        layer='api', targets=[str(sample)], source={'PATH': os.environ['PATH'], 'HOME': os.environ['HOME']},
        database_url=database_url, artifacts=artifacts, python=sys.executable,
        pytest_entrypoint=(str(root / 'scripts' / 'check-ci-pure.py'),),
    )

    assert receipt['selected'] == receipt['passed'] == 1
    assert receipt['status'] == 'PASSED'
    public_log = next(artifacts.glob('*.log')).read_text()
    public_receipt = next(artifacts.glob('*-receipt.json')).read_text()
    assert 'db/password' not in public_log + public_receipt
    assert 'db%2Fpassword' not in public_log + public_receipt
    assert not list(artifacts.glob('*.xml'))
    assert not list(artifacts.glob('*.hooks.json'))


@pytest.mark.parametrize('layer', ['api', 'browser', 'scanner', 'live'])
def test_layer_removes_sdk_endpoint_overrides_and_preserves_official_defaults(layer, monkeypatch):
    import asyncio
    from importlib import import_module
    from unittest.mock import patch
    import openai
    import anthropic
    from tests.e2e.capa_outcome_runner import build_layer_environment

    live = {
        'LLM_PROVIDER': 'openai', 'LLM_API_KEY': 'synthetic-live-key',
        'LLM_MODEL': 'synthetic-model', 'LLM_BASE_URL': 'https://live.invalid/v1', 'LLM_TIMEOUT': '30',
    } if layer == 'live' else None
    environment = build_layer_environment({
        'OPENAI_BASE_URL': 'https://ambient-openai.invalid',
        'ANTHROPIC_BASE_URL': 'https://ambient-anthropic.invalid',
    }, 'postgresql+asyncpg://u:p@127.0.0.1:1/qms_test', layer, live)
    assert 'OPENAI_BASE_URL' not in environment
    assert 'ANTHROPIC_BASE_URL' not in environment
    assert environment['LLM_BASE_URL'] == (live['LLM_BASE_URL'] if live else '')

    async def check_clients():
        def reject(request):
            pytest.fail('SDK default URL inspection must never send a request')
        def mock_client(sdk):
            # SDK majors use either httpx or httpx2; never mix their transports.
            client_class = sdk.DefaultAsyncHttpxClient
            http = import_module(client_class.__bases__[0].__module__.split('.')[0])
            return client_class(transport=http.MockTransport(reject))

        async with openai.AsyncOpenAI(
            api_key='synthetic-test-key', http_client=mock_client(openai),
        ) as openai_client, anthropic.AsyncAnthropic(
            api_key='synthetic-test-key', http_client=mock_client(anthropic),
        ) as anthropic_client:
            assert str(openai_client.base_url) == 'https://api.openai.com/v1/'
            assert str(anthropic_client.base_url) == 'https://api.anthropic.com'

    with patch.dict(os.environ, environment, clear=True):
        asyncio.run(check_clients())
