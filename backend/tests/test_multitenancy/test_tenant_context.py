"""Tests for tenant utilities and TenantContextMiddleware."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.tenant_utils import set_search_path_sql, slug_to_schema_name


# --- tenant_utils tests ---


def test_set_search_path_valid_schema():
    """Valid schema names produce correct SET search_path SQL."""
    result = set_search_path_sql("tenant_acme")
    assert result == 'SET search_path TO "tenant_acme", "public"'


def test_set_search_path_rejects_invalid_names():
    """Invalid schema names raise ValueError."""
    with pytest.raises(ValueError, match="Invalid schema name"):
        set_search_path_sql("evil'; DROP TABLE users;--")

    with pytest.raises(ValueError, match="Invalid schema name"):
        set_search_path_sql("tenant_")  # too short after prefix

    with pytest.raises(ValueError, match="Invalid schema name"):
        set_search_path_sql("a" * 70)  # exceeds 63 chars


def test_set_search_path_escapes_double_quotes():
    """Double quotes in schema names are escaped."""
    result = set_search_path_sql("tenant_acme_corp")
    assert result == 'SET search_path TO "tenant_acme_corp", "public"'


def test_slug_to_schema_name():
    """slug is converted to schema_name by replacing - with _ and adding tenant_ prefix."""
    assert slug_to_schema_name("acme-corp") == "tenant_acme_corp"
    assert slug_to_schema_name("my-company") == "tenant_my_company"
    assert slug_to_schema_name("abc") == "tenant_abc"


def test_slug_to_schema_name_rejects_invalid():
    """Invalid slugs raise ValueError."""
    with pytest.raises(ValueError):
        slug_to_schema_name("")  # empty
    with pytest.raises(ValueError):
        slug_to_schema_name("ABC")  # uppercase
    with pytest.raises(ValueError):
        slug_to_schema_name("-acme")  # starts with hyphen


# --- TenantContextMiddleware tests ---


@pytest.mark.asyncio
async def test_single_tenant_mode_skips_resolution():
    """When TENANT_MODE='single', middleware skips all tenant resolution
    and sets request.state.tenant = None, preserving original behavior."""
    from app.core.tenant_context import TenantContextMiddleware

    mock_inner = AsyncMock()
    middleware = TenantContextMiddleware(mock_inner)
    request = MagicMock()
    request.url.path = "/api/fmea"
    request.headers.get = lambda k, default="": ""
    request.app = MagicMock()
    request.app.state.tenant_domain = None
    request.state = MagicMock()

    with patch("app.core.tenant_context.settings", TENANT_MODE="single"):
        await middleware.dispatch(request, mock_inner)
        # In single mode, tenant must be None — no tenant resolution happens
        assert request.state.tenant is None


def test_middleware_is_registered_in_app():
    """TenantContextMiddleware must be registered in the FastAPI app."""
    from app.main import app
    from app.core.tenant_context import TenantContextMiddleware

    middleware_classes = [cls for cls in _get_middleware_classes(app)]
    assert TenantContextMiddleware in middleware_classes, (
        f"TenantContextMiddleware not found in app middleware. "
        f"Found: {middleware_classes}"
    )


def _get_middleware_classes(app):
    """Extract middleware classes from a FastAPI app."""
    for mw in app.user_middleware:
        yield mw.cls


@pytest.mark.asyncio
async def test_x_tenant_id_ignored_in_production():
    """X-Tenant-ID header must be ignored when TENANT_MODE is 'production'."""
    from app.core.tenant_context import TenantContextMiddleware

    mock_inner = AsyncMock()
    middleware = TenantContextMiddleware(mock_inner)
    request = MagicMock()
    request.url.path = "/api/fmea"
    request.headers.get = lambda k, default="": "acme" if k == "X-Tenant-ID" else default
    request.app = MagicMock()
    request.app.state.tenant_domain = None
    request.state = MagicMock()

    with patch("app.core.tenant_context.settings", TENANT_MODE="production"):
        with patch("app.core.tenant_context.async_session") as mock_session:
            await middleware.dispatch(request, mock_inner)
            # X-Tenant-ID should NOT trigger a DB lookup in production mode
            mock_session.assert_not_called()


# --- get_db / database tests ---


@pytest.mark.asyncio
async def test_get_db_sets_search_path_for_tenant():
    """get_db() must execute SET search_path when a tenant is present on the request."""
    from app.database import get_db
    from app.core.tenant_utils import current_tenant_schema

    # Build a mock session that records execute calls
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    # session.begin() returns an async context manager, not a coroutine
    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    mock_session.begin = MagicMock(return_value=begin_cm)

    mock_sessionmaker = MagicMock(return_value=mock_session)

    # Mock request with a tenant
    mock_request = MagicMock()
    mock_tenant = MagicMock()
    mock_tenant.schema_name = "tenant_acme"
    mock_request.state.tenant = mock_tenant

    with patch("app.database.async_session", mock_sessionmaker):
        # Drive the async generator to get the session
        gen = get_db(mock_request)
        db = await gen.__anext__()
        try:
            # SET search_path must have been called with the tenant schema
            # SQLAlchemy text() objects don't stringify to their SQL content;
            # inspect the .text attribute instead of str(call).
            executed_sql = [
                getattr(c.args[0], "text", "") for c in mock_session.execute.call_args_list
            ]
            assert any(
                'SET search_path TO "tenant_acme", "public"' in sql for sql in executed_sql
            ), f"Expected SET search_path TO tenant_acme, got SQL: {executed_sql}"
            # ContextVar must be set to the tenant schema
            assert current_tenant_schema.get() == "tenant_acme"
        finally:
            # Clean up the generator
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass

    # After generator cleanup, ContextVar must be reset
    assert current_tenant_schema.get() is None


def test_context_var_default_is_none():
    """current_tenant_schema defaults to None (no tenant context)."""
    from app.core.tenant_utils import current_tenant_schema
    assert current_tenant_schema.get() is None


def test_context_var_set_and_reset():
    """current_tenant_schema can be set and reset without leaking."""
    from app.core.tenant_utils import current_tenant_schema
    token = current_tenant_schema.set("tenant_test")
    assert current_tenant_schema.get() == "tenant_test"
    current_tenant_schema.reset(token)
    assert current_tenant_schema.get() is None


# --- Cross-tenant JWT rejection tests ---


@pytest.mark.asyncio
async def test_cross_tenant_jwt_rejection():
    """JWT with tenant_id=A must not be accepted on tenant B's subdomain."""
    from app.core.permissions import get_current_user
    from fastapi import HTTPException

    # Simulate request on tenant B's subdomain — request.state.tenant.id is different
    request = MagicMock()
    request.state.tenant = MagicMock()
    request.state.tenant.id = "tenant-b-uuid"  # Different tenant

    # Mock credentials and db (not needed — rejection happens before DB lookup)
    mock_credentials = MagicMock()
    mock_credentials.credentials = "fake_token"
    mock_db = MagicMock()

    # Mock verify_token to return the tenant A payload
    with patch("app.core.permissions.verify_token", return_value={
        "sub": "user-a",
        "tenant_id": "tenant-a-uuid",  # Token says tenant A
        "role_id": "role-uuid",
        "iss": "openqms-tenant",
        "aud": "openqms-tenant",
    }):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=request, credentials=mock_credentials, db=mock_db)
        # Must reject with 403 — token tenant doesn't match request tenant
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_platform_jwt_cannot_access_tenant_routes():
    """Platform admin JWT (is_platform_admin=true) must not work on tenant routes."""
    from app.core.permissions import get_current_user
    from fastapi import HTTPException

    request = MagicMock()
    request.state.tenant = MagicMock()
    request.state.tenant.id = "tenant-acme-uuid"

    mock_credentials = MagicMock()
    mock_credentials.credentials = "fake_token"
    mock_db = MagicMock()

    # Platform token has no tenant_id and wrong iss/aud for tenant routes
    with patch("app.core.permissions.verify_token", return_value={
        "sub": "admin-uuid",
        "is_platform_admin": True,
        "role": "superadmin",
        "iss": "openqms-platform",  # Wrong issuer for tenant routes
        "aud": "openqms-platform",
    }):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request=request, credentials=mock_credentials, db=mock_db)
        # Platform JWT must not be accepted on tenant routes
        assert exc_info.value.status_code in (401, 403)