from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.core.permissions import get_user_permission, Module, PermissionLevel
from app.core.deps import RequestScope, get_request_scope
from app.models.user import User
from app.models.user_dashboard_layout import UserDashboardLayout
from app.schemas import dashboard_layout as layout_schemas
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _resolve_filter_codes(scope: RequestScope, product_line: str | None = None) -> tuple[list[str] | None, bool]:
    """Resolve product line filter codes from scope + optional product_line query param.

    Returns (filter_codes, should_return_empty):
      - filter_codes: list of codes to filter on, or None for no filter
      - should_return_empty: True if the user has no access at all
    """
    if scope.pl_scope.mode == "NONE":
        return None, True
    elif scope.pl_scope.mode == "ALL":
        if product_line:
            return [product_line], False
        return None, False
    else:  # EXPLICIT
        if product_line:
            if product_line not in (scope.pl_scope.codes or []):
                raise HTTPException(403, f"无权访问产品线 '{product_line}'")
            return [product_line], False
        return scope.pl_scope.codes, False


@router.get("")
async def get_dashboard(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.DASHBOARD, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 dashboard 模块的 VIEW 权限")
    filter_codes, empty = _resolve_filter_codes(scope, product_line)
    if empty:
        return {"kpi": {}, "trends": {}, "alerts": []}
    return await dashboard_service.get_dashboard(db, product_line_codes=filter_codes, factory_id=scope.effective_factory_id)


@router.get("/kpi")
async def get_kpi(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.DASHBOARD, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 dashboard 模块的 VIEW 权限")
    filter_codes, empty = _resolve_filter_codes(scope, product_line)
    if empty:
        return {}
    data = await dashboard_service.get_dashboard(db, product_line_codes=filter_codes, factory_id=scope.effective_factory_id)
    return data["kpi"]


@router.get("/trends")
async def get_trends(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.DASHBOARD, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 dashboard 模块的 VIEW 权限")
    filter_codes, empty = _resolve_filter_codes(scope, product_line)
    if empty:
        return {}
    data = await dashboard_service.get_dashboard(db, product_line_codes=filter_codes, factory_id=scope.effective_factory_id)
    return data["trends"]


@router.get("/alerts")
async def get_alerts(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.DASHBOARD, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 dashboard 模块的 VIEW 权限")
    filter_codes, empty = _resolve_filter_codes(scope, product_line)
    if empty:
        return {}
    return await dashboard_service.get_alerts(db, product_line_codes=filter_codes, factory_id=scope.effective_factory_id)


@router.get("/summary")
async def get_summary(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.DASHBOARD, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 dashboard 模块的 VIEW 权限")
    filter_codes, empty = _resolve_filter_codes(scope, product_line)
    if empty:
        return {}
    return await dashboard_service.get_summary(db, product_line_codes=filter_codes, factory_id=scope.effective_factory_id)


@router.get("/recent-actions")
async def get_recent_actions(
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.DASHBOARD, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 dashboard 模块的 VIEW 权限")
    return await dashboard_service.get_recent_actions(db, scope.user.user_id)

@router.get("/layout")
async def get_layout(
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.DASHBOARD, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 dashboard 模块的 VIEW 权限")
    result = await db.execute(
        select(UserDashboardLayout).where(UserDashboardLayout.user_id == scope.user.user_id)
    )
    layout = result.scalar_one_or_none()

    if layout is None:
        from app.services.dashboard_service import get_default_layout

        default_config = await get_default_layout(db, scope.user)
        return layout_schemas.DashboardLayoutResponse(
            layout_id=None,
            user_id=scope.user.user_id,
            layout_config=layout_schemas.LayoutConfig.model_validate(default_config),
            created_at=None,
            updated_at=None,
        )

    from app.services.dashboard_service import filter_layout_by_permissions

    filtered_config = await filter_layout_by_permissions(layout.layout_config, scope.user, db)
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
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.DASHBOARD, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 dashboard 模块的 EDIT 权限")
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
        if not await _user_can_view_module(scope.user, module, db):
            raise HTTPException(status_code=403, detail=f"no permission for widget type: {widget.type}")

        min_size = WIDGET_MIN_SIZES.get(widget.type, {"w": 1, "h": 1})
        if widget.w < min_size["w"] or widget.h < min_size["h"]:
            raise HTTPException(status_code=400, detail=f"widget {widget.type} size below minimum")

    result = await db.execute(
        select(UserDashboardLayout).where(UserDashboardLayout.user_id == scope.user.user_id)
    )
    layout = result.scalar_one_or_none()

    if layout is None:
        layout = UserDashboardLayout(
            user_id=scope.user.user_id,
            layout_config=req.layout_config.model_dump(),
        )
        db.add(layout)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            result = await db.execute(
                select(UserDashboardLayout).where(UserDashboardLayout.user_id == scope.user.user_id)
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
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.DASHBOARD, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 dashboard 模块的 VIEW 权限")
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
        if await _user_can_view_module(scope.user, module, db):
            allowed_types.append(widget_type)

    quality_trend_allowed_modules = set()
    if "quality_trend_ai_summary" in allowed_types:
        for module in ("spc", "capa", "fmea"):
            if await dashboard_service._user_can_view_module(scope.user, module, db):
                quality_trend_allowed_modules.add(module)

    filter_codes, empty = _resolve_filter_codes(scope, product_line)
    if empty:
        return layout_schemas.DashboardWidgetsResponse()

    data = await dashboard_service.get_widgets_data(
        db, allowed_types, filter_codes, scope.user.user_id,
        quality_trend_allowed_modules=quality_trend_allowed_modules,
        factory_id=scope.effective_factory_id,
    )
    return layout_schemas.DashboardWidgetsResponse(**data)


from fastapi import Request
from pydantic import BaseModel
from app.services.quality_trend_service import (
    InsufficientTrendDataError,
    LLMNotConfiguredError,
    LLMResponseParseError,
    RateLimitError,
    build_scope_description,
    build_scope_hash,
    interpret_quality_trend as interpret_quality_trend_service,
)


class QualityTrendInterpretRequest(BaseModel):
    product_line: str | None = None


@router.post("/widgets/quality-trend/interpret")
async def interpret_quality_trend(
    req: QualityTrendInterpretRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.DASHBOARD, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 dashboard 模块的 VIEW 权限")

    filter_codes, empty = _resolve_filter_codes(scope, req.product_line)
    if empty:
        raise HTTPException(status_code=403, detail="无可访问产品线")

    quality_trend_allowed_modules = set()
    for module in ("spc", "capa", "fmea"):
        if await dashboard_service._user_can_view_module(scope.user, module, db):
            quality_trend_allowed_modules.add(module)

    scope_description = build_scope_description(filter_codes or None)
    scope_hash = await build_scope_hash(filter_codes)
    llm_provider = getattr(request.app.state, "llm_provider", None)

    try:
        return await interpret_quality_trend_service(
            db=db,
            user_id=str(scope.user.user_id),
            llm_provider=llm_provider,
            filter_codes=filter_codes,
            allowed_modules=quality_trend_allowed_modules,
            scope_description=scope_description,
            selected_product_line=filter_codes[0] if filter_codes and len(filter_codes) == 1 else None,
            scope_hash=scope_hash,
        )
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InsufficientTrendDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMResponseParseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="AI 解读生成失败") from exc