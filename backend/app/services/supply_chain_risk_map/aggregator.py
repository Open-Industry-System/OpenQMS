"""Supply-chain risk map aggregation service.

Gathers ERP delivery, purchase-amount, IQC PPM, and SCAR metrics
for a set of suppliers in a given period, then normalises each
dimension to a 0-100 risk index.
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

def _parse_period(period: str) -> tuple[date, date]:
    """Convert ``"YYYY-MM"`` to ``(period_start, period_end)``."""
    year, month = map(int, period.split("-"))
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


# ---------------------------------------------------------------------------
# Main aggregation
# ---------------------------------------------------------------------------

async def aggregate_supply_chain_metrics(
    db: AsyncSession,
    supplier_ids: list[UUID],
    product_line_code: Optional[str],
    period: str,
) -> dict[UUID, dict]:
    """Return per-supplier metrics for the given period.

    Returns a dict mapping each *supplier_id* to a metrics dict with keys:
    ``erp_on_time_rate``, ``erp_on_time_rate_source``,
    ``purchase_amount_pct``, ``delivery_delay_days``,
    ``open_scar_count``, ``ppm_value``, ``ppm_source``.
    """
    period_start, period_end = _parse_period(period)
    result: dict[UUID, dict] = {
        sid: {
            "erp_on_time_rate": None,
            "erp_on_time_rate_source": None,
            "purchase_amount_pct": None,
            "delivery_delay_days": None,
            "open_scar_count": 0,
            "ppm_value": None,
            "ppm_source": None,
        }
        for sid in supplier_ids
    }

    await _query_erp_on_time(db, supplier_ids, product_line_code, period_start, period_end, result)
    await _query_purchase_amount_pct(db, supplier_ids, product_line_code, period_start, period_end, result)
    await _query_delivery_delay(db, supplier_ids, product_line_code, period_start, period_end, result)
    await _query_scar_count(db, supplier_ids, period_end, result)
    await _query_ppm(db, supplier_ids, product_line_code, period_start, period_end, result)

    return result


# ---------------------------------------------------------------------------
# ERP on-time delivery rate
# ---------------------------------------------------------------------------

async def _query_erp_on_time(
    db: AsyncSession,
    supplier_ids: list[UUID],
    product_line_code: Optional[str],
    period_start: date,
    period_end: date,
    result: dict[UUID, dict],
) -> None:
    """Compute on-time delivery rate from ERP POs; fall back to evaluation score."""

    # --- Try ERP PO data first ---
    pl_filter = "AND po.product_line_code = :pl_code" if product_line_code else ""
    params: dict = {
        "period_start": period_start,
        "period_end": period_end,
        "sids": [str(s) for s in supplier_ids],
    }
    if product_line_code:
        params["pl_code"] = product_line_code

    query = text(f"""
        SELECT
            s.supplier_id,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE po.actual_delivery_date <= po.delivery_date) AS on_time,
            AVG(
                (po.actual_delivery_date - po.delivery_date)
            ) FILTER (
                WHERE po.actual_delivery_date > po.delivery_date
            ) AS avg_delay_days
        FROM erp_purchase_orders po
        JOIN erp_suppliers es ON po.supplier_code = es.supplier_code
        JOIN suppliers s ON es.openqms_supplier_id = s.supplier_id
        WHERE s.supplier_id = ANY(:sids)
          AND po.delivery_date BETWEEN :period_start AND :period_end
          AND po.actual_delivery_date IS NOT NULL
          AND po.delivery_date IS NOT NULL
          {pl_filter}
        GROUP BY s.supplier_id
    """)

    rows = (await db.execute(query, params)).mappings().all()
    erp_hit: set[UUID] = set()

    for row in rows:
        sid = row["supplier_id"]
        total = row["total"]
        on_time = row["on_time"]
        result[sid]["erp_on_time_rate"] = round(on_time / total * 100, 2) if total else None
        result[sid]["erp_on_time_rate_source"] = "erp_po"
        # avg_delay_days is an interval; extract days
        delay = row["avg_delay_days"]
        result[sid]["delivery_delay_days"] = float(delay.days) if delay is not None and hasattr(delay, "days") else (float(delay) if delay is not None else None)
        erp_hit.add(sid)

    # --- Fallback: supplier_evaluations.delivery_score ---
    missing = [s for s in supplier_ids if s not in erp_hit]
    if missing:
        eval_query = text("""
            SELECT supplier_id, delivery_score
            FROM supplier_evaluations
            WHERE supplier_id = ANY(:sids)
              AND eval_period = :period
            ORDER BY created_at DESC
        """)
        eval_rows = (await db.execute(eval_query, {"sids": [str(s) for s in missing], "period": period_start.strftime("%Y-%m")})).mappings().all()
        seen: set[UUID] = set()
        for row in eval_rows:
            sid = row["supplier_id"]
            if sid not in seen:
                result[sid]["erp_on_time_rate"] = row["delivery_score"]
                result[sid]["erp_on_time_rate_source"] = "supplier_evaluation_fallback"
                seen.add(sid)


# ---------------------------------------------------------------------------
# Purchase amount percentage (window function)
# ---------------------------------------------------------------------------

async def _query_purchase_amount_pct(
    db: AsyncSession,
    supplier_ids: list[UUID],
    product_line_code: Optional[str],
    period_start: date,
    period_end: date,
    result: dict[UUID, dict],
) -> None:
    pl_filter = "AND po.product_line_code = :pl_code" if product_line_code else ""
    params: dict = {
        "period_start": period_start,
        "period_end": period_end,
        "sids": [str(s) for s in supplier_ids],
    }
    if product_line_code:
        params["pl_code"] = product_line_code

    query = text(f"""
        SELECT
            s.supplier_id,
            SUM(po.quantity * po.unit_price) AS supplier_amount,
            SUM(SUM(po.quantity * po.unit_price)) OVER () AS total_amount
        FROM erp_purchase_orders po
        JOIN erp_suppliers es ON po.supplier_code = es.supplier_code
        JOIN suppliers s ON es.openqms_supplier_id = s.supplier_id
        WHERE s.supplier_id = ANY(:sids)
          AND po.delivery_date BETWEEN :period_start AND :period_end
          {pl_filter}
        GROUP BY s.supplier_id
    """)

    rows = (await db.execute(query, params)).mappings().all()
    for row in rows:
        sid = row["supplier_id"]
        total = row["total_amount"]
        supplier_amt = row["supplier_amount"]
        if total and total > 0:
            result[sid]["purchase_amount_pct"] = round(float(supplier_amt) / float(total) * 100, 2)


# ---------------------------------------------------------------------------
# Delivery delay days (late POs only) — populated inside _query_erp_on_time
# ---------------------------------------------------------------------------

async def _query_delivery_delay(
    db: AsyncSession,
    supplier_ids: list[UUID],
    product_line_code: Optional[str],
    period_start: date,
    period_end: date,
    result: dict[UUID, dict],
) -> None:
    """Delivery delay is already extracted in _query_erp_on_time (avg_delay_days)."""
    # No-op: delay days are computed alongside on-time rate above.
    pass


# ---------------------------------------------------------------------------
# Open SCAR count (time-point logic)
# ---------------------------------------------------------------------------

async def _query_scar_count(
    db: AsyncSession,
    supplier_ids: list[UUID],
    period_end: date,
    result: dict[UUID, dict],
) -> None:
    query = text("""
        SELECT supplier_id, COUNT(*) AS cnt
        FROM supplier_scars
        WHERE supplier_id = ANY(:sids)
          AND issued_date <= :period_end
          AND (closed_date IS NULL OR closed_date > :period_end)
        GROUP BY supplier_id
    """)
    rows = (await db.execute(query, {"sids": [str(s) for s in supplier_ids], "period_end": period_end})).mappings().all()
    for row in rows:
        result[row["supplier_id"]]["open_scar_count"] = row["cnt"]


# ---------------------------------------------------------------------------
# PPM from IQC inspections
# ---------------------------------------------------------------------------

async def _query_ppm(
    db: AsyncSession,
    supplier_ids: list[UUID],
    product_line_code: Optional[str],
    period_start: date,
    period_end: date,
    result: dict[UUID, dict],
) -> None:
    pl_filter = "AND product_line_code = :pl_code" if product_line_code else ""
    params: dict = {
        "period_start": period_start,
        "period_end": period_end,
        "sids": [str(s) for s in supplier_ids],
    }
    if product_line_code:
        params["pl_code"] = product_line_code

    query = text(f"""
        SELECT
            supplier_id,
            SUM(defect_qty) AS total_defect,
            SUM(lot_qty) AS total_lot
        FROM iqc_inspections
        WHERE supplier_id = ANY(:sids)
          AND inspection_date BETWEEN :period_start AND :period_end
          {pl_filter}
        GROUP BY supplier_id
    """)
    rows = (await db.execute(query, params)).mappings().all()
    for row in rows:
        sid = row["supplier_id"]
        total_lot = row["total_lot"]
        total_defect = row["total_defect"]
        if total_lot and total_lot > 0:
            result[sid]["ppm_value"] = round(float(total_defect) / float(total_lot) * 1_000_000, 2)
            result[sid]["ppm_source"] = "iqc_inspection"


# ---------------------------------------------------------------------------
# Pure normalisation functions
# ---------------------------------------------------------------------------

def normalize_to_risk_index(dimensions: dict) -> dict:
    """Normalise raw metric values to 0-100 risk indices.

    *dimensions* maps a dimension name to a dict with keys
    ``raw_value``, ``polarity``, and ``source``.

    Polarity rules:
      - ``higher_is_risk``  → risk_index = raw_value
      - ``lower_is_risk``   → risk_index = 100 - raw_value
      - ``neutral_exposure`` → risk_index = raw_value

    If ``raw_value`` is ``None``, ``risk_index`` is also ``None``.
    """
    out: dict = {}
    for name, dim in dimensions.items():
        raw = dim.get("raw_value")
        polarity = dim.get("polarity", "higher_is_risk")
        source = dim.get("source")
        if raw is None:
            out[name] = {"raw_value": None, "polarity": polarity, "source": source, "risk_index": None}
            continue
        if polarity == "lower_is_risk":
            ri = 100 - raw
        else:  # higher_is_risk or neutral_exposure
            ri = raw
        out[name] = {"raw_value": raw, "polarity": polarity, "source": source, "risk_index": ri}
    return out


def ppm_to_risk_index(ppm: float) -> float:
    """Linear mapping: ppm / 50, capped at 100.

    * 0 ppm  → 0
    * 500 ppm → 10
    * 5 000 ppm → 100
    * 10 000 ppm → 100 (capped)
    """
    return min(100.0, ppm / 50.0)