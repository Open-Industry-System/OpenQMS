"""Explicit validation for the process that is allowed to access a live provider."""
from __future__ import annotations

from collections.abc import Mapping


_PROVIDER_NAMES = frozenset({'openai', 'deepseek', 'ark', 'anthropic', 'claude', 'local', 'ollama'})
_LOCAL_PROVIDERS = frozenset({'local', 'ollama'})
_LIVE_KEYS = frozenset({'LLM_PROVIDER', 'LLM_API_KEY', 'LLM_MODEL', 'LLM_BASE_URL', 'LLM_TIMEOUT'})


def _required(values: Mapping[str, str], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f'{key} is required for the live acceptance gate')
    return value


def validate_live_configuration(values: Mapping[str, str]) -> dict[str, str]:
    """Return the permitted live-provider values or reject incomplete unsafe input."""
    if 'LLM_TIMEOUT' in values and not isinstance(values['LLM_TIMEOUT'], str):
        raise ValueError('LLM_TIMEOUT must be an integer from 1 through 120')
    result = {key: value for key, value in values.items() if key in _LIVE_KEYS and isinstance(value, str) and value}
    if any('$' in value or '\n' in value or '\r' in value for value in result.values()):
        raise ValueError('live provider configuration may not contain interpolation or line breaks')

    provider = _required(result, 'LLM_PROVIDER').lower()
    if provider not in _PROVIDER_NAMES:
        raise ValueError('live provider is not supported')
    result['LLM_PROVIDER'] = provider
    _required(result, 'LLM_MODEL')
    timeout = result.setdefault('LLM_TIMEOUT', '30')
    if not timeout.isdecimal() or not 1 <= int(timeout) <= 120:
        raise ValueError('LLM_TIMEOUT must be an integer from 1 through 120')

    if provider in _LOCAL_PROVIDERS:
        _required(result, 'LLM_BASE_URL')
    else:
        _required(result, 'LLM_API_KEY')
    return result
