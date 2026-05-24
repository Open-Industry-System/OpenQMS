import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User
from app.schemas.special_characteristic import (
    SCCreate, SCUpdate, SCResponse, SCListResponse,
    MatrixResponse, SeverityWarning, CPSyncStatusResponse,
)
from app.services import special_characteristic_service as sc_svc

router = APIRouter(prefix="/api/special-characteristics", tags=["special-characteristics"])


@router.get("/list", response_model=SCListResponse)
async def list_scs(
    sc_type: str | None = None,
    product_line: str | None = None,
    source_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await sc_svc.list_special_characteristics(
        db, sc_type, product_line, source_type, page, page_size,
    )


@router.get("/matrix", response_model=MatrixResponse)
async def get_matrix(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await sc_svc.get_matrix(db, product_line)


@router.get("/cp-sync-status/{cp_id}", response_model=CPSyncStatusResponse)
async def cp_sync_status(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await sc_svc.check_cp_sync_status(db, cp_id)


@router.get("/{sc_id}", response_model=SCResponse)
async def get_sc(
    sc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await sc_svc.get_special_characteristic(db, sc_id)
    if not result:
        raise HTTPException(404, "Special characteristic not found")
    return result


@router.post("/create", response_model=SCResponse, status_code=201)
async def create_sc(
    data: SCCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    return await sc_svc.create_special_characteristic(db, data, user.user_id)


@router.put("/{sc_id}", response_model=SCResponse)
async def update_sc(
    sc_id: uuid.UUID,
    data: SCUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    result = await sc_svc.update_special_characteristic(db, sc_id, data, user.user_id)
    if not result:
        raise HTTPException(404, "Special characteristic not found")
    return result


@router.delete("/{sc_id}")
async def delete_sc(
    sc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    ok = await sc_svc.delete_special_characteristic(db, sc_id, user.user_id)
    if not ok:
        raise HTTPException(404, "Special characteristic not found")
    return {"detail": "deleted"}


@router.post("/sync-from-fmea/{fmea_id}")
async def sync_from_fmea(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        result = await sc_svc.sync_from_fmea(db, fmea_id, user.user_id)
        return {"detail": "synced", "count": len(result)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/sync-to-cp/{cp_id}")
async def sync_to_cp(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        result = await sc_svc.sync_to_cp(db, cp_id, user.user_id)
        return {"detail": "synced", "updated_count": len(result)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/msa-callback/{sc_id}", response_model=SCResponse)
async def msa_callback(
    sc_id: uuid.UUID,
    grr_percent: float = Query(..., ge=0, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    result = await sc_svc.update_msa_status(db, sc_id, grr_percent)
    if not result:
        raise HTTPException(404, "Special characteristic not found")
    return result
