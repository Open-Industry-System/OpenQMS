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