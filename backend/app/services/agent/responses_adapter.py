"""Buffered stateless Responses turns for explicitly approved R5 deployments.

Opaque typed output stays in the platform's bounded in-memory round. It is not
an employee/plugin DTO, a database record or a provider-stored response chain.
"""
from copy import deepcopy
import json

UNAVAILABLE = "Invalid Responses turn"
MAX_REPLAY_BYTES = 256 * 1024


def response_items(items):
    if not isinstance(items, list):
        raise ValueError(UNAVAILABLE)
    result = [item.model_dump(mode="json", exclude_none=True) if hasattr(item, "model_dump")
              else deepcopy(item) for item in items]
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode()) > MAX_REPLAY_BYTES:
        raise ValueError(UNAVAILABLE)
    ids = set()
    for item in result:
        if not isinstance(item, dict):
            raise ValueError(UNAVAILABLE)
        kind = item.get("type")
        if kind == "reasoning":
            if not isinstance(item.get("encrypted_content"), str) or not item["encrypted_content"]:
                raise ValueError(UNAVAILABLE)
        elif kind == "function_call":
            call_id = item.get("call_id")
            if not isinstance(call_id, str) or not call_id or call_id in ids:
                raise ValueError(UNAVAILABLE)
            ids.add(call_id)
            if item.get("status") not in (None, "completed"):
                raise ValueError(UNAVAILABLE)
        elif kind == "message":
            if item.get("role") != "assistant" or item.get("status") not in (None, "completed"):
                raise ValueError(UNAVAILABLE)
            if not isinstance(item.get("content"), list) or any(
                not isinstance(part, dict) or part.get("type") not in {"output_text", "refusal"}
                or not isinstance(part.get("text" if part["type"] == "output_text" else "refusal"), str)
                for part in item["content"]
            ):
                raise ValueError(UNAVAILABLE)
        else:
            # No hosted tools, compaction or implicit execution capabilities.
            raise ValueError(UNAVAILABLE)
    return result


def input_items(messages):
    result = []
    for message in messages:
        role = message.get("role")
        if "_responses_output" in message:
            if role != "assistant":
                raise ValueError(UNAVAILABLE)
            result.extend(response_items(message["_responses_output"]))
        elif role == "tool":
            if not isinstance(message.get("content"), str) or not isinstance(message.get("tool_call_id"), str):
                raise ValueError(UNAVAILABLE)
            result.append({"type": "function_call_output", "call_id": message["tool_call_id"], "output": message["content"]})
        elif role in {"user", "system", "assistant", "developer"}:
            if not isinstance(message.get("content"), str):
                raise ValueError(UNAVAILABLE)
            result.append({"role": role, "content": message["content"]})
        else:
            raise ValueError(UNAVAILABLE)
    return result


def function_tools(tools):
    result = []
    for tool in tools:
        if tool.get("type") != "function" or not isinstance(tool.get("function"), dict):
            raise ValueError(UNAVAILABLE)
        definition = tool["function"]
        result.append({"type": "function", "name": definition["name"],
                       "description": definition.get("description", ""),
                       "parameters": deepcopy(definition["parameters"]), "strict": False})
    return result


async def chat_with_tools(pc, messages, tools):
    from app.services.agent.provider_adapter import AssistantTurn

    definitions = function_tools(tools)
    options = {}
    # Model-specific controls never choose the route or receiver. Other
    # explicitly registered Responses models keep their provider defaults.
    if pc.model == "gpt-6.1-terra":
        options = {"reasoning": {"effort": "medium"}, "text": {"verbosity": "medium"}}
    response = await pc.client.responses.create(model=pc.model, input=input_items(messages),
        tools=definitions, store=False, include=["reasoning.encrypted_content"], **options)
    if response.status != "completed":
        raise ValueError(UNAVAILABLE)
    items = response_items(response.output)
    allowed = {tool["name"] for tool in definitions}
    calls, text = [], []
    for item in items:
        if item["type"] == "function_call":
            if item.get("name") not in allowed or not isinstance(item.get("arguments"), str):
                raise ValueError(UNAVAILABLE)
            try:
                arguments = json.loads(item["arguments"])
            except (TypeError, ValueError):
                raise ValueError(UNAVAILABLE) from None
            if not isinstance(arguments, dict):
                raise ValueError(UNAVAILABLE)
            calls.append({"id": item["call_id"], "name": item["name"], "arguments": arguments})
        elif item["type"] == "message":
            text.extend(part.get("text", part.get("refusal", "")) for part in item["content"])
    return AssistantTurn(content="".join(text), tool_calls=calls, response_items=items)
