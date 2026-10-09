"""Actual runtime middleware and strict readonly context query."""
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
from tests.services.agent_runtime.test_runtime_messages import delivery
from tests.services.agent_runtime.test_readonly_delivery import context_delivery

PATH = "/api/agent/runtime/capa/context"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "dev", "production"])
async def test_context_default_off_precedes_tenant_auth_and_validation(mode, monkeypatch):
    monkeypatch.setattr(settings, "TENANT_MODE", mode)
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method in ("GET", "POST", "DELETE", "PUT"):
            response = await client.request(method, PATH+"?view=invalid&actor=spoof", content="invalid-json",
                headers={"X-Tenant-ID": "unresolved", "Authorization": "Bearer invalid"})
            assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_actual_context_http_without_target_then_strict_queries_and_token_domains(context_delivery, monkeypatch):
    import app.database as database
    owned = context_delivery
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(database, "tenant_async_session", owned.factory)
    auth = {"Authorization": "Bearer "+owned.token}
    assert not app.dependency_overrides
    async with owned.engine.connect() as conn:
        slug = await conn.scalar(text("SELECT slug FROM public.tenants WHERE id=:id"), {"id": owned.binding.tenant_id})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(PATH, headers=auth)
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["report_id"] == str(owned.report_id) and "verifications" not in report
        result = await client.get(PATH, params={"report_id": report["report_id"], "view": "verifications"}, headers=auth)
        assert result.status_code == 200, result.text
        assert result.json()["projection_digest"] == report["projection_digest"]
        assert "SECRET" not in result.text
        for key in ("actor", "schema", "factory_id", "tenant_id", "trust", "controlled_egress", "data_class", "scope"):
            assert (await client.get(PATH, params={key: "spoof"}, headers=auth)).status_code == 422
        for params in ({"view": "raw"}, {"report_id": "not-uuid"}):
            assert (await client.get(PATH, params=params, headers=auth)).status_code == 422
        assert (await client.get(PATH, params={"report_id": str(uuid.uuid4())}, headers=auth)).status_code == 403
        ordinary = (create_access_token({"sub": str(owned.user_id), "tenant_id": str(owned.binding.tenant_id)}),
            create_platform_admin_token(str(owned.user_id)), create_refresh_token(str(owned.user_id))[0])
        for token in ordinary:
            response = await client.get(PATH, headers={"X-Tenant-ID": slug, "Authorization": "Bearer "+token})
            assert response.status_code == 401 and "SECRET" not in response.text
        claims = jwt.get_unverified_claims(owned.token)
        for overrides in ({"tenant_generation": claims["tenant_generation"]+1}, {"tenant_id": str(uuid.uuid4())}):
            token = jwt.encode({**claims, **overrides}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
            response = await client.get(PATH, headers={"X-Tenant-ID": slug, "Authorization": "Bearer "+token})
            assert response.status_code == 401 and "SECRET" not in response.text
        # Fallback authority registers one exact method/path tuple only.
        assert (await client.post(PATH, headers=auth)).status_code == 400
        assert (await client.get(PATH+"-extra", headers=auth)).status_code == 400
