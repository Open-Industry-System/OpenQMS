import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User
from app import schemas
from app.services import audit_service

router = APIRouter(prefix="/api/audit-findings", tags=["audit-findings"])


@router.get("", response_model=schemas.audit.AuditFindingListResponse)
async def list_audit_findings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    audit_id: uuid.UUID | None = Query(None),
    finding_type: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await audit_service.list_audit_findings(
        db, page, page_size, audit_id, finding_type, status
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
    user: User = Depends(require_engineer_or_admin),
):
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
            user_id=user.user_id,
        )
        return schemas.audit.AuditFindingResponse.model_validate(finding)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{finding_id}", response_model=schemas.audit.AuditFindingResponse)
async def get_audit_finding(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    finding = await audit_service.get_audit_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="audit finding not found")
    return schemas.audit.AuditFindingResponse.model_validate(finding)


@router.put("/{finding_id}", response_model=schemas.audit.AuditFindingResponse)
async def update_audit_finding(
    finding_id: uuid.UUID,
    req: schemas.audit.AuditFindingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    finding = await audit_service.get_audit_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="audit finding not found")
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
            status=req.status,
            due_date=req.due_date,
            user_id=user.user_id,
        )
        return schemas.audit.AuditFindingResponse.model_validate(finding)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{finding_id}/close", response_model=schemas.audit.AuditFindingResponse)
async def close_audit_finding(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    finding = await audit_service.get_audit_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="audit finding not found")
    try:
        finding = await audit_service.close_audit_finding(db, finding, user.user_id)
        return schemas.audit.AuditFindingResponse.model_validate(finding)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{finding_id}/create-capa")
async def create_capa_from_finding(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    finding = await audit_service.get_audit_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="audit finding not found")
    try:
        capa = await audit_service.create_capa_from_finding(db, finding, user.user_id)
        return {
            "message": "CAPA created",
            "capa_id": str(capa.report_id),
            "document_no": capa.document_no,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
