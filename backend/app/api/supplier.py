import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin, require_manager_or_admin
from app.models.user import User
from app import schemas
from app.services import supplier_service

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


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


@router.get("", response_model=schemas.supplier.SupplierListResponse)
async def list_suppliers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
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
            notes=req.notes, user_id=user.user_id,
        )
        return schemas.supplier.SupplierEvaluationResponse.model_validate(evaluation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
