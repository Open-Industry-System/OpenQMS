"""Backward-compatible dependency re-exports + RequestScope."""
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import (
    get_current_user,
    require_permission,
    require_admin,
    require_engineer_or_admin,
    PermissionLevel,
    Module,
    get_user_permission,
)
from app.core.factory_scope import (
    FactoryScope,
    ProductLineScope,
    resolve_factory_scope,
    resolve_product_line_scope,
    resolve_effective_factory_id,
    get_user_factory_ids,
    get_user_product_line_codes,
)
from app.core.security import verify_token, PLATFORM_ISSUER, PLATFORM_AUDIENCE, TENANT_ISSUER, TENANT_AUDIENCE
from jose import JWTError
from app.database import get_db
from app.models.user import User


@dataclass
class RequestScope:
    """Pre-resolved scope for the current request. One object, one Depends."""
    factory_scope: FactoryScope
    effective_factory_id: UUID | None
    pl_scope: ProductLineScope
    user: User


async def get_request_scope(
    request: Request,
    factory_id: UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequestScope:
    # 1. Factory scope
    user_factory_ids = await get_user_factory_ids(user, db)
    group_level = await get_user_permission(user, Module.GROUP, db)
    has_group_admin = group_level >= PermissionLevel.ADMIN
    factory_scope = resolve_factory_scope(user, user_factory_ids, has_group_admin)
    effective_factory_id = resolve_effective_factory_id(factory_scope, factory_id)

    # 2. Product line scope
    user_pl_codes = await get_user_product_line_codes(user, db)
    pl_scope = resolve_product_line_scope(user, user_pl_codes, factory_scope)

    return RequestScope(
        factory_scope=factory_scope,
        effective_factory_id=effective_factory_id,
        pl_scope=pl_scope,
        user=user,
    )


async def require_platform_admin(request: Request):
    """Dependency for /api/platform/* routes.
    Rejects tenant JWTs (tenant_id claim present) with 403.
    Requires platform admin JWT (is_platform_admin: true) with correct iss/aud.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header[7:]
    try:
        payload = verify_token(token, issuer=PLATFORM_ISSUER, audience=PLATFORM_AUDIENCE)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if payload.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Tenant JWT cannot access platform routes")

    if not payload.get("is_platform_admin"):
        raise HTTPException(status_code=403, detail="Platform admin access required")

    if payload.get("iss") != PLATFORM_ISSUER:
        raise HTTPException(status_code=403, detail="Invalid token issuer")
    if payload.get("aud") != PLATFORM_AUDIENCE:
        raise HTTPException(status_code=403, detail="Invalid token audience")

    return payload


__all__ = [
    "get_current_user",
    "require_permission",
    "require_admin",
    "require_engineer_or_admin",
    "PermissionLevel",
    "Module",
    "RequestScope",
    "get_request_scope",
    "require_platform_admin",
]