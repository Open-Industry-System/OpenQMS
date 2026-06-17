# backend/app/services/llm_provider.py
import json
import logging
from typing import Protocol

from app.config import settings as app_settings

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 10_240  # 10KB


def _extract_json(text: str) -> dict:
    """Parse JSON from an LLM response, tolerating ```json code fences.

    Used when a model returns JSON without response_format enforcement (the
    prompt already requests JSON); some models wrap output in fences.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


class LLMProvider(Protocol):
    async def complete(self, prompt: str, response_schema: dict) -> dict: ...


class ClaudeProvider:
    def __init__(self, api_key: str, model: str):
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def complete(self, prompt: str, response_schema: dict) -> dict:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        if len(text.encode()) > MAX_RESPONSE_BYTES:
            raise ValueError("LLM response too large")
        return json.loads(text)


class OpenAIProvider:
    def __init__(self, api_key: str, model: str, base_url: str = ""):
        from openai import AsyncOpenAI
        # base_url lets OpenAI-compatible endpoints (DeepSeek, Azure OpenAI,
        # OpenRouter, ...) override the default api.openai.com target.
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self.model = model

    async def complete(self, prompt: str, response_schema: dict) -> dict:
        messages = [{"role": "user", "content": prompt}]
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            # Some OpenAI-compatible models/gateways (e.g. Volcengine Ark Coding
            # Plan) reject response_format=json_object with a 400 like
            # "json_object is not supported by this model". The prompt already
            # requests JSON, so retry without the parameter.
            if "json_object" in str(e) or "response_format" in str(e):
                logger.info("LLM rejected response_format=json_object, retrying without it: %s", e)
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                )
            else:
                raise
        text = response.choices[0].message.content or ""
        if len(text.encode()) > MAX_RESPONSE_BYTES:
            raise ValueError("LLM response too large")
        return _extract_json(text)


class LocalProvider:
    def __init__(self, base_url: str, model: str):
        import httpx
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30)

    async def aclose(self):
        await self.client.aclose()

    async def complete(self, prompt: str, response_schema: dict) -> dict:
        response = await self.client.post(
            "/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        text = response.json().get("response", "")
        if len(text.encode()) > MAX_RESPONSE_BYTES:
            raise ValueError("LLM response too large")
        return json.loads(text)


def create_llm_provider(config=None) -> LLMProvider | None:
    """Factory: create provider from env vars or an explicit config object.

    `config` should expose the uppercase env attributes: LLM_PROVIDER,
    LLM_API_KEY, LLM_MODEL, LLM_BASE_URL. When omitted, the global app settings
    are used.
    """
    cfg = config or app_settings
    provider_name = getattr(cfg, "LLM_PROVIDER", "") or getattr(cfg, "llm_provider", "")
    if not provider_name:
        return None

    api_key = getattr(cfg, "LLM_API_KEY", "") or getattr(cfg, "llm_api_key", "")
    if not api_key and provider_name != "local":
        logger.warning("LLM_PROVIDER=%s requires LLM_API_KEY, falling back to rule-only mode", provider_name)
        return None

    model = getattr(cfg, "LLM_MODEL", "") or getattr(cfg, "llm_model", "")

    try:
        if provider_name == "claude":
            return ClaudeProvider(api_key=api_key, model=model or "claude-sonnet-4-6-20250514")
        elif provider_name == "openai":
            base_url = getattr(cfg, "LLM_BASE_URL", "") or getattr(cfg, "llm_base_url", "")
            return OpenAIProvider(api_key=api_key, model=model or "gpt-4o", base_url=base_url)
        elif provider_name == "local":
            base_url = getattr(cfg, "LLM_BASE_URL", "") or getattr(cfg, "llm_base_url", "")
            if not base_url:
                logger.warning("LLM_PROVIDER=local requires LLM_BASE_URL, falling back to rule-only mode")
                return None
            if not model:
                logger.warning("LLM_PROVIDER=local requires LLM_MODEL, falling back to rule-only mode")
                return None
            return LocalProvider(base_url=base_url, model=model)
        else:
            logger.warning("Unknown LLM_PROVIDER: %s, falling back to rule-only mode", provider_name)
            return None
    except ImportError as e:
        logger.warning("LLM provider import failed (%s), falling back to rule-only mode: %s", provider_name, e)
        return None
