import uuid
import pytest
from app.services.agent import harness
from app.services.agent.registry import AgentContext
from app.models.agent import AgentSession


@pytest.mark.asyncio
async def test_create_session_persists_with_factory(db, admin_user, default_factory):
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    assert s.session_id is not None
    assert s.factory_id == default_factory.id
    assert s.tenant_schema == "public"


@pytest.mark.asyncio
async def test_build_context_injects_scope_not_from_llm(db, admin_user, default_factory):
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    assert isinstance(ctx, AgentContext)
    assert ctx.factory_id == default_factory.id
    assert ctx.tenant_schema == "public"
    assert ctx.session_id == s.session_id
    # permission_levels is a dict keyed by Module
    from app.core.permissions import Module
    assert isinstance(ctx.permission_levels, dict)


@pytest.mark.asyncio
async def test_write_audit_links_correlation_id(db, admin_user, default_factory):
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    corr = uuid.uuid4()
    log = await harness.write_audit(db, ctx, "agent_tool_calls", uuid.uuid4(), "call", corr)
    assert log.correlation_id == corr
    assert log.factory_id == default_factory.id
    assert log.tenant_schema == "public"
