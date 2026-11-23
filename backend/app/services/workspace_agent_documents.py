"""Allowlisted page reads and confirmed PFMEA creation for the workspace assistant."""

from dataclasses import dataclass
from datetime import datetime
from unicodedata import category
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.core.factory_scope import apply_scope_filter, resolve_effective_factory_id
from app.core.permissions import Module, PermissionLevel
from app.core.tenant_transaction import TenantBinding
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.product_line import ProductLine
from app.services.capa_current_access import current_module_access
from app.services.fmea_service import create_fmea_no_commit
from app.services.product_line_service import lock_candidate_scopes
from app.state_machines.fmea_state import FMEAState

PFMEA_LIMIT = 20


@dataclass(frozen=True, slots=True)
class Source:
    report_id: UUID
    document_no: str
    title: str
    status: str
    factory_id: UUID
    factory_name: str
    product_line_code: str
    product_line_name: str
    updated_at: datetime
    factory_active: bool
    product_line_active: bool
    user_id: UUID
    effective_factory_id: UUID | None
    tenant_binding: TenantBinding | None


@dataclass(frozen=True, slots=True)
class DraftPreview:
    source: Source
    title: str
    document_no: str

    def public(self) -> dict:
        return {
            "title": self.title,
            "document_no": self.document_no,
            "factory_name": self.source.factory_name,
            "product_line_name": self.source.product_line_name,
            "source_document_no": self.source.document_no,
            "fmea_type": "PFMEA",
            "status": FMEAState.DRAFT.value,
        }


def _require_permission(levels: dict, module: Module, level: PermissionLevel) -> None:
    if levels.get(module, PermissionLevel.NONE) < level:
        raise HTTPException(403, f"需要 {module.value} 模块的 {level.name} 权限")


async def _live_scope(
    db: AsyncSession, scope: RequestScope,
) -> tuple[RequestScope, dict]:
    # Runtime tool calls carry only the authenticated actor and selected factory.
    try:
        levels, factories, lines = await current_module_access(db, scope, Module.CAPA, PermissionLevel.VIEW)
    except PermissionError as exc:
        raise HTTPException(403, "需要 capa 模块的 VIEW 权限") from exc
    effective_factory = resolve_effective_factory_id(factories, scope.effective_factory_id)
    return RequestScope(factories, effective_factory, lines, scope.user), levels


async def read_source(
    db: AsyncSession, scope: RequestScope, report_id: UUID,
) -> Source:
    scope, _ = await _live_scope(db, scope)
    return await _read_source(db, scope, report_id)


async def _read_source(
    db: AsyncSession, scope: RequestScope, report_id: UUID, *, lock: bool = False,
) -> Source:
    query = (
        select(
            CAPAEightD.report_id, CAPAEightD.document_no, CAPAEightD.title, CAPAEightD.status,
            CAPAEightD.factory_id, Factory.name.label("factory_name"),
            CAPAEightD.product_line_code, ProductLine.name.label("product_line_name"),
            CAPAEightD.updated_at, Factory.is_active.label("factory_active"),
            ProductLine.is_active.label("product_line_active"),
        )
        .join(Factory, Factory.id == CAPAEightD.factory_id)
        .join(ProductLine, (ProductLine.code == CAPAEightD.product_line_code)
              & (ProductLine.factory_id == CAPAEightD.factory_id))
        .where(CAPAEightD.report_id == report_id)
    )
    query = apply_scope_filter(query, CAPAEightD, Module.CAPA, scope.factory_scope,
                               scope.effective_factory_id, scope.pl_scope, scope.user, db)
    if lock:
        # Some CAPA writers already hold a report lock before taking the product line lock.
        query = query.with_for_update(read=True, nowait=True, of=(CAPAEightD, Factory))
    row = (await db.execute(query)).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "当前 8D 报告不可访问")
    return Source(**row, user_id=scope.user.user_id, effective_factory_id=scope.effective_factory_id,
                  tenant_binding=db.info.get("tenant_binding"))


def _changed_preview() -> HTTPException:
    return HTTPException(409, "来源或目标范围已变化，请重新生成预览")


async def _current_source(
    db: AsyncSession, scope: RequestScope, source: Source, *, lock: bool = False,
) -> Source:
    if (source.user_id != scope.user.user_id or source.effective_factory_id != scope.effective_factory_id
            or source.tenant_binding != db.info.get("tenant_binding")):
        raise _changed_preview()
    fresh = await _read_source(db, scope, source.report_id, lock=lock)
    if fresh.factory_id != source.factory_id or fresh.product_line_code != source.product_line_code:
        raise _changed_preview()
    return fresh


def _document_link(fmea_id: UUID, document_no: str, title: str) -> dict:
    return {"id": str(fmea_id), "document_no": document_no, "title": title}


async def list_pfmeas(db: AsyncSession, scope: RequestScope, source: Source) -> list[dict]:
    await require_list_access(db, scope, source)
    rows = (await db.execute(
        select(FMEADocument.fmea_id, FMEADocument.document_no, FMEADocument.title)
        .join(CAPAEightD, (CAPAEightD.factory_id == FMEADocument.factory_id)
              & (CAPAEightD.product_line_code == FMEADocument.product_line_code))
        .where(CAPAEightD.report_id == source.report_id, FMEADocument.factory_id == source.factory_id,
               FMEADocument.product_line_code == source.product_line_code,
               FMEADocument.fmea_type == "PFMEA")
        .order_by(FMEADocument.created_at.desc(), FMEADocument.fmea_id)
        .limit(PFMEA_LIMIT)
    )).all()
    return [_document_link(row.fmea_id, row.document_no, row.title) for row in rows]


async def require_list_access(db: AsyncSession, scope: RequestScope, source: Source) -> Source:
    scope, levels = await _live_scope(db, scope)
    fresh = await _current_source(db, scope, source)
    _require_permission(levels, Module.FMEA, PermissionLevel.VIEW)
    return fresh


def _draft_field(value: str, label: str, max_length: int) -> str:
    value = value.strip()
    if not value or len(value) > max_length or any(category(char) in {"Cc", "Cs"} for char in value):
        raise HTTPException(422, f"{label}须填写 1 至 {max_length} 个字符，且不能含控制字符")
    return value


def _check_active(source: Source) -> None:
    if not source.factory_active or not source.product_line_active:
        raise HTTPException(403, "目标工厂或产品线已停用")


async def require_draft_access(db: AsyncSession, scope: RequestScope, source: Source) -> Source:
    scope, levels = await _live_scope(db, scope)
    fresh = await _current_source(db, scope, source)
    _require_permission(levels, Module.FMEA, PermissionLevel.CREATE)
    _check_active(fresh)
    return fresh


async def preview_draft(
    db: AsyncSession, scope: RequestScope, source: Source, title: str, document_no: str,
) -> DraftPreview:
    fresh = await require_draft_access(db, scope, source)
    return DraftPreview(fresh, _draft_field(title, "标题", 200), _draft_field(document_no, "单号", 50))


async def _prior_draft(
    db: AsyncSession, source: Source, preview: DraftPreview, action_id: UUID,
) -> dict | None:
    audit = (await db.execute(
        select(AuditLog.changed_fields).where(
            AuditLog.log_id == action_id,
            AuditLog.table_name == "fmea_documents", AuditLog.action == "CREATE",
            AuditLog.record_id == action_id, AuditLog.correlation_id == action_id,
            AuditLog.factory_id == source.factory_id, AuditLog.operated_by == source.user_id,
        )
    )).one_or_none()
    if audit is None:
        return None

    expected = {
        "workspace_source_report_id": str(source.report_id), "fmea_type": "PFMEA",
        "product_line_code": source.product_line_code, "status": FMEAState.DRAFT.value,
        "title": preview.title, "document_no": preview.document_no,
    }
    if any((audit.changed_fields or {}).get(field) != value for field, value in expected.items()):
        raise HTTPException(409, "该确认操作已使用")
    visible = await db.scalar(select(FMEADocument.fmea_id).where(
        FMEADocument.fmea_id == action_id, FMEADocument.factory_id == source.factory_id,
        FMEADocument.product_line_code == source.product_line_code, FMEADocument.fmea_type == "PFMEA",
    ))
    if visible is None:
        raise HTTPException(404, "已创建的 PFMEA 当前不可访问")
    return _document_link(visible, preview.document_no, preview.title)


async def apply_draft(
    db: AsyncSession, scope: RequestScope, source: Source, preview: DraftPreview, action_id: UUID,
) -> dict:
    if source != preview.source:
        raise _changed_preview()
    await require_draft_access(db, scope, source)
    try:
        # The scope lock serializes retries with the transaction that records the receipt.
        await lock_candidate_scopes(db, [(source.factory_id, source.product_line_code)])
        scope, levels = await _live_scope(db, scope)
        fresh = await _current_source(db, scope, source, lock=True)
        _require_permission(levels, Module.FMEA, PermissionLevel.CREATE)
        prior = await _prior_draft(db, fresh, preview, action_id)
        if prior is not None:
            return prior
        if fresh != source:
            raise _changed_preview()
        _check_active(fresh)

        await create_fmea_no_commit(
            db, preview.title, preview.document_no, "PFMEA", scope.user.user_id,
            source.product_line_code, source.factory_id, fmea_id=action_id,
            workspace_source_report_id=source.report_id,
        )
        await db.commit()
    except ValueError as exc:
        raise _changed_preview() from exc
    except IntegrityError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(409, "该单号当前不可用，请更换单号后重新预览") from exc
        raise
    except DBAPIError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) in {"55P03", "40P01", "40001"}:
            raise HTTPException(503, "当前单据正在更新，请重试确认") from exc
        raise
    return _document_link(action_id, preview.document_no, preview.title)
