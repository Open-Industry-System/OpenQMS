"""Agent harness: session lifecycle, AgentContext construction, audit helper."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.models.agent import AgentMessage, AgentSession
from app.models.user import User
from app.services.agent import gateway, guardrails, provider_adapter
from app.services.agent.audit import write_audit
from app.services.agent.registry import TOOL_REGISTRY, AgentContext


@dataclass
class RunResult:
    assistant_text: str | None
    blocked: bool = False
    reason: str | None = None
    pending_action_ids: list = field(default_factory=list)


_SYSTEM_PROMPT = (
    "你是 OpenQMS 质量管理助手。只能调用提供的工具。"
    "严禁泄露 factory_id 或跨工厂访问数据。"
)
_MAX_ITER = 6


async def run_message(db, session, user, redis, user_message: str) -> RunResult:
    ctx = await build_context(db, session, user)

    # guardrails: input
    gr = guardrails.check_input(user_message)
    if not gr.ok:
        db.add(AgentMessage(message_id=uuid.uuid4(), session_id=session.session_id,
                            factory_id=session.factory_id, role="user", content=user_message))
        db.add(AgentMessage(message_id=uuid.uuid4(), session_id=session.session_id,
                            factory_id=session.factory_id, role="assistant",
                            content=f"已拒绝：{gr.reason}"))
        await write_audit(db, ctx, "agent_messages", session.session_id, "guardrail_block", None)
        await db.flush()
        return RunResult(assistant_text=None, blocked=True, reason=gr.reason)

    db.add(AgentMessage(message_id=uuid.uuid4(), session_id=session.session_id,
                        factory_id=session.factory_id, role="user", content=user_message))

    pc = await provider_adapter.build_client(db)
    specs = list(TOOL_REGISTRY.values())
    tools = provider_adapter.tools_schema_for(pc, specs)
    # P0 minimal: system + current user message (short-term history can be prepended in P2)
    messages = [{"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message}]

    assistant_text = ""
    pending = []
    for _ in range(_MAX_ITER):
        turn = await provider_adapter.chat_with_tools(pc, messages, tools)
        if not turn.tool_calls:
            assistant_text = turn.content or ""
            break
        # append the assistant turn (openai-style tool_calls) and execute each via the gateway
        messages.append(
            {
                "role": "assistant",
                "content": turn.content,
                "tool_calls": [
                    {
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": c["name"],
                            "arguments": json.dumps(c.get("arguments") or {}),
                        },
                    }
                    for i, c in enumerate(turn.tool_calls)
                ],
            }
        )
        for c in turn.tool_calls:
            res = await gateway.invoke(ctx, c["name"], c.get("arguments") or {})
            if res.status == "pending" and res.action_id:
                pending.append(res.action_id)
            # feed the tool result back (openai-style tool message; anthropic shaping is a P2 follow-up)
            messages.append({"role": "tool", "tool_call_id": "call_0",
                             "content": json.dumps(res.result if res.result is not None else {"status": res.status})})
    else:
        assistant_text = "（已达到最大工具调用轮数）"

    # guardrails: output (sanitize before persisting/returning)
    if isinstance(assistant_text, str):
        assistant_text = guardrails._redact(assistant_text, ctx.factory_id)

    db.add(AgentMessage(message_id=uuid.uuid4(), session_id=session.session_id,
                        factory_id=session.factory_id, role="assistant", content=str(assistant_text)))
    await db.flush()
    return RunResult(assistant_text=str(assistant_text), pending_action_ids=pending)


async def create_session(
    db: AsyncSession,
    user: User,
    factory_id: uuid.UUID,
    tenant_schema: str,
    scenario: str,
    related_entity_type: str | None = None,
    related_entity_id: uuid.UUID | None = None,
) -> AgentSession:
    s = AgentSession(
        session_id=uuid.uuid4(),
        user_id=user.user_id,
        factory_id=factory_id,
        tenant_schema=tenant_schema,
        scenario=scenario,
        status="active",
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        task_state={"todo": []},
    )
    db.add(s)
    await db.flush()
    return s


async def build_context(db: AsyncSession, session: AgentSession, user: User) -> AgentContext:
    levels: dict[Module, PermissionLevel] = {}
    for module in Module:
        levels[module] = await get_user_permission(user, module, db)
    return AgentContext(
        db=db,
        session_id=session.session_id,
        user_id=user.user_id,
        factory_id=session.factory_id,
        tenant_schema=session.tenant_schema,
        permission_levels=levels,
        session=session,
    )
