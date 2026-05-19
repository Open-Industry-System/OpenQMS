from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD


async def get_dashboard(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)

    total_fmea = await db.scalar(select(func.count(FMEADocument.fmea_id)))
    approved_fmea = await db.scalar(
        select(func.count(FMEADocument.fmea_id)).where(FMEADocument.status == "approved")
    )

    total_capa = await db.scalar(select(func.count(CAPAEightD.report_id)))
    open_capa = await db.scalar(
        select(func.count(CAPAEightD.report_id)).where(
            CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"])
        )
    )

    overdue_capa = await db.scalar(
        select(func.count(CAPAEightD.report_id)).where(
            CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]),
            CAPAEightD.due_date < now.date(),
        )
    )

    fmeas = await db.execute(select(FMEADocument.graph_data))
    total_rpn = 0
    rpn_count = 0
    high_rpn_count = 0
    for (graph_data,) in fmeas:
        for node in graph_data.get("nodes", []):
            if node.get("type") == "FailureMode":
                s = node.get("severity", 0)
                o = node.get("occurrence", 0)
                d = node.get("detection", 0)
                if s and o and d:
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
