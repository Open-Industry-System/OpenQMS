"""Knowledge entries list/detail API (US-E2E-01.8 §6.1)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_request_scope
from app.core.permissions import PermissionLevel
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
        closure_review_scope="unreviewed_supplement" if entry.source_type == "capa" and "closure" in fields else None,
        tags=[str(t) for t in tags],
        created_at=entry.created_at,
    )


def _to_detail(entry: KnowledgeEntry) -> KnowledgeEntryDetail:
    item = _to_list_item(entry)
    fields = dict(entry.fields or {})
    if item.closure_review_scope is not None:
        fields["closure_review_scope"] = item.closure_review_scope
    return KnowledgeEntryDetail(
        **item.model_dump(),
        fields=fields,
        content_hash=entry.content_hash,
        llm_status=entry.llm_status,
        updated_at=entry.updated_at,
    )


async def _current_scope(db, scope):
    from app.services.capa_current_access import current_capa_access
    try:
        _, factories, lines = await current_capa_access(db, scope)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Current CAPA permission required", headers={'Cache-Control': 'no-store'}) from None
    from app.core.factory_scope import FactoryScope, ProductLineScope
    requested_factories = scope.factory_scope.accessible_factory_ids
    fresh_factories = factories.accessible_factory_ids
    allowed_factories = (fresh_factories if requested_factories is None else requested_factories
        if fresh_factories is None else sorted(set(requested_factories) & set(fresh_factories), key=str))
    factories = FactoryScope(allowed_factories, factories.default_factory_id)
    requested_lines = scope.pl_scope
    if requested_lines.mode == 'NONE' or lines.mode == 'NONE':
        lines = ProductLineScope('NONE', [])
    elif requested_lines.mode != 'ALL':
        codes = (requested_lines.codes or []) if lines.mode == 'ALL' else sorted(
            set(requested_lines.codes or []) & set(lines.codes or []))
        lines = ProductLineScope('EXPLICIT' if codes else 'NONE', codes)
    current = RequestScope(factories, scope.effective_factory_id, lines, scope.user)
    if (current.effective_factory_id is not None and factories.accessible_factory_ids is not None
            and current.effective_factory_id not in factories.accessible_factory_ids):
        raise HTTPException(status_code=403, detail="Current factory permission required", headers={'Cache-Control': 'no-store'})
    return current


def _filters(scope, factory_id=None, product_line_code=None, source_type=None, q=None, *, active=True):
    from app.services.capa_d4_material import ordinary_capa_predicate
    predicates = [or_(KnowledgeEntry.source_type != 'capa', text(ordinary_capa_predicate('knowledge_entries.source_id')))]
    if active:
        predicates.append(KnowledgeEntry.status == 'active')
    factory = _resolve_list_factory_predicate(scope, factory_id)
    if factory is not None:
        predicates.append(factory)
    lines = _resolve_list_pl_codes(scope, product_line_code)
    if lines is not None:
        predicates.append(KnowledgeEntry.product_line_code.in_(lines))
    if source_type:
        predicates.append(KnowledgeEntry.source_type == source_type)
    if q:
        pattern = f"%{q}%"
        predicates.append(or_(KnowledgeEntry.document_no.ilike(pattern), KnowledgeEntry.title.ilike(pattern),
                              KnowledgeEntry.embedding_text.ilike(pattern)))
    return predicates


def _metadata(entry):
    return dict(id=str(entry.entry_id), hash=entry.content_hash, source_type=entry.source_type,
        source_id=str(entry.source_id), factory_id=str(entry.factory_id), line=entry.product_line_code)


async def _final_projection(db, predicates, frozen_ids):
    # Count and frozen-page admission share ONE final database snapshot. No
    # private fields/text are selected into this integrity-only projection.
    total = select(func.count()).select_from(KnowledgeEntry).where(*predicates).scalar_subquery()
    page = select(func.jsonb_agg(func.jsonb_build_object(
        'id', KnowledgeEntry.entry_id, 'hash', KnowledgeEntry.content_hash,
        'source_type', KnowledgeEntry.source_type, 'source_id', KnowledgeEntry.source_id,
        'factory_id', KnowledgeEntry.factory_id, 'line', KnowledgeEntry.product_line_code))).where(
            KnowledgeEntry.entry_id.in_(frozen_ids), *predicates).scalar_subquery()
    count, metadata = (await db.execute(select(total, page))).one()
    return int(count), {row['id']: row for row in (metadata or [])}


def _reply(payload):
    return JSONResponse(content=jsonable_encoder(payload), headers={'Cache-Control': 'no-store'})


@router.get("/entries", response_model=KnowledgeEntryListResponse)
async def list_knowledge_entries(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    product_line_code: str | None = Query(None), factory_id: uuid.UUID | None = Query(None),
    source_type: str | None = Query(None), q: str | None = Query(None),
    db: AsyncSession = Depends(get_db), scope: RequestScope = Depends(get_request_scope),
):
    scope = await _current_scope(db, scope)
    predicates = _filters(scope, factory_id, product_line_code, source_type, q)
    ids = list(await db.scalars(select(KnowledgeEntry.entry_id).where(*predicates)
        .order_by(KnowledgeEntry.created_at.desc()).offset((page - 1) * page_size).limit(page_size)))
    rows = list(await db.scalars(select(KnowledgeEntry).where(
        KnowledgeEntry.entry_id.in_(ids), *predicates))) if ids else []
    scope = await _current_scope(db, scope)
    total, current = await _final_projection(db,
        _filters(scope, factory_id, product_line_code, source_type, q), ids)
    by_id = {row.entry_id: row for row in rows if current.get(str(row.entry_id)) == _metadata(row)}
    return _reply(KnowledgeEntryListResponse(items=[_to_list_item(by_id[id]) for id in ids if id in by_id],
        total=total, page=page, page_size=page_size))


@router.get("/entries/{entry_id}", response_model=KnowledgeEntryDetail)
async def get_knowledge_entry(entry_id: uuid.UUID, db: AsyncSession = Depends(get_db),
        scope: RequestScope = Depends(get_request_scope)):
    scope = await _current_scope(db, scope)
    predicates = _filters(scope, active=False)
    admitted = await db.scalar(select(KnowledgeEntry.entry_id).where(
        KnowledgeEntry.entry_id == entry_id, *predicates))
    if admitted is None:
        raise HTTPException(status_code=404, detail="Knowledge entry not found", headers={'Cache-Control': 'no-store'})
    entry = await db.scalar(select(KnowledgeEntry).where(KnowledgeEntry.entry_id == entry_id, *predicates)
        .execution_options(populate_existing=True))
    scope = await _current_scope(db, scope)
    _, current = await _final_projection(db, _filters(scope, active=False), [entry_id])
    if entry is None or current.get(str(entry_id)) != _metadata(entry):
        raise HTTPException(status_code=404, detail="Knowledge entry not found", headers={'Cache-Control': 'no-store'})
    return _reply(_to_detail(entry))
