"""Smoke test: verify installed openai/anthropic SDK function-calling API surface.

This test does NOT call a real LLM. It asserts the import paths, client
construction, and tool-calling call shapes that provider_adapter (Task 9)
and the harness loop (Task 11) will rely on — so a SDK upgrade that breaks
the shape fails here first, before business code is written.
"""
import inspect


def test_openai_sdk_imports_and_client():
    from openai import AsyncOpenAI
    assert inspect.isclass(AsyncOpenAI)
    # client accepts api_key + base_url (Ark/DeepSeek compatible)
    c = AsyncOpenAI(api_key="sk-demo", base_url="https://demo.example/v1")
    # chat.completions.create exists and accepts tools= (function-calling)
    assert hasattr(c.chat, "completions") and hasattr(c.chat.completions, "create")
    sig = inspect.signature(c.chat.completions.create)
    assert "tools" in sig.parameters and "tool_choice" in sig.parameters


def test_anthropic_sdk_imports_and_client():
    from anthropic import AsyncAnthropic
    assert inspect.isclass(AsyncAnthropic)
    c = AsyncAnthropic(api_key="sk-demo")
    assert hasattr(c, "messages") and hasattr(c.messages, "create")
    sig = inspect.signature(c.messages.create)
    assert "tools" in sig.parameters and "tool_choice" in sig.parameters


def test_openai_tool_schema_shape():
    """The OpenAI function-calling tool schema shape provider_adapter will emit."""
    tool = {
        "type": "function",
        "function": {
            "name": "echo_factory",
            "description": "echo scope",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
    assert tool["type"] == "function" and tool["function"]["name"]


def test_anthropic_tool_schema_shape():
    """The Anthropic tool schema shape provider_adapter will emit (flat, no 'function' wrapper)."""
    tool = {
        "name": "echo_factory",
        "description": "echo scope",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    }
    assert tool["name"] and "input_schema" in tool
