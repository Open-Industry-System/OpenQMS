import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User
from app.schemas.customer_quality import (
    ShipmentRecordCreate,
    ShipmentRecordUpdate,
    ShipmentRecordResponse,
    ShipmentRecordListResponse,
)
from app.services import customer_quality_service

router = APIRouter(prefix="/api/customers", tags=["shipments"])


@router.get("/{customer_id}/shipments", response_model=ShipmentRecordListResponse)
async def list_shipments(
    customer_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await customer_quality_service.list_shipments(db, customer_id, page, page_size)
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
    user: User = Depends(require_engineer_or_admin),
):
    try:
        shipment = await customer_quality_service.create_shipment(db, customer_id, req.model_dump(), user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ShipmentRecordResponse.model_validate(shipment)


@router.put("/{customer_id}/shipments/{shipment_id}", response_model=ShipmentRecordResponse)
async def update_shipment(
    customer_id: uuid.UUID,
    shipment_id: uuid.UUID,
    req: ShipmentRecordUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        shipment = await customer_quality_service.update_shipment(db, customer_id, shipment_id, req.model_dump(exclude_unset=True), user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ShipmentRecordResponse.model_validate(shipment)


@router.delete("/{customer_id}/shipments/{shipment_id}", status_code=204)
async def delete_shipment(
    customer_id: uuid.UUID,
    shipment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        await customer_quality_service.delete_shipment(db, customer_id, shipment_id, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return None
