import uuid
import pytest
from fastapi import status
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.main import app
from app.database import get_db
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.models.user import User
from app.models.management_review import ManagementReview

# Shared mock scope — admin with full factory access
_DEFAULT_FACTORY_ID = UUID("00000000-0000-0000-0000-000000000001")


def _make_mock_user(bypass_rls=True):
    """Create a mock User with sensible defaults."""
    u = MagicMock(spec=User)
    u.user_id = uuid.uuid4()
    u.is_active = True
    u.role_id = uuid.uuid4()
    u.role_definition = MagicMock()
    u.role_definition.bypass_row_level_security = bypass_rls
    u.factory_id = _DEFAULT_FACTORY_ID
    return u


def _mock_scope(user=None):
    """Build a mock RequestScope with GROUP-admin-level factory access."""
    if user is None:
        user = _make_mock_user()
    return RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=_DEFAULT_FACTORY_ID),
        effective_factory_id=_DEFAULT_FACTORY_ID,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=user,
    )


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
    review.factory_id = _DEFAULT_FACTORY_ID
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
    scope = _mock_scope(user=_make_mock_user(bypass_rls=False))

    app.dependency_overrides[get_request_scope] = lambda: scope
    with patch("app.api.management_review.get_user_permission", new=AsyncMock(return_value=PermissionLevel.VIEW)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/management-reviews/{_mock_review().review_id}/report/generate",
                json={"use_llm": False},
            )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_permission_levels():
    """CREATE level should succeed; VIEW should be forbidden."""
    scope = _mock_scope(user=_make_mock_user(bypass_rls=True))
    review = _mock_review()

    # VIEW should be forbidden
    app.dependency_overrides[get_request_scope] = lambda: scope
    with patch("app.api.management_review.get_user_permission", new=AsyncMock(return_value=PermissionLevel.VIEW)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/management-reviews/{review.review_id}/report/generate",
                json={"use_llm": False},
            )
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # CREATE should succeed — mock both service.get_review and report generation
    mock_db = MagicMock()
    mock_db.get = AsyncMock(return_value=review)
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()

    async def mock_generate(db, review, user, llm_provider=None, use_llm=True, **kwargs):
        review.report_status = "draft"
        review.generated_report = _sample_report_content()
        return review.generated_report

    app.dependency_overrides[get_request_scope] = lambda: scope
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.management_review.get_user_permission", new=AsyncMock(return_value=PermissionLevel.CREATE)), \
         patch("app.api.management_review.report_service.generate_report", new=mock_generate), \
         patch("app.api.management_review.management_review_service.get_review", new=AsyncMock(return_value=review)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/management-reviews/{review.review_id}/report/generate",
                json={"use_llm": False},
            )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["report_status"] == "draft"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_closed_review_rejects_save_draft():
    scope = _mock_scope()
    review = _mock_review(status="closed", report_status="draft")

    async def _raise_closed(*args, **kwargs):
        raise ValueError("cannot edit report of a closed review")

    app.dependency_overrides[get_request_scope] = lambda: scope
    with patch("app.api.management_review.get_user_permission", new=AsyncMock(return_value=PermissionLevel.CREATE)), \
         patch("app.api.management_review.management_review_service.get_review", new=AsyncMock(return_value=review)), \
         patch("app.api.management_review.report_service.save_report_draft", new=_raise_closed):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/management-reviews/{review.review_id}/report/save-draft",
                json={"generated_report": _sample_report_content()},
            )
    # A closed review rejects save-draft with 400
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_final_report_rejects_regenerate():
    scope = _mock_scope()
    review = _mock_review(status="data_collected", report_status="final")

    async def _raise_final(*args, **kwargs):
        raise ValueError("report is finalized, reopen before editing")

    app.dependency_overrides[get_request_scope] = lambda: scope
    with patch("app.api.management_review.get_user_permission", new=AsyncMock(return_value=PermissionLevel.CREATE)), \
         patch("app.api.management_review.management_review_service.get_review", new=AsyncMock(return_value=review)), \
         patch("app.api.management_review.report_service.generate_report", new=_raise_final):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/management-reviews/{review.review_id}/report/generate",
                json={"use_llm": False},
            )
    # A finalized report rejects regeneration with 400
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    app.dependency_overrides.clear()