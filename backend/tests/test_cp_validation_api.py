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
from app.core.deps import get_request_scope, RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
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

    user = MagicMock(spec=User)
    user.user_id = uuid.uuid4()
    user.username = "engineer"
    user.role = "quality_engineer"
    user.role_id = uuid.uuid4()
    user.is_active = True
    user.role_definition = MagicMock()
    user.role_definition.bypass_row_level_security = True
    user.factory_id = uuid.uuid4()

    async def mock_get_current_user():
        return user

    mock_scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=user.factory_id),
        effective_factory_id=user.factory_id,
        pl_scope=ProductLineScope(mode="ALL", codes=["DC-DC-100"]),
        user=user,
    )

    async def mock_get_request_scope():
        return mock_scope

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_request_scope] = mock_get_request_scope
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)), \
         patch("app.api.cp_validation.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)), \
         patch("app.api.cp_validation._check_factory_access"):
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

    user = MagicMock(spec=User)
    user.user_id = uuid.uuid4()
    user.username = "viewer"
    user.role = "viewer"
    user.role_id = uuid.uuid4()
    user.is_active = True
    user.role_definition = MagicMock()
    user.role_definition.bypass_row_level_security = False
    user.factory_id = uuid.uuid4()

    async def mock_get_current_user():
        return user

    mock_scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=user.factory_id),
        effective_factory_id=user.factory_id,
        pl_scope=ProductLineScope(mode="ALL", codes=["DC-DC-100"]),
        user=user,
    )

    async def mock_get_request_scope():
        return mock_scope

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_request_scope] = mock_get_request_scope
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.VIEW)), \
         patch("app.api.cp_validation.get_user_permission", new=AsyncMock(return_value=PermissionLevel.VIEW)):
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
    fake_occ.description = "该控制计划项缺少控制方法"
    fake_occ.affected_items = []
    fake_occ.fmea_node_ids = []
    fake_occ.suggestion = "请添加控制方法"
    fake_occ.suggestion_data = None
    fake_occ.present = True
    fake_occ.created_at = datetime.now(timezone.utc)

    # Mock run for _get_latest_run
    fake_run = MagicMock()
    fake_run.run_id = fake_run_id
    fake_run.cp_id = fake_cp_id
    fake_run.status = "completed"
    fake_run.rule_count = 1
    fake_run.error_count = 1
    fake_run.warning_count = 0
    fake_run.info_count = 0
    fake_run.started_at = datetime.now(timezone.utc)
    fake_run.completed_at = datetime.now(timezone.utc)
    fake_run.failed_rules = []
    fake_run.trigger = "manual"
    fake_run.created_by = None

    # result.all() returns list of (occ, finding) tuples — matches real code
    list_result = MagicMock()
    list_result.all.return_value = [(fake_occ, fake_finding)]
    list_result.scalars.return_value.all.return_value = [fake_occ]

    # _get_latest_run result
    run_result = MagicMock()
    run_result.scalar_one_or_none.return_value = fake_run

    # finding result for _get_finding
    finding_result = MagicMock()
    finding_result.scalar_one_or_none.return_value = fake_finding

    # occ result for _get_latest_occurrence
    occ_result = MagicMock()
    occ_result.scalar_one.return_value = fake_occ
    occ_scalars = MagicMock()
    occ_scalars.one.return_value = fake_occ
    occ_result.scalars.return_value = occ_scalars

    # count result for summary
    count_result = MagicMock()
    count_result.all.return_value = [("open", 1)]

    async def mock_execute(*args, **kwargs):
        sql_str = str(args[0]) if args else ""
        # _get_latest_run query (ORDER BY + LIMIT on runs)
        if "cp_validation_runs" in sql_str and "ORDER BY" in sql_str:
            return run_result
        # _get_latest_occurrence query (occurrences + ORDER BY + LIMIT)
        if "cp_validation_occurrences" in sql_str and "ORDER BY" in sql_str and "LIMIT" in sql_str:
            return occ_result
        # count query (for summary)
        if "count(" in sql_str.lower() or "func.count" in sql_str:
            return count_result
        # finding-only query
        if "cp_validation_findings" in sql_str and "cp_validation_occurrences" not in sql_str:
            return finding_result
        # joined query (list results)
        return list_result

    async def mock_get_db():
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(side_effect=mock_execute)
        db.get = AsyncMock(return_value=None)
        return db

    user = MagicMock(spec=User)
    user.user_id = uuid.uuid4()
    user.username = "engineer"
    user.role = "quality_engineer"
    user.role_id = uuid.uuid4()
    user.is_active = True
    user.role_definition = MagicMock()
    user.role_definition.bypass_row_level_security = True
    user.factory_id = uuid.uuid4()

    async def mock_get_current_user():
        return user

    mock_scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=user.factory_id),
        effective_factory_id=user.factory_id,
        pl_scope=ProductLineScope(mode="ALL", codes=["DC-DC-100"]),
        user=user,
    )

    async def mock_get_request_scope():
        return mock_scope

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_request_scope] = mock_get_request_scope
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)), \
         patch("app.api.cp_validation.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)), \
         patch("app.api.cp_validation._check_factory_access"):
        yield {
            "finding_id": fake_finding_id,
            "occ_id": fake_occ_id,
            "run_id": fake_run_id,
            "cp_id": fake_cp_id,
        }
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
    ids = override_dependencies_results
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/api/control-plans/{ids['cp_id']}/validation-results")

    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] == 1
    assert len(body["items"]) == 1

    item = body["items"][0]
    assert item["rule_id"] == "R001"
    assert item["severity"] == "error"
    assert item["status"] == "open"
    assert item["title"] == "控制方法缺失"
    assert item["description"] == "该控制计划项缺少控制方法"
    assert item["suggestion"] == "请添加控制方法"


@pytest.mark.asyncio
async def test_reject_finding_returns_200(override_dependencies_results):
    ids = override_dependencies_results
    finding_id = ids["finding_id"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/validation-results/{finding_id}/reject")
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["finding_id"] == str(finding_id)


@pytest.mark.asyncio
async def test_resolve_finding_returns_200(override_dependencies_results):
    ids = override_dependencies_results
    finding_id = ids["finding_id"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/validation-results/{finding_id}/resolve")
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["finding_id"] == str(finding_id)


@pytest.mark.asyncio
async def test_viewer_cannot_validate(override_dependencies_view):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/control-plans/{uuid.uuid4()}/validate")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
