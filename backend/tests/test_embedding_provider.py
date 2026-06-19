"""测试 EmbeddingProvider 工厂逻辑和向量维度解析（纯逻辑测试）。"""
import pytest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.embedding_provider import create_embedding_provider, OllamaEmbeddingProvider
from app.utils.vector import parse_vector_dimensions


class TestCreateEmbeddingProvider:
    """测试工厂函数。"""

    @patch("app.services.embedding_provider.app_settings")
    def test_returns_none_when_no_provider(self, mock_settings):
        """未配置 provider 时返回 None。"""
        mock_settings.EMBEDDING_PROVIDER = ""
        mock_settings.LLM_PROVIDER = ""
        assert create_embedding_provider() is None

    @patch("app.services.embedding_provider.app_settings")
    def test_returns_ollama_provider(self, mock_settings):
        """配置 ollama 时返回 OllamaEmbeddingProvider。"""
        mock_settings.EMBEDDING_PROVIDER = "ollama"
        mock_settings.EMBEDDING_MODEL = ""
        mock_settings.EMBEDDING_BASE_URL = "http://localhost:11434"
        provider = create_embedding_provider()
        assert isinstance(provider, OllamaEmbeddingProvider)
        assert provider.dimensions == 768  # nomic-embed-text default

    @patch("app.services.embedding_provider.app_settings")
    def test_returns_none_for_unsupported_provider(self, mock_settings):
        """不支持的 provider 返回 None。"""
        mock_settings.EMBEDDING_PROVIDER = "unsupported"
        mock_settings.LLM_API_KEY = ""
        assert create_embedding_provider() is None


class TestOllamaDimensions:
    """测试 Ollama 维度映射。"""

    def test_nomic_embed_text_dimensions(self):
        """nomic-embed-text 默认 768 维。"""
        provider = OllamaEmbeddingProvider(model="nomic-embed-text")
        assert provider.dimensions == 768

    def test_bge_m3_dimensions(self):
        """bge-m3 默认 1024 维。"""
        provider = OllamaEmbeddingProvider(model="bge-m3")
        assert provider.dimensions == 1024

    def test_unknown_model_defaults_to_768(self):
        """未知模型默认 768 维。"""
        provider = OllamaEmbeddingProvider(model="unknown-model")
        assert provider.dimensions == 768


class TestOllamaDimensionsFromConfig:
    """Ollama 维度来自模型固定输出，而非 EMBEDDING_DIMENSIONS。

    回归 / 与 OpenAI 维度测试对称：OpenAI 的 /v1/embeddings 支持 dimensions
    参数，因此配置值即真实值；Ollama 的 /api/embeddings 无该参数，模型输出维度
    固定，配置值只在与模型不一致时告警（告警后仍以模型维度为准，避免向存储层
    谎报一个模型从不产生的维度）。
    """

    def test_config_matches_model_known_dim(self, caplog):
        """配置维度与模型已知维度一致时，照常返回该维度且不告警。"""
        with caplog.at_level("WARNING", logger="app.services.embedding_provider"):
            provider = OllamaEmbeddingProvider(model="nomic-embed-text", dimensions=768)
        assert provider.dimensions == 768
        assert not [r for r in caplog.records if "model-fixed" in r.message]

    def test_config_disagrees_with_model_is_ignored_and_warned(self, caplog):
        """配置维度与模型不符时：以模型维度为准（model-fixed），并告警。"""
        with caplog.at_level("WARNING", logger="app.services.embedding_provider"):
            provider = OllamaEmbeddingProvider(model="nomic-embed-text", dimensions=1024)
        # 模型固定输出 768，配置 1024 被忽略 —— 否则存储层的列/向量会错配
        assert provider.dimensions == 768
        assert any("model-fixed" in r.message for r in caplog.records)

    def test_factory_passes_dimensions_to_ollama(self):
        """工厂应把 EMBEDDING_DIMENSIONS 传给 OllamaEmbeddingProvider。"""
        cfg = SimpleNamespace(
            EMBEDDING_PROVIDER="ollama",
            EMBEDDING_MODEL="nomic-embed-text",
            EMBEDDING_BASE_URL="http://localhost:11434",
            EMBEDDING_DIMENSIONS=1024,
        )
        provider = create_embedding_provider(cfg)
        assert isinstance(provider, OllamaEmbeddingProvider)
        # 配置 1024 与 nomic 的 768 不符 → 模型维度为准
        assert provider.dimensions == 768

    def test_factory_defaults_to_model_known_dim_without_config(self):
        """未配置 EMBEDDING_DIMENSIONS 时使用模型已知维度。"""
        cfg = SimpleNamespace(
            EMBEDDING_PROVIDER="ollama",
            EMBEDDING_MODEL="bge-m3",
            EMBEDDING_BASE_URL="http://localhost:11434",
        )
        provider = create_embedding_provider(cfg)
        assert isinstance(provider, OllamaEmbeddingProvider)
        assert provider.dimensions == 1024


class TestParseVectorDimensions:
    """测试迁移中的维度参数解析（使用与迁移相同的 parse_vector_dimensions 函数）。"""

    def test_valid_dimensions(self):
        """有效维度通过校验。"""
        assert parse_vector_dimensions("768") == 768
        assert parse_vector_dimensions("1024") == 1024
        assert parse_vector_dimensions("1536") == 1536

    def test_none_returns_default(self):
        """None 返回默认值。"""
        assert parse_vector_dimensions(None) == 1536
        assert parse_vector_dimensions(None, default=768) == 768

    def test_empty_string_returns_default(self):
        """空字符串返回默认值。"""
        assert parse_vector_dimensions("") == 1536
        assert parse_vector_dimensions("  ") == 1536

    def test_invalid_string_raises(self):
        """非法字符串直接 raise，不静默回退。"""
        with pytest.raises(ValueError, match="Must be an integer"):
            parse_vector_dimensions("768x")
        with pytest.raises(ValueError, match="Must be an integer"):
            parse_vector_dimensions("abc")

    def test_out_of_range_raises(self):
        """超范围直接 raise。"""
        with pytest.raises(ValueError, match="Must be 1-2000"):
            parse_vector_dimensions("0")
        with pytest.raises(ValueError, match="Must be 1-2000"):
            parse_vector_dimensions("-1")
        with pytest.raises(ValueError, match="Must be 1-2000"):
            parse_vector_dimensions("2001")


class TestEmbeddingBaseUrlAndApiKey:
    """openai embedding provider 应当使用自定义 base_url，并支持独立的 EMBEDDING_API_KEY。

    回归：OpenAIEmbeddingProvider 曾忽略 base_url（始终连 api.openai.com），且只读
    LLM_API_KEY，无法用与 LLM 不同的密钥/端点做 embedding。
    """

    def test_wires_embedding_base_url_to_openai_client(self):
        """配置的 EMBEDDING_BASE_URL 应传到 OpenAI embedding client。"""
        cfg = SimpleNamespace(
            EMBEDDING_PROVIDER="openai",
            EMBEDDING_API_KEY="sk-test",
            EMBEDDING_MODEL="text-embedding-3-small",
            EMBEDDING_BASE_URL="https://api.deepseek.com",
            LLM_PROVIDER="",
            LLM_API_KEY="",
            LLM_BASE_URL="",
        )
        provider = create_embedding_provider(cfg)
        assert provider is not None, "expected an OpenAIEmbeddingProvider, got None"
        assert "deepseek" in str(provider._client.base_url), (
            f"EMBEDDING_BASE_URL not wired: {provider._client.base_url}"
        )

    def test_uses_embedding_api_key_when_set(self):
        """设置了 EMBEDDING_API_KEY 时应优先于 LLM_API_KEY。"""
        cfg = SimpleNamespace(
            EMBEDDING_PROVIDER="openai",
            EMBEDDING_API_KEY="sk-emb",
            EMBEDDING_MODEL="text-embedding-3-small",
            EMBEDDING_BASE_URL="",
            LLM_PROVIDER="openai",
            LLM_API_KEY="sk-llm",
            LLM_BASE_URL="",
        )
        provider = create_embedding_provider(cfg)
        assert provider is not None
        assert provider._client.api_key == "sk-emb", (
            f"expected EMBEDDING_API_KEY to win, got {provider._client.api_key}"
        )

    def test_falls_back_to_llm_api_key(self):
        """未设置 EMBEDDING_API_KEY 时回退到 LLM_API_KEY（跟随 LLM）。"""
        cfg = SimpleNamespace(
            EMBEDDING_PROVIDER="openai",
            EMBEDDING_API_KEY="",
            EMBEDDING_MODEL="text-embedding-3-small",
            EMBEDDING_BASE_URL="",
            LLM_PROVIDER="openai",
            LLM_API_KEY="sk-llm",
            LLM_BASE_URL="",
        )
        provider = create_embedding_provider(cfg)
        assert provider is not None
        assert provider._client.api_key == "sk-llm"

    def test_openai_defaults_to_openai_without_base_url(self):
        """base_url 均为空时仍指向官方 api.openai.com。"""
        cfg = SimpleNamespace(
            EMBEDDING_PROVIDER="openai",
            EMBEDDING_API_KEY="sk-test",
            EMBEDDING_MODEL="text-embedding-3-small",
            EMBEDDING_BASE_URL="",
            LLM_PROVIDER="",
            LLM_API_KEY="",
            LLM_BASE_URL="",
        )
        provider = create_embedding_provider(cfg)
        assert provider is not None
        assert "openai.com" in str(provider._client.base_url)

    def test_openai_dimensions_read_from_config(self):
        """OpenAIEmbeddingProvider 的 dimensions 应取自 EMBEDDING_DIMENSIONS，而非硬编码 1536。"""
        cfg = SimpleNamespace(
            EMBEDDING_PROVIDER="openai",
            EMBEDDING_API_KEY="sk-test",
            EMBEDDING_MODEL="text-embedding-3-small",
            EMBEDDING_BASE_URL="",
            EMBEDDING_DIMENSIONS=768,
            LLM_PROVIDER="",
            LLM_API_KEY="",
            LLM_BASE_URL="",
        )
        provider = create_embedding_provider(cfg)
        assert provider is not None
        assert provider.dimensions == 768, (
            f"expected dimensions=768 from config, got {provider.dimensions}"
        )

    def test_openai_dimensions_defaults_to_1536(self):
        """未配置 EMBEDDING_DIMENSIONS 时默认 1536。"""
        cfg = SimpleNamespace(
            EMBEDDING_PROVIDER="openai",
            EMBEDDING_API_KEY="sk-test",
            EMBEDDING_MODEL="text-embedding-3-small",
            EMBEDDING_BASE_URL="",
            EMBEDDING_DIMENSIONS=0,
            LLM_PROVIDER="",
            LLM_API_KEY="",
            LLM_BASE_URL="",
        )
        provider = create_embedding_provider(cfg)
        assert provider is not None
        assert provider.dimensions == 1536
