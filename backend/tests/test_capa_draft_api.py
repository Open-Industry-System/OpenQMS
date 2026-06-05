# backend/tests/test_capa_draft_api.py
import pytest
import uuid
from fastapi import status
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.database import get_db
from app.core.permissions import get_current_user
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
        user.role_definition.bypass_row_level_security = True
        return user

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_draft_unauthenticated():
    """未认证应返回 401"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/capa/123/draft/d2", json={"format": "structured"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_capabilities_unauthenticated():
    """未认证访问 capabilities 应返回 401"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/capa/123/draft/capabilities")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
