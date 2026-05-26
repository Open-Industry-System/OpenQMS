import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin, require_manager_or_admin, require_admin
from app.models.user import User
from app import schemas
from app.services import iqc_material_service, iqc_template_service, iqc_inspection_service
from app.services.aql_engine import calculate_aql_plan

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
    user=Depends(require_engineer_or_admin),
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
    user=Depends(require_engineer_or_admin),
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
    user=Depends(require_admin),
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
    user=Depends(require_engineer_or_admin),
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
    user=Depends(require_engineer_or_admin),
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
    user=Depends(require_admin),
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
    user=Depends(require_engineer_or_admin),
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
    user=Depends(require_engineer_or_admin),
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
    user=Depends(require_admin),
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
    user=Depends(require_engineer_or_admin),
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
    user=Depends(require_engineer_or_admin),
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
    user=Depends(require_engineer_or_admin),
):
    try:
        inspection = await iqc_inspection_service.judge_inspection(
            db, inspection_id, req.inspection_result, req.defect_qty,
            req.defect_description, req.sample_qty, user.user_id,
        )
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/request-reinspect", response_model=schemas.iqc.IqcInspectionResponse)
async def request_reinspect(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
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
    user=Depends(require_manager_or_admin),
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
    user=Depends(require_manager_or_admin),
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
    user=Depends(require_engineer_or_admin),
):
    try:
        inspection = await iqc_inspection_service.trigger_scar(db, inspection_id, user.user_id)
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))
