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

    assert command[:4] == ['/test/python', '-m', 'pytest', 'tests/e2e']
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
