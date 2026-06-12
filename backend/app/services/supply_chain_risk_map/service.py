"""Supply chain risk map service: snapshot generation, heatmap queries, export."""
import json
from datetime import date
from io import BytesIO
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import StreamingResponse

from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
from app.services.supplier_risk.service import calculate_all_supplier_scores
from app.services.supply_chain_risk_map.aggregator import (
    aggregate_supply_chain_metrics,
    normalize_to_risk_index,
    ppm_to_risk_index,
)
from app.schemas.supply_chain_risk_map import (
    HeatmapCell, HeatmapColumn, HeatmapRow, HeatmapResponse,
    TimelineResponse, SupplierDetailResponse, DimensionDetail,
    SupplierDimensionTrend, ComparisonSupplier, ComparisonResponse,
    SnapshotGenerateResponse,
)


def current_period() -> str:
    """Return current month as YYYY-MM string."""
    today = date.today()
    return f"{today.year}-{today.month:02d}"


def _prev_period(period: str) -> str:
    """Return previous month as YYYY-MM."""
    year, month = period.split("-")
    y, m = int(year), int(month)
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


# Column definitions for the heatmap
HEATMAP_COLUMNS = [
    HeatmapColumn(key="risk_score", label="风险分", type="risk", polarity="higher_is_risk"),
    HeatmapColumn(key="quality_score", label="质量分", type="score", polarity="higher_is_risk"),
    HeatmapColumn(key="delivery_score", label="交付分", type="score", polarity="higher_is_risk"),
    HeatmapColumn(key="compliance_score", label="合规分", type="score", polarity="higher_is_risk"),
    HeatmapColumn(key="erp_on_time_rate", label="ERP准时率", type="percent", polarity="lower_is_risk"),
    HeatmapColumn(key="purchase_amount_pct", label="采购占比", type="percent", polarity="neutral_exposure"),
    HeatmapColumn(key="open_scar_count", label="开放SCAR", type="count", polarity="higher_is_risk"),
    HeatmapColumn(key="ppm_value", label="PPM", type="number", polarity="higher_is_risk"),
]


async def generate_snapshot(
    db: AsyncSession,
    product_line_code: Optional[str],
    period: str,
) -> int:
    """Calculate scores, aggregate metrics, normalize, and UPSERT snapshots.

    Returns number of snapshots created/updated.
    Only allowed for the current period.
    """
    if period != current_period():
        raise ValueError(f"Cannot generate snapshot for {period}: only current period {current_period()} is allowed")

    # 1. Calculate risk scores for all suppliers
    scores = await calculate_all_supplier_scores(db, product_line_code)

    # 2. Aggregate ERP/IQC/SCAR metrics
    supplier_ids = [s["supplier_id"] for s in scores]
    metrics = {}
    if supplier_ids:
        metrics = await aggregate_supply_chain_metrics(db, supplier_ids, product_line_code, period)

    # 3. Build normalized dimensions and UPSERT
    count = 0
    for score_result in scores:
        sid = score_result["supplier_id"]
        supplier_metrics = metrics.get(sid, {})

        # Merge score + metrics into dimensions dict
        dimensions = {
            "risk_score": {"raw_value": score_result["risk_score"], "polarity": "higher_is_risk", "source": "risk_evaluation"},
            "quality_score": {"raw_value": score_result["quality_score"], "polarity": "higher_is_risk", "source": "risk_evaluation"},
            "delivery_score": {"raw_value": score_result["delivery_score"], "polarity": "higher_is_risk", "source": "risk_evaluation"},
            "compliance_score": {"raw_value": score_result["compliance_score"], "polarity": "higher_is_risk", "source": "risk_evaluation"},
            "erp_on_time_rate": {"raw_value": supplier_metrics.get("erp_on_time_rate"), "polarity": "lower_is_risk", "source": supplier_metrics.get("erp_on_time_rate_source", "missing")},
            "purchase_amount_pct": {"raw_value": supplier_metrics.get("purchase_amount_pct"), "polarity": "neutral_exposure", "source": supplier_metrics.get("purchase_amount_pct_source", "missing")},
            "open_scar_count": {"raw_value": supplier_metrics.get("open_scar_count", 0), "polarity": "higher_is_risk", "source": supplier_metrics.get("open_scar_count_source", "missing")},
            "ppm_value": {"raw_value": supplier_metrics.get("ppm_value"), "polarity": "higher_is_risk", "source": supplier_metrics.get("ppm_source", "missing")},
        }

        # Normalize all dimensions to risk_index
        dimensions = normalize_to_risk_index(dimensions)

        # PPM uses a dedicated normalization (min(ppm/50, 100)) instead of raw value
        if dimensions.get("ppm_value", {}).get("raw_value") is not None:
            dimensions["ppm_value"]["risk_index"] = ppm_to_risk_index(dimensions["ppm_value"]["raw_value"])

        # UPSERT using the named constraint (covers both NULL and non-NULL product_line_code)
        await db.execute(
            text("""
                INSERT INTO supply_chain_risk_snapshots
                    (snapshot_id, supplier_id, product_line_code, snapshot_period,
                     risk_score, risk_level, quality_score, delivery_score, compliance_score,
                     erp_on_time_rate, purchase_amount_pct, open_scar_count, ppm_value, dimensions)
                VALUES (gen_random_uuid(), :sid, :plc, :period,
                        :rs, :rl, :qs, :ds, :cs,
                        :ot, :pap, :osc, :ppm, CAST(:dims AS jsonb))
                ON CONFLICT ON CONSTRAINT uq_supplier_pl_period
                DO UPDATE SET
                    risk_score = EXCLUDED.risk_score, risk_level = EXCLUDED.risk_level,
                    quality_score = EXCLUDED.quality_score, delivery_score = EXCLUDED.delivery_score,
                    compliance_score = EXCLUDED.compliance_score, erp_on_time_rate = EXCLUDED.erp_on_time_rate,
                    purchase_amount_pct = EXCLUDED.purchase_amount_pct, open_scar_count = EXCLUDED.open_scar_count,
                    ppm_value = EXCLUDED.ppm_value, dimensions = EXCLUDED.dimensions
            """),
            {
                "sid": sid, "plc": product_line_code, "period": period,
                "rs": score_result["risk_score"], "rl": score_result["risk_level"],
                "qs": score_result["quality_score"], "ds": score_result["delivery_score"],
                "cs": score_result["compliance_score"],
                "ot": supplier_metrics.get("erp_on_time_rate"),
                "pap": supplier_metrics.get("purchase_amount_pct"),
                "osc": supplier_metrics.get("open_scar_count", 0),
                "ppm": supplier_metrics.get("ppm_value"),
                "dims": json.dumps(dimensions),
            },
        )
        count += 1

    await db.commit()
    return count


async def get_heatmap_data(
    db: AsyncSession,
    product_line_code: Optional[str],
    period: Optional[str],
) -> HeatmapResponse:
    """Build heatmap from snapshot + previous month for diff calculation."""
    period = period or current_period()
    prev = _prev_period(period)

    # Current period snapshots
    current_rows = (await db.execute(
        select(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.snapshot_period == period)
        .where(
            SupplyChainRiskSnapshot.product_line_code == product_line_code
            if product_line_code else
            SupplyChainRiskSnapshot.product_line_code.is_(None)
        )
    )).scalars().all()

    # Fetch supplier names for all snapshot supplier_ids
    from app.models.supplier import Supplier
    supplier_ids = list({snap.supplier_id for snap in current_rows})
    supplier_name_map = {}
    if supplier_ids:
        sup_result = await db.execute(
            select(Supplier.supplier_id, Supplier.name)
            .where(Supplier.supplier_id.in_(supplier_ids))
        )
        supplier_name_map = {sid: name for sid, name in sup_result.all()}

    # Previous period snapshots for diff
    prev_map = {}
    prev_rows = (await db.execute(
        select(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.snapshot_period == prev)
        .where(
            SupplyChainRiskSnapshot.product_line_code == product_line_code
            if product_line_code else
            SupplyChainRiskSnapshot.product_line_code.is_(None)
        )
    )).scalars().all()
    for row in prev_rows:
        prev_map[row.supplier_id] = row

    rows = []
    for snap in current_rows:
        prev_snap = prev_map.get(snap.supplier_id)
        cells = []
        for col in HEATMAP_COLUMNS:
            dims = snap.dimensions or {}
            dim = dims.get(col.key, {})
            raw = dim.get("raw_value")
            ri = dim.get("risk_index")
            prev_raw = None
            if prev_snap and prev_snap.dimensions:
                prev_dim = prev_snap.dimensions.get(col.key, {})
                prev_raw = prev_dim.get("raw_value")
            diff_val = None
            if raw is not None and prev_raw is not None:
                diff_val = raw - prev_raw
            cells.append(HeatmapCell(
                key=col.key,
                value=raw,
                risk_index=ri,
                level=_risk_level(raw) if col.key == "risk_score" else None,
                diff=diff_val,
                source=dim.get("source", "missing"),
            ))
        rows.append(HeatmapRow(
            supplier_id=snap.supplier_id,
            supplier_name=supplier_name_map.get(snap.supplier_id, str(snap.supplier_id)),
            cells=cells,
        ))

    return HeatmapResponse(
        period=period,
        prev_period=prev,
        product_line_code=product_line_code,
        columns=HEATMAP_COLUMNS,
        rows=rows,
    )


async def get_timeline(
    db: AsyncSession,
    product_line_code: Optional[str],
) -> TimelineResponse:
    """Return list of periods that have snapshots, filtered by product line."""
    query = select(SupplyChainRiskSnapshot.snapshot_period).distinct()
    if product_line_code:
        query = query.where(SupplyChainRiskSnapshot.product_line_code == product_line_code)
    else:
        query = query.where(SupplyChainRiskSnapshot.product_line_code.is_(None))
    result = await db.execute(query.order_by(SupplyChainRiskSnapshot.snapshot_period))
    periods = [r for (r,) in result.all()]

    # Count distinct suppliers in current period
    count_query = select(func.count(SupplyChainRiskSnapshot.supplier_id.distinct()))
    if product_line_code:
        count_query = count_query.where(SupplyChainRiskSnapshot.product_line_code == product_line_code)
    else:
        count_query = count_query.where(SupplyChainRiskSnapshot.product_line_code.is_(None))
    supplier_count = (await db.execute(
        count_query.where(SupplyChainRiskSnapshot.snapshot_period == current_period())
    )).scalar() or 0

    return TimelineResponse(
        periods=periods,
        current_period=current_period(),
        supplier_count=supplier_count,
    )


async def get_supplier_detail(
    db: AsyncSession,
    supplier_id: UUID,
    product_line_code: Optional[str],
    period: Optional[str],
) -> SupplierDetailResponse:
    """Return single supplier detail with dimensions + 6-month trend."""
    period = period or current_period()

    snap = (await db.execute(
        select(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.supplier_id == supplier_id)
        .where(SupplyChainRiskSnapshot.snapshot_period == period)
        .where(
            SupplyChainRiskSnapshot.product_line_code == product_line_code
            if product_line_code else
            SupplyChainRiskSnapshot.product_line_code.is_(None)
        )
    )).scalar_one_or_none()

    if not snap:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Fetch supplier name
    from app.models.supplier import Supplier
    sup = await db.get(Supplier, snap.supplier_id)
    supplier_name = sup.name if sup else str(snap.supplier_id)

    dimensions = {
        key: DimensionDetail(
            raw_value=val.get("raw_value"),
            risk_index=val.get("risk_index"),
            polarity=val.get("polarity", "higher_is_risk"),
            source=val.get("source", "missing"),
        )
        for key, val in (snap.dimensions or {}).items()
    }

    # 6-month trend (filtered by product_line_code and up to the selected period)
    trend_query = (
        select(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.supplier_id == supplier_id)
        .where(
            SupplyChainRiskSnapshot.product_line_code == product_line_code
            if product_line_code else
            SupplyChainRiskSnapshot.product_line_code.is_(None)
        )
        .where(SupplyChainRiskSnapshot.snapshot_period <= period)
        .order_by(SupplyChainRiskSnapshot.snapshot_period.desc())
        .limit(6)
    )
    trend_rows = (await db.execute(trend_query)).scalars().all()
    trend = [
        SupplierDimensionTrend(
            period=t.snapshot_period,
            risk_score=t.risk_score,
            quality_score=t.quality_score,
            delivery_score=t.delivery_score,
            compliance_score=t.compliance_score,
        )
        for t in reversed(trend_rows)
    ]

    return SupplierDetailResponse(
        supplier_id=snap.supplier_id,
        supplier_name=supplier_name,
        product_line_code=product_line_code,
        period=period,
        dimensions=dimensions,
        trend=trend,
    )


async def get_comparison(
    db: AsyncSession,
    supplier_ids: list[UUID],
    product_line_code: Optional[str],
    period: Optional[str],
) -> ComparisonResponse:
    """Return side-by-side comparison of multiple suppliers."""
    period = period or current_period()

    snaps = (await db.execute(
        select(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.supplier_id.in_(supplier_ids))
        .where(SupplyChainRiskSnapshot.snapshot_period == period)
        .where(
            SupplyChainRiskSnapshot.product_line_code == product_line_code
            if product_line_code else
            SupplyChainRiskSnapshot.product_line_code.is_(None)
        )
    )).scalars().all()

    # Fetch supplier names
    from app.models.supplier import Supplier
    sup_result = await db.execute(
        select(Supplier.supplier_id, Supplier.name)
        .where(Supplier.supplier_id.in_(supplier_ids))
    )
    sup_name_map = {sid: name for sid, name in sup_result.all()}

    suppliers = []
    for snap in snaps:
        dimensions = {
            key: DimensionDetail(
                raw_value=val.get("raw_value"),
                risk_index=val.get("risk_index"),
                polarity=val.get("polarity", "higher_is_risk"),
                source=val.get("source", "missing"),
            )
            for key, val in (snap.dimensions or {}).items()
        }
        suppliers.append(ComparisonSupplier(
            supplier_id=snap.supplier_id,
            supplier_name=sup_name_map.get(snap.supplier_id, str(snap.supplier_id)),
            dimensions=dimensions,
        ))

    return ComparisonResponse(period=period, suppliers=suppliers)


async def export_heatmap(
    db: AsyncSession,
    product_line_code: Optional[str],
    period: Optional[str],
    format: str,
) -> StreamingResponse:
    """Export heatmap as CSV or Excel with conditional formatting."""
    heatmap = await get_heatmap_data(db, product_line_code, period)

    if format == "excel":
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "风险热力图"

        # Header
        headers = ["供应商"] + [c.label for c in heatmap.columns] + [c.label + "(来源)" for c in heatmap.columns]
        ws.append(headers)

        # Rows with conditional formatting
        for row in heatmap.rows:
            values = [row.supplier_name]
            sources = [""]
            for cell in row.cells:
                values.append(cell.value if cell.value is not None else "")
                sources.append(cell.source)
            ws.append(values + sources)

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=risk_map_{period}.xlsx"},
        )

    # CSV fallback
    import csv
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)
    headers = ["供应商"] + [c.label for c in heatmap.columns] + [c.label + "(来源)" for c in heatmap.columns]
    writer.writerow(headers)
    for row in heatmap.rows:
        values = [row.supplier_name]
        sources = [""]
        for cell in row.cells:
            values.append(cell.value if cell.value is not None else "")
            sources.append(cell.source)
        writer.writerow(values + sources)

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=risk_map_{period}.csv"},
    )


def _risk_level(score: float | None) -> str | None:
    if score is None:
        return None
    if score <= 30:
        return "low"
    if score <= 60:
        return "medium"
    if score <= 80:
        return "high"
    return "critical"