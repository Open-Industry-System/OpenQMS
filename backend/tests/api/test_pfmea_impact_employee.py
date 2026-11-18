"""Employee v1 uses dedicated report-bound paths and sealed no-store responses."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from app.api import pfmea_impact_tasks as api
from app.config import settings
from app.core.deps import get_request_scope
from app.database import get_db

REPORT, FMEA, VERSION, INSTALL, DEPLOY, TASK, RESULT = (UUID(int=i) for i in range(1, 8))


@pytest.fixture
def harness(monkeypatch):
    calls = []
    from app.core.tenant_transaction import TenantBinding
    from app.services.agent_runtime.pfmea_impact_pilot import ImpactPilot

    tenant = TenantBinding(UUID(int=70), "tenant_test", 1, "business")
    pilot = ImpactPilot(None, tenant.tenant_id, tenant.generation, INSTALL, 0, "1", 8080,
        datetime.now(UTC) + timedelta(minutes=1))
    db = SimpleNamespace(info={"r7_impact_pilot": pilot, "tenant_binding": tenant})

    async def commit():
        calls.append("commit")

    async def rollback():
        calls.append("rollback")

    async def ready_db():
        calls.append("db")
        yield db

    def scope():
        calls.append("scope")
        return SimpleNamespace(user=SimpleNamespace(user_id=UUID(int=8)))

    db.commit, db.rollback = commit, rollback
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_db] = ready_db
    app.dependency_overrides[get_request_scope] = scope
    monkeypatch.setattr(settings, "AGENT_TASK_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "AGENT_R7_PFMEA_IMPACT_ENABLED", True)
    transport = httpx.ASGITransport(app=app)
    return SimpleNamespace(calls=calls, db=db, transport=transport, base=f"/api/capa/{REPORT}/pfmea-impact")


@pytest.mark.asyncio
async def test_default_off_denies_before_employee_or_database_lookup(harness, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_R7_PFMEA_IMPACT_ENABLED", False)
    async with httpx.AsyncClient(transport=harness.transport, base_url="http://test") as session:
        response = await session.get(harness.base + "/targets")
    assert response.status_code == 404 and response.headers["cache-control"] == "no-store"
    assert harness.calls == []


@pytest.mark.asyncio
async def test_create_binding_accepts_only_explicit_client_choices_under_report_path(harness, monkeypatch):
    seen = []

    async def create(db, scope, body):
        seen.append(body)
        return SimpleNamespace(task_id=TASK, replayed=False)

    monkeypatch.setattr(api.tasks, "create_task", create)
    body = {
        "fmea_id": str(FMEA), "approved_version_id": str(VERSION),
        "installation_id": str(INSTALL), "model_deployment_id": str(DEPLOY), "request_key": "unchanged-key",
    }
    async with httpx.AsyncClient(transport=harness.transport, base_url="http://test") as session:
        response = await session.post(harness.base + "/tasks", json=body)
        rejected = await session.post(harness.base + "/tasks", json={**body, "report_id": str(VERSION)})
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"taskId": str(TASK), "status": "blocked_capability", "resultId": None}
    assert seen[0].report_id == REPORT and seen[0].request_key == "unchanged-key"
    assert rejected.status_code == 422 and len(seen) == 1


@pytest.mark.asyncio
async def test_history_commit_requires_current_reader_authority_and_hides_denial(harness, monkeypatch):
    async def denied(db, scope, ref, *, authorize):
        assert (ref.report_id, ref.task_id, ref.result_id) == (REPORT, TASK, RESULT)
        raise PermissionError("active reader lost evidence id=secret")

    monkeypatch.setattr(api.history, "read_history_review", denied, raising=False)
    async with httpx.AsyncClient(transport=harness.transport, base_url="http://test") as session:
        response = await session.get(harness.base + f"/tasks/{TASK}/results/{RESULT}")
    assert response.status_code == 404 and response.headers["cache-control"] == "no-store"
    assert "secret" not in response.text and harness.calls[-1] == "rollback"


@pytest.mark.asyncio
async def test_configured_pilot_does_not_enable_a_different_tenant(harness, monkeypatch):
    from dataclasses import replace

    binding = harness.db.info["tenant_binding"]
    harness.db.info["tenant_binding"] = replace(binding, tenant_id=UUID(int=71))

    async def targets(*args, **kwargs):
        pytest.fail("Wrong tenant must not enumerate PFMEA candidates")

    monkeypatch.setattr(api.tasks, "list_targets", targets)
    async with httpx.AsyncClient(transport=harness.transport, base_url="http://test") as session:
        response = await session.get(harness.base + "/targets")
    assert response.status_code == 404 and response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_history_page_scans_past_denied_batches_without_exposing_hidden_total(harness, monkeypatch):
    now = datetime.now(UTC)
    hidden = [(TASK, UUID(int=i), now) for i in range(100, 0, -1)]
    allowed = [(TASK, UUID(int=200), now), (TASK, UUID(int=199), now)]
    batches = iter([hidden[:50], hidden[50:], allowed])

    async def report(*args):
        return SimpleNamespace(factory_id=UUID(int=70))

    async def execute(*args):
        return SimpleNamespace(all=lambda: next(batches))

    async def read(db, scope, ref, **kwargs):
        if ref.result_id.int <= 100:
            raise api.history.ImpactHistoryUnavailable()
        return SimpleNamespace(major_no=3, stale=False, created_at=now)

    harness.db.execute = execute
    harness.db.in_transaction = lambda: True
    monkeypatch.setattr(api.tasks, "_report_scope", report)
    monkeypatch.setattr(api.history, "read_history_metadata", read)
    async with httpx.AsyncClient(transport=harness.transport, base_url="http://test") as session:
        response = await session.get(harness.base + "/results?page_size=1")
    assert response.status_code == 200 and harness.calls[-1] == "commit"
    assert response.json() == {
        "items": [{"taskId": str(TASK), "resultId": str(allowed[0][1]), "approvedVersionLabel": "v3.0",
                   "freshness": "current", "createdAt": now.isoformat()}],
        "hasMore": True,
    }


@pytest.mark.asyncio
async def test_retired_execution_policy_allows_verified_history_only(harness, monkeypatch):
    from dataclasses import replace

    pilot = harness.db.info["r7_impact_pilot"]
    harness.db.info["r7_impact_pilot"] = replace(pilot, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    visible = []

    async def report(*args):
        return SimpleNamespace(factory_id=UUID(int=70))

    async def history_page(*args, **kwargs):
        return {"items": visible, "hasMore": False}

    async def review(db, scope, lookup, *, authorize):
        assert lookup == api.history.HistoryLookup(REPORT, TASK, RESULT)
        return {"freshness": "stale"}

    monkeypatch.setattr(api.tasks, "_report_scope", report)
    monkeypatch.setattr(api, "_history_page", history_page, raising=False)
    monkeypatch.setattr(api.history, "read_history_review", review)
    async with httpx.AsyncClient(transport=harness.transport, base_url="http://test") as session:
        empty = await session.get(harness.base + "/availability")
        assert empty.json() == {"available": False, "canGenerate": False}
        visible.append({"taskId": str(TASK), "resultId": str(RESULT)})
        available = await session.get(harness.base + "/availability")
        assert available.json() == {"available": True, "canGenerate": False}
        targets = await session.get(harness.base + "/targets")
        assert targets.status_code == 404
        index = await session.get(harness.base + "/results")
        assert index.json() == {"items": visible, "hasMore": False}
        detail = await session.get(harness.base + f"/tasks/{TASK}/results/{RESULT}")
        assert detail.status_code == 200 and detail.json() == {"freshness": "stale"}
