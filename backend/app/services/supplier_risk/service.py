"""Main service: evaluate supplier risk, handle alerts, create SCAR/CAPA from alerts."""
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier_risk import SupplierRiskAlert
from app.models.supplier import Supplier, SupplierSCAR, SupplierCertification, SupplierEvaluation
from app.models.capa import CAPAEightD
from app.models.iqc_inspection import IqcInspection
from app.services.supplier_risk.rule_engine import SupplierRiskInput, run_all_rules
from app.services.supplier_risk.scorer import calculate_risk_score
from app.services.supplier_risk.config import get_effective_configs, get_effective_configs_batch


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

    # 6. Upsert alert (returns alert + event type)
    alert, event_type = await _upsert_alert(
        db, supplier_id, product_line_code, risk_score, results, failed_ids
    )

    # 7. Commit so the alert is persisted before returning / notifying
    await db.commit()
    if alert:
        await db.refresh(alert)

    # 8. Send notifications ONLY for new or escalated high-risk alerts (non-blocking)
    if alert and event_type in ("new", "escalated") and alert.risk_level in ("high", "critical"):
        from app.services.supplier_risk.notifier import send_notifications
        try:
            await send_notifications(db, alert, product_line_code)
        except Exception:
            logger = __import__("logging").getLogger(__name__)
            logger.exception("Notification failed for alert %s", alert.alert_id)

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
    """Evaluate all active suppliers.

    Uses a batch strategy: one query per data type (IQC, SCAR, Evaluation,
    Certification) to load all relevant records, then groups by supplier in
    Python. Avoids the per-supplier N+1 query pattern.
    """
    # Get all active suppliers
    result = await db.execute(
        select(Supplier).where(Supplier.status == "approved")
    )
    suppliers = list(result.scalars().all())
    if not suppliers:
        return []

    supplier_ids = [s.supplier_id for s in suppliers]

    # Batch load all data types in parallel-friendly queries
    inspections_by_supplier = await _batch_gather_inspections(db, supplier_ids, product_line_code)
    scars_by_supplier = await _batch_gather_scars(db, supplier_ids, product_line_code)
    evaluations_by_supplier = await _batch_gather_evaluations(db, supplier_ids)
    certifications_by_supplier = await _batch_gather_certifications(db, supplier_ids)

    # Batch load effective configs for all suppliers in a single query
    configs_by_supplier = await get_effective_configs_batch(db, supplier_ids, product_line_code)

    results = []
    for supplier in suppliers:
        try:
            configs = configs_by_supplier.get(supplier.supplier_id)
            if not configs:
                continue

            input_data = SupplierRiskInput(
                supplier=supplier,
                inspections=inspections_by_supplier.get(supplier.supplier_id, []),
                scars=scars_by_supplier.get(supplier.supplier_id, []),
                evaluations=evaluations_by_supplier.get(supplier.supplier_id, []),
                certifications=certifications_by_supplier.get(supplier.supplier_id, []),
            )
            rule_results, failed_ids = run_all_rules(input_data, configs)
            risk_score = calculate_risk_score(rule_results, configs)

            alert, event_type = await _upsert_alert(
                db, supplier.supplier_id, product_line_code, risk_score, rule_results, failed_ids
            )

            # Commit per supplier so partial failures don't lose all progress
            await db.commit()
            if alert:
                await db.refresh(alert)

            if alert and event_type in ("new", "escalated") and alert.risk_level in ("high", "critical"):
                from app.services.supplier_risk.notifier import send_notifications
                try:
                    await send_notifications(db, alert, product_line_code)
                except Exception:
                    logger = __import__("logging").getLogger(__name__)
                    logger.exception("Notification failed for alert %s", alert.alert_id)

            results.append({
                "supplier_id": supplier.supplier_id,
                "risk_level": risk_score.risk_level,
                "risk_score": risk_score.risk_score,
                "quality_score": risk_score.quality_score,
                "delivery_score": risk_score.delivery_score,
                "compliance_score": risk_score.compliance_score,
                "rule_results": [
                    {"rule_id": r.rule_id, "triggered": r.triggered, "score": r.score,
                     "detail": r.detail, "category": r.category, "critical": r.critical}
                    for r in rule_results
                ],
                "alert_id": alert.alert_id if alert else None,
            })
        except Exception:
            # Skip suppliers with config/data issues; rollback to avoid dirty session
            await db.rollback()
            continue

    return results


async def calculate_all_supplier_scores(
    db: AsyncSession,
    product_line_code: Optional[str] = None,
) -> list[dict]:
    """Pure scoring — returns risk scores for all approved suppliers without side effects.

    Unlike evaluate_all_suppliers, this function:
    - Does NOT write alerts
    - Does NOT commit
    - Does NOT send notifications
    - Returns scores for every approved supplier (evaluate_all_suppliers scores
      the same set but only upserts alerts for those above threshold)
    """
    result = await db.execute(
        select(Supplier).where(Supplier.status == "approved")
    )
    suppliers = list(result.scalars().all())
    if not suppliers:
        return []

    supplier_ids = [s.supplier_id for s in suppliers]

    inspections_by_supplier = await _batch_gather_inspections(db, supplier_ids, product_line_code)
    scars_by_supplier = await _batch_gather_scars(db, supplier_ids, product_line_code)
    evaluations_by_supplier = await _batch_gather_evaluations(db, supplier_ids)
    certifications_by_supplier = await _batch_gather_certifications(db, supplier_ids)
    configs_by_supplier = await get_effective_configs_batch(db, supplier_ids, product_line_code)

    results = []
    for supplier in suppliers:
        configs = configs_by_supplier.get(supplier.supplier_id)
        if not configs:
            continue
        input_data = SupplierRiskInput(
            supplier=supplier,
            inspections=inspections_by_supplier.get(supplier.supplier_id, []),
            scars=scars_by_supplier.get(supplier.supplier_id, []),
            evaluations=evaluations_by_supplier.get(supplier.supplier_id, []),
            certifications=certifications_by_supplier.get(supplier.supplier_id, []),
        )
        rule_results, _ = run_all_rules(input_data, configs)
        risk_score = calculate_risk_score(rule_results, configs)

        results.append({
            "supplier_id": supplier.supplier_id,
            "supplier_name": supplier.name,
            "risk_level": risk_score.risk_level,
            "risk_score": risk_score.risk_score,
            "quality_score": risk_score.quality_score,
            "delivery_score": risk_score.delivery_score,
            "compliance_score": risk_score.compliance_score,
            "rule_results": [
                {"rule_id": r.rule_id, "triggered": r.triggered, "score": r.score,
                 "detail": r.detail, "category": r.category, "critical": r.critical}
                for r in rule_results
            ],
        })
    return results


# ── Per-supplier gatherers (used by single-supplier evaluation) ────────────────

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


# ── Batch gatherers (used by evaluate_all_suppliers) ───────────────────────────

async def _batch_gather_inspections(db, supplier_ids, product_line_code):
    query = select(IqcInspection).where(IqcInspection.supplier_id.in_(supplier_ids))
    if product_line_code:
        query = query.where(IqcInspection.product_line_code == product_line_code)
    result = await db.execute(query)
    rows = list(result.scalars().all())
    by_supplier = {}
    for r in rows:
        by_supplier.setdefault(r.supplier_id, []).append(r)
    return by_supplier


async def _batch_gather_scars(db, supplier_ids, product_line_code):
    query = select(SupplierSCAR).where(SupplierSCAR.supplier_id.in_(supplier_ids))
    if product_line_code:
        query = query.where(SupplierSCAR.product_line_code == product_line_code)
    result = await db.execute(query)
    rows = list(result.scalars().all())
    by_supplier = {}
    for r in rows:
        by_supplier.setdefault(r.supplier_id, []).append(r)
    return by_supplier


async def _batch_gather_evaluations(db, supplier_ids):
    result = await db.execute(
        select(SupplierEvaluation)
        .where(SupplierEvaluation.supplier_id.in_(supplier_ids))
        .order_by(SupplierEvaluation.created_at.desc())
    )
    rows = list(result.scalars().all())
    by_supplier = {}
    for r in rows:
        by_supplier.setdefault(r.supplier_id, []).append(r)
    return by_supplier


async def _batch_gather_certifications(db, supplier_ids):
    result = await db.execute(
        select(SupplierCertification)
        .where(SupplierCertification.supplier_id.in_(supplier_ids))
    )
    rows = list(result.scalars().all())
    by_supplier = {}
    for r in rows:
        by_supplier.setdefault(r.supplier_id, []).append(r)
    return by_supplier


# ── Alert upsert with event type ───────────────────────────────────────────────

async def _upsert_alert(db, supplier_id, product_line_code, risk_score, results, failed_ids):
    """Upsert alert: dedup by (supplier_id, product_line_code, snapshot_date).

    Returns (alert, event_type) where event_type is:
    - "new": newly created alert
    - "escalated": existing alert risk level increased
    - "unchanged": existing alert, same or lower level (or newly low)
    - None: no alert created (low risk, no existing)
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
        return None, None

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
            await db.flush()
            return existing, "escalated"
        # If same or lower level, skip update
        return existing, "unchanged"

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
    return alert, "new"


# ── Alert state machine ────────────────────────────────────────────────────────

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


async def create_scar_from_alert(
    db: AsyncSession,
    alert_id: uuid.UUID,
    user_id: uuid.UUID,
) -> SupplierSCAR:
    """Create a SCAR from an alert atomically."""
    alert = await db.get(SupplierRiskAlert, alert_id)
    if not alert:
        raise ValueError("预警不存在")

    from app.services.scar_service import _create_scar_without_commit
    from app.services.embedding_outbox import enqueue_embedding

    # Create SCAR without commit
    scar = await _create_scar_without_commit(
        db,
        supplier_id=alert.supplier_id,
        source_type="risk_alert",
        source_id=alert.alert_id,
        description=f"由风险预警 {alert.alert_id} 自动创建",
        issued_by=user_id,
        product_line_code=alert.product_line_code,
    )

    # Link alert to SCAR and update status
    alert.linked_scar_id = scar.scar_id
    alert.status = "action_taken"

    # Commit everything atomically
    await db.commit()
    await db.refresh(scar)
    await db.refresh(alert)

    # Enqueue embedding after commit
    await enqueue_embedding(db, "scar", scar.scar_id, scar.product_line_code)

    return scar


async def create_capa_from_alert(
    db: AsyncSession,
    alert_id: uuid.UUID,
    user_id: uuid.UUID,
) -> CAPAEightD:
    """Create a CAPA from an alert atomically."""
    alert = await db.get(SupplierRiskAlert, alert_id)
    if not alert:
        raise ValueError("预警不存在")

    from app.services.capa_service import _create_capa_without_commit
    from app.services.embedding_outbox import enqueue_embedding
    from app.models.capa import CAPAEightD
    import uuid as _uuid

    # Generate document number
    doc_no = f"8D-{date.today().year}-{str(alert.alert_id)[:8].upper()}"

    # Create CAPA without commit
    capa = await _create_capa_without_commit(
        db,
        title=f"供应商风险预警处置 — {alert.alert_id}",
        document_no=doc_no,
        severity="严重" if alert.risk_level in ("high", "critical") else "一般",
        due_date=date.today(),
        user_id=user_id,
        product_line_code=alert.product_line_code or "DC-DC-100",
        factory_id=alert.factory_id,
    )

    # Link alert to CAPA and update status
    alert.linked_capa_id = capa.report_id
    alert.status = "action_taken"

    # Commit everything atomically
    await db.commit()
    await db.refresh(capa)
    await db.refresh(alert)

    # Enqueue embedding after commit
    await enqueue_embedding(db, "capa", capa.report_id, capa.product_line_code)

    return capa
