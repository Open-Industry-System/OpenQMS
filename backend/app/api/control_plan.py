import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User

from app.schemas.control_plan import (
    ControlPlanCreate,
    ControlPlanUpdate,
    ControlPlanResponse,
    ControlPlanListResponse,
    ImportFromFMEARequest,
)
from app.services import control_plan_service

router = APIRouter(prefix="/api/control-plans", tags=["control-plans"])


@router.get("", response_model=ControlPlanListResponse)
async def list_control_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await control_plan_service.list_control_plans(db, page, page_size)
    return ControlPlanListResponse(
        items=[ControlPlanResponse.model_validate(cp) for cp in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.post("", response_model=ControlPlanResponse, status_code=201)
async def create_control_plan(
    req: ControlPlanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        cp = await control_plan_service.create_control_plan(db, req, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ControlPlanResponse.model_validate(cp)


@router.get("/{cp_id}", response_model=ControlPlanResponse)
async def get_control_plan(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    return ControlPlanResponse.model_validate(cp)


@router.put("/{cp_id}", response_model=ControlPlanResponse)
async def update_control_plan(
    cp_id: uuid.UUID,
    req: ControlPlanUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    try:
        cp = await control_plan_service.update_control_plan(db, cp, req, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ControlPlanResponse.model_validate(cp)


@router.delete("/{cp_id}")
async def delete_control_plan(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    await control_plan_service.delete_control_plan(db, cp, user.user_id)
    return {"message": "已删除"}


@router.post("/{cp_id}/import-from-fmea")
async def import_from_fmea(
    cp_id: uuid.UUID,
    req: ImportFromFMEARequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        items = await control_plan_service.import_from_fmea(db, cp_id, req, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"imported_count": len(items)}


@router.get("/{cp_id}/stale-check")
async def stale_check(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    try:
        stale = await control_plan_service.check_stale_items(db, cp_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"stale_items": stale}


@router.post("/{cp_id}/approve", response_model=ControlPlanResponse)
async def approve_control_plan(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    if user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="仅管理员或经理可批准")
    try:
        cp = await control_plan_service.approve_control_plan(db, cp, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ControlPlanResponse.model_validate(cp)
