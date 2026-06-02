import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import get_current_user, require_permission, Module, PermissionLevel
from app.core.product_line_filter import get_user_product_line_codes, enforce_product_line_access
from app.models.user import User

from app.schemas.fmea import (
    FMEACreate, FMEAUpdate, FMEAResponse, FMEAListResponse, TransitionRequest,
)
from app.services import fmea_service

router = APIRouter(prefix="/api/fmea", tags=["fmea"])


@router.get("", response_model=FMEAListResponse)
async def list_fmeas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: str | None = None,
    product_line: str | None = None,
    high_rpn: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.VIEW)),
):
    allowed_pls = None
    if not user.role_definition.bypass_row_level_security:
        allowed_pls = await get_user_product_line_codes(user, db)
        if not allowed_pls:
            return FMEAListResponse(items=[], total=0, page=page, page_size=page_size)
    items, total = await fmea_service.list_fmeas(db, page, page_size, status, product_line, high_rpn=high_rpn, allowed_product_line_codes=allowed_pls)
    return FMEAListResponse(
        items=[FMEAResponse.model_validate(f) for f in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=FMEAResponse, status_code=201)
async def create_fmea(
    req: FMEACreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.CREATE)),
):
    try:
        await enforce_product_line_access(user, req.product_line_code, db)
        fmea = await fmea_service.create_fmea(db, req.title, req.document_no, req.fmea_type, user.user_id, req.product_line_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return FMEAResponse.model_validate(fmea)


@router.get("/{fmea_id}", response_model=FMEAResponse)
async def get_fmea(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.VIEW)),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)
    return FMEAResponse.model_validate(fmea)


@router.put("/{fmea_id}", response_model=FMEAResponse)
async def update_fmea(
    fmea_id: uuid.UUID,
    req: FMEAUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.EDIT)),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)
    if req.product_line_code is not None and req.product_line_code != fmea.product_line_code:
        await enforce_product_line_access(user, req.product_line_code, db)
    graph_dict = req.graph_data.model_dump() if req.graph_data else None
    try:
        fmea = await fmea_service.update_fmea(
            db, fmea, req.title, graph_dict, user.user_id, req.product_line_code,
            lock_version=req.lock_version,
            confirmed_latest_lock_version=req.confirmed_latest_lock_version,
        )
    except ValueError as e:
        error_msg = str(e)
        if error_msg == "lock_version_mismatch":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "Document has been modified by another user.",
                    "conflict": {
                        "saved_by": None,
                        "saved_at": None,
                        "latest_lock_version": fmea.lock_version,
                    },
                },
            )
        if error_msg == "lock_version_changed_again":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "Document was modified again while you were reviewing. Please refresh.",
                    "conflict": {
                        "saved_by": None,
                        "saved_at": None,
                        "latest_lock_version": fmea.lock_version,
                    },
                },
            )
        raise HTTPException(status_code=400, detail=error_msg)
    return FMEAResponse.model_validate(fmea)


async def require_approve_permission(
    req: TransitionRequest,
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.EDIT)),
    db: AsyncSession = Depends(get_db),
) -> User:
    if req.target_status == "approved":
        from app.core.permissions import get_user_permission
        level = await get_user_permission(user, Module.FMEA, db)
        if level < PermissionLevel.APPROVE:
            raise HTTPException(status_code=403, detail="审批权限不足")
    return user


@router.post("/{fmea_id}/transition", response_model=FMEAResponse)
async def transition_fmea(
    fmea_id: uuid.UUID,
    req: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_approve_permission),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)
    try:
        fmea = await fmea_service.transition_fmea(db, fmea, req.target_status, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return FMEAResponse.model_validate(fmea)


import time
from collections import defaultdict
from app.schemas.recommendation import RecommendRequest, RecommendResponse
from app.services.recommendation_service import RecommendationService

# Simple in-memory rate limiter
_rate_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMITS = {"per_user": (5, 1.0), "per_fmea": (20, 1.0)}


def _check_rate_limit(key: str, limit: tuple[int, float]) -> bool:
    """Returns True if allowed, False if rate limited."""
    now = time.time()
    window = limit[1]
    max_req = limit[0]
    entries = _rate_store[key]
    _rate_store[key] = [t for t in entries if now - t < window]
    if len(_rate_store[key]) >= max_req:
        return False
    _rate_store[key].append(now)
    return True


from app.graph.deps import get_graph_repository
from app.graph.repository import FMEAGraphRepository
from app.core.permissions import get_user_permission

@router.post("/{fmea_id}/recommend", response_model=RecommendResponse)
async def recommend(
    fmea_id: uuid.UUID,
    request: RecommendRequest,
    fastapi_request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.EDIT)),
    graph_repo: FMEAGraphRepository = Depends(get_graph_repository),
):
    # Rate limiting (unchanged)
    user_key = f"rec_user:{user.user_id}"
    fmea_key = f"rec_fmea:{fmea_id}"
    if not _check_rate_limit(user_key, _RATE_LIMITS["per_user"]):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")
    if not _check_rate_limit(fmea_key, _RATE_LIMITS["per_fmea"]):
        raise HTTPException(status_code=429, detail="该文档请求过于频繁，请稍后重试")

    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)

    # 提前计算 effective_scope（短输入 early return 也需要正确值）
    requested_scope = getattr(request, "scope", "global")
    has_kg = await get_user_permission(user, Module.KNOWLEDGE_GRAPH, db) >= PermissionLevel.VIEW
    effective_scope = "current_product_line" if (not has_kg and requested_scope == "global") else requested_scope

    if len(request.context.get("function_description", request.context.get("failure_mode", ""))) < 2:
        return RecommendResponse(
            suggestions=[], source="rule", cached=False,
            llm_available=False, graph_match_count=0,
            effective_scope=effective_scope,
        )

    llm = getattr(fastapi_request.app.state, "llm_provider", None)
    service = RecommendationService(db=db, llm_provider=llm, graph_repo=graph_repo)
    result = await service.recommend(fmea_id, request, user)
    await db.commit()
    return result


@router.get("/{fmea_id}/graph")
async def get_fmea_graph(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.VIEW)),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)
    return fmea.graph_data


@router.get("/{fmea_id}/severity-warnings")
async def severity_warnings(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.VIEW)),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)
    from app.services.special_characteristic_service import check_severity_compliance
    return await check_severity_compliance(db, fmea_id)
