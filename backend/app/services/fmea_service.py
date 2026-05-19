import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fmea import FMEADocument
from app.state_machines.fmea_state import FMEAState, can_transition


async def list_fmeas(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[FMEADocument], int]:
    query = select(FMEADocument)
    count_query = select(func.count(FMEADocument.fmea_id))

    if status:
        query = query.where(FMEADocument.status == status)
        count_query = count_query.where(FMEADocument.status == status)

    query = query.order_by(FMEADocument.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return items, total


async def get_fmea(db: AsyncSession, fmea_id: uuid.UUID) -> FMEADocument | None:
    result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
    return result.scalar_one_or_none()


async def create_fmea(
    db: AsyncSession, title: str, document_no: str, fmea_type: str, user_id: uuid.UUID
) -> FMEADocument:
    fmea = FMEADocument(
        title=title,
        document_no=document_no,
        fmea_type=fmea_type,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(fmea)
    await db.commit()
    await db.refresh(fmea)
    return fmea


async def update_fmea(
    db: AsyncSession,
    fmea: FMEADocument,
    title: str | None,
    graph_data: dict | None,
    user_id: uuid.UUID,
) -> FMEADocument:
    if title is not None:
        fmea.title = title
    if graph_data is not None:
        fmea.graph_data = graph_data
    fmea.updated_by = user_id
    await db.commit()
    await db.refresh(fmea)
    return fmea


async def transition_fmea(
    db: AsyncSession,
    fmea: FMEADocument,
    target_status: str,
    user_id: uuid.UUID,
) -> FMEADocument:
    current = FMEAState(fmea.status)
    target = FMEAState(target_status)

    if not can_transition(current, target):
        allowed = [s.value for s in FMEAState if can_transition(current, s)]
        raise ValueError(f"Cannot transition from {fmea.status} to {target_status}. Allowed: {allowed}")

    fmea.status = target_status
    fmea.updated_by = user_id

    if target == FMEAState.APPROVED:
        fmea.approved_by = user_id
        fmea.approved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(fmea)
    return fmea
