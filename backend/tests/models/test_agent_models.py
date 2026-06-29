import uuid
import pytest
from sqlalchemy import select
from app.models.agent import (
    AgentSession, AgentMessage, AgentToolCall, AgentAction,
    AgentMemory, AgentCommitWhitelist,
)


@pytest.mark.asyncio
async def test_agent_session_factory_insert(db, admin_user, default_factory):
    s = AgentSession(
        session_id=uuid.uuid4(),
        user_id=admin_user.user_id,
        factory_id=default_factory.id,
        tenant_schema="public",
        scenario="copilot",
        status="active",
        task_state={"todo": []},
    )
    db.add(s)
    await db.flush()
    got = (await db.execute(select(AgentSession).where(AgentSession.session_id == s.session_id))).scalar_one()
    assert got.task_state == {"todo": []}
    assert got.factory_id == default_factory.id


@pytest.mark.asyncio
async def test_agent_action_decision_source_nullable_when_pending(db, admin_user, default_factory):
    s = AgentSession(session_id=uuid.uuid4(), user_id=admin_user.user_id,
                     factory_id=default_factory.id, tenant_schema="public",
                     scenario="copilot", status="active")
    db.add(s); await db.flush()
    a = AgentAction(action_id=uuid.uuid4(), session_id=s.session_id,
                    factory_id=default_factory.id, tool_name="commit_tag",
                    level="commit", payload={"k": "v"}, status="pending")
    db.add(a); await db.flush()
    got = (await db.execute(select(AgentAction).where(AgentAction.action_id == a.action_id))).scalar_one()
    assert got.decision_source is None  # pending has no decision source yet
    assert got.approver_id is None


def test_agent_commit_whitelist_is_tenant_model():
    from app.database import Base
    # whitelist is a tenant table so its created_by FK to users.user_id (also tenant) is valid
    assert issubclass(AgentCommitWhitelist, Base)
