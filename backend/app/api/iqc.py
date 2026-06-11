import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.permissions import get_current_user, require_permission, require_admin, PermissionLevel, Module
from app.models.user import User
from app import schemas
from app.services import iqc_material_service, iqc_template_service, iqc_inspection_service
from app.services.aql_engine import calculate_aql_plan
from app.services.iqc_aql_service import AqlService, RuleEngine, ProfileManager, RecommendationManager, AqlConfigManager, QualitySnapshotCalculator
from app.schemas.iqc_aql import (
    AqlProfileCreate, AqlProfileUpdate, AqlProfileResponse, AqlProfileListResponse,
    AqlRecommendationResponse, AqlRecommendationListResponse,
    AqlRecommendationApproveRequest, AqlRecommendationRejectRequest,
    AqlQualitySnapshotResponse, AqlQualitySnapshotTrendResponse,
    AqlConfigResponse, AqlConfigUpdate,
    AqlTriggerRequest, AqlPreviewRequest, AqlPreviewResponse,
)
from app.models.iqc_aql_profile import IqcAqlProfile
from app.models.iqc_aql_recommendation import IqcAqlRecommendation
from app.models.iqc_aql_quality_snapshot import IqcAqlQualitySnapshot
from app.models.iqc_aql_config import IqcAqlConfig

router = APIRouter(prefix="/api/iqc", tags=["iqc"])


# ─── Material routes ───

@router.get("/materials", response_model=schemas.iqc.IqcMaterialListResponse)
async def list_materials(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    search: str | None = Query(None),
    product_line_code: str | None = Query(None),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    items, total = await iqc_material_service.list_materials(
        db, page, page_size, search, product_line_code
    )
    return schemas.iqc.IqcMaterialListResponse(
        items=[schemas.iqc.IqcMaterialResponse.model_validate(m) for m in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/materials", response_model=schemas.iqc.IqcMaterialResponse)
async def create_material(
    req: schemas.iqc.IqcMaterialCreate,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        material = await iqc_material_service.create_material(
            db,
            part_no=req.part_no,
            part_name=req.part_name,
            part_spec=req.part_spec,
            material_type=req.material_type,
            default_aql=req.default_aql,
            default_inspection_level=req.default_inspection_level,
            unit=req.unit,
            product_line_code=req.product_line_code,
            user_id=user.user_id,
        )
        return schemas.iqc.IqcMaterialResponse.model_validate(material)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/materials/import")
async def import_materials(
    file: UploadFile = File(...),
    product_line_code: str = Query("DC-DC-100"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    from app.utils.excel import parse_upload, ExcelParseError, ImportError as ExcelImportError, MAX_UPLOAD_BYTES
    from dataclasses import asdict
    from fastapi.responses import JSONResponse

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 限制")

    header_mapping = {
        "物料号*": "part_no", "名称*": "part_name", "规格": "part_spec",
        "类型": "material_type", "默认AQL": "default_aql", "检验水平": "default_inspection_level",
        "单位": "unit", "产品线": "product_line_code",
    }
    try:
        rows = parse_upload(raw, header_mapping, required_headers=["物料号*", "名称*"])
    except ExcelParseError as e:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [{"row": 0, "field": "", "message": str(e)}]})

    result = await iqc_material_service.bulk_import_materials(db, rows, product_line_code, user.user_id)
    if result.errors:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [asdict(e) for e in result.errors]})
    return {"imported_count": result.imported_count, "errors": []}


@router.get("/materials/import-template")
async def download_material_import_template():
    from app.utils.excel import create_template, excel_response
    headers = ["物料号*", "名称*", "规格", "类型", "默认AQL", "检验水平", "单位", "产品线"]
    example = ["PN-001", "示例物料", "10x20mm", "raw", "0.65", "II", "pcs", "DC-DC-100"]
    template_bytes = create_template(headers, "物料导入模板", example)
    return excel_response(template_bytes, "iqc_material_import_template.xlsx")


@router.get("/materials/{material_id}", response_model=schemas.iqc.IqcMaterialResponse)
async def get_material(
    material_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    material = await iqc_material_service.get_material(db, material_id)
    if not material:
        raise HTTPException(404, "物料不存在")
    return schemas.iqc.IqcMaterialResponse.model_validate(material)


@router.put("/materials/{material_id}", response_model=schemas.iqc.IqcMaterialResponse)
async def update_material(
    material_id: uuid.UUID,
    req: schemas.iqc.IqcMaterialUpdate,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        material = await iqc_material_service.update_material(
            db, material_id, user.user_id,
            **req.model_dump(exclude_none=True),
        )
        return schemas.iqc.IqcMaterialResponse.model_validate(material)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/materials/{material_id}")
async def delete_material(
    material_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.ADMIN)),
):
    try:
        await iqc_material_service.delete_material(db, material_id, user.user_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─── Template routes ───

@router.get("/templates", response_model=schemas.iqc.IqcTemplateListResponse)
async def list_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    material_id: uuid.UUID | None = Query(None),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    items, total = await iqc_template_service.list_templates(db, page, page_size, material_id)
    return schemas.iqc.IqcTemplateListResponse(
        items=[schemas.iqc.IqcTemplateResponse.model_validate(t) for t in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/templates", response_model=schemas.iqc.IqcTemplateResponse)
async def create_template(
    req: schemas.iqc.IqcTemplateCreate,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        template = await iqc_template_service.create_template(
            db,
            template_name=req.template_name,
            material_id=req.material_id,
            items=[i.model_dump() for i in req.items],
            user_id=user.user_id,
        )
        return schemas.iqc.IqcTemplateResponse.model_validate(template)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/templates/{template_id}", response_model=schemas.iqc.IqcTemplateResponse)
async def get_template(
    template_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    template = await iqc_template_service.get_template(db, template_id)
    if not template:
        raise HTTPException(404, "模板不存在")
    return schemas.iqc.IqcTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=schemas.iqc.IqcTemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    req: schemas.iqc.IqcTemplateCreate,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        template = await iqc_template_service.update_template(
            db, template_id, req.template_name,
            items=[i.model_dump() for i in req.items],
            user_id=user.user_id,
        )
        return schemas.iqc.IqcTemplateResponse.model_validate(template)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.ADMIN)),
):
    try:
        await iqc_template_service.delete_template(db, template_id, user.user_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─── Inspection routes (list BEFORE /{id}) ───

@router.get("/inspections", response_model=schemas.iqc.IqcInspectionListResponse)
async def list_inspections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: str | None = Query(None),
    inspection_result: str | None = Query(None),
    supplier_id: uuid.UUID | None = Query(None),
    material_id: uuid.UUID | None = Query(None),
    keyword: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    product_line_code: str | None = Query(None),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    from datetime import date as date_type
    d_from = date_type.fromisoformat(date_from) if date_from else None
    d_to = date_type.fromisoformat(date_to) if date_to else None

    items, total = await iqc_inspection_service.list_inspections(
        db, page, page_size, status, inspection_result,
        supplier_id, material_id, keyword, d_from, d_to, product_line_code,
    )
    return schemas.iqc.IqcInspectionListResponse(
        items=[schemas.iqc.IqcInspectionResponse.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/inspections", response_model=schemas.iqc.IqcInspectionResponse)
async def create_inspection(
    req: schemas.iqc.IqcInspectionCreate,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        inspection = await iqc_inspection_service.create_inspection(
            db,
            supplier_id=req.supplier_id,
            inspection_mode=req.inspection_mode,
            material_id=req.material_id,
            template_id=req.template_id,
            part_no=req.part_no,
            part_name=req.part_name,
            lot_no=req.lot_no,
            lot_qty=req.lot_qty,
            aql_level=req.aql_level,
            inspection_level=req.inspection_level,
            inspection_date=req.inspection_date,
            product_line_code=req.product_line_code,
            user_id=user.user_id,
        )
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─── AQL calculate endpoint (before /{id}) ───

@router.post("/calculate-aql", response_model=schemas.iqc.AqlCalculateResponse)
async def calculate_aql(
    req: schemas.iqc.AqlCalculateRequest,
    _user=Depends(get_current_user),
):
    try:
        plan = calculate_aql_plan(req.lot_qty, req.aql_level, req.inspection_level)
        return schemas.iqc.AqlCalculateResponse(**plan)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─── Stats endpoint (before /{id}) ───

@router.get("/stats", response_model=schemas.iqc.IqcStatsResponse)
async def get_stats(
    product_line_code: str | None = Query(None),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    stats = await iqc_inspection_service.get_stats(db, product_line_code)
    return schemas.iqc.IqcStatsResponse(**stats)


# ─── Inspection detail routes ───

@router.get("/inspections/{inspection_id}", response_model=schemas.iqc.IqcInspectionResponse)
async def get_inspection(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    inspection = await iqc_inspection_service.get_inspection(db, inspection_id)
    if not inspection:
        raise HTTPException(404, "检验单不存在")
    return schemas.iqc.IqcInspectionResponse.model_validate(inspection)


@router.put("/inspections/{inspection_id}", response_model=schemas.iqc.IqcInspectionResponse)
async def update_inspection(
    inspection_id: uuid.UUID,
    req: schemas.iqc.IqcInspectionUpdate,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        inspection = await iqc_inspection_service.update_inspection(
            db, inspection_id, user.user_id,
            **req.model_dump(exclude_none=True),
        )
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/inspections/{inspection_id}")
async def delete_inspection(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.ADMIN)),
):
    try:
        await iqc_inspection_service.delete_inspection(db, inspection_id, user.user_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/start", response_model=schemas.iqc.IqcInspectionResponse)
async def start_inspection(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        inspection = await iqc_inspection_service.start_inspection(db, inspection_id, user.user_id)
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/inspections/{inspection_id}/items", response_model=schemas.iqc.IqcInspectionResponse)
async def update_items(
    inspection_id: uuid.UUID,
    req: schemas.iqc.IqcBatchItemUpdate,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        inspection = await iqc_inspection_service.update_items(
            db, inspection_id,
            [i.model_dump(exclude_none=True) for i in req.items],
            user.user_id,
        )
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/judge", response_model=schemas.iqc.IqcInspectionResponse)
async def judge_inspection(
    inspection_id: uuid.UUID,
    req: schemas.iqc.IqcInspectionJudge,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        inspection = await iqc_inspection_service.judge_inspection(
            db, inspection_id, req.inspection_result, req.defect_qty,
            req.defect_description, req.sample_qty, user.user_id,
            has_safety_defect=req.has_safety_defect,
            linked_customer_complaint_id=req.linked_customer_complaint_id,
        )
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/request-reinspect", response_model=schemas.iqc.IqcInspectionResponse)
async def request_reinspect(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        inspection = await iqc_inspection_service.request_reinspect(db, inspection_id, user.user_id)
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/concession", response_model=schemas.iqc.IqcInspectionResponse)
async def approve_concession(
    inspection_id: uuid.UUID,
    req: schemas.iqc.IqcInspectionConcession,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.APPROVE)),
):
    try:
        inspection = await iqc_inspection_service.approve_concession(
            db, inspection_id, req.reason, user.user_id,
        )
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/close", response_model=schemas.iqc.IqcInspectionResponse)
async def close_inspection(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.APPROVE)),
):
    try:
        inspection = await iqc_inspection_service.close_inspection(db, inspection_id, user.user_id)
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/trigger-scar", response_model=schemas.iqc.IqcInspectionResponse)
async def trigger_scar(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        inspection = await iqc_inspection_service.trigger_scar(db, inspection_id, user.user_id)
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─── AQL Profile routes ───

@router.get("/aql-profiles", response_model=AqlProfileListResponse)
async def list_aql_profiles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    state: str | None = Query(None),
    supplier_id: uuid.UUID | None = Query(None),
    product_line_code: str | None = Query(None),
    db=Depends(get_db),
    _user=Depends(require_permission(Module.IQC, PermissionLevel.VIEW)),
):
    from sqlalchemy import select, func
    q = select(IqcAqlProfile)
    count_q = select(func.count(IqcAqlProfile.profile_id))
    if state:
        q = q.where(IqcAqlProfile.state == state)
        count_q = count_q.where(IqcAqlProfile.state == state)
    if supplier_id:
        q = q.where(IqcAqlProfile.supplier_id == supplier_id)
        count_q = count_q.where(IqcAqlProfile.supplier_id == supplier_id)
    if product_line_code:
        q = q.where(IqcAqlProfile.product_line_code == product_line_code)
        count_q = count_q.where(IqcAqlProfile.product_line_code == product_line_code)
    total = (await db.execute(count_q)).scalar() or 0
    items = (await db.execute(
        q.order_by(IqcAqlProfile.updated_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return AqlProfileListResponse(
        items=[AqlProfileResponse.model_validate(p) for p in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/aql-profiles", response_model=AqlProfileResponse)
async def create_aql_profile(
    req: AqlProfileCreate,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        profile = await ProfileManager.get_or_create_profile(
            db, req.supplier_id, req.material_id, req.product_line_code, user.user_id,
        )
        return AqlProfileResponse.model_validate(profile)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/aql-profiles/{profile_id}", response_model=AqlProfileResponse)
async def get_aql_profile(
    profile_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(require_permission(Module.IQC, PermissionLevel.VIEW)),
):
    from sqlalchemy import select
    result = await db.execute(select(IqcAqlProfile).where(IqcAqlProfile.profile_id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "AQL档案不存在")
    return AqlProfileResponse.model_validate(profile)


@router.put("/aql-profiles/{profile_id}", response_model=AqlProfileResponse)
async def update_aql_profile(
    profile_id: uuid.UUID,
    req: AqlProfileUpdate,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    from sqlalchemy import select
    result = await db.execute(select(IqcAqlProfile).where(IqcAqlProfile.profile_id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "AQL档案不存在")
    changed = {}
    for key, val in req.model_dump(exclude_none=True).items():
        old = getattr(profile, key)
        if val != old:
            changed[key] = {"before": old, "after": val}
            setattr(profile, key, val)
    if changed:
        from app.models.audit import AuditLog
        db.add(AuditLog(
            table_name="iqc_aql_profiles",
            record_id=profile_id,
            action="UPDATE",
            changed_fields=changed,
            operated_by=user.user_id,
        ))
        await db.commit()
    return AqlProfileResponse.model_validate(profile)


@router.get("/aql-profiles/{profile_id}/history", response_model=AqlQualitySnapshotTrendResponse)
async def get_aql_profile_history(
    profile_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(require_permission(Module.IQC, PermissionLevel.VIEW)),
):
    from sqlalchemy import select
    # Get profile to find supplier_id/material_id
    result = await db.execute(select(IqcAqlProfile).where(IqcAqlProfile.profile_id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "AQL档案不存在")
    snapshots = (await db.execute(
        select(IqcAqlQualitySnapshot)
        .where(
            IqcAqlQualitySnapshot.supplier_id == profile.supplier_id,
            IqcAqlQualitySnapshot.material_id == profile.material_id,
        )
        .order_by(IqcAqlQualitySnapshot.snapshot_at.desc())
    )).scalars().all()
    return AqlQualitySnapshotTrendResponse(
        snapshots=[AqlQualitySnapshotResponse.model_validate(s) for s in snapshots],
    )


# ─── AQL Recommendation routes ───

@router.get("/aql-recommendations", response_model=AqlRecommendationListResponse)
async def list_aql_recommendations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: str | None = Query(None),
    direction: str | None = Query(None),
    supplier_id: uuid.UUID | None = Query(None),
    material_id: uuid.UUID | None = Query(None),
    db=Depends(get_db),
    _user=Depends(require_permission(Module.IQC, PermissionLevel.VIEW)),
):
    from sqlalchemy import select, func
    q = select(IqcAqlRecommendation)
    count_q = select(func.count(IqcAqlRecommendation.recommendation_id))
    if status:
        q = q.where(IqcAqlRecommendation.status == status)
        count_q = count_q.where(IqcAqlRecommendation.status == status)
    if direction:
        q = q.where(IqcAqlRecommendation.direction == direction)
        count_q = count_q.where(IqcAqlRecommendation.direction == direction)
    if supplier_id:
        q = q.where(IqcAqlRecommendation.supplier_id == supplier_id)
        count_q = count_q.where(IqcAqlRecommendation.supplier_id == supplier_id)
    if material_id:
        q = q.where(IqcAqlRecommendation.material_id == material_id)
        count_q = count_q.where(IqcAqlRecommendation.material_id == material_id)
    total = (await db.execute(count_q)).scalar() or 0
    items = (await db.execute(
        q.order_by(IqcAqlRecommendation.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return AqlRecommendationListResponse(
        items=[AqlRecommendationResponse.model_validate(r) for r in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/aql-recommendations/{recommendation_id}", response_model=AqlRecommendationResponse)
async def get_aql_recommendation(
    recommendation_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(require_permission(Module.IQC, PermissionLevel.VIEW)),
):
    from sqlalchemy import select
    result = await db.execute(
        select(IqcAqlRecommendation).where(IqcAqlRecommendation.recommendation_id == recommendation_id)
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "建议记录不存在")
    return AqlRecommendationResponse.model_validate(rec)


@router.post("/aql-recommendations/{recommendation_id}/engineer-approve", response_model=AqlRecommendationResponse)
async def engineer_approve_recommendation(
    recommendation_id: uuid.UUID,
    req: AqlRecommendationApproveRequest,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        rec = await RecommendationManager.approve(db, recommendation_id, user.user_id, is_engineer=True)
        await db.commit()
        return AqlRecommendationResponse.model_validate(rec)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/aql-recommendations/{recommendation_id}/engineer-reject", response_model=AqlRecommendationResponse)
async def engineer_reject_recommendation(
    recommendation_id: uuid.UUID,
    req: AqlRecommendationRejectRequest,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        rec = await RecommendationManager.reject(db, recommendation_id, user.user_id, reason=req.reason, is_engineer=True)
        await db.commit()
        return AqlRecommendationResponse.model_validate(rec)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/aql-recommendations/{recommendation_id}/forward", response_model=AqlRecommendationResponse)
async def forward_recommendation(
    recommendation_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        rec = await RecommendationManager.forward(db, recommendation_id, user.user_id)
        await db.commit()
        return AqlRecommendationResponse.model_validate(rec)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/aql-recommendations/{recommendation_id}/manager-approve", response_model=AqlRecommendationResponse)
async def manager_approve_recommendation(
    recommendation_id: uuid.UUID,
    req: AqlRecommendationApproveRequest,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.APPROVE)),
):
    try:
        rec = await RecommendationManager.approve(db, recommendation_id, user.user_id, is_engineer=False)
        await db.commit()
        return AqlRecommendationResponse.model_validate(rec)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/aql-recommendations/{recommendation_id}/manager-reject", response_model=AqlRecommendationResponse)
async def manager_reject_recommendation(
    recommendation_id: uuid.UUID,
    req: AqlRecommendationRejectRequest,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.APPROVE)),
):
    try:
        rec = await RecommendationManager.reject(db, recommendation_id, user.user_id, reason=req.reason, is_engineer=False)
        await db.commit()
        return AqlRecommendationResponse.model_validate(rec)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/aql-recommendations/{recommendation_id}/expired", response_model=AqlRecommendationResponse)
async def mark_recommendation_expired(
    recommendation_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        rec = await RecommendationManager.mark_expired(db, recommendation_id)
        await db.commit()
        return AqlRecommendationResponse.model_validate(rec)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/aql-recommendations/trigger", response_model=AqlRecommendationResponse | None)
async def trigger_aql_evaluation(
    req: AqlTriggerRequest,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        recommendation = await AqlService.on_inspection_judged(
            db, req.supplier_id, req.material_id,
        )
        await db.commit()
        if recommendation:
            return AqlRecommendationResponse.model_validate(recommendation)
        return None
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/aql-recommendations/preview", response_model=AqlPreviewResponse)
async def preview_aql_recommendation(
    req: AqlPreviewRequest,
    db=Depends(get_db),
    user=Depends(require_permission(Module.IQC, PermissionLevel.CREATE)),
):
    try:
        ctx = await QualitySnapshotCalculator.calculate(db, req.supplier_id, req.material_id)
        engine = RuleEngine()
        rule_result = engine.evaluate(ctx)
        profile = await ProfileManager.get_profile(db, req.supplier_id, req.material_id)
        from app.services.iqc_aql_service import get_aql_by_state
        base_aql = profile.base_aql if profile else 1.0
        current_aql = profile.current_aql if profile else 1.0
        min_aql = profile.min_aql if profile else None
        max_aql = profile.max_aql if profile else None
        recommended_aql = get_aql_by_state(
            base_aql, rule_result["target_state"], rule_result.get("aql_steps", 0),
            current_aql=current_aql, min_aql=min_aql, max_aql=max_aql,
        )
        return AqlPreviewResponse(
            target_state=rule_result["target_state"],
            recommended_aql=recommended_aql,
            direction=rule_result["direction"],
            trigger_rules=[{"rule_id": rule_result["rule_id"], "reason": rule_result["reason_cn"]}],
            evidence=rule_result,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─── AQL Quality Snapshot routes ───

@router.get("/aql-quality-snapshot/{supplier_id}/{material_id}", response_model=AqlQualitySnapshotResponse)
async def get_quality_snapshot(
    supplier_id: uuid.UUID,
    material_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(require_permission(Module.IQC, PermissionLevel.VIEW)),
):
    from sqlalchemy import select
    result = await db.execute(
        select(IqcAqlQualitySnapshot)
        .where(
            IqcAqlQualitySnapshot.supplier_id == supplier_id,
            IqcAqlQualitySnapshot.material_id == material_id,
        )
        .order_by(IqcAqlQualitySnapshot.snapshot_at.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(404, "质量快照不存在")
    return AqlQualitySnapshotResponse.model_validate(snapshot)


@router.get("/aql-quality-snapshot/{supplier_id}/{material_id}/trend", response_model=AqlQualitySnapshotTrendResponse)
async def get_quality_snapshot_trend(
    supplier_id: uuid.UUID,
    material_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(require_permission(Module.IQC, PermissionLevel.VIEW)),
):
    from sqlalchemy import select
    snapshots = (await db.execute(
        select(IqcAqlQualitySnapshot)
        .where(
            IqcAqlQualitySnapshot.supplier_id == supplier_id,
            IqcAqlQualitySnapshot.material_id == material_id,
        )
        .order_by(IqcAqlQualitySnapshot.snapshot_at.desc())
    )).scalars().all()
    return AqlQualitySnapshotTrendResponse(
        snapshots=[AqlQualitySnapshotResponse.model_validate(s) for s in snapshots],
    )


# ─── AQL Config routes ───

@router.get("/aql-config")
async def list_aql_configs(
    product_line_code: str | None = Query(None),
    db=Depends(get_db),
    _user=Depends(require_permission(Module.IQC, PermissionLevel.VIEW)),
):
    configs = await AqlConfigManager.list_all(db, product_line_code)
    return [AqlConfigResponse.model_validate(c) for c in configs]


@router.put("/aql-config/{config_key}", response_model=AqlConfigResponse)
async def update_aql_config(
    config_key: str,
    req: AqlConfigUpdate,
    product_line_code: str | None = Query(None),
    db=Depends(get_db),
    _user=Depends(require_admin),
):
    try:
        cfg = await AqlConfigManager.set(db, config_key, req.config_value, product_line_code)
        await db.commit()
        return AqlConfigResponse.model_validate(cfg)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/aql-config/reset")
async def reset_aql_configs(
    db=Depends(get_db),
    _user=Depends(require_admin),
):
    configs = await AqlConfigManager.reset_defaults(db)
    await db.commit()
    return [AqlConfigResponse.model_validate(c) for c in configs]
