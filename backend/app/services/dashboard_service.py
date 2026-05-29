from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD


async def get_dashboard(db: AsyncSession, product_line: str | None = None) -> dict:
    now = datetime.now(timezone.utc)

    fmea_base = select(func.count(FMEADocument.fmea_id))
    capa_base = select(func.count(CAPAEightD.report_id))

    if product_line:
        fmea_base = fmea_base.where(FMEADocument.product_line_code == product_line)
        capa_base = capa_base.where(CAPAEightD.product_line_code == product_line)

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
    if product_line:
        fmea_query = fmea_query.where(FMEADocument.product_line_code == product_line)
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
    if product_line:
        sc_base = sc_base.where(SpecialCharacteristic.product_line_code == product_line)

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
    if product_line:
        mr_base = mr_base.where(ManagementReview.product_line_code == product_line)

    total_reviews = await db.scalar(mr_base) or 0
    closed_reviews = await db.scalar(
        mr_base.where(ManagementReview.status == "closed")
    ) or 0

    output_base = select(func.count(ReviewOutput.output_id)).join(
        ManagementReview, ReviewOutput.review_id == ManagementReview.review_id
    )
    if product_line:
        output_base = output_base.where(
            ManagementReview.product_line_code == product_line
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


async def get_summary(db: AsyncSession, product_line: str | None = None) -> dict:
    now = datetime.now(timezone.utc)

    fmea_pending = select(func.count(FMEADocument.fmea_id)).where(
        FMEADocument.status.in_(["draft", "in_review"])
    )
    if product_line:
        fmea_pending = fmea_pending.where(FMEADocument.product_line_code == product_line)
    fmea_pending_count = await db.scalar(fmea_pending) or 0

    capa_pending = select(func.count(CAPAEightD.report_id)).where(
        CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"])
    )
    if product_line:
        capa_pending = capa_pending.where(CAPAEightD.product_line_code == product_line)
    capa_pending_count = await db.scalar(capa_pending) or 0

    from app.models.customer_quality import CustomerComplaint

    complaint_pending = select(func.count(CustomerComplaint.complaint_id)).where(
        CustomerComplaint.status == "open"
    )
    if product_line:
        complaint_pending = complaint_pending.where(
            CustomerComplaint.product_line_code == product_line
        )
    complaint_pending_count = await db.scalar(complaint_pending) or 0

    pending_actions = fmea_pending_count + capa_pending_count + complaint_pending_count

    overdue_capa_q = select(func.count(CAPAEightD.report_id)).where(
        CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]),
        CAPAEightD.due_date < now.date(),
    )
    if product_line:
        overdue_capa_q = overdue_capa_q.where(CAPAEightD.product_line_code == product_line)
    overdue_tasks = await db.scalar(overdue_capa_q) or 0

    from app.utils.fmea_graph import build_rpn_rows

    fmea_query = select(FMEADocument.fmea_id, FMEADocument.graph_data)
    if product_line:
        fmea_query = fmea_query.where(FMEADocument.product_line_code == product_line)
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
    if product_line:
        this_month = this_month.where(FMEADocument.product_line_code == product_line)
        last_month = last_month.where(FMEADocument.product_line_code == product_line)

    this_count = await db.scalar(this_month) or 0
    last_count = await db.scalar(last_month) or 0

    return {
        "pending_actions": pending_actions,
        "overdue_tasks": overdue_tasks,
        "high_risk_items": high_risk_items,
        "month_trend": this_count - last_count,
    }


async def get_alerts(db: AsyncSession, product_line: str | None = None) -> dict:
    from app.utils.fmea_graph import build_rpn_rows
    from app.models.supplier import Supplier

    now = datetime.now(timezone.utc)

    fmea_query = select(FMEADocument.fmea_id, FMEADocument.document_no, FMEADocument.graph_data)
    if product_line:
        fmea_query = fmea_query.where(FMEADocument.product_line_code == product_line)
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
    if product_line:
        capa_query = capa_query.where(CAPAEightD.product_line_code == product_line)
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
    if product_line:
        ppm_query = ppm_query.where(IqcInspection.product_line_code == product_line)
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
