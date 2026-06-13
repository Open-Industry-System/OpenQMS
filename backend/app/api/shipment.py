import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access, resolve_create_factory_id, validate_factory_invariant
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.database import get_db
from app.models.customer_quality import ShipmentRecord
from app.schemas.customer_quality import (
    ShipmentRecordCreate,
    ShipmentRecordListResponse,
    ShipmentRecordResponse,
    ShipmentRecordUpdate,
)
from app.services import customer_quality_service

router = APIRouter(prefix="/api/customers", tags=["shipments"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="Shipment not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="Shipment not found")


@router.get("/{customer_id}/shipments", response_model=ShipmentRecordListResponse)
async def list_shipments(
    customer_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 VIEW 权限")

    items, total = await customer_quality_service.list_shipments(
        db, customer_id, page, page_size,
        factory_id=scope.effective_factory_id,
    )
    return ShipmentRecordListResponse(
        items=[ShipmentRecordResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{customer_id}/shipments", response_model=ShipmentRecordResponse, status_code=201)
async def create_shipment(
    customer_id: uuid.UUID,
    req: ShipmentRecordCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if perm_level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")

    try:
        factory_id = await resolve_create_factory_id(db, scope, product_line_code=req.product_line_code)
        check_factory_access(factory_id, scope)
        shipment = await customer_quality_service.create_shipment(db, customer_id, req.model_dump(), scope.user.user_id, factory_id=factory_id)
        await validate_factory_invariant(shipment, db)
        await db.refresh(shipment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ShipmentRecordResponse.model_validate(shipment)


@router.put("/{customer_id}/shipments/{shipment_id}", response_model=ShipmentRecordResponse)
async def update_shipment(
    customer_id: uuid.UUID,
    shipment_id: uuid.UUID,
    req: ShipmentRecordUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if perm_level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")

    # Factory access check
    result = await db.execute(
        select(ShipmentRecord).where(
            ShipmentRecord.shipment_id == shipment_id,
            ShipmentRecord.customer_id == customer_id,
        )
    )
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail="发运记录不存在")
    _check_factory_access(shipment, scope)

    try:
        shipment = await customer_quality_service.update_shipment(db, customer_id, shipment_id, req.model_dump(exclude_unset=True), scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ShipmentRecordResponse.model_validate(shipment)


@router.delete("/{customer_id}/shipments/{shipment_id}", status_code=204)
async def delete_shipment(
    customer_id: uuid.UUID,
    shipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if perm_level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")

    # Factory access check
    result = await db.execute(
        select(ShipmentRecord).where(
            ShipmentRecord.shipment_id == shipment_id,
            ShipmentRecord.customer_id == customer_id,
        )
    )
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail="发运记录不存在")
    _check_factory_access(shipment, scope)

    try:
        await customer_quality_service.delete_shipment(db, customer_id, shipment_id, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return None