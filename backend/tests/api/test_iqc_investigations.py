"""Employee route protections for the independent IQC entry point."""
import httpx
import pytest
from fastapi import FastAPI

from app.api import iqc_investigations
from app.config import settings
from app.core.tenant_context import TenantContextMiddleware


@pytest.mark.asyncio
async def test_default_off_hides_iqc_routes_before_tenant_auth_and_validation(monkeypatch):
    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_R7_IQC_INVESTIGATION_ENABLED", False)
    app = FastAPI()
    app.add_middleware(TenantContextMiddleware)
    app.include_router(iqc_investigations.router)
    paths = (
        ("GET", "/api/iqc/inspections/invalid/investigation-context"),
        ("POST", "/api/iqc/inspections/invalid/investigations"),
        ("GET", "/api/iqc/inspections/invalid/investigations/invalid/results/invalid"),
        ("POST", "/api/agent/runtime/iqc-investigation/infer"),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for method, path in paths:
            response = await client.request(method, path)
            assert response.status_code == 404
            assert response.headers["cache-control"] == "no-store"
