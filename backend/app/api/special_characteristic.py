import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access, resolve_create_factory_id, validate_factory_invariant
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.database import get_db
from app.models.special_characteristic import SpecialCharacteristic as SCModel
from app.schemas.special_characteristic import (
    CPSyncStatusResponse,
    MatrixResponse,
    SafetyApprovalAction,
    SafetySubmitRequest,
    SCCreate,
    SCListResponse,
    SCResponse,
    SCUpdate,
)
from app.services import special_characteristic_service as sc_svc

router = APIRouter(prefix="/api/special-characteristics", tags=["special-characteristics"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="Special characteristic not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="Special characteristic not found")


@router.get("/list", response_model=SCListResponse)
async def list_scs(
    sc_type: str | None = None,
    product_line: str | None = None,
    source_type: str | None = None,
    safety_related_only: bool = False,
    approval_status: str | None = None,
    suggested_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Product line scope filtering
    if scope.pl_scope.mode == "NONE":
        return SCListResponse(items=[], total=0, page=page, page_size=page_size)
    allowed_pls = scope.pl_scope.codes if scope.pl_scope.mode == "EXPLICIT" else None
    return await sc_svc.list_special_characteristics(
        db, sc_type, product_line, source_type, page, page_size,
        safety_related_only, approval_status, suggested_only,
        factory_id=scope.effective_factory_id, allowed_product_lines=allowed_pls,
    )


@router.get("/matrix", response_model=MatrixResponse)
async def get_matrix(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    return await sc_svc.get_matrix(db, product_line, factory_id=scope.effective_factory_id)


@router.get("/traceability/{sc_id}")
async def get_traceability(
    sc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    try:
        result = await sc_svc.get_traceability_chain(db, sc_id)
        # Traceability returns a dict; check factory access on the SC itself
        sc = await sc_svc.get_special_characteristic(db, sc_id)
        if sc and hasattr(sc, "factory_id"):
            _check_factory_access(sc, scope)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/cp-sync-status/{cp_id}", response_model=CPSyncStatusResponse)
async def cp_sync_status(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    return await sc_svc.check_cp_sync_status(db, cp_id)


@router.get("/{sc_id}/references")
async def get_sc_references(
    sc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    return await sc_svc.get_sc_references(db, sc_id)


@router.get("/{sc_id}", response_model=SCResponse)
async def get_sc(
    sc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    result = await sc_svc.get_special_characteristic(db, sc_id)
    if not result:
        raise HTTPException(404, "Special characteristic not found")
    _check_factory_access(result, scope)
    return result


@router.post("/create", response_model=SCResponse, status_code=201)
async def create_sc(
    data: SCCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要特殊特性模块的 CREATE 权限")
    factory_id = await resolve_create_factory_id(db, scope, product_line_code=data.product_line_code)
    check_factory_access(factory_id, scope)
    result = await sc_svc.create_special_characteristic(db, data, scope.user.user_id, factory_id=factory_id)
    # Re-fetch ORM model to validate factory_id
    orm_result = await db.execute(select(SCModel).where(SCModel.sc_id == result.sc_id))
    orm_sc = orm_result.scalar_one_or_none()
    if orm_sc:
        await validate_factory_invariant(orm_sc, db)
        await db.refresh(orm_sc)
        result = sc_svc._to_response(orm_sc)
    return result


@router.put("/{sc_id}", response_model=SCResponse)
async def update_sc(
    sc_id: uuid.UUID,
    data: SCUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要特殊特性模块的 CREATE 权限")
    result = await sc_svc.update_special_characteristic(db, sc_id, data, scope.user.user_id)
    if not result:
        raise HTTPException(404, "Special characteristic not found")
    _check_factory_access(result, scope)
    return result


@router.delete("/{sc_id}")
async def delete_sc(
    sc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要特殊特性模块的 CREATE 权限")
    # Fetch first to check factory access
    existing = await sc_svc.get_special_characteristic(db, sc_id)
    if not existing:
        raise HTTPException(404, "Special characteristic not found")
    _check_factory_access(existing, scope)
    ok = await sc_svc.delete_special_characteristic(db, sc_id, scope.user.user_id)
    if not ok:
        raise HTTPException(404, "Special characteristic not found")
    return {"detail": "deleted"}


@router.post("/sync-from-fmea/{fmea_id}")
async def sync_from_fmea(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要特殊特性模块的 CREATE 权限")
    try:
        result = await sc_svc.sync_from_fmea(db, fmea_id, scope.user.user_id)
        return {"detail": "synced", "count": len(result)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/sync-to-cp/{cp_id}")
async def sync_to_cp(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要特殊特性模块的 CREATE 权限")
    try:
        result = await sc_svc.sync_to_cp(db, cp_id, scope.user.user_id)
        return {"detail": "synced", "updated_count": len(result)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/msa-callback/{sc_id}", response_model=SCResponse)
async def msa_callback(
    sc_id: uuid.UUID,
    grr_percent: float = Query(..., ge=0, le=100),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要特殊特性模块的 CREATE 权限")
    result = await sc_svc.update_msa_status(db, sc_id, grr_percent)
    if not result:
        raise HTTPException(404, "Special characteristic not found")
    _check_factory_access(result, scope)
    return result


@router.post("/{sc_id}/safety-submit", response_model=SCResponse)
async def safety_submit(
    sc_id: uuid.UUID,
    data: SafetySubmitRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要特殊特性模块的 CREATE 权限")
    try:
        result = await sc_svc.safety_submit(db, sc_id, data, scope.user.user_id)
        _check_factory_access(result, scope)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{sc_id}/safety-approve", response_model=SCResponse)
async def safety_approve(
    sc_id: uuid.UUID,
    data: SafetyApprovalAction,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if level_perm < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要特殊特性模块的 APPROVE 权限")
    try:
        result = await sc_svc.safety_approve(db, sc_id, data, scope.user.user_id)
        _check_factory_access(result, scope)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{sc_id}/safety-reject", response_model=SCResponse)
async def safety_reject(
    sc_id: uuid.UUID,
    data: SafetyApprovalAction,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if level_perm < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要特殊特性模块的 APPROVE 权限")
    try:
        result = await sc_svc.safety_reject(db, sc_id, data, scope.user.user_id)
        _check_factory_access(result, scope)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{sc_id}/safety-confirm", response_model=SCResponse)
async def safety_confirm(
    sc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要特殊特性模块的 CREATE 权限")
    try:
        result = await sc_svc.safety_confirm(db, sc_id, scope.user.user_id)
        _check_factory_access(result, scope)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{sc_id}/safety-dismiss", response_model=SCResponse)
async def safety_dismiss(
    sc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要特殊特性模块的 CREATE 权限")
    try:
        result = await sc_svc.safety_dismiss(db, sc_id, scope.user.user_id)
        _check_factory_access(result, scope)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{sc_id}/safety-cancel", response_model=SCResponse)
async def safety_cancel(
    sc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if level_perm < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要特殊特性模块的 APPROVE 权限")
    try:
        result = await sc_svc.safety_cancel(db, sc_id, scope.user.user_id)
        _check_factory_access(result, scope)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/audit-logs/{log_id}/read")
async def mark_audit_log_read(
    log_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    try:
        log = await sc_svc.mark_audit_log_read(db, log_id, scope.user.user_id, scope.user.username or scope.user.display_name or "")
        return {"detail": "marked as read", "log_id": str(log.log_id)}
    except ValueError as e:
        raise HTTPException(400, str(e))