"""Backward-compatible dependency re-exports + RequestScope."""
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Query, Request
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


__all__ = [
    "get_current_user",
    "require_permission",
    "require_admin",
    "require_engineer_or_admin",
    "PermissionLevel",
    "Module",
    "RequestScope",
    "get_request_scope",
]