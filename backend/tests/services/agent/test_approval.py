import pytest
from sqlalchemy import select

from app.services.agent import approval, gateway, harness
from app.services.agent.tools import demo  # noqa


@pytest.mark.asyncio
async def test_approve_pending_commit_executes_tool(db, admin_user, default_factory):
    from app.models.agent import AgentToolCall
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    res = await gateway.invoke(ctx, "commit_tag", {"tag": "x"})  # not whitelisted -> pending
    assert res.status == "pending"
    action = await approval.approve(db, res.action_id, admin_user, reason="ok")
    assert action.status == "approved"
    assert action.decision_source == "user"
    assert action.approver_id == admin_user.user_id
    # the tool actually executed: post_values recorded + an approved AgentToolCall exists
    assert action.post_values == {"tagged": "x"}
    tcs = (await db.execute(select(AgentToolCall).where(AgentToolCall.session_id == s.session_id)
                            .where(AgentToolCall.status == "approved"))).scalars().all()
    assert any(tc.tool_name == "commit_tag" for tc in tcs)


@pytest.mark.asyncio
async def test_reject_does_not_execute(db, admin_user, default_factory):
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    res = await gateway.invoke(ctx, "commit_tag", {"tag": "x"})
    action = await approval.reject(db, res.action_id, admin_user, reason="no")
    assert action.status == "rejected"


@pytest.mark.asyncio
async def test_list_pending_isolated_by_factory(db, admin_user, default_factory):
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    await gateway.invoke(ctx, "commit_tag", {"tag": "x"})
    pendings = await approval.list_pending(db, default_factory.id)
    assert any(a.tool_name == "commit_tag" for a in pendings)
