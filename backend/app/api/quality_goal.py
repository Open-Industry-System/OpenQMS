import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin, require_manager_or_admin
from app.models.user import User
from app import schemas
from app.services import quality_goal_service

router = APIRouter(prefix="/api/quality-goals", tags=["quality-goals"])


@router.get("", response_model=schemas.quality_goal.QualityGoalListResponse)
async def list_quality_goals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    level: int | None = Query(None),
    product_line: str | None = Query(None),
    status: str | None = Query(None),
    period: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await quality_goal_service.list_quality_goals(
        db, page, page_size, level, product_line, status, period
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
    user: User = Depends(require_engineer_or_admin),
):
    try:
        goal = await quality_goal_service.create_quality_goal(
            db,
            parent_id=req.parent_id,
            level=req.level,
            product_line=req.product_line,
            name=req.name,
            target_value=req.target_value,
            unit=req.unit,
            period=req.period,
            owner_id=req.owner_id,
            description=req.description,
            user_id=user.user_id,
        )
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{goal_id}", response_model=schemas.quality_goal.QualityGoalResponse)
async def get_quality_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    return schemas.quality_goal.QualityGoalResponse.model_validate(goal)


@router.put("/{goal_id}", response_model=schemas.quality_goal.QualityGoalResponse)
async def update_quality_goal(
    goal_id: uuid.UUID,
    req: schemas.quality_goal.QualityGoalUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
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
            user_id=user.user_id,
        )
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{goal_id}")
async def delete_quality_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        await quality_goal_service.delete_quality_goal(db, goal, user.user_id)
        return {"message": "quality goal deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/submit", response_model=schemas.quality_goal.QualityGoalResponse)
async def submit_for_approval(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        goal = await quality_goal_service.submit_for_approval(db, goal, user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/withdraw", response_model=schemas.quality_goal.QualityGoalResponse)
async def withdraw_submission(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        goal = await quality_goal_service.withdraw_submission(db, goal, user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/approve", response_model=schemas.quality_goal.QualityGoalResponse)
async def approve_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        goal = await quality_goal_service.approve_goal(db, goal, user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/reject", response_model=schemas.quality_goal.QualityGoalResponse)
async def reject_goal(
    goal_id: uuid.UUID,
    req: schemas.quality_goal.QualityGoalRejectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        goal = await quality_goal_service.reject_goal(db, goal, req.reject_reason, user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/archive", response_model=schemas.quality_goal.QualityGoalResponse)
async def archive_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        goal = await quality_goal_service.archive_goal(db, goal, user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/actual-value", response_model=schemas.quality_goal.QualityGoalResponse)
async def update_actual_value(
    goal_id: uuid.UUID,
    req: schemas.quality_goal.QualityGoalUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    if req.actual_value is None:
        raise HTTPException(status_code=400, detail="actual_value is required")
    try:
        goal = await quality_goal_service.update_actual_value(db, goal, req.actual_value, user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stats = await quality_goal_service.get_quality_goal_stats(db)
    return stats
