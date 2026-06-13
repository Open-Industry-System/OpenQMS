"""Search API routes: semantic search, RAG Q&A, reindex."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Module, PermissionLevel, get_current_user, get_user_permission
from app.database import get_db
from app.models.user import User
from app.schemas.search import (
    QARequest,
    QAResponse,
    ReindexResponse,
    SemanticSearchResponse,
)
from app.services.search_service import SearchService

router = APIRouter(prefix="/api/search", tags=["search"])


def _get_search_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SearchService:
    llm_provider = getattr(request.app.state, "llm_provider", None)
    embedding_provider = getattr(request.app.state, "embedding_provider", None)
    return SearchService(db=db, llm_provider=llm_provider, embedding_provider=embedding_provider)


@router.get("/semantic", response_model=SemanticSearchResponse)
async def semantic_search(
    q: str = Query(..., min_length=1, max_length=500),
    entity_types: str | None = Query(None, description="Comma-separated entity types"),
    product_line_code: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: SearchService = Depends(_get_search_service),
):
    """Semantic search across all quality documents."""
    level = await get_user_permission(user, Module.KNOWLEDGE_GRAPH, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 knowledge_graph 模块的 VIEW 权限")
    parsed_types = entity_types.split(",") if entity_types else None
    return await service.semantic_search(
        query=q,
        user=user,
        product_line_code=product_line_code,
        entity_types=parsed_types,
        limit=limit,
    )


@router.post("/ask", response_model=QAResponse)
async def ask_question(
    body: QARequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: SearchService = Depends(_get_search_service),
):
    """RAG Q&A: ask a question and get an LLM-generated answer with citations.

    Uses generic auth — result-level permission filtering in SearchService handles access control.
    """
    level = await get_user_permission(user, Module.KNOWLEDGE_GRAPH, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 knowledge_graph 模块的 VIEW 权限")
    if not service.llm and not service.embedding:
        raise HTTPException(status_code=503, detail="搜索服务未配置（无 embedding 或 LLM provider）")
    return await service.ask(
        question=body.question,
        user=user,
        product_line_code=body.product_line_code,
        max_context_chunks=body.max_context_chunks,
    )


@router.post("/reindex", response_model=ReindexResponse)
async def reindex(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger re-indexing of all quality documents (admin only)."""
    if not user.role_definition or user.role_definition.role_key != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可执行重新索引")
    from app.services.embedding_backfill import ENTITY_TYPES, backfill_entity_type

    total = 0
    for entity_type in ENTITY_TYPES:
        count = await backfill_entity_type(db, entity_type, batch_size=100)
        total += count

    return ReindexResponse(
        message=f"已入队 {total} 条记录等待重新索引",
        enqueued=total,
    )
