import uuid
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.grr import GrrStudy, GrrMeasurement, GrrResult
from app.models.audit import AuditLog


async def _generate_study_no(db: AsyncSession) -> str:
    now = datetime.now()
    pattern = f"GRR-{now.year}"
    result = await db.execute(
        select(func.count()).where(GrrStudy.study_no.like(f"{pattern}-%"))
    )
    count = result.scalar() or 0
    return f"{pattern}-{count + 1:03d}"


async def list_studies(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    gauge_id: uuid.UUID | None = None,
) -> tuple[list[GrrStudy], int]:
    query = select(GrrStudy)
    count_query = select(func.count()).select_from(GrrStudy)
    if status:
        query = query.where(GrrStudy.status == status)
        count_query = count_query.where(GrrStudy.status == status)
    if gauge_id:
        query = query.where(GrrStudy.gauge_id == gauge_id)
        count_query = count_query.where(GrrStudy.gauge_id == gauge_id)
    query = query.order_by(GrrStudy.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    items = (await db.execute(query)).scalars().all()
    total = (await db.execute(count_query)).scalar() or 0
    return list(items), total


async def get_study(db: AsyncSession, study_id: uuid.UUID) -> GrrStudy | None:
    return await db.get(GrrStudy, study_id)


async def create_study(
    db: AsyncSession,
    title: str,
    method: str,
    gauge_id: uuid.UUID | None,
    characteristic_name: str,
    user_id: uuid.UUID,
    **kwargs,
) -> GrrStudy:
    study_no = await _generate_study_no(db)
    study = GrrStudy(
        study_no=study_no,
        title=title,
        method=method,
        gauge_id=gauge_id,
        characteristic_name=characteristic_name,
        created_by=user_id,
        **kwargs,
    )
    db.add(study)
    db.add(
        AuditLog(
            table_name="grr_studies",
            record_id=study.study_id,
            action="CREATE",
            changed_fields={
                "study_no": study_no,
                "title": title,
                "method": method,
            },
            operated_by=user_id,
        )
    )
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create GRR study: {e}")
    await db.refresh(study)
    return study


async def update_study(
    db: AsyncSession, study: GrrStudy, user_id: uuid.UUID, **kwargs
) -> GrrStudy:
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
            table_name="grr_studies",
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
        raise ValueError(f"failed to update GRR study: {e}")
    await db.refresh(study)
    return study


async def delete_study(
    db: AsyncSession, study: GrrStudy, user_id: uuid.UUID
) -> None:
    db.add(
        AuditLog(
            table_name="grr_studies",
            record_id=study.study_id,
            action="DELETE",
            changed_fields={
                "study_no": study.study_no,
                "title": study.title,
            },
            operated_by=user_id,
        )
    )
    await db.delete(study)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to delete GRR study: {e}")


async def upsert_measurements(
    db: AsyncSession, study_id: uuid.UUID, measurements: list[dict]
) -> list[GrrMeasurement]:
    study = await db.get(GrrStudy, study_id)
    if not study:
        raise ValueError("GRR study not found")
    if study.status == "completed":
        raise ValueError("study is completed, cannot modify measurements")
    study.status = "ongoing"
    existing = (
        await db.execute(
            select(GrrMeasurement).where(GrrMeasurement.study_id == study_id)
        )
    ).scalars().all()
    for m in existing:
        await db.delete(m)
    new_items = []
    for d in measurements:
        new_items.append(
            GrrMeasurement(
                study_id=study_id,
                appraiser_name=d["appraiser_name"],
                part_no=d["part_no"],
                trial_no=d["trial_no"],
                value=d["value"],
            )
        )
    for item in new_items:
        db.add(item)
    await db.commit()
    return new_items


async def get_measurements(
    db: AsyncSession, study_id: uuid.UUID
) -> list[GrrMeasurement]:
    result = await db.execute(
        select(GrrMeasurement)
        .where(GrrMeasurement.study_id == study_id)
        .order_by(
            GrrMeasurement.appraiser_name,
            GrrMeasurement.part_no,
            GrrMeasurement.trial_no,
        )
    )
    return list(result.scalars().all())


async def get_result(db: AsyncSession, study_id: uuid.UUID) -> GrrResult | None:
    result = await db.execute(
        select(GrrResult).where(GrrResult.study_id == study_id)
    )
    return result.scalar_one_or_none()


async def save_result(db: AsyncSession, result: GrrResult) -> GrrResult:
    existing = await get_result(db, result.study_id)
    if existing:
        await db.delete(existing)
        await db.flush()
    db.add(result)
    await db.commit()
    await db.refresh(result)
    return result


async def complete_study(
    db: AsyncSession, study: GrrStudy, user_id: uuid.UUID, accepted: bool
) -> GrrStudy:
    if not await get_result(db, study.study_id):
        raise ValueError("Please compute results before completing the study.")
    study.status = "completed"
    study.accepted_by = user_id if accepted else None
    db.add(
        AuditLog(
            table_name="grr_studies",
            record_id=study.study_id,
            action="TRANSITION",
            changed_fields={"status": "completed"},
            operated_by=user_id,
        )
    )
    await db.commit()
    await db.refresh(study)
    return study
