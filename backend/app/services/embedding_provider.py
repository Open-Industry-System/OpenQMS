"""Embedding provider abstraction for semantic search."""
import hashlib
import logging
import math
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


class HashEmbeddingProvider:
    """Deterministic in-process embeddings for E2E / offline.

    Produces fixed-length L2-normalized vectors from text hashes so the
    embedding_sync outbox can complete without an external model, and so the
    reported dimensionality can match the document_embeddings column (default
    1536) without pulling nomic-embed-text (768d).
    """

    def __init__(self, dimensions: int = 1536, model: str = "hash-embedding"):
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._dimensions = dimensions
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        # Expand a SHA-256 stream into `dimensions` floats in [-1, 1], then L2-normalize.
        out: list[float] = []
        counter = 0
        while len(out) < self._dimensions:
            digest = hashlib.sha256(f"{counter}:{text}".encode("utf-8")).digest()
            for i in range(0, len(digest), 4):
                if len(out) >= self._dimensions:
                    break
                # signed 32-bit → [-1, 1]
                n = int.from_bytes(digest[i : i + 4], "big", signed=False)
                out.append((n / 0xFFFFFFFF) * 2.0 - 1.0)
            counter += 1
        norm = math.sqrt(sum(v * v for v in out)) or 1.0
        return [v / norm for v in out]

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def aclose(self):
        return None


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small", base_url: str = "", dimensions: int = 1536):
        from openai import AsyncOpenAI
        # base_url lets OpenAI-compatible endpoints (an Ollama OpenAI shim, a
        # proxy, etc.) override the default api.openai.com target.
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model
        # dimensions is a reported property (used by the vector/storage layer);
        # it must match the model's actual output dimensionality, not be hardcoded.
        self._dimensions = dimensions

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
    def __init__(
        self,
        base_url: str = "http://ollama:11434",
        model: str = "nomic-embed-text",
        dimensions: int | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)
        # Unlike OpenAI, Ollama's /api/embeddings endpoint has no `dimensions`
        # parameter — a model always emits a fixed output dimensionality. dim_map
        # mirrors each model's known output dim so the reported `dimensions`
        # matches what the model actually emits (which is what the pgvector
        # column must match). A configured EMBEDDING_DIMENSIONS that disagrees
        # with the model is a likely misconfiguration and is warned about rather
        # than silently honored — honoring it would report a dimension the model
        # never produces, letting the storage layer's table-vs-provider check
        # pass while upserts still fail.
        dim_map = {"nomic-embed-text": 768, "bge-m3": 1024}
        known_dim = dim_map.get(model, 768)
        if dimensions and dimensions != known_dim:
            logger.warning(
                "EMBEDDING_DIMENSIONS=%s configured for Ollama model '%s', but its "
                "output dimensionality is model-fixed at %s. The configured value "
                "is ignored; the document_embeddings column must match %s.",
                dimensions, model, known_dim, known_dim,
            )
        self._dimensions = known_dim

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

    E2E_MODE: when embedding_provider is unset (or set to hash/e2e/deterministic),
    return HashEmbeddingProvider sized to EMBEDDING_DIMENSIONS so the outbox can
    complete against document_embeddings without an external model. Without this,
    empty embedding_provider falls back to LLM_PROVIDER=ollama → nomic 768d while
    the table is typically 1536d (US-E2E-01.8 BLOCKED).
    """
    cfg = config or app_settings

    def _str_attr(*names: str) -> str:
        for name in names:
            v = getattr(cfg, name, None)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    emb_explicit = _str_attr("EMBEDDING_PROVIDER", "embedding_provider")
    e2e_mode = bool(getattr(app_settings, "E2E_MODE", False))
    dim_cfg = getattr(cfg, "EMBEDDING_DIMENSIONS", 0) or getattr(cfg, "embedding_dimensions", 0)
    dimensions = (
        dim_cfg
        if isinstance(dim_cfg, int) and dim_cfg > 0
        else (getattr(app_settings, "EMBEDDING_DIMENSIONS", 1536) or 1536)
    )

    if emb_explicit in ("hash", "e2e", "deterministic") or (
        e2e_mode and not emb_explicit
    ):
        return HashEmbeddingProvider(dimensions=int(dimensions))

    provider_name = emb_explicit or _str_attr("LLM_PROVIDER", "llm_provider")
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
        return OpenAIEmbeddingProvider(api_key=api_key, model=model, base_url=base_url, dimensions=int(dimensions))

    if provider_name == "ollama":
        model = getattr(cfg, "EMBEDDING_MODEL", "") or getattr(cfg, "embedding_model", "") or "nomic-embed-text"
        base_url = getattr(cfg, "EMBEDDING_BASE_URL", "") or getattr(cfg, "embedding_base_url", "")
        # Guard against a non-int value (e.g. a mocked settings object) leaking
        # through; only an explicit positive int configures the dimension.
        ollama_dims = dim_cfg if isinstance(dim_cfg, int) and dim_cfg > 0 else None
        return OllamaEmbeddingProvider(base_url=base_url, model=model, dimensions=ollama_dims)

    logger.warning(f"Unsupported EMBEDDING_PROVIDER: {provider_name}")
    return None
