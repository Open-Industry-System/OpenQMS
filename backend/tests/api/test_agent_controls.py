"""Actual HTTP, runtime domain registry, and strict content-free control DTOs."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select

from app.config import settings
from app.core.security import create_access_token, create_platform_admin_token, create_refresh_token
from app.main import app
from app.models.agent_readonly_control import AgentTaskControl
from tests.services.agent_runtime.conftest import committed_runtime
from tests.services.agent_runtime.test_runtime_access import direct_caps, ready_owned
from tests.services.agent_runtime.test_runtime_messages import delivery


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "dev", "production"])
async def test_controls_default_off_before_tenant_auth_body_all_methods(monkeypatch, mode):
    monkeypatch.setattr(settings, "TENANT_MODE", mode)
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/api/agent/runtime/finish", "/api/agent/tasks/bad-id/control"):
            for method in ("POST", "GET", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"):
                result = await client.request(method, path, content="invalid", headers={"X-Tenant-ID": "unresolved", "Authorization": "Bearer invalid"})
                assert result.status_code == 404, (mode, method, path, result.text)


@pytest.mark.asyncio
async def test_actual_control_http_current_state_retry_and_strict_body(delivery, monkeypatch):
    import app.database as database
    owned = delivery
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(database, "tenant_async_session", owned.factory)
    user_token = create_access_token({"sub": str(owned.user_id), "tenant_id": str(owned.binding.tenant_id)})
    path = "/api/agent/tasks/"+str(owned.task_id)+"/control"
    fields = dict(action="pause", run_id=str(owned.run_id), expected_epoch=1, idempotency_key="pause")
    assert not app.dependency_overrides
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        auth = {"Authorization": "Bearer "+user_token}
        for change in ({"expected_epoch": True}, {"expected_epoch": "1"}, {"action": "restart"},
                       {"executor_user_id": str(owned.user_id)}, {"checkpoint_id": str(uuid.uuid4())}, {"state": "paused"}):
            response = await client.post(path, json={**fields, **change}, headers=auth)
            assert response.status_code == 422, response.text
        assert (await client.post(path, json={**fields, "expected_epoch": 0}, headers=auth)).status_code == 409
        result = await client.post(path, json=fields, headers=auth)
        assert result.status_code == 200, result.text
        assert set(result.json()) == {"control_id", "task_id", "task_status", "run_id", "run_status", "lease_epoch"}
        assert result.json()["task_status"] == "paused"
        repeated = await client.post(path, json=fields, headers=auth)
        assert repeated.json() == result.json()
        assert (await client.post(path, json={**fields, "action": "cancel"}, headers=auth)).status_code == 409
        assert (await client.post(path, json=fields, headers={"Authorization": "Bearer "+owned.token})).status_code == 400
    async with owned.factory(binding=owned.binding) as observer:
        assert len(list((await observer.scalars(select(AgentTaskControl))).all())) == 1


@pytest.mark.asyncio
async def test_actual_finish_http_domain_registry_terminal_token_and_fixed_failure(delivery, monkeypatch):
    import app.database as database
    from sqlalchemy import text
    owned = delivery
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(database, "tenant_async_session", owned.factory)
    async with owned.engine.connect() as conn:
        slug = await conn.scalar(text("SELECT slug FROM public.tenants WHERE id=:id"), {"id": owned.binding.tenant_id})
    path = "/api/agent/runtime/finish"
    auth = {"Authorization": "Bearer "+owned.token}
    assert not app.dependency_overrides
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for fields in ({"status": "cancelled"}, {"status": "failed", "reason": "private exception"},
                       {"status": "completed", "idempotency_key": "retry"}, {"status": "completed", "task_id": str(owned.task_id)}):
            response = await client.post(path, json=fields, headers=auth)
            assert response.status_code == 422, response.text
        for token in (create_access_token({"sub": str(owned.user_id), "tenant_id": str(owned.binding.tenant_id)}),
                      create_platform_admin_token(str(owned.user_id)), create_refresh_token(str(owned.user_id))[0]):
            response = await client.post(path, json={"status": "completed"}, headers={"X-Tenant-ID": slug, "Authorization": "Bearer "+token})
            assert response.status_code == 401, response.text
        claims = jwt.get_unverified_claims(owned.token)
        stale = jwt.encode({**claims, "tenant_generation": claims["tenant_generation"]+1}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        assert (await client.post(path, json={"status": "completed"}, headers={"Authorization": "Bearer "+stale})).status_code == 401
        assert (await client.get(path, headers=auth)).status_code == 400
        assert (await client.post(path+"-extra", json={"status": "completed"}, headers=auth)).status_code == 400
        response = await client.post(path, json={"status": "failed"}, headers=auth)
        assert response.status_code == 200, response.text
        assert set(response.json()) == {"task_id", "task_status", "run_id", "run_status", "lease_epoch"}
        assert response.json()["task_status"] == response.json()["run_status"] == "failed"
        assert (await client.post(path, json={"status": "failed"}, headers=auth)).status_code == 401
