from __future__ import annotations

import pytest

from tests.ci.acceptance_config import validate_live_configuration


@pytest.mark.parametrize(
    'values',
    [
        {},
        {'LLM_PROVIDER': 'openai', 'LLM_MODEL': 'test-model', 'LLM_TIMEOUT': '30'},
        {'LLM_PROVIDER': 'local', 'LLM_MODEL': 'test-model', 'LLM_TIMEOUT': '30'},
        {'LLM_PROVIDER': 'openai', 'LLM_API_KEY': 'key', 'LLM_TIMEOUT': '30'},
        {'LLM_PROVIDER': 'openai', 'LLM_API_KEY': 'key', 'LLM_MODEL': 'test-model', 'LLM_TIMEOUT': '0'},
        {'LLM_PROVIDER': 'openai', 'LLM_API_KEY': 'key', 'LLM_MODEL': 'test-model', 'LLM_TIMEOUT': '121'},
        {'LLM_PROVIDER': 'openai', 'LLM_API_KEY': 'key', 'LLM_MODEL': 'test-model', 'LLM_TIMEOUT': 'not-a-number'},
        {'LLM_PROVIDER': 'openai', 'LLM_API_KEY': '${INJECTED}', 'LLM_MODEL': 'test-model', 'LLM_TIMEOUT': '30'},
        {'LLM_PROVIDER': 'openai', 'LLM_API_KEY': 'key\nnext', 'LLM_MODEL': 'test-model', 'LLM_TIMEOUT': '30'},
    ],
)
def test_validate_live_configuration_rejects_missing_or_unsafe_values(values):
    with pytest.raises(ValueError):
        validate_live_configuration(values)


@pytest.mark.parametrize('timeout', ['1', '120'])
def test_validate_live_configuration_accepts_remote_provider_at_timeout_boundaries(timeout):
    values = {
        'LLM_PROVIDER': 'openai',
        'LLM_API_KEY': 'test-api-key',
        'LLM_MODEL': 'test-model',
        'LLM_BASE_URL': 'https://provider.invalid/v1',
        'LLM_TIMEOUT': timeout,
    }

    assert validate_live_configuration(values) == values


def test_validate_live_configuration_accepts_local_provider_only_with_endpoint():
    values = {
        'LLM_PROVIDER': 'local',
        'LLM_MODEL': 'test-model',
        'LLM_BASE_URL': 'http://127.0.0.1:11434/v1',
        'LLM_TIMEOUT': '30',
    }

    assert validate_live_configuration(values) == values


@pytest.mark.parametrize('timeout', [None, '', '1', '120'])
@pytest.mark.parametrize('via_profile', [False, True])
def test_optional_live_timeout_for_environment_and_explicit_fake_profile(tmp_path, timeout, via_profile):
    from tests.e2e.capa_outcome_runner import _live_configuration

    values = {'LLM_PROVIDER': 'openai', 'LLM_MODEL': 'synthetic-model', 'LLM_API_KEY': 'synthetic-key'}
    if timeout is not None:
        values['LLM_TIMEOUT'] = timeout
    profile = None
    if via_profile:
        profile = tmp_path / 'synthetic-provider.txt'
        profile.write_text(''.join(f'{key}={value}\n' for key, value in values.items()))
    configured = _live_configuration({} if via_profile else values, profile)
    assert configured['LLM_TIMEOUT'] == (timeout or '30')


@pytest.mark.parametrize('timeout', [' ', '-1', '1.0', 'NaN', 30])
def test_supplied_malformed_timeout_is_not_treated_as_absent(timeout):
    with pytest.raises(ValueError):
        validate_live_configuration({'LLM_PROVIDER': 'openai', 'LLM_MODEL': 'synthetic-model',
                                     'LLM_API_KEY': 'synthetic-key', 'LLM_TIMEOUT': timeout})
