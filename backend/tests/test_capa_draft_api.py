# backend/tests/test_capa_draft_api.py
import pytest
import uuid
from fastapi import status
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.database import get_db
from app.core.permissions import get_current_user, Module, PermissionLevel
from app.models.user import User


@pytest.fixture
def override_dependencies():
    """注入 mock 数据库和认证用户"""
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
    # Patch get_user_permission so mock DB doesn't fail RolePermission queries
    # Must patch at module where the function is defined (permissions.py), since
    # require_permission's closure captures the original reference
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)):
        yield
    app.dependency_overrides.clear()


# ---------- 路由顺序验证 ----------

@pytest.mark.asyncio
async def test_capabilities_not_intercepted_by_report_id():
    """GET /api/capa/capabilities 不应被 /{report_id} 拦截"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/capa/capabilities")
    # 不认证 → 401，说明路由匹配到 capabilities 而非 {report_id}
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ---------- 认证测试 ----------

@pytest.mark.asyncio
async def test_draft_unauthenticated():
    """未认证应返回 401"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/capa/{}/draft/d2".format(str(uuid.uuid4())),
            json={"format": "structured", "request_id": str(uuid.uuid4())},
        )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_capabilities_unauthenticated():
    """未认证访问 /{report_id}/draft/capabilities 应返回 401"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/capa/{}/draft/capabilities".format(str(uuid.uuid4())))
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ---------- capabilities 已认证 ----------

@pytest.mark.asyncio
async def test_global_capabilities_authenticated(override_dependencies):
    """GET /api/capa/capabilities 认证后返回 ai_draft_enabled"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/capa/capabilities")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "ai_draft_enabled" in data
    assert isinstance(data["ai_draft_enabled"], bool)


# ---------- invalid request_id → 400 ----------

@pytest.mark.asyncio
async def test_invalid_request_id_returns_400(override_dependencies):
    """POST draft with invalid request_id → 400 (not 422)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/capa/{}/draft/d2".format(str(uuid.uuid4())),
            json={"format": "structured", "request_id": "not-a-uuid"},
        )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "request_id" in resp.json()["detail"]


# ---------- invalid step → 400 ----------

@pytest.mark.asyncio
async def test_invalid_step_returns_400(override_dependencies):
    """POST draft with invalid step → 400"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/capa/{}/draft/d9".format(str(uuid.uuid4())),
            json={"format": "structured", "request_id": str(uuid.uuid4())},
        )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "无效的步骤" in resp.json()["detail"]