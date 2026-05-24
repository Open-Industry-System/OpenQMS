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

    return {
        "kpi": {
            "total_fmea": total_fmea or 0,
            "approved_fmea": approved_fmea or 0,
            "total_capa": total_capa or 0,
            "open_capa": open_capa or 0,
            "overdue_capa": overdue_capa or 0,
            "avg_rpn": avg_rpn,
            "high_rpn_count": high_rpn_count,
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
