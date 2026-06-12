from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import RequestScope, get_request_scope
from app.core.permissions import get_user_permission, Module, PermissionLevel, get_current_user, require_admin
from app.core.factory_scope import resolve_create_factory_id, check_factory_access
from app.models.user import User
from app.schemas import product_line as schemas
from app.services import product_line_service

router = APIRouter(prefix="/api/product-lines", tags=["product-lines"])


@router.get("", response_model=schemas.ProductLineListResponse)
async def list_product_lines(
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Filter product lines by accessible factories; GROUP ADMIN sees all
    accessible = scope.factory_scope.accessible_factory_ids
    items = await product_line_service.list_product_lines(db, is_active, accessible_factory_ids=accessible)
    return schemas.ProductLineListResponse(
        items=[schemas.ProductLineResponse.model_validate(i) for i in items]
    )


@router.post("", response_model=schemas.ProductLineResponse)
async def create_product_line(
    req: schemas.ProductLineCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLANNING, db)
    if level < PermissionLevel.ADMIN:
        raise HTTPException(status_code=403, detail="需要 planning 模块的 ADMIN 权限")
    try:
        factory_id = await resolve_create_factory_id(db, scope)
        check_factory_access(factory_id, scope)
        pl = await product_line_service.create_product_line(db, req.code, req.name, factory_id=factory_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.ProductLineResponse.model_validate(pl)


@router.put("/{code}", response_model=schemas.ProductLineResponse)
async def update_product_line(
    code: str,
    req: schemas.ProductLineUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    pl = await product_line_service.get_product_line(db, code)
    if not pl:
        raise HTTPException(status_code=404, detail=f"产品线 '{code}' 不存在")
    updated = await product_line_service.update_product_line(db, pl, req.name, req.is_active)
    return schemas.ProductLineResponse.model_validate(updated)


@router.delete("/{code}")
async def delete_product_line(
    code: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    pl = await product_line_service.get_product_line(db, code)
    if not pl:
        raise HTTPException(status_code=404, detail=f"产品线 '{code}' 不存在")
    await product_line_service.delete_product_line(db, pl)
    return {"message": f"产品线 '{code}' 已停用"}
