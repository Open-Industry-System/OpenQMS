"""Write ADOPT_RECOMMENDATION audit logs, idempotent by recommendation_id."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.schemas.fmea import RecommendationAdoption


async def write_adoption_audits(
    db: AsyncSession,
    fmea_id: uuid.UUID,
    adoptions: list[RecommendationAdoption],
    user_id: uuid.UUID,
) -> int:
    if not adoptions:
        return 0
    existing = (await db.execute(
        select(AuditLog.changed_fields["recommendation_id"].astext).where(
            AuditLog.table_name == "fmea_documents",
            AuditLog.action == "ADOPT_RECOMMENDATION",
            AuditLog.record_id == fmea_id,
        )
    )).scalars().all()
    seen = set(existing)
    written = 0
    for a in adoptions:
        if a.recommendation_id in seen:
            continue
        seen.add(a.recommendation_id)
        db.add(AuditLog(
            table_name="fmea_documents",
            record_id=fmea_id,
            action="ADOPT_RECOMMENDATION",
            changed_fields={
                "field_id": a.field_id,
                "recommendation_id": a.recommendation_id,
                "source": a.source,
                "stage_index": a.stage_index,
                "adopted_text": a.adopted_text,
            },
            operated_by=user_id,
        ))
        written += 1
    return written
