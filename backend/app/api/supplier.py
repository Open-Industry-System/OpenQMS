import uuid
from datetime import date as date_type
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access, resolve_create_factory_id, validate_factory_invariant
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.database import get_db
from app.services import supplier_quality_service, supplier_service
from app.utils.excel import excel_response

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="supplier not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="supplier not found")


def _resolve_allowed_pls(scope: RequestScope) -> list[str] | None:
    """Resolve allowed product line codes from scope. Returns None for ALL mode, empty list for NONE."""
    if scope.pl_scope.mode == "NONE":
        return []
    elif scope.pl_scope.mode == "EXPLICIT":
        return scope.pl_scope.codes
    return None  # ALL mode — no restriction


# Export MUST be before "/{supplier_id}"
@router.get("/export")
async def export_suppliers(
    status: str | None = Query(None),
    grade: str | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 VIEW 权限")
    allowed_pls = _resolve_allowed_pls(scope)
    excel_bytes = await supplier_service.export_suppliers_excel(
        db, status, grade, search,
        allowed_product_line_codes=allowed_pls,
        factory_id=scope.effective_factory_id,
    )
    return excel_response(excel_bytes, f"suppliers_{date_type.today().strftime('%Y%m%d')}.xlsx")


# Import MUST be before "/{supplier_id}"
@router.post("/import")
async def import_suppliers(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 CREATE 权限")
    from dataclasses import asdict

    from fastapi.responses import JSONResponse

    from app.utils.excel import MAX_UPLOAD_BYTES, ExcelParseError, parse_upload

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 限制")

    header_mapping = {
        "名称*": "name", "简称*": "short_name",
        "联系人": "contact_name", "电话": "contact_phone",
        "邮箱": "contact_email", "地址": "address",
        "供货范围": "product_scope",
    }
    try:
        rows = parse_upload(raw, header_mapping, required_headers=["名称*", "简称*"])
    except ExcelParseError as e:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [{"row": 0, "field": "", "message": str(e)}]})

    result = await supplier_service.bulk_import_suppliers(db, rows, scope.user.user_id)
    if result.errors:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [asdict(e) for e in result.errors]})
    return {"imported_count": result.imported_count, "errors": []}


# Import template MUST be before "/{supplier_id}"
@router.get("/import-template")
async def download_supplier_import_template():
    headers = ["名称*", "简称*", "联系人", "电话", "邮箱", "地址", "供货范围"]
    example = ["示例供应商", "示例", "张三", "13800138000", "test@example.com", "上海市", "电子元器件"]
    from app.utils.excel import create_template
    template_bytes = create_template(headers, "供应商导入模板", example)
    return excel_response(template_bytes, "supplier_import_template.xlsx")


# Stats MUST be before "/{supplier_id}" to avoid routing conflict
@router.get("/stats", response_model=schemas.supplier.SupplierStatsResponse)
async def get_stats(
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 VIEW 权限")
    stats = await supplier_service.get_supplier_stats(
        db,
        factory_id=scope.effective_factory_id,
        allowed_product_line_codes=_resolve_allowed_pls(scope),
    )
    return schemas.supplier.SupplierStatsResponse(**stats)


# Expiry alerts MUST be before "/{supplier_id}" to avoid routing conflict
@router.get("/expiry-alerts", response_model=list[schemas.supplier.SupplierExpiryAlertResponse])
async def get_expiry_alerts(
    days: int = Query(90, ge=1, le=365),
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 VIEW 权限")
    return await supplier_service.get_expiry_alerts(
        db, days,
        factory_id=scope.effective_factory_id,
        allowed_product_line_codes=_resolve_allowed_pls(scope),
    )


# ─── Quality Dashboard ───

@router.get("/quality/dashboard", response_model=schemas.supplier.QualityDashboardResponse)
async def get_quality_dashboard(
    start_date: date_type | None = Query(None),
    end_date: date_type | None = Query(None),
    product_line_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 VIEW 权限")
    return await supplier_quality_service.get_quality_dashboard(
        db, start_date, end_date, product_line_code,
        factory_id=scope.effective_factory_id,
    )


@router.get("/quality/supplier/{supplier_id}", response_model=schemas.supplier.SupplierQualityDetailResponse)
async def get_supplier_quality_detail(
    supplier_id: uuid.UUID,
    start_date: date_type | None = Query(None),
    end_date: date_type | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 VIEW 权限")
    return await supplier_quality_service.get_supplier_quality_detail(
        db, str(supplier_id), start_date, end_date,
        factory_id=scope.effective_factory_id,
    )


@router.get("/quality/compare", response_model=schemas.supplier.SupplierCompareResponse)
async def get_supplier_compare(
    supplier_ids: str = Query(..., description="Comma-separated supplier IDs"),
    start_date: date_type | None = Query(None),
    end_date: date_type | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 VIEW 权限")
    ids = supplier_ids.split(",")
    return await supplier_quality_service.get_supplier_compare(
        db, ids, start_date, end_date,
        factory_id=scope.effective_factory_id,
    )


@router.get("/quality/export")
async def export_quality_dashboard(
    start_date: date_type | None = Query(None),
    end_date: date_type | None = Query(None),
    product_line_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 VIEW 权限")
    excel_bytes = await supplier_quality_service.export_quality_dashboard_excel(
        db, start_date, end_date, product_line_code,
        factory_id=scope.effective_factory_id,
    )
    filename = f"supplier_quality_{date_type.today().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("", response_model=schemas.supplier.SupplierListResponse)
async def list_suppliers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: str | None = Query(None),
    grade: str | None = Query(None),
    search: str | None = Query(None),
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 VIEW 权限")

    allowed_pls = _resolve_allowed_pls(scope)
    if allowed_pls is not None and not allowed_pls:
        return schemas.supplier.SupplierListResponse(
            items=[], total=0, page=page, page_size=page_size,
        )

    items, total = await supplier_service.list_suppliers(
        db, page, page_size, status, grade, search,
        allowed_product_line_codes=allowed_pls,
        factory_id=scope.effective_factory_id,
    )
    return schemas.supplier.SupplierListResponse(
        items=[schemas.supplier.SupplierResponse.model_validate(s) for s in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", response_model=schemas.supplier.SupplierResponse)
async def create_supplier(
    req: schemas.supplier.SupplierCreate,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 CREATE 权限")
    try:
        factory_id = await resolve_create_factory_id(db, scope)
        check_factory_access(factory_id, scope)
        supplier = await supplier_service.create_supplier(
            db, name=req.name, short_name=req.short_name,
            contact_name=req.contact_name, contact_phone=req.contact_phone,
            contact_email=req.contact_email, address=req.address,
            product_scope=req.product_scope, user_id=scope.user.user_id,
            factory_id=factory_id,
        )
        await validate_factory_invariant(supplier, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.supplier.SupplierResponse.model_validate(supplier)


@router.get("/{supplier_id}/related")
async def get_supplier_related(
    supplier_id: uuid.UUID,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 VIEW 权限")
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    _check_factory_access(supplier, scope)
    return await supplier_service.get_supplier_related(db, supplier_id)


@router.get("/{supplier_id}", response_model=schemas.supplier.SupplierResponse)
async def get_supplier(
    supplier_id: uuid.UUID,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 VIEW 权限")
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    _check_factory_access(supplier, scope)
    return schemas.supplier.SupplierResponse.model_validate(supplier)


@router.put("/{supplier_id}", response_model=schemas.supplier.SupplierResponse)
async def update_supplier(
    supplier_id: uuid.UUID,
    req: schemas.supplier.SupplierUpdate,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 CREATE 权限")
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    _check_factory_access(supplier, scope)
    try:
        supplier = await supplier_service.update_supplier(
            db, supplier=supplier, name=req.name, short_name=req.short_name,
            contact_name=req.contact_name, contact_phone=req.contact_phone,
            contact_email=req.contact_email, address=req.address,
            product_scope=req.product_scope, audit_plan_id=req.audit_plan_id,
            user_id=scope.user.user_id,
        )
        return schemas.supplier.SupplierResponse.model_validate(supplier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{supplier_id}")
async def delete_supplier(
    supplier_id: uuid.UUID,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 CREATE 权限")
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    _check_factory_access(supplier, scope)
    try:
        await supplier_service.delete_supplier(db, supplier, scope.user.user_id)
        return {"message": "supplier deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── State transitions (all require manager/admin) ───

@router.post("/{supplier_id}/approve", response_model=schemas.supplier.SupplierResponse)
async def approve_supplier(
    supplier_id: uuid.UUID,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 APPROVE 权限")
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    _check_factory_access(supplier, scope)
    try:
        return schemas.supplier.SupplierResponse.model_validate(
            await supplier_service.transition_supplier(db, supplier, "approve", scope.user.user_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{supplier_id}/reject", response_model=schemas.supplier.SupplierResponse)
async def reject_supplier(
    supplier_id: uuid.UUID,
    reason: str = Query(...),
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 APPROVE 权限")
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    _check_factory_access(supplier, scope)
    try:
        return schemas.supplier.SupplierResponse.model_validate(
            await supplier_service.transition_supplier(db, supplier, "reject", scope.user.user_id, reason=reason)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{supplier_id}/confirm-approved", response_model=schemas.supplier.SupplierResponse)
async def confirm_approved(
    supplier_id: uuid.UUID,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 APPROVE 权限")
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    _check_factory_access(supplier, scope)
    try:
        return schemas.supplier.SupplierResponse.model_validate(
            await supplier_service.transition_supplier(db, supplier, "confirm_approved", scope.user.user_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{supplier_id}/suspend", response_model=schemas.supplier.SupplierResponse)
async def suspend_supplier(
    supplier_id: uuid.UUID,
    reason: str = Query(...),
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 APPROVE 权限")
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    _check_factory_access(supplier, scope)
    try:
        return schemas.supplier.SupplierResponse.model_validate(
            await supplier_service.transition_supplier(db, supplier, "suspend", scope.user.user_id, reason=reason)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{supplier_id}/reinstate", response_model=schemas.supplier.SupplierResponse)
async def reinstate_supplier(
    supplier_id: uuid.UUID,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 APPROVE 权限")
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    _check_factory_access(supplier, scope)
    try:
        return schemas.supplier.SupplierResponse.model_validate(
            await supplier_service.transition_supplier(db, supplier, "reinstate", scope.user.user_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Certifications ───

@router.get("/{supplier_id}/certifications", response_model=schemas.supplier.SupplierCertificationListResponse)
async def list_certifications(
    supplier_id: uuid.UUID,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 VIEW 权限")
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    _check_factory_access(supplier, scope)
    items = await supplier_service.list_certifications(db, supplier_id)
    return schemas.supplier.SupplierCertificationListResponse(
        items=[schemas.supplier.SupplierCertificationResponse.model_validate(c) for c in items]
    )


@router.post("/{supplier_id}/certifications", response_model=schemas.supplier.SupplierCertificationResponse)
async def create_certification(
    supplier_id: uuid.UUID,
    req: schemas.supplier.SupplierCertificationCreate,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 CREATE 权限")
    try:
        cert = await supplier_service.create_certification(
            db, supplier_id=supplier_id, cert_type=req.cert_type, cert_no=req.cert_no,
            issued_by=req.issued_by, issue_date=req.issue_date, expiry_date=req.expiry_date, user_id=scope.user.user_id,
        )
        return schemas.supplier.SupplierCertificationResponse.model_validate(cert)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{supplier_id}/certifications/{cert_id}", response_model=schemas.supplier.SupplierCertificationResponse)
async def update_certification(
    supplier_id: uuid.UUID,
    cert_id: uuid.UUID,
    req: schemas.supplier.SupplierCertificationUpdate,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 CREATE 权限")
    cert = await supplier_service.get_certification(db, cert_id)
    if cert is None or cert.supplier_id != supplier_id:
        raise HTTPException(status_code=404, detail="certification not found")
    try:
        cert = await supplier_service.update_certification(
            db, cert=cert, cert_type=req.cert_type, cert_no=req.cert_no,
            issued_by=req.issued_by, issue_date=req.issue_date, expiry_date=req.expiry_date, user_id=scope.user.user_id,
        )
        return schemas.supplier.SupplierCertificationResponse.model_validate(cert)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{supplier_id}/certifications/{cert_id}")
async def delete_certification(
    supplier_id: uuid.UUID,
    cert_id: uuid.UUID,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 CREATE 权限")
    cert = await supplier_service.get_certification(db, cert_id)
    if cert is None or cert.supplier_id != supplier_id:
        raise HTTPException(status_code=404, detail="certification not found")
    try:
        await supplier_service.delete_certification(db, cert, scope.user.user_id)
        return {"message": "certification deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Evaluations ───

@router.get("/{supplier_id}/evaluations", response_model=schemas.supplier.SupplierEvaluationListResponse)
async def list_evaluations(
    supplier_id: uuid.UUID,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 VIEW 权限")
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    _check_factory_access(supplier, scope)
    items = await supplier_service.list_evaluations(db, supplier_id)
    return schemas.supplier.SupplierEvaluationListResponse(
        items=[schemas.supplier.SupplierEvaluationResponse.model_validate(e) for e in items]
    )


@router.post("/{supplier_id}/evaluations", response_model=schemas.supplier.SupplierEvaluationResponse)
async def create_evaluation(
    supplier_id: uuid.UUID,
    req: schemas.supplier.SupplierEvaluationCreate,
    db=Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.SUPPLIER, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 supplier 模块的 CREATE 权限")
    try:
        evaluation = await supplier_service.create_evaluation(
            db, supplier_id=supplier_id, eval_period=req.eval_period, eval_type=req.eval_type,
            quality_score=req.quality_score, delivery_score=req.delivery_score, service_score=req.service_score,
            capa_count=req.capa_count or 0, finding_count=req.finding_count or 0,
            premium_freight_count=req.premium_freight_count or 0, customer_disruption_count=req.customer_disruption_count or 0,
            notes=req.notes, user_id=scope.user.user_id,
        )
        return schemas.supplier.SupplierEvaluationResponse.model_validate(evaluation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))