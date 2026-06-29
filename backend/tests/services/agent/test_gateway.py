import uuid

import pytest
from sqlalchemy import select

from app.models.agent import AgentToolCall
from app.services.agent import harness, gateway
from app.services.agent.registry import agent_tool, AgentContext, TOOL_REGISTRY
from app.services.agent.tools import demo  # noqa: F401 — registers tools


@pytest.mark.asyncio
async def test_readonly_executes_when_permitted(db, admin_user, default_factory):
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    res = await gateway.invoke(ctx, "echo_factory", {})
    assert res.status == "executed"
    assert res.result == {"scope_bound": True, "factory_match": True}


@pytest.mark.asyncio
async def test_unknown_tool_rejected_with_audit(db, admin_user, default_factory):
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    res = await gateway.invoke(ctx, "does_not_exist", {})
    assert res.status == "rejected"
    # rejected calls must leave a rejected AgentToolCall + audit (no silent rejection)
    tc = (await db.execute(select(AgentToolCall).where(AgentToolCall.tool_call_id == res.tool_call_id))).scalar_one()
    assert tc.status == "rejected"
    assert tc.audit_log_id is not None


@pytest.mark.asyncio
async def test_commit_without_whitelist_becomes_pending(db, admin_user, default_factory):
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    res = await gateway.invoke(ctx, "commit_tag", {"tag": "x"})
    assert res.status == "pending"
    assert res.action_id is not None


@pytest.mark.asyncio
async def test_whitelist_max_scope_excludes_other_factory(db, admin_user, default_factory):
    """Whitelist with max_scope.factory_ids=[other] must NOT match ctx.factory_id."""
    import uuid as _uuid
    from app.models.agent import AgentCommitWhitelist
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    other = _uuid.uuid4()
    wl = AgentCommitWhitelist(id=_uuid.uuid4(), tool_name="commit_tag", action="tag",
                              entity_type="tag", max_scope={"factory_ids": [str(other)]},
                              required_permission={"module": None, "min_level": None}, enabled=True)
    db.add(wl); await db.flush()
    res = await gateway.invoke(ctx, "commit_tag", {"tag": "x"})
    # scope mismatch -> not whitelisted -> pending (NOT auto-approved)
    assert res.status == "pending"


@pytest.mark.asyncio
async def test_whitelist_product_line_scope_enforced_when_ctx_none(db, admin_user, default_factory):
    """max_scope.product_line_codes non-empty but ctx has no product_line_code -> no match -> pending.
    Proves product_line scope is enforced (not silently ignored)."""
    import uuid as _uuid
    from app.models.agent import AgentCommitWhitelist
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    assert ctx.product_line_code is None  # P0: no product line in scope
    wl = AgentCommitWhitelist(id=_uuid.uuid4(), tool_name="commit_tag", action="tag",
                              entity_type="tag", max_scope={"product_line_codes": ["DC-DC-100"]},
                              required_permission={"module": None, "min_level": None}, enabled=True)
    db.add(wl); await db.flush()
    res = await gateway.invoke(ctx, "commit_tag", {"tag": "x"})
    assert res.status == "pending"  # product_line required but ctx has none -> no whitelist match


@pytest.mark.asyncio
async def test_whitelist_required_permission_mismatch_blocks_auto_approve(db, admin_user, default_factory):
    """Same tool/action/entity/scope but whitelist required_permission != tool spec's
    required_permission -> no match -> pending. Prevents a stale row auto-approving
    after the tool's declared permission changes."""
    import uuid as _uuid
    from app.core.permissions import Module, PermissionLevel
    from app.models.agent import AgentCommitWhitelist
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    # commit_tag spec requires {module: None, min_level: None}; whitelist row declares FMEA/ADMIN -> mismatch
    wl = AgentCommitWhitelist(id=_uuid.uuid4(), tool_name="commit_tag", action="tag",
                              entity_type="tag", max_scope={},
                              required_permission={"module": Module.FMEA, "min_level": PermissionLevel.ADMIN},
                              enabled=True)
    db.add(wl); await db.flush()
    res = await gateway.invoke(ctx, "commit_tag", {"tag": "x"})
    assert res.status == "pending"  # required_permission mismatch -> not whitelisted


@pytest.mark.asyncio
async def test_whitelist_jsonb_matches_enum_spec_regression(db, admin_user, default_factory):
    """Regression: whitelist JSONB {"module":"fmea","min_level":3} matches a tool spec
    declared with Module.FMEA/PermissionLevel.EDIT (enum), admin (FMEA ADMIN>=EDIT)
    auto-approved. Uses a throwaway tool registered locally and cleaned up — NOT added
    to demo.py, to keep Task 5's LLM-visible demo surface at 2 stubs (echo_factory + commit_tag)."""
    import uuid as _uuid
    from app.core.permissions import Module, PermissionLevel
    from app.services.agent.registry import agent_tool, AgentContext, TOOL_REGISTRY
    from app.models.agent import AgentCommitWhitelist, AgentAction

    @agent_tool(level="commit", entity_type="fmea_tag", action="tag",
                required_permission={"module": Module.FMEA, "min_level": PermissionLevel.EDIT},
                description="throwaway jsonb regression tool")
    async def _jsonb_test_commit(ctx: AgentContext, tag: str = "") -> dict:
        return {"tagged": tag}
    try:
        s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
        ctx = await harness.build_context(db, s, admin_user)
        wl = AgentCommitWhitelist(id=_uuid.uuid4(), tool_name="_jsonb_test_commit", action="tag",
                                  entity_type="fmea_tag", max_scope={},
                                  required_permission={"module": "fmea", "min_level": 3},  # JSONB form
                                  enabled=True)
        db.add(wl); await db.flush()
        res = await gateway.invoke(ctx, "_jsonb_test_commit", {"tag": "z"})
        assert res.status == "approved"
        assert res.action_id is not None
        a = (await db.execute(select(AgentAction).where(AgentAction.action_id == res.action_id))).scalar_one()
        assert a.decision_source == "whitelist"
    finally:
        TOOL_REGISTRY.pop("_jsonb_test_commit", None)  # never pollute the global registry


@pytest.mark.asyncio
async def test_param_invalid_rejected_with_audit(db, admin_user, default_factory):
    """Bad/missing/extra params must produce status rejected + a rejected AgentToolCall
    with an audit_log_id, instead of bubbling the TypeError uncaught."""
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    res = await gateway.invoke(ctx, "echo_factory", {"unexpected": 1})
    assert res.status == "rejected"
    assert res.tool_call_id is not None
    tc = (await db.execute(select(AgentToolCall).where(AgentToolCall.tool_call_id == res.tool_call_id))).scalar_one()
    assert tc.status == "rejected"
    assert tc.audit_log_id is not None
    assert "param invalid" in tc.result.get("error", "")
