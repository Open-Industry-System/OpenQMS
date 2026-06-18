"""Tests for LLM provider factory base_url wiring.

OpenAI-compatible endpoints (DeepSeek, Azure OpenAI, OpenRouter, ...) must be
reachable by configuring `llm_base_url`. The `openai` provider honors that
base_url; without it the client falls back to the official OpenAI endpoint.

Regression: OpenAIProvider ignored base_url, so a DeepSeek API key was sent to
api.openai.com and rejected with HTTP 401.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.llm_provider import create_llm_provider


def test_create_llm_provider_wires_llm_base_url_to_openai():
    """A configured LLM_BASE_URL reaches the OpenAI provider's HTTP client."""
    cfg = SimpleNamespace(
        LLM_PROVIDER="openai",
        LLM_API_KEY="sk-test",
        LLM_MODEL="deepseek-chat",
        LLM_BASE_URL="https://api.deepseek.com",
    )
    provider = create_llm_provider(cfg)
    assert provider is not None, "expected an OpenAIProvider, got None"
    assert "deepseek" in str(provider.client.base_url), (
        f"LLM_BASE_URL not wired to the OpenAI client: {provider.client.base_url}"
    )


def test_create_llm_provider_openai_defaults_to_openai_without_base_url():
    """With no LLM_BASE_URL, the openai provider still targets api.openai.com."""
    cfg = SimpleNamespace(
        LLM_PROVIDER="openai",
        LLM_API_KEY="sk-test",
        LLM_MODEL="gpt-4o",
        LLM_BASE_URL="",
    )
    provider = create_llm_provider(cfg)
    assert provider is not None
    assert "openai.com" in str(provider.client.base_url)


async def test_openai_provider_response_format_fallback_parses_fenced_json():
    """When the gateway rejects response_format=json_object, OpenAIProvider
    retries without it and _extract_json parses the fenced ```json response.

    Regression: Volcengine Ark / DeepSeek reject response_format=json_object with
    a 400, and the provider had no fallback path.
    """
    pytest.importorskip("openai")  # skip cleanly when the package is absent
    from app.services.llm_provider import OpenAIProvider, _extract_json

    provider = OpenAIProvider(api_key="sk-test", model="gpt-4o", base_url="")

    fenced_payload = '```json\n{"analysis": "ok", "findings": [], "recommendations": []}\n```'

    # Build a fake chat completion response object with the .choices[0].message.content shape.
    def _fake_choice(content: str):
        msg = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    create = AsyncMock(side_effect=[
        Exception("400 Bad Request: json_object is not supported by this model"),
        _fake_choice(fenced_payload),
    ])
    provider.client.chat.completions.create = create

    result = await provider.complete("ignored", {"type": "object"})

    # Two calls: first (with response_format) raised, second (without) returned.
    assert create.call_count == 2
    first_kwargs = create.call_args_list[0].kwargs
    second_kwargs = create.call_args_list[1].kwargs
    assert first_kwargs.get("response_format") == {"type": "json_object"}
    assert "response_format" not in second_kwargs, "retry must omit response_format"

    # _extract_json must unwrap the ```json fences.
    assert result == _extract_json(fenced_payload)
    assert result["analysis"] == "ok"