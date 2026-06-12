import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.core.permissions import get_user_permission, Module, PermissionLevel
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import populate_factory_id, validate_factory_invariant
from app.database import get_db
from app.models.customer_quality import Customer, CustomerComplaint, RMARecord
from app.services import customer_quality_service

router = APIRouter(tags=["customer-quality"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="customer quality record not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="customer quality record not found")


def _resolve_allowed_pls(scope: RequestScope) -> list[str] | None:
    """Resolve allowed product line codes from scope. Returns None for ALL mode, empty list for NONE."""
    if scope.pl_scope.mode == "NONE":
        return []
    elif scope.pl_scope.mode == "EXPLICIT":
        return scope.pl_scope.codes
    return None  # ALL mode — no restriction


@router.get("/api/customers", response_model=schemas.customer_quality.CustomerListResponse)
async def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None),
    segment: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 VIEW 权限")
    items, total = await customer_quality_service.list_customers(
        db, page, page_size, q, segment,
        factory_id=scope.effective_factory_id,
    )
    return schemas.customer_quality.CustomerListResponse(
        items=[schemas.customer_quality.CustomerResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/api/customers", response_model=schemas.customer_quality.CustomerResponse, status_code=201)
async def create_customer(
    req: schemas.customer_quality.CustomerCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    try:
        customer = await customer_quality_service.create_customer(db, req, scope.user.user_id)
        await populate_factory_id(customer, Customer, db, scope=scope)
        await validate_factory_invariant(customer, db)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.CustomerResponse.model_validate(customer)


@router.get("/api/customers/{customer_id}", response_model=schemas.customer_quality.CustomerResponse)
async def get_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 VIEW 权限")
    customer = await customer_quality_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    _check_factory_access(customer, scope)
    return schemas.customer_quality.CustomerResponse.model_validate(customer)


@router.put("/api/customers/{customer_id}", response_model=schemas.customer_quality.CustomerResponse)
async def update_customer(
    customer_id: uuid.UUID,
    req: schemas.customer_quality.CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    customer = await customer_quality_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    _check_factory_access(customer, scope)
    try:
        customer = await customer_quality_service.update_customer(
            db, customer, req.model_dump(exclude_unset=True), scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.CustomerResponse.model_validate(customer)


@router.get(
    "/api/customers/{customer_id}/summary",
    response_model=schemas.customer_quality.CustomerSummaryResponse,
)
async def get_customer_summary(
    customer_id: uuid.UUID,
    product_line: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    shipment_qty: int | None = Query(None, ge=0),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 VIEW 权限")
    customer = await customer_quality_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    _check_factory_access(customer, scope)
    try:
        return await customer_quality_service.customer_summary(
            db, customer_id, product_line, date_from, date_to, shipment_qty
        )
    except ValueError as e:
        if str(e) == "customer not found":
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/api/customer-complaints",
    response_model=schemas.customer_quality.ComplaintListResponse,
)
async def list_complaints(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    product_line: str | None = Query(None),
    customer_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    severity: str | None = Query(None),
    overdue: bool | None = Query(None),
    assignee_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 VIEW 权限")

    allowed_pls = _resolve_allowed_pls(scope)
    if allowed_pls is not None and not allowed_pls:
        return schemas.customer_quality.ComplaintListResponse(
            items=[], total=0, page=page, page_size=page_size,
        )

    # If user passed product_line, intersect with allowed_pls
    effective_pl = product_line
    if allowed_pls is not None:
        if product_line and product_line not in allowed_pls:
            return schemas.customer_quality.ComplaintListResponse(
                items=[], total=0, page=page, page_size=page_size,
            )
        if not product_line:
            # Apply scope restriction — pass None to let service use allowed_pls
            pass

    items, total = await customer_quality_service.list_complaints(
        db, page, page_size, product_line, customer_id, status, severity, overdue, assignee_id,
        allowed_product_line_codes=allowed_pls,
        factory_id=scope.effective_factory_id,
    )
    return schemas.customer_quality.ComplaintListResponse(
        items=[schemas.customer_quality.ComplaintResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/api/customer-complaints",
    response_model=schemas.customer_quality.ComplaintResponse,
    status_code=201,
)
async def create_complaint(
    req: schemas.customer_quality.ComplaintCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    try:
        complaint = await customer_quality_service.create_complaint(db, req, scope.user.user_id)
        await populate_factory_id(complaint, CustomerComplaint, db, scope=scope)
        await validate_factory_invariant(complaint, db)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.ComplaintResponse.model_validate(complaint)


@router.get("/api/customer-complaints/by-supplier/{supplier_id}")
async def get_complaints_by_supplier(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 VIEW 权限")
    return await customer_quality_service.get_complaints_by_supplier(db, supplier_id)


@router.get(
    "/api/customer-complaints/{complaint_id}",
    response_model=schemas.customer_quality.ComplaintResponse,
)
async def get_complaint(
    complaint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 VIEW 权限")
    complaint = await customer_quality_service.get_complaint(db, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="complaint not found")
    _check_factory_access(complaint, scope)
    return schemas.customer_quality.ComplaintResponse.model_validate(complaint)


@router.put(
    "/api/customer-complaints/{complaint_id}",
    response_model=schemas.customer_quality.ComplaintResponse,
)
async def update_complaint(
    complaint_id: uuid.UUID,
    req: schemas.customer_quality.ComplaintUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    complaint = await customer_quality_service.get_complaint(db, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="complaint not found")
    _check_factory_access(complaint, scope)
    try:
        complaint = await customer_quality_service.update_complaint(
            db, complaint, req.model_dump(exclude_unset=True), scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.ComplaintResponse.model_validate(complaint)


async def _get_complaint_or_404(db: AsyncSession, complaint_id: uuid.UUID, scope: RequestScope):
    complaint = await customer_quality_service.get_complaint(db, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="complaint not found")
    _check_factory_access(complaint, scope)
    return complaint


@router.post(
    "/api/customer-complaints/{complaint_id}/start-investigation",
    response_model=schemas.customer_quality.ComplaintResponse,
)
async def start_complaint_investigation(
    complaint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    complaint = await _get_complaint_or_404(db, complaint_id, scope)
    try:
        complaint = await customer_quality_service.transition_complaint(
            db, complaint, "start_investigation", scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.ComplaintResponse.model_validate(complaint)


@router.post(
    "/api/customer-complaints/{complaint_id}/mark-responded",
    response_model=schemas.customer_quality.ComplaintResponse,
)
async def mark_complaint_responded(
    complaint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    complaint = await _get_complaint_or_404(db, complaint_id, scope)
    try:
        complaint = await customer_quality_service.transition_complaint(
            db, complaint, "mark_responded", scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.ComplaintResponse.model_validate(complaint)


@router.post(
    "/api/customer-complaints/{complaint_id}/cancel",
    response_model=schemas.customer_quality.ComplaintResponse,
)
async def cancel_complaint(
    complaint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    complaint = await _get_complaint_or_404(db, complaint_id, scope)
    try:
        complaint = await customer_quality_service.transition_complaint(
            db, complaint, "cancel", scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.ComplaintResponse.model_validate(complaint)


@router.post(
    "/api/customer-complaints/{complaint_id}/close",
    response_model=schemas.customer_quality.ComplaintResponse,
)
async def close_complaint(
    complaint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 APPROVE 权限")
    complaint = await _get_complaint_or_404(db, complaint_id, scope)
    try:
        complaint = await customer_quality_service.transition_complaint(
            db, complaint, "close", scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.ComplaintResponse.model_validate(complaint)


@router.post(
    "/api/customer-complaints/{complaint_id}/link-capa",
    response_model=schemas.customer_quality.ComplaintResponse,
)
async def link_complaint_capa(
    complaint_id: uuid.UUID,
    capa_ref_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    complaint = await _get_complaint_or_404(db, complaint_id, scope)
    try:
        complaint = await customer_quality_service.link_complaint_capa(
            db, complaint, capa_ref_id, scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.ComplaintResponse.model_validate(complaint)


@router.post(
    "/api/customer-complaints/{complaint_id}/create-capa",
    response_model=schemas.customer_quality.ComplaintResponse,
)
async def create_capa_from_complaint(
    complaint_id: uuid.UUID,
    document_no: str = Query(...),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    complaint = await _get_complaint_or_404(db, complaint_id, scope)
    try:
        await customer_quality_service.create_capa_from_complaint(
            db, complaint, document_no, scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    refreshed = await customer_quality_service.get_complaint(db, complaint_id)
    return schemas.customer_quality.ComplaintResponse.model_validate(refreshed)


@router.post(
    "/api/customer-complaints/{complaint_id}/link-fmea",
    response_model=schemas.customer_quality.ComplaintResponse,
)
async def link_complaint_fmea(
    complaint_id: uuid.UUID,
    fmea_ref_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    complaint = await _get_complaint_or_404(db, complaint_id, scope)
    try:
        complaint = await customer_quality_service.link_complaint_fmea(
            db, complaint, fmea_ref_id, scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.ComplaintResponse.model_validate(complaint)


@router.get("/api/rma-records", response_model=schemas.customer_quality.RMARecordListResponse)
async def list_rma_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    product_line: str | None = Query(None),
    customer_id: uuid.UUID | None = Query(None),
    complaint_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    responsibility: str | None = Query(None),
    assignee_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 VIEW 权限")

    allowed_pls = _resolve_allowed_pls(scope)
    if allowed_pls is not None and not allowed_pls:
        return schemas.customer_quality.RMARecordListResponse(
            items=[], total=0, page=page, page_size=page_size,
        )

    items, total = await customer_quality_service.list_rma_records(
        db, page, page_size, product_line, customer_id, complaint_id, status, responsibility, assignee_id,
        allowed_product_line_codes=allowed_pls,
        factory_id=scope.effective_factory_id,
    )
    return schemas.customer_quality.RMARecordListResponse(
        items=[schemas.customer_quality.RMARecordResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/api/rma-records",
    response_model=schemas.customer_quality.RMARecordResponse,
    status_code=201,
)
async def create_rma_record(
    req: schemas.customer_quality.RMARecordCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    try:
        rma = await customer_quality_service.create_rma_record(db, req, scope.user.user_id)
        await populate_factory_id(rma, RMARecord, db, scope=scope)
        await validate_factory_invariant(rma, db)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.RMARecordResponse.model_validate(rma)


@router.get(
    "/api/rma-records/{rma_id}",
    response_model=schemas.customer_quality.RMARecordResponse,
)
async def get_rma_record(
    rma_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 VIEW 权限")
    rma = await customer_quality_service.get_rma_record(db, rma_id)
    if rma is None:
        raise HTTPException(status_code=404, detail="RMA not found")
    _check_factory_access(rma, scope)
    return schemas.customer_quality.RMARecordResponse.model_validate(rma)


@router.put(
    "/api/rma-records/{rma_id}",
    response_model=schemas.customer_quality.RMARecordResponse,
)
async def update_rma_record(
    rma_id: uuid.UUID,
    req: schemas.customer_quality.RMARecordUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    rma = await customer_quality_service.get_rma_record(db, rma_id)
    if rma is None:
        raise HTTPException(status_code=404, detail="RMA not found")
    _check_factory_access(rma, scope)
    try:
        rma = await customer_quality_service.update_rma_record(
            db, rma, req.model_dump(exclude_unset=True), scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.RMARecordResponse.model_validate(rma)


async def _get_rma_or_404(db: AsyncSession, rma_id: uuid.UUID, scope: RequestScope):
    rma = await customer_quality_service.get_rma_record(db, rma_id)
    if rma is None:
        raise HTTPException(status_code=404, detail="RMA not found")
    _check_factory_access(rma, scope)
    return rma


@router.post(
    "/api/rma-records/{rma_id}/start-analysis",
    response_model=schemas.customer_quality.RMARecordResponse,
)
async def start_rma_analysis(
    rma_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    rma = await _get_rma_or_404(db, rma_id, scope)
    try:
        rma = await customer_quality_service.transition_rma(db, rma, "start_analysis", scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.RMARecordResponse.model_validate(rma)


@router.post(
    "/api/rma-records/{rma_id}/mark-action-pending",
    response_model=schemas.customer_quality.RMARecordResponse,
)
async def mark_rma_action_pending(
    rma_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    rma = await _get_rma_or_404(db, rma_id, scope)
    try:
        rma = await customer_quality_service.transition_rma(
            db, rma, "mark_action_pending", scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.RMARecordResponse.model_validate(rma)


@router.post(
    "/api/rma-records/{rma_id}/cancel",
    response_model=schemas.customer_quality.RMARecordResponse,
)
async def cancel_rma_record(
    rma_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    rma = await _get_rma_or_404(db, rma_id, scope)
    try:
        rma = await customer_quality_service.transition_rma(db, rma, "cancel", scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.RMARecordResponse.model_validate(rma)


@router.post(
    "/api/rma-records/{rma_id}/close",
    response_model=schemas.customer_quality.RMARecordResponse,
)
async def close_rma_record(
    rma_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 APPROVE 权限")
    rma = await _get_rma_or_404(db, rma_id, scope)
    try:
        rma = await customer_quality_service.transition_rma(db, rma, "close", scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.RMARecordResponse.model_validate(rma)


@router.post(
    "/api/rma-records/{rma_id}/link-complaint",
    response_model=schemas.customer_quality.RMARecordResponse,
)
async def link_rma_complaint(
    rma_id: uuid.UUID,
    complaint_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    rma = await _get_rma_or_404(db, rma_id, scope)
    try:
        rma = await customer_quality_service.link_rma_complaint(
            db, rma, complaint_id, scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.RMARecordResponse.model_validate(rma)


@router.post(
    "/api/rma-records/{rma_id}/link-capa",
    response_model=schemas.customer_quality.RMARecordResponse,
)
async def link_rma_capa(
    rma_id: uuid.UUID,
    capa_ref_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    rma = await _get_rma_or_404(db, rma_id, scope)
    try:
        rma = await customer_quality_service.link_rma_capa(db, rma, capa_ref_id, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.RMARecordResponse.model_validate(rma)


@router.post(
    "/api/rma-records/{rma_id}/link-fmea",
    response_model=schemas.customer_quality.RMARecordResponse,
)
async def link_rma_fmea(
    rma_id: uuid.UUID,
    fmea_ref_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    rma = await _get_rma_or_404(db, rma_id, scope)
    try:
        rma = await customer_quality_service.link_rma_fmea(db, rma, fmea_ref_id, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.customer_quality.RMARecordResponse.model_validate(rma)


@router.get(
    "/api/customer-quality/dashboard",
    response_model=schemas.customer_quality.CustomerQualityDashboardResponse,
)
async def get_customer_quality_dashboard(
    product_line: str | None = Query(None),
    customer_id: uuid.UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    shipment_qty: int | None = Query(None, ge=0),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 VIEW 权限")
    try:
        return await customer_quality_service.dashboard(
            db, product_line, customer_id, date_from, date_to, shipment_qty,
            factory_id=scope.effective_factory_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/api/customer-quality/customers/{customer_id}/trend",
    response_model=list[schemas.customer_quality.CustomerQualityTrendPoint],
)
async def get_customer_trend(
    customer_id: uuid.UUID,
    product_line: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    shipment_qty: int | None = Query(None, ge=0),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 VIEW 权限")
    customer = await customer_quality_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    _check_factory_access(customer, scope)
    try:
        data = await customer_quality_service.dashboard(
            db, product_line, customer_id, date_from, date_to, shipment_qty,
            factory_id=scope.effective_factory_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data["trend"]


# ─── SCAR creation from complaint / RMA ───

from app.schemas.customer_quality import SCARRelatedCreate


@router.post("/api/customer-complaints/{complaint_id}/create-scar")
async def create_scar_from_complaint_endpoint(
    complaint_id: uuid.UUID,
    req: SCARRelatedCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    complaint = await customer_quality_service.get_complaint(db, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="complaint not found")
    _check_factory_access(complaint, scope)
    try:
        scar = await customer_quality_service.create_scar_from_complaint(
            db, complaint_id, req.model_dump(), scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"scar_id": scar.scar_id, "scar_no": scar.scar_no}


@router.post("/api/rma-records/{rma_id}/create-scar")
async def create_scar_from_rma_endpoint(
    rma_id: uuid.UUID,
    req: SCARRelatedCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CUSTOMER_QUALITY, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 customer_quality 模块的 CREATE 权限")
    rma = await customer_quality_service.get_rma_record(db, rma_id)
    if rma is None:
        raise HTTPException(status_code=404, detail="RMA not found")
    _check_factory_access(rma, scope)
    try:
        scar = await customer_quality_service.create_scar_from_rma(
            db, rma_id, req.model_dump(), scope.user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"scar_id": scar.scar_id, "scar_no": scar.scar_no}