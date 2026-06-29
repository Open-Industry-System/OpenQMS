"""Provider adapter: extend existing openai/anthropic SDK providers with tool-calling.

No pydantic-ai (conflicts with project's pinned pydantic 2.9.2). Uses the
already-installed openai/anthropic SDK function-calling APIs directly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.ai_config import AIConfigOut
from app.services.ai_config_service import get_raw_ai_config  # raw (unmasked) keys


@dataclass
class ProviderClient:
    provider: str  # "openai" | "anthropic"
    client: Any  # AsyncOpenAI | AsyncAnthropic
    model: str


@dataclass
class AssistantTurn:
    content: str  # assistant text (may be "")
    tool_calls: list[dict]  # [{"name": str, "arguments": dict}]


async def build_client(db: AsyncSession) -> ProviderClient:
    cfg: AIConfigOut = await get_raw_ai_config(db)  # real api key, not masked
    provider = (cfg.llm_provider or "openai").lower()
    if provider in ("anthropic", "claude"):
        from anthropic import AsyncAnthropic

        return ProviderClient(
            provider="anthropic",
            client=AsyncAnthropic(api_key=cfg.llm_api_key),
            model=cfg.llm_model or "claude-sonnet-4-6-20250514",
        )
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
    if pc.provider == "openai":
        resp = await pc.client.chat.completions.create(
            model=pc.model, messages=messages, tools=tools
        )
        msg = resp.choices[0].message
        calls = []
        for tc in msg.tool_calls or []:
            calls.append(
                {
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
            calls.append({"name": block.name, "arguments": block.input})
    return AssistantTurn(content="".join(text_parts), tool_calls=calls)
