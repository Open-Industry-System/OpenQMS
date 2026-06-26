"""Admin log endpoints: paginated response; admin 200; non-admin 403."""
import uuid

import pytest
from sqlalchemy import select

from app.models.login_audit_log import LoginAuditLog
from app.models.role import RoleDefinition
from app.models.user import User

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_login_logs_paginated(admin_client, db, default_factory):
    # seed two login log rows
    db.add(LoginAuditLog(username="u1", user_id=None, success=False, failure_reason="x", ip_address="1.1.1.1"))
    db.add(LoginAuditLog(username="u2", user_id=None, success=True, ip_address="2.2.2.2"))
    await db.flush()
    resp = await admin_client.get("/api/admin/logs/login?page=1&page_size=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1 and body["page_size"] == 10
    assert body["total"] >= 2
    assert {i["username"] for i in body["items"]} >= {"u1", "u2"}
    assert all("occurred_at" in i for i in body["items"])


@pytest.mark.asyncio
async def test_system_logs_filter_by_level(admin_client, db):
    from app.models.system_log import SystemLog
    db.add(SystemLog(logger_name="app.x", level="ERROR", message="e", module="x"))
    db.add(SystemLog(logger_name="app.x", level="WARNING", message="w", module="x"))
    await db.flush()
    resp = await admin_client.get("/api/admin/logs/system?level=ERROR")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert all(i["level"] == "ERROR" for i in body["items"])


@pytest.mark.asyncio
async def test_audit_logs_admin_ok(admin_client, db):
    resp = await admin_client.get("/api/admin/logs/audit?page=1&page_size=5")
    assert resp.status_code == 200
    body = resp.json()
    assert {"items", "total", "page", "page_size"} <= set(body.keys())


@pytest.mark.asyncio
async def test_logs_forbidden_for_non_admin(db, default_factory, admin_user):
    """A viewer token must get 403 from all three log endpoints."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.deps import get_current_user, get_db, get_request_scope

    # viewer user
    role = (await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "viewer"))).scalar_one_or_none()
    if role is None:
        role = RoleDefinition(role_key="viewer", name_zh="只读", name_en="Viewer", is_system=True, is_active=True)
        db.add(role); await db.flush()
    viewer = User(user_id=uuid.uuid4(), username="v_log", display_name="V", password_hash="h",
                  role_id=role.id, legacy_role="viewer", is_active=True, factory_id=default_factory.id)
    db.add(viewer); await db.flush()

    from tests.conftest import _scope_for
    app.dependency_overrides[get_current_user] = lambda: viewer
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: _scope_for(viewer, default_factory, accessible_factory_ids=None)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            for path in ("/audit", "/login", "/system"):
                r = await ac.get(f"/api/admin/logs{path}")
                assert r.status_code == 403, (path, r.text)
    finally:
        app.dependency_overrides.clear()
