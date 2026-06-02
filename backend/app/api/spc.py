from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import get_current_user, require_permission, PermissionLevel, Module
from app.models.user import User
from app.models.spc import SampleValue, SPCAlarm
from app import schemas
from app.schemas.spc import ControlLimitSnapshotOut
from app.services import spc_service
from sqlalchemy import select as sa_select

router = APIRouter(prefix="/api/spc", tags=["SPC"])


# ============ Inspection Characteristics ============

@router.post("/inspection-characteristics", response_model=schemas.spc.InspectionCharacteristicOut)
async def create_ic(
    data: schemas.spc.InspectionCharacteristicCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.SPC, PermissionLevel.CREATE)),
):
    try:
        ic = await spc_service.create_inspection_characteristic(db, user.user_id, data.model_dump())
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
    _user: User = Depends(get_current_user),
):
    items, total = await spc_service.list_inspection_characteristics(
        db, page=page, page_size=page_size, product_line=product_line, process_name=process_name
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
    _user: User = Depends(get_current_user),
):
    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="Inspection characteristic not found")
    return ic


@router.put("/inspection-characteristics/{ic_id}", response_model=schemas.spc.InspectionCharacteristicOut)
async def update_ic(
    ic_id: UUID,
    data: schemas.spc.InspectionCharacteristicUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.SPC, PermissionLevel.CREATE)),
):
    try:
        ic = await spc_service.update_inspection_characteristic(
            db, user.user_id, ic_id, data.model_dump(exclude_unset=True)
        )
        return ic
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/inspection-characteristics/{ic_id}")
async def delete_ic(
    ic_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.SPC, PermissionLevel.CREATE)),
):
    try:
        await spc_service.delete_inspection_characteristic(db, user.user_id, ic_id)
        return {"message": "Deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/inspection-characteristics/{ic_id}/lock-limits")
async def lock_limits(
    ic_id: UUID,
    locked: bool = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.SPC, PermissionLevel.CREATE)),
):
    try:
        ic = await spc_service.lock_unlock_control_limits(db, user.user_id, ic_id, locked)
        return ic
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ Samples ============

@router.post("/inspection-characteristics/{ic_id}/samples", response_model=schemas.spc.SampleBatchOut)
async def add_samples(
    ic_id: UUID,
    data: schemas.spc.SampleBatchCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.SPC, PermissionLevel.CREATE)),
):
    try:
        batch = await spc_service.add_sample_batch(db, user.user_id, ic_id, data.model_dump())
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
    user: User = Depends(require_permission(Module.SPC, PermissionLevel.CREATE)),
):
    from app.utils.excel import parse_upload, ExcelParseError, ImportError as ExcelImportError, MAX_UPLOAD_BYTES
    from dataclasses import asdict
    from fastapi.responses import JSONResponse

    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="inspection characteristic not found")

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

    result = await spc_service.bulk_import_samples(db, ic, rows, user.user_id)
    if result.errors:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [asdict(e) for e in result.errors]})
    return {"imported_count": result.imported_count, "errors": []}


@router.get("/inspection-characteristics/{ic_id}/samples/import-template")
async def download_sample_import_template(
    ic_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    from app.utils.excel import create_template, excel_response

    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="inspection characteristic not found")

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
    _user: User = Depends(get_current_user),
):
    try:
        return await spc_service.get_chart_data(db, ic_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/inspection-characteristics/{ic_id}/capability", response_model=schemas.spc.CapabilityResponse)
async def get_capability(
    ic_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
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
    _user: User = Depends(get_current_user),
):
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
    user: User = Depends(require_permission(Module.SPC, PermissionLevel.CREATE)),
):
    try:
        alarm = await spc_service.acknowledge_alarm(db, user.user_id, alarm_id)
        return alarm
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/alarms/{alarm_id}/create-capa")
async def create_capa_from_alarm(
    alarm_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.SPC, PermissionLevel.CREATE)),
):
    try:
        capa = await spc_service.create_capa_from_alarm(db, user.user_id, alarm_id)
        return {"capa_id": capa.report_id, "document_number": capa.document_no}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ FMEA Match Recommendations ============

@router.get("/alarms/{alarm_id}/fmea-recommendations", response_model=schemas.spc.FMEAMatchResponse)
async def get_fmea_recommendations(
    alarm_id: UUID,
    force: bool = Query(False, description="强制重新匹配，忽略缓存"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取 SPC 告警的 FMEA 失效模式推荐。"""
    alarm = await db.get(SPCAlarm, alarm_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")

    ic = await spc_service.get_inspection_characteristic(db, alarm.ic_id)
    if not ic:
        raise HTTPException(status_code=400, detail="Inspection characteristic not found")

    if alarm.fmea_recommendations and not force:
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
    user: User = Depends(require_permission(Module.SPC, PermissionLevel.EDIT)),
):
    """用户确认 FMEA 关联。"""
    alarm = await db.get(SPCAlarm, alarm_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")

    alarm.confirmed_fmea_id = req.fmea_id
    alarm.confirmed_fmea_node_id = req.node_id

    await spc_service._add_audit_log_no_commit(
        db, user.user_id, "UPDATE", "spc_alarms", alarm_id,
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
    current_user=Depends(get_current_user),
):
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
    current_user=Depends(get_current_user),
):
    try:
        return await spc_service.activate_snapshot(db, current_user.user_id, ic_id, snapshot_id, change_reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============ External Ingestion ============

@router.post("/spc-data-ingestion")
async def ingest_data(
    request: Request,
    data: schemas.spc.ExternalDataIngestion,
    db: AsyncSession = Depends(get_db),
):
    api_key = request.headers.get("X-API-Key")
    # Simple API key validation (in production, use a proper key store)
    if not api_key or api_key != "spc-ingestion-key":
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        batch = await spc_service.ingest_external_data(db, data.model_dump())
        return {"batch_id": batch.batch_id, "message": "Data ingested successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
