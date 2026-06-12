import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException

from app.core.security import (
    create_tenant_user_token,
    create_platform_admin_token,
    TENANT_ISSUER,
    PLATFORM_ISSUER,
)


@pytest.mark.asyncio
async def test_platform_route_rejects_tenant_jwt():
    """Platform routes must reject JWTs with tenant_id claim — returns 403."""
    from app.core.deps import require_platform_admin

    request = MagicMock()
    request.headers.get.return_value = "Bearer fake_token"

    # Mock verify_token to return a tenant JWT payload
    tenant_payload = {
        "sub": "user-123",
        "tenant_id": "tenant-acme-uuid",
        "role_id": "role-uuid",
        "iss": TENANT_ISSUER,
        "aud": TENANT_ISSUER,
    }
    with patch("app.core.deps.verify_token", return_value=tenant_payload):
        with pytest.raises(HTTPException) as exc_info:
            await require_platform_admin(request)
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_platform_route_ignores_x_tenant_id_header():
    """Platform routes must set request.state.tenant = None regardless of
    X-Tenant-ID header. The header is simply ignored, not treated as an error."""
    from app.core.tenant_context import TenantContextMiddleware

    mock_inner = AsyncMock()
    middleware = TenantContextMiddleware(mock_inner)
    # Platform route with X-Tenant-ID header — must be ignored
    request = MagicMock()
    request.url.path = "/api/platform/tenants"
    request.headers.get = lambda k, default="": {
        "host": "",
        "X-Tenant-ID": "acme",
        "authorization": "",
    }.get(k, default)
    request.app = MagicMock()
    request.app.state.tenant_domain = None
    request.state = MagicMock()

    await middleware.dispatch(request, mock_inner)
    # For platform routes, tenant must be None regardless of X-Tenant-ID
    assert request.state.tenant is None


@pytest.mark.asyncio
async def test_platform_route_requires_platform_admin_jwt():
    """Platform routes must require is_platform_admin: true — returns 403 for regular users."""
    from app.core.deps import require_platform_admin

    request = MagicMock()
    request.headers.get.return_value = "Bearer fake_token"

    # Mock verify_token to return a regular user payload (no is_platform_admin)
    regular_payload = {
        "sub": "user-123",
        "role_id": "role-uuid",
        "iss": TENANT_ISSUER,
        "aud": TENANT_ISSUER,
    }
    with patch("app.core.deps.verify_token", return_value=regular_payload):
        with pytest.raises(HTTPException) as exc_info:
            await require_platform_admin(request)
        assert exc_info.value.status_code == 403


def _collect_dependencies(dependant):
    """Recursively collect all dependency functions from a FastAPI dependant tree."""
    deps = set()
    for dep in dependant.dependencies:
        # FastAPI stores the actual function/callable in .call
        deps.add(getattr(dep, "call", None))
        deps.update(_collect_dependencies(dep))
    return deps


# Routes that are explicitly DB-free (no database access needed).
PLATFORM_DB_FREE_ALLOWLIST = {"/api/platform/health"}


def test_ci_route_dependency_check():
    """CI test: all /api/platform/* routes must depend on get_platform_db, not get_db.

    Every platform route (except allowlisted DB-free routes) MUST include
    get_platform_db in its dependency tree. No platform route may use get_db.
    """
    from app.main import app
    from app.database import get_db, get_platform_db

    violations = []
    for route in app.routes:
        if not hasattr(route, "path") or not hasattr(route, "dependant"):
            continue
        if not route.path.startswith("/api/platform"):
            continue
        # Recursively walk the dependency tree to catch nested sub-dependencies
        all_deps = _collect_dependencies(route.dependant)
        # NEGATIVE: platform routes must NOT use get_db (at any depth)
        if get_db in all_deps:
            violations.append(
                f"{route.path} [{route.methods}] uses get_db instead of get_platform_db"
            )
        # POSITIVE: all platform routes must use get_platform_db unless allowlisted
        if route.path not in PLATFORM_DB_FREE_ALLOWLIST and get_platform_db not in all_deps:
            violations.append(
                f"{route.path} [{route.methods}] missing get_platform_db "
                f"(add to PLATFORM_DB_FREE_ALLOWLIST if DB-free)"
            )

    assert violations == [], "Platform route dependency violations:\n" + "\n".join(violations)


@pytest.mark.asyncio
async def test_x_tenant_id_ignored_in_production():
    """X-Tenant-ID header must be ignored when TENANT_MODE != 'dev'."""
    from app.core.tenant_context import TenantContextMiddleware
    from app.config import settings

    # Save original TENANT_MODE and restore after test
    original = getattr(settings, 'TENANT_MODE', None)

    # Simulate production: TENANT_MODE is not "dev"
    settings.TENANT_MODE = "production"
    try:
        mock_inner = AsyncMock()
        middleware = TenantContextMiddleware(mock_inner)
        # Request with X-Tenant-ID header but no auth — in production
        # the header should be ignored, leaving tenant unresolved
        request = MagicMock()
        request.url.path = "/api/fmea"
        request.headers.get = lambda k, default="": {
            "host": "",
            "X-Tenant-ID": "acme",  # Should be ignored in production
            "authorization": "",
        }.get(k, default)
        request.app = MagicMock()
        request.app.state.tenant_domain = None
        request.state = MagicMock()

        await middleware.dispatch(request, mock_inner)
        # X-Tenant-ID is ignored in production — tenant remains None
        assert request.state.tenant is None
    finally:
        settings.TENANT_MODE = original


@pytest.mark.asyncio
async def test_jwt_fallback_resolves_tenant():
    """When no subdomain or X-Tenant-ID is present, JWT tenant_id resolves the tenant."""
    from app.core.tenant_context import TenantContextMiddleware

    mock_tenant = MagicMock()
    mock_tenant.id = "tenant-acme-uuid"
    mock_tenant.status = "active"

    mock_inner = AsyncMock()
    middleware = TenantContextMiddleware(mock_inner)

    # No subdomain, no X-Tenant-ID (TENANT_MODE=production), but Bearer token present
    fake_payload = {"sub": "user-1", "tenant_id": "tenant-acme-uuid", "iss": "openqms-tenant"}

    request = MagicMock()
    request.url.path = "/api/fmea"
    request.headers.get = lambda k, default="": {
        "host": "",
        "X-Tenant-ID": "",
        "authorization": "Bearer fake.bearer.token",
    }.get(k, default)
    request.app = MagicMock()
    request.app.state.tenant_domain = None
    request.state = MagicMock()

    with patch.object(middleware, "_resolve_by_id", return_value=mock_tenant), \
         patch("app.core.tenant_context.decode_token_without_verification", return_value=fake_payload), \
         patch("app.core.tenant_context.settings", TENANT_MODE="production"):
        await middleware.dispatch(request, mock_inner)

    # JWT fallback should have resolved the tenant
    assert request.state.tenant is not None


@pytest.mark.asyncio
async def test_suspended_tenant_returns_503():
    """Middleware must raise 503 for suspended tenants."""
    from app.core.tenant_context import TenantContextMiddleware

    mock_tenant = MagicMock()
    mock_tenant.status = "suspended"

    mock_inner = AsyncMock()
    middleware = TenantContextMiddleware(mock_inner)
    # Set up request with X-Tenant-ID header and TENANT_MODE=dev
    # so the slug resolver is triggered
    request = MagicMock()
    request.url.path = "/api/fmea"
    # headers.get returns values for: host (empty), X-Tenant-ID (acme), authorization (empty)
    request.headers.get = lambda k, default="": {
        "host": "",
        "X-Tenant-ID": "acme",
        "authorization": "",
    }.get(k, default)
    request.app = MagicMock()
    request.app.state.tenant_domain = None
    request.state = MagicMock()

    with patch.object(middleware, "_resolve_by_slug", return_value=mock_tenant), \
         patch("app.core.tenant_context.settings", TENANT_MODE="dev"):
        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(request, mock_inner)
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail.get("tenant_suspended") is True


@pytest.mark.asyncio
async def test_deactivated_tenant_returns_410():
    """Middleware must raise 410 for deactivated tenants."""
    from app.core.tenant_context import TenantContextMiddleware

    mock_tenant = MagicMock()
    mock_tenant.status = "deactivated"

    mock_inner = AsyncMock()
    middleware = TenantContextMiddleware(mock_inner)
    request = MagicMock()
    request.url.path = "/api/fmea"
    request.headers.get = lambda k, default="": {
        "host": "",
        "X-Tenant-ID": "deact-corp",
        "authorization": "",
    }.get(k, default)
    request.app = MagicMock()
    request.app.state.tenant_domain = None
    request.state = MagicMock()

    with patch.object(middleware, "_resolve_by_slug", return_value=mock_tenant), \
         patch("app.core.tenant_context.settings", TENANT_MODE="dev"):
        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(request, mock_inner)
        assert exc_info.value.status_code == 410