import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.gauge import Gauge, GaugeCalibration


async def _generate_gauge_no(db: AsyncSession) -> str:
    result = await db.execute(
        select(func.count()).select_from(Gauge).where(Gauge.gauge_no.like("Q-%"))
    )
    count = result.scalar() or 0
    return f"Q-{count + 1:03d}"


async def list_gauges(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    department: str | None = None,
    search: str | None = None,
    expiring_days: int | None = None,
    factory_id: uuid.UUID | None = None,
) -> tuple[list[Gauge], int]:
    query = select(Gauge)
    count_query = select(func.count()).select_from(Gauge)

    if factory_id:
        query = query.where(Gauge.factory_id == factory_id)
        count_query = count_query.where(Gauge.factory_id == factory_id)

    if status:
        query = query.where(Gauge.status == status)
        count_query = count_query.where(Gauge.status == status)
    if department:
        query = query.where(Gauge.department == department)
        count_query = count_query.where(Gauge.department == department)
    if search:
        pattern = f"%{search}%"
        search_filter = (
            Gauge.name.like(pattern)
            | Gauge.gauge_no.like(pattern)
            | Gauge.model.like(pattern)
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
    if expiring_days:
        today = date.today()
        cutoff = today + timedelta(days=expiring_days)
        query = query.where(
            Gauge.next_calibration_date >= today,
            Gauge.next_calibration_date <= cutoff,
        )
        count_query = count_query.where(
            Gauge.next_calibration_date >= today,
            Gauge.next_calibration_date <= cutoff,
        )

    query = query.order_by(Gauge.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    items = (await db.execute(query)).scalars().all()
    total = (await db.execute(count_query)).scalar() or 0
    return list(items), total


async def get_gauge(db: AsyncSession, gauge_id: uuid.UUID) -> Gauge | None:
    return await db.get(Gauge, gauge_id)


async def create_gauge(
    db: AsyncSession,
    gauge_no: str | None,
    name: str,
    model: str | None,
    manufacturer: str | None,
    resolution: float | None,
    measuring_range: str | None,
    department: str | None,
    location: str | None,
    calibration_cycle_days: int | None,
    next_calibration_date: date | None,
    user_id: uuid.UUID,
    factory_id: uuid.UUID | None = None,
) -> Gauge:
    if not gauge_no:
        gauge_no = await _generate_gauge_no(db)
    gauge_id = uuid.uuid4()
    gauge = Gauge(
        gauge_id=gauge_id,
        gauge_no=gauge_no,
        name=name,
        model=model,
        manufacturer=manufacturer,
        resolution=resolution,
        measuring_range=measuring_range,
        department=department,
        location=location,
        calibration_cycle_days=calibration_cycle_days,
        next_calibration_date=next_calibration_date,
        created_by=user_id,
        factory_id=factory_id,
    )
    db.add(gauge)
    db.add(
        AuditLog(
            table_name="gauges",
            record_id=gauge_id,
            action="CREATE",
            changed_fields={
                "gauge_no": gauge_no,
                "name": name,
                "model": model,
            },
            operated_by=user_id,
        )
    )
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create gauge: {e}")
    await db.refresh(gauge)
    return gauge


async def update_gauge(
    db: AsyncSession, gauge: Gauge, user_id: uuid.UUID, **kwargs
) -> Gauge:
    changed = {}
    for key, new_val in kwargs.items():
        if key in ("user_id",):
            continue
        old_val = getattr(gauge, key, None)
        if new_val is not None and new_val != old_val:
            changed[key] = {
                "before": str(old_val) if old_val is not None else None,
                "after": str(new_val) if new_val is not None else None,
            }
            setattr(gauge, key, new_val)
    if not changed:
        return gauge
    db.add(
        AuditLog(
            table_name="gauges",
            record_id=gauge.gauge_id,
            action="UPDATE",
            changed_fields=changed,
            operated_by=user_id,
        )
    )
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to update gauge: {e}")
    await db.refresh(gauge)
    return gauge


async def delete_gauge(
    db: AsyncSession, gauge: Gauge, user_id: uuid.UUID
) -> None:
    db.add(
        AuditLog(
            table_name="gauges",
            record_id=gauge.gauge_id,
            action="DELETE",
            changed_fields={"gauge_no": gauge.gauge_no, "name": gauge.name},
            operated_by=user_id,
        )
    )
    await db.delete(gauge)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to delete gauge: {e}")


async def list_calibrations(
    db: AsyncSession, gauge_id: uuid.UUID
) -> list[GaugeCalibration]:
    result = await db.execute(
        select(GaugeCalibration)
        .where(GaugeCalibration.gauge_id == gauge_id)
        .order_by(GaugeCalibration.calibration_date.desc())
    )
    return list(result.scalars().all())


async def create_calibration(
    db: AsyncSession,
    gauge_id: uuid.UUID,
    calibration_date: date,
    result: str,
    certificate_no: str | None,
    calibrated_by: str | None,
    notes: str | None,
    next_calibration_date: date | None,
    user_id: uuid.UUID,
) -> GaugeCalibration:
    calibration_id = uuid.uuid4()
    cal = GaugeCalibration(
        calibration_id=calibration_id,
        gauge_id=gauge_id,
        calibration_date=calibration_date,
        result=result,
        certificate_no=certificate_no,
        calibrated_by=calibrated_by,
        notes=notes,
        next_calibration_date=next_calibration_date,
    )
    db.add(cal)
    db.add(
        AuditLog(
            table_name="gauge_calibrations",
            record_id=calibration_id,
            action="CREATE",
            changed_fields={
                "gauge_id": str(gauge_id),
                "calibration_date": calibration_date.isoformat(),
                "result": result,
            },
            operated_by=user_id,
        )
    )
    if next_calibration_date:
        gauge = await db.get(Gauge, gauge_id)
        if gauge:
            gauge.next_calibration_date = next_calibration_date
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create calibration: {e}")
    await db.refresh(cal)
    return cal



async def validate_gauge_for_use(db: AsyncSession, gauge_id: uuid.UUID) -> Gauge:
    """Validate that a gauge is active and within calibration date for use in inspections/SPC/CP.
    
    Raises ValueError if gauge is inactive, calibrating, or past calibration date.
    """
    gauge = await db.get(Gauge, gauge_id)
    if gauge is None:
        raise ValueError(f"量具 {gauge_id} 不存在")
    if gauge.status != "active":
        raise ValueError(f"量具 '{gauge.name}' ({gauge.gauge_no}) 当前状态为 '{gauge.status}'，不可用于检验。仅 'active' 状态量具可用。")
    if gauge.next_calibration_date and gauge.next_calibration_date < date.today():
        raise ValueError(f"量具 '{gauge.name}' ({gauge.gauge_no}) 校准已过期 (到期日: {gauge.next_calibration_date.isoformat()})，请先完成校准。")
    return gauge
