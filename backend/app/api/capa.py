import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline, RecommendationContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import require_permission, Module, PermissionLevel, get_user_permission, get_current_user
from app.core.product_line_filter import get_user_product_line_codes, enforce_product_line_access
from typing import Any
from app.models.user import User

from app.config import settings
from app.schemas.capa import CAPACreate, CAPAUpdate, CAPAResponse, CAPAListResponse, AdvanceRequest, D4RecommendationResponse, D5RecommendationResponse
from app.schemas.capa_draft import DraftRequest, DraftResponse
from app.services import capa_service
from app.services.capa_draft_service import generate_draft

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
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    allowed_pls = None
    if not user.role_definition.bypass_row_level_security:
        allowed_pls = await get_user_product_line_codes(user, db)
        if not allowed_pls:
            return CAPAListResponse(items=[], total=0, page=page, page_size=page_size)
    items, total = await capa_service.list_capas(
        db, page, page_size, status, product_line,
        overdue=overdue, pending_action=pending_action,
        allowed_product_line_codes=allowed_pls,
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
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.CREATE)),
):
    try:
        await enforce_product_line_access(user, req.product_line_code, db)
        capa = await capa_service.create_capa(
            db, req.title, req.document_no, req.severity, req.due_date, user.user_id, req.product_line_code
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CAPAResponse.model_validate(capa)


@router.get("/by-fmea-node/{fmea_id}")
async def get_capas_by_fmea_node(
    fmea_id: str,
    fmea_node_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    capas = await capa_service.get_capas_by_fmea_node(db, fmea_id, fmea_node_id)
    # Filter by product line access
    if not user.role_definition.bypass_row_level_security:
        user_codes = await get_user_product_line_codes(user, db)
        capas = [c for c in capas if c.get("product_line_code") in user_codes]
    return capas


@router.get("/{report_id}", response_model=CAPAResponse)
async def get_capa(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    await enforce_product_line_access(user, capa.product_line_code, db)
    return CAPAResponse.model_validate(capa)


@router.put("/{report_id}", response_model=CAPAResponse)
async def update_capa(
    report_id: uuid.UUID,
    req: CAPAUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.EDIT)),
):
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    await enforce_product_line_access(user, capa.product_line_code, db)
    update_data = req.model_dump(exclude_unset=True)
    new_pl = update_data.get("product_line_code")
    if new_pl is not None and new_pl != capa.product_line_code:
        await enforce_product_line_access(user, new_pl, db)
    capa = await capa_service.update_capa(db, capa, update_data, user.user_id)
    return CAPAResponse.model_validate(capa)


async def require_close_permission(
    report_id: uuid.UUID,
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.EDIT)),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, Any]:
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    await enforce_product_line_access(user, capa.product_line_code, db)
    if capa.status in ["D7_PREVENTION", "D8_CLOSURE"]:
        level = await get_user_permission(user, Module.CAPA, db)
        if level < PermissionLevel.APPROVE:
            raise HTTPException(status_code=403, detail="审批权限不足")
    return user, capa


@router.post("/{report_id}/advance", response_model=CAPAResponse)
async def advance_capa(
    report_id: uuid.UUID,
    body: AdvanceRequest | None = None,
    db: AsyncSession = Depends(get_db),
    result: tuple[User, Any] = Depends(require_close_permission),
):
    user, capa = result
    skip_reasons = body.d7_skip_reasons if body else None
    try:
        capa = await capa_service.advance_capa(db, capa, user.user_id, skip_reasons)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CAPAResponse.model_validate(capa)


@router.post("/{report_id}/link-fmea", response_model=CAPAResponse)
async def link_fmea(
    report_id: uuid.UUID,
    fmea_id: uuid.UUID,
    fmea_node_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.EDIT)),
):
    from app.models.fmea import FMEADocument

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    await enforce_product_line_access(user, capa.product_line_code, db)

    # Validate target FMEA exists and user can access its product line
    target_fmea = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
    target_fmea = target_fmea.scalar_one_or_none()
    if target_fmea is None:
        raise HTTPException(status_code=404, detail="目标 FMEA 不存在")
    await enforce_product_line_access(user, target_fmea.product_line_code, db)

    capa = await capa_service.link_fmea(db, capa, fmea_id, user.user_id, fmea_node_id)
    return CAPAResponse.model_validate(capa)


@router.get("/{report_id}/related-fmea")
async def get_related_fmea(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    from app.models.capa import CAPAEightD
    from app.models.fmea import FMEADocument

    capa = (
        await db.execute(
            select(CAPAEightD).where(CAPAEightD.report_id == report_id)
        )
    ).scalar_one_or_none()
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA not found")
    await enforce_product_line_access(user, capa.product_line_code, db)
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


@router.get("/{report_id}/d7-fmea-recommendations")
async def get_d7_fmea_recommendations(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    from app.models.fmea import FMEADocument
    from app.services.capa_service import get_d7_recommendations

    # Require both CAPA VIEW and FMEA VIEW
    fmea_level = await get_user_permission(user, Module.FMEA, db)
    if fmea_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    await enforce_product_line_access(user, capa.product_line_code, db)

    # Get user's accessible product lines (bypass for admins)
    if user.role_definition.bypass_row_level_security:
        allowed_pls = None  # no restriction
    else:
        allowed_pls = await get_user_product_line_codes(user, db)
        if not allowed_pls:
            return {"recommendations": []}

    # Fetch FMEA documents — always same product line as CAPA, plus RLS filter
    fmea_query = select(FMEADocument).where(FMEADocument.product_line_code == capa.product_line_code)
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

    recs = get_d7_recommendations(capa_data, fmea_docs, allowed_pls)
    return {"recommendations": recs}


@router.get("/{report_id}/d4-fmea-recommendations", response_model=D4RecommendationResponse)
async def get_d4_fmea_recommendations(
    report_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    from app.models.fmea import FMEADocument
    from app.services.capa_service import get_capa

    fmea_level = await get_user_permission(user, Module.FMEA, db)
    if fmea_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    capa = await get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    await enforce_product_line_access(user, capa.product_line_code, db)

    if user.role_definition.bypass_row_level_security:
        allowed_pls = None
    else:
        allowed_pls = await get_user_product_line_codes(user, db)
        if not allowed_pls:
            return {"items": []}

    # Preload FMEA docs for all allowed product lines (not just current CAPA's PL)
    # SemanticSearchSource may retrieve cross-PL matches; doc_map must cover them
    fmea_query = select(FMEADocument)
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
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    from app.models.fmea import FMEADocument
    from app.services.capa_service import get_capa

    fmea_level = await get_user_permission(user, Module.FMEA, db)
    if fmea_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    capa = await get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    await enforce_product_line_access(user, capa.product_line_code, db)

    if user.role_definition.bypass_row_level_security:
        allowed_pls = None
    else:
        allowed_pls = await get_user_product_line_codes(user, db)
        if not allowed_pls:
            return {"existing_controls": [], "general_suggestions": []}

    # Preload FMEA docs for all allowed product lines (not just current CAPA's PL)
    # SemanticSearchSource may retrieve cross-PL matches; doc_map must cover them
    fmea_query = select(FMEADocument)
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


@router.get("/capabilities")
async def capa_capabilities(
    request: Request,
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    """获取 AI 草拟功能是否可用及当前 LLM Provider"""
    llm_provider = getattr(request.app.state, "llm_provider", None)
    return {
        "ai_draft_enabled": llm_provider is not None,
        "llm_provider": getattr(llm_provider, "model", None) or settings.LLM_PROVIDER or None,
    }


@router.get("/{report_id}/draft/capabilities")
async def draft_capabilities(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.EDIT)),
):
    """获取当前 CAPA 报告可生成 AI 草稿的步骤列表"""
    capa = await capa_service.get_capa(db, report_id)
    if not capa:
        raise HTTPException(status_code=404, detail="CAPA 报告不存在")
    await enforce_product_line_access(user, capa.product_line_code, db)

    current_status = capa.status
    if current_status == "ARCHIVED":
        return {"available_steps": [], "current_step": current_status}

    # 根据当前状态返回可用步骤
    status_to_steps = {
        "D1_TEAM": ["d2"],
        "D2_DESCRIPTION": ["d2", "d3"],
        "D3_INTERIM": ["d3", "d4"],
        "D4_ROOT_CAUSE": ["d4", "d5"],
        "D5_CORRECTION": ["d5", "d6"],
        "D6_VERIFICATION": ["d6", "d7"],
        "D7_PREVENTION": ["d7", "d8"],
        "D8_CLOSURE": ["d8"],
        "CLOSED": ["d8"],
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
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.EDIT)),
):
    """为指定步骤生成 AI 草稿"""
    if step not in {"d2", "d3", "d4", "d5", "d6", "d7", "d8"}:
        raise HTTPException(status_code=400, detail="无效的步骤")
    result = await generate_draft(db, report_id, step, req, user, request)
    return DraftResponse(**result)
