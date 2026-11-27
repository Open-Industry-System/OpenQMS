"""Optional read-only projections for an IQC investigation."""

from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
from json import dumps
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.core.factory_scope import check_product_line_access, is_factory_visible
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.models.iqc_inspection import IqcInspection
from app.models.iqc_material import IqcMaterial
from app.models.product_line import ProductLine
from app.models.supplier import Supplier

HISTORY_PROJECTION = "iqc.inspection.related_history.v1"
MATERIAL_PROJECTION = "iqc.material.current_summary.v1"
SUPPLIER_PROJECTION = "supplier.current_summary.v1"

_HISTORY_WINDOW_DAYS = 90
_MAX_PAGE_SIZE = 50


@dataclass(frozen=True)
class ProjectionSource:
    projection: str
    object_id: UUID
    version: str


@dataclass(frozen=True)
class HistoryCursor:
    inspection_date: date
    inspection_id: UUID


@dataclass(frozen=True)
class InspectionHistoryEntry:
    source: ProjectionSource
    inspection_no: str
    inspection_date: date
    status: str
    inspection_result: str
    defect_qty: int


@dataclass(frozen=True)
class InspectionHistoryPage:
    start: date
    end: date
    items: tuple[InspectionHistoryEntry, ...]
    next_cursor: HistoryCursor | None


@dataclass(frozen=True)
class CurrentMaterialSummary:
    source: ProjectionSource
    part_no: str
    part_name: str


@dataclass(frozen=True)
class CurrentSupplierSummary:
    source: ProjectionSource
    supplier_no: str
    name: str


@dataclass(frozen=True)
class _InspectionAnchor:
    factory_id: UUID
    product_line_code: str | None
    supplier_id: UUID
    material_id: UUID | None
    part_no: str | None


def _source(projection: str, object_id: UUID, *version_parts: object) -> ProjectionSource:
    encoded = dumps((projection, object_id, version_parts), default=str, separators=(",", ":"))
    return ProjectionSource(projection, object_id, sha256(encoded.encode()).hexdigest())


async def _read_anchor(
    db: AsyncSession, scope: RequestScope, inspection_id: UUID,
) -> _InspectionAnchor:
    """Reauthorize the current anchor in the caller's tenant-bound session."""
    if await get_user_permission(scope.user, Module.IQC, db) < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")
    inspection = IqcInspection
    row = (await db.execute(select(
        inspection.factory_id, inspection.product_line_code,
        inspection.supplier_id, inspection.material_id, inspection.part_no,
    ).where(inspection.inspection_id == inspection_id))).one_or_none()
    if row is None or not is_factory_visible(row.factory_id, scope):
        raise HTTPException(status_code=404, detail="对象不存在")
    check_product_line_access(row.product_line_code, scope)
    if row.product_line_code is not None:
        factory_id = await db.scalar(
            select(ProductLine.factory_id).where(ProductLine.code == row.product_line_code),
        )
        if factory_id != row.factory_id:
            raise HTTPException(status_code=404, detail="对象不存在")
    return _InspectionAnchor(*row)


def _history_entry(row) -> InspectionHistoryEntry:
    source = _source(
        HISTORY_PROJECTION, row.inspection_id, row.identity_generation, row.inspection_revision,
        row.inspection_no, row.inspection_date, row.status, row.inspection_result, row.defect_qty,
    )
    return InspectionHistoryEntry(
        source, row.inspection_no, row.inspection_date, row.status, row.inspection_result, row.defect_qty,
    )


async def read_inspection_history(
    db: AsyncSession,
    scope: RequestScope,
    inspection_id: UUID,
    *,
    task_date: date,
    cursor: HistoryCursor | None = None,
    limit: int = 20,
) -> InspectionHistoryPage | None:
    """Read related inspections with coordinates fixed by the task and anchor.

    The runtime supplies the bound date, authenticates any cursor, and signs
    returned source versions. None indicates the history capability is unavailable.
    """
    if not 1 <= limit <= _MAX_PAGE_SIZE:
        raise ValueError("Invalid inspection history page size")
    anchor = await _read_anchor(db, scope, inspection_id)
    if anchor.product_line_code is None:
        return None

    inspection = IqcInspection
    if anchor.material_id is not None:
        material_filter = inspection.material_id == anchor.material_id
    elif anchor.part_no and anchor.part_no.strip():
        material_filter = inspection.part_no == anchor.part_no
    else:
        return None

    start = task_date - timedelta(days=_HISTORY_WINDOW_DAYS - 1)
    query = select(
        inspection.inspection_id, inspection.inspection_no, inspection.inspection_date,
        inspection.status, inspection.inspection_result, inspection.defect_qty,
        inspection.identity_generation, inspection.inspection_revision,
    ).where(
        inspection.inspection_id != inspection_id,
        inspection.factory_id == anchor.factory_id,
        inspection.product_line_code == anchor.product_line_code,
        inspection.supplier_id == anchor.supplier_id,
        material_filter,
        inspection.inspection_date.between(start, task_date),
    )
    if cursor is not None:
        if not start <= cursor.inspection_date <= task_date:
            raise ValueError("Invalid inspection history cursor")
        query = query.where(or_(
            inspection.inspection_date < cursor.inspection_date,
            and_(inspection.inspection_date == cursor.inspection_date,
                 inspection.inspection_id < cursor.inspection_id),
        ))
    rows = (await db.execute(query.order_by(
        inspection.inspection_date.desc(), inspection.inspection_id.desc(),
    ).limit(limit + 1))).all()
    items = tuple(_history_entry(row) for row in rows[:limit])
    boundary = rows[limit - 1] if len(rows) > limit else None
    return InspectionHistoryPage(
        start, task_date, items,
        HistoryCursor(boundary.inspection_date, boundary.inspection_id) if boundary is not None else None,
    )


async def read_current_material(
    db: AsyncSession, scope: RequestScope, inspection_id: UUID,
) -> CurrentMaterialSummary | None:
    """Read the in-scope material attached to the inspection, if available."""
    anchor = await _read_anchor(db, scope, inspection_id)
    if anchor.material_id is None or anchor.product_line_code is None:
        return None
    material = IqcMaterial
    row = (await db.execute(select(
        material.material_id, material.part_no, material.part_name, material.created_at, material.updated_at,
    ).where(
        material.material_id == anchor.material_id,
        material.factory_id == anchor.factory_id,
        material.product_line_code == anchor.product_line_code,
    ))).one_or_none()
    if row is None:
        return None
    return CurrentMaterialSummary(
        _source(MATERIAL_PROJECTION, row.material_id, anchor.factory_id, anchor.product_line_code,
                row.created_at, row.updated_at, row.part_no, row.part_name),
        row.part_no, row.part_name,
    )


async def read_current_supplier(
    db: AsyncSession, scope: RequestScope, inspection_id: UUID,
) -> CurrentSupplierSummary | None:
    """Read the factory-scoped supplier attached to the inspection, if available."""
    anchor = await _read_anchor(db, scope, inspection_id)
    if await get_user_permission(scope.user, Module.SUPPLIER, db) < PermissionLevel.VIEW:
        return None
    supplier = Supplier
    row = (await db.execute(select(
        supplier.supplier_id, supplier.supplier_no, supplier.name, supplier.created_at, supplier.updated_at,
    ).where(
        supplier.supplier_id == anchor.supplier_id,
        supplier.factory_id == anchor.factory_id,
    ))).one_or_none()
    if row is None:
        return None
    return CurrentSupplierSummary(
        _source(SUPPLIER_PROJECTION, row.supplier_id, anchor.factory_id,
                row.created_at, row.updated_at, row.supplier_no, row.name),
        row.supplier_no, row.name,
    )
