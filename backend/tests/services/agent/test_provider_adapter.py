import pytest

from app.services.agent import provider_adapter
from app.services.agent.provider_adapter import (
    ProviderClient,
    ProviderNotConfiguredError,
    complete_json,
    tools_schema_for,
)


@pytest.mark.asyncio
async def test_build_client_returns_provider_client(monkeypatch):
    from app.schemas.ai_config import AIConfigOut

    async def _cfg(db):
        return AIConfigOut(llm_provider="openai", llm_api_key="sk-x", llm_model="gpt-4o-mini",
                           llm_base_url="https://demo/v1", llm_timeout=30, capa_draft_llm_timeout=15,
                           report_llm_timeout=10, embedding_provider="", embedding_api_key="",
                           embedding_model="", embedding_base_url="", embedding_dimensions=1536,
                           search_vector_weight=0.7, search_fulltext_weight=0.3)

    monkeypatch.setattr(provider_adapter, "get_raw_ai_config", _cfg)
    pc = await provider_adapter.build_client(object())
    assert pc.provider in ("openai", "anthropic")
    assert pc.client is not None
    assert pc.model  # non-empty model name


def test_tools_schema_shape_openai():
    from types import SimpleNamespace

    spec = SimpleNamespace(
        name="echo_factory",
        description="d",
        param_schema={"type": "object", "properties": {}},
    )
    pc = ProviderClient(provider="openai", client=None, model="m")
    schema = tools_schema_for(pc, [spec])
    assert schema[0]["type"] == "function"
    assert schema[0]["function"]["name"] == "echo_factory"


def test_tools_schema_shape_anthropic():
    from types import SimpleNamespace

    spec = SimpleNamespace(
        name="echo_factory",
        description="d",
        param_schema={"type": "object", "properties": {}},
    )
    pc = ProviderClient(provider="anthropic", client=None, model="m")
    schema = tools_schema_for(pc, [spec])
    assert schema[0]["name"] == "echo_factory"
    assert "input_schema" in schema[0]


def test_extract_json_strips_code_fence():
    from app.services.agent.llm_json import extract_json
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('{"b": 2}') == {"b": 2}


def test_extract_json_tolerates_prose_wrapper():
    """Small models often wrap JSON in prose; US-E2E-01.9 failed on bare prose."""
    from app.services.agent.llm_json import extract_json

    assert extract_json('Here is the result:\n{"ok": true}\nThanks') == {"ok": True}
    assert extract_json("suggestions: [1, 2]") == [1, 2]


@pytest.mark.asyncio
async def test_complete_json_openai_success(monkeypatch):
    pc = ProviderClient(provider="openai", client=object(), model="m")

    class _Msg:
        content = '{"summary": "ok", "evidence_refs": []}'

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})]

    async def _create(**kwargs):
        assert kwargs.get("response_format") == {"type": "json_object"}
        return _Resp()

    pc.client = type("C", (), {"chat": type("CH", (), {"completions": type("CM", (), {"create": _create})})})()
    out = await complete_json(pc, "prompt", {"type": "object"})
    assert out == {"summary": "ok", "evidence_refs": []}


@pytest.mark.asyncio
async def test_complete_json_openai_retries_without_response_format(monkeypatch):
    pc = ProviderClient(provider="openai", client=object(), model="m")
    calls = []

    class _Msg:
        content = '{"x": 1}'

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})]

    async def _create(**kwargs):
        calls.append(kwargs.get("response_format"))
        if kwargs.get("response_format") and len(calls) == 1:
            raise RuntimeError("json_object is not supported by this model")
        return _Resp()

    pc.client = type("C", (), {"chat": type("CH", (), {"completions": type("CM", (), {"create": _create})})})()
    out = await complete_json(pc, "p", {})
    assert out == {"x": 1}
    assert calls[0] == {"type": "json_object"}
    assert calls[1] is None  # retry without response_format


@pytest.mark.asyncio
async def test_complete_json_openai_oversize_raises():
    pc = ProviderClient(provider="openai", client=object(), model="m")
    big = '{"x": "' + "a" * 11_000 + '"}'

    class _Msg:
        content = big

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})]

    async def _create(**kwargs):
        return _Resp()

    pc.client = type("C", (), {"chat": type("CH", (), {"completions": type("CM", (), {"create": _create})})})()
    with pytest.raises(ValueError):
        await complete_json(pc, "p", {})


@pytest.mark.asyncio
async def test_complete_json_anthropic_success():
    pc = ProviderClient(provider="anthropic", client=object(), model="m")

    class _Block:
        type = "text"
        text = '{"y": 2}'

    class _Resp:
        content = [_Block()]

    async def _create(**kwargs):
        assert kwargs.get("max_tokens")
        return _Resp()

    pc.client = type("C", (), {"messages": type("M", (), {"create": _create})})()
    out = await complete_json(pc, "p", {})
    assert out == {"y": 2}


@pytest.mark.asyncio
async def test_build_client_raises_when_unconfigured(monkeypatch):
    """Empty provider/api_key (non-local) -> ProviderNotConfiguredError. Mirrors
    legacy create_llm_provider returning None for rule-only mode."""
    from app.schemas.ai_config import AIConfigOut

    async def _empty_cfg(db):
        return AIConfigOut(llm_provider="", llm_api_key="", llm_model="",
                           llm_base_url="", llm_timeout=30, capa_draft_llm_timeout=15,
                           report_llm_timeout=10, embedding_provider="", embedding_api_key="",
                           embedding_model="", embedding_base_url="", embedding_dimensions=1536,
                           search_vector_weight=0.7, search_fulltext_weight=0.3)

    monkeypatch.setattr(provider_adapter, "get_raw_ai_config", _empty_cfg)
    with pytest.raises(ProviderNotConfiguredError):
        await provider_adapter.build_client(object())


@pytest.mark.asyncio
async def test_build_client_openai_empty_model_uses_default(monkeypatch):
    """claude/openai with empty model does NOT raise — uses provider default."""
    from app.schemas.ai_config import AIConfigOut

    async def _cfg(db):
        return AIConfigOut(llm_provider="openai", llm_api_key="sk-x", llm_model="",
                           llm_base_url="", llm_timeout=30, capa_draft_llm_timeout=15,
                           report_llm_timeout=10, embedding_provider="", embedding_api_key="",
                           embedding_model="", embedding_base_url="", embedding_dimensions=1536,
                           search_vector_weight=0.7, search_fulltext_weight=0.3)

    monkeypatch.setattr(provider_adapter, "get_raw_ai_config", _cfg)
    pc = await provider_adapter.build_client(object())
    assert pc.model == "gpt-4o"
    assert pc.provider == "openai"


@pytest.mark.asyncio
async def test_chat_with_tools_rejects_local_provider():
    """local provider has no tool-calling API; chat_with_tools must raise, not
    silently fall through to the anthropic branch and AttributeError."""
    pc = ProviderClient(provider="local", client=object(), model="m")
    with pytest.raises(ProviderNotConfiguredError):
        await provider_adapter.chat_with_tools(pc, [{"role": "user", "content": "x"}], [])


@pytest.mark.asyncio
async def test_build_client_raises_when_anthropic_api_key_empty(monkeypatch):
    """anthropic/claude provider without api_key -> ProviderNotConfiguredError.
    Mirrors legacy create_llm_provider returning None for that case."""
    from app.schemas.ai_config import AIConfigOut

    async def _cfg(db):
        return AIConfigOut(llm_provider="anthropic", llm_api_key="", llm_model="",
                           llm_base_url="", llm_timeout=30, capa_draft_llm_timeout=15,
                           report_llm_timeout=10, embedding_provider="", embedding_api_key="",
                           embedding_model="", embedding_base_url="", embedding_dimensions=1536,
                           search_vector_weight=0.7, search_fulltext_weight=0.3)

    monkeypatch.setattr(provider_adapter, "get_raw_ai_config", _cfg)
    with pytest.raises(ProviderNotConfiguredError):
        await provider_adapter.build_client(object())


@pytest.mark.asyncio
async def test_build_client_raises_when_local_base_url_empty(monkeypatch):
    """local provider without base_url -> ProviderNotConfiguredError."""
    from app.schemas.ai_config import AIConfigOut

    async def _cfg(db):
        return AIConfigOut(llm_provider="local", llm_api_key="", llm_model="some-model",
                           llm_base_url="", llm_timeout=30, capa_draft_llm_timeout=15,
                           report_llm_timeout=10, embedding_provider="", embedding_api_key="",
                           embedding_model="", embedding_base_url="", embedding_dimensions=1536,
                           search_vector_weight=0.7, search_fulltext_weight=0.3)

    monkeypatch.setattr(provider_adapter, "get_raw_ai_config", _cfg)
    with pytest.raises(ProviderNotConfiguredError):
        await provider_adapter.build_client(object())


@pytest.mark.asyncio
async def test_build_client_raises_when_local_model_empty(monkeypatch):
    """local provider without model -> ProviderNotConfiguredError (local requires
    explicit model; only claude/openai default the model)."""
    from app.schemas.ai_config import AIConfigOut

    async def _cfg(db):
        return AIConfigOut(llm_provider="local", llm_api_key="", llm_model="",
                           llm_base_url="http://localhost:11434", llm_timeout=30,
                           capa_draft_llm_timeout=15, report_llm_timeout=10,
                           embedding_provider="", embedding_api_key="",
                           embedding_model="", embedding_base_url="", embedding_dimensions=1536,
                           search_vector_weight=0.7, search_fulltext_weight=0.3)

    monkeypatch.setattr(provider_adapter, "get_raw_ai_config", _cfg)
    with pytest.raises(ProviderNotConfiguredError):
        await provider_adapter.build_client(object())


@pytest.mark.asyncio
async def test_build_client_raises_when_unknown_provider(monkeypatch):
    """Unknown provider (e.g. typo 'opneai') -> ProviderNotConfiguredError. Mirrors
    legacy create_llm_provider returning None for unknown providers."""
    from app.schemas.ai_config import AIConfigOut

    async def _cfg(db):
        return AIConfigOut(llm_provider="opneai", llm_api_key="sk-x", llm_model="",
                           llm_base_url="", llm_timeout=30, capa_draft_llm_timeout=15,
                           report_llm_timeout=10, embedding_provider="", embedding_api_key="",
                           embedding_model="", embedding_base_url="", embedding_dimensions=1536,
                           search_vector_weight=0.7, search_fulltext_weight=0.3)

    monkeypatch.setattr(provider_adapter, "get_raw_ai_config", _cfg)
    with pytest.raises(ProviderNotConfiguredError):
        await provider_adapter.build_client(object())


@pytest.mark.asyncio
async def test_build_client_local_returns_base_url_and_no_client(monkeypatch):
    """local provider must not hold a long-lived httpx client; base_url is the sentinel."""
    from app.schemas.ai_config import AIConfigOut

    async def _cfg(db):
        return AIConfigOut(llm_provider="local", llm_api_key="", llm_model="llama3",
                           llm_base_url="http://localhost:11434/", llm_timeout=30,
                           capa_draft_llm_timeout=15, report_llm_timeout=10,
                           embedding_provider="", embedding_api_key="",
                           embedding_model="", embedding_base_url="", embedding_dimensions=1536,
                           search_vector_weight=0.7, search_fulltext_weight=0.3)

    monkeypatch.setattr(provider_adapter, "get_raw_ai_config", _cfg)
    pc = await provider_adapter.build_client(object())
    assert pc.provider == "local"
    assert pc.client is None
    assert pc.base_url == "http://localhost:11434"
    assert pc.model == "llama3"


@pytest.mark.asyncio
async def test_build_client_ollama_aliases_local(monkeypatch):
    """ollama provider is recognized and routed through the local (/api/generate) path,
    so .env.e2e's LLM_PROVIDER=ollama no longer falls through to '未知 provider'."""
    from app.schemas.ai_config import AIConfigOut

    async def _cfg(db):
        return AIConfigOut(llm_provider="ollama", llm_api_key="ollama", llm_model="kimi-k2",
                           llm_base_url="http://127.0.0.1:11434", llm_timeout=30,
                           capa_draft_llm_timeout=15, report_llm_timeout=10,
                           embedding_provider="", embedding_api_key="",
                           embedding_model="", embedding_base_url="", embedding_dimensions=1536,
                           search_vector_weight=0.7, search_fulltext_weight=0.3)

    monkeypatch.setattr(provider_adapter, "get_raw_ai_config", _cfg)
    pc = await provider_adapter.build_client(object())
    assert pc.provider == "local"
    assert pc.client is None
    assert pc.base_url == "http://127.0.0.1:11434"
    assert pc.model == "kimi-k2"


@pytest.mark.asyncio
async def test_complete_json_local_success(monkeypatch):
    from unittest.mock import AsyncMock

    pc = ProviderClient(provider="local", client=None, model="llama3", base_url="http://localhost:11434")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=type("R", (), {
        "raise_for_status": lambda self: None,
        "json": lambda self: {"response": '{"z": 3}'},
    })())

    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)

    out = await complete_json(pc, "prompt", {"type": "object"})
    assert out == {"z": 3}
    mock_client.post.assert_awaited_once_with(
        "/api/generate",
        json={
            "model": "llama3",
            "prompt": "prompt",
            "stream": False,
            "format": "json",
        },
    )
