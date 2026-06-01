"""Product line filtering for data isolation."""
from fastapi import Request, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.role import UserProductLine

QUERY_PARAM_NAMES = ["product_line", "product_line_code"]

PRODUCT_LINE_FIELD_MAP: dict[str, str] = {
    "fmea": "product_line_code",
    "capa": "product_line_code",
    "audit": "product_line_code",
    "customer_quality": "product_line_code",
    "customer_audit": "product_line_code",
    "iqc": "product_line_code",
    "ppap": "product_line_code",
    "spc": "product_line",
    "msa": "product_line_code",
    "planning": "product_line_code",
    "management_review": "product_line_code",
    "special_characteristic": "product_line_code",
    "quality_goal": "product_line_code",
    "scar": "product_line_code",
}


def get_requested_product_line(request: Request) -> str | None:
    for param in QUERY_PARAM_NAMES:
        code = request.query_params.get(param)
        if code:
            return code
    return None


async def get_user_product_line_codes(user: User, db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(UserProductLine.product_line_code)
        .where(UserProductLine.user_id == user.user_id)
    )
    return [row[0] for row in result.all()]


async def apply_product_line_filter(
    query,
    user: User,
    model: type,
    module: str,
    db: AsyncSession,
    request: Request,
):
    field_name = PRODUCT_LINE_FIELD_MAP.get(module)
    if not field_name or not hasattr(model, field_name):
        return query

    if user.role_definition.bypass_row_level_security:
        requested_code = get_requested_product_line(request)
        if requested_code:
            query = query.where(getattr(model, field_name) == requested_code)
        return query

    user_codes = await get_user_product_line_codes(user, db)
    if not user_codes:
        return query.where(False)

    requested_code = get_requested_product_line(request)
    if requested_code:
        if requested_code not in user_codes:
            raise HTTPException(403, f"无权访问产品线 '{requested_code}'")
        query = query.where(getattr(model, field_name) == requested_code)
    else:
        query = query.where(getattr(model, field_name).in_(user_codes))

    return query


async def enforce_product_line_access(
    user: User,
    entity_product_line_code: str | None,
    db: AsyncSession,
) -> None:
    """Raise 403 if user has no access to the entity's product line.
       Admin bypasses. Empty product_line_code allows all (no isolation)."""
    if user.role_definition.bypass_row_level_security:
        return
    if entity_product_line_code is None:
        return
    user_codes = await get_user_product_line_codes(user, db)
    if entity_product_line_code not in user_codes:
        raise HTTPException(
            status_code=403,
            detail=f"无权访问产品线 '{entity_product_line_code}'",
        )
