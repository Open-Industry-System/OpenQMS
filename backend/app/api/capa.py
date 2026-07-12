import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access, check_product_line_access, resolve_create_factory_id, validate_factory_invariant
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.core.tenant import tenant_schema
from app.database import get_db
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaPptExport
from app.models.capa_d3 import (
    CapaD3AdviceAdoption,
    CapaD3AdviceGeneration,
    CapaD3AiAdvice,
    CapaD3ContainmentSnapshot,
    CapaD3Execution,
    CapaD3ImpactReport,
    CapaD3ImportRun,
)
from app.models.fmea import FMEADocument
from app.schemas.capa import (
    AdvanceRequest,
    CAPAAdvanceResponse,
    CAPACreate,
    CAPAListResponse,
    CAPAResponse,
    CAPAUpdate,
    D4RecommendationResponse,
    D5RecommendationResponse,
)
from app.schemas.capa_d3 import (
    D3AdviceItem,
    D3AdviceRequest,
    D3AdviceResponse,
    D3AdviceRunningResponse,
    D3AdoptionResponse,
    D3DecisionRequest,
    D3ExecutionRequest,
    D3ExecutionResponse,
    D3ExecutionUpdateRequest,
    D3ImportRequest,
    D3ImportResponse,
    D3ReportResponse,
    D3ReportRunningResponse,
    D3RunResponse,
    D3SnapshotResponse,
    ProvenanceEntry,
)
from app.schemas.capa_draft import DraftRequest, DraftResponse
from app.schemas.capa_ppt import PptExportDetailResponse
from app.schemas.capa_verification import (
    AdoptRequest, AdoptResponse, D7AutoFillRequest, D7AutoFillResponse,
    D7NodeActionCreate, D7NodeActionResponse,
    VerificationCreate, VerificationResponse, VerificationUpdate,
)
from app.schemas.lessons_learned import LessonsLearnedRequest, LessonsLearnedResponse
from app.schemas.recommendation_stage import StageRunSchema
from app.services import capa_d3_containment_service
from app.services import capa_d7_action_service
from app.services import capa_ppt_review_service, capa_ppt_service, capa_service
from app.services import capa_verification_service
from app.services.capa_d7_action_service import ConflictError
from app.services.capa_draft_service import generate_draft
from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline, RecommendationContext
from app.services.lessons_learned.service import LessonsLearnedService
from app.services.agent import provider_adapter
from app.state_machines.eightd_state import EightDState, _linear_next_safe
from app.utils.pptx import pptx_response

router = APIRouter(prefix="/api/capa", tags=["capa"])

D4_RETRY_THRESHOLD = 3


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
    from app.services.agent import provider_adapter
    from app.services.agent.provider_adapter import ProviderNotConfiguredError
    try:
        pc = await provider_adapter.build_client(db)
        ai_draft_enabled = True
        llm_provider_name = pc.model or settings.LLM_MODEL or None
    except ProviderNotConfiguredError:
        ai_draft_enabled = False
        llm_provider_name = None
    return {
        "ai_draft_enabled": ai_draft_enabled,
        "llm_provider": llm_provider_name,
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
    try:
        capa = await capa_service.update_capa(db, capa, update_data, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CAPAResponse.model_validate(capa)


async def require_advance_permission(
    report_id: uuid.UUID,
    body: AdvanceRequest | None = None,
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
) -> tuple[RequestScope, Any]:
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    # P1 TOCTOU：锁 capa 行 FOR UPDATE + 刷新状态，再做边权限校验，确保授权与状态迁移基于
    # 同一份锁定状态。否则「锁前按 D8_GATE_PENDING 判 EDIT 放行 → 并发推进到 D8_APPROVAL_PENDING
    # → 锁后 (D8_APPROVAL_PENDING→D8_CLOSURE) 变合法 APPROVE 边」会让 EDIT 用户越权完成审批。
    # 锁在同一请求 session 上持有至 advance_capa（后者再锁为 no-op，并保护绕过依赖的直接调用方）。
    await db.execute(
        select(CAPAEightD).where(CAPAEightD.report_id == report_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    target = body.target_state if body else None
    # target_state=None（线性 advance）时算出实际 target，否则归档边 (D8_CLOSURE→ARCHIVED)
    # 因 target=None 不命中 approve_edges，会误落 EDIT 分支放行 field_qe 归档。
    target = target or _linear_next_safe(capa.status)
    # APPROVE 边：审批 / 驳回 / 归档（capa.status 此时为锁后刷新值，与 advance_capa 迁移同一状态）
    approve_edges = (
        (EightDState.D8_APPROVAL_PENDING.value, EightDState.D8_CLOSURE.value),
        (EightDState.D8_APPROVAL_PENDING.value, EightDState.D7_PREVENTION.value),
        (EightDState.D8_CLOSURE.value, EightDState.ARCHIVED.value),
    )
    if (capa.status, target.value if target else None) in approve_edges:
        level = await get_user_permission(scope.user, Module.CAPA, db)
        if level < PermissionLevel.APPROVE:
            raise HTTPException(status_code=403, detail="审批权限不足")
    else:
        level = await get_user_permission(scope.user, Module.CAPA, db)
        if level < PermissionLevel.EDIT:
            raise HTTPException(status_code=403, detail="编辑权限不足")
    return scope, capa


@router.post("/{report_id}/advance", response_model=CAPAAdvanceResponse)
async def advance_capa(
    report_id: uuid.UUID,
    body: AdvanceRequest | None = None,
    db: AsyncSession = Depends(get_db),
    result: tuple[RequestScope, Any] = Depends(require_advance_permission),
):
    scope, capa = result
    from_status = capa.status
    try:
        capa = await capa_service.advance_capa(
            db, capa, scope.user.user_id, body or AdvanceRequest()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    warning = None
    if from_status == EightDState.D4_ROOT_CAUSE.value and (capa.d4_retry_count or 0) >= D4_RETRY_THRESHOLD:
        warning = "建议升级处理（D4 验证已回退 {} 次）".format(capa.d4_retry_count)
    return CAPAAdvanceResponse(capa=CAPAResponse.model_validate(capa), warning=warning)


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

    embedding_provider = request.app.state.embedding_provider
    from app.services.agent import provider_adapter
    from app.services.agent.provider_adapter import ProviderNotConfiguredError
    try:
        pc = await provider_adapter.build_client(db)
    except ProviderNotConfiguredError:
        pc = None
    pipeline = HybridRecommendationPipeline(db, pc, embedding_provider)

    context = RecommendationContext(
        capa_data={
            "d2_description": capa.d2_description or "",
            "d3_interim": capa.d3_interim or "",
            "fmea_ref_id": capa.fmea_ref_id,
            "fmea_node_id": capa.fmea_node_id,
            "product_line_code": capa.product_line_code,
            "report_id": capa.report_id,
        },
        user_product_lines=allowed_pls,
        stage="d4",
        factory_id=capa.factory_id,   # R13-修复：源查询按 factory_id 隔离
        fmea_docs=fmea_docs,
        linked_fmea=linked_fmea,
    )

    result = await pipeline.recommend(
        context,
        user=scope.user,
        report_id=report_id,
        factory_id=capa.factory_id,
        tenant_schema=tenant_schema(request),
    )
    await db.commit()
    if result.blocked:
        raise HTTPException(
            status_code=422,
            detail={"blocked": True, "reason": "LLM credentials not configured",
                    "stages": [StageRunSchema(**s.__dict__).model_dump() for s in result.stages]},
        )
    return {
        "stages": [StageRunSchema(**s.__dict__).model_dump() for s in result.stages],
        "items": [c.to_d4_schema() for c in result.items],
    }


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

    embedding_provider = request.app.state.embedding_provider
    from app.services.agent import provider_adapter
    from app.services.agent.provider_adapter import ProviderNotConfiguredError
    try:
        pc = await provider_adapter.build_client(db)
    except ProviderNotConfiguredError:
        pc = None
    pipeline = HybridRecommendationPipeline(db, pc, embedding_provider)

    context = RecommendationContext(
        capa_data={
            "d4_root_cause": capa.d4_root_cause or "",
            "d2_description": capa.d2_description or "",
            "fmea_ref_id": capa.fmea_ref_id,
            "fmea_node_id": capa.fmea_node_id,
            "product_line_code": capa.product_line_code,
            "report_id": capa.report_id,
        },
        user_product_lines=allowed_pls,
        stage="d5",
        factory_id=capa.factory_id,   # R13-修复：源查询按 factory_id 隔离
        fmea_docs=fmea_docs,
        linked_fmea=linked_fmea,
    )

    result = await pipeline.recommend(
        context,
        user=scope.user,
        report_id=report_id,
        factory_id=capa.factory_id,
        tenant_schema=tenant_schema(request),
    )
    await db.commit()
    if result.blocked:
        raise HTTPException(
            status_code=422,
            detail={"blocked": True, "reason": "LLM credentials not configured",
                    "stages": [StageRunSchema(**s.__dict__).model_dump() for s in result.stages]},
        )

    existing_controls = []
    general_suggestions = []
    for c in result.items:
        control = c.to_d5_control_schema()
        if control:
            existing_controls.append(control)
        else:
            general_suggestions.append(c.to_d5_suggestion_schema())

    return {
        "stages": [StageRunSchema(**s.__dict__).model_dump() for s in result.stages],
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
        # 新壳状态：无可用编辑步骤（D7 已冻结、D8 待审批冻结）
        "D7_COMPLETED": [],
        "D8_GATE_PENDING": [],
        "D8_APPROVAL_PENDING": [],
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


@router.post("/{report_id}/adopt-recommendation", response_model=AdoptResponse)
async def adopt_recommendation_ep(
    report_id: uuid.UUID, req: AdoptRequest,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    check_product_line_access(capa.product_line_code, scope)
    adoption, field_value = await capa_verification_service.adopt_recommendation(db, capa, req, scope.user)
    return AdoptResponse(adoption_id=adoption.adoption_id, d_step=req.d_step, field_value=field_value)


@router.post("/{report_id}/root-cause-verifications", response_model=VerificationResponse)
async def create_verification_ep(
    report_id: uuid.UUID, req: VerificationCreate,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    check_product_line_access(capa.product_line_code, scope)
    try:
        rec = await capa_verification_service.create_verification(db, capa, req, scope.user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return VerificationResponse.model_validate(rec)


@router.get("/{report_id}/root-cause-verifications", response_model=list[VerificationResponse])
async def list_verifications_ep(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    check_product_line_access(capa.product_line_code, scope)
    items = await capa_verification_service.list_verifications(db, capa)
    return [VerificationResponse.model_validate(i) for i in items]


@router.patch("/{report_id}/root-cause-verifications/{vid}", response_model=VerificationResponse)
async def update_verification_ep(
    report_id: uuid.UUID, vid: uuid.UUID, req: VerificationUpdate,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    check_product_line_access(capa.product_line_code, scope)
    try:
        rec = await capa_verification_service.update_verification(db, capa, vid, req, scope.user)
    except LookupError:
        raise HTTPException(status_code=404, detail="verification not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return VerificationResponse.model_validate(rec)


@router.post("/{report_id}/d7-node-actions", response_model=D7NodeActionResponse)
async def d7_record_action_ep(
    report_id: uuid.UUID, req: D7NodeActionCreate,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    if await get_user_permission(scope.user, Module.FMEA, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 VIEW 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    check_product_line_access(capa.product_line_code, scope)
    try:
        rec = await capa_d7_action_service.record_d7_action(db, capa, req, scope.user)
    except LookupError:
        raise HTTPException(status_code=404, detail="目标 FMEA 不存在")
    except PermissionError:
        raise HTTPException(status_code=403, detail="目标 FMEA 跨工厂")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return D7NodeActionResponse.model_validate(rec)


@router.get("/{report_id}/d7-node-actions", response_model=list[D7NodeActionResponse])
async def d7_list_actions_ep(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    # D7 action 行含 fmea_id/node_id/control 状态，属 FMEA 衍生数据——读也要 FMEA VIEW（与 POST 对齐，防 CAPA-only 用户绕过 FMEA 权限读 D7 元数据）
    if await get_user_permission(scope.user, Module.FMEA, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 VIEW 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    check_product_line_access(capa.product_line_code, scope)
    items = await capa_d7_action_service.list_d7_actions(db, capa)
    return [D7NodeActionResponse.model_validate(i) for i in items]


@router.post("/{report_id}/d7-auto-fill", response_model=D7AutoFillResponse)
async def d7_auto_fill_ep(
    report_id: uuid.UUID, req: D7AutoFillRequest,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    if await get_user_permission(scope.user, Module.FMEA, db) < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    check_factory_access(capa.factory_id, scope)
    check_product_line_access(capa.product_line_code, scope)
    try:
        rec, info = await capa_d7_action_service.auto_fill_d7(db, capa, req, scope.user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError:
        raise HTTPException(status_code=404, detail="目标 FMEA 不存在")
    except PermissionError:
        raise HTTPException(status_code=403, detail="目标 FMEA 跨工厂")
    except ConflictError:
        raise HTTPException(status_code=409, detail="已自动回填")
    return D7AutoFillResponse(action_id=rec.action_id,
                              prevention_control_node_id=info["prevention_control_node_id"],
                              prevention_control_name_after=info["prevention_control_name_after"],
                              is_new_control=info["is_new_control"])


@router.post("/{report_id}/ppt-export")
async def export_ppt(
    report_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(404, "CAPA 不存在")
    check_factory_access(capa.factory_id, scope)
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.CREATE:  # engineer+（L2=CREATE，seed quality_engineer capa=2）
        raise HTTPException(403, "生成权限不足（需 engineer+）")
    if capa.status not in (EightDState.D8_CLOSURE.value, EightDState.ARCHIVED.value):
        raise HTTPException(400, "8D 未关闭，不可生成 PPT")

    # 预生成 export 元数据
    export_id = uuid.uuid4()
    generated_at = datetime.now(UTC)
    version = generated_at.strftime("%Y%m%dT%H%M%SZ")
    tenant = tenant_schema(request)

    # 解析 LLM provider client（None = 未配置）
    try:
        pc = await provider_adapter.build_client(db)
    except provider_adapter.ProviderNotConfiguredError:
        pc = None

    # 审查闭环 + 渲染：审查闭环异常（非 LLM 缺失）/ 渲染失败均属故事 §92 FAILED 条件 → 500，不落 export
    try:
        content, review = await capa_ppt_review_service.review_and_correct(
            db, report_id, pc, tenant,
        )
        # 最终渲染一次（审查后 review_status 已知）
        meta = capa_ppt_service.ExportMeta(
            export_id=export_id, version=version,
            generated_at=generated_at, generated_by=scope.user.user_id,
        )
        pptx_bytes = capa_ppt_service.render_pptx(content, meta, review.status, review.rounds)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(500, "PPT 生成失败（审查闭环异常或渲染失败）")

    # 写 capa_ppt_export + PPT_GENERATED 审计
    export = CapaPptExport(
        export_id=export_id, capa_id=report_id, factory_id=capa.factory_id,
        tenant_schema=tenant, generated_at=generated_at, generated_by=scope.user.user_id,
        version=version, file_url=None,
        review_status=review.status, review_rounds=review.rounds, review_report=review.report,
    )
    db.add(export)
    db.add(AuditLog(
        table_name="capa_eightd", record_id=report_id, action="PPT_GENERATED",
        changed_fields={"export_id": str(export_id), "version": version,
                        "review_status": review.status, "review_rounds": review.rounds},
        operated_by=scope.user.user_id, factory_id=capa.factory_id, tenant_schema=tenant,
    ))
    await db.commit()

    headers = {
        "X-PPT-Review-Status": review.status,
        "X-PPT-Review-Rounds": str(review.rounds),
        "X-PPT-Export-Id": str(export_id),
    }
    return pptx_response(pptx_bytes, f"8D_{capa.document_no}_{version}.pptx", headers)


@router.get("/{report_id}/ppt-exports/{export_id}", response_model=PptExportDetailResponse)
async def get_ppt_export(
    report_id: uuid.UUID,
    export_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(404, "CAPA 不存在")
    check_factory_access(capa.factory_id, scope)
    export = await capa_ppt_service.get_export(db, export_id, report_id)
    if export is None:
        raise HTTPException(404, "PPT 生成记录不存在")
    return PptExportDetailResponse(
        export_id=str(export.export_id), capa_id=str(export.capa_id),
        generated_at=export.generated_at, generated_by=str(export.generated_by),
        version=export.version, review_status=export.review_status,
        review_rounds=export.review_rounds, review_report=export.review_report,
    )


# ===== D3 Containment endpoints (US-E2E-01.1 Task 6) =====


def _d3_check_scope(entity, scope: RequestScope):
    """Wrap factory/product-line checks to raise 404 (information hiding)."""
    try:
        check_factory_access(entity.factory_id, scope)
        check_product_line_access(getattr(entity, "product_line_code", None), scope)
    except HTTPException:
        raise HTTPException(status_code=404, detail="8D report not found")


def _assert_d3_stage(capa: CAPAEightD):
    if capa.status != EightDState.D3_INTERIM.value:
        raise HTTPException(status_code=400, detail="仅 D3 阶段可操作")


@router.post("/{report_id}/d3/import", response_model=D3ImportResponse)
async def d3_import_ep(
    report_id: uuid.UUID, req: D3ImportRequest,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    _d3_check_scope(capa, scope)
    _assert_d3_stage(capa)
    try:
        result = await capa_d3_containment_service.import_containment_data(
            db, capa.report_id, scope.user, req.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return D3ImportResponse(**result)


@router.get("/{report_id}/d3/runs", response_model=list[D3RunResponse])
async def d3_list_runs_ep(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    _d3_check_scope(capa, scope)
    result = await db.execute(
        select(CapaD3ImportRun)
        .where(CapaD3ImportRun.capa_id == report_id)
        .order_by(CapaD3ImportRun.created_at)
    )
    return [D3RunResponse.model_validate(r) for r in result.scalars().all()]


@router.get("/{report_id}/d3/snapshots", response_model=list[D3SnapshotResponse])
async def d3_list_snapshots_ep(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    _d3_check_scope(capa, scope)
    current_run = await db.scalar(
        select(CapaD3ImportRun)
        .where(CapaD3ImportRun.capa_id == report_id, CapaD3ImportRun.is_current == True)
    )
    if current_run is None:
        return []
    result = await db.execute(
        select(CapaD3ContainmentSnapshot)
        .where(CapaD3ContainmentSnapshot.run_id == current_run.run_id)
        .order_by(CapaD3ContainmentSnapshot.created_at)
    )
    return [D3SnapshotResponse.model_validate(s) for s in result.scalars().all()]


@router.get("/{report_id}/d3/report", response_model=D3ReportResponse)
async def d3_get_report_ep(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    _d3_check_scope(capa, scope)
    current_run = await db.scalar(
        select(CapaD3ImportRun)
        .where(CapaD3ImportRun.capa_id == report_id, CapaD3ImportRun.is_current == True)
    )
    if current_run is None:
        raise HTTPException(status_code=404, detail="当前导入运行不存在")
    report = await db.scalar(
        select(CapaD3ImpactReport)
        .where(
            CapaD3ImpactReport.run_id == current_run.run_id,
            CapaD3ImpactReport.is_current == True,
        )
    )
    if report is None:
        raise HTTPException(status_code=404, detail="D3 影响报告不存在")
    return D3ReportResponse.model_validate(report)


@router.post("/{report_id}/d3/report")
async def d3_generate_report_ep(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    _d3_check_scope(capa, scope)
    _assert_d3_stage(capa)

    current_run = await db.scalar(
        select(CapaD3ImportRun)
        .where(CapaD3ImportRun.capa_id == report_id, CapaD3ImportRun.is_current == True)
    )
    if current_run is None:
        raise HTTPException(status_code=400, detail="需先导入遏制数据")

    # 1. Already running -> 202
    running_report = await db.scalar(
        select(CapaD3ImpactReport)
        .where(
            CapaD3ImpactReport.run_id == current_run.run_id,
            CapaD3ImpactReport.status == "running",
        )
    )
    if running_report is not None:
        retry_after = capa_d3_containment_service.RETRY_AFTER_SECONDS
        return JSONResponse(
            status_code=202,
            content={"report_id": str(running_report.report_id), "status": "running"},
            headers={"Retry-After": str(retry_after)},
        )

    # 2. Current report done/failed/superseded -> 200
    current_report = await db.scalar(
        select(CapaD3ImpactReport)
        .where(
            CapaD3ImpactReport.run_id == current_run.run_id,
            CapaD3ImpactReport.is_current == True,
        )
    )
    if current_report is not None:
        return D3ReportResponse.model_validate(current_report)

    # 3. No report yet -> generate
    result = await capa_d3_containment_service.generate_impact_report(
        db, current_run.run_id, scope.user
    )
    if result["status"] == "blocked":
        raise HTTPException(
            status_code=422,
            detail={"blocked": True, "message": "LLM 凭证未配置，报告生成被阻断"},
        )
    if result["status"] == "running":
        retry_after = result.get("retry_after", capa_d3_containment_service.RETRY_AFTER_SECONDS)
        return JSONResponse(
            status_code=202,
            content={"report_id": str(result["report_id"]), "status": "running"},
            headers={"Retry-After": str(retry_after)},
        )

    # done / failed / superseded -> return the report row
    report_id_out = result.get("report_id")
    if report_id_out:
        report = await db.get(CapaD3ImpactReport, uuid.UUID(report_id_out))
    else:
        report = await db.scalar(
            select(CapaD3ImpactReport)
            .where(CapaD3ImpactReport.run_id == current_run.run_id)
            .order_by(CapaD3ImpactReport.created_at.desc())
            .limit(1)
        )
    if report is None:
        raise HTTPException(status_code=404, detail="D3 影响报告不存在")
    return D3ReportResponse.model_validate(report)
"""D3 Advice endpoint implementation to append to capa.py"""

# ===== D3 Advice endpoints (US-E2E-01.1 Task 8) =====


@router.post("/{report_id}/d3/advice")
async def d3_generate_advice_ep(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    """POST /d3/advice: Generate AI advice for a CAPA's current impact report."""
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    _d3_check_scope(capa, scope)
    _assert_d3_stage(capa)

    # Find current run -> current report
    current_run = await db.scalar(
        select(CapaD3ImportRun)
        .where(CapaD3ImportRun.capa_id == report_id, CapaD3ImportRun.is_current == True)
    )
    if current_run is None:
        raise HTTPException(status_code=400, detail="需先导入遏制数据")

    current_report = await db.scalar(
        select(CapaD3ImpactReport)
        .where(
            CapaD3ImpactReport.run_id == current_run.run_id,
            CapaD3ImpactReport.is_current == True,
        )
    )
    if current_report is None:
        raise HTTPException(status_code=400, detail="需先生成影响报告")

    # 1. Already running -> 202
    running_gen = await db.scalar(
        select(CapaD3AdviceGeneration)
        .where(
            CapaD3AdviceGeneration.report_id == current_report.report_id,
            CapaD3AdviceGeneration.status == "running",
        )
    )
    if running_gen is not None:
        retry_after = capa_d3_containment_service.RETRY_AFTER_SECONDS
        return JSONResponse(
            status_code=202,
            content={"generation_id": str(running_gen.generation_id), "status": "running"},
            headers={"Retry-After": str(retry_after)},
        )

    # 2. Current generation done -> return advice list
    current_gen = await db.scalar(
        select(CapaD3AdviceGeneration)
        .where(
            CapaD3AdviceGeneration.report_id == current_report.report_id,
            CapaD3AdviceGeneration.is_current == True,
        )
    )
    if current_gen is not None and current_gen.status == "done":
        return await _build_advice_response(db, current_gen)

    # 3. No generation yet -> generate
    result = await capa_d3_containment_service.generate_advice(
        db, capa.report_id, current_report.report_id, scope.user, None
    )
    if result["status"] == "blocked":
        raise HTTPException(
            status_code=422,
            detail={"blocked": True, "message": "LLM 凭证未配置，建议生成被阻断"},
        )
    if result["status"] == "running":
        retry_after = result.get("retry_after", capa_d3_containment_service.RETRY_AFTER_SECONDS)
        return JSONResponse(
            status_code=202,
            content={"generation_id": str(result["generation_id"]), "status": "running"},
            headers={"Retry-After": str(retry_after)},
        )

    # done / failed -> return advice list (done) or failed status
    gen_id = result.get("generation_id")
    if gen_id:
        gen = await db.get(CapaD3AdviceGeneration, uuid.UUID(str(gen_id)))
        if gen and gen.status == "done":
            return await _build_advice_response(db, gen)
        if gen and gen.status == "failed":
            return D3AdviceResponse(advice=[], status="failed", error=gen.error)

    # failed generation without a retrievable gen row
    return D3AdviceResponse(advice=[], status="failed", error=result.get("error"))


@router.get("/{report_id}/d3/advice", response_model=D3AdviceResponse)
async def d3_get_advice_ep(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    """GET /d3/advice: Return current generation's advice list with provenance and adoption status."""
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    _d3_check_scope(capa, scope)

    # Find current report
    current_run = await db.scalar(
        select(CapaD3ImportRun)
        .where(CapaD3ImportRun.capa_id == report_id, CapaD3ImportRun.is_current == True)
    )
    if current_run is None:
        return D3AdviceResponse(advice=[])

    current_report = await db.scalar(
        select(CapaD3ImpactReport)
        .where(
            CapaD3ImpactReport.run_id == current_run.run_id,
            CapaD3ImpactReport.is_current == True,
        )
    )
    if current_report is None:
        return D3AdviceResponse(advice=[])

    # Find current generation
    current_gen = await db.scalar(
        select(CapaD3AdviceGeneration)
        .where(
            CapaD3AdviceGeneration.report_id == current_report.report_id,
            CapaD3AdviceGeneration.is_current == True,
        )
    )
    if current_gen is None:
        return D3AdviceResponse(advice=[])

    return await _build_advice_response(db, current_gen)


async def _build_advice_response(db: AsyncSession, gen: CapaD3AdviceGeneration) -> D3AdviceResponse:
    """Build D3AdviceResponse from a current advice generation."""
    advice_rows = (
        await db.execute(
            select(CapaD3AiAdvice).where(
                CapaD3AiAdvice.generation_id == gen.generation_id
            )
        )
    ).scalars().all()

    # Fetch adoption status for each advice
    advice_ids = [a.advice_id for a in advice_rows]
    adoptions = {}
    if advice_ids:
        adoption_rows = (
            await db.execute(
                select(CapaD3AdviceAdoption).where(
                    CapaD3AdviceAdoption.advice_id.in_(advice_ids)
                )
            )
        ).scalars().all()
        for ad in adoption_rows:
            adoptions[ad.advice_id] = ad.decision

    items = []
    for a in advice_rows:
        provenance = [
            ProvenanceEntry(
                source_type=p["source_type"],
                snapshot_id=uuid.UUID(p["snapshot_id"]) if p.get("snapshot_id") else None,
                record_key=p["record_key"],
                stage=p.get("stage", "llm_advice"),
            )
            for p in (a.source_provenance or [])
        ]
        items.append(
            D3AdviceItem(
                advice_id=a.advice_id,
                advice_type=a.advice_type,
                advice_text=a.advice_text,
                source_provenance=provenance,
                adoption_status=adoptions.get(a.advice_id),
            )
        )

    return D3AdviceResponse(advice=items, status="done")


# ===== D3 Advice Adoption endpoints (US-E2E-01.1 Task 9) =====


@router.post("/{report_id}/d3/advice/{advice_id}/decision")
async def d3_decision_advice_ep(
    report_id: uuid.UUID,
    advice_id: uuid.UUID,
    req: D3DecisionRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """POST /d3/advice/{advice_id}/decision: Adopt or reject an advice item."""
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    _d3_check_scope(capa, scope)
    _assert_d3_stage(capa)

    try:
        result = await capa_d3_containment_service.adopt_advice(
            db, report_id, advice_id, req.decision, req.adopted_text, scope.user
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        # CHECK constraint: rejected requires NULL adopted_text
        raise HTTPException(
            status_code=400, detail="rejected decision requires adopted_text to be null"
        )

    await db.commit()
    return {"adoption_id": result["adoption_id"]}


@router.get("/{report_id}/d3/adoptions", response_model=list[D3AdoptionResponse])
async def d3_list_adoptions_ep(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """GET /d3/adoptions: Return list of adoptions for the current generation."""
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    _d3_check_scope(capa, scope)

    # Find current run → current report → current generation
    current_run = await db.scalar(
        select(CapaD3ImportRun).where(
            CapaD3ImportRun.capa_id == report_id, CapaD3ImportRun.is_current == True
        )
    )
    if current_run is None:
        return []

    current_report = await db.scalar(
        select(CapaD3ImpactReport).where(
            CapaD3ImpactReport.run_id == current_run.run_id,
            CapaD3ImpactReport.is_current == True,
        )
    )
    if current_report is None:
        return []

    current_gen = await db.scalar(
        select(CapaD3AdviceGeneration).where(
            CapaD3AdviceGeneration.report_id == current_report.report_id,
            CapaD3AdviceGeneration.is_current == True,
        )
    )
    if current_gen is None:
        return []

    # Get advice IDs for this generation
    advice_rows = (
        await db.execute(
            select(CapaD3AiAdvice.advice_id).where(
                CapaD3AiAdvice.generation_id == current_gen.generation_id
            )
        )
    ).scalars().all()

    if not advice_rows:
        return []

    # Get adoptions for these advice IDs
    adoptions = (
        await db.execute(
            select(CapaD3AdviceAdoption).where(
                CapaD3AdviceAdoption.advice_id.in_(advice_rows)
            )
        )
    ).scalars().all()

    return [D3AdoptionResponse.model_validate(a) for a in adoptions]


# ===== D3 Execution endpoints (US-E2E-01.1 Task 10) =====


@router.post("/{report_id}/d3/execution")
async def d3_record_execution_ep(
    report_id: uuid.UUID,
    req: D3ExecutionRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """POST /d3/execution: Record a containment execution.

    Note: Uses report_id as both CAPA ID and URL parameter.
    """
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    _d3_check_scope(capa, scope)
    _assert_d3_stage(capa)

    try:
        # Find current report
        current_run = await db.scalar(
            select(CapaD3ImportRun).where(
                CapaD3ImportRun.capa_id == capa.report_id, CapaD3ImportRun.is_current == True
            )
        )
        if current_run is None:
            raise HTTPException(status_code=400, detail="需先导入遏制数据")

        current_report = await db.scalar(
            select(CapaD3ImpactReport).where(
                CapaD3ImpactReport.run_id == current_run.run_id,
                CapaD3ImpactReport.is_current == True,
            )
        )
        if current_report is None:
            raise HTTPException(status_code=400, detail="需先生成影响报告")

        # First param is capa_id, second is report_id
        result = await capa_d3_containment_service.record_execution(
            db, capa.report_id, current_report.report_id, scope.user, req.model_dump()
        )
        # Re-fetch to get full data
        execution = await db.get(CapaD3Execution, uuid.UUID(result["execution_id"]))
        await db.commit()
        return D3ExecutionResponse.model_validate(execution)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.patch("/{report_id}/d3/execution/{execution_id}")
async def d3_update_execution_ep(
    report_id: uuid.UUID,
    execution_id: uuid.UUID,
    req: D3ExecutionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """PATCH /d3/execution/{id}: Update execution status/text/evidence."""
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 EDIT 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    _d3_check_scope(capa, scope)

    try:
        result = await capa_d3_containment_service.update_execution(
            db, report_id, execution_id, scope.user, req.model_dump(exclude_unset=True)
        )
        await db.commit()
        execution = await db.get(CapaD3Execution, execution_id)
        return D3ExecutionResponse.model_validate(execution)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

@router.get("/{report_id}/d3/executions", response_model=list[D3ExecutionResponse])
async def d3_list_executions_ep(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """GET /d3/executions: List executions for current report."""
    if await get_user_permission(scope.user, Module.CAPA, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    _d3_check_scope(capa, scope)

    # Find current report
    current_run = await db.scalar(
        select(CapaD3ImportRun).where(
            CapaD3ImportRun.capa_id == report_id, CapaD3ImportRun.is_current == True
        )
    )
    if current_run is None:
        return []

    current_report = await db.scalar(
        select(CapaD3ImpactReport).where(
            CapaD3ImpactReport.run_id == current_run.run_id,
            CapaD3ImpactReport.is_current == True,
        )
    )
    if current_report is None:
        return []

    executions = (
        await db.execute(
            select(CapaD3Execution)
            .where(CapaD3Execution.report_id == current_report.report_id)
            .order_by(CapaD3Execution.created_at)
        )
    ).scalars().all()

    return [D3ExecutionResponse.model_validate(e) for e in executions]
