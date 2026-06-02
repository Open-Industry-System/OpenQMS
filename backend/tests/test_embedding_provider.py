"""测试 EmbeddingProvider 工厂逻辑和向量维度解析（纯逻辑测试）。"""
import pytest
from unittest.mock import patch

from app.services.embedding_provider import create_embedding_provider, OllamaEmbeddingProvider
from app.utils.vector import parse_vector_dimensions


class TestCreateEmbeddingProvider:
    """测试工厂函数。"""

    @patch("app.config.settings")
    def test_returns_none_when_no_provider(self, mock_settings):
        """未配置 provider 时返回 None。"""
        mock_settings.EMBEDDING_PROVIDER = ""
        mock_settings.LLM_PROVIDER = ""
        assert create_embedding_provider() is None

    @patch("app.config.settings")
    def test_returns_ollama_provider(self, mock_settings):
        """配置 ollama 时返回 OllamaEmbeddingProvider。"""
        mock_settings.EMBEDDING_PROVIDER = "ollama"
        mock_settings.EMBEDDING_MODEL = ""
        mock_settings.EMBEDDING_BASE_URL = "http://localhost:11434"
        provider = create_embedding_provider()
        assert isinstance(provider, OllamaEmbeddingProvider)
        assert provider.dimensions == 768  # nomic-embed-text default

    @patch("app.config.settings")
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
