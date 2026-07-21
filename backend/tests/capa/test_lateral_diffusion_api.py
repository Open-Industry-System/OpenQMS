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


@pytest.mark.asyncio
async def test_advance_api_returns_422_blocked_lateral_stage(sessionmaker, monkeypatch):
    """/advance must return 422 with outcome=blocked stage=lateral_diffusion
    when sink succeeds but lateral LLM is unavailable."""
    from app.models.capa import CAPAEightD
    from app.models.factory import Factory
    from app.models.product_line import ProductLine
    from app.models.product_type import ProductType
    from app.models.role import RoleDefinition
    from app.models.user import User
    from app.services.agent.provider_adapter import ProviderNotConfiguredError

    suffix = uuid.uuid4().hex[:8]
    factory_id = uuid.uuid4()
    user_id = uuid.uuid4()
    capa_id = uuid.uuid4()
    role_id = uuid.uuid4()

    async with sessionmaker() as s:
        s.add(Factory(id=factory_id, code=f"F-APIBLK-{suffix}", name="T", is_active=True))
        await s.flush()
        s.add(ProductType(code=f"T-APIBLK-{suffix}", name="T", is_active=True))
        await s.flush()
        s.add(ProductLine(code=f"P-APIBLK-{suffix}", name="T", factory_id=factory_id, product_type_code=f"T-APIBLK-{suffix}"))
        # Second PL with same type so lateral check has hits and requires LLM
        s.add(ProductLine(code=f"P-APIBLK2-{suffix}", name="T2", factory_id=factory_id, product_type_code=f"T-APIBLK-{suffix}"))
        s.add(RoleDefinition(id=role_id, role_key=f"r-apiblk-{suffix}", name_zh="t", name_en="t", is_system=False, is_editable=True, is_active=True))
        await s.flush()
        s.add(User(user_id=user_id, username=f"u-apiblk-{suffix}", display_name="u", password_hash="x", role_id=role_id, legacy_role="viewer", is_active=True, factory_id=factory_id))
        await s.flush()
        s.add(CAPAEightD(
            report_id=capa_id, document_no=f"8D-APIBLK-{suffix}", title="t",
            product_line_code=f"P-APIBLK-{suffix}", factory_id=factory_id,
            status="D8_APPROVAL_PENDING", severity="general", created_by=user_id,
            d2_description="d2", d4_root_cause="d4", d5_correction="d5",
            d6_verification="d6", d7_prevention="d7", d8_closure="d8", d1_team=[],
        ))
        await s.commit()

    async def _noop_sink(db, capa, uid, manual=False):
        return None

    monkeypatch.setattr("app.services.knowledge_sink_service.sink_capa_on_close", _noop_sink)
    monkeypatch.setattr(
        "app.services.capa_lateral_diffusion_service.build_client",
        AsyncMock(side_effect=ProviderNotConfiguredError("no cfg")),
    )

    # Override deps and call the real advance route
    from app.core.deps import get_current_user, get_db, get_request_scope
    from app.core.factory_scope import FactoryScope, ProductLineScope
    from app.core.deps import RequestScope

    async def _override_db():
        async with sessionmaker() as db:
            yield db

    async def _override_scope():
        async with sessionmaker() as db:
            user = await db.get(User, user_id)
            return RequestScope(
                user=user,
                factory_scope=FactoryScope(accessible_factory_ids=[factory_id], default_factory_id=factory_id),
                pl_scope=ProductLineScope(mode="ALL", codes=None),
                effective_factory_id=factory_id,
            )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: None  # unused when scope override
    app.dependency_overrides[get_request_scope] = _override_scope

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            from unittest.mock import patch as _patch
            with _patch("app.api.capa.get_user_permission", new=AsyncMock(return_value=5)):
                r = await client.post(
                    f"/api/capa/{capa_id}/advance",
                    json={"target_state": "D8_CLOSURE"},
                )
                assert r.status_code == 422, r.text
                body = r.json()
                assert body["detail"]["outcome"] == "blocked"
                assert body["detail"]["stage"] == "lateral_diffusion"
    finally:
        app.dependency_overrides.clear()
