from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import get_user_permission, PermissionLevel, Module
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import validate_factory_invariant, resolve_create_factory_id, check_factory_access, apply_scope_filter
from app.models.user import User
from app.models.spc import SampleValue, SPCAlarm, InspectionCharacteristic
from app import schemas
from app.schemas.spc import ControlLimitSnapshotOut
from app.services import spc_service
from sqlalchemy import select as sa_select

router = APIRouter(prefix="/api/spc", tags=["SPC"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="Inspection characteristic not found")


# ============ Inspection Characteristics ============

@router.post("/inspection-characteristics", response_model=schemas.spc.InspectionCharacteristicOut)
async def create_ic(
    data: schemas.spc.InspectionCharacteristicCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 CREATE 权限")
    try:
        factory_id = await resolve_create_factory_id(db, scope, product_line_code=data.product_line if hasattr(data, 'product_line') else None)
        check_factory_access(factory_id, scope)
        ic = await spc_service.create_inspection_characteristic(db, scope.user.user_id, data.model_dump(), factory_id=factory_id)
        await validate_factory_invariant(ic, db)
        await db.refresh(ic)
        return ic
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/inspection-characteristics", response_model=schemas.spc.InspectionCharacteristicListResponse)
async def list_ics(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    product_line: Optional[str] = None,
    process_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 VIEW 权限")

    # Product line scope early return
    if scope.pl_scope.mode == "NONE":
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    items, total = await spc_service.list_inspection_characteristics(
        db, page=page, page_size=page_size, product_line=product_line, process_name=process_name,
        factory_id=scope.effective_factory_id,
        allowed_product_line_codes=scope.pl_scope.codes if scope.pl_scope.mode == "EXPLICIT" else None,
    )
    return {
        "items": [schemas.spc.InspectionCharacteristicOut.model_validate(ic) for ic in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/inspection-characteristics/{ic_id}", response_model=schemas.spc.InspectionCharacteristicOut)
async def get_ic(
    ic_id: UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 VIEW 权限")
    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    _check_factory_access(ic, scope)
    return ic


@router.put("/inspection-characteristics/{ic_id}", response_model=schemas.spc.InspectionCharacteristicOut)
async def update_ic(
    ic_id: UUID,
    data: schemas.spc.InspectionCharacteristicUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 CREATE 权限")
    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    _check_factory_access(ic, scope)
    try:
        ic = await spc_service.update_inspection_characteristic(
            db, scope.user.user_id, ic_id, data.model_dump(exclude_unset=True)
        )
        return ic
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/inspection-characteristics/{ic_id}")
async def delete_ic(
    ic_id: UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 CREATE 权限")
    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    _check_factory_access(ic, scope)
    try:
        await spc_service.delete_inspection_characteristic(db, scope.user.user_id, ic_id)
        return {"message": "Deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/inspection-characteristics/{ic_id}/lock-limits")
async def lock_limits(
    ic_id: UUID,
    locked: bool = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 CREATE 权限")
    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    _check_factory_access(ic, scope)
    try:
        ic = await spc_service.lock_unlock_control_limits(db, scope.user.user_id, ic_id, locked)
        return ic
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ Samples ============

@router.post("/inspection-characteristics/{ic_id}/samples", response_model=schemas.spc.SampleBatchOut)
async def add_samples(
    ic_id: UUID,
    data: schemas.spc.SampleBatchCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 CREATE 权限")
    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    _check_factory_access(ic, scope)
    try:
        batch = await spc_service.add_sample_batch(db, scope.user.user_id, ic_id, data.model_dump())
        # Eagerly load values for response
        result = await db.execute(
            sa_select(SampleValue).where(SampleValue.batch_id == batch.batch_id)
        )
        values = [float(v.value) for v in result.scalars().all()]
        return {
            "batch_id": batch.batch_id,
            "ic_id": batch.ic_id,
            "batch_no": batch.batch_no,
            "sampled_at": batch.sampled_at,
            "subgroup_size": batch.subgroup_size,
            "values": values,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/inspection-characteristics/{ic_id}/samples/import")
async def import_samples(
    ic_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    from app.utils.excel import parse_upload, ExcelParseError, ImportError as ExcelImportError, MAX_UPLOAD_BYTES
    from dataclasses import asdict
    from fastapi.responses import JSONResponse

    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 CREATE 权限")

    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="inspection characteristic not found")
    _check_factory_access(ic, scope)

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 限制")

    if ic.chart_type in ("p", "np", "c", "u"):
        header_mapping = {"批次号*": "batch_no", "采样时间*": "sampled_at", "检验数": "inspected_count", "缺陷数": "defect_count"}
    else:
        header_mapping = {"批次号*": "batch_no", "采样时间*": "sampled_at"}
        for i in range(1, ic.subgroup_size + 1):
            header_mapping[f"样本值{i}"] = f"value_{i}"

    try:
        rows = parse_upload(raw, header_mapping, required_headers=["批次号*", "采样时间*"])
    except ExcelParseError as e:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [{"row": 0, "field": "", "message": str(e)}]})

    result = await spc_service.bulk_import_samples(db, ic, rows, scope.user.user_id)
    if result.errors:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [asdict(e) for e in result.errors]})
    return {"imported_count": result.imported_count, "errors": []}


@router.get("/inspection-characteristics/{ic_id}/samples/import-template")
async def download_sample_import_template(
    ic_id: UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    from app.utils.excel import create_template, excel_response

    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 VIEW 权限")

    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    _check_factory_access(ic, scope)

    if ic.chart_type in ("p", "np", "c", "u"):
        headers = ["批次号*", "采样时间*", "检验数", "缺陷数"]
        example = ["B001", "2026-05-28 10:00", "100", "3"]
    else:
        headers = ["批次号*", "采样时间*"] + [f"样本值{i}" for i in range(1, ic.subgroup_size + 1)]
        example = ["B001", "2026-05-28 10:00"] + ["10.5"] * ic.subgroup_size

    template_bytes = create_template(headers, "样本导入模板", example)
    filename = f"spc_samples_{ic.chart_type}_template.xlsx"
    return excel_response(template_bytes, filename)


@router.get("/inspection-characteristics/{ic_id}/chart-data")
async def get_chart_data(
    ic_id: UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 VIEW 权限")
    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    _check_factory_access(ic, scope)
    try:
        return await spc_service.get_chart_data(db, ic_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/inspection-characteristics/{ic_id}/capability", response_model=schemas.spc.CapabilityResponse)
async def get_capability(
    ic_id: UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 VIEW 权限")
    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    _check_factory_access(ic, scope)
    try:
        return await spc_service.calculate_capability(db, ic_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ Alarms ============

@router.get("/inspection-characteristics/{ic_id}/alarms", response_model=schemas.spc.SPCAlarmListResponse)
async def list_ic_alarms(
    ic_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 VIEW 权限")
    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    _check_factory_access(ic, scope)
    items, total = await spc_service.list_alarms(db, ic_id=ic_id, page=page, page_size=page_size)
    return {
        "items": [schemas.spc.SPCAlarmOut.model_validate(a) for a in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/alarms/{alarm_id}/acknowledge", response_model=schemas.spc.SPCAlarmOut)
async def acknowledge_alarm(
    alarm_id: UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 CREATE 权限")
    # Fetch alarm first to check factory access
    alarm = await db.get(SPCAlarm, alarm_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_factory_access(alarm, scope)
    try:
        alarm = await spc_service.acknowledge_alarm(db, scope.user.user_id, alarm_id)
        return alarm
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/alarms/{alarm_id}/create-capa")
async def create_capa_from_alarm(
    alarm_id: UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 CREATE 权限")
    # Fetch alarm first to check factory access
    alarm = await db.get(SPCAlarm, alarm_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_factory_access(alarm, scope)
    try:
        capa = await spc_service.create_capa_from_alarm(db, scope.user.user_id, alarm_id)
        return {"capa_id": capa.report_id, "document_number": capa.document_no}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ FMEA Match Recommendations ============

@router.get("/alarms/{alarm_id}/fmea-recommendations", response_model=schemas.spc.FMEAMatchResponse)
async def get_fmea_recommendations(
    alarm_id: UUID,
    force: bool = Query(False, description="强制重新匹配，忽略缓存"),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """获取 SPC 告警的 FMEA 失效模式推荐。"""
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 VIEW 权限")
    alarm = await db.get(SPCAlarm, alarm_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_factory_access(alarm, scope)

    ic = await spc_service.get_inspection_characteristic(db, alarm.ic_id)
    if not ic:
        raise HTTPException(status_code=400, detail="Inspection characteristic not found")

    if alarm.fmea_recommendations is not None and not force:
        recommendations = alarm.fmea_recommendations
    else:
        recommendations = await spc_service.match_fmea_for_alarm(db, alarm)

    return {
        "alarm_id": str(alarm_id),
        "ic_code": ic.ic_code,
        "process_name": ic.process_name,
        "characteristic_name": ic.characteristic_name,
        "recommendations": recommendations,
        "has_confirmed": bool(alarm.confirmed_fmea_node_id),
        "confirmed_fmea_id": str(alarm.confirmed_fmea_id) if alarm.confirmed_fmea_id else None,
        "confirmed_fmea_node_id": alarm.confirmed_fmea_node_id,
    }


@router.post("/alarms/{alarm_id}/confirm-fmea")
async def confirm_fmea_association(
    alarm_id: UUID,
    req: schemas.spc.ConfirmFMEARequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """用户确认 FMEA 关联。"""
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 EDIT 权限")
    alarm = await db.get(SPCAlarm, alarm_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    _check_factory_access(alarm, scope)

    # 验证 node_id 在 FMEA 文档中存在且为 FailureMode
    from sqlalchemy import select
    from app.models.fmea import FMEADocument
    fmea_result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == req.fmea_id))
    fmea = fmea_result.scalar_one_or_none()
    if not fmea or not fmea.graph_data:
        raise HTTPException(status_code=400, detail="FMEA document not found or has no graph data")
    node = next((n for n in fmea.graph_data.get("nodes", []) if n.get("id") == req.node_id), None)
    if not node or node.get("type") != "FailureMode":
        raise HTTPException(status_code=400, detail="Invalid FMEA node: must be a FailureMode")

    alarm.confirmed_fmea_id = req.fmea_id
    alarm.confirmed_fmea_node_id = req.node_id

    await spc_service._add_audit_log_no_commit(
        db, scope.user.user_id, "UPDATE", "spc_alarms", alarm_id,
        {
            "confirmed_fmea_id": str(req.fmea_id),
            "confirmed_fmea_node_id": req.node_id,
        }
    )
    await db.commit()
    return {"success": True}


# ============ Control Limit Snapshots ============

@router.get(
    "/inspection-characteristics/{ic_id}/snapshots",
    response_model=List[ControlLimitSnapshotOut],
)
async def get_snapshots(
    ic_id: UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 VIEW 权限")
    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    _check_factory_access(ic, scope)
    try:
        return await spc_service.list_snapshots(db, ic_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch(
    "/inspection-characteristics/{ic_id}/snapshots/{snapshot_id}/activate",
    response_model=ControlLimitSnapshotOut,
)
async def activate_snapshot(
    ic_id: UUID,
    snapshot_id: UUID,
    change_reason: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SPC, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 spc 模块的 CREATE 权限")
    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    _check_factory_access(ic, scope)
    try:
        return await spc_service.activate_snapshot(db, scope.user.user_id, ic_id, snapshot_id, change_reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============ External Ingestion ============

@router.post("/spc-data-ingestion")
async def ingest_data(
    request: Request,
    data: schemas.spc.ExternalDataIngestion,
    db: AsyncSession = Depends(get_db),
):
    # API key auth — NOT JWT, so no RequestScope here
    api_key = request.headers.get("X-API-Key")
    # Simple API key validation (in production, use a proper key store)
    if not api_key or api_key != "spc-ingestion-key":
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        batch = await spc_service.ingest_external_data(db, data.model_dump())
        return {"batch_id": batch.batch_id, "message": "Data ingested successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))