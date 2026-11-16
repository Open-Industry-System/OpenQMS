from fastapi import HTTPException
from sqlalchemy import select
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_product_line_access, is_factory_visible
from app.models.supplier import Supplier
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Module, PermissionLevel, require_permission
from app.database import get_db
from app.schemas.supply_chain_risk_map import (
    ComparisonResponse,
    HeatmapResponse,
    SnapshotGenerateResponse,
    SupplierCompareRequest,
    SupplierDetailResponse,
    TimelineResponse,
)
from app.services.supply_chain_risk_map.service import (
    current_period,
    export_heatmap,
    generate_snapshot,
    get_comparison,
    get_heatmap_data,
    get_supplier_detail,
)
from app.services.supply_chain_risk_map.service import (
    get_timeline as get_timeline_service,
)

router = APIRouter(prefix="/api/supply-chain-risk-map", tags=["supply-chain-risk-map"])


@router.get("/heatmap", response_model=HeatmapResponse)
async def get_heatmap(
    product_line_code: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    if product_line_code is not None:
        check_product_line_access(product_line_code, scope)
    return await get_heatmap_data(db, product_line_code, period, scope=scope)


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    product_line_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    if product_line_code is not None:
        check_product_line_access(product_line_code, scope)
    return await get_timeline_service(db, product_line_code, scope=scope)


@router.get("/suppliers/{supplier_id}", response_model=SupplierDetailResponse)
async def get_supplier_detail_route(
    supplier_id: UUID,
    product_line_code: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    if product_line_code is not None:
        check_product_line_access(product_line_code, scope)
    await _authorize_suppliers(db, scope, [supplier_id])
    return await get_supplier_detail(db, supplier_id, product_line_code, period, scope=scope)


@router.post("/suppliers/compare", response_model=ComparisonResponse)
async def compare_suppliers(
    body: SupplierCompareRequest,
    product_line_code: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    if product_line_code is not None:
        check_product_line_access(product_line_code, scope)
    await _authorize_suppliers(db, scope, body.supplier_ids)
    return await get_comparison(db, body.supplier_ids, product_line_code, period, scope=scope)


@router.post("/snapshots/generate", response_model=SnapshotGenerateResponse)
async def generate_snapshot_route(
    product_line_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.EDIT)),
):
    if product_line_code is not None:
        check_product_line_access(product_line_code, scope)
    count = await generate_snapshot(db, product_line_code, current_period(), scope=scope)
    return SnapshotGenerateResponse(snapshot_count=count, period=current_period())


@router.get("/export")
async def export_heatmap_route(
    format: str = Query("csv"),
    product_line_code: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    if product_line_code is not None:
        check_product_line_access(product_line_code, scope)
    return await export_heatmap(db, product_line_code, period, format, scope=scope)

async def _authorize_suppliers(db, scope, supplier_ids):
    rows = (await db.execute(select(Supplier).where(Supplier.supplier_id.in_(supplier_ids)))).scalars().all()
    if len(rows) != len(set(supplier_ids)) or any(not is_factory_visible(s.factory_id, scope) for s in rows):
        raise HTTPException(status_code=404, detail="供应商不存在")
