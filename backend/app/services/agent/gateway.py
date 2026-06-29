"""Three-state permission gateway: readonly / draft / commit.

Whitelist matching uses the full 5-tuple: tool_name + action + entity_type +
max_scope (ctx.factory_id must fall in scope) + required_permission (ctx must
satisfy the whitelist's own permission requirement, in addition to the tool's).
Rejected calls (unknown tool / permission denied) still write a rejected
AgentToolCall + audit summary — no silent rejections.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Module, PermissionLevel
from app.models.agent import AgentAction, AgentCommitWhitelist, AgentToolCall
from app.services.agent import harness
from app.services.agent.registry import AgentContext, TOOL_REGISTRY


@dataclass
class GatewayResult:
    status: str            # executed / rejected / pending / approved
    result: Any = None
    action_id: uuid.UUID | None = None
    audit_log_id: uuid.UUID | None = None
    tool_call_id: uuid.UUID | None = None
    reason: str | None = None


async def _check_permission(ctx: AgentContext, required: dict) -> bool:
    """Check ctx.user satisfies `required`. Normalizes JSONB-form input
    (e.g. {"module": "fmea", "min_level": 1} from DB) and Enum form alike,
    so whitelist rows stored as JSON never break the lookup or raise TypeError."""
    mod = (required or {}).get("module")
    lvl = (required or {}).get("min_level")
    if mod is None or lvl is None:
        return True  # demo tools with no permission requirement
    if not isinstance(mod, Module):
        try:
            mod = Module(mod)  # JSONB string -> Module enum
        except ValueError:
            return False  # unknown module string
    try:
        min_level = int(lvl)  # JSONB int or numeric string -> int
    except (TypeError, ValueError):
        return False
    level = ctx.permission_levels.get(mod, PermissionLevel.NONE)
    return int(level) >= min_level


def _in_max_scope(max_scope: dict, ctx: AgentContext) -> tuple[bool, str | None]:
    """Check ctx against max_scope = {"factory_ids": [...], "product_line_codes": [...]}.
    Empty/missing list = no restriction on that dimension. Both dimensions enforced
    (no silent ignore). Returns (ok, reason)."""
    ms = max_scope or {}
    fids = ms.get("factory_ids")
    if fids and str(ctx.factory_id) not in [str(x) for x in fids]:
        return False, "factory_id not in max_scope.factory_ids"
    plcs = ms.get("product_line_codes")
    if plcs:
        if ctx.product_line_code is None:
            return False, "product_line scope required but ctx has no product_line_code"
        if ctx.product_line_code not in plcs:
            return False, "product_line_code not in max_scope.product_line_codes"
    return True, None


def _norm_perm(req: dict) -> tuple:
    """Normalize a required_permission dict to a comparable tuple.
    Tolerates Module/PermissionLevel enums, their values, or None."""
    mod = (req or {}).get("module")
    lvl = (req or {}).get("min_level")
    mod_v = mod.value if hasattr(mod, "value") else (str(mod) if mod is not None else None)
    lvl_v = int(lvl) if lvl is not None else 0
    return (mod_v, lvl_v)


def _required_permission_matches(wl_req: dict, spec_req: dict) -> bool:
    """5-tuple equality: the whitelist row must declare the SAME permission
    requirement as the tool spec — otherwise a stale whitelist row could keep
    auto-approving after the tool's declared permission changes."""
    return _norm_perm(wl_req) == _norm_perm(spec_req)


async def _whitelist_match(ctx: AgentContext, spec) -> AgentCommitWhitelist | None:
    """Full 5-tuple match: tool_name + action + entity_type + max_scope + required_permission."""
    rows = (await ctx.db.execute(
        select(AgentCommitWhitelist)
        .where(AgentCommitWhitelist.tool_name == spec.name)
        .where(AgentCommitWhitelist.action == spec.action)
        .where(AgentCommitWhitelist.entity_type == spec.entity_type)
        .where(AgentCommitWhitelist.enabled.is_(True))
    )).scalars().all()
    for wl in rows:
        ok, _reason = _in_max_scope(wl.max_scope, ctx)
        if not ok:
            continue
        if not _required_permission_matches(wl.required_permission, spec.required_permission):
            continue
        # equality already confirmed wl_req == spec_req; check the USER against the
        # enum-typed spec.required_permission (avoids any JSONB-form lookup issue).
        if not await _check_permission(ctx, spec.required_permission):
            continue
        return wl
    return None


async def _record_rejected(ctx: AgentContext, tool_name: str, params: dict, level: str, reason: str) -> GatewayResult:
    tool_call_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    log = await harness.write_audit(ctx.db, ctx, "agent_tool_calls", tool_call_id, "rejected", correlation_id)
    tc = AgentToolCall(tool_call_id=tool_call_id, session_id=ctx.session_id, tool_name=tool_name,
                       level=level, params=params, status="rejected", factory_id=ctx.factory_id,
                       correlation_id=correlation_id, audit_log_id=log.log_id, result={"error": reason})
    ctx.db.add(tc); await ctx.db.flush()
    return GatewayResult(status="rejected", reason=reason, tool_call_id=tool_call_id, audit_log_id=log.log_id)


async def _safe_call(spec, ctx: AgentContext, params: dict):
    """Run spec.func; on param-validation failure (TypeError/ValueError) return a
    GatewayResult(rejected) with a rejected AgentToolCall + audit (no silent bubble)."""
    try:
        result = await spec.func(ctx, **params)
        return result, None
    except (TypeError, ValueError) as e:
        return None, await _record_rejected(ctx, spec.name, params, spec.level, f"param invalid: {e}")


async def invoke(ctx: AgentContext, tool_name: str, params: dict) -> GatewayResult:
    spec = TOOL_REGISTRY.get(tool_name)
    if spec is None:
        return await _record_rejected(ctx, tool_name, params, "unknown", f"unknown tool {tool_name}")

    if not await _check_permission(ctx, spec.required_permission):
        return await _record_rejected(ctx, tool_name, params, spec.level, "permission denied")

    t0 = time.perf_counter()
    tool_call_id = uuid.uuid4()
    correlation_id = uuid.uuid4()

    if spec.level == "readonly":
        result, rejected = await _safe_call(spec, ctx, params)
        if rejected is not None:
            return rejected
        dur = int((time.perf_counter() - t0) * 1000)
        log = await harness.write_audit(ctx.db, ctx, "agent_tool_calls", tool_call_id, "call", correlation_id)
        tc = AgentToolCall(tool_call_id=tool_call_id, session_id=ctx.session_id,
                           tool_name=tool_name, level="readonly", params=params,
                           result=result, status="executed", factory_id=ctx.factory_id,
                           correlation_id=correlation_id, duration_ms=dur, audit_log_id=log.log_id)
        ctx.db.add(tc); await ctx.db.flush()
        return GatewayResult(status="executed", result=result, tool_call_id=tool_call_id,
                             audit_log_id=log.log_id)

    if spec.level == "draft":
        result, rejected = await _safe_call(spec, ctx, params)
        if rejected is not None:
            return rejected
        action_id = uuid.uuid4()
        action = AgentAction(action_id=action_id, session_id=ctx.session_id, factory_id=ctx.factory_id,
                             tool_name=tool_name, level="draft", payload=result, status="pending")
        ctx.db.add(action); await ctx.db.flush()
        log = await harness.write_audit(ctx.db, ctx, "agent_actions", action_id, "draft", correlation_id)
        return GatewayResult(status="pending", result=result, action_id=action_id, audit_log_id=log.log_id)

    # commit: three-state
    wl = await _whitelist_match(ctx, spec)
    if wl is None:
        action_id = uuid.uuid4()
        action = AgentAction(action_id=action_id, session_id=ctx.session_id, factory_id=ctx.factory_id,
                             tool_name=tool_name, level="commit", payload=params, status="pending")
        ctx.db.add(action); await ctx.db.flush()
        log = await harness.write_audit(ctx.db, ctx, "agent_actions", action_id, "commit_pending", correlation_id)
        return GatewayResult(status="pending", action_id=action_id, audit_log_id=log.log_id, reason="awaiting approval")

    # whitelisted -> execute + full audit
    result, rejected = await _safe_call(spec, ctx, params)
    if rejected is not None:
        return rejected
    dur = int((time.perf_counter() - t0) * 1000)
    action_id = uuid.uuid4()
    action = AgentAction(action_id=action_id, session_id=ctx.session_id, factory_id=ctx.factory_id,
                         tool_name=tool_name, level="commit", payload=params, status="approved",
                         decision_source="whitelist", post_values=result)
    ctx.db.add(action); await ctx.db.flush()
    log = await harness.write_audit(ctx.db, ctx, "agent_tool_calls", tool_call_id, "commit", correlation_id,
                                    new_values=result)
    tc = AgentToolCall(tool_call_id=tool_call_id, session_id=ctx.session_id, tool_name=tool_name,
                       level="commit", params=params, result=result, status="approved",
                       factory_id=ctx.factory_id, correlation_id=correlation_id, duration_ms=dur,
                       audit_log_id=log.log_id)
    ctx.db.add(tc); await ctx.db.flush()
    return GatewayResult(status="approved", result=result, action_id=action_id,
                         audit_log_id=log.log_id, tool_call_id=tool_call_id)


async def execute_approved_action(ctx: AgentContext, action: AgentAction) -> GatewayResult:
    """Force-execute a previously-pending commit action after HITL approval.

    Skips the whitelist/pending branch (approval IS the authorization) but still
    enforces permission + writes tool_call + audit. Used by approval.approve/modify.
    """
    if action.level != "commit":
        return await _record_rejected(ctx, action.tool_name, action.payload or {}, action.level or "commit",
                                        "execute_approved_action only handles commit actions")
    spec = TOOL_REGISTRY.get(action.tool_name)
    if spec is None:
        return await _record_rejected(ctx, action.tool_name, action.payload or {}, "commit", "unknown tool at exec time")
    if not await _check_permission(ctx, spec.required_permission):
        return await _record_rejected(ctx, action.tool_name, action.payload or {}, "commit", "permission denied")
    t0 = time.perf_counter()
    tool_call_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    result, rejected = await _safe_call(spec, ctx, action.payload or {})
    if rejected is not None:
        return rejected
    dur = int((time.perf_counter() - t0) * 1000)
    log = await harness.write_audit(ctx.db, ctx, "agent_tool_calls", tool_call_id, "commit", correlation_id,
                                    new_values=result)
    tc = AgentToolCall(tool_call_id=tool_call_id, session_id=ctx.session_id, tool_name=action.tool_name,
                       level="commit", params=action.payload, result=result, status="approved",
                       factory_id=ctx.factory_id, correlation_id=correlation_id, duration_ms=dur,
                       audit_log_id=log.log_id)
    ctx.db.add(tc); await ctx.db.flush()
    return GatewayResult(status="approved", result=result, action_id=action.action_id,
                         audit_log_id=log.log_id, tool_call_id=tool_call_id)
