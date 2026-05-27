import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin, require_manager_or_admin
from app.models.user import User
from app.schemas import scar as scar_schemas
from app.services import scar_service

router = APIRouter(prefix="/api/scars", tags=["scars"])


def _to_response(s) -> dict:
    """Convert SupplierSCAR ORM object with loaded supplier to SCARResponse dict."""
    return scar_schemas.SCARResponse(
        scar_id=s.scar_id,
        scar_no=s.scar_no,
        supplier_id=s.supplier_id,
        supplier_name=s.supplier.name if s.supplier else None,
        supplier_no=s.supplier.supplier_no if s.supplier else None,
        source_type=s.source_type,
        source_id=s.source_id,
        description=s.description,
        product_line_code=s.product_line_code,
        requested_action=s.requested_action,
        supplier_response=s.supplier_response,
        status=s.status,
        capa_ref_id=s.capa_ref_id,
        resolution_summary=s.resolution_summary,
        issued_by=s.issued_by,
        issued_date=s.issued_date,
        due_date=s.due_date,
        closed_date=s.closed_date,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.get("", response_model=scar_schemas.SCARListResponse)
async def list_scars(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Comma-separated statuses"),
    supplier_id: uuid.UUID | None = Query(None),
    source_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    statuses = status.split(",") if status else None
    items, total = await scar_service.list_scars(
        db, page, page_size, statuses, supplier_id, source_type
    )
    return scar_schemas.SCARListResponse(
        items=[_to_response(s) for s in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{scar_id}", response_model=scar_schemas.SCARResponse)
async def get_scar(
    scar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    return _to_response(scar)


@router.post("", response_model=scar_schemas.SCARResponse)
async def create_scar(
    req: scar_schemas.SCARCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        scar = await scar_service.create_scar(
            db,
            supplier_id=req.supplier_id,
            source_type=req.source_type,
            source_id=req.source_id,
            description=req.description,
            product_line_code=req.product_line_code,
            requested_action=req.requested_action,
            due_date=req.due_date,
            user_id=user.user_id,
        )
        return _to_response(scar)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{scar_id}", response_model=scar_schemas.SCARResponse)
async def update_scar(
    scar_id: uuid.UUID,
    req: scar_schemas.SCARUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    try:
        scar = await scar_service.update_scar(
            db, scar,
            user_id=user.user_id,
            description=req.description,
            requested_action=req.requested_action,
            due_date=req.due_date,
        )
        return _to_response(scar)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{scar_id}/transition", response_model=scar_schemas.SCARResponse)
async def transition_scar(
    scar_id: uuid.UUID,
    req: scar_schemas.SCARTransitionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Route-level role check
    if req.action in ("verify", "reject", "close", "reopen"):
        if user.role not in ("admin", "manager"):
            raise HTTPException(403, "需要 manager 或 admin 权限")
    elif req.action in ("start", "respond"):
        if user.role not in ("admin", "manager", "quality_engineer"):
            raise HTTPException(403, "需要 engineer 或更高权限")

    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    try:
        scar = await scar_service.transition_scar(
            db, scar, req.action, user_id=user.user_id,
            supplier_response=req.supplier_response,
            resolution_summary=req.resolution_summary,
        )
        return _to_response(scar)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{scar_id}/link-capa", response_model=scar_schemas.SCARResponse)
async def link_capa(
    scar_id: uuid.UUID,
    req: scar_schemas.SCARLinkCAPARequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    try:
        scar = await scar_service.link_capa(db, scar, req.capa_ref_id, user.user_id)
        return _to_response(scar)
    except ValueError as e:
        raise HTTPException(400, str(e))
