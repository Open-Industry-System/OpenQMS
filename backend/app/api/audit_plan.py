import json
import uuid
from datetime import date
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User
from app import schemas
from app.services import audit_service

router = APIRouter(prefix="/api/audit-plans", tags=["audit-plans"])

_TEMPLATES_PATH = Path(__file__).parent.parent / "data" / "checklist_templates.json"
CHECKLIST_TEMPLATES: list[dict] = json.loads(_TEMPLATES_PATH.read_text(encoding="utf-8"))


@router.get("", response_model=schemas.audit.AuditPlanListResponse)
async def list_audit_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    program_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await audit_service.list_audit_plans(
        db, page, page_size, program_id, status, date_from, date_to
    )
    return schemas.audit.AuditPlanListResponse(
        items=[schemas.audit.AuditPlanResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=schemas.audit.AuditPlanResponse)
async def create_audit_plan(
    req: schemas.audit.AuditPlanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        plan = await audit_service.create_audit_plan(
            db,
            program_id=req.program_id,
            audit_scope=req.audit_scope,
            audit_criteria=req.audit_criteria,
            planned_date=req.planned_date,
            lead_auditor=req.lead_auditor,
            team_members=req.team_members,
            checklist=req.checklist,
            user_id=user.user_id,
        )
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{audit_id}", response_model=schemas.audit.AuditPlanResponse)
async def get_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    return schemas.audit.AuditPlanResponse.model_validate(plan)


@router.put("/{audit_id}", response_model=schemas.audit.AuditPlanResponse)
async def update_audit_plan(
    audit_id: uuid.UUID,
    req: schemas.audit.AuditPlanUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        plan = await audit_service.update_audit_plan(
            db,
            plan=plan,
            audit_scope=req.audit_scope,
            audit_criteria=req.audit_criteria,
            planned_date=req.planned_date,
            actual_date=req.actual_date,
            lead_auditor=req.lead_auditor,
            team_members=req.team_members,
            checklist=req.checklist,
            status=req.status,
            user_id=user.user_id,
        )
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{audit_id}")
async def delete_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        await audit_service.delete_audit_plan(db, plan, user.user_id)
        return {"message": "audit plan deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{audit_id}/start", response_model=schemas.audit.AuditPlanResponse)
async def start_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        plan = await audit_service.start_audit_plan(db, plan, user.user_id)
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{audit_id}/complete", response_model=schemas.audit.AuditPlanResponse)
async def complete_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        plan = await audit_service.complete_audit_plan(db, plan, user.user_id)
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{audit_id}/cancel", response_model=schemas.audit.AuditPlanResponse)
async def cancel_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        plan = await audit_service.cancel_audit_plan(db, plan, user.user_id)
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{audit_id}/findings", response_model=schemas.audit.AuditFindingListResponse)
async def get_plan_findings(
    audit_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await audit_service.list_audit_findings(
        db, page, page_size, audit_id=audit_id
    )
    return schemas.audit.AuditFindingListResponse(
        items=[schemas.audit.AuditFindingResponse.model_validate(f) for f in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/checklist-templates")
async def get_checklist_templates(
    _user: User = Depends(get_current_user),
):
    return CHECKLIST_TEMPLATES
