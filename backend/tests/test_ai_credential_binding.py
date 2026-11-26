"""Saved AI credentials keep their effective provider/origin binding."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.system_setting import SystemSetting
from app.schemas.ai_config import AIConfigUpdate
from app.services import ai_config_service, embedding_provider, llm_provider


@pytest.fixture
def saved_config(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setattr(ai_config_service.settings, "E2E_MODE", False)
    environment = AIConfigUpdate().model_dump()
    monkeypatch.setattr(ai_config_service, "_env_default", environment.__getitem__)
    values = {
        "llm_provider": "openai",
        "llm_base_url": "https://model.example/v1",
        "llm_api_key": "synthetic-model-key",
        "embedding_provider": "openai",
        "embedding_base_url": "https://vectors.example/v1",
        "embedding_api_key": "synthetic-vector-key",
    }
    rows = {key: SystemSetting(key=key, value=value) for key, value in values.items()}

    def add(row):
        if isinstance(row, SystemSetting):
            rows[row.key] = row

    db = SimpleNamespace(
        execute=AsyncMock(side_effect=lambda *_: SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: list(rows.values()))
        )),
        add=Mock(side_effect=add),
        commit=AsyncMock(),
    )
    rebuild = AsyncMock(wraps=ai_config_service._rebuild_providers)
    monkeypatch.setattr(ai_config_service, "_rebuild_providers", rebuild)
    return SimpleNamespace(db=db, rows=rows, environment=environment, rebuild=rebuild)


def _update(config, **overrides):
    values = {key: row.value for key, row in config.rows.items()}
    values.update(llm_api_key=ai_config_service.MASKED_VALUE, embedding_api_key="")
    values.update(overrides)
    return AIConfigUpdate(**values)


def _assert_unchanged(config, before):
    assert {key: row.value for key, row in config.rows.items()} == before
    config.db.add.assert_not_called()
    config.db.commit.assert_not_awaited()
    config.rebuild.assert_not_awaited()
    assert config.db.execute.await_count == 1


@pytest.mark.parametrize("model_key_source", ["db", "env"])
@pytest.mark.parametrize("embedding_provider_name", ["openai", " openai ", "\topenai\n", ""])
@pytest.mark.parametrize("cleared_key", ["", None])
async def test_stable_vector_origin_cannot_switch_to_hidden_model_key(
    saved_config, model_key_source, embedding_provider_name, cleared_key
):
    config = saved_config
    if model_key_source == "env":
        config.rows["llm_api_key"].value = ""
        config.environment["llm_api_key"] = "synthetic-env-model-key"
    before = {key: row.value for key, row in config.rows.items()}
    update = _update(config, embedding_provider=embedding_provider_name)
    if cleared_key is None:
        # The public schema rejects null; the service also guards internal
        # callers supplying an unvalidated update instead of treating it as a
        # permission to reuse another hidden credential.
        update = update.model_copy(update={"embedding_api_key": None})

    with pytest.raises(ValueError, match="re-entry"):
        await ai_config_service.update_ai_config(config.db, update, None, SimpleNamespace())

    _assert_unchanged(config, before)


async def test_clearing_vector_key_cannot_activate_unbound_hidden_environment_key(saved_config):
    config = saved_config
    config.environment["embedding_api_key"] = "synthetic-env-vector-key"
    before = {key: row.value for key, row in config.rows.items()}

    with pytest.raises(ValueError, match="re-entry"):
        await ai_config_service.update_ai_config(config.db, _update(config), None, SimpleNamespace())

    _assert_unchanged(config, before)


@pytest.mark.parametrize("model_key_source", ["db", "env"])
async def test_same_origin_model_key_reuse_reaches_embedding_factory(
    saved_config, monkeypatch, model_key_source
):
    config = saved_config
    expected_key = "synthetic-model-key"
    if model_key_source == "env":
        config.rows["llm_api_key"].value = ""
        expected_key = "synthetic-env-model-key"
        config.environment["llm_api_key"] = expected_key
    config.rows["embedding_base_url"].value = "https://MODEL.example:443/embeddings"
    received = []
    monkeypatch.setattr(llm_provider, "create_llm_provider", lambda _: None)
    monkeypatch.setattr(embedding_provider, "OpenAIEmbeddingProvider", lambda **kwargs: received.append(kwargs))

    await ai_config_service.update_ai_config(config.db, _update(config), None, SimpleNamespace())

    config.db.commit.assert_awaited_once()
    config.rebuild.assert_awaited_once()
    assert len(received) == 1
    assert received[0]["api_key"] == expected_key
    assert received[0]["base_url"] == "https://MODEL.example:443/embeddings"


@pytest.mark.parametrize("explicit_field", ["llm_api_key", "embedding_api_key"])
async def test_explicit_key_reentry_allows_stable_cross_origin_vector_service(
    saved_config, monkeypatch, explicit_field
):
    config = saved_config
    received = []
    monkeypatch.setattr(llm_provider, "create_llm_provider", lambda _: None)
    monkeypatch.setattr(embedding_provider, "OpenAIEmbeddingProvider", lambda **kwargs: received.append(kwargs))

    update = _update(config, **{explicit_field: "synthetic-explicit-key"})
    await ai_config_service.update_ai_config(config.db, update, None, SimpleNamespace())

    config.db.commit.assert_awaited_once()
    assert len(received) == 1
    assert received[0]["api_key"] == "synthetic-explicit-key"
    assert received[0]["base_url"] == "https://vectors.example/v1"


async def test_existing_separate_origin_bindings_can_keep_both_saved_keys(saved_config, monkeypatch):
    config = saved_config
    received = []
    monkeypatch.setattr(llm_provider, "create_llm_provider", lambda _: None)
    monkeypatch.setattr(embedding_provider, "OpenAIEmbeddingProvider", lambda **kwargs: received.append(kwargs))

    update = _update(config, embedding_api_key=ai_config_service.MASKED_VALUE)
    await ai_config_service.update_ai_config(config.db, update, None, SimpleNamespace())

    config.db.commit.assert_awaited_once()
    assert received[0]["api_key"] == "synthetic-vector-key"
    assert received[0]["base_url"] == "https://vectors.example/v1"


@pytest.mark.parametrize("provider_name", ["openai", "OPENAI", "deepseek", "ark"])
async def test_sdk_environment_origin_cannot_be_replaced_with_a_fictitious_default_binding(
    saved_config, monkeypatch, provider_name
):
    config = saved_config
    monkeypatch.setenv("OPENAI_BASE_URL", "https://model.example/v1")
    config.rows["llm_provider"].value = provider_name
    config.rows["llm_base_url"].value = ""
    config.rows["embedding_base_url"].value = "https://api.openai.com/v1"
    before = {key: row.value for key, row in config.rows.items()}

    with pytest.raises(ValueError, match="re-entry"):
        await ai_config_service.update_ai_config(config.db, _update(config), None, SimpleNamespace())

    _assert_unchanged(config, before)


@pytest.mark.parametrize("sdk_base_url", [None, "https://model.example/v1"])
async def test_implicit_sdk_origin_allows_same_origin_reuse_and_reaches_actual_sdk(
    saved_config, monkeypatch, sdk_base_url
):
    config = saved_config
    if sdk_base_url is not None:
        monkeypatch.setenv("OPENAI_BASE_URL", sdk_base_url)
    config.rows["llm_base_url"].value = ""
    config.rows["embedding_base_url"].value = ""
    monkeypatch.setattr(llm_provider, "create_llm_provider", lambda _: None)
    state = SimpleNamespace()

    await ai_config_service.update_ai_config(config.db, _update(config), None, state)
    try:
        # Keep the real embedding factory and SDK constructor. No request is
        # made; the pure guard rejects accidental network activity.
        assert str(state.embedding_provider._client.base_url) == (sdk_base_url or "https://api.openai.com/v1") + "/"
        assert state.embedding_provider._client.api_key == "synthetic-model-key"
    finally:
        await state.embedding_provider.aclose()
    config.db.commit.assert_awaited_once()


@pytest.mark.parametrize("explicit_field", ["llm_api_key", "embedding_api_key"])
async def test_sdk_environment_origin_still_allows_explicit_cross_origin_reentry(
    saved_config, monkeypatch, explicit_field
):
    config = saved_config
    monkeypatch.setenv("OPENAI_BASE_URL", "https://model.example/v1")
    config.rows["llm_base_url"].value = ""
    config.rows["embedding_base_url"].value = "https://api.openai.com/v1"
    monkeypatch.setattr(llm_provider, "create_llm_provider", lambda _: None)
    state = SimpleNamespace()

    await ai_config_service.update_ai_config(
        config.db, _update(config, **{explicit_field: "synthetic-explicit-key"}), None, state
    )
    try:
        assert str(state.embedding_provider._client.base_url) == "https://api.openai.com/v1/"
        assert state.embedding_provider._client.api_key == "synthetic-explicit-key"
    finally:
        await state.embedding_provider.aclose()


@pytest.mark.parametrize("provider_name", ["claude", "anthropic", "CLAUDE"])
async def test_anthropic_sdk_and_agent_aliases_use_environment_origin_not_llm_url(
    saved_config, monkeypatch, provider_name
):
    from app.services.agent.provider_adapter import build_client

    config = saved_config
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://anthropic-gateway.example/v1")
    config.rows["llm_provider"].value = provider_name
    config.rows["embedding_provider"].value = "hash"
    state = SimpleNamespace()

    await ai_config_service.update_ai_config(
        config.db, _update(config, llm_base_url="https://ignored.example"), None, state
    )
    agent = await build_client(config.db)
    try:
        assert agent.provider == "anthropic"
        assert str(agent.client.base_url) == "https://anthropic-gateway.example/v1/"
        assert agent.client.api_key == "synthetic-model-key"
        if state.llm_provider is not None:
            assert str(state.llm_provider.client.base_url) == str(agent.client.base_url)
    finally:
        await agent.client.close()
        if state.llm_provider is not None:
            await state.llm_provider.client.close()
    config.db.commit.assert_awaited_once()


@pytest.mark.parametrize("provider_name,environment_key", [
    ("openai", "OPENAI_BASE_URL"), ("claude", "ANTHROPIC_BASE_URL"),
])
async def test_empty_sdk_url_environment_is_rejected_without_inventing_a_default_origin(
    saved_config, monkeypatch, provider_name, environment_key
):
    config = saved_config
    monkeypatch.setenv(environment_key, "")
    config.rows["llm_provider"].value = provider_name
    config.rows["llm_base_url"].value = ""
    before = {key: row.value for key, row in config.rows.items()}

    with pytest.raises(ValueError, match="URL"):
        await ai_config_service.update_ai_config(config.db, _update(config), None, SimpleNamespace())

    _assert_unchanged(config, before)


@pytest.mark.parametrize("vector_url,explicit_key", [
    ("https://vectors.example/v1", None),
    ("https://model.example/v1", None),
    ("https://vectors.example/v1", "synthetic-explicit-key"),
])
async def test_implicit_e2e_hash_does_not_authorize_hidden_key_for_a_new_service(
    saved_config, monkeypatch, vector_url, explicit_key
):
    config = saved_config
    monkeypatch.setattr(ai_config_service.settings, "E2E_MODE", True)
    config.rows["embedding_provider"].value = ""
    config.rows["embedding_api_key"].value = ""
    config.rows["embedding_base_url"].value = vector_url
    before = {key: row.value for key, row in config.rows.items()}
    old_snapshot = ai_config_service._build_snapshot((await ai_config_service.get_raw_ai_config(config.db)).model_dump())
    old_provider = embedding_provider.create_embedding_provider(old_snapshot)
    assert isinstance(old_provider, embedding_provider.HashEmbeddingProvider)
    config.db.execute.reset_mock()
    monkeypatch.setattr(llm_provider, "create_llm_provider", lambda _: None)
    updates = {"embedding_provider": "openai"}
    if explicit_key is not None:
        updates["llm_api_key"] = explicit_key
    update = _update(config, **updates)
    state = SimpleNamespace()

    if vector_url == "https://vectors.example/v1" and explicit_key is None:
        with pytest.raises(ValueError, match="re-entry"):
            await ai_config_service.update_ai_config(config.db, update, None, state)
        _assert_unchanged(config, before)
        return

    await ai_config_service.update_ai_config(config.db, update, None, state)
    try:
        assert str(state.embedding_provider._client.base_url) == vector_url + "/"
        assert state.embedding_provider._client.api_key == (explicit_key or "synthetic-model-key")
    finally:
        await state.embedding_provider.aclose()
    config.db.commit.assert_awaited_once()


@pytest.mark.parametrize("provider_name", ["claude", ""])
async def test_non_openai_consumers_ignore_unused_empty_openai_sdk_url(
    saved_config, monkeypatch, provider_name
):
    config = saved_config
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    config.rows["llm_provider"].value = provider_name
    config.rows["llm_base_url"].value = ""
    config.rows["embedding_provider"].value = "hash"
    config.rows["embedding_base_url"].value = ""
    state = SimpleNamespace()

    await ai_config_service.update_ai_config(config.db, _update(config), None, state)
    try:
        assert isinstance(state.embedding_provider, embedding_provider.HashEmbeddingProvider)
        if provider_name == "claude":
            assert str(state.llm_provider.client.base_url).rstrip("/") == "https://api.anthropic.com"
        else:
            assert state.llm_provider is None
    finally:
        if state.llm_provider is not None:
            await state.llm_provider.client.close()
    config.db.commit.assert_awaited_once()
