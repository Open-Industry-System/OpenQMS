# backend/app/services/llm_provider.py
import json
import logging
from typing import Protocol

from app.config import settings

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 10_240  # 10KB


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
    def __init__(self, api_key: str, model: str):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def complete(self, prompt: str, response_schema: dict) -> dict:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content
        if len(text.encode()) > MAX_RESPONSE_BYTES:
            raise ValueError("LLM response too large")
        return json.loads(text)


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


def create_llm_provider() -> LLMProvider | None:
    """Factory: create provider from env vars. Returns None if not configured."""
    provider_name = settings.LLM_PROVIDER
    if not provider_name:
        return None

    api_key = settings.LLM_API_KEY
    if not api_key and provider_name != "local":
        logger.warning("LLM_PROVIDER=%s requires LLM_API_KEY, falling back to rule-only mode", provider_name)
        return None

    model = settings.LLM_MODEL

    try:
        if provider_name == "claude":
            return ClaudeProvider(api_key=api_key, model=model or "claude-sonnet-4-6-20250514")
        elif provider_name == "openai":
            return OpenAIProvider(api_key=api_key, model=model or "gpt-4o")
        elif provider_name == "local":
            base_url = settings.LLM_BASE_URL
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
