import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import validate_factory_invariant, resolve_create_factory_id, check_factory_access
from app.core.permissions import get_user_permission, PermissionLevel, Module
from app.models.gauge import Gauge
from app import schemas
from app.services import gauge_service

router = APIRouter(prefix="/api/gauges", tags=["gauges"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="Gauge not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="Gauge not found")


@router.get("/expiring", response_model=schemas.gauge.GaugeListResponse)
async def get_expiring_gauges(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.MSA, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 msa 模块的 VIEW 权限")

    items, total = await gauge_service.list_gauges(
        db, page=1, page_size=100, expiring_days=days,
        factory_id=scope.effective_factory_id,
    )
    return schemas.gauge.GaugeListResponse(
        items=[schemas.gauge.GaugeResponse.model_validate(g) for g in items],
        total=total,
        page=1,
        page_size=100,
    )


@router.get("", response_model=schemas.gauge.GaugeListResponse)
async def list_gauges(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    department: str | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.MSA, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 msa 模块的 VIEW 权限")

    items, total = await gauge_service.list_gauges(
        db, page, page_size, status, department, search,
        factory_id=scope.effective_factory_id,
    )
    return schemas.gauge.GaugeListResponse(
        items=[schemas.gauge.GaugeResponse.model_validate(g) for g in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=schemas.gauge.GaugeResponse)
async def create_gauge(
    req: schemas.gauge.GaugeCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.MSA, db)
    if perm_level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 msa 模块的 CREATE 权限")

    try:
        factory_id = await resolve_create_factory_id(db, scope)
        check_factory_access(factory_id, scope)
        gauge = await gauge_service.create_gauge(
            db,
            gauge_no=req.gauge_no,
            name=req.name,
            model=req.model,
            manufacturer=req.manufacturer,
            resolution=req.resolution,
            measuring_range=req.measuring_range,
            department=req.department,
            location=req.location,
            calibration_cycle_days=req.calibration_cycle_days,
            next_calibration_date=req.next_calibration_date,
            user_id=scope.user.user_id,
            factory_id=factory_id,
        )
        await validate_factory_invariant(gauge, db)
        await db.refresh(gauge)
        return schemas.gauge.GaugeResponse.model_validate(gauge)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{gauge_id}", response_model=schemas.gauge.GaugeResponse)
async def get_gauge(
    gauge_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.MSA, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 msa 模块的 VIEW 权限")

    gauge = await gauge_service.get_gauge(db, gauge_id)
    if gauge is None:
        raise HTTPException(status_code=404, detail="gauge not found")
    _check_factory_access(gauge, scope)
    return schemas.gauge.GaugeResponse.model_validate(gauge)


@router.put("/{gauge_id}", response_model=schemas.gauge.GaugeResponse)
async def update_gauge(
    gauge_id: uuid.UUID,
    req: schemas.gauge.GaugeUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.MSA, db)
    if perm_level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 msa 模块的 CREATE 权限")

    gauge = await gauge_service.get_gauge(db, gauge_id)
    if gauge is None:
        raise HTTPException(status_code=404, detail="gauge not found")
    _check_factory_access(gauge, scope)
    try:
        gauge = await gauge_service.update_gauge(
            db,
            gauge,
            scope.user.user_id,
            gauge_no=req.gauge_no,
            name=req.name,
            model=req.model,
            manufacturer=req.manufacturer,
            resolution=req.resolution,
            measuring_range=req.measuring_range,
            department=req.department,
            location=req.location,
            status=req.status,
            calibration_cycle_days=req.calibration_cycle_days,
            next_calibration_date=req.next_calibration_date,
        )
        return schemas.gauge.GaugeResponse.model_validate(gauge)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{gauge_id}")
async def delete_gauge(
    gauge_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.MSA, db)
    if perm_level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 msa 模块的 CREATE 权限")

    gauge = await gauge_service.get_gauge(db, gauge_id)
    if gauge is None:
        raise HTTPException(status_code=404, detail="gauge not found")
    _check_factory_access(gauge, scope)
    try:
        await gauge_service.delete_gauge(db, gauge, scope.user.user_id)
        return {"message": "gauge deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{gauge_id}/calibrations",
    response_model=schemas.gauge.GaugeCalibrationListResponse,
)
async def list_calibrations(
    gauge_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.MSA, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 msa 模块的 VIEW 权限")

    gauge = await gauge_service.get_gauge(db, gauge_id)
    if gauge is None:
        raise HTTPException(status_code=404, detail="gauge not found")
    _check_factory_access(gauge, scope)
    items = await gauge_service.list_calibrations(db, gauge_id)
    return schemas.gauge.GaugeCalibrationListResponse(
        items=[
            schemas.gauge.GaugeCalibrationResponse.model_validate(c)
            for c in items
        ]
    )


@router.post(
    "/{gauge_id}/calibrations",
    response_model=schemas.gauge.GaugeCalibrationResponse,
)
async def create_calibration(
    gauge_id: uuid.UUID,
    req: schemas.gauge.GaugeCalibrationCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.MSA, db)
    if perm_level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 msa 模块的 CREATE 权限")

    gauge = await gauge_service.get_gauge(db, gauge_id)
    if gauge is None:
        raise HTTPException(status_code=404, detail="gauge not found")
    _check_factory_access(gauge, scope)
    try:
        cal = await gauge_service.create_calibration(
            db,
            gauge_id=gauge_id,
            calibration_date=req.calibration_date,
            result=req.result,
            certificate_no=req.certificate_no,
            calibrated_by=req.calibrated_by,
            notes=req.notes,
            next_calibration_date=req.next_calibration_date,
            user_id=scope.user.user_id,
        )
        return schemas.gauge.GaugeCalibrationResponse.model_validate(cal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))