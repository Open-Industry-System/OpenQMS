import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import RequestScope, get_request_scope
from app.core.permissions import get_user_permission, PermissionLevel, Module
from app.core.factory_scope import validate_factory_invariant, resolve_create_factory_id, check_factory_access
from app import schemas
from app.services import quality_goal_service

router = APIRouter(prefix="/api/quality-goals", tags=["quality-goals"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="quality goal not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="quality goal not found")


@router.get("", response_model=schemas.quality_goal.QualityGoalListResponse)
async def list_quality_goals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    level: int | None = Query(None),
    product_line_code: str | None = Query(None, alias="product_line"),
    status: str | None = Query(None),
    period: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.QUALITY_GOAL, db)
    if level_perm < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要质量目标模块的 VIEW 权限")
    # Product line scope filtering
    if scope.pl_scope.mode == "NONE":
        return schemas.quality_goal.QualityGoalListResponse(
            items=[], total=0, page=page, page_size=page_size,
        )
    allowed_pls = scope.pl_scope.codes if scope.pl_scope.mode == "EXPLICIT" else None
    items, total = await quality_goal_service.list_quality_goals(
        db, page, page_size, level, product_line_code, status, period,
        factory_id=scope.effective_factory_id, allowed_product_lines=allowed_pls,
    )
    return schemas.quality_goal.QualityGoalListResponse(
        items=[schemas.quality_goal.QualityGoalResponse.model_validate(g) for g in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=schemas.quality_goal.QualityGoalResponse)
async def create_quality_goal(
    req: schemas.quality_goal.QualityGoalCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.QUALITY_GOAL, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要质量目标模块的 CREATE 权限")
    try:
        factory_id = await resolve_create_factory_id(db, scope, product_line_code=req.product_line_code)
        check_factory_access(factory_id, scope)
        goal = await quality_goal_service.create_quality_goal(
            db,
            parent_id=req.parent_id,
            level=req.level,
            product_line=req.product_line_code,
            name=req.name,
            target_value=req.target_value,
            unit=req.unit,
            period=req.period,
            owner_id=req.owner_id,
            description=req.description,
            user_id=scope.user.user_id,
            factory_id=factory_id,
        )
        await validate_factory_invariant(goal, db)
        await db.refresh(goal)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    stats = await quality_goal_service.get_quality_goal_stats(
        db, factory_id=scope.effective_factory_id,
    )
    return stats


@router.get("/{goal_id}", response_model=schemas.quality_goal.QualityGoalResponse)
async def get_quality_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    _check_factory_access(goal, scope)
    return schemas.quality_goal.QualityGoalResponse.model_validate(goal)


@router.put("/{goal_id}", response_model=schemas.quality_goal.QualityGoalResponse)
async def update_quality_goal(
    goal_id: uuid.UUID,
    req: schemas.quality_goal.QualityGoalUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.QUALITY_GOAL, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要质量目标模块的 CREATE 权限")
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    _check_factory_access(goal, scope)
    try:
        goal = await quality_goal_service.update_quality_goal(
            db,
            goal=goal,
            name=req.name,
            target_value=req.target_value,
            actual_value=req.actual_value,
            unit=req.unit,
            period=req.period,
            owner_id=req.owner_id,
            description=req.description,
            user_id=scope.user.user_id,
        )
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{goal_id}")
async def delete_quality_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.QUALITY_GOAL, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要质量目标模块的 CREATE 权限")
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    _check_factory_access(goal, scope)
    try:
        await quality_goal_service.delete_quality_goal(db, goal, scope.user.user_id)
        return {"message": "quality goal deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/submit", response_model=schemas.quality_goal.QualityGoalResponse)
async def submit_for_approval(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.QUALITY_GOAL, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要质量目标模块的 CREATE 权限")
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    _check_factory_access(goal, scope)
    try:
        goal = await quality_goal_service.submit_for_approval(db, goal, scope.user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/withdraw", response_model=schemas.quality_goal.QualityGoalResponse)
async def withdraw_submission(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.QUALITY_GOAL, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要质量目标模块的 CREATE 权限")
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    _check_factory_access(goal, scope)
    try:
        goal = await quality_goal_service.withdraw_submission(db, goal, scope.user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/approve", response_model=schemas.quality_goal.QualityGoalResponse)
async def approve_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.QUALITY_GOAL, db)
    if level_perm < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要质量目标模块的 APPROVE 权限")
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    _check_factory_access(goal, scope)
    try:
        goal = await quality_goal_service.approve_goal(db, goal, scope.user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/reject", response_model=schemas.quality_goal.QualityGoalResponse)
async def reject_goal(
    goal_id: uuid.UUID,
    req: schemas.quality_goal.QualityGoalRejectRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.QUALITY_GOAL, db)
    if level_perm < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要质量目标模块的 APPROVE 权限")
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    _check_factory_access(goal, scope)
    try:
        goal = await quality_goal_service.reject_goal(db, goal, req.reject_reason, scope.user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/archive", response_model=schemas.quality_goal.QualityGoalResponse)
async def archive_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.QUALITY_GOAL, db)
    if level_perm < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要质量目标模块的 APPROVE 权限")
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    _check_factory_access(goal, scope)
    try:
        goal = await quality_goal_service.archive_goal(db, goal, scope.user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/actual-value", response_model=schemas.quality_goal.QualityGoalResponse)
async def update_actual_value(
    goal_id: uuid.UUID,
    req: schemas.quality_goal.QualityGoalUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level_perm = await get_user_permission(scope.user, Module.QUALITY_GOAL, db)
    if level_perm < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要质量目标模块的 CREATE 权限")
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    _check_factory_access(goal, scope)
    if req.actual_value is None:
        raise HTTPException(status_code=400, detail="actual_value is required")
    try:
        goal = await quality_goal_service.update_actual_value(db, goal, req.actual_value, scope.user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))