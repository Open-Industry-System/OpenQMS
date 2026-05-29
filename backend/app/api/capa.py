import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin, require_manager_or_admin
from typing import Any
from app.models.user import User

from app.schemas.capa import CAPACreate, CAPAUpdate, CAPAResponse, CAPAListResponse
from app.services import capa_service

router = APIRouter(prefix="/api/capa", tags=["capa"])


@router.get("", response_model=CAPAListResponse)
async def list_capas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: str | None = None,
    product_line: str | None = None,
    overdue: bool = Query(False),
    pending_action: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await capa_service.list_capas(
        db, page, page_size, status, product_line,
        overdue=overdue, pending_action=pending_action,
    )
    return CAPAListResponse(
        items=[CAPAResponse.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=CAPAResponse, status_code=201)
async def create_capa(
    req: CAPACreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        capa = await capa_service.create_capa(
            db, req.title, req.document_no, req.severity, req.due_date, user.user_id, req.product_line_code
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CAPAResponse.model_validate(capa)


@router.get("/by-fmea-node/{fmea_id}")
async def get_capas_by_fmea_node(
    fmea_id: str,
    fmea_node_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await capa_service.get_capas_by_fmea_node(db, fmea_id, fmea_node_id)


@router.get("/{report_id}", response_model=CAPAResponse)
async def get_capa(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    return CAPAResponse.model_validate(capa)


@router.put("/{report_id}", response_model=CAPAResponse)
async def update_capa(
    report_id: uuid.UUID,
    req: CAPAUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    capa = await capa_service.update_capa(db, capa, req.model_dump(exclude_unset=True), user.user_id)
    return CAPAResponse.model_validate(capa)


async def require_close_permission(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
) -> tuple[User, Any]:
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    if capa.status in ["D7_PREVENTION", "D8_CLOSURE"]:
        user = await require_manager_or_admin(user)
    return user, capa


@router.post("/{report_id}/advance", response_model=CAPAResponse)
async def advance_capa(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    result: tuple[User, Any] = Depends(require_close_permission),
):
    user, capa = result
    try:
        capa = await capa_service.advance_capa(db, capa, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CAPAResponse.model_validate(capa)


@router.post("/{report_id}/link-fmea", response_model=CAPAResponse)
async def link_fmea(
    report_id: uuid.UUID,
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    capa = await capa_service.link_fmea(db, capa, fmea_id, user.user_id)
    return CAPAResponse.model_validate(capa)


@router.get("/{report_id}/related-fmea")
async def get_related_fmea(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    from app.models.capa import CAPAEightD
    from app.models.fmea import FMEADocument

    capa = (
        await db.execute(
            select(CAPAEightD).where(CAPAEightD.report_id == report_id)
        )
    ).scalar_one_or_none()
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA not found")
    if not capa.fmea_ref_id:
        return {"fmea_id": None, "document_no": None, "fmea_node_id": None}

    fmea = (
        await db.execute(
            select(FMEADocument).where(FMEADocument.fmea_id == capa.fmea_ref_id)
        )
    ).scalar_one_or_none()

    return {
        "fmea_id": str(capa.fmea_ref_id),
        "document_no": fmea.document_no if fmea else None,
        "fmea_node_id": capa.fmea_node_id,
    }
