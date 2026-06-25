import pytest
from app.models.product_line import ProductLine


@pytest.mark.asyncio
async def test_create_product_type_admin_ok(admin_client):
    resp = await admin_client.post("/api/product-types", json={"code": "POWER", "name": "电源类"})
    assert resp.status_code == 200
    assert resp.json()["code"] == "POWER"


@pytest.mark.asyncio
async def test_create_product_type_duplicate_logs_failed_audit(db, default_factory, admin_user):
    """A duplicate-code create attempt is rejected AND recorded as a CREATE_FAILED audit log,
    so failed attempts are traceable (audit parity with successful writes)."""
    from app.services.product_type_service import create_product_type
    from app.models.audit import AuditLog
    from sqlalchemy import select

    await create_product_type(db, "POWER", "电源类", None, admin_user.user_id)
    # Second create with the same code → 400 at the API / ValueError at the service.
    with pytest.raises(ValueError):
        await create_product_type(db, "POWER", "电源类", None, admin_user.user_id)

    failed = (await db.execute(
        select(AuditLog).where(AuditLog.table_name == "product_types", AuditLog.action == "CREATE_FAILED")
    )).scalars().all()
    assert len(failed) == 1
    assert failed[0].changed_fields.get("code") == "POWER"
    assert failed[0].changed_fields.get("reason") == "duplicate_code"
    assert failed[0].operated_by == admin_user.user_id


@pytest.mark.asyncio
async def test_create_product_type_non_admin_forbidden(db, viewer_user, default_factory):
    # Build an ASGI client authenticated as viewer_user (non-admin role) — require_admin raises 403.
    from app.main import app
    from app.core.deps import get_current_user, get_db, get_request_scope, RequestScope
    from app.core.factory_scope import FactoryScope, ProductLineScope
    from httpx import ASGITransport, AsyncClient
    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=default_factory.id),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=viewer_user,
    )
    app.dependency_overrides[get_current_user] = lambda: viewer_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/product-types", json={"code": "X", "name": "X"})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_product_type_refused_when_active_product_line_references(admin_client, db, default_factory):
    await admin_client.post("/api/product-types", json={"code": "POWER", "name": "电源类"})
    # Use a unique product-line code (admin_user fixture pre-creates DC-DC-100).
    db.add(ProductLine(code="PT-REF-1", name="Ref PL", factory_id=default_factory.id, product_type_code="POWER"))
    await db.commit()
    resp = await admin_client.delete("/api/product-types/POWER")
    assert resp.status_code == 400
    assert "引用" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_delete_product_type_soft_deletes_when_no_references(admin_client):
    await admin_client.post("/api/product-types", json={"code": "MOTOR", "name": "电机类"})
    resp = await admin_client.delete("/api/product-types/MOTOR")
    assert resp.status_code == 200
    resp = await admin_client.get("/api/product-types")
    motor = next(i for i in resp.json()["items"] if i["code"] == "MOTOR")
    assert motor["is_active"] is False
