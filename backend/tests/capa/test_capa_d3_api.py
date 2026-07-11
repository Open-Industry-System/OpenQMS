"""API tests for D3 containment endpoints (US-E2E-01.1 Task 6)."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.capa import CAPAEightD
from app.models.capa_d3 import CapaD3ImpactReport, CapaD3ImportRun
from app.models.factory import Factory
from app.models.role import RolePermission
from app.models.user import User
from app.services.capa_d3_containment_service import (
    generate_impact_report,
    import_containment_data,
)
from tests.conftest import _scope_for
from tests.capa.conftest import _seed_d3_source_data

pytestmark = pytest.mark.requires_db


async def _seed_perm(db, role_id, module, level):
    """Upsert role permission level."""
    existing = await db.execute(
        select(RolePermission).where(
            RolePermission.role_id == role_id, RolePermission.module == module
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        db.add(RolePermission(role_id=role_id, module=module, permission_level=level))
    else:
        row.permission_level = level
    await db.flush()


@pytest.fixture
async def client(db, admin_user, default_factory):
    """ASGI client authenticated as engineer (CAPA EDIT = 3)."""
    await _seed_perm(db, admin_user.role_id, "capa", 3)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def viewer_client(db, admin_user, default_factory):
    """ASGI client authenticated as viewer (CAPA VIEW = 1)."""
    await _seed_perm(db, admin_user.role_id, "capa", 1)
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def other_factory_client(db, admin_user, default_factory):
    """ASGI client whose scope is restricted to a different factory."""
    other_factory = Factory(
        id=uuid.uuid4(),
        code="OTHER-D3",
        name="Other D3 Factory",
        is_active=True,
    )
    db.add(other_factory)
    await db.flush()
    await _seed_perm(db, admin_user.role_id, "capa", 3)
    scope = _scope_for(
        admin_user, default_factory, accessible_factory_ids=[other_factory.id]
    )
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def capa_d3_url(db, capa_d3_setup):
    """CAPA at D3_INTERIM plus its URL stem (unused)."""
    capa, _user = capa_d3_setup
    return capa, f"/api/capa/{capa.report_id}/d3"


@pytest_asyncio.fixture
async def capa_d2_url(db, capa_d3_setup):
    """CAPA at D2_DESCRIPTION for stage-guard tests."""
    capa, _user = capa_d3_setup
    capa.status = "D2_DESCRIPTION"
    await db.flush()
    return capa, f"/api/capa/{capa.report_id}/d3"


@pytest_asyncio.fixture
async def capa_d3_imported(db, capa_d3_setup, no_creds):
    """Imported run + 4 snapshots, no report (report_status=blocked)."""
    capa, user = capa_d3_setup
    await _seed_d3_source_data(db, capa.factory_id, user.user_id)
    result = await import_containment_data(db, capa.report_id, user, {})
    run = await db.get(CapaD3ImportRun, uuid.UUID(result["run_id"]))
    return capa, run


@pytest_asyncio.fixture
async def capa_d3_done_report(db, capa_d3_imported, llm_mock):
    """Imported run with a done impact report."""
    llm_mock.return_value = {"risk_level": "medium", "risk_explanation": "ok"}
    capa, run = capa_d3_imported
    user = await db.get(User, run.imported_by)
    await generate_impact_report(db, run.run_id, user)
    return capa, run


@pytest_asyncio.fixture
async def capa_d3_report_running(db, capa_d3_imported):
    """Imported run with a manually inserted running report."""
    capa, run = capa_d3_imported
    user = await db.get(User, run.imported_by)
    report = CapaD3ImpactReport(
        report_id=uuid.uuid4(),
        run_id=run.run_id,
        factory_id=run.factory_id,
        is_current=False,
        status="running",
        attempt_token=uuid.uuid4(),
        started_at=datetime.utcnow(),
        generated_by=user.user_id,
        stage_runs=[],
        prompt_stats={},
        llm_available=False,
        batches=[],
        impact_qty=[],
        customer_impact=[],
        time_window={},
    )
    db.add(report)
    await db.flush()
    return capa, report


async def test_import_returns_200_with_report_status(client, capa_d3_url, llm_mock):
    capa, _ = capa_d3_url
    resp = await client.post(
        f"/api/capa/{capa.report_id}/d3/import",
        json={"snapshot_types": ["inventory", "shipment", "iqc", "spc"]},
    )
    assert resp.status_code == 200
    assert resp.json()["report_status"] in {"done", "failed", "blocked", "superseded"}


async def test_import_viewer_forbidden(viewer_client, capa_d3_url):
    capa, _ = capa_d3_url
    resp = await viewer_client.post(
        f"/api/capa/{capa.report_id}/d3/import",
        json={"snapshot_types": ["inventory", "shipment", "iqc", "spc"]},
    )
    assert resp.status_code == 403


async def test_import_non_d3_stage_rejected(client, capa_d2_url):
    capa, _ = capa_d2_url
    resp = await client.post(
        f"/api/capa/{capa.report_id}/d3/import",
        json={"snapshot_types": ["inventory", "shipment", "iqc", "spc"]},
    )
    assert resp.status_code in (400, 403)


async def test_import_cross_factory_404(other_factory_client, capa_d3_url):
    capa, _ = capa_d3_url
    resp = await other_factory_client.post(
        f"/api/capa/{capa.report_id}/d3/import",
        json={"snapshot_types": ["inventory", "shipment", "iqc", "spc"]},
    )
    assert resp.status_code == 404


async def test_get_runs_lists_current(client, capa_d3_imported):
    capa, _ = capa_d3_imported
    resp = await client.get(f"/api/capa/{capa.report_id}/d3/runs")
    assert resp.status_code == 200
    assert any(r["is_current"] for r in resp.json())


async def test_get_snapshots_current_run(client, capa_d3_imported):
    capa, _ = capa_d3_imported
    resp = await client.get(f"/api/capa/{capa.report_id}/d3/snapshots")
    assert resp.status_code == 200
    assert {s["snapshot_type"] for s in resp.json()} == {
        "inventory",
        "shipment",
        "iqc",
        "spc",
    }


async def test_report_post_no_creds_422_blocked(client, capa_d3_imported, no_creds):
    capa, _ = capa_d3_imported
    resp = await client.post(f"/api/capa/{capa.report_id}/d3/report")
    assert resp.status_code == 422 and resp.json()["detail"]["blocked"] is True


async def test_report_post_running_returns_202_body_and_retry_after_header(
    client, capa_d3_report_running, llm_slow
):
    capa, _ = capa_d3_report_running
    resp = await client.post(f"/api/capa/{capa.report_id}/d3/report")
    assert resp.status_code == 202
    assert resp.json()["status"] == "running" and "report_id" in resp.json()
    assert int(resp.headers["retry-after"]) >= 1


async def test_report_post_done_returns_200(client, capa_d3_imported, llm_mock):
    capa, _ = capa_d3_imported
    resp = await client.post(f"/api/capa/{capa.report_id}/d3/report")
    assert resp.status_code == 200 and resp.json()["status"] in {"done", "failed", "superseded"}


async def test_report_get_current(client, capa_d3_done_report):
    capa, _ = capa_d3_done_report
    resp = await client.get(f"/api/capa/{capa.report_id}/d3/report")
    assert resp.status_code == 200 and resp.json()["status"] == "done"
