"""Embedding provider abstraction for semantic search."""
import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key)
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


def create_embedding_provider() -> EmbeddingProvider | None:
    """Factory function. Returns None if no embedding provider is configured."""
    from app.config import settings

    provider_name = settings.EMBEDDING_PROVIDER
    if not provider_name:
        provider_name = settings.LLM_PROVIDER
    if not provider_name:
        return None

    if provider_name == "openai":
        if not settings.LLM_API_KEY:
            logger.warning("EMBEDDING_PROVIDER=openai but LLM_API_KEY not set")
            return None
        model = settings.EMBEDDING_MODEL or "text-embedding-3-small"
        return OpenAIEmbeddingProvider(api_key=settings.LLM_API_KEY, model=model)

    if provider_name == "ollama":
        model = settings.EMBEDDING_MODEL or "nomic-embed-text"
        return OllamaEmbeddingProvider(base_url=settings.EMBEDDING_BASE_URL, model=model)

    logger.warning(f"Unsupported EMBEDDING_PROVIDER: {provider_name}")
    return None
