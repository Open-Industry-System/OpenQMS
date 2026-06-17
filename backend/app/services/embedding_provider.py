"""Embedding provider abstraction for semantic search."""
import logging
from typing import Protocol

import httpx

from app.config import settings as app_settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small", base_url: str = ""):
        from openai import AsyncOpenAI
        # base_url lets OpenAI-compatible endpoints (an Ollama OpenAI shim, a
        # proxy, etc.) override the default api.openai.com target.
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model
        self._dimensions = 1536

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def aclose(self):
        await self._client.close()


class OllamaEmbeddingProvider:
    def __init__(self, base_url: str = "http://ollama:11434", model: str = "nomic-embed-text"):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)
        dim_map = {"nomic-embed-text": 768, "bge-m3": 1024}
        self._dimensions = dim_map.get(model, 768)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            resp = await self._client.post("/api/embeddings", json={
                "model": self._model,
                "prompt": text,
            })
            resp.raise_for_status()
            results.append(resp.json()["embedding"])
        return results

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def aclose(self):
        await self._client.aclose()


def create_embedding_provider(config=None) -> EmbeddingProvider | None:
    """Factory function. Returns None if no embedding provider is configured.

    `config` may be the global settings object or any object exposing the
    uppercase env attributes (EMBEDDING_PROVIDER, LLM_PROVIDER, LLM_API_KEY,
    EMBEDDING_MODEL, EMBEDDING_BASE_URL).
    """
    cfg = config or app_settings

    provider_name = getattr(cfg, "EMBEDDING_PROVIDER", "") or getattr(cfg, "embedding_provider", "")
    if not provider_name:
        provider_name = getattr(cfg, "LLM_PROVIDER", "") or getattr(cfg, "llm_provider", "")
    if not provider_name:
        return None

    if provider_name == "openai":
        api_key = (
            getattr(cfg, "EMBEDDING_API_KEY", "") or getattr(cfg, "embedding_api_key", "")
            or getattr(cfg, "LLM_API_KEY", "") or getattr(cfg, "llm_api_key", "")
        )
        if not api_key:
            logger.warning("EMBEDDING_PROVIDER=openai but no EMBEDDING_API_KEY or LLM_API_KEY set")
            return None
        model = getattr(cfg, "EMBEDDING_MODEL", "") or getattr(cfg, "embedding_model", "") or "text-embedding-3-small"
        base_url = (
            getattr(cfg, "EMBEDDING_BASE_URL", "") or getattr(cfg, "embedding_base_url", "")
            or getattr(cfg, "LLM_BASE_URL", "") or getattr(cfg, "llm_base_url", "")
        )
        return OpenAIEmbeddingProvider(api_key=api_key, model=model, base_url=base_url)

    if provider_name == "ollama":
        model = getattr(cfg, "EMBEDDING_MODEL", "") or getattr(cfg, "embedding_model", "") or "nomic-embed-text"
        base_url = getattr(cfg, "EMBEDDING_BASE_URL", "") or getattr(cfg, "embedding_base_url", "")
        return OllamaEmbeddingProvider(base_url=base_url, model=model)

    logger.warning(f"Unsupported EMBEDDING_PROVIDER: {provider_name}")
    return None
