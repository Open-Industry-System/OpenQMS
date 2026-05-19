import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.fmea import (
    FMEACreate, FMEAUpdate, FMEAResponse, FMEAListResponse, TransitionRequest,
)
from app.services import fmea_service

router = APIRouter(prefix="/api/fmea", tags=["fmea"])


@router.get("", response_model=FMEAListResponse)
async def list_fmeas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await fmea_service.list_fmeas(db, page, page_size, status)
    return FMEAListResponse(
        items=[FMEAResponse.model_validate(f) for f in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=FMEAResponse, status_code=201)
async def create_fmea(
    req: FMEACreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fmea = await fmea_service.create_fmea(db, req.title, req.document_no, req.fmea_type, user.user_id)
    return FMEAResponse.model_validate(fmea)


@router.get("/{fmea_id}", response_model=FMEAResponse)
async def get_fmea(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    return FMEAResponse.model_validate(fmea)


@router.put("/{fmea_id}", response_model=FMEAResponse)
async def update_fmea(
    fmea_id: uuid.UUID,
    req: FMEAUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    graph_dict = req.graph_data.model_dump() if req.graph_data else None
    fmea = await fmea_service.update_fmea(db, fmea, req.title, graph_dict, user.user_id)
    return FMEAResponse.model_validate(fmea)


@router.post("/{fmea_id}/transition", response_model=FMEAResponse)
async def transition_fmea(
    fmea_id: uuid.UUID,
    req: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    try:
        fmea = await fmea_service.transition_fmea(db, fmea, req.target_status, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return FMEAResponse.model_validate(fmea)


@router.get("/{fmea_id}/graph")
async def get_fmea_graph(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    return fmea.graph_data
