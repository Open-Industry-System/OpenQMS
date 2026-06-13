import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attribute import AttributeMeasurement, AttributeResult, AttributeStudy
from app.models.audit import AuditLog


async def _generate_study_no(db: AsyncSession) -> str:
    now = datetime.now()
    pattern = f"ATTR-{now.year}"
    result = await db.execute(
        select(func.count()).where(AttributeStudy.study_no.like(f"{pattern}-%"))
    )
    count = result.scalar() or 0
    return f"{pattern}-{count + 1:03d}"


async def list_studies(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    gauge_id: uuid.UUID | None = None,
    factory_id: uuid.UUID | None = None,
    allowed_product_line_codes: list[str] | None = None,
) -> tuple[list[AttributeStudy], int]:
    query = select(AttributeStudy)
    count_query = select(func.count()).select_from(AttributeStudy)
    if status:
        query = query.where(AttributeStudy.status == status)
        count_query = count_query.where(AttributeStudy.status == status)
    if gauge_id:
        query = query.where(AttributeStudy.gauge_id == gauge_id)
        count_query = count_query.where(AttributeStudy.gauge_id == gauge_id)
    if factory_id:
        query = query.where(AttributeStudy.factory_id == factory_id)
        count_query = count_query.where(AttributeStudy.factory_id == factory_id)
    if allowed_product_line_codes:
        query = query.where(AttributeStudy.product_line_code.in_(allowed_product_line_codes))
        count_query = count_query.where(AttributeStudy.product_line_code.in_(allowed_product_line_codes))
    query = query.order_by(AttributeStudy.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    items = (await db.execute(query)).scalars().all()
    total = (await db.execute(count_query)).scalar() or 0
    return list(items), total


async def get_study(db: AsyncSession, study_id: uuid.UUID) -> AttributeStudy | None:
    return await db.get(AttributeStudy, study_id)


async def create_study(
    db: AsyncSession,
    title: str,
    gauge_id: uuid.UUID | None,
    characteristic_name: str,
    user_id: uuid.UUID,
    **kwargs,
) -> AttributeStudy:
    study_no = await _generate_study_no(db)
    study_id = uuid.uuid4()
    study = AttributeStudy(
        study_id=study_id,
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
            table_name="attribute_studies",
            record_id=study_id,
            action="CREATE",
            changed_fields={"study_no": study_no, "title": title},
            operated_by=user_id,
        )
    )
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create attribute study: {e}")
    await db.refresh(study)
    return study


async def update_study(
    db: AsyncSession, study: AttributeStudy, user_id: uuid.UUID, **kwargs
) -> AttributeStudy:
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
            table_name="attribute_studies",
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
        raise ValueError(f"failed to update attribute study: {e}")
    await db.refresh(study)
    return study


async def delete_study(
    db: AsyncSession, study: AttributeStudy, user_id: uuid.UUID
) -> None:
    db.add(
        AuditLog(
            table_name="attribute_studies",
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
        raise ValueError(f"failed to delete attribute study: {e}")


async def upsert_measurements(
    db: AsyncSession, study_id: uuid.UUID, measurements: list[dict]
) -> list[AttributeMeasurement]:
    study = await db.get(AttributeStudy, study_id)
    if not study:
        raise ValueError("attribute study not found")
    if study.status == "completed":
        raise ValueError("study is completed, cannot modify measurements")
    study.status = "ongoing"
    existing = (
        await db.execute(
            select(AttributeMeasurement).where(AttributeMeasurement.study_id == study_id)
        )
    ).scalars().all()
    for m in existing:
        await db.delete(m)
    new_items = []
    for d in measurements:
        new_items.append(
            AttributeMeasurement(
                study_id=study_id,
                appraiser_name=d["appraiser_name"],
                part_no=d["part_no"],
                known_standard=d["known_standard"],
                appraiser_decision=d["appraiser_decision"],
                trial_no=d.get("trial_no", 1),
                factory_id=study.factory_id,
            )
        )
    for item in new_items:
        db.add(item)
    await db.commit()
    return new_items


async def get_measurements(
    db: AsyncSession, study_id: uuid.UUID
) -> list[AttributeMeasurement]:
    result = await db.execute(
        select(AttributeMeasurement)
        .where(AttributeMeasurement.study_id == study_id)
        .order_by(AttributeMeasurement.appraiser_name, AttributeMeasurement.part_no)
    )
    return list(result.scalars().all())


async def get_result(db: AsyncSession, study_id: uuid.UUID) -> AttributeResult | None:
    result = await db.execute(
        select(AttributeResult).where(AttributeResult.study_id == study_id)
    )
    return result.scalar_one_or_none()


async def save_result(db: AsyncSession, result: AttributeResult) -> AttributeResult:
    existing = await get_result(db, result.study_id)
    if existing:
        await db.delete(existing)
        await db.flush()
    db.add(result)
    await db.commit()
    await db.refresh(result)
    return result


async def complete_study(
    db: AsyncSession, study: AttributeStudy, user_id: uuid.UUID, accepted: bool
) -> AttributeStudy:
    if not await get_result(db, study.study_id):
        raise ValueError("Please compute results before completing the study.")
    study.status = "completed"
    study.accepted_by = user_id if accepted else None
    db.add(
        AuditLog(
            table_name="attribute_studies",
            record_id=study.study_id,
            action="TRANSITION",
            changed_fields={"status": "completed"},
            operated_by=user_id,
        )
    )
    await db.commit()
    await db.refresh(study)
    return study
