import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import get_current_user, require_permission, Module, PermissionLevel
from app.core.product_line_filter import get_user_product_line_codes, enforce_product_line_access
from app.models.user import User

from app.schemas.fmea import (
    FMEACreate, FMEAUpdate, FMEAResponse, FMEAListResponse, TransitionRequest,
)
from app.services import fmea_service

router = APIRouter(prefix="/api/fmea", tags=["fmea"])


@router.get("", response_model=FMEAListResponse)
async def list_fmeas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: str | None = None,
    product_line: str | None = None,
    high_rpn: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.VIEW)),
):
    allowed_pls = None
    if not user.role_definition.bypass_row_level_security:
        allowed_pls = await get_user_product_line_codes(user, db)
        if not allowed_pls:
            return FMEAListResponse(items=[], total=0, page=page, page_size=page_size)
    items, total = await fmea_service.list_fmeas(db, page, page_size, status, product_line, high_rpn=high_rpn, allowed_product_line_codes=allowed_pls)
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
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.CREATE)),
):
    try:
        await enforce_product_line_access(user, req.product_line_code, db)
        fmea = await fmea_service.create_fmea(db, req.title, req.document_no, req.fmea_type, user.user_id, req.product_line_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return FMEAResponse.model_validate(fmea)


@router.get("/{fmea_id}", response_model=FMEAResponse)
async def get_fmea(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.VIEW)),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)
    return FMEAResponse.model_validate(fmea)


@router.put("/{fmea_id}", response_model=FMEAResponse)
async def update_fmea(
    fmea_id: uuid.UUID,
    req: FMEAUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.EDIT)),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)
    if req.product_line_code is not None and req.product_line_code != fmea.product_line_code:
        await enforce_product_line_access(user, req.product_line_code, db)
    graph_dict = req.graph_data.model_dump() if req.graph_data else None
    fmea = await fmea_service.update_fmea(db, fmea, req.title, graph_dict, user.user_id, req.product_line_code)
    return FMEAResponse.model_validate(fmea)


async def require_approve_permission(
    req: TransitionRequest,
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.EDIT)),
    db: AsyncSession = Depends(get_db),
) -> User:
    if req.target_status == "approved":
        from app.core.permissions import get_user_permission
        level = await get_user_permission(user, Module.FMEA, db)
        if level < PermissionLevel.APPROVE:
            raise HTTPException(status_code=403, detail="审批权限不足")
    return user


@router.post("/{fmea_id}/transition", response_model=FMEAResponse)
async def transition_fmea(
    fmea_id: uuid.UUID,
    req: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_approve_permission),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)
    try:
        fmea = await fmea_service.transition_fmea(db, fmea, req.target_status, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return FMEAResponse.model_validate(fmea)


@router.post("/{fmea_id}/recommend", response_model=dict)
async def recommend_fmea(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.VIEW)),
):
    """预留：Phase 3 接入历史数据推荐"""
    raise HTTPException(status_code=501, detail="历史数据推荐功能将在 Phase 3 实现")


@router.get("/{fmea_id}/graph")
async def get_fmea_graph(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.VIEW)),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)
    return fmea.graph_data


@router.get("/{fmea_id}/severity-warnings")
async def severity_warnings(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.VIEW)),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)
    from app.services.special_characteristic_service import check_severity_compliance
    return await check_severity_compliance(db, fmea_id)
