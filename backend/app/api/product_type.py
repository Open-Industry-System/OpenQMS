from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_request_scope
from app.core.permissions import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas import product_type as schemas
from app.services import product_type_service

router = APIRouter(prefix="/api/product-types", tags=["product-types"])


@router.get("", response_model=schemas.ProductTypeListResponse)
async def list_product_types(
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _scope: RequestScope = Depends(get_request_scope),
):
    items = await product_type_service.list_product_types(db, is_active)
    return schemas.ProductTypeListResponse(items=[schemas.ProductTypeResponse.model_validate(i) for i in items])


@router.post("", response_model=schemas.ProductTypeResponse)
async def create_product_type(
    req: schemas.ProductTypeCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    _user: User = Depends(require_admin),
):
    try:
        pt = await product_type_service.create_product_type(db, req.code, req.name, req.description, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.ProductTypeResponse.model_validate(pt)


@router.put("/{code}", response_model=schemas.ProductTypeResponse)
async def update_product_type(
    code: str,
    req: schemas.ProductTypeUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    _user: User = Depends(require_admin),
):
    pt = await product_type_service.get_product_type(db, code)
    if not pt:
        raise HTTPException(status_code=404, detail=f"产品类型 '{code}' 不存在")
    try:
        updated = await product_type_service.update_product_type(db, pt, req.name, req.description, req.is_active, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.ProductTypeResponse.model_validate(updated)


@router.delete("/{code}")
async def delete_product_type(
    code: str,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    _user: User = Depends(require_admin),
):
    pt = await product_type_service.get_product_type(db, code)
    if not pt:
        raise HTTPException(status_code=404, detail=f"产品类型 '{code}' 不存在")
    try:
        await product_type_service.delete_product_type(db, pt, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": f"产品类型 '{code}' 已停用"}
