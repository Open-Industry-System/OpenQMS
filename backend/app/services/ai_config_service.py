"""Runtime AI configuration service.

Reads/writes AI provider settings from the `system_settings` table. Falls back to
environment variables when no database value exists. After an update it recreates
the global LLM and embedding provider instances so changes take effect immediately.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.system_setting import SystemSetting
from app.schemas.ai_config import AIConfigOut, AIConfigUpdate

logger = logging.getLogger(__name__)

# Keys persisted in system_settings. Order is irrelevant but kept explicit.
AI_CONFIG_KEYS = [
    "llm_provider",
    "llm_api_key",
    "llm_model",
    "llm_base_url",
    "llm_timeout",
    "capa_draft_llm_timeout",
    "report_llm_timeout",
    "embedding_provider",
    "embedding_model",
    "embedding_base_url",
    "embedding_dimensions",
    "search_vector_weight",
    "search_fulltext_weight",
]

# Sentinel used in GET responses to mask a stored API key.
MASKED_VALUE = "********"


def _coerce(key: str, raw: str | None) -> Any:
    """Convert a stored string value back to the correct Python type."""
    if raw is None:
        return None
    if key in {
        "llm_timeout",
        "capa_draft_llm_timeout",
        "report_llm_timeout",
        "embedding_dimensions",
    }:
        try:
            return int(raw)
        except ValueError:
            return None
    if key in {"search_vector_weight", "search_fulltext_weight"}:
        try:
            return float(raw)
        except ValueError:
            return None
    return raw


def _env_default(key: str) -> Any:
    """Return the current env-backed default for a config key."""
    return getattr(settings, key.upper(), "")


async def get_ai_config(db: AsyncSession) -> AIConfigOut:
    """Load AI config from DB, falling back to env defaults."""
    result = await db.execute(select(SystemSetting).where(SystemSetting.key.in_(AI_CONFIG_KEYS)))
    rows = {row.key: row.value for row in result.scalars().all()}

    values: dict[str, Any] = {}
    for key in AI_CONFIG_KEYS:
        raw = rows.get(key)
        coerced = _coerce(key, raw)
        if coerced is None or coerced == "":
            coerced = _env_default(key)
        values[key] = coerced

    # Never expose the real API key to the frontend.
    if values.get("llm_api_key"):
        values["llm_api_key"] = MASKED_VALUE

    return AIConfigOut(**values)


async def update_ai_config(
    db: AsyncSession,
    update: AIConfigUpdate,
    user_id: Any,
    app_state: Any,
) -> AIConfigOut:
    """Persist updated AI config and recreate providers."""
    # Read current DB values so we can keep the existing API key if masked.
    result = await db.execute(select(SystemSetting).where(SystemSetting.key.in_(AI_CONFIG_KEYS)))
    existing = {row.key: row for row in result.scalars().all()}

    payload = update.model_dump()
    for key in AI_CONFIG_KEYS:
        value = payload.get(key)

        # Keep existing API key when UI sends the masked sentinel.
        if key == "llm_api_key" and value == MASKED_VALUE:
            continue

        str_value = "" if value is None else str(value)
        row = existing.get(key)
        if row is None:
            row = SystemSetting(
                key=key,
                value=str_value,
                description=f"AI / LLM configuration: {key}",
            )
            db.add(row)
        else:
            row.value = str_value
        row.updated_by = user_id

    await db.commit()

    # Re-hydrate providers with the merged configuration.
    await _rebuild_providers(db, app_state)

    return await get_ai_config(db)


def _build_snapshot(values: dict[str, Any]) -> Any:
    """Build a mutable settings-like namespace from lowercase config keys.

    A plain SimpleNamespace is used instead of deepcopy(settings) because
    pydantic BaseSettings instances do not reliably accept runtime attribute
    assignment, which silently left provider fields empty.
    """
    base = settings.model_dump()
    snapshot = SimpleNamespace(**base)
    for key, value in values.items():
        setattr(snapshot, key.upper(), value)
    return snapshot


async def _rebuild_providers(db: AsyncSession, app_state: Any) -> None:
    """Recreate LLM and embedding providers from the latest settings."""
    config = await get_ai_config(db)
    snapshot = _build_snapshot(config.model_dump())

    # Close existing providers gracefully.
    old_llm = getattr(app_state, "llm_provider", None)
    old_emb = getattr(app_state, "embedding_provider", None)
    if old_llm and hasattr(old_llm, "aclose"):
        try:
            await old_llm.aclose()
        except Exception as e:
            logger.warning("Error closing old LLM provider: %s", e)
    if old_emb and hasattr(old_emb, "aclose"):
        try:
            await old_emb.aclose()
        except Exception as e:
            logger.warning("Error closing old embedding provider: %s", e)

    # Recreate.
    from app.services.llm_provider import create_llm_provider
    from app.services.embedding_provider import create_embedding_provider

    try:
        app_state.llm_provider = create_llm_provider(snapshot)
    except Exception as e:
        logger.warning("Failed to recreate LLM provider: %s", e)
        app_state.llm_provider = None

    try:
        app_state.embedding_provider = create_embedding_provider(snapshot)
    except Exception as e:
        logger.warning("Failed to recreate embedding provider: %s", e)
        app_state.embedding_provider = None


@dataclass
class ProviderTestResult:
    ok: bool
    latency_ms: int | None = None
    detail: str | None = None


@dataclass
class AIConfigTestResult:
    llm: ProviderTestResult
    embedding: ProviderTestResult


async def _build_effective_snapshot(
    db: AsyncSession, update: AIConfigUpdate
) -> Any:
    """Merge submitted values with stored/env values, resolving the masked API key."""
    result = await db.execute(select(SystemSetting).where(SystemSetting.key.in_(AI_CONFIG_KEYS)))
    rows = {row.key: row.value for row in result.scalars().all()}

    effective: dict[str, Any] = {}
    payload = update.model_dump()
    for key in AI_CONFIG_KEYS:
        submitted = payload.get(key)
        if key == "llm_api_key" and submitted == MASKED_VALUE:
            # Keep the stored key (or env default).
            stored = _coerce(key, rows.get(key))
            effective[key] = stored if stored not in (None, "") else _env_default(key)
            continue
        if submitted in (None, ""):
            stored = _coerce(key, rows.get(key))
            effective[key] = stored if stored not in (None, "") else _env_default(key)
        else:
            effective[key] = submitted

    return _build_snapshot(effective)


async def test_ai_config(
    db: AsyncSession, update: AIConfigUpdate
) -> AIConfigTestResult:
    """Build temporary providers from the submitted config and probe them.

    Nothing is persisted. Returns per-provider ok/latency/error.
    """
    from app.services.llm_provider import create_llm_provider
    from app.services.embedding_provider import create_embedding_provider

    snapshot = await _build_effective_snapshot(db, update)
    timeout = int(getattr(snapshot, "LLM_TIMEOUT", 5) or 5)

    llm_result = ProviderTestResult(ok=False)
    provider = None
    try:
        provider = create_llm_provider(snapshot)
        if provider is None:
            llm_result = ProviderTestResult(
                ok=False,
                detail="未配置 LLM Provider（纯规则引擎模式，无需测试）",
            )
        else:
            start = time.perf_counter()
            await asyncio.wait_for(
                provider.complete(
                    'Reply with only the JSON object: {"ok": true}',
                    {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                ),
                timeout=timeout,
            )
            llm_result = ProviderTestResult(
                ok=True,
                latency_ms=int((time.perf_counter() - start) * 1000),
                detail="LLM 调用成功",
            )
    except asyncio.TimeoutError:
        llm_result = ProviderTestResult(ok=False, detail=f"请求超时（{timeout}秒）")
    except Exception as e:
        llm_result = ProviderTestResult(ok=False, detail=f"{type(e).__name__}: {e}")
    finally:
        if provider and hasattr(provider, "aclose"):
            try:
                await provider.aclose()
            except Exception:
                pass

    emb_result = ProviderTestResult(ok=False)
    provider = None
    try:
        provider = create_embedding_provider(snapshot)
        if provider is None:
            emb_result = ProviderTestResult(
                ok=False,
                detail="未配置 Embedding Provider",
            )
        else:
            start = time.perf_counter()
            vectors = await asyncio.wait_for(provider.embed(["test"]), timeout=timeout)
            dims = len(vectors[0]) if vectors and vectors[0] else 0
            emb_result = ProviderTestResult(
                ok=True,
                latency_ms=int((time.perf_counter() - start) * 1000),
                detail=f"向量维度 {dims}",
            )
    except asyncio.TimeoutError:
        emb_result = ProviderTestResult(ok=False, detail=f"请求超时（{timeout}秒）")
    except Exception as e:
        emb_result = ProviderTestResult(ok=False, detail=f"{type(e).__name__}: {e}")
    finally:
        if provider and hasattr(provider, "aclose"):
            try:
                await provider.aclose()
            except Exception:
                pass

    return AIConfigTestResult(llm=llm_result, embedding=emb_result)
