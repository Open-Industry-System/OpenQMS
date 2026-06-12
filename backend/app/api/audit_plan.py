import json
import uuid
from datetime import date
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.permissions import get_user_permission, PermissionLevel, Module
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import validate_factory_invariant, resolve_create_factory_id, check_factory_access
from app.models.audit_plan import AuditPlan
from app.models.audit import AuditLog
from app import schemas
from app.services import audit_service, customer_audit_service

router = APIRouter(prefix="/api/audit-plans", tags=["audit-plans"])

_TEMPLATES_PATH = Path(__file__).parent.parent / "data" / "checklist_templates.json"
CHECKLIST_TEMPLATES: list[dict] = json.loads(_TEMPLATES_PATH.read_text(encoding="utf-8"))


async def _check_factory_access(entity, scope: RequestScope, db: AsyncSession):
    """Raise 404 if entity's factory_id (or parent program's) is not in the user's accessible factories."""
    fid = getattr(entity, "factory_id", None)
    # AuditPlan doesn't have factory_id; derive from parent AuditProgram
    if fid is None and hasattr(entity, "program_id") and entity.program_id:
        program = await audit_service.get_audit_program(db, entity.program_id)
        if program and program.factory_id:
            fid = program.factory_id
    if fid is None:
        return
    if scope.effective_factory_id and fid != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="audit plan not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if fid not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="audit plan not found")


@router.get("/checklist-templates")
async def get_checklist_templates(
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 VIEW 权限")
    return CHECKLIST_TEMPLATES


@router.get("/customer-stats", response_model=schemas.audit.CustomerAuditStatsResponse)
async def get_customer_audit_stats(
    product_line_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 VIEW 权限")
    stats = await customer_audit_service.get_customer_audit_stats(
        db, product_line_code=product_line_code, factory_id=scope.effective_factory_id,
    )
    return schemas.audit.CustomerAuditStatsResponse(**stats)


@router.get("", response_model=schemas.audit.AuditPlanListResponse)
async def list_audit_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    program_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    audit_category: str | None = Query(None),
    customer_type: str | None = Query(None),
    audit_mode: str | None = Query(None),
    customer_name: str | None = Query(None),
    product_line_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 VIEW 权限")
    # Apply product line scope
    allowed_pls = None
    if scope.pl_scope.mode == "NONE":
        return schemas.audit.AuditPlanListResponse(items=[], total=0, page=page, page_size=page_size)
    elif scope.pl_scope.mode == "EXPLICIT":
        allowed_pls = scope.pl_scope.codes
    items, total = await audit_service.list_audit_plans(
        db, page, page_size, program_id, status, date_from, date_to,
        audit_category, customer_type, audit_mode, customer_name, product_line_code,
        factory_id=scope.effective_factory_id,
        allowed_product_line_codes=allowed_pls,
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
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    try:
        factory_id = await resolve_create_factory_id(db, scope, product_line_code=req.product_line_code)
        check_factory_access(factory_id, scope)
        if req.audit_category == "customer":
            plan = await customer_audit_service.create_customer_audit(
                db,
                audit_scope=req.audit_scope,
                audit_criteria=req.audit_criteria,
                planned_date=req.planned_date,
                customer_name=req.customer_name,
                customer_type=req.customer_type,
                audit_mode=req.audit_mode,
                lead_auditor=req.lead_auditor,
                team_members=req.team_members,
                checklist=req.checklist,
                product_line_code=req.product_line_code,
                user_id=scope.user.user_id,
                factory_id=factory_id,
            )
        else:
            plan = await audit_service.create_audit_plan(
                db,
                program_id=req.program_id,
                audit_scope=req.audit_scope,
                audit_criteria=req.audit_criteria,
                planned_date=req.planned_date,
                lead_auditor=req.lead_auditor,
                team_members=req.team_members,
                checklist=req.checklist,
                user_id=scope.user.user_id,
                product_line_code=req.product_line_code,
                factory_id=factory_id,
            )
        await validate_factory_invariant(plan, db)
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{audit_id}", response_model=schemas.audit.AuditPlanResponse)
async def get_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 VIEW 权限")
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    await _check_factory_access(plan, scope, db)
    return schemas.audit.AuditPlanResponse.model_validate(plan)


@router.put("/{audit_id}", response_model=schemas.audit.AuditPlanResponse)
async def update_audit_plan(
    audit_id: uuid.UUID,
    req: schemas.audit.AuditPlanUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    await _check_factory_access(plan, scope, db)
    try:
        if plan.audit_category == "customer":
            plan = await customer_audit_service.update_customer_audit(
                db,
                plan,
                user_id=scope.user.user_id,
                customer_name=req.customer_name,
                customer_type=req.customer_type,
                audit_mode=req.audit_mode,
                audit_scope=req.audit_scope,
                audit_criteria=req.audit_criteria,
                planned_date=req.planned_date,
                actual_date=req.actual_date,
                lead_auditor=req.lead_auditor,
                team_members=req.team_members,
                checklist=req.checklist,
                product_line_code=req.product_line_code,
            )
        else:
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
                user_id=scope.user.user_id,
                product_line_code=req.product_line_code,
            )
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{audit_id}")
async def delete_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    await _check_factory_access(plan, scope, db)
    try:
        await audit_service.delete_audit_plan(db, plan, scope.user.user_id)
        return {"message": "audit plan deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{audit_id}/start", response_model=schemas.audit.AuditPlanResponse)
async def start_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    await _check_factory_access(plan, scope, db)
    try:
        plan = await audit_service.start_audit_plan(db, plan, scope.user.user_id)
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{audit_id}/complete", response_model=schemas.audit.AuditPlanResponse)
async def complete_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    await _check_factory_access(plan, scope, db)
    try:
        if plan.audit_category == "customer":
            plan = await customer_audit_service.complete_customer_audit(db, plan, scope.user.user_id)
        else:
            plan = await audit_service.complete_audit_plan(db, plan, scope.user.user_id)
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{audit_id}/cancel", response_model=schemas.audit.AuditPlanResponse)
async def cancel_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    await _check_factory_access(plan, scope, db)
    try:
        plan = await audit_service.cancel_audit_plan(db, plan, scope.user.user_id)
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{audit_id}/customer-confirm", response_model=schemas.audit.AuditPlanResponse)
async def confirm_customer_audit(
    audit_id: uuid.UUID,
    req: schemas.audit.CustomerConfirmationRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    await _check_factory_access(plan, scope, db)
    if plan.audit_category != "customer":
        raise HTTPException(status_code=400, detail="not a customer audit")

    plan.customer_confirmation_doc = [
        a.model_dump() for a in req.attachments
    ] if req.attachments else []

    audit_log = AuditLog(
        table_name="audit_plans",
        record_id=audit_id,
        action="CUSTOMER_CONFIRM",
        changed_fields={"customer_confirmation_date": req.confirmation_date.isoformat()},
        operated_by=scope.user.user_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(plan)
    return schemas.audit.AuditPlanResponse.model_validate(plan)


@router.get("/{audit_id}/findings", response_model=schemas.audit.AuditFindingListResponse)
async def get_plan_findings(
    audit_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 VIEW 权限")
    items, total = await audit_service.list_audit_findings(
        db, page, page_size, audit_id=audit_id,
        factory_id=scope.effective_factory_id,
    )
    return schemas.audit.AuditFindingListResponse(
        items=[schemas.audit.AuditFindingResponse.model_validate(f) for f in items],
        total=total,
        page=page,
        page_size=page_size,
    )