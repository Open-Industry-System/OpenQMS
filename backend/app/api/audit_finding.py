import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.permissions import get_user_permission, PermissionLevel, Module
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import populate_factory_id, validate_factory_invariant
from app.models.audit_finding import AuditFinding
from app import schemas
from app.services import audit_service, customer_audit_service

router = APIRouter(prefix="/api/audit-findings", tags=["audit-findings"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="audit finding not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="audit finding not found")


@router.get("", response_model=schemas.audit.AuditFindingListResponse)
async def list_audit_findings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    audit_id: uuid.UUID | None = Query(None),
    finding_type: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 VIEW 权限")
    items, total = await audit_service.list_audit_findings(
        db, page, page_size, audit_id, finding_type, status,
        factory_id=scope.effective_factory_id,
    )
    return schemas.audit.AuditFindingListResponse(
        items=[schemas.audit.AuditFindingResponse.model_validate(f) for f in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=schemas.audit.AuditFindingResponse)
async def create_audit_finding(
    req: schemas.audit.AuditFindingCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    try:
        finding = await audit_service.create_audit_finding(
            db,
            audit_id=req.audit_id,
            clause_ref=req.clause_ref,
            finding_type=req.finding_type,
            description=req.description,
            root_cause=req.root_cause,
            correction=req.correction,
            corrective_action=req.corrective_action,
            due_date=req.due_date,
            user_id=scope.user.user_id,
        )
        await populate_factory_id(finding, AuditFinding, db, scope=scope)
        await validate_factory_invariant(finding, db)
        await db.commit()
        return schemas.audit.AuditFindingResponse.model_validate(finding)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{finding_id}", response_model=schemas.audit.AuditFindingResponse)
async def get_audit_finding(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 VIEW 权限")
    finding = await audit_service.get_audit_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="audit finding not found")
    _check_factory_access(finding, scope)
    return schemas.audit.AuditFindingResponse.model_validate(finding)


@router.put("/{finding_id}", response_model=schemas.audit.AuditFindingResponse)
async def update_audit_finding(
    finding_id: uuid.UUID,
    req: schemas.audit.AuditFindingUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    finding = await audit_service.get_audit_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="audit finding not found")
    _check_factory_access(finding, scope)
    try:
        finding = await audit_service.update_audit_finding(
            db,
            finding=finding,
            clause_ref=req.clause_ref,
            finding_type=req.finding_type,
            description=req.description,
            root_cause=req.root_cause,
            correction=req.correction,
            corrective_action=req.corrective_action,
            due_date=req.due_date,
            user_id=scope.user.user_id,
        )
        return schemas.audit.AuditFindingResponse.model_validate(finding)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{finding_id}/transition", response_model=schemas.audit.AuditFindingResponse)
async def transition_audit_finding(
    finding_id: uuid.UUID,
    req: schemas.audit.FindingTransitionRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    finding = await audit_service.get_audit_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="audit finding not found")
    _check_factory_access(finding, scope)
    try:
        finding = await customer_audit_service.transition_finding(
            db,
            finding,
            action=req.action,
            user_id=scope.user.user_id,
            customer_confirmed=req.customer_confirmed,
            customer_confirmation_date=req.customer_confirmation_date,
            customer_confirmation_attachments=req.customer_confirmation_attachments,
        )
        return schemas.audit.AuditFindingResponse.model_validate(finding)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{finding_id}/customer-confirm", response_model=schemas.audit.AuditFindingResponse)
async def confirm_customer_finding(
    finding_id: uuid.UUID,
    req: schemas.audit.CustomerConfirmationRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    finding = await audit_service.get_audit_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="audit finding not found")
    _check_factory_access(finding, scope)
    try:
        finding = await customer_audit_service.customer_confirm_finding(
            db,
            finding,
            confirmation_date=req.confirmation_date,
            attachments=[a.model_dump() for a in req.attachments] if req.attachments else [],
            user_id=scope.user.user_id,
        )
        return schemas.audit.AuditFindingResponse.model_validate(finding)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{finding_id}/close", response_model=schemas.audit.AuditFindingResponse)
async def close_audit_finding(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    finding = await audit_service.get_audit_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="audit finding not found")
    _check_factory_access(finding, scope)
    try:
        plan = await audit_service.get_audit_plan(db, finding.audit_id)
        if plan and plan.audit_category == "customer":
            finding = await customer_audit_service.transition_finding(
                db, finding, action="close", user_id=scope.user.user_id
            )
        else:
            finding = await audit_service.close_audit_finding(db, finding, scope.user.user_id)
        return schemas.audit.AuditFindingResponse.model_validate(finding)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{finding_id}/create-capa")
async def create_capa_from_finding(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    finding = await audit_service.get_audit_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="audit finding not found")
    _check_factory_access(finding, scope)
    try:
        capa = await audit_service.create_capa_from_finding(db, finding, scope.user.user_id)
        return {
            "message": "CAPA created",
            "capa_id": str(capa.report_id),
            "document_no": capa.document_no,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))