import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import RequestScope, get_request_scope
from app.core.permissions import get_user_permission, PermissionLevel, Module
from app.core.factory_scope import populate_factory_id, validate_factory_invariant

from app.schemas.control_plan import (
    ControlPlanCreate,
    ControlPlanUpdate,
    ControlPlanResponse,
    ControlPlanListResponse,
    ImportFromFMEARequest,
)
from app.services import control_plan_service

router = APIRouter(prefix="/api/control-plans", tags=["control-plans"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="控制计划不存在")


@router.get("", response_model=ControlPlanListResponse)
async def list_control_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.PLANNING, db)
    if level_perm < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要计划模块的 VIEW 权限")
    # Product line scope filtering
    if scope.pl_scope.mode == "NONE":
        return ControlPlanListResponse(items=[], total=0, page=page, page_size=page_size)
    allowed_pls = scope.pl_scope.codes if scope.pl_scope.mode == "EXPLICIT" else None
    result = await control_plan_service.list_control_plans(
        db, page, page_size, product_line,
        factory_id=scope.effective_factory_id, allowed_product_lines=allowed_pls,
    )
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
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.PLANNING, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要计划模块的 CREATE 权限")
    try:
        cp = await control_plan_service.create_control_plan(db, req, scope.user.user_id)
        await populate_factory_id(cp, type(cp), db, scope=scope)
        await validate_factory_invariant(cp, db)
        await db.commit()
        await db.refresh(cp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ControlPlanResponse.model_validate(cp)


@router.get("/{cp_id}", response_model=ControlPlanResponse)
async def get_control_plan(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    _check_factory_access(cp, scope)
    return ControlPlanResponse.model_validate(cp)


@router.put("/{cp_id}", response_model=ControlPlanResponse)
async def update_control_plan(
    cp_id: uuid.UUID,
    req: ControlPlanUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.PLANNING, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要计划模块的 CREATE 权限")
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    _check_factory_access(cp, scope)
    try:
        cp = await control_plan_service.update_control_plan(db, cp, req, scope.user.user_id)
    except ValueError as e:
        error_msg = str(e)
        if error_msg == "lock_version_mismatch":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "Document has been modified by another user.",
                    "conflict": {
                        "saved_by": None,
                        "saved_at": None,
                        "latest_lock_version": cp.lock_version,
                    },
                },
            )
        if error_msg == "lock_version_changed_again":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "Document was modified again while you were reviewing. Please refresh.",
                    "conflict": {
                        "saved_by": None,
                        "saved_at": None,
                        "latest_lock_version": cp.lock_version,
                    },
                },
            )
        raise HTTPException(status_code=400, detail=error_msg)
    return ControlPlanResponse.model_validate(cp)


@router.delete("/{cp_id}")
async def delete_control_plan(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.PLANNING, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要计划模块的 CREATE 权限")
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    _check_factory_access(cp, scope)
    await control_plan_service.delete_control_plan(db, cp, scope.user.user_id)
    return {"message": "已删除"}


@router.post("/{cp_id}/import-from-fmea")
async def import_from_fmea(
    cp_id: uuid.UUID,
    req: ImportFromFMEARequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.PLANNING, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要计划模块的 CREATE 权限")
    try:
        items = await control_plan_service.import_from_fmea(db, cp_id, req, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"imported_count": len(items)}


@router.get("/{cp_id}/stale-check")
async def stale_check(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    _check_factory_access(cp, scope)
    try:
        stale = await control_plan_service.check_stale_items(db, cp_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"stale_items": stale}


@router.post("/{cp_id}/approve", response_model=ControlPlanResponse)
async def approve_control_plan(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.PLANNING, db)
    if level_perm < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要计划模块的 APPROVE 权限")
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    _check_factory_access(cp, scope)
    try:
        cp = await control_plan_service.approve_control_plan(db, cp, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ControlPlanResponse.model_validate(cp)


# ─── CSR Sync ───

from app.schemas.control_plan import CSRSyncRequest


@router.post("/{plan_id}/sync-csr")
async def sync_csr_endpoint(
    plan_id: uuid.UUID,
    req: CSRSyncRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.PLANNING, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要计划模块的 CREATE 权限")
    try:
        plan = await control_plan_service.sync_csr_to_control_plan(
            db, plan_id, req.customer_ids, scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ControlPlanResponse.model_validate(plan)