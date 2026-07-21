"""API contract tests for lateral diffusion decide/rerun (US-E2E-01.9 Task 5)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.deps import get_current_user, get_db, get_request_scope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.deps import RequestScope
from app.main import app
from app.models.capa_lateral_diffusion import CapaLateralDiffusionCheck
from app.schemas.capa_lateral_diffusion import LateralDecisionRequest
from app.services.capa_lateral_diffusion_service import _check_id_for
from tests.capa.test_lateral_diffusion_match import _make_capa, _make_pl, _seed_base

pytestmark = pytest.mark.requires_db


async def _auth_client(db, user, factory):
    async def _override_db():
        yield db

    async def _override_user():
        return user

    async def _override_scope():
        return RequestScope(
            user=user,
            factory_scope=FactoryScope(
                accessible_factory_ids=[factory.id],
                default_factory_id=factory.id,
            ),
            pl_scope=ProductLineScope(mode="ALL", codes=None),
            effective_factory_id=factory.id,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_request_scope] = _override_scope
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    return client


@pytest.mark.asyncio
async def test_decide_api_notify_and_409(db):
    factory, user = await _seed_base(db, "api1")
    # elevate role for EDIT if needed — admin-like role_key manager
    from app.models.role import RoleDefinition
    from app.core.permissions import Module, PermissionLevel
    from unittest.mock import AsyncMock, patch as _patch

    await _make_pl(db, "PL-SRC-API1", factory.id, product_type_code="TYPE-API1")
    await _make_pl(db, "PL-A-API1", factory.id, product_type_code="TYPE-API1")
    capa = await _make_capa(db, factory.id, user.user_id, "PL-SRC-API1")
    db.add(
        CapaLateralDiffusionCheck(
            check_id=_check_id_for(capa.report_id),
            capa_id=capa.report_id,
            factory_id=factory.id,
            source_product_line_code="PL-SRC-API1",
            source_product_type_code="TYPE-API1",
            similar_products=[
                {
                    "product_type_code": "TYPE-API1",
                    "hit_criteria": ["same_product_type"],
                    "suggestion_direction": "x",
                    "product_lines": [
                        {"code": "PL-A-API1", "factory_id": str(factory.id)}
                    ],
                    "evidence": {},
                }
            ],
            status="done",
            llm_status="done",
            truncated=False,
        )
    )
    await db.flush()

    client = await _auth_client(db, user, factory)
    try:
        with _patch(
            "app.api.capa.get_user_permission",
            new=AsyncMock(return_value=PermissionLevel.EDIT),
        ):
            r1 = await client.post(
                f"/api/capa/{capa.report_id}/lateral-diffusion/decide",
                json={"decision": "notify"},
            )
            assert r1.status_code == 200, r1.text
            body = r1.json()
            assert body["decision"] == "notified"

            r2 = await client.post(
                f"/api/capa/{capa.report_id}/lateral-diffusion/decide",
                json={"decision": "skip", "skip_reason": "x"},
            )
            assert r2.status_code == 409
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


@pytest.mark.asyncio
async def test_decide_api_rejects_subset(db):
    factory, user = await _seed_base(db, "api2")
    client = await _auth_client(db, user, factory)
    try:
        from app.core.permissions import PermissionLevel
        from unittest.mock import AsyncMock, patch as _patch

        with _patch(
            "app.api.capa.get_user_permission",
            new=AsyncMock(return_value=PermissionLevel.EDIT),
        ):
            r = await client.post(
                f"/api/capa/{uuid.uuid4()}/lateral-diffusion/decide",
                json={"decision": "notify", "product_type_codes": ["T"]},
            )
            assert r.status_code == 422  # pydantic validation
    finally:
        app.dependency_overrides.clear()
        await client.aclose()


@pytest.mark.asyncio
async def test_decide_api_no_check_404(db):
    factory, user = await _seed_base(db, "api3")
    await _make_pl(db, "PL-SRC-API3", factory.id, product_type_code="TYPE-API3")
    capa = await _make_capa(db, factory.id, user.user_id, "PL-SRC-API3")
    client = await _auth_client(db, user, factory)
    try:
        from app.core.permissions import PermissionLevel
        from unittest.mock import AsyncMock, patch as _patch

        with _patch(
            "app.api.capa.get_user_permission",
            new=AsyncMock(return_value=PermissionLevel.EDIT),
        ):
            r = await client.post(
                f"/api/capa/{capa.report_id}/lateral-diffusion/decide",
                json={"decision": "notify"},
            )
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
        await client.aclose()
