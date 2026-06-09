from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD


DEFAULT_LAYOUT = {
    "lg": [
        {"i": "kpi-pending", "type": "kpi_pending_actions", "x": 0, "y": 0, "w": 3, "h": 2},
        {"i": "kpi-overdue", "type": "kpi_overdue_tasks", "x": 3, "y": 0, "w": 3, "h": 2},
        {"i": "kpi-risk", "type": "kpi_high_risk_items", "x": 6, "y": 0, "w": 3, "h": 2},
        {"i": "kpi-trend", "type": "kpi_month_trend", "x": 9, "y": 0, "w": 3, "h": 2},
        {"i": "alert-fmea", "type": "alert_high_rpn_fmea", "x": 0, "y": 2, "w": 4, "h": 4},
        {"i": "alert-capa", "type": "alert_overdue_capa", "x": 4, "y": 2, "w": 4, "h": 4},
        {"i": "alert-ppm", "type": "alert_high_ppm_suppliers", "x": 8, "y": 2, "w": 4, "h": 4},
        {"i": "recent-actions", "type": "recent_actions", "x": 0, "y": 6, "w": 12, "h": 3},
    ]
}

WIDGET_MODULE_MAP = {
    "kpi_pending_actions": "dashboard",
    "kpi_overdue_tasks": "dashboard",
    "kpi_high_risk_items": "dashboard",
    "kpi_month_trend": "dashboard",
    "alert_high_rpn_fmea": "fmea",
    "alert_overdue_capa": "capa",
    "alert_high_ppm_suppliers": "supplier",
    "recent_actions": "dashboard",
    "spc_abnormal_count": "spc",
    "spc_capability_summary": "spc",
    "msa_gauge_expiry": "msa",
    "iqc_pending_inspections": "iqc",
    "mes_equipment_status": "mes",
    "supplier_ppm_trend": "supplier",
    "quality_trend_ai_summary": "dashboard",
}

WIDGET_MIN_SIZES = {
    "kpi_pending_actions": {"w": 2, "h": 2},
    "kpi_overdue_tasks": {"w": 2, "h": 2},
    "kpi_high_risk_items": {"w": 2, "h": 2},
    "kpi_month_trend": {"w": 2, "h": 2},
    "alert_high_rpn_fmea": {"w": 3, "h": 3},
    "alert_overdue_capa": {"w": 3, "h": 3},
    "alert_high_ppm_suppliers": {"w": 3, "h": 3},
    "recent_actions": {"w": 6, "h": 2},
    "spc_abnormal_count": {"w": 2, "h": 2},
    "spc_capability_summary": {"w": 3, "h": 3},
    "msa_gauge_expiry": {"w": 2, "h": 2},
    "iqc_pending_inspections": {"w": 2, "h": 2},
    "mes_equipment_status": {"w": 3, "h": 2},
    "supplier_ppm_trend": {"w": 3, "h": 3},
    "quality_trend_ai_summary": {"w": 6, "h": 4},
}


async def _user_can_view_module(user, module: str, db: AsyncSession) -> bool:
    from app.core.permissions import Module, PermissionLevel, get_user_permission

    level = await get_user_permission(user, Module(module), db)
    return level >= PermissionLevel.VIEW


async def filter_layout_by_permissions(layout: dict, user, db: AsyncSession) -> dict:
    filtered_layout = dict(layout or {})
    widgets = []
    for item in (layout or {}).get("lg", []):
        module = WIDGET_MODULE_MAP.get(item.get("type", ""), "dashboard")
        if await _user_can_view_module(user, module, db):
            widgets.append(dict(item))
    filtered_layout["lg"] = widgets
    return filtered_layout


async def get_default_layout(db: AsyncSession, user) -> dict:
    return await filter_layout_by_permissions(DEFAULT_LAYOUT, user, db)


async def get_dashboard(db: AsyncSession, product_line: str | None = None, product_line_codes: list[str] | None = None) -> dict:
    now = datetime.now(timezone.utc)

    # Resolve effective product line codes
    if product_line_codes is not None:
        codes = product_line_codes
    elif product_line is not None:
        codes = [product_line]
    else:
        codes = None

    fmea_base = select(func.count(FMEADocument.fmea_id))
    capa_base = select(func.count(CAPAEightD.report_id))

    if codes:
        fmea_base = fmea_base.where(FMEADocument.product_line_code.in_(codes))
        capa_base = capa_base.where(CAPAEightD.product_line_code.in_(codes))

    total_fmea = await db.scalar(fmea_base)
    approved_fmea = await db.scalar(
        fmea_base.where(FMEADocument.status == "approved")
    )

    total_capa = await db.scalar(capa_base)
    open_capa = await db.scalar(
        capa_base.where(CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]))
    )

    overdue_capa = await db.scalar(
        capa_base.where(
            CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]),
            CAPAEightD.due_date < now.date(),
        )
    )

    from app.utils.fmea_graph import build_rpn_rows

    # 获取所有FMEA文档的graph_data，在Python中遍历edges计算RPN
    fmea_query = select(FMEADocument.fmea_id, FMEADocument.graph_data)
    if codes:
        fmea_query = fmea_query.where(FMEADocument.product_line_code.in_(codes))
    result = await db.execute(fmea_query)
    all_docs = result.all()

    total_rpn = 0
    rpn_count = 0
    high_rpn_count = 0

    for _doc_id, graph_data in all_docs:
        if not graph_data:
            continue
        nodes = graph_data.get("nodes", []) if isinstance(graph_data, dict) else []
        edges = graph_data.get("edges", []) if isinstance(graph_data, dict) else []
        rows = build_rpn_rows(nodes, edges)
        for row in rows:
            s = row.get("severity", 0)
            o = row.get("occurrence", 0)
            d = row.get("detection", 0)
            if s > 0 and o > 0 and d > 0:
                rpn = s * o * d
                total_rpn += rpn
                rpn_count += 1
                if rpn >= 100:
                    high_rpn_count += 1

    avg_rpn = round(total_rpn / rpn_count) if rpn_count > 0 else 0

    from app.models.special_characteristic import SpecialCharacteristic
    from app.models.management_review import ManagementReview, ReviewOutput

    sc_base = select(func.count(SpecialCharacteristic.sc_id))
    if codes:
        sc_base = sc_base.where(SpecialCharacteristic.product_line_code.in_(codes))

    total_safety = await db.scalar(
        sc_base.where(SpecialCharacteristic.is_safety_related == True)
    )
    pending_safety_approval = await db.scalar(
        sc_base.where(SpecialCharacteristic.safety_approval_status == "submitted")
    )
    safety_suggestions = await db.scalar(
        sc_base.where(SpecialCharacteristic.is_safety_suggested == True)
    )

    # Management review stats
    mr_base = select(func.count(ManagementReview.review_id))
    if codes:
        mr_base = mr_base.where(ManagementReview.product_line_code.in_(codes))

    total_reviews = await db.scalar(mr_base) or 0
    closed_reviews = await db.scalar(
        mr_base.where(ManagementReview.status == "closed")
    ) or 0

    output_base = select(func.count(ReviewOutput.output_id)).join(
        ManagementReview, ReviewOutput.review_id == ManagementReview.review_id
    )
    if codes:
        output_base = output_base.where(
            ManagementReview.product_line_code.in_(codes)
        )

    total_outputs = await db.scalar(output_base) or 0
    verified_outputs = await db.scalar(
        output_base.where(ReviewOutput.status == "verified")
    ) or 0
    pending_verification = await db.scalar(
        output_base.where(ReviewOutput.status == "completed")
    ) or 0

    return {
        "kpi": {
            "total_fmea": total_fmea or 0,
            "approved_fmea": approved_fmea or 0,
            "total_capa": total_capa or 0,
            "open_capa": open_capa or 0,
            "overdue_capa": overdue_capa or 0,
            "avg_rpn": avg_rpn,
            "high_rpn_count": high_rpn_count,
            "total_safety": total_safety or 0,
            "pending_safety_approval": pending_safety_approval or 0,
            "safety_suggestions": safety_suggestions or 0,
            "management_review": {
                "total_reviews": total_reviews,
                "closed_reviews": closed_reviews,
                "total_outputs": total_outputs,
                "verified_outputs": verified_outputs,
                "pending_verification": pending_verification,
                "completion_rate": round(verified_outputs / total_outputs, 3) if total_outputs > 0 else 0,
            },
        },
        "trends": {
            "fmea_by_status": {},
            "capa_by_status": {
                "open": open_capa or 0,
                "closed": (total_capa or 0) - (open_capa or 0),
            },
        },
        "alerts": [],
    }


async def get_summary(db: AsyncSession, product_line: str | None = None, product_line_codes: list[str] | None = None) -> dict:
    now = datetime.now(timezone.utc)

    # Resolve effective product line codes
    if product_line_codes is not None:
        codes = product_line_codes
    elif product_line is not None:
        codes = [product_line]
    else:
        codes = None

    fmea_pending = select(func.count(FMEADocument.fmea_id)).where(
        FMEADocument.status.in_(["draft", "in_review"])
    )
    if codes:
        fmea_pending = fmea_pending.where(FMEADocument.product_line_code.in_(codes))
    fmea_pending_count = await db.scalar(fmea_pending) or 0

    capa_pending = select(func.count(CAPAEightD.report_id)).where(
        CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"])
    )
    if codes:
        capa_pending = capa_pending.where(CAPAEightD.product_line_code.in_(codes))
    capa_pending_count = await db.scalar(capa_pending) or 0

    from app.models.customer_quality import CustomerComplaint

    complaint_pending = select(func.count(CustomerComplaint.complaint_id)).where(
        CustomerComplaint.status == "open"
    )
    if codes:
        complaint_pending = complaint_pending.where(
            CustomerComplaint.product_line_code.in_(codes)
        )
    complaint_pending_count = await db.scalar(complaint_pending) or 0

    pending_actions = fmea_pending_count + capa_pending_count + complaint_pending_count

    overdue_capa_q = select(func.count(CAPAEightD.report_id)).where(
        CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]),
        CAPAEightD.due_date < now.date(),
    )
    if codes:
        overdue_capa_q = overdue_capa_q.where(CAPAEightD.product_line_code.in_(codes))
    overdue_tasks = await db.scalar(overdue_capa_q) or 0

    from app.utils.fmea_graph import build_rpn_rows

    fmea_query = select(FMEADocument.fmea_id, FMEADocument.graph_data)
    if codes:
        fmea_query = fmea_query.where(FMEADocument.product_line_code.in_(codes))
    result = await db.execute(fmea_query)
    all_docs = result.all()

    high_risk_items = 0
    for _doc_id, graph_data in all_docs:
        if not graph_data:
            continue
        nodes = graph_data.get("nodes", []) if isinstance(graph_data, dict) else []
        edges = graph_data.get("edges", []) if isinstance(graph_data, dict) else []
        rows = build_rpn_rows(nodes, edges)
        for row in rows:
            s = row.get("severity", 0)
            o = row.get("occurrence", 0)
            d = row.get("detection", 0)
            if s > 0 and o > 0 and d > 0:
                rpn = s * o * d
                if rpn >= 100:
                    high_risk_items += 1

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

    this_month = select(func.count(FMEADocument.fmea_id)).where(
        FMEADocument.created_at >= month_start
    )
    last_month = select(func.count(FMEADocument.fmea_id)).where(
        FMEADocument.created_at >= prev_month_start,
        FMEADocument.created_at < month_start,
    )
    if codes:
        this_month = this_month.where(FMEADocument.product_line_code.in_(codes))
        last_month = last_month.where(FMEADocument.product_line_code.in_(codes))

    this_count = await db.scalar(this_month) or 0
    last_count = await db.scalar(last_month) or 0

    return {
        "pending_actions": pending_actions,
        "overdue_tasks": overdue_tasks,
        "high_risk_items": high_risk_items,
        "month_trend": this_count - last_count,
    }


async def get_alerts(db: AsyncSession, product_line: str | None = None, product_line_codes: list[str] | None = None) -> dict:
    from app.utils.fmea_graph import build_rpn_rows
    from app.models.supplier import Supplier

    now = datetime.now(timezone.utc)

    # Resolve effective product line codes
    if product_line_codes is not None:
        codes = product_line_codes
    elif product_line is not None:
        codes = [product_line]
    else:
        codes = None

    fmea_query = select(FMEADocument.fmea_id, FMEADocument.document_no, FMEADocument.graph_data)
    if codes:
        fmea_query = fmea_query.where(FMEADocument.product_line_code.in_(codes))
    result = await db.execute(fmea_query)
    all_docs = result.all()

    high_rpn_items = []
    for doc_id, doc_no, graph_data in all_docs:
        if not graph_data:
            continue
        nodes = graph_data.get("nodes", []) if isinstance(graph_data, dict) else []
        edges = graph_data.get("edges", []) if isinstance(graph_data, dict) else []
        rows = build_rpn_rows(nodes, edges)
        for row in rows:
            s = row.get("severity", 0)
            o = row.get("occurrence", 0)
            d = row.get("detection", 0)
            if s > 0 and o > 0 and d > 0:
                rpn = s * o * d
                if rpn >= 100:
                    high_rpn_items.append({
                        "fmea_id": str(doc_id),
                        "document_no": doc_no,
                        "node_name": row.get("failure_mode", ""),
                        "rpn": rpn,
                    })

    high_rpn_items.sort(key=lambda x: x["rpn"], reverse=True)
    high_rpn_items = high_rpn_items[:5]

    capa_query = (
        select(CAPAEightD.report_id, CAPAEightD.document_no, CAPAEightD.due_date)
        .where(
            CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]),
            CAPAEightD.due_date < now.date(),
        )
        .order_by(CAPAEightD.due_date)
        .limit(5)
    )
    if codes:
        capa_query = capa_query.where(CAPAEightD.product_line_code.in_(codes))
    capa_result = await db.execute(capa_query)
    overdue_capas = [
        {
            "report_id": str(row.report_id),
            "document_no": row.document_no,
            "overdue_days": (now.date() - row.due_date).days,
        }
        for row in capa_result.all()
    ]

    from app.models.customer_quality import Customer
    from app.models.iqc_inspection import IqcInspection

    ppm_target_q = select(func.min(Customer.ppm_target))
    ppm_threshold = await db.scalar(ppm_target_q) or 500.0
    if ppm_threshold is None or ppm_threshold <= 0:
        ppm_threshold = 500.0

    ppm_query = (
        select(
            IqcInspection.supplier_id,
            func.sum(IqcInspection.defect_qty).label("total_defects"),
            func.sum(IqcInspection.lot_qty).label("total_lots"),
        )
        .where(IqcInspection.supplier_id.isnot(None))
        .group_by(IqcInspection.supplier_id)
    )
    if codes:
        ppm_query = ppm_query.where(IqcInspection.product_line_code.in_(codes))
    ppm_result = await db.execute(ppm_query)

    high_ppm_suppliers = []
    for row in ppm_result.all():
        if row.total_lots and row.total_lots > 0:
            ppm = (row.total_defects / row.total_lots) * 1_000_000
            if ppm > ppm_threshold:
                supp = await db.get(Supplier, row.supplier_id)
                if supp:
                    high_ppm_suppliers.append({
                        "supplier_id": str(row.supplier_id),
                        "supplier_name": supp.name,
                        "ppm": round(ppm, 1),
                    })

    high_ppm_suppliers.sort(key=lambda x: x["ppm"], reverse=True)
    high_ppm_suppliers = high_ppm_suppliers[:5]

    return {
        "high_rpn_fmeas": high_rpn_items,
        "overdue_capas": overdue_capas,
        "high_ppm_suppliers": high_ppm_suppliers,
    }


async def get_recent_actions(db: AsyncSession, user_id: str, limit: int = 5) -> list[dict]:
    from app.models.audit import AuditLog

    query = (
        select(AuditLog)
        .where(AuditLog.operated_by == user_id)
        .where(AuditLog.action != "AI_TREND_INTERPRET")
        .where(AuditLog.table_name != "quality_trends")
        .order_by(AuditLog.operated_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    logs = result.scalars().all()

    actions = []
    for log in logs:
        entity_no = ""
        if log.table_name == "fmea_documents":
            q = select(FMEADocument.document_no).where(FMEADocument.fmea_id == log.record_id)
            entity_no = await db.scalar(q) or ""
        elif log.table_name == "capa_eightd":
            q = select(CAPAEightD.document_no).where(CAPAEightD.report_id == log.record_id)
            entity_no = await db.scalar(q) or ""

        actions.append({
            "record_id": str(log.record_id),
            "table_name": log.table_name,
            "entity_no": entity_no,
            "action": log.action,
            "operated_at": log.operated_at.isoformat(),
        })

    return actions


async def get_widgets_data(
    db: AsyncSession,
    types: list[str],
    product_line_codes: list[str] | None,
    user_id: str,
) -> dict:
    result = {
        "kpi": {},
        "alerts": {},
        "recent_actions": [],
        "spc": {},
        "msa": {},
        "iqc": {},
        "mes": {},
        "supplier": {},
        "errors": {},
    }

    needs_kpi = any(widget_type.startswith("kpi_") for widget_type in types)
    needs_alerts = any(widget_type.startswith("alert_") for widget_type in types)
    needs_recent = "recent_actions" in types
    needs_spc = any(widget_type.startswith("spc_") for widget_type in types)
    needs_msa = any(widget_type.startswith("msa_") for widget_type in types)
    needs_iqc = any(widget_type.startswith("iqc_") for widget_type in types)
    needs_mes = any(widget_type.startswith("mes_") for widget_type in types)
    needs_supplier = any(widget_type.startswith("supplier_") for widget_type in types)

    if needs_kpi:
        try:
            summary = await get_summary(db, product_line_codes=product_line_codes)
            result["kpi"] = {
                "pending_actions": summary.get("pending_actions", 0),
                "overdue_tasks": summary.get("overdue_tasks", 0),
                "high_risk_items": summary.get("high_risk_items", 0),
                "month_trend": summary.get("month_trend", 0),
            }
        except Exception as e:
            result["errors"]["kpi"] = str(e)

    if needs_alerts:
        try:
            alerts = await get_alerts(db, product_line_codes=product_line_codes)
            alert_payload_map = {
                "alert_high_rpn_fmea": "high_rpn_fmeas",
                "alert_overdue_capa": "overdue_capas",
                "alert_high_ppm_suppliers": "high_ppm_suppliers",
            }
            result["alerts"] = {
                payload_key: alerts.get(payload_key, [])
                for widget_type, payload_key in alert_payload_map.items()
                if widget_type in types
            }
        except Exception as e:
            result["errors"]["alerts"] = str(e)

    if needs_recent:
        try:
            result["recent_actions"] = await get_recent_actions(db, user_id)
        except Exception as e:
            result["errors"]["recent_actions"] = str(e)

    if needs_spc:
        try:
            from app.models.spc import InspectionCharacteristic, SPCAlarm

            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            abnormal_q = select(func.count(SPCAlarm.alarm_id)).where(
                SPCAlarm.status == "open",
                SPCAlarm.triggered_at >= week_ago,
            )
            if product_line_codes:
                abnormal_q = abnormal_q.join(
                    InspectionCharacteristic,
                    SPCAlarm.ic_id == InspectionCharacteristic.ic_id,
                ).where(InspectionCharacteristic.product_line.in_(product_line_codes))
            abnormal_count = await db.scalar(abnormal_q) or 0

            ic_q = select(func.count(InspectionCharacteristic.ic_id))
            if product_line_codes:
                ic_q = ic_q.where(InspectionCharacteristic.product_line.in_(product_line_codes))
            ic_count = await db.scalar(ic_q) or 0

            result["spc"] = {
                "abnormal_count": abnormal_count,
                "capability_summary": {"count": ic_count, "cpk_avg": None},
            }
        except Exception as e:
            result["errors"]["spc"] = str(e)

    if needs_msa:
        try:
            from app.models.gauge import Gauge

            expiry_date = datetime.now(timezone.utc).date() + timedelta(days=30)
            expiry_q = select(func.count(Gauge.gauge_id)).where(
                Gauge.status == "active",
                Gauge.next_calibration_date.isnot(None),
                Gauge.next_calibration_date <= expiry_date,
            )
            if product_line_codes:
                expiry_q = expiry_q.where(Gauge.product_line_code.in_(product_line_codes))
            result["msa"] = {"gauges_expiring_30d": await db.scalar(expiry_q) or 0}
        except Exception as e:
            result["errors"]["msa"] = str(e)

    if needs_iqc:
        try:
            from app.models.iqc_inspection import IqcInspection

            pending_q = select(func.count(IqcInspection.inspection_id)).where(
                IqcInspection.status == "pending"
            )
            if product_line_codes:
                pending_q = pending_q.where(IqcInspection.product_line_code.in_(product_line_codes))
            result["iqc"] = {"pending_inspections": await db.scalar(pending_q) or 0}
        except Exception as e:
            result["errors"]["iqc"] = str(e)

    if needs_mes:
        try:
            from app.models.mes import MESEquipmentStatus

            latest_status_q = select(
                MESEquipmentStatus.status,
                func.row_number().over(
                    partition_by=[MESEquipmentStatus.connection_id, MESEquipmentStatus.equipment_code],
                    order_by=MESEquipmentStatus.recorded_at.desc(),
                ).label("rn"),
            )
            if product_line_codes:
                latest_status_q = latest_status_q.where(MESEquipmentStatus.product_line_code.in_(product_line_codes))

            latest_status_subq = latest_status_q.subquery()
            status_q = (
                select(latest_status_subq.c.status, func.count())
                .where(latest_status_subq.c.rn == 1)
                .group_by(latest_status_subq.c.status)
            )
            status_rows = (await db.execute(status_q)).all()
            status_counts = {row[0]: row[1] for row in status_rows}

            result["mes"] = {
                "equipment_running": status_counts.get("running", 0),
                "equipment_down": status_counts.get("down", 0),
                "equipment_idle": status_counts.get("idle", 0),
                "status_counts": status_counts,
            }
        except Exception as e:
            result["errors"]["mes"] = str(e)

    if needs_supplier:
        try:
            from app.models.iqc_inspection import IqcInspection
            from app.models.supplier import Supplier

            total_lots = func.sum(IqcInspection.lot_qty)
            total_defects = func.sum(IqcInspection.defect_qty)
            ppm_expr = (total_defects * 1_000_000.0) / func.nullif(total_lots, 0)
            ppm_q = (
                select(
                    IqcInspection.supplier_id,
                    total_defects.label("defects"),
                    total_lots.label("lots"),
                    ppm_expr.label("ppm"),
                )
                .where(IqcInspection.supplier_id.isnot(None))
                .group_by(IqcInspection.supplier_id)
                .having(total_lots > 0)
                .order_by(ppm_expr.desc())
                .limit(5)
            )
            if product_line_codes:
                ppm_q = ppm_q.where(IqcInspection.product_line_code.in_(product_line_codes))

            ppm_rows = (await db.execute(ppm_q)).all()
            ppm_trend = []
            for row in ppm_rows:
                supplier = await db.get(Supplier, row.supplier_id)
                ppm_trend.append({
                    "supplier_id": str(row.supplier_id),
                    "supplier_name": supplier.name if supplier else "Unknown",
                    "ppm": round(float(row.ppm or 0), 1),
                })
            result["supplier"] = {"ppm_trend": ppm_trend}
        except Exception as e:
            result["errors"]["supplier"] = str(e)

    return result
