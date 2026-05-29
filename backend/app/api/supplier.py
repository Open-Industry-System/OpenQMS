import uuid
from datetime import date as date_type
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin, require_manager_or_admin
from app.models.user import User
from app import schemas
from app.services import supplier_service, supplier_quality_service
from app.utils.excel import excel_response

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


# Export MUST be before "/{supplier_id}"
@router.get("/export")
async def export_suppliers(
    status: str | None = Query(None),
    grade: str | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    excel_bytes = await supplier_service.export_suppliers_excel(db, status, grade, search)
    return excel_response(excel_bytes, f"suppliers_{date_type.today().strftime('%Y%m%d')}.xlsx")


# Import MUST be before "/{supplier_id}"
@router.post("/import")
async def import_suppliers(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    from app.utils.excel import parse_upload, ExcelParseError, ImportError as ExcelImportError
    from dataclasses import asdict
    from fastapi.responses import JSONResponse

    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
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

    result = await supplier_service.bulk_import_suppliers(db, rows, user.user_id)
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
async def get_stats(db=Depends(get_db), _user=Depends(get_current_user)):
    stats = await supplier_service.get_supplier_stats(db)
    return schemas.supplier.SupplierStatsResponse(**stats)


# Expiry alerts MUST be before "/{supplier_id}" to avoid routing conflict
@router.get("/expiry-alerts", response_model=list[schemas.supplier.SupplierExpiryAlertResponse])
async def get_expiry_alerts(
    days: int = Query(90, ge=1, le=365),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    return await supplier_service.get_expiry_alerts(db, days)


# ─── Quality Dashboard ───

@router.get("/quality/dashboard", response_model=schemas.supplier.QualityDashboardResponse)
async def get_quality_dashboard(
    start_date: date_type | None = Query(None),
    end_date: date_type | None = Query(None),
    product_line_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await supplier_quality_service.get_quality_dashboard(
        db, start_date, end_date, product_line_code
    )


@router.get("/quality/supplier/{supplier_id}", response_model=schemas.supplier.SupplierQualityDetailResponse)
async def get_supplier_quality_detail(
    supplier_id: uuid.UUID,
    start_date: date_type | None = Query(None),
    end_date: date_type | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await supplier_quality_service.get_supplier_quality_detail(
        db, str(supplier_id), start_date, end_date
    )


@router.get("/quality/compare", response_model=schemas.supplier.SupplierCompareResponse)
async def get_supplier_compare(
    supplier_ids: str = Query(..., description="Comma-separated supplier IDs"),
    start_date: date_type | None = Query(None),
    end_date: date_type | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    ids = supplier_ids.split(",")
    return await supplier_quality_service.get_supplier_compare(db, ids, start_date, end_date)


@router.get("/quality/export")
async def export_quality_dashboard(
    start_date: date_type | None = Query(None),
    end_date: date_type | None = Query(None),
    product_line_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    excel_bytes = await supplier_quality_service.export_quality_dashboard_excel(
        db, start_date, end_date, product_line_code
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
    _user=Depends(get_current_user),
):
    items, total = await supplier_service.list_suppliers(db, page, page_size, status, grade, search)
    return schemas.supplier.SupplierListResponse(
        items=[schemas.supplier.SupplierResponse.model_validate(s) for s in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", response_model=schemas.supplier.SupplierResponse)
async def create_supplier(
    req: schemas.supplier.SupplierCreate,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        supplier = await supplier_service.create_supplier(
            db, name=req.name, short_name=req.short_name,
            contact_name=req.contact_name, contact_phone=req.contact_phone,
            contact_email=req.contact_email, address=req.address,
            product_scope=req.product_scope, user_id=user.user_id,
        )
        return schemas.supplier.SupplierResponse.model_validate(supplier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{supplier_id}", response_model=schemas.supplier.SupplierResponse)
async def get_supplier(supplier_id: uuid.UUID, db=Depends(get_db), _user=Depends(get_current_user)):
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    return schemas.supplier.SupplierResponse.model_validate(supplier)


@router.put("/{supplier_id}", response_model=schemas.supplier.SupplierResponse)
async def update_supplier(
    supplier_id: uuid.UUID,
    req: schemas.supplier.SupplierUpdate,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    try:
        supplier = await supplier_service.update_supplier(
            db, supplier=supplier, name=req.name, short_name=req.short_name,
            contact_name=req.contact_name, contact_phone=req.contact_phone,
            contact_email=req.contact_email, address=req.address,
            product_scope=req.product_scope, audit_plan_id=req.audit_plan_id,
            user_id=user.user_id,
        )
        return schemas.supplier.SupplierResponse.model_validate(supplier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{supplier_id}")
async def delete_supplier(supplier_id: uuid.UUID, db=Depends(get_db), user=Depends(require_engineer_or_admin)):
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    try:
        await supplier_service.delete_supplier(db, supplier, user.user_id)
        return {"message": "supplier deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── State transitions (all require manager/admin) ───

@router.post("/{supplier_id}/approve", response_model=schemas.supplier.SupplierResponse)
async def approve_supplier(supplier_id: uuid.UUID, db=Depends(get_db), user=Depends(require_manager_or_admin)):
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    try:
        return schemas.supplier.SupplierResponse.model_validate(
            await supplier_service.transition_supplier(db, supplier, "approve", user.user_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{supplier_id}/reject", response_model=schemas.supplier.SupplierResponse)
async def reject_supplier(supplier_id: uuid.UUID, reason: str = Query(...), db=Depends(get_db), user=Depends(require_manager_or_admin)):
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    try:
        return schemas.supplier.SupplierResponse.model_validate(
            await supplier_service.transition_supplier(db, supplier, "reject", user.user_id, reason=reason)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{supplier_id}/confirm-approved", response_model=schemas.supplier.SupplierResponse)
async def confirm_approved(supplier_id: uuid.UUID, db=Depends(get_db), user=Depends(require_manager_or_admin)):
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    try:
        return schemas.supplier.SupplierResponse.model_validate(
            await supplier_service.transition_supplier(db, supplier, "confirm_approved", user.user_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{supplier_id}/suspend", response_model=schemas.supplier.SupplierResponse)
async def suspend_supplier(supplier_id: uuid.UUID, reason: str = Query(...), db=Depends(get_db), user=Depends(require_manager_or_admin)):
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    try:
        return schemas.supplier.SupplierResponse.model_validate(
            await supplier_service.transition_supplier(db, supplier, "suspend", user.user_id, reason=reason)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{supplier_id}/reinstate", response_model=schemas.supplier.SupplierResponse)
async def reinstate_supplier(supplier_id: uuid.UUID, db=Depends(get_db), user=Depends(require_manager_or_admin)):
    supplier = await supplier_service.get_supplier(db, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="supplier not found")
    try:
        return schemas.supplier.SupplierResponse.model_validate(
            await supplier_service.transition_supplier(db, supplier, "reinstate", user.user_id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Certifications ───

@router.get("/{supplier_id}/certifications", response_model=schemas.supplier.SupplierCertificationListResponse)
async def list_certifications(supplier_id: uuid.UUID, db=Depends(get_db), _user=Depends(get_current_user)):
    items = await supplier_service.list_certifications(db, supplier_id)
    return schemas.supplier.SupplierCertificationListResponse(
        items=[schemas.supplier.SupplierCertificationResponse.model_validate(c) for c in items]
    )


@router.post("/{supplier_id}/certifications", response_model=schemas.supplier.SupplierCertificationResponse)
async def create_certification(supplier_id: uuid.UUID, req: schemas.supplier.SupplierCertificationCreate, db=Depends(get_db), user=Depends(require_engineer_or_admin)):
    try:
        cert = await supplier_service.create_certification(
            db, supplier_id=supplier_id, cert_type=req.cert_type, cert_no=req.cert_no,
            issued_by=req.issued_by, issue_date=req.issue_date, expiry_date=req.expiry_date, user_id=user.user_id,
        )
        return schemas.supplier.SupplierCertificationResponse.model_validate(cert)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{supplier_id}/certifications/{cert_id}", response_model=schemas.supplier.SupplierCertificationResponse)
async def update_certification(supplier_id: uuid.UUID, cert_id: uuid.UUID, req: schemas.supplier.SupplierCertificationUpdate, db=Depends(get_db), user=Depends(require_engineer_or_admin)):
    cert = await supplier_service.get_certification(db, cert_id)
    if cert is None or cert.supplier_id != supplier_id:
        raise HTTPException(status_code=404, detail="certification not found")
    try:
        cert = await supplier_service.update_certification(
            db, cert=cert, cert_type=req.cert_type, cert_no=req.cert_no,
            issued_by=req.issued_by, issue_date=req.issue_date, expiry_date=req.expiry_date, user_id=user.user_id,
        )
        return schemas.supplier.SupplierCertificationResponse.model_validate(cert)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{supplier_id}/certifications/{cert_id}")
async def delete_certification(supplier_id: uuid.UUID, cert_id: uuid.UUID, db=Depends(get_db), user=Depends(require_engineer_or_admin)):
    cert = await supplier_service.get_certification(db, cert_id)
    if cert is None or cert.supplier_id != supplier_id:
        raise HTTPException(status_code=404, detail="certification not found")
    try:
        await supplier_service.delete_certification(db, cert, user.user_id)
        return {"message": "certification deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Evaluations ───

@router.get("/{supplier_id}/evaluations", response_model=schemas.supplier.SupplierEvaluationListResponse)
async def list_evaluations(supplier_id: uuid.UUID, db=Depends(get_db), _user=Depends(get_current_user)):
    items = await supplier_service.list_evaluations(db, supplier_id)
    return schemas.supplier.SupplierEvaluationListResponse(
        items=[schemas.supplier.SupplierEvaluationResponse.model_validate(e) for e in items]
    )


@router.post("/{supplier_id}/evaluations", response_model=schemas.supplier.SupplierEvaluationResponse)
async def create_evaluation(supplier_id: uuid.UUID, req: schemas.supplier.SupplierEvaluationCreate, db=Depends(get_db), user=Depends(require_engineer_or_admin)):
    try:
        evaluation = await supplier_service.create_evaluation(
            db, supplier_id=supplier_id, eval_period=req.eval_period, eval_type=req.eval_type,
            quality_score=req.quality_score, delivery_score=req.delivery_score, service_score=req.service_score,
            capa_count=req.capa_count or 0, finding_count=req.finding_count or 0,
            premium_freight_count=req.premium_freight_count or 0, customer_disruption_count=req.customer_disruption_count or 0,
            notes=req.notes, user_id=user.user_id,
        )
        return schemas.supplier.SupplierEvaluationResponse.model_validate(evaluation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
