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
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    return await get_heatmap_data(db, product_line_code, period)


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    product_line_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    return await get_timeline_service(db, product_line_code)


@router.get("/suppliers/{supplier_id}", response_model=SupplierDetailResponse)
async def get_supplier_detail_route(
    supplier_id: UUID,
    product_line_code: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    return await get_supplier_detail(db, supplier_id, product_line_code, period)


@router.post("/suppliers/compare", response_model=ComparisonResponse)
async def compare_suppliers(
    body: SupplierCompareRequest,
    product_line_code: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    return await get_comparison(db, body.supplier_ids, product_line_code, period)


@router.post("/snapshots/generate", response_model=SnapshotGenerateResponse)
async def generate_snapshot_route(
    product_line_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.EDIT)),
):
    count = await generate_snapshot(db, product_line_code, current_period())
    return SnapshotGenerateResponse(snapshot_count=count, period=current_period())


@router.get("/export")
async def export_heatmap_route(
    format: str = Query("csv"),
    product_line_code: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    return await export_heatmap(db, product_line_code, period, format)