"""Tests for LLM provider factory base_url wiring.

OpenAI-compatible endpoints (DeepSeek, Azure OpenAI, OpenRouter, ...) must be
reachable by configuring `llm_base_url`. The `openai` provider honors that
base_url; without it the client falls back to the official OpenAI endpoint.

Regression: OpenAIProvider ignored base_url, so a DeepSeek API key was sent to
api.openai.com and rejected with HTTP 401.
"""
from types import SimpleNamespace

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