"""Actual middleware and message router with dedicated runtime credentials."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import text

from app.config import settings
from app.core.security import create_access_token, create_platform_admin_token, create_refresh_token
from app.main import app
from tests.services.agent_runtime.conftest import committed_runtime
from tests.services.agent_runtime.test_runtime_access import direct_caps, ready_owned
from tests.services.agent_runtime.test_runtime_messages import append, delivery


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "dev", "production"])
async def test_messages_default_off_paths_precede_tenant_body_and_auth(mode, monkeypatch):
    monkeypatch.setattr(settings, "TENANT_MODE", mode)
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for action in ("claim", "ack"):
            for method in ("POST", "GET", "DELETE"):
                response = await client.request(method, "/api/agent/runtime/messages/"+action,
                    content="invalid-json", headers={"X-Tenant-ID": "unresolved", "Authorization": "Bearer invalid"})
                assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_actual_message_http_signed_fallback_strict_body_and_domains(delivery, monkeypatch):
    import app.database as database
    owned = delivery
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(database, "tenant_async_session", owned.factory)
    await append(owned, "original restricted instruction")
    assert not app.dependency_overrides
    async with owned.engine.connect() as conn:
        slug = await conn.scalar(text("SELECT slug FROM public.tenants WHERE id=:id"), {"id": owned.binding.tenant_id})
    auth = {"Authorization": "Bearer "+owned.token}
    claim_path = "/api/agent/runtime/messages/claim"
    ack_path = "/api/agent/runtime/messages/ack"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(claim_path, json={"limit": 1}, headers=auth)
        assert response.status_code == 200, response.text
        batch = response.json()
        assert batch["messages"][0]["content"] == "original restricted instruction"
        assert set(batch) == {"batch_id", "messages", "accepted_sequence"}
        ack_body = {"batch_id": batch["batch_id"], "through_sequence": 1}
        for path, body in ((claim_path, {"limit": 1, "actor_id": str(owned.user_id)}),
                            (ack_path, {**ack_body, "lease_epoch": 1}),
                            (ack_path, {**ack_body, "through_sequence": True})):
            assert (await client.post(path, json=body, headers=auth)).status_code == 422
        invalid = await client.post(ack_path, json={**ack_body, "batch_id": str(uuid.uuid4())}, headers=auth)
        assert invalid.status_code == 409 and "original restricted" not in invalid.text
        assert (await client.post(ack_path, json=ack_body, headers=auth)).json() == {"accepted_sequence": 1}
        assert (await client.post(ack_path, json=ack_body, headers=auth)).json() == {"accepted_sequence": 1}
        ordinary = (create_access_token({"sub": str(owned.user_id), "tenant_id": str(owned.binding.tenant_id)}),
            create_platform_admin_token(str(owned.user_id)), create_refresh_token(str(owned.user_id))[0])
        for token in ordinary:
            for path, body in ((claim_path, {}), (ack_path, ack_body)):
                result = await client.post(path, json=body, headers={"X-Tenant-ID": slug, "Authorization": "Bearer "+token})
                assert result.status_code == 401 and "original restricted" not in result.text
        claims = jwt.get_unverified_claims(owned.token)
        wrong = jwt.encode({**claims, "tenant_id": str(uuid.uuid4())}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        assert (await client.post(claim_path, json={}, headers={"X-Tenant-ID": slug, "Authorization": "Bearer "+wrong})).status_code == 401
        stale = jwt.encode({**claims, "tenant_generation": claims["tenant_generation"]+1}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        assert (await client.post(claim_path, json={}, headers={"Authorization": "Bearer "+stale})).status_code == 401
        # JWT fallback must be exactly registered by method and path.
        assert (await client.get(claim_path, headers=auth)).status_code == 400
        assert (await client.post(claim_path+"-extra", json={}, headers=auth)).status_code == 400
