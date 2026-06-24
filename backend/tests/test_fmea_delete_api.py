"""API-level tests for the FMEA delete status guard.

The DELETE /api/fmea/{fmea_id} endpoint must reject non-deletable statuses
(approved, in_review, archived) with 400 and allow draft / rework.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.deps import RequestScope, get_current_user, get_db, get_request_scope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.permissions import PermissionLevel
from app.main import app
from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument

import app.models as _models  # noqa: F401 — register all FK-referenced tables


def _make_doc(factory_id, user_id, status):
    return FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=f"PFMEA-{uuid.uuid4().hex[:8]}",
        title="to delete",
        fmea_type="PFMEA",
        product_line_code="T" + uuid.uuid4().hex[:12],
        factory_id=factory_id,
        created_by=user_id,
        status=status,
        graph_data={"nodes": [], "edges": []},
    )


@pytest.mark.asyncio
async def test_delete_rejects_non_deletable_allows_deletable(db, default_factory, admin_user):
    """approved/in_review/archived → 400; draft/rework → 204."""
    statuses = {
        "approved": _make_doc(default_factory.id, admin_user.user_id, "approved"),
        "in_review": _make_doc(default_factory.id, admin_user.user_id, "in_review"),
        "archived": _make_doc(default_factory.id, admin_user.user_id, "archived"),
        "draft": _make_doc(default_factory.id, admin_user.user_id, "draft"),
        "rework": _make_doc(default_factory.id, admin_user.user_id, "rework"),
    }
    db.add_all(list(statuses.values()))
    await db.flush()

    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=default_factory.id),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode="ALL", codes=["DC-DC-100"]),
        user=admin_user,
    )

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_request_scope] = lambda: scope
    try:
        with patch("app.api.fmea.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                for status in ("approved", "in_review", "archived"):
                    resp = await ac.delete(f"/api/fmea/{statuses[status].fmea_id}")
                    assert resp.status_code == 400, f"{status} should be rejected"
                for status in ("draft", "rework"):
                    resp = await ac.delete(f"/api/fmea/{statuses[status].fmea_id}")
                    assert resp.status_code == 204, f"{status} should be allowed"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_rework_with_linked_capa_nulls_ref(db, default_factory, admin_user):
    """A rework FMEA referenced by a CAPA's fmea_ref_id must delete cleanly
    (the service nulls the FK) rather than raise IntegrityError → 500."""
    rework = _make_doc(default_factory.id, admin_user.user_id, "rework")
    db.add(rework)
    await db.flush()
    db.add(CAPAEightD(
        document_no=f"8D-{uuid.uuid4().hex[:8]}",
        title="linked capa",
        factory_id=default_factory.id,
        product_line_code=rework.product_line_code,
        created_by=admin_user.user_id,
        fmea_ref_id=rework.fmea_id,
    ))
    await db.flush()

    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=default_factory.id),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode="ALL", codes=["DC-DC-100"]),
        user=admin_user,
    )

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_request_scope] = lambda: scope
    try:
        with patch("app.api.fmea.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete(f"/api/fmea/{rework.fmea_id}")
                assert resp.status_code == 204
    finally:
        app.dependency_overrides.clear()
