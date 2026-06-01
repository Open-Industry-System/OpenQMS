from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import require_permission, Module, PermissionLevel
from app.core.product_line_filter import get_user_product_line_codes
from app.models.user import User
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.DASHBOARD, PermissionLevel.VIEW)),
):
    if user.role_definition.bypass_row_level_security:
        filter_codes = [product_line] if product_line else None
    else:
        user_codes = await get_user_product_line_codes(user, db)
        if not user_codes:
            return {"kpi": {}, "trends": {}, "alerts": []}
        if product_line:
            if product_line not in user_codes:
                raise HTTPException(403, f"无权访问产品线 '{product_line}'")
            filter_codes = [product_line]
        else:
            filter_codes = user_codes
    return await dashboard_service.get_dashboard(db, product_line_codes=filter_codes)


@router.get("/kpi")
async def get_kpi(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.DASHBOARD, PermissionLevel.VIEW)),
):
    if user.role_definition.bypass_row_level_security:
        filter_codes = [product_line] if product_line else None
    else:
        user_codes = await get_user_product_line_codes(user, db)
        if not user_codes:
            return {}
        if product_line:
            if product_line not in user_codes:
                raise HTTPException(403, f"无权访问产品线 '{product_line}'")
            filter_codes = [product_line]
        else:
            filter_codes = user_codes
    data = await dashboard_service.get_dashboard(db, product_line_codes=filter_codes)
    return data["kpi"]


@router.get("/trends")
async def get_trends(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.DASHBOARD, PermissionLevel.VIEW)),
):
    if user.role_definition.bypass_row_level_security:
        filter_codes = [product_line] if product_line else None
    else:
        user_codes = await get_user_product_line_codes(user, db)
        if not user_codes:
            return {}
        if product_line:
            if product_line not in user_codes:
                raise HTTPException(403, f"无权访问产品线 '{product_line}'")
            filter_codes = [product_line]
        else:
            filter_codes = user_codes
    data = await dashboard_service.get_dashboard(db, product_line_codes=filter_codes)
    return data["trends"]


@router.get("/alerts")
async def get_alerts(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.DASHBOARD, PermissionLevel.VIEW)),
):
    if user.role_definition.bypass_row_level_security:
        filter_codes = [product_line] if product_line else None
    else:
        user_codes = await get_user_product_line_codes(user, db)
        if not user_codes:
            return {}
        if product_line:
            if product_line not in user_codes:
                raise HTTPException(403, f"无权访问产品线 '{product_line}'")
            filter_codes = [product_line]
        else:
            filter_codes = user_codes
    return await dashboard_service.get_alerts(db, product_line_codes=filter_codes)


@router.get("/summary")
async def get_summary(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.DASHBOARD, PermissionLevel.VIEW)),
):
    if user.role_definition.bypass_row_level_security:
        filter_codes = [product_line] if product_line else None
    else:
        user_codes = await get_user_product_line_codes(user, db)
        if not user_codes:
            return {}
        if product_line:
            if product_line not in user_codes:
                raise HTTPException(403, f"无权访问产品线 '{product_line}'")
            filter_codes = [product_line]
        else:
            filter_codes = user_codes
    return await dashboard_service.get_summary(db, product_line_codes=filter_codes)


@router.get("/recent-actions")
async def get_recent_actions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.DASHBOARD, PermissionLevel.VIEW)),
):
    return await dashboard_service.get_recent_actions(db, user.user_id)
