"""Tool registry + AgentContext.

AgentContext carries factory/user/tenant scope injected by the harness.
It is NEVER exposed to the LLM — tools receive it as the first arg but
the LLM only sees the business params in the tool schema.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.models.agent import AgentSession


@dataclass
class AgentContext:
    db: AsyncSession
    session_id: uuid.UUID
    user_id: uuid.UUID
    factory_id: uuid.UUID          # from RequestScope, not LLM
    tenant_schema: str
    permission_levels: dict[Module, PermissionLevel] = field(default_factory=dict)
    product_line_code: str | None = None  # resolved from request query (P0: usually None)
    session: AgentSession | None = None


@dataclass
class ToolSpec:
    name: str
    func: Callable
    level: str                       # readonly/draft/commit
    action: str                      # sub-action for whitelist 5-tuple (defaults to tool name)
    entity_type: str
    required_permission: dict        # {module: Module, min_level: PermissionLevel}
    description: str
    param_schema: dict               # JSON schema for LLM-visible params (no scope)


TOOL_REGISTRY: dict[str, ToolSpec] = {}


def agent_tool(*, level: str, entity_type: str, required_permission: dict, description: str, action: str | None = None):
    def decorator(func: Callable) -> Callable:
        spec = ToolSpec(
            name=func.__name__,
            func=func,
            level=level,
            action=action or func.__name__,
            entity_type=entity_type,
            required_permission=required_permission,
            description=description,
            param_schema=_derive_param_schema(func),
        )
        TOOL_REGISTRY[func.__name__] = spec
        return func
    return decorator


def _derive_param_schema(func: Callable) -> dict:
    """Return a JSON schema for the LLM-visible params of `func`.

    Skips the first parameter (ctx: AgentContext) — scope is injected, not LLM-supplied.
    Minimal implementation: returns {"type": "object", "properties": {}}; richer
    inference is added when needed (the self-contained loop consumes spec.param_schema
    in Task 12, so this stays a lightweight metadata placeholder).
    """
    return {"type": "object", "properties": {}}
