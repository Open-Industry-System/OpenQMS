from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.core.permissions import require_permission, Module, PermissionLevel
from app.core.product_line_filter import get_user_product_line_codes
from app.models.user import User
from app.models.user_dashboard_layout import UserDashboardLayout
from app.schemas import dashboard_layout as layout_schemas
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

@router.get("/layout")
async def get_layout(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.DASHBOARD, PermissionLevel.VIEW)),
):
    result = await db.execute(
        select(UserDashboardLayout).where(UserDashboardLayout.user_id == user.user_id)
    )
    layout = result.scalar_one_or_none()

    if layout is None:
        from app.services.dashboard_service import get_default_layout

        default_config = await get_default_layout(db, user)
        return layout_schemas.DashboardLayoutResponse(
            layout_id=None,
            user_id=user.user_id,
            layout_config=layout_schemas.LayoutConfig.model_validate(default_config),
            created_at=None,
            updated_at=None,
        )

    from app.services.dashboard_service import filter_layout_by_permissions

    filtered_config = await filter_layout_by_permissions(layout.layout_config, user, db)
    return layout_schemas.DashboardLayoutResponse(
        layout_id=layout.layout_id,
        user_id=layout.user_id,
        layout_config=layout_schemas.LayoutConfig.model_validate(filtered_config),
        created_at=layout.created_at.isoformat() if layout.created_at else None,
        updated_at=layout.updated_at.isoformat() if layout.updated_at else None,
    )


@router.put("/layout")
async def save_layout(
    req: layout_schemas.DashboardLayoutUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.DASHBOARD, PermissionLevel.EDIT)),
):
    from app.services.dashboard_service import (
        WIDGET_MIN_SIZES,
        WIDGET_MODULE_MAP,
        _user_can_view_module,
    )

    seen_i = set()
    for widget in req.layout_config.lg:
        if widget.i in seen_i:
            raise HTTPException(status_code=400, detail=f"duplicate widget id: {widget.i}")
        seen_i.add(widget.i)

        if widget.x < 0 or widget.y < 0:
            raise HTTPException(status_code=400, detail="coordinates must be non-negative")
        if widget.w > 12 or widget.h > 50:
            raise HTTPException(status_code=400, detail="widget size exceeds grid bounds")
        if widget.x + widget.w > 12:
            raise HTTPException(status_code=400, detail="widget exceeds horizontal grid boundary")
        if widget.type not in WIDGET_MODULE_MAP:
            raise HTTPException(status_code=400, detail=f"invalid widget type: {widget.type}")

        module = WIDGET_MODULE_MAP[widget.type]
        if not await _user_can_view_module(user, module, db):
            raise HTTPException(status_code=403, detail=f"no permission for widget type: {widget.type}")

        min_size = WIDGET_MIN_SIZES.get(widget.type, {"w": 1, "h": 1})
        if widget.w < min_size["w"] or widget.h < min_size["h"]:
            raise HTTPException(status_code=400, detail=f"widget {widget.type} size below minimum")

    result = await db.execute(
        select(UserDashboardLayout).where(UserDashboardLayout.user_id == user.user_id)
    )
    layout = result.scalar_one_or_none()

    if layout is None:
        layout = UserDashboardLayout(
            user_id=user.user_id,
            layout_config=req.layout_config.model_dump(),
        )
        db.add(layout)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            result = await db.execute(
                select(UserDashboardLayout).where(UserDashboardLayout.user_id == user.user_id)
            )
            layout = result.scalar_one_or_none()
            if layout is None:
                raise
            layout.layout_config = req.layout_config.model_dump()
            await db.commit()
    else:
        layout.layout_config = req.layout_config.model_dump()
        await db.commit()

    await db.refresh(layout)

    return layout_schemas.DashboardLayoutResponse(
        layout_id=layout.layout_id,
        user_id=layout.user_id,
        layout_config=layout_schemas.LayoutConfig.model_validate(layout.layout_config),
        created_at=layout.created_at.isoformat() if layout.created_at else None,
        updated_at=layout.updated_at.isoformat() if layout.updated_at else None,
    )


@router.get("/widgets")
async def get_widgets(
    types: str = Query("", description="Comma-separated widget types"),
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.DASHBOARD, PermissionLevel.VIEW)),
):
    type_list = list(dict.fromkeys(t.strip() for t in (types or "").split(",") if t.strip()))
    if not type_list:
        return layout_schemas.DashboardWidgetsResponse()

    from app.services.dashboard_service import WIDGET_MODULE_MAP, _user_can_view_module

    invalid = [widget_type for widget_type in type_list if widget_type not in WIDGET_MODULE_MAP]
    if invalid:
        raise HTTPException(status_code=400, detail=f"unknown widget type: {', '.join(invalid)}")

    allowed_types = []
    for widget_type in type_list:
        module = WIDGET_MODULE_MAP[widget_type]
        if await _user_can_view_module(user, module, db):
            allowed_types.append(widget_type)

    if user.role_definition.bypass_row_level_security:
        filter_codes = [product_line] if product_line else None
    else:
        user_codes = await get_user_product_line_codes(user, db)
        if not user_codes:
            return layout_schemas.DashboardWidgetsResponse()
        if product_line:
            if product_line not in user_codes:
                raise HTTPException(403, f"无权访问产品线 '{product_line}'")
            filter_codes = [product_line]
        else:
            filter_codes = user_codes

    data = await dashboard_service.get_widgets_data(db, allowed_types, filter_codes, user.user_id)
    return layout_schemas.DashboardWidgetsResponse(**data)
