"""Responses interoperability: exact stateless replay and retained Chat behavior."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.agent import provider_adapter as adapter


TOOLS = [{"type": "function", "function": {
    "name": "read_d4", "description": "Read evidence",
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}}]
ITEMS = [
    {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "opaque-private-sentinel"},
    {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
     "phase": "commentary", "content": [{"type": "output_text", "text": "Reading evidence", "annotations": []}]},
    {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "read_d4",
     "arguments": "{}", "status": "completed"},
]


def client(items=None, status="completed"):
    sdk = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(
        status=status, output=deepcopy(ITEMS if items is None else items)))))
    return adapter.ProviderClient("openai_responses", sdk, "gpt-6.1-terra")


@pytest.mark.asyncio
async def test_responses_request_is_explicit_stateless_and_preserves_tool_schema():
    pc = client()
    turn = await adapter.chat_with_tools(pc, [{"role": "system", "content": "Authorized context only"}], TOOLS)
    request = pc.client.responses.create.await_args.kwargs
    assert request["model"] == "gpt-6.1-terra"
    assert request["store"] is False
    assert request["include"] == ["reasoning.encrypted_content"]
    assert request["reasoning"]["effort"] == "medium"
    assert request["text"]["verbosity"] == "medium"
    assert "previous_response_id" not in request and "max_output_tokens" not in request
    assert request["tools"] == [{"type": "function", **TOOLS[0]["function"], "strict": False}]
    assert turn.content == "Reading evidence"
    assert turn.tool_calls == [{"id": "call_1", "name": "read_d4", "arguments": {}}]
    assert turn.response_items == ITEMS
    assert "opaque-private-sentinel" not in repr(turn)


@pytest.mark.asyncio
async def test_complete_typed_history_replays_before_call_outputs_and_following_user():
    pc = client()
    first = await adapter.chat_with_tools(pc, [{"role": "user", "content": "Start"}], TOOLS)
    history = [{"role": "system", "content": "Authorized context only"},
               {"role": "user", "content": "Start"},
               {"role": "assistant", "content": first.content, "_responses_output": first.response_items},
               {"role": "tool", "tool_call_id": "call_1", "content": '{"root":"synthetic"}'},
               {"role": "user", "content": "Continue with no additional sources"}]
    before = deepcopy(history)
    await adapter.chat_with_tools(pc, history, TOOLS)
    actual = pc.client.responses.create.await_args.kwargs["input"]
    assert actual[:2] == history[:2]
    assert actual[2:5] == ITEMS
    assert actual[5] == {"type": "function_call_output", "call_id": "call_1", "output": '{"root":"synthetic"}'}
    assert actual[6] == history[-1]
    assert history == before


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled", "in_progress"])
async def test_nonterminal_or_failed_response_cannot_become_a_successful_turn(status):
    with pytest.raises(ValueError):
        await adapter.chat_with_tools(client(status=status), [{"role": "user", "content": "Start"}], TOOLS)


@pytest.mark.asyncio
@pytest.mark.parametrize("items", [
    [{"type": "web_search_call", "id": "unexpected-hosted-tool"}],
    [{"type": "function_call", "call_id": "call_1", "name": "read_d4", "arguments": "not-json"}],
    [{"type": "function_call", "call_id": "call_1", "name": "read_d4", "arguments": "[]"}],
    [{"type": "function_call", "call_id": "call_1", "name": "arbitrary_tool", "arguments": "{}"}],
    [ITEMS[-1], ITEMS[-1]],
    [{"type": "reasoning", "id": "rs_missing", "summary": []}],
    [{"type": "reasoning", "id": "rs_big", "summary": [], "encrypted_content": "x" * 300_000}],
])
async def test_malformed_unknown_or_unbounded_provider_output_fails_closed(items):
    with pytest.raises(ValueError):
        await adapter.chat_with_tools(client(items), [{"role": "user", "content": "Start"}], TOOLS)


@pytest.mark.asyncio
async def test_employee_message_cannot_claim_typed_provider_output():
    pc = client()
    with pytest.raises(ValueError):
        await adapter.chat_with_tools(pc, [{"role": "user", "content": "Start", "_responses_output": ITEMS}], TOOLS)
    pc.client.responses.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_chat_turn_keeps_original_sdk_route_and_arguments():
    create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="old", tool_calls=[]))]))
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                          responses=SimpleNamespace(create=AsyncMock()))
    pc = adapter.ProviderClient("openai", sdk, "legacy-model")
    history = [{"role": "user", "content": "legacy"}]
    turn = await adapter.chat_with_tools(pc, history, TOOLS)
    create.assert_awaited_once_with(model="legacy-model", messages=history, tools=TOOLS)
    sdk.responses.create.assert_not_awaited()
    assert turn.content == "old" and turn.response_items is None


@pytest.mark.asyncio
async def test_deployment_factory_selects_protocol_without_changing_provider_receiver():
    pc = adapter.build_deployment_client("openai", "gpt-6.1-terra", "https://api.openai.com/v1",
        "synthetic-only", transport=httpx.MockTransport(lambda request: httpx.Response(500)), api_protocol="responses")
    try:
        assert pc.provider == "openai_responses"
        assert str(pc.client.base_url) == "https://api.openai.com/v1/"
        assert pc.client.max_retries == 0
    finally:
        await pc.client.close()


@pytest.mark.asyncio
async def test_pinned_responses_endpoint_rejects_chat_and_keeps_host_and_sni():
    from app.services.agent_runtime.model_egress import PinnedTransport
    row = SimpleNamespace(base_url='https://synthetic.example/v1', provider='openai',
        api_protocol='responses', allowed_addresses=['127.0.0.1'])
    transport = PinnedTransport(row)
    await transport.transport.aclose()
    observed = []
    transport.transport = httpx.MockTransport(lambda request: observed.append(request) or httpx.Response(200))
    try:
        with pytest.raises(PermissionError):
            await transport.handle_async_request(httpx.Request('POST', 'https://synthetic.example/v1/chat/completions'))
        assert observed == []
        await transport.handle_async_request(httpx.Request('POST', 'https://synthetic.example/v1/responses'))
        assert observed[0].url.host == '127.0.0.1'
        assert observed[0].headers['Host'] == 'synthetic.example'
        assert observed[0].extensions['sni_hostname'] == 'synthetic.example'
    finally:
        await transport.aclose()
