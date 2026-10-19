"""TenantContext middleware — resolves tenant from request and injects into request.state."""
import logging
import re

from fastapi import Request
from sqlalchemy import select, text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings
from app.core.agent_local_trial import is_local_trial_path, local_trial_peer_allowed
from app.core.security import verify_token
from app.core.tenant_transaction import TenantBinding
from app.database import async_session
from app.models.tenant import Tenant
from app.services.agent_runtime.routes import RUNTIME_PATHS, RUNTIME_JWT_ROUTES

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Middleware that resolves tenant from subdomain or X-Tenant-ID header
    and injects it into request.state.tenant.

    Does NOT set search_path — that happens in get_db() dependency.
    """

    async def dispatch(self, request: Request, call_next):
        # Hide the default-off feature before auth, validation or tenant lookups.
        path = request.url.path
        if (not settings.CAPA_D4_TEXT_PREVIEW_ENABLED
                and re.fullmatch(r'/api/capa/[^/]+/d4-text-preview(?:/version|/availability)?/?', path)):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        if (not (settings.AGENT_TASK_RUNTIME_ENABLED and settings.AGENT_TASK_ATTACHMENTS_ENABLED)
                and re.fullmatch(r'/api/agent/tasks/[^/]+/attachments(?:/[^/]+(?:/download)?)?/?', path)):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        if not settings.AGENT_TASK_RUNTIME_ENABLED and (path in RUNTIME_PATHS or any(
            path == prefix or path.startswith(prefix + "/")
            for prefix in ("/api/agent/tasks", "/api/admin/agent-plugins")
        )):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

        if (settings.AGENT_LOCAL_TRIAL_MODE == "local_metadata" and is_local_trial_path(path)
                and not local_trial_peer_allowed(request)):
            return JSONResponse(status_code=403, content={"detail": "Access denied"})

        # In single-tenant mode, skip all tenant resolution
        if settings.TENANT_MODE == "single":
            request.state.tenant = None
            response = await call_next(request)
            return response

        # Skip tenant resolution for platform admin routes
        if request.url.path.startswith("/api/platform/"):
            request.state.tenant = None
            response = await call_next(request)
            return response

        # Skip tenant resolution for health check and docs
        if request.url.path in ("/api/health", "/docs", "/openapi.json", "/redoc"):
            request.state.tenant = None
            response = await call_next(request)
            return response

        tenant = None

        # 1. Try subdomain from Host header (production)
        host = request.headers.get("host", "")
        domain_suffix = request.app.state.tenant_domain if hasattr(request.app.state, "tenant_domain") else None

        if domain_suffix and host:
            # Extract subdomain: "acme.openqms.com" -> "acme"
            if host.endswith(f".{domain_suffix}"):
                subdomain = host[: -(len(domain_suffix) + 1)]
                if subdomain and subdomain != "admin":
                    tenant = await self._resolve_by_subdomain(subdomain)

        # 2. Try X-Tenant-ID header (development/internal only)
        # Production must not trust this header — an attacker could forge tenant identity.
        if tenant is None and settings.TENANT_MODE == "dev":
            tenant_slug = request.headers.get("X-Tenant-ID")
            if tenant_slug:
                tenant = await self._resolve_by_slug(tenant_slug)

        # 3. Try JWT tenant_id claim (fallback for authenticated requests)
        # Verify the JWT fully to prevent tenant enumeration attacks — an
        # unverified token would allow attackers to probe tenant statuses.
        if tenant is None and (request.method, path) != ("POST", "/api/agent/runtime/claim"):
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    token = auth_header[7:]
                    if (request.method, path) in RUNTIME_JWT_ROUTES:
                        from app.services.agent_runtime.run_auth import _claims
                        payload = _claims(token)
                    else:
                        payload = verify_token(token)
                        if payload.get("type") == "agent_run":
                            raise ValueError("Runtime credentials cannot resolve ordinary user routes")
                    jwt_tenant_id = payload.get("tenant_id")
                    if jwt_tenant_id:
                        tenant = await self._resolve_by_id(jwt_tenant_id)
                        if ((request.method, path) in RUNTIME_JWT_ROUTES and tenant is not None
                                and tenant.generation != payload["tenant_generation"]):
                            return JSONResponse(status_code=401, content={"detail": "Invalid run credential"})
                except Exception:
                    pass  # Invalid token — will be caught by auth dependency

        # Handle non-active tenant statuses — use JSONResponse instead of
        # HTTPException to ensure CORS headers are properly added by outer middleware.
        if tenant is not None:
            if tenant.status == "suspended":
                return JSONResponse(
                    status_code=503,
                    content={"message": "租户已暂停", "tenant_suspended": True},
                )
            if tenant.status == "deactivated":
                return JSONResponse(
                    status_code=410,
                    content={"message": "租户已停用"},
                )
            if tenant.status != "active":
                return JSONResponse(
                    status_code=503,
                    content={"message": "租户尚未就绪"},
                )
        elif settings.TENANT_MODE != "single":
            # Multi-tenant mode but tenant could not be resolved — reject the
            # request with 400 instead of letting it fall through to a 500 when
            # queries hit the public schema (which lacks tenant tables).
            return JSONResponse(
                status_code=400,
                content={"message": "无法解析租户，请使用正确的访问地址", "tenant_unresolved": True},
            )

        # Freeze admission identity at request entry, not after later registry changes.
        request.state.tenant = tenant
        request.state.tenant_binding = TenantBinding(
            tenant_id=tenant.id, schema_name=tenant.schema_name,
            generation=tenant.generation, mode="business",
        )
        response = await call_next(request)
        return response

    async def _resolve_by_subdomain(self, subdomain: str):
        """Look up tenant by subdomain. Returns tenant regardless of status
        (suspended/deactivated handling is done by the caller)."""
        async with async_session() as session:
            await session.execute(text('SET search_path TO "public"'))
            result = await session.execute(
                select(Tenant).where(Tenant.subdomain == subdomain)
            )
            return result.scalar_one_or_none()

    async def _resolve_by_slug(self, slug: str):
        """Look up tenant by slug. Returns tenant regardless of status
        (suspended/deactivated handling is done by the caller)."""
        async with async_session() as session:
            await session.execute(text('SET search_path TO "public"'))
            result = await session.execute(
                select(Tenant).where(Tenant.slug == slug)
            )
            return result.scalar_one_or_none()

    async def _resolve_by_id(self, tenant_id: str):
        """Look up tenant by UUID. Returns tenant regardless of status
        (suspended/deactivated handling is done by the caller)."""
        async with async_session() as session:
            await session.execute(text('SET search_path TO "public"'))
            result = await session.execute(
                select(Tenant).where(Tenant.id == tenant_id)
            )
            return result.scalar_one_or_none()