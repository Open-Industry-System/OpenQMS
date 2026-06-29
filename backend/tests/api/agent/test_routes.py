"""Integration tests for agent API routes.

Uses the project's existing `admin_client` fixture (dependency overrides) to
authenticate as an admin user.  The LLM provider is stubbed so no real API call
is made.
"""
import uuid

import pytest

from app.services.agent import provider_adapter

pytestmark = pytest.mark.requires_db


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
async def test_list_actions_requires_factory(admin_client, default_factory):
    r = await admin_client.get("/api/agent/actions")
    assert r.status_code == 422  # factory_id query param required

    r2 = await admin_client.get(
        f"/api/agent/actions?factory_id={default_factory.id}"
    )
    assert r2.status_code == 200
    assert r2.json() == []
