"""Knowledge entries list/detail API (US-E2E-01.8 §6.1)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import is_factory_visible
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.database import get_db
from app.models.knowledge_entry import KnowledgeEntry
from app.schemas.knowledge import (
    KnowledgeEntryDetail,
    KnowledgeEntryListItem,
    KnowledgeEntryListResponse,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _require_capa_view(level: int) -> None:
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")


def _resolve_list_factory_predicate(
    scope: RequestScope,
    query_factory_id: uuid.UUID | None,
):
    """Return SQLAlchemy predicate for factory isolation (spec v5 §6.1).

    Rules:
    1. effective_factory_id set → SQL factory_id == effective.
       Query foreign factory_id (≠ effective) → 403.
    2. Else query factory_id → must be accessible (None=all); else 403;
       SQL factory_id == query.
    3. Else accessible_factory_ids is not None → IN (...); empty → empty result.
    4. Else (group admin, no factory) → no factory filter.
    """
    effective = scope.effective_factory_id
    accessible = scope.factory_scope.accessible_factory_ids

    if effective is not None:
        if query_factory_id is not None and query_factory_id != effective:
            raise HTTPException(
                status_code=403,
                detail=f"无权访问工厂 '{query_factory_id}'",
            )
        return KnowledgeEntry.factory_id == effective

    if query_factory_id is not None:
        if accessible is not None and query_factory_id not in accessible:
            raise HTTPException(
                status_code=403,
                detail=f"无权访问工厂 '{query_factory_id}'",
            )
        return KnowledgeEntry.factory_id == query_factory_id

    if accessible is not None:
        if not accessible:
            return False  # empty accessible set → no rows
        return KnowledgeEntry.factory_id.in_(accessible)

    return None  # no factory filter


def _resolve_list_pl_codes(
    scope: RequestScope,
    query_pl: str | None,
) -> list[str] | None | object:
    """Intersect query product_line_code with allowed PLs.

    Returns:
      - None: no PL filter (ALL mode, no query)
      - list[str]: SQL IN filter (may be empty → empty result)
      - special EMPTY sentinel handled by caller via empty list
    """
    if scope.pl_scope.mode == "NONE":
        return []
    if scope.pl_scope.mode == "EXPLICIT":
        allowed = list(scope.pl_scope.codes or [])
        if query_pl is not None:
            return [query_pl] if query_pl in allowed else []
        return allowed
    # ALL
    if query_pl is not None:
        return [query_pl]
    return None


def _is_pl_visible(product_line_code: str | None, scope: RequestScope) -> bool:
    pl = scope.pl_scope
    if pl.mode == "ALL":
        return True
    if pl.mode == "NONE" or product_line_code is None:
        return False
    if pl.codes is None:
        return False
    return product_line_code in pl.codes


def _to_list_item(entry: KnowledgeEntry) -> KnowledgeEntryListItem:
    fields = entry.fields or {}
    tags = fields.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    return KnowledgeEntryListItem(
        entry_id=entry.entry_id,
        source_type=entry.source_type,
        source_id=entry.source_id,
        document_no=entry.document_no,
        title=entry.title,
        severity=entry.severity,
        product_line_code=entry.product_line_code,
        factory_id=entry.factory_id,
        status=entry.status,
        embedding_status=entry.embedding_status,
        embedding_id=entry.embedding_id,
        lesson_summary=fields.get("lesson_summary"),
        tags=[str(t) for t in tags],
        created_at=entry.created_at,
    )


def _to_detail(entry: KnowledgeEntry) -> KnowledgeEntryDetail:
    item = _to_list_item(entry)
    return KnowledgeEntryDetail(
        **item.model_dump(),
        fields=entry.fields or {},
        content_hash=entry.content_hash,
        llm_status=entry.llm_status,
        updated_at=entry.updated_at,
    )


@router.get("/entries", response_model=KnowledgeEntryListResponse)
async def list_knowledge_entries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    product_line_code: str | None = Query(None),
    factory_id: uuid.UUID | None = Query(None),
    source_type: str | None = Query(None),
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    _require_capa_view(level)

    factory_pred = _resolve_list_factory_predicate(scope, factory_id)
    pl_codes = _resolve_list_pl_codes(scope, product_line_code)

    # Empty PL intersection → empty page (200)
    if isinstance(pl_codes, list) and len(pl_codes) == 0:
        return KnowledgeEntryListResponse(
            items=[], total=0, page=page, page_size=page_size
        )

    # Empty accessible factories predicate
    if factory_pred is False:
        return KnowledgeEntryListResponse(
            items=[], total=0, page=page, page_size=page_size
        )

    stmt = select(KnowledgeEntry).where(KnowledgeEntry.status == "active")
    count_stmt = (
        select(func.count())
        .select_from(KnowledgeEntry)
        .where(KnowledgeEntry.status == "active")
    )

    if factory_pred is not None:
        stmt = stmt.where(factory_pred)
        count_stmt = count_stmt.where(factory_pred)

    if pl_codes is not None:
        stmt = stmt.where(KnowledgeEntry.product_line_code.in_(pl_codes))
        count_stmt = count_stmt.where(KnowledgeEntry.product_line_code.in_(pl_codes))

    if source_type:
        stmt = stmt.where(KnowledgeEntry.source_type == source_type)
        count_stmt = count_stmt.where(KnowledgeEntry.source_type == source_type)

    if q:
        pattern = f"%{q}%"
        q_pred = or_(
            KnowledgeEntry.document_no.ilike(pattern),
            KnowledgeEntry.title.ilike(pattern),
            KnowledgeEntry.embedding_text.ilike(pattern),
        )
        stmt = stmt.where(q_pred)
        count_stmt = count_stmt.where(q_pred)

    total = int((await db.execute(count_stmt)).scalar_one())
    stmt = (
        stmt.order_by(KnowledgeEntry.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return KnowledgeEntryListResponse(
        items=[_to_list_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/entries/{entry_id}", response_model=KnowledgeEntryDetail)
async def get_knowledge_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.CAPA, db)
    _require_capa_view(level)

    entry = await db.get(KnowledgeEntry, entry_id)
    # Missing, factory-invisible, or PL-denied → 404 (no existence leak / no 403)
    if (
        entry is None
        or not is_factory_visible(entry.factory_id, scope)
        or not _is_pl_visible(entry.product_line_code, scope)
    ):
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    return _to_detail(entry)
