import uuid
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.bias import BiasStudy, BiasMeasurement, BiasResult
from app.models.audit import AuditLog
from app.services.spc_service import get_spc_measurements_for_msa
from app.services.gauge_service import validate_gauge_for_use


async def _generate_study_no(db: AsyncSession) -> str:
    now = datetime.now()
    pattern = f"BIAS-{now.year}"
    result = await db.execute(
        select(func.count()).where(BiasStudy.study_no.like(f"{pattern}-%"))
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
) -> tuple[list[BiasStudy], int]:
    query = select(BiasStudy)
    count_query = select(func.count()).select_from(BiasStudy)
    if status:
        query = query.where(BiasStudy.status == status)
        count_query = count_query.where(BiasStudy.status == status)
    if gauge_id:
        query = query.where(BiasStudy.gauge_id == gauge_id)
        count_query = count_query.where(BiasStudy.gauge_id == gauge_id)
    if factory_id:
        query = query.where(BiasStudy.factory_id == factory_id)
        count_query = count_query.where(BiasStudy.factory_id == factory_id)
    if allowed_product_line_codes:
        query = query.where(BiasStudy.product_line_code.in_(allowed_product_line_codes))
        count_query = count_query.where(BiasStudy.product_line_code.in_(allowed_product_line_codes))
    query = query.order_by(BiasStudy.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    items = (await db.execute(query)).scalars().all()
    total = (await db.execute(count_query)).scalar() or 0
    return list(items), total


async def get_study(db: AsyncSession, study_id: uuid.UUID) -> BiasStudy | None:
    return await db.get(BiasStudy, study_id)


async def create_study(
    db: AsyncSession,
    title: str,
    gauge_id: uuid.UUID | None,
    characteristic_name: str,
    user_id: uuid.UUID,
    **kwargs,
) -> BiasStudy:
    if gauge_id:
        await validate_gauge_for_use(db, gauge_id)
    study_no = await _generate_study_no(db)
    study_id = uuid.uuid4()
    study = BiasStudy(
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
            table_name="bias_studies",
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
        raise ValueError(f"failed to create bias study: {e}")
    await db.refresh(study)
    return study


async def update_study(
    db: AsyncSession, study: BiasStudy, user_id: uuid.UUID, **kwargs
) -> BiasStudy:
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
            table_name="bias_studies",
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
        raise ValueError(f"failed to update bias study: {e}")
    await db.refresh(study)
    return study


async def delete_study(
    db: AsyncSession, study: BiasStudy, user_id: uuid.UUID
) -> None:
    db.add(
        AuditLog(
            table_name="bias_studies",
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
        raise ValueError(f"failed to delete bias study: {e}")


async def upsert_measurements(
    db: AsyncSession, study_id: uuid.UUID, measurements: list[dict]
) -> list[BiasMeasurement]:
    study = await db.get(BiasStudy, study_id)
    if not study:
        raise ValueError("bias study not found")
    if study.status == "completed":
        raise ValueError("study is completed, cannot modify measurements")
    study.status = "ongoing"
    existing = (
        await db.execute(
            select(BiasMeasurement).where(BiasMeasurement.study_id == study_id)
        )
    ).scalars().all()
    for m in existing:
        await db.delete(m)
    new_items = []
    for d in measurements:
        new_items.append(
            BiasMeasurement(
                study_id=study_id,
                value=d["value"],
                sequence_no=d["sequence_no"],
            )
        )
    for item in new_items:
        db.add(item)
    await db.commit()
    return new_items


async def get_measurements(
    db: AsyncSession, study_id: uuid.UUID
) -> list[BiasMeasurement]:
    result = await db.execute(
        select(BiasMeasurement)
        .where(BiasMeasurement.study_id == study_id)
        .order_by(BiasMeasurement.sequence_no)
    )
    return list(result.scalars().all())


async def get_result(db: AsyncSession, study_id: uuid.UUID) -> BiasResult | None:
    result = await db.execute(
        select(BiasResult).where(BiasResult.study_id == study_id)
    )
    return result.scalar_one_or_none()


async def save_result(db: AsyncSession, result: BiasResult) -> BiasResult:
    existing = await get_result(db, result.study_id)
    if existing:
        await db.delete(existing)
        await db.flush()
    db.add(result)
    await db.commit()
    await db.refresh(result)
    return result


async def complete_study(
    db: AsyncSession, study: BiasStudy, user_id: uuid.UUID, accepted: bool
) -> BiasStudy:
    if not await get_result(db, study.study_id):
        raise ValueError("Please compute results before completing the study.")
    study.status = "completed"
    study.accepted_by = user_id if accepted else None
    db.add(
        AuditLog(
            table_name="bias_studies",
            record_id=study.study_id,
            action="TRANSITION",
            changed_fields={"status": "completed"},
            operated_by=user_id,
        )
    )
    await db.commit()
    await db.refresh(study)
    return study


async def populate_measurements_from_spc(
    db: AsyncSession,
    study_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int | None = None,
) -> list[BiasMeasurement]:
    """Auto-populate bias study measurements from linked SPC characteristic data.

    Uses the study's spc_characteristic_id to extract SampleValue data
    and create BiasMeasurement records. Existing measurements are replaced.
    """
    study = await db.get(BiasStudy, study_id)
    if not study:
        raise ValueError("bias study not found")
    if not study.spc_characteristic_id:
        raise ValueError("study has no linked SPC characteristic")
    if study.status == "completed":
        raise ValueError("study is completed, cannot modify measurements")

    # Extract SPC sample measurements
    spc_data = await get_spc_measurements_for_msa(
        db, study.spc_characteristic_id, limit=limit
    )
    if not spc_data:
        raise ValueError("no SPC sample data found for the linked characteristic")

    # Clear existing measurements
    existing = (
        await db.execute(
            select(BiasMeasurement).where(BiasMeasurement.study_id == study_id)
        )
    ).scalars().all()
    for m in existing:
        await db.delete(m)

    # Create new measurements from SPC data
    new_items = []
    for i, spc_measurement in enumerate(spc_data):
        new_items.append(
            BiasMeasurement(
                study_id=study_id,
                value=spc_measurement["value"],
                sequence_no=i + 1,
            )
        )
    for item in new_items:
        db.add(item)

    study.status = "ongoing"
    db.add(AuditLog(
        table_name="bias_studies",
        record_id=study_id,
        action="POPULATE_FROM_SPC",
        changed_fields={
            "spc_characteristic_id": str(study.spc_characteristic_id),
            "measurement_count": len(new_items),
        },
        operated_by=user_id,
    ))
    await db.commit()
    return new_items
