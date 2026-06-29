"""Integration tests for agent API routes.

Uses the project's existing `admin_client` fixture (dependency overrides) to
authenticate as an admin user.  The LLM provider is stubbed so no real API call
is made.
"""
import uuid

import pytest
from sqlalchemy import select

from app.core.deps import get_current_user, get_request_scope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.main import app
from app.models.audit import AuditLog
from app.services.agent import provider_adapter

pytestmark = pytest.mark.requires_db


def _scope_for(user, default_factory, accessible_factory_ids=None, pl_mode="ALL", pl_codes=None):
    from app.core.deps import RequestScope

    return RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=accessible_factory_ids, default_factory_id=default_factory.id),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode=pl_mode, codes=pl_codes),
        user=user,
    )


@pytest.fixture
def stub_llm(monkeypatch):
    """Stub provider_adapter so the agent loop runs locally."""

    async def _fake_chat(pc, messages, tools):
        return provider_adapter.AssistantTurn(content="ok", tool_calls=[])

    async def _fake_client(db_):
        return provider_adapter.ProviderClient(provider="openai", client=None, model="m")

    monkeypatch.setattr(provider_adapter, "chat_with_tools", _fake_chat)
    monkeypatch.setattr(provider_adapter, "build_client", _fake_client)


@pytest.mark.asyncio
async def test_create_session_and_post_message(admin_client, stub_llm):
    r = await admin_client.post("/api/agent/sessions", json={"scenario": "copilot"})
    assert r.status_code == 201
    body = r.json()
    assert "session_id" in body
    assert body["scenario"] == "copilot"
    sid = body["session_id"]

    r2 = await admin_client.post(
        f"/api/agent/sessions/{sid}/messages", json={"content": "帮我查 SPC"}
    )
    assert r2.status_code == 200
    msg = r2.json()
    assert "assistant_text" in msg
    assert msg["assistant_text"] == "ok"
    assert msg["blocked"] is False


@pytest.mark.asyncio
async def test_list_sessions_for_current_user(admin_client, stub_llm):
    r = await admin_client.post("/api/agent/sessions", json={"scenario": "copilot"})
    assert r.status_code == 201

    r_list = await admin_client.get("/api/agent/sessions")
    assert r_list.status_code == 200
    items = r_list.json()
    assert isinstance(items, list)
    assert any(i["scenario"] == "copilot" for i in items)


@pytest.mark.asyncio
async def test_whitelist_admin_crud(admin_client):
    payload = {
        "tool_name": "draft_note",
        "action": "create",
        "entity_type": "note",
        "max_scope": {"factories": [str(uuid.uuid4())]},
        "required_permission": {"module": "fmea", "min_level": 3},
        "enabled": True,
    }
    r = await admin_client.post("/api/agent/whitelist", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["tool_name"] == "draft_note"
    wid = body["id"]

    r_get = await admin_client.get(f"/api/agent/whitelist/{wid}")
    assert r_get.status_code == 200
    assert r_get.json()["id"] == wid

    r_list = await admin_client.get("/api/agent/whitelist")
    assert r_list.status_code == 200
    assert any(i["id"] == wid for i in r_list.json())

    updated = {**payload, "enabled": False}
    r_put = await admin_client.put(f"/api/agent/whitelist/{wid}", json=updated)
    assert r_put.status_code == 200
    assert r_put.json()["enabled"] is False

    r_del = await admin_client.delete(f"/api/agent/whitelist/{wid}")
    assert r_del.status_code == 204

    r_get2 = await admin_client.get(f"/api/agent/whitelist/{wid}")
    assert r_get2.status_code == 404


@pytest.mark.asyncio
async def test_post_message_ownership_check(admin_client, other_admin_user, default_factory, stub_llm):
    r = await admin_client.post("/api/agent/sessions", json={"scenario": "copilot"})
    assert r.status_code == 201
    sid = r.json()["session_id"]

    # Switch auth to another admin in the same factory
    app.dependency_overrides[get_current_user] = lambda: other_admin_user
    app.dependency_overrides[get_request_scope] = lambda: _scope_for(other_admin_user, default_factory)
    try:
        r2 = await admin_client.post(
            f"/api/agent/sessions/{sid}/messages", json={"content": "帮我查 SPC"}
        )
    finally:
        # admin_client fixture teardown will clear overrides; restore in case other tests share scope
        pass
    assert r2.status_code == 403
    assert "无权操作他人会话" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_action_decision_not_found_returns_404(admin_client):
    missing_id = str(uuid.uuid4())
    for endpoint in ("approve", "reject", "modify"):
        url = f"/api/agent/actions/{missing_id}/{endpoint}"
        payload = {"reason": "test"} if endpoint != "modify" else {"reason": "test", "new_payload": {}}
        r = await admin_client.post(url, json=payload)
        assert r.status_code == 404, f"{endpoint} should return 404 for missing action"
        assert "动作不存在" in r.json()["detail"]


@pytest.mark.asyncio
async def test_whitelist_crud_writes_audit_log(admin_client, db):
    payload = {
        "tool_name": "draft_note",
        "action": "create",
        "entity_type": "note",
        "max_scope": {"factories": [str(uuid.uuid4())]},
        "required_permission": {"module": "fmea", "min_level": 3},
        "enabled": True,
    }
    r = await admin_client.post("/api/agent/whitelist", json=payload)
    assert r.status_code == 201
    wid = r.json()["id"]

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.table_name == "agent_commit_whitelist")
        .where(AuditLog.record_id == uuid.UUID(wid))
        .where(AuditLog.action == "create")
    )
    assert result.scalar_one_or_none() is not None

    updated = {**payload, "enabled": False}
    r_put = await admin_client.put(f"/api/agent/whitelist/{wid}", json=updated)
    assert r_put.status_code == 200
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.table_name == "agent_commit_whitelist")
        .where(AuditLog.record_id == uuid.UUID(wid))
        .where(AuditLog.action == "update")
    )
    assert result.scalar_one_or_none() is not None

    r_del = await admin_client.delete(f"/api/agent/whitelist/{wid}")
    assert r_del.status_code == 204
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.table_name == "agent_commit_whitelist")
        .where(AuditLog.record_id == uuid.UUID(wid))
        .where(AuditLog.action == "delete")
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_list_actions_requires_factory(admin_client, default_factory):
    r = await admin_client.get("/api/agent/actions")
    assert r.status_code == 422  # factory_id query param required

    r2 = await admin_client.get(
        f"/api/agent/actions?factory_id={default_factory.id}"
    )
    assert r2.status_code == 200
    assert r2.json() == []
