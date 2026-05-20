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

    from sqlalchemy import text

    rpn_stats_query = text("""
        SELECT 
            COALESCE(SUM(COALESCE((node->>'severity')::int, 0) * COALESCE((node->>'occurrence')::int, 0) * COALESCE((node->>'detection')::int, 0)), 0) AS total_rpn,
            COUNT(node) FILTER (WHERE (node->>'severity')::int > 0 AND (node->>'occurrence')::int > 0 AND (node->>'detection')::int > 0) AS rpn_count,
            COUNT(node) FILTER (WHERE COALESCE((node->>'severity')::int, 0) * COALESCE((node->>'occurrence')::int, 0) * COALESCE((node->>'detection')::int, 0) >= 100) AS high_rpn_count
        FROM fmea_documents,
        LATERAL jsonb_array_elements(
            CASE 
                WHEN jsonb_typeof(graph_data->'nodes') = 'array' THEN graph_data->'nodes'
                ELSE '[]'::jsonb
            END
        ) AS node
        WHERE node->>'type' = 'FailureMode';
    """)
    stats_result = await db.execute(rpn_stats_query)
    stats = stats_result.fetchone()

    total_rpn = stats[0] if stats else 0
    rpn_count = stats[1] if stats else 0
    high_rpn_count = stats[2] if stats else 0

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
