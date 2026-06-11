"""Main service: evaluate supplier risk, handle alerts, create SCAR/CAPA from alerts."""
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier_risk import SupplierRiskAlert
from app.models.supplier import Supplier, SupplierSCAR, SupplierCertification, SupplierEvaluation
from app.models.iqc_inspection import IqcInspection
from app.services.supplier_risk.rule_engine import SupplierRiskInput, run_all_rules
from app.services.supplier_risk.scorer import calculate_risk_score
from app.services.supplier_risk.config import get_effective_configs


async def evaluate_supplier_risk(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    product_line_code: Optional[str] = None,
) -> dict:
    """Evaluate a single supplier's risk and upsert alert."""

    # 1. Get supplier
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise ValueError("供应商不存在")

    # 2. Get effective configs
    configs = await get_effective_configs(db, product_line_code, supplier_id)
    if not configs:
        raise ValueError("无有效的风险规则配置")

    # 3. Gather data
    inspections = await _gather_inspections(db, supplier_id, product_line_code)
    scars = await _gather_scars(db, supplier_id, product_line_code)
    evaluations = await _gather_evaluations(db, supplier_id)
    certifications = await _gather_certifications(db, supplier_id)

    # 4. Build input and run rules
    input_data = SupplierRiskInput(
        supplier=supplier,
        inspections=inspections,
        scars=scars,
        evaluations=evaluations,
        certifications=certifications,
    )
    results, failed_ids = run_all_rules(input_data, configs)

    # 5. Calculate score
    risk_score = calculate_risk_score(results, configs)

    # 6. Upsert alert
    alert = await _upsert_alert(
        db, supplier_id, product_line_code, risk_score, results, failed_ids
    )

    return {
        "supplier_id": supplier_id,
        "risk_level": risk_score.risk_level,
        "risk_score": risk_score.risk_score,
        "quality_score": risk_score.quality_score,
        "delivery_score": risk_score.delivery_score,
        "compliance_score": risk_score.compliance_score,
        "rule_results": [
            {"rule_id": r.rule_id, "triggered": r.triggered, "score": r.score,
             "detail": r.detail, "category": r.category, "critical": r.critical}
            for r in results
        ],
        "alert_id": alert.alert_id if alert else None,
    }


async def evaluate_all_suppliers(
    db: AsyncSession,
    product_line_code: Optional[str] = None,
) -> list[dict]:
    """Evaluate all active suppliers. Uses batch aggregate query, not N+1."""
    # Get all active suppliers
    result = await db.execute(
        select(Supplier).where(Supplier.status == "approved")
    )
    suppliers = list(result.scalars().all())

    results = []
    for supplier in suppliers:
        try:
            eval_result = await evaluate_supplier_risk(db, supplier.supplier_id, product_line_code)
            results.append(eval_result)
        except Exception:
            # Skip suppliers with config/data issues
            continue

    return results


async def _gather_inspections(db, supplier_id, product_line_code):
    """Gather IQC inspections for supplier, optionally filtered by product line."""
    query = select(IqcInspection).where(IqcInspection.supplier_id == supplier_id)
    if product_line_code:
        query = query.where(IqcInspection.product_line_code == product_line_code)
    query = query.order_by(IqcInspection.inspection_date.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def _gather_scars(db, supplier_id, product_line_code):
    """Gather SCARs for supplier, optionally filtered by product line."""
    query = select(SupplierSCAR).where(SupplierSCAR.supplier_id == supplier_id)
    if product_line_code:
        query = query.where(SupplierSCAR.product_line_code == product_line_code)
    query = query.order_by(SupplierSCAR.issued_date.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def _gather_evaluations(db, supplier_id):
    """Gather evaluations for supplier (global, no product_line_code filter)."""
    result = await db.execute(
        select(SupplierEvaluation)
        .where(SupplierEvaluation.supplier_id == supplier_id)
        .order_by(SupplierEvaluation.created_at.desc())
    )
    return list(result.scalars().all())


async def _gather_certifications(db, supplier_id):
    """Gather certifications for supplier (global, no product_line_code filter)."""
    result = await db.execute(
        select(SupplierCertification)
        .where(SupplierCertification.supplier_id == supplier_id)
    )
    return list(result.scalars().all())


async def _upsert_alert(db, supplier_id, product_line_code, risk_score, results, failed_ids):
    """Upsert alert: dedup by (supplier_id, product_line_code, snapshot_date).

    - If existing alert and new risk_level > existing → update scores, set alert_type="escalated"
    - If existing alert and new risk_level <= existing → skip (no update)
    - If no existing alert and risk_level != "low" → insert new alert
    """
    today = date.today()

    # Find existing alert for today
    query = select(SupplierRiskAlert).where(
        SupplierRiskAlert.supplier_id == supplier_id,
        SupplierRiskAlert.snapshot_date == today,
    )
    if product_line_code:
        query = query.where(SupplierRiskAlert.product_line_code == product_line_code)
    else:
        query = query.where(SupplierRiskAlert.product_line_code.is_(None))

    result = await db.execute(query)
    existing = result.scalar_one_or_none()

    # Build rule_results JSON
    rule_results_data = [
        {"rule_id": r.rule_id, "triggered": r.triggered, "score": r.score,
         "detail": r.detail, "category": r.category, "critical": r.critical}
        for r in results
    ]

    # Don't create alerts for low-risk suppliers
    if risk_score.risk_level == "low" and not existing:
        return None

    if existing:
        # Check if risk level escalated
        level_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        if level_order.get(risk_score.risk_level, 0) > level_order.get(existing.risk_level, 0):
            existing.risk_level = risk_score.risk_level
            existing.risk_score = risk_score.risk_score
            existing.quality_score = risk_score.quality_score
            existing.delivery_score = risk_score.delivery_score
            existing.compliance_score = risk_score.compliance_score
            existing.rule_results = rule_results_data
            existing.alert_type = "escalated"
            # updated_at handled by SQLAlchemy onupdate
            await db.flush()
        # If same or lower level, skip update
        return existing

    # Create new alert
    alert = SupplierRiskAlert(
        supplier_id=supplier_id,
        risk_level=risk_score.risk_level,
        risk_score=risk_score.risk_score,
        quality_score=risk_score.quality_score,
        delivery_score=risk_score.delivery_score,
        compliance_score=risk_score.compliance_score,
        rule_results=rule_results_data,
        alert_type="initial",
        status="open",
        snapshot_date=today,
        product_line_code=product_line_code,
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return alert


async def handle_alert(
    db: AsyncSession,
    alert_id: uuid.UUID,
    action: str,
    note: Optional[str],
    user_id: uuid.UUID,
) -> SupplierRiskAlert:
    """Handle an alert with state machine transitions.

    Actions:
    - "acknowledge": open -> acknowledged
    - "ignore": open -> ignored (requires note)
    - "close": acknowledged/action_taken -> closed
    """
    alert = await db.get(SupplierRiskAlert, alert_id)
    if not alert:
        raise ValueError("预警不存在")

    if action == "acknowledge":
        if alert.status != "open":
            raise ValueError("只能确认开放状态的预警")
        alert.status = "acknowledged"
    elif action == "ignore":
        if alert.status != "open":
            raise ValueError("只能忽略开放状态的预警")
        if not note or not note.strip():
            raise ValueError("忽略预警需填写理由")
        alert.status = "ignored"
        alert.handle_note = note.strip()
    elif action == "close":
        if alert.status not in ("acknowledged", "action_taken"):
            raise ValueError("只能关闭已确认或已处置的预警")
        alert.status = "closed"
    else:
        raise ValueError(f"无效的操作: {action}")

    alert.handled_by = user_id
    alert.handled_at = func.now()

    await db.commit()
    await db.refresh(alert)
    return alert
