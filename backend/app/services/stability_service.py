import uuid
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.stability import StabilityStudy, StabilityMeasurement, StabilityResult
from app.models.audit import AuditLog


async def _generate_study_no(db: AsyncSession) -> str:
    now = datetime.now()
    pattern = f"STB-{now.year}"
    result = await db.execute(
        select(func.count()).where(StabilityStudy.study_no.like(f"{pattern}-%"))
    )
    count = result.scalar() or 0
    return f"{pattern}-{count + 1:03d}"


async def list_studies(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    gauge_id: uuid.UUID | None = None,
) -> tuple[list[StabilityStudy], int]:
    query = select(StabilityStudy)
    count_query = select(func.count()).select_from(StabilityStudy)
    if status:
        query = query.where(StabilityStudy.status == status)
        count_query = count_query.where(StabilityStudy.status == status)
    if gauge_id:
        query = query.where(StabilityStudy.gauge_id == gauge_id)
        count_query = count_query.where(StabilityStudy.gauge_id == gauge_id)
    query = query.order_by(StabilityStudy.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    items = (await db.execute(query)).scalars().all()
    total = (await db.execute(count_query)).scalar() or 0
    return list(items), total


async def get_study(db: AsyncSession, study_id: uuid.UUID) -> StabilityStudy | None:
    return await db.get(StabilityStudy, study_id)


async def create_study(
    db: AsyncSession,
    title: str,
    gauge_id: uuid.UUID | None,
    characteristic_name: str,
    user_id: uuid.UUID,
    **kwargs,
) -> StabilityStudy:
    study_no = await _generate_study_no(db)
    study = StabilityStudy(
        study_no=study_no,
        title=title,
        gauge_id=gauge_id,
        characteristic_name=characteristic_name,
        created_by=user_id,
        **kwargs,
    )
    db.add(study)
    db.add(
        AuditLog(
            table_name="stability_studies",
            record_id=study.study_id,
            action="CREATE",
            changed_fields={"study_no": study_no, "title": title},
            operated_by=user_id,
        )
    )
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create stability study: {e}")
    await db.refresh(study)
    return study


async def update_study(
    db: AsyncSession, study: StabilityStudy, user_id: uuid.UUID, **kwargs
) -> StabilityStudy:
    changed = {}
    for key, new_val in kwargs.items():
        if key in ("user_id",):
            continue
        old_val = getattr(study, key, None)
        if new_val is not None and new_val != old_val:
            changed[key] = {
                "before": str(old_val) if old_val is not None else None,
                "after": str(new_val) if new_val is not None else None,
            }
            setattr(study, key, new_val)
    if not changed:
        return study
    db.add(
        AuditLog(
            table_name="stability_studies",
            record_id=study.study_id,
            action="UPDATE",
            changed_fields=changed,
            operated_by=user_id,
        )
    )
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to update stability study: {e}")
    await db.refresh(study)
    return study


async def delete_study(
    db: AsyncSession, study: StabilityStudy, user_id: uuid.UUID
) -> None:
    db.add(
        AuditLog(
            table_name="stability_studies",
            record_id=study.study_id,
            action="DELETE",
            changed_fields={"study_no": study.study_no, "title": study.title},
            operated_by=user_id,
        )
    )
    await db.delete(study)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to delete stability study: {e}")


async def upsert_measurements(
    db: AsyncSession, study_id: uuid.UUID, measurements: list[dict]
) -> list[StabilityMeasurement]:
    study = await db.get(StabilityStudy, study_id)
    if not study:
        raise ValueError("stability study not found")
    if study.status == "completed":
        raise ValueError("study is completed, cannot modify measurements")
    study.status = "ongoing"
    existing = (
        await db.execute(
            select(StabilityMeasurement).where(StabilityMeasurement.study_id == study_id)
        )
    ).scalars().all()
    for m in existing:
        await db.delete(m)
    new_items = []
    for d in measurements:
        new_items.append(
            StabilityMeasurement(
                study_id=study_id,
                measurement_date=d["measurement_date"],
                sample_mean=d["sample_mean"],
                sample_range=d["sample_range"],
                sequence_no=d["sequence_no"],
            )
        )
    for item in new_items:
        db.add(item)
    await db.commit()
    return new_items


async def get_measurements(
    db: AsyncSession, study_id: uuid.UUID
) -> list[StabilityMeasurement]:
    result = await db.execute(
        select(StabilityMeasurement)
        .where(StabilityMeasurement.study_id == study_id)
        .order_by(StabilityMeasurement.sequence_no)
    )
    return list(result.scalars().all())


async def get_result(db: AsyncSession, study_id: uuid.UUID) -> StabilityResult | None:
    result = await db.execute(
        select(StabilityResult).where(StabilityResult.study_id == study_id)
    )
    return result.scalar_one_or_none()


async def save_result(db: AsyncSession, result: StabilityResult) -> StabilityResult:
    existing = await get_result(db, result.study_id)
    if existing:
        await db.delete(existing)
        await db.flush()
    db.add(result)
    await db.commit()
    await db.refresh(result)
    return result


async def complete_study(
    db: AsyncSession, study: StabilityStudy, user_id: uuid.UUID, accepted: bool
) -> StabilityStudy:
    if not await get_result(db, study.study_id):
        raise ValueError("Please compute results before completing the study.")
    study.status = "completed"
    study.accepted_by = user_id if accepted else None
    db.add(
        AuditLog(
            table_name="stability_studies",
            record_id=study.study_id,
            action="TRANSITION",
            changed_fields={"status": "completed"},
            operated_by=user_id,
        )
    )
    await db.commit()
    await db.refresh(study)
    return study
