import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access, resolve_create_factory_id, validate_factory_invariant
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.database import get_db
from app.schemas import apqp as apqp_schemas
from app.services import apqp_service

router = APIRouter(prefix="/api/apqp-projects", tags=["apqp"])

PHASE_NAMES = {
    1: "策划与定义",
    2: "产品设计与开发",
    3: "过程设计与开发",
    4: "产品与过程确认",
    5: "量产启动与反馈",
}


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="APQP project not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="APQP project not found")


def _to_response(p) -> apqp_schemas.APQPProjectResponse:
    return apqp_schemas.APQPProjectResponse(
        project_id=p.project_id,
        project_code=p.project_code,
        project_name=p.project_name,
        product_name=p.product_name,
        product_line_code=p.product_line_code,
        customer_name=p.customer_name,
        description=p.description,
        target_sop_date=p.target_sop_date,
        team_members=p.team_members,
        current_phase=p.current_phase,
        phase_name=PHASE_NAMES.get(p.current_phase, ""),
        phase_status=p.phase_status,
        project_status=p.project_status,
        phase_1_completed_at=p.phase_1_completed_at,
        phase_2_completed_at=p.phase_2_completed_at,
        phase_3_completed_at=p.phase_3_completed_at,
        phase_4_completed_at=p.phase_4_completed_at,
        phase_5_completed_at=p.phase_5_completed_at,
        gate_approved_by=p.gate_approved_by,
        gate_approved_by_name=p.gate_approver.display_name if p.gate_approver else None,
        gate_approved_at=p.gate_approved_at,
        gate_comments=p.gate_comments,
        gate_history=p.gate_history,
        dfmea_id=p.dfmea_id,
        dfmea_document_no=p.dfmea.document_no if p.dfmea else None,
        pfmea_id=p.pfmea_id,
        pfmea_document_no=p.pfmea.document_no if p.pfmea else None,
        control_plan_id=p.control_plan_id,
        control_plan_document_no=p.control_plan.document_no if p.control_plan else None,
        ppap_submission_id=p.ppap_submission_id,
        ppap_submission_part_no=p.ppap_submission.part_no if p.ppap_submission else None,
        ppap_submission_part_name=p.ppap_submission.part_name if p.ppap_submission else None,
        created_by=p.created_by,
        created_by_name=p.creator.display_name if p.creator else "",
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("", response_model=apqp_schemas.APQPProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_status: str | None = Query(None),
    current_phase: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLANNING, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 planning 模块的 VIEW 权限")
    items, total = await apqp_service.list_projects(
        db, page, page_size, project_status, current_phase,
        factory_id=scope.effective_factory_id,
    )
    return apqp_schemas.APQPProjectListResponse(
        items=[_to_response(p) for p in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/stats", response_model=apqp_schemas.APQPProjectStatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLANNING, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 planning 模块的 VIEW 权限")
    return await apqp_service.get_stats(db, factory_id=scope.effective_factory_id)


@router.get("/{project_id}", response_model=apqp_schemas.APQPProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLANNING, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 planning 模块的 VIEW 权限")
    project = await apqp_service.get_project(db, project_id)
    if not project:
        raise HTTPException(404, "APQP project not found")
    _check_factory_access(project, scope)
    return _to_response(project)


@router.post("", response_model=apqp_schemas.APQPProjectResponse)
async def create_project(
    req: apqp_schemas.APQPProjectCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLANNING, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 planning 模块的 CREATE 权限")
    try:
        factory_id = await resolve_create_factory_id(db, scope, product_line_code=req.product_line_code)
        check_factory_access(factory_id, scope)
        project = await apqp_service.create_project(
            db,
            project_name=req.project_name,
            product_name=req.product_name,
            product_line_code=req.product_line_code,
            user_id=scope.user.user_id,
            customer_name=req.customer_name,
            description=req.description,
            target_sop_date=req.target_sop_date,
            team_members=req.team_members,
            dfmea_id=req.dfmea_id,
            pfmea_id=req.pfmea_id,
            control_plan_id=req.control_plan_id,
            ppap_submission_id=req.ppap_submission_id,
            factory_id=factory_id,
        )
        await validate_factory_invariant(project, db)
        return _to_response(project)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{project_id}", response_model=apqp_schemas.APQPProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    req: apqp_schemas.APQPProjectUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLANNING, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 planning 模块的 CREATE 权限")
    project = await apqp_service.get_project(db, project_id)
    if not project:
        raise HTTPException(404, "APQP project not found")
    _check_factory_access(project, scope)
    if project.project_status != "active":
        raise HTTPException(400, "只能编辑进行中的项目")
    try:
        update_data = req.model_dump(exclude_unset=True)
        project = await apqp_service.update_project(db, project, user_id=scope.user.user_id, **update_data)
        return _to_response(project)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{project_id}/transition", response_model=apqp_schemas.APQPProjectResponse)
async def transition_project(
    project_id: uuid.UUID,
    req: apqp_schemas.APQPGateTransitionRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Route-level permission check
    perm_level = await get_user_permission(scope.user, Module.PLANNING, db)
    if req.action in ("approve_gate", "reject_gate"):
        if perm_level < PermissionLevel.APPROVE:
            raise HTTPException(403, "需要经理或管理员权限")
    elif req.action in ("submit_gate",):
        if perm_level < PermissionLevel.CREATE:
            raise HTTPException(403, "需要工程师或更高权限")
    elif req.action == "cancel":
        if perm_level < PermissionLevel.ADMIN:
            raise HTTPException(403, "仅管理员可取消项目")

    project = await apqp_service.get_project(db, project_id)
    if not project:
        raise HTTPException(404, "APQP project not found")
    _check_factory_access(project, scope)
    try:
        project = await apqp_service.transition_project(
            db, project, req.action, scope.user.user_id, scope.user.display_name, req.comments,
        )
        return _to_response(project)
    except ValueError as e:
        raise HTTPException(400, str(e))