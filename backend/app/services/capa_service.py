import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capa import CAPAEightD
from app.state_machines.eightd_state import EightDState, can_transition


async def list_capas(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[CAPAEightD], int]:
    query = select(CAPAEightD)
    count_query = select(func.count(CAPAEightD.report_id))

    if status:
        query = query.where(CAPAEightD.status == status)
        count_query = count_query.where(CAPAEightD.status == status)

    query = query.order_by(CAPAEightD.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return items, total


async def get_capa(db: AsyncSession, report_id: uuid.UUID) -> CAPAEightD | None:
    result = await db.execute(select(CAPAEightD).where(CAPAEightD.report_id == report_id))
    return result.scalar_one_or_none()


async def create_capa(
    db: AsyncSession,
    title: str,
    document_no: str,
    severity: str,
    due_date,
    user_id: uuid.UUID,
) -> CAPAEightD:
    capa = CAPAEightD(
        title=title,
        document_no=document_no,
        severity=severity,
        due_date=due_date,
        created_by=user_id,
    )
    db.add(capa)
    await db.commit()
    await db.refresh(capa)
    return capa


async def update_capa(
    db: AsyncSession,
    capa: CAPAEightD,
    update_data: dict,
) -> CAPAEightD:
    for key, value in update_data.items():
        if value is not None and hasattr(capa, key):
            setattr(capa, key, value)
    await db.commit()
    await db.refresh(capa)
    return capa


async def advance_capa(
    db: AsyncSession,
    capa: CAPAEightD,
) -> CAPAEightD:
    current = EightDState(capa.status)
    transitions = [
        EightDState.D1_TEAM,
        EightDState.D2_DESCRIPTION,
        EightDState.D3_INTERIM,
        EightDState.D4_ROOT_CAUSE,
        EightDState.D5_CORRECTION,
        EightDState.D6_VERIFICATION,
        EightDState.D7_PREVENTION,
        EightDState.D8_CLOSURE,
        EightDState.ARCHIVED,
    ]

    if current in transitions:
        idx = transitions.index(current)
        next_state = transitions[idx + 1] if idx + 1 < len(transitions) else EightDState.ARCHIVED
    else:
        raise ValueError(f"Cannot advance from {capa.status}")

    if not can_transition(current, next_state):
        raise ValueError(f"Cannot transition from {capa.status} to {next_state.value}")

    capa.status = next_state.value
    await db.commit()
    await db.refresh(capa)
    return capa


async def link_fmea(
    db: AsyncSession,
    capa: CAPAEightD,
    fmea_ref_id: uuid.UUID,
) -> CAPAEightD:
    capa.fmea_ref_id = fmea_ref_id
    await db.commit()
    await db.refresh(capa)
    return capa
