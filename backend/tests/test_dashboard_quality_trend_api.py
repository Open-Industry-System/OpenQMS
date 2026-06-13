import os
os.environ.setdefault("SECRET_KEY", "test-non-default-secret-key")

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from app.core.deps import get_request_scope, RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.permissions import PermissionLevel, get_current_user
from app.database import get_db
from app.main import app
from app.models.user import User
from app.services.dashboard_service import get_widgets_data
from app.services.quality_trend_service import build_scope_hash


@pytest.mark.anyio
async def test_dashboard_widgets_passes_quality_trend_module_permissions(monkeypatch):
    service_call = {}

    async def mock_get_db():
        return MagicMock()

    async def mock_get_current_user():
        user = MagicMock(spec=User)
        user.user_id = uuid.uuid4()
        user.role_id = uuid.uuid4()
        user.role_definition = MagicMock()
        user.role_definition.bypass_row_level_security = True
        user.factory_id = uuid.uuid4()
        return user

    mock_user = MagicMock(spec=User)
    mock_user.user_id = uuid.uuid4()
    mock_user.role_id = uuid.uuid4()
    mock_user.role_definition = MagicMock()
    mock_user.role_definition.bypass_row_level_security = True
    mock_user.factory_id = uuid.uuid4()

    mock_scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=mock_user.factory_id),
        effective_factory_id=mock_user.factory_id,
        pl_scope=ProductLineScope(mode="ALL", codes=["DC-DC-100"]),
        user=mock_user,
    )

    async def mock_get_request_scope():
        return mock_scope

    async def fake_get_widgets_data(db, types, product_line_codes, user_id, quality_trend_allowed_modules=None, **kwargs):
        service_call["types"] = types
        service_call["product_line_codes"] = product_line_codes
        service_call["quality_trend_allowed_modules"] = quality_trend_allowed_modules
        return {
            "quality_trend": {
                "summary": {
                    "risk_level": "insufficient_data",
                    "headline": "数据不足以判断趋势",
                    "evidence": [],
                    "actions": [],
                    "data_window_days": 30,
                    "generated_at": "2026-06-09T00:00:00Z",
                    "evidence_hash": "sha256:test",
                    "scope_hash": "sha256:scope_test",
                    "ai_available": False,
                    "metadata": {"omitted_modules": [], "available_modules": []},
                }
            },
            "errors": {},
        }

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_request_scope] = mock_get_request_scope
    monkeypatch.setattr("app.services.dashboard_service.get_widgets_data", fake_get_widgets_data)

    async def mock_get_user_permission(user, module, db):
        return PermissionLevel.VIEW if module.value in {"dashboard", "spc", "capa", "fmea"} else PermissionLevel.NONE

    try:
        with patch("app.core.permissions.get_user_permission", new=mock_get_user_permission), \
             patch("app.api.dashboard.get_user_permission", new=mock_get_user_permission):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get(
                    "/api/dashboard/widgets",
                    params={"types": "quality_trend_ai_summary", "product_line": "DC-DC-100"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "quality_trend" in body
    assert "summary" in body["quality_trend"]
    assert service_call["types"] == ["quality_trend_ai_summary"]
    assert service_call["product_line_codes"] == ["DC-DC-100"]
    assert service_call["quality_trend_allowed_modules"] == {"spc", "capa", "fmea"}


@pytest.mark.anyio
async def test_widgets_data_returns_scope_hash_for_quality_trend(monkeypatch):
    """Verify that get_widgets_data populates scope_hash in the quality_trend summary."""
    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[0, 0, 0, 0, 0])
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    data = await get_widgets_data(
        db=db,
        types=["quality_trend_ai_summary"],
        product_line_codes=["DC-DC-100"],
        user_id="test-user",
        quality_trend_allowed_modules={"spc", "capa"},
    )
    summary = data["quality_trend"]["summary"]
    assert summary["scope_hash"] != ""
    assert summary["scope_hash"].startswith("sha256:")
    # Changing product line should change scope_hash
    db2 = AsyncMock()
    db2.scalar = AsyncMock(side_effect=[0, 0, 0, 0, 0])
    db2.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    data2 = await get_widgets_data(
        db=db2,
        types=["quality_trend_ai_summary"],
        product_line_codes=["AC-DC-200"],
        user_id="test-user",
        quality_trend_allowed_modules={"spc", "capa"},
    )
    assert data2["quality_trend"]["summary"]["scope_hash"] != summary["scope_hash"]
