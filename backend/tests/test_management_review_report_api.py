import uuid
import pytest
from fastapi import status
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.database import get_db
from app.core.permissions import get_current_user, Module, PermissionLevel
from app.models.user import User
from app.models.management_review import ManagementReview
from app.services import management_review_report_service as report_service


def _mock_review(status="data_collected", report_status="none"):
    review = MagicMock(spec=ManagementReview)
    review.review_id = uuid.uuid4()
    review.status = status
    review.report_status = report_status
    review.data_package = {"quality_goals": {"total": 1}}
    review.manual_inputs = {}
    review.generated_report = {"sections": []} if report_status == "draft" else None
    review.doc_no = "MR-MOCK-001"
    review.title = "Mock Review"
    review.product_line_code = "DC-DC-100"
    return review


def _sample_report_content():
    return {
        "generated_at": "2026-06-11T10:00:00+00:00",
        "generation_model": "rule-only",
        "llm_enriched": False,
        "sections": [
            {
                "key": "quality_goals",
                "title": "2. 质量目标实现程度",
                "source": "data_package",
                "base_text": "total: 1",
                "ai_analysis": "",
                "findings": [],
                "recommendations": [],
                "manual_text": "",
                "data_snapshot": {"total": 1},
            }
        ],
        "executive_summary": "test summary",
        "overall_recommendations": [],
    }


@pytest.mark.asyncio
async def test_generate_report_unauthenticated():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/management-reviews/{uuid.uuid4()}/report/generate", json={"use_llm": False})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_viewer_cannot_generate_report():
    """VIEW-level permission should be rejected with 403."""
    async def mock_user():
        u = MagicMock(spec=User)
        u.user_id = uuid.uuid4()
        u.is_active = True
        u.role_id = uuid.uuid4()
        u.role_definition = MagicMock()
        u.role_definition.bypass_row_level_security = False
        return u

    review = _mock_review()
    mock_db = MagicMock()
    mock_db.get = AsyncMock(return_value=review)
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()

    app.dependency_overrides[get_current_user] = mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.VIEW)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/management-reviews/{review.review_id}/report/generate",
                json={"use_llm": False},
            )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_permission_levels():
    """CREATE level should succeed; VIEW should be forbidden."""
    async def run_with_permission(level):
        async def mock_user():
            u = MagicMock(spec=User)
            u.user_id = uuid.uuid4()
            u.is_active = True
            u.role_id = uuid.uuid4()
            u.role_definition = MagicMock()
            u.role_definition.bypass_row_level_security = True
            return u

        review = _mock_review()
        mock_db = MagicMock()
        mock_db.get = AsyncMock(return_value=review)
        mock_db.commit = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.execute = AsyncMock()

        app.dependency_overrides[get_current_user] = mock_user
        app.dependency_overrides[get_db] = lambda: mock_db
        with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=level)):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                return await ac.post(
                    f"/api/management-reviews/{review.review_id}/report/generate",
                    json={"use_llm": False},
                )
        app.dependency_overrides.clear()

    # VIEW should be forbidden
    resp = await run_with_permission(PermissionLevel.VIEW)
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    app.dependency_overrides.clear()

    # CREATE should succeed with mocked service
    async def mock_generate(db, review, user, llm_provider=None, use_llm=True):
        review.report_status = "draft"
        review.generated_report = _sample_report_content()
        return review.generated_report

    with patch.object(report_service, "generate_report", new=mock_generate):
        resp = await run_with_permission(PermissionLevel.CREATE)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["report_status"] == "draft"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_closed_review_rejects_save_draft():
    async def mock_user():
        u = MagicMock(spec=User)
        u.user_id = uuid.uuid4()
        u.is_active = True
        u.role_id = uuid.uuid4()
        u.role_definition = MagicMock()
        u.role_definition.bypass_row_level_security = True
        return u

    review = _mock_review(status="closed", report_status="draft")
    mock_db = MagicMock()
    mock_db.get = AsyncMock(return_value=review)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    app.dependency_overrides[get_current_user] = mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.CREATE)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/management-reviews/{review.review_id}/report/save-draft",
                json={"generated_report": _sample_report_content()},
            )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "closed" in resp.json()["detail"].lower()
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_final_report_rejects_regenerate():
    async def mock_user():
        u = MagicMock(spec=User)
        u.user_id = uuid.uuid4()
        u.is_active = True
        u.role_id = uuid.uuid4()
        u.role_definition = MagicMock()
        u.role_definition.bypass_row_level_security = True
        return u

    review = _mock_review(status="data_collected", report_status="final")
    mock_db = MagicMock()
    mock_db.get = AsyncMock(return_value=review)
    mock_db.commit = AsyncMock()

    app.dependency_overrides[get_current_user] = mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.CREATE)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/management-reviews/{review.review_id}/report/generate",
                json={"use_llm": False},
            )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    app.dependency_overrides.clear()
