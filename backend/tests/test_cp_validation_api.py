"""Integration tests for cp_validation API endpoints."""
import uuid
import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import status
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_db
from app.core.permissions import get_current_user, Module, PermissionLevel
from app.models.user import User


@pytest.fixture
def override_dependencies():
    """Inject mock DB and authenticated user with PLANNING + EDIT permission."""
    async def mock_get_db():
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        db.get = AsyncMock(return_value=None)
        return db

    async def mock_get_current_user():
        user = MagicMock(spec=User)
        user.user_id = uuid.uuid4()
        user.username = "engineer"
        user.role = "quality_engineer"
        user.role_id = uuid.uuid4()
        user.is_active = True
        user.role_definition = MagicMock()
        user.role_definition.bypass_row_level_security = True
        return user

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)):
        yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_dependencies_view():
    """Same but with VIEW-only permission."""
    async def mock_get_db():
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        return db

    async def mock_get_current_user():
        user = MagicMock(spec=User)
        user.user_id = uuid.uuid4()
        user.username = "viewer"
        user.role = "viewer"
        user.role_id = uuid.uuid4()
        user.is_active = True
        user.role_definition = MagicMock()
        user.role_definition.bypass_row_level_security = False
        return user

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.VIEW)):
        yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_dependencies_results():
    """Mock DB returning rows for list-results + finding + occurrence (reject/resolve)."""
    from datetime import datetime, timezone

    fake_finding_id = uuid.uuid4()
    fake_occ_id = uuid.uuid4()
    fake_run_id = uuid.uuid4()
    fake_cp_id = uuid.uuid4()

    fake_finding = MagicMock()
    fake_finding.finding_id = fake_finding_id
    fake_finding.cp_id = fake_cp_id
    fake_finding.finding_hash = "abc123"
    fake_finding.rule_id = "R001"
    fake_finding.severity = "error"
    fake_finding.category = "completeness"
    fake_finding.status = "open"
    fake_finding.resolved_by = None
    fake_finding.resolved_at = None
    fake_finding.created_at = datetime.now(timezone.utc)

    fake_occ = MagicMock()
    fake_occ.occurrence_id = fake_occ_id
    fake_occ.run_id = fake_run_id
    fake_occ.finding_id = fake_finding_id
    fake_occ.cp_id = fake_cp_id
    fake_occ.validation_type = "rule"
    fake_occ.title = "控制方法缺失"
    fake_occ.description = "test"
    fake_occ.affected_items = []
    fake_occ.fmea_node_ids = []
    fake_occ.suggestion = None
    fake_occ.suggestion_data = None
    fake_occ.present = True
    fake_occ.created_at = datetime.now(timezone.utc)

    mock_row = MagicMock()
    mock_row.finding_id = fake_finding_id
    mock_row.occurrence_id = fake_occ_id
    mock_row.rule_id = "R001"
    mock_row.severity = "error"
    mock_row.status = "open"
    mock_row.title = "控制方法缺失"
    mock_row.description = "test"
    mock_row.present = True
    mock_row.fmea_node_ids = []

    list_result = MagicMock()
    list_result.mappings.return_value = [mock_row]

    finding_result = MagicMock()
    finding_result.scalar_one_or_none.return_value = fake_finding

    occ_result = MagicMock()
    occ_result.scalar_one.return_value = fake_occ

    call_count = 0

    async def mock_execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        sql_str = str(args[0]) if args else ""
        if "cp_validation_findings" in sql_str and "cp_validation_occurrences" not in sql_str:
            return finding_result
        if "cp_validation_occurrences" in sql_str and "ORDER BY" in sql_str:
            return occ_result
        return list_result

    async def mock_get_db():
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(side_effect=mock_execute)
        db.get = AsyncMock(return_value=None)
        return db

    async def mock_get_current_user():
        user = MagicMock(spec=User)
        user.user_id = uuid.uuid4()
        user.username = "engineer"
        user.role = "quality_engineer"
        user.role_id = uuid.uuid4()
        user.is_active = True
        user.role_definition = MagicMock()
        user.role_definition.bypass_row_level_security = True
        return user

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)):
        yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_validate_unauthenticated():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/control-plans/{uuid.uuid4()}/validate")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_results_unauthenticated():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/api/control-plans/{uuid.uuid4()}/validation-results")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_summary_unauthenticated():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/api/control-plans/{uuid.uuid4()}/validation-summary")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_validate_returns_200(override_dependencies):
    from unittest.mock import patch as mock_patch
    mock_run = MagicMock()
    mock_run.run_id = uuid.uuid4()
    mock_run.cp_id = uuid.uuid4()
    mock_run.trigger = "manual"
    mock_run.status = "completed"
    mock_run.rule_count = 4
    mock_run.error_count = 1
    mock_run.warning_count = 0
    mock_run.info_count = 0
    mock_run.started_at = "2026-06-10T12:00:00"
    mock_run.completed_at = "2026-06-10T12:00:01"
    mock_run.failed_rules = []
    mock_run.created_by = None

    with mock_patch(
        "app.services.cp_validation.engine.CPValidationEngine.validate",
        new=AsyncMock(return_value=mock_run),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(f"/api/control-plans/{uuid.uuid4()}/validate")

    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["status"] == "completed"
    assert body["error_count"] == 1


@pytest.mark.asyncio
async def test_validate_returns_409_when_already_running(override_dependencies):
    from unittest.mock import patch as mock_patch
    from app.services.cp_validation.engine import ValidationAlreadyRunning

    with mock_patch(
        "app.services.cp_validation.engine.CPValidationEngine.validate",
        new=AsyncMock(side_effect=ValidationAlreadyRunning()),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(f"/api/control-plans/{uuid.uuid4()}/validate")

    assert resp.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_results_returns_200(override_dependencies_results):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/api/control-plans/{uuid.uuid4()}/validation-results")

    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 0


@pytest.mark.asyncio
async def test_reject_finding_returns_200(override_dependencies_results):
    finding_id = uuid.uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/validation-results/{finding_id}/reject")
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_resolve_finding_returns_200(override_dependencies_results):
    finding_id = uuid.uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/validation-results/{finding_id}/resolve")
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_viewer_cannot_validate(override_dependencies_view):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/control-plans/{uuid.uuid4()}/validate")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
