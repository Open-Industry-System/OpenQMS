import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access, resolve_create_factory_id, validate_factory_invariant
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.database import get_db
from app.schemas.fmea import (
    FMEACreate,
    FMEAListResponse,
    FMEAResponse,
    FMEAUpdate,
    TransitionRequest,
)
from app.schemas.lessons_learned import LessonsLearnedRequest, LessonsLearnedResponse
from app.services import fmea_service
from app.services.lessons_learned.service import LessonsLearnedService

router = APIRouter(prefix="/api/fmea", tags=["fmea"])


@router.get("", response_model=FMEAListResponse)
async def list_fmeas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: str | None = None,
    product_line: str | None = None,
    high_rpn: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 VIEW 权限")

    # Product line filtering
    allowed_pls = None
    if scope.pl_scope.mode == "NONE":
        return FMEAListResponse(items=[], total=0, page=page, page_size=page_size)
    elif scope.pl_scope.mode == "EXPLICIT":
        allowed_pls = scope.pl_scope.codes

    items, total = await fmea_service.list_fmeas(
        db, page, page_size, status, product_line,
        high_rpn=high_rpn,
        allowed_product_line_codes=allowed_pls,
        factory_id=scope.effective_factory_id,
    )
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
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 CREATE 权限")
    try:
        factory_id = await resolve_create_factory_id(db, scope, product_line_code=req.product_line_code)
        check_factory_access(factory_id, scope)
        fmea = await fmea_service.create_fmea(
            db, req.title, req.document_no, req.fmea_type,
            scope.user.user_id, req.product_line_code, factory_id=factory_id,
        )
        await validate_factory_invariant(fmea, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return FMEAResponse.model_validate(fmea)


@router.get("/{fmea_id}", response_model=FMEAResponse)
async def get_fmea(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 VIEW 权限")
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    # Factory access check
    if scope.effective_factory_id and fmea.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="FMEA not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if fmea.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="FMEA not found")
    return FMEAResponse.model_validate(fmea)


@router.put("/{fmea_id}", response_model=FMEAResponse)
async def update_fmea(
    fmea_id: uuid.UUID,
    req: FMEAUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 EDIT 权限")
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    # Factory access check
    if scope.effective_factory_id and fmea.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="FMEA not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if fmea.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="FMEA not found")
    graph_dict = req.graph_data.model_dump() if req.graph_data else None
    try:
        fmea = await fmea_service.update_fmea(
            db, fmea, req.title, graph_dict, scope.user.user_id, req.product_line_code,
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
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
) -> RequestScope:
    if req.target_status == "approved":
        level = await get_user_permission(scope.user, Module.FMEA, db)
        if level < PermissionLevel.APPROVE:
            raise HTTPException(status_code=403, detail="审批权限不足")
    return scope


@router.post("/{fmea_id}/transition", response_model=FMEAResponse)
async def transition_fmea(
    fmea_id: uuid.UUID,
    req: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(require_approve_permission),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    check_factory_access(fmea.factory_id, scope)
    try:
        fmea = await fmea_service.transition_fmea(db, fmea, req.target_status, scope.user.user_id)
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


@router.post("/{fmea_id}/recommend", response_model=RecommendResponse)
async def recommend(
    fmea_id: uuid.UUID,
    request: RecommendRequest,
    fastapi_request: Request,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    graph_repo: FMEAGraphRepository = Depends(get_graph_repository),
):
    # Permission check
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 EDIT 权限")

    # Rate limiting (unchanged)
    user_key = f"rec_user:{scope.user.user_id}"
    fmea_key = f"rec_fmea:{fmea_id}"
    if not _check_rate_limit(user_key, _RATE_LIMITS["per_user"]):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")
    if not _check_rate_limit(fmea_key, _RATE_LIMITS["per_fmea"]):
        raise HTTPException(status_code=429, detail="该文档请求过于频繁，请稍后重试")

    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    # Factory access check
    if scope.effective_factory_id and fmea.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="FMEA not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if fmea.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="FMEA not found")

    # 提前计算 effective_scope（短输入 early return 也需要正确值）
    requested_scope = getattr(request, "scope", "global")
    has_kg = await get_user_permission(scope.user, Module.KNOWLEDGE_GRAPH, db) >= PermissionLevel.VIEW
    effective_scope = "current_product_line" if (not has_kg and requested_scope == "global") else requested_scope

    if len(request.context.get("function_description", request.context.get("failure_mode", ""))) < 2:
        return RecommendResponse(
            suggestions=[], source="rule", cached=False,
            llm_available=False, graph_match_count=0,
            effective_scope=effective_scope,
        )

    llm = getattr(fastapi_request.app.state, "llm_provider", None)
    service = RecommendationService(db=db, llm_provider=llm, graph_repo=graph_repo)
    result = await service.recommend(fmea_id, request, scope.user)
    await db.commit()
    return result


@router.get("/{fmea_id}/graph")
async def get_fmea_graph(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 VIEW 权限")
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    # Factory access check
    if scope.effective_factory_id and fmea.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="FMEA not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if fmea.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="FMEA not found")
    return fmea.graph_data


@router.get("/{fmea_id}/severity-warnings")
async def severity_warnings(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 VIEW 权限")
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    # Factory access check
    if scope.effective_factory_id and fmea.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="FMEA not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if fmea.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="FMEA not found")
    from app.services.special_characteristic_service import check_severity_compliance
    return await check_severity_compliance(db, fmea_id)


@router.post("/{fmea_id}/lessons-learned", response_model=LessonsLearnedResponse)
async def get_fmea_lessons(
    fmea_id: uuid.UUID,
    request: Request,
    req: LessonsLearnedRequest | None = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """Get lessons learned recommendations for a newly created FMEA."""
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 VIEW 权限")
    from app.services.fmea_service import get_fmea
    fmea_doc = await get_fmea(db, fmea_id)
    if fmea_doc is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    # Factory access check
    if scope.effective_factory_id and fmea_doc.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="FMEA not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if fmea_doc.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="FMEA not found")

    embedding = getattr(request.app.state, "embedding_provider", None)
    service = LessonsLearnedService(db, embedding)
    result = await service.recommend(fmea_id, "fmea", req.problem_description if req else None, scope.user)
    await db.commit()
    return result