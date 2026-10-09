"""Actual runtime router admission and dedicated signed tenant fallback."""
import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import update

from app.config import settings
from app.core.security import create_access_token, create_platform_admin_token, create_refresh_token
from app.main import app
from app.models.agent_task import AgentRun
from tests.services.agent_runtime.conftest import committed_runtime
from tests.services.agent_runtime.test_runtime_access import direct_caps, ready_owned


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "dev", "production"])
async def test_runtime_disabled_exact_routes_before_any_auth_tenant_body(mode, monkeypatch):
    monkeypatch.setattr(settings, "TENANT_MODE", mode)
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method, path in (("POST", "/api/agent/runtime/claim"), ("GET", "/api/agent/runtime/capabilities"),
                             ("GET", "/api/agent/runtime/claim"), ("POST", "/api/agent/runtime/capabilities")):
            response = await client.request(method, path, content="invalid-json", headers={"X-Tenant-ID": "invalid", "Authorization": "Bearer invalid"})
            assert response.status_code == 404, response.text
        if mode != "single":
            assert (await client.get("/api/agent/runtime/capabilities-extra")).status_code == 400


@pytest.mark.asyncio
async def test_actual_tenant_claim_and_signed_runtime_fallback(ready_owned, monkeypatch):
    import app.database as database
    owned = ready_owned
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(database, "tenant_async_session", owned.factory)
    assert not app.dependency_overrides
    async with owned.engine.connect() as conn:
        from sqlalchemy import text
        slug = await conn.scalar(text("SELECT slug FROM public.tenants WHERE id=:id"), {"id": owned.binding.tenant_id})
    request = dict(installation_id=str(owned.plugin_id), secret=owned.secret, request_key="http-claim")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/agent/runtime/claim", json=request)).status_code == 400
        response = await client.post("/api/agent/runtime/claim", json=request, headers={"X-Tenant-ID": slug})
        assert response.status_code == 200, response.text
        claimed = response.json()
        assert set(claimed) == {"run_id", "task_id", "token", "lease_epoch", "lease_expires_at", "accepted_message_seq", "has_resume_checkpoint"}
        token = claimed["token"]
        auth = {"Authorization": "Bearer " + token}
        capabilities = await client.get("/api/agent/runtime/capabilities", headers=auth)
        assert capabilities.status_code == 200, capabilities.text
        assert capabilities.json()["capabilities"][0]["id"] == "capa.d4.summary.masked.v1"
        assert "source_capa_id" not in capabilities.text and "report_id" not in capabilities.text
        # A valid runtime token must NEVER resolve tenant on ordinary user paths.
        assert (await client.get("/api/agent/tasks", headers=auth)).status_code == 400
        assert (await client.get("/api/agent/tasks", headers={**auth, "X-Tenant-ID": slug})).status_code == 401
        forged_user = jwt.encode({**jwt.get_unverified_claims(token), "sub": str(owned.user_id)}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        assert (await client.get("/api/agent/tasks", headers={"X-Tenant-ID": slug, "Authorization": "Bearer " + forged_user})).status_code == 401
        assert (await client.get("/api/agent/runtime/capabilities-extra", headers=auth)).status_code == 400
        assert (await client.post("/api/agent/runtime/claim", json=request, headers=auth)).status_code == 400
        for ordinary in (create_access_token({"sub": str(owned.user_id), "tenant_id": str(owned.binding.tenant_id)}),
            create_platform_admin_token(str(owned.user_id)), create_refresh_token(str(owned.user_id))[0]):
            response = await client.get("/api/agent/runtime/capabilities", headers={"X-Tenant-ID": slug, "Authorization": "Bearer " + ordinary})
            assert response.status_code == 401
        claims = jwt.get_unverified_claims(token)
        stale = jwt.encode({**claims, "tenant_generation": claims["tenant_generation"]+1}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        assert (await client.get("/api/agent/runtime/capabilities", headers={"Authorization": "Bearer " + stale})).status_code == 401
        async with owned.factory(binding=owned.binding) as revoker:
            await revoker.execute(update(AgentRun).where(AgentRun.run_id == owned.run_id).values(status="stopped"))
            await revoker.commit()
        assert (await client.get("/api/agent/runtime/capabilities", headers=auth)).status_code == 401
