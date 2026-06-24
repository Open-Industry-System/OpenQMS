from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.models.product_line import ProductLine
from app.services.product_line_service import list_product_lines


async def _user_accessible_product_lines(db: AsyncSession, request_scope: RequestScope) -> list[str] | None:
    """Codes the user may see, filtered by accessible factories + pl_scope.

    Returns None if the user has unrestricted access (group admin: all factories + ALL pl_scope).
    """
    accessible = request_scope.factory_scope.accessible_factory_ids
    pl_scope = request_scope.pl_scope

    if pl_scope is not None and pl_scope.mode == "ALL" and accessible is None:
        return None  # unrestricted

    pls = await list_product_lines(db, is_active=True, accessible_factory_ids=accessible)
    codes = {pl.code for pl in pls}

    if pl_scope is not None and pl_scope.mode == "EXPLICIT":
        codes = codes & set(pl_scope.codes or [])
    if pl_scope is not None and pl_scope.mode == "NONE":
        codes = set()
    return list(codes)


async def resolve_product_line_codes(
    scope: str,
    current_product_line_code: str | None,
    db: AsyncSession,
    request_scope: RequestScope,
) -> list[str] | None:
    if scope == "global":
        return None
    if current_product_line_code is None:
        return []

    if scope == "current_product_line":
        business = {current_product_line_code}
    elif scope == "current_product_type":
        result = await db.execute(
            select(ProductLine.product_type_code).where(ProductLine.code == current_product_line_code)
        )
        pt_code = result.scalar_one_or_none()
        if not pt_code:
            business = {current_product_line_code}  # untyped → degrade
        else:
            type_result = await db.execute(
                select(ProductLine.code).where(ProductLine.product_type_code == pt_code)
            )
            business = {row[0] for row in type_result.fetchall()}
    else:
        business = {current_product_line_code}

    accessible = await _user_accessible_product_lines(db, request_scope)
    if accessible is None:
        return sorted(business)
    return sorted(business & set(accessible))
