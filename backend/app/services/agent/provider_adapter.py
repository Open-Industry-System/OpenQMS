"""Provider adapter: extend existing openai/anthropic SDK providers with tool-calling.

No pydantic-ai (conflicts with project's pinned pydantic 2.9.2). Uses the
already-installed openai/anthropic SDK function-calling APIs directly.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.ai_config import AIConfigOut
from app.services.agent.llm_json import MAX_RESPONSE_BYTES, extract_json
from app.services.ai_config_service import get_raw_ai_config  # raw (unmasked) keys

logger = logging.getLogger(__name__)


@dataclass
class ProviderClient:
    provider: str  # "openai" | "anthropic"
    client: Any  # AsyncOpenAI | AsyncAnthropic
    model: str


@dataclass
class AssistantTurn:
    content: str  # assistant text (may be "")
    tool_calls: list[dict]  # [{"name": str, "arguments": dict}]


class ProviderNotConfiguredError(RuntimeError):
    """Raised by build_client when AI config is missing (rule-only mode)."""


async def build_client(db: AsyncSession) -> ProviderClient:
    cfg: AIConfigOut = await get_raw_ai_config(db)
    provider = (cfg.llm_provider or "").lower()
    if not provider:
        raise ProviderNotConfiguredError("LLM_PROVIDER 未配置（纯规则引擎模式）")
    if provider in ("anthropic", "claude"):
        if not cfg.llm_api_key:
            raise ProviderNotConfiguredError("anthropic/claude 需要 LLM_API_KEY")
        from anthropic import AsyncAnthropic
        return ProviderClient(
            provider="anthropic",
            client=AsyncAnthropic(api_key=cfg.llm_api_key),
            model=cfg.llm_model or "claude-sonnet-4-6-20250514",
        )
    if provider == "local":
        if not cfg.llm_base_url:
            raise ProviderNotConfiguredError("local 需要 LLM_BASE_URL")
        if not cfg.llm_model:
            raise ProviderNotConfiguredError("local 需要 LLM_MODEL")
        import httpx
        return ProviderClient(
            provider="local",
            client=httpx.AsyncClient(base_url=cfg.llm_base_url.rstrip("/"), timeout=30),
            model=cfg.llm_model,
        )
    # openai-compatible (openai / deepseek / ark via base_url)
    if not cfg.llm_api_key:
        raise ProviderNotConfiguredError(f"{provider} 需要 LLM_API_KEY")
    from openai import AsyncOpenAI
    return ProviderClient(
        provider="openai",
        client=AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url or None),
        model=cfg.llm_model or "gpt-4o",
    )


def tools_schema_for(pc: ProviderClient, tool_specs) -> list[dict]:
    """Convert ToolSpecs to the SDK-native tool schema shape (openai vs anthropic)."""
    out = []
    for spec in tool_specs:
        if pc.provider == "openai":
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.param_schema,
                    },
                }
            )
        else:
            out.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "input_schema": spec.param_schema,
                }
            )
    return out


async def chat_with_tools(
    pc: ProviderClient, messages: list[dict], tools: list[dict]
) -> AssistantTurn:
    """One LLM turn with function-calling. Returns assistant text + parsed tool_calls.

    Note: anthropic requires a top-level 'system' param rather than a system-role
    message in `messages`; the harness (Task 11) passes system prompt separately
    and this function routes it correctly per provider.
    """
    if pc.provider == "local":
        raise ProviderNotConfiguredError("local provider does not support tool-calling")
    if pc.provider == "openai":
        resp = await pc.client.chat.completions.create(
            model=pc.model, messages=messages, tools=tools
        )
        msg = resp.choices[0].message
        calls = []
        for tc in msg.tool_calls or []:
            calls.append(
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments or "{}"),
                }
            )
        return AssistantTurn(content=msg.content or "", tool_calls=calls)
    # anthropic
    system_text = ""
    convo = []
    for m in messages:
        if m.get("role") == "system":
            system_text += m.get("content", "")
        else:
            convo.append(m)
    resp = await pc.client.messages.create(
        model=pc.model,
        system=system_text or None,
        messages=convo,
        tools=tools,
        max_tokens=1024,
    )
    text_parts, calls = [], []
    for block in resp.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            calls.append({"id": block.id, "name": block.name, "arguments": block.input})
    return AssistantTurn(content="".join(text_parts), tool_calls=calls)


async def complete_json(pc: ProviderClient, prompt: str, response_schema: dict) -> dict:
    """Single-shot JSON LLM call: prompt -> dict. Parity with legacy LLMProvider.complete.

    openai: response_format=json_object, retry without it if the gateway rejects.
    anthropic: messages.create + json.loads.
    Both enforce MAX_RESPONSE_BYTES and use extract_json for fenced JSON.
    local: httpx POST {base_url}/api/generate (mirrors legacy LocalProvider.complete).
    """
    messages = [{"role": "user", "content": prompt}]
    if pc.provider == "openai":
        try:
            resp = await pc.client.chat.completions.create(
                model=pc.model, messages=messages,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            if "json_object" in str(e) or "response_format" in str(e):
                logger.info("LLM rejected response_format=json_object, retrying without: %s", e)
                resp = await pc.client.chat.completions.create(model=pc.model, messages=messages)
            else:
                raise
        text = resp.choices[0].message.content or ""
    elif pc.provider == "local":
        resp = await pc.client.post(
            "/api/generate",
            json={"model": pc.model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")
    else:  # anthropic
        resp = await pc.client.messages.create(
            model=pc.model, messages=messages, max_tokens=1024,
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    if len(text.encode()) > MAX_RESPONSE_BYTES:
        raise ValueError("LLM response too large")
    return extract_json(text)
