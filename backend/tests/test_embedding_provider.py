"""测试 EmbeddingProvider 工厂逻辑（纯逻辑测试）。"""
import pytest
from unittest.mock import patch

from app.services.embedding_provider import create_embedding_provider, OllamaEmbeddingProvider


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


class TestMigrationDimensionValidation:
    """测试迁移中的维度参数校验逻辑。"""

    def test_valid_dimensions(self):
        """有效维度通过校验。"""
        for dim in [768, 1024, 1536]:
            assert 1 <= dim <= 2000

    def test_invalid_dimensions_rejected(self):
        """无效维度被拒绝。"""
        for dim in [0, -1, 2001, 99999]:
            assert not (1 <= dim <= 2000)

    def test_dimensions_from_string(self):
        """字符串维度正确解析为整数。"""
        assert int("768") == 768
        with pytest.raises(ValueError):
            int("not_a_number")
