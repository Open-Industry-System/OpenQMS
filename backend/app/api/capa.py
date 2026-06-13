import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline, RecommendationContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import get_user_permission, Module, PermissionLevel
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import validate_factory_invariant, resolve_create_factory_id, check_factory_access
from typing import Any
from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument

from app.config import settings
from app.schemas.capa import CAPACreate, CAPAUpdate, CAPAResponse, CAPAListResponse, AdvanceRequest, D4RecommendationResponse, D5RecommendationResponse
from app.schemas.capa_draft import DraftRequest, DraftResponse
from app.schemas.lessons_learned import LessonsLearnedRequest, LessonsLearnedResponse
from app.services import capa_service
from app.services.capa_draft_service import generate_draft
from app.services.lessons_learned.service import LessonsLearnedService

router = APIRouter(prefix="/api/capa", tags=["capa"])


@router.get("", response_model=CAPAListResponse)
async def list_capas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: str | None = None,
    product_line: str | None = None,
    overdue: bool = Query(False),
    pending_action: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")

    # Product line filtering
    allowed_pls = None
    if scope.pl_scope.mode == "NONE":
        return CAPAListResponse(items=[], total=0, page=page, page_size=page_size)
    elif scope.pl_scope.mode == "EXPLICIT":
        allowed_pls = scope.pl_scope.codes

    items, total = await capa_service.list_capas(
        db, page, page_size, status, product_line,
        overdue=overdue, pending_action=pending_action,
        allowed_product_line_codes=allowed_pls,
        factory_id=scope.effective_factory_id,
    )
    return CAPAListResponse(
        items=[CAPAResponse.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=CAPAResponse, status_code=201)
async def create_capa(
    req: CAPACreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 CREATE 权限")
    try:
        factory_id = await resolve_create_factory_id(db, scope, product_line_code=req.product_line_code)
        check_factory_access(factory_id, scope)
        capa = await capa_service.create_capa(
            db, req.title, req.document_no, req.severity, req.due_date,
            scope.user.user_id, req.product_line_code, factory_id=factory_id,
        )
        await validate_factory_invariant(capa, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CAPAResponse.model_validate(capa)


@router.get("/by-fmea-node/{fmea_id}")
async def get_capas_by_fmea_node(
    fmea_id: str,
    fmea_node_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    capas = await capa_service.get_capas_by_fmea_node(db, fmea_id, fmea_node_id)
    # Filter by product line access
    if scope.pl_scope.mode == "EXPLICIT" and scope.pl_scope.codes:
        capas = [c for c in capas if c.get("product_line_code") in scope.pl_scope.codes]
    elif scope.pl_scope.mode == "NONE":
        capas = []
    return capas


@router.get("/capabilities")
async def capa_capabilities(
    request: Request,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """获取 AI 草拟功能是否可用及当前 LLM Provider"""
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    llm_provider = getattr(request.app.state, "llm_provider", None)
    return {
        "ai_draft_enabled": llm_provider is not None,
        "llm_provider": getattr(llm_provider, "model", None) or settings.LLM_PROVIDER or None,
    }


@router.get("/{report_id}", response_model=CAPAResponse)
async def get_capa(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    return CAPAResponse.model_validate(capa)


@router.put("/{report_id}", response_model=CAPAResponse)
async def update_capa(
    report_id: uuid.UUID,
    req: CAPAUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    update_data = req.model_dump(exclude_unset=True)
    capa = await capa_service.update_capa(db, capa, update_data, scope.user.user_id)
    return CAPAResponse.model_validate(capa)


async def require_close_permission(
    report_id: uuid.UUID,
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
) -> tuple[RequestScope, Any]:
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    if capa.status in ["D7_PREVENTION", "D8_CLOSURE"]:
        level = await get_user_permission(scope.user, Module.CAPA, db)
        if level < PermissionLevel.APPROVE:
            raise HTTPException(status_code=403, detail="审批权限不足")
    return scope, capa


@router.post("/{report_id}/advance", response_model=CAPAResponse)
async def advance_capa(
    report_id: uuid.UUID,
    body: AdvanceRequest | None = None,
    db: AsyncSession = Depends(get_db),
    result: tuple[RequestScope, Any] = Depends(require_close_permission),
):
    scope, capa = result
    skip_reasons = body.d7_skip_reasons if body else None
    try:
        capa = await capa_service.advance_capa(db, capa, scope.user.user_id, skip_reasons)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CAPAResponse.model_validate(capa)


@router.post("/{report_id}/link-fmea", response_model=CAPAResponse)
async def link_fmea(
    report_id: uuid.UUID,
    fmea_id: uuid.UUID,
    fmea_node_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)

    # Validate target FMEA exists and user can access its factory
    target_fmea = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
    target_fmea = target_fmea.scalar_one_or_none()
    if target_fmea is None:
        raise HTTPException(status_code=404, detail="目标 FMEA 不存在")
    check_factory_access(target_fmea.factory_id, scope)

    capa = await capa_service.link_fmea(db, capa, fmea_id, scope.user.user_id, fmea_node_id)
    return CAPAResponse.model_validate(capa)


@router.get("/{report_id}/related-fmea")
async def get_related_fmea(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")

    capa = (
        await db.execute(
            select(CAPAEightD).where(CAPAEightD.report_id == report_id)
        )
    ).scalar_one_or_none()
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA not found")
    check_factory_access(capa.factory_id, scope)
    if not capa.fmea_ref_id:
        return {"fmea_id": None, "document_no": None, "fmea_node_id": None}

    fmea = (
        await db.execute(
            select(FMEADocument).where(FMEADocument.fmea_id == capa.fmea_ref_id)
        )
    ).scalar_one_or_none()

    return {
        "fmea_id": str(capa.fmea_ref_id),
        "document_no": fmea.document_no if fmea else None,
        "fmea_node_id": capa.fmea_node_id,
    }


def _resolve_allowed_pls(scope: RequestScope) -> list[str] | None:
    """Resolve allowed product line codes from scope. Returns None for ALL mode."""
    if scope.pl_scope.mode == "NONE":
        return []
    elif scope.pl_scope.mode == "EXPLICIT":
        return scope.pl_scope.codes
    return None  # ALL mode — no restriction


@router.get("/{report_id}/d7-fmea-recommendations")
async def get_d7_fmea_recommendations(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Require both CAPA VIEW and FMEA VIEW
    capa_level = await get_user_permission(scope.user, Module.CAPA, db)
    if capa_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 CAPA 模块的 VIEW 权限")
    fmea_level = await get_user_permission(scope.user, Module.FMEA, db)
    if fmea_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)

    # Resolve product line scope
    allowed_pls = _resolve_allowed_pls(scope)
    if allowed_pls is not None and not allowed_pls:
        return {"recommendations": []}

    # Fetch FMEA documents — always same product line as CAPA, plus RLS filter
    fmea_query = select(FMEADocument).where(FMEADocument.product_line_code == capa.product_line_code)
    if scope.effective_factory_id:
        fmea_query = fmea_query.where(FMEADocument.factory_id == scope.effective_factory_id)
    elif scope.factory_scope.accessible_factory_ids is not None:
        if scope.factory_scope.accessible_factory_ids:
            fmea_query = fmea_query.where(FMEADocument.factory_id.in_(scope.factory_scope.accessible_factory_ids))
        else:
            fmea_query = fmea_query.where(False)
    if allowed_pls is not None:
        fmea_query = fmea_query.where(FMEADocument.product_line_code.in_(allowed_pls))
    fmea_result = await db.execute(fmea_query)
    fmea_docs = [
        {
            "fmea_id": f.fmea_id,
            "document_no": f.document_no,
            "graph_data": f.graph_data,
        }
        for f in fmea_result.scalars().all()
    ]

    capa_data = {
        "fmea_ref_id": capa.fmea_ref_id,
        "fmea_node_id": capa.fmea_node_id,
        "d4_root_cause": capa.d4_root_cause or "",
        "d5_correction": capa.d5_correction,
        "product_line_code": capa.product_line_code,
    }

    from app.services.capa_service import get_d7_recommendations
    recs = get_d7_recommendations(capa_data, fmea_docs, allowed_pls)
    return {"recommendations": recs}


@router.get("/{report_id}/d4-fmea-recommendations", response_model=D4RecommendationResponse)
async def get_d4_fmea_recommendations(
    report_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    capa_level = await get_user_permission(scope.user, Module.CAPA, db)
    if capa_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 CAPA 模块的 VIEW 权限")
    fmea_level = await get_user_permission(scope.user, Module.FMEA, db)
    if fmea_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)

    allowed_pls = _resolve_allowed_pls(scope)
    if allowed_pls is not None and not allowed_pls:
        return {"items": []}

    # Preload FMEA docs for all allowed product lines (not just current CAPA's PL)
    # SemanticSearchSource may retrieve cross-PL matches; doc_map must cover them
    fmea_query = select(FMEADocument)
    if scope.effective_factory_id:
        fmea_query = fmea_query.where(FMEADocument.factory_id == scope.effective_factory_id)
    elif scope.factory_scope.accessible_factory_ids is not None:
        if scope.factory_scope.accessible_factory_ids:
            fmea_query = fmea_query.where(FMEADocument.factory_id.in_(scope.factory_scope.accessible_factory_ids))
        else:
            fmea_query = fmea_query.where(False)
    if allowed_pls is not None:
        fmea_query = fmea_query.where(FMEADocument.product_line_code.in_(allowed_pls))
    # admin (allowed_pls=None): load all FMEA docs
    fmea_result = await db.execute(fmea_query)
    fmea_docs = [
        {"fmea_id": f.fmea_id, "document_no": f.document_no, "graph_data": f.graph_data, "product_line_code": f.product_line_code}
        for f in fmea_result.scalars().all()
    ]

    linked_fmea = None
    if capa.fmea_ref_id:
        for doc in fmea_docs:
            if doc["fmea_id"] == capa.fmea_ref_id:
                linked_fmea = doc
                break

    llm_provider = request.app.state.llm_provider
    embedding_provider = request.app.state.embedding_provider
    pipeline = HybridRecommendationPipeline(db, llm_provider, embedding_provider)

    context = RecommendationContext(
        capa_data={
            "d2_description": capa.d2_description or "",
            "d3_interim": capa.d3_interim or "",
            "fmea_ref_id": capa.fmea_ref_id,
            "fmea_node_id": capa.fmea_node_id,
            "product_line_code": capa.product_line_code,
        },
        user_product_lines=allowed_pls,
        stage="d4",
        fmea_docs=fmea_docs,
        linked_fmea=linked_fmea,
    )

    result = await pipeline.recommend(context)
    return {"items": [c.to_d4_schema() for c in result.items]}


@router.get("/{report_id}/d5-fmea-recommendations", response_model=D5RecommendationResponse)
async def get_d5_fmea_recommendations(
    report_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    capa_level = await get_user_permission(scope.user, Module.CAPA, db)
    if capa_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 CAPA 模块的 VIEW 权限")
    fmea_level = await get_user_permission(scope.user, Module.FMEA, db)
    if fmea_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)

    allowed_pls = _resolve_allowed_pls(scope)
    if allowed_pls is not None and not allowed_pls:
        return {"existing_controls": [], "general_suggestions": []}

    # Preload FMEA docs for all allowed product lines (not just current CAPA's PL)
    # SemanticSearchSource may retrieve cross-PL matches; doc_map must cover them
    fmea_query = select(FMEADocument)
    if scope.effective_factory_id:
        fmea_query = fmea_query.where(FMEADocument.factory_id == scope.effective_factory_id)
    elif scope.factory_scope.accessible_factory_ids is not None:
        if scope.factory_scope.accessible_factory_ids:
            fmea_query = fmea_query.where(FMEADocument.factory_id.in_(scope.factory_scope.accessible_factory_ids))
        else:
            fmea_query = fmea_query.where(False)
    if allowed_pls is not None:
        fmea_query = fmea_query.where(FMEADocument.product_line_code.in_(allowed_pls))
    # admin (allowed_pls=None): load all FMEA docs
    fmea_result = await db.execute(fmea_query)
    fmea_docs = [
        {"fmea_id": f.fmea_id, "document_no": f.document_no, "graph_data": f.graph_data, "product_line_code": f.product_line_code}
        for f in fmea_result.scalars().all()
    ]

    linked_fmea = None
    if capa.fmea_ref_id:
        for doc in fmea_docs:
            if doc["fmea_id"] == capa.fmea_ref_id:
                linked_fmea = doc
                break

    llm_provider = request.app.state.llm_provider
    embedding_provider = request.app.state.embedding_provider
    pipeline = HybridRecommendationPipeline(db, llm_provider, embedding_provider)

    context = RecommendationContext(
        capa_data={
            "d4_root_cause": capa.d4_root_cause or "",
            "d2_description": capa.d2_description or "",
            "fmea_ref_id": capa.fmea_ref_id,
            "fmea_node_id": capa.fmea_node_id,
            "product_line_code": capa.product_line_code,
        },
        user_product_lines=allowed_pls,
        stage="d5",
        fmea_docs=fmea_docs,
        linked_fmea=linked_fmea,
    )

    result = await pipeline.recommend(context)

    existing_controls = []
    general_suggestions = []
    for c in result.items:
        control = c.to_d5_control_schema()
        if control:
            existing_controls.append(control)
        else:
            general_suggestions.append(c.to_d5_suggestion_schema())

    return {
        "existing_controls": existing_controls,
        "general_suggestions": general_suggestions,
    }


@router.get("/{report_id}/draft/capabilities")
async def draft_capabilities(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """获取当前 CAPA 报告可生成 AI 草稿的步骤列表"""
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA 报告不存在")
    check_factory_access(capa.factory_id, scope)

    current_status = capa.status
    if current_status in ("ARCHIVED", "CLOSED", "D1_TEAM"):
        return {"available_steps": [], "current_step": current_status}

    # 根据当前状态返回可用步骤（仅 D2_DESCRIPTION ~ D8_CLOSURE）
    status_to_steps = {
        "D2_DESCRIPTION": ["d2"],
        "D3_INTERIM": ["d3"],
        "D4_ROOT_CAUSE": ["d4"],
        "D5_CORRECTION": ["d5"],
        "D6_VERIFICATION": ["d6"],
        "D7_PREVENTION": ["d7"],
        "D8_CLOSURE": ["d8"],
    }

    return {
        "available_steps": status_to_steps.get(current_status, []),
        "current_step": current_status,
    }


@router.post("/{report_id}/draft/{step}", response_model=DraftResponse)
async def draft_capa_step(
    report_id: uuid.UUID,
    step: str,
    req: DraftRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """为指定步骤生成 AI 草稿"""
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    if step not in {"d2", "d3", "d4", "d5", "d6", "d7", "d8"}:
        raise HTTPException(status_code=400, detail="无效的步骤")
    result = await generate_draft(db, report_id, step, req, scope.user, request)
    return DraftResponse(**result)


@router.post("/{report_id}/lessons-learned", response_model=LessonsLearnedResponse)
async def get_capa_lessons(
    report_id: uuid.UUID,
    request: Request,
    req: LessonsLearnedRequest | None = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """Get lessons learned recommendations for a newly created CAPA."""
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    capa_doc = await capa_service.get_capa(db, report_id)
    if capa_doc is None:
        raise HTTPException(status_code=404, detail="CAPA not found")
    check_factory_access(capa_doc.factory_id, scope)

    # Check FMEA VIEW permission since service may query FMEA sources
    fmea_level = await get_user_permission(scope.user, Module.FMEA, db)
    has_fmea_view = fmea_level >= PermissionLevel.VIEW

    embedding = getattr(request.app.state, "embedding_provider", None)
    service = LessonsLearnedService(db, embedding)
    result = await service.recommend(
        report_id, "capa", req.problem_description if req else None, scope.user,
        skip_fmea_sources=not has_fmea_view,
    )
    await db.commit()
    return result