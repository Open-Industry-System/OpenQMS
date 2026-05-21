import uuid
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.spc import (
    InspectionCharacteristic, SampleBatch, SampleValue,
    SPCAlarm, ControlLimitSnapshot, DEFAULT_RULES_CONFIG,
)
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.services.spc_calculation_engine import (
    calculate_xbar_r_limits, calculate_imr_limits,
    evaluate_western_electric, calculate_cp_cpk,
    calculate_pp_ppk, calculate_cm, calculate_ppm,
    get_capability_grade, get_capability_advice,
)


async def _create_audit_log(
    db: AsyncSession, user_id: uuid.UUID, action: str, table_name: str,
    record_id: uuid.UUID, changed_fields: Optional[dict] = None
) -> None:
    db.add(AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        changed_fields=changed_fields or {},
        operated_by=user_id,
    ))
    await db.commit()


async def create_inspection_characteristic(
    db: AsyncSession, user_id: uuid.UUID, data: dict
) -> InspectionCharacteristic:
    product_line = data.get("product_line", "DC-DC-100")
    process_name = data["process_name"]
    characteristic_name = data["characteristic_name"]
    ic_code = f"{product_line}-{process_name}-{characteristic_name}"

    # Check uniqueness
    existing = await db.execute(
        select(InspectionCharacteristic).where(InspectionCharacteristic.ic_code == ic_code)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"Inspection characteristic with code '{ic_code}' already exists")

    rules_config = data.get("rules_config")
    if rules_config:
        merged = dict(DEFAULT_RULES_CONFIG)
        merged.update(rules_config)
        rules_config = merged
    else:
        rules_config = dict(DEFAULT_RULES_CONFIG)

    ic = InspectionCharacteristic(
        ic_code=ic_code,
        product_line=product_line,
        process_name=process_name,
        characteristic_name=characteristic_name,
        spec_upper=data["spec_upper"],
        spec_lower=data["spec_lower"],
        target_value=data.get("target_value"),
        chart_type=data["chart_type"],
        subgroup_size=data.get("subgroup_size", 5),
        rules_config=rules_config,
        created_by_id=user_id,
    )
    db.add(ic)
    await db.commit()
    await db.refresh(ic)

    await _create_audit_log(
        db, user_id, "CREATE", "inspection_characteristics", ic.ic_id,
        {"ic_code": ic_code, "chart_type": data["chart_type"]}
    )
    return ic


async def list_inspection_characteristics(
    db: AsyncSession, page: int = 1, page_size: int = 20,
    product_line: Optional[str] = None, process_name: Optional[str] = None,
) -> Tuple[List[InspectionCharacteristic], int]:
    query = select(InspectionCharacteristic)
    count_query = select(func.count(InspectionCharacteristic.ic_id))

    filters = []
    if product_line:
        filters.append(InspectionCharacteristic.product_line == product_line)
    if process_name:
        filters.append(InspectionCharacteristic.process_name.ilike(f"%{process_name}%"))

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
        .order_by(InspectionCharacteristic.created_at.desc())
    )
    items = result.scalars().all()
    return list(items), total


async def get_inspection_characteristic(db: AsyncSession, ic_id: uuid.UUID) -> Optional[InspectionCharacteristic]:
    result = await db.execute(
        select(InspectionCharacteristic).where(InspectionCharacteristic.ic_id == ic_id)
    )
    return result.scalar_one_or_none()


async def update_inspection_characteristic(
    db: AsyncSession, user_id: uuid.UUID, ic_id: uuid.UUID, data: dict
) -> InspectionCharacteristic:
    ic = await get_inspection_characteristic(db, ic_id)
    if not ic:
        raise ValueError("Inspection characteristic not found")

    changed = {}
    for field in ["process_name", "characteristic_name", "spec_upper", "spec_lower",
                  "target_value", "chart_type", "subgroup_size", "control_limits_locked"]:
        if field in data and data[field] is not None:
            old = getattr(ic, field)
            new = data[field]
            if old != new:
                changed[field] = {"before": str(old) if old is not None else None, "after": str(new)}
                setattr(ic, field, new)

    if "rules_config" in data and data["rules_config"] is not None:
        merged = dict(ic.rules_config)
        merged.update(data["rules_config"])
        changed["rules_config"] = {"before": ic.rules_config, "after": merged}
        ic.rules_config = merged

    # Handle process_name / characteristic_name change -> regenerate ic_code
    if "process_name" in data and data["process_name"] is not None:
        new_code = f"{ic.product_line}-{ic.process_name}-{ic.characteristic_name}"
        if new_code != ic.ic_code:
            existing = await db.execute(
                select(InspectionCharacteristic).where(InspectionCharacteristic.ic_code == new_code)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Inspection characteristic with code '{new_code}' already exists")
            changed["ic_code"] = {"before": ic.ic_code, "after": new_code}
            ic.ic_code = new_code

    await db.commit()
    await db.refresh(ic)

    if changed:
        await _create_audit_log(
            db, user_id, "UPDATE", "inspection_characteristics", ic_id, changed
        )
    return ic


async def delete_inspection_characteristic(db: AsyncSession, user_id: uuid.UUID, ic_id: uuid.UUID) -> None:
    ic = await get_inspection_characteristic(db, ic_id)
    if not ic:
        raise ValueError("Inspection characteristic not found")

    await _create_audit_log(
        db, user_id, "DELETE", "inspection_characteristics", ic_id,
        {"ic_code": ic.ic_code}
    )
    await db.delete(ic)
    await db.commit()


async def lock_unlock_control_limits(
    db: AsyncSession, user_id: uuid.UUID, ic_id: uuid.UUID,
    locked: bool
) -> InspectionCharacteristic:
    ic = await get_inspection_characteristic(db, ic_id)
    if not ic:
        raise ValueError("Inspection characteristic not found")

    old_state = ic.control_limits_locked
    ic.control_limits_locked = locked

    # If locking, snapshot current limits
    if locked:
        chart_data = await _compute_chart_data(db, ic)
        limits = chart_data["limits"]
        snapshot = ControlLimitSnapshot(
            ic_id=ic_id,
            ucl=limits.get("ucl") or 0,
            lcl=limits.get("lcl") or 0,
            cl=limits.get("cl") or 0,
            r_ucl=limits.get("r_ucl"),
            r_lcl=limits.get("r_lcl"),
            is_locked=True,
        )
        db.add(snapshot)

    await db.commit()
    await db.refresh(ic)

    await _create_audit_log(
        db, user_id, "TRANSITION", "inspection_characteristics", ic_id,
        {"control_limits_locked": {"before": old_state, "after": locked}}
    )
    return ic


async def add_sample_batch(
    db: AsyncSession, user_id: uuid.UUID, ic_id: uuid.UUID,
    data: dict
) -> SampleBatch:
    ic = await get_inspection_characteristic(db, ic_id)
    if not ic:
        raise ValueError("Inspection characteristic not found")

    values = data["values"]
    if not values:
        raise ValueError("Values cannot be empty")

    if ic.chart_type == "xbar_r" and len(values) != ic.subgroup_size:
        raise ValueError(f"Expected {ic.subgroup_size} values for xbar_r, got {len(values)}")

    if ic.chart_type == "imr" and len(values) != 1:
        raise ValueError(f"Expected 1 value for imr, got {len(values)}")

    batch = SampleBatch(
        ic_id=ic_id,
        batch_no=data["batch_no"],
        sampled_at=data["sampled_at"],
        subgroup_size=len(values),
    )
    db.add(batch)
    await db.flush()

    for i, val in enumerate(values):
        db.add(SampleValue(batch_id=batch.batch_id, sequence_no=i + 1, value=val))

    await db.commit()
    await db.refresh(batch)

    # Re-evaluate alarms if not locked
    if not ic.control_limits_locked:
        await _reevaluate_alarms(db, ic)

    await _create_audit_log(
        db, user_id, "CREATE", "sample_batches", batch.batch_id,
        {"ic_id": str(ic_id), "batch_no": data["batch_no"], "count": len(values)}
    )
    return batch


async def _compute_chart_data(db: AsyncSession, ic: InspectionCharacteristic) -> Dict[str, Any]:
    """Compute chart data and limits for an inspection characteristic."""
    result = await db.execute(
        select(SampleBatch, SampleValue)
        .join(SampleValue, SampleBatch.batch_id == SampleValue.batch_id)
        .where(SampleBatch.ic_id == ic.ic_id)
        .where(SampleBatch.is_locked == False)
        .order_by(SampleBatch.sampled_at)
    )

    batches = {}
    for batch, value in result.all():
        if batch.batch_id not in batches:
            batches[batch.batch_id] = {"batch": batch, "values": []}
        batches[batch.batch_id]["values"].append(float(value.value))

    batch_list = sorted(batches.values(), key=lambda x: x["batch"].sampled_at)

    if ic.chart_type == "xbar_r":
        values_2d = [b["values"] for b in batch_list]
        limits = calculate_xbar_r_limits(values_2d) if len(values_2d) >= 2 else {}
        data_points = []
        for i, b in enumerate(batch_list):
            vals = b["values"]
            data_points.append({
                "batch_index": i,
                "batch_no": b["batch"].batch_no,
                "sampled_at": b["batch"].sampled_at,
                "x_value": round(sum(vals) / len(vals), 4) if vals else None,
                "r_value": round(max(vals) - min(vals), 4) if vals else None,
                "alarm_flags": [],
            })
    else:  # imr
        values_1d = []
        for b in batch_list:
            values_1d.extend(b["values"])
        limits = calculate_imr_limits(values_1d) if len(values_1d) >= 2 else {}
        data_points = []
        idx = 0
        for b in batch_list:
            for val in b["values"]:
                mr = None
                if idx > 0:
                    mr = round(abs(val - values_1d[idx - 1]), 4)
                data_points.append({
                    "batch_index": idx,
                    "batch_no": b["batch"].batch_no,
                    "sampled_at": b["batch"].sampled_at,
                    "x_value": round(val, 4),
                    "r_value": mr,
                    "alarm_flags": [],
                })
                idx += 1

    return {
        "chart_type": ic.chart_type,
        "data_points": data_points,
        "limits": limits,
        "total_batches": len(batch_list),
    }


async def _reevaluate_alarms(db: AsyncSession, ic: InspectionCharacteristic) -> None:
    """Re-evaluate all Western Electric rules after new data is added."""
    chart_data = await _compute_chart_data(db, ic)
    data_points = chart_data["data_points"]
    limits = chart_data["limits"]

    if not data_points or not limits.get("ucl"):
        return

    # Evaluate rules
    subgroup_stats = [dp["x_value"] for dp in data_points if dp["x_value"] is not None]
    alarms = evaluate_western_electric(subgroup_stats, limits, ic.rules_config)

    # Create alarm records for new violations
    for alarm in alarms:
        dp = data_points[alarm["batch_index"]]
        # Check if this alarm already exists (same rule, same batch)
        batch_result = await db.execute(
            select(SampleBatch).where(SampleBatch.batch_no == dp["batch_no"])
        )
        batch = batch_result.scalar_one_or_none()

        existing = await db.execute(
            select(SPCAlarm).where(
                and_(
                    SPCAlarm.ic_id == ic.ic_id,
                    SPCAlarm.rule_no == alarm["rule_no"],
                    SPCAlarm.batch_id == (batch.batch_id if batch else None),
                )
            )
        )
        if existing.scalar_one_or_none():
            continue

        spc_alarm = SPCAlarm(
            ic_id=ic.ic_id,
            batch_id=batch.batch_id if batch else None,
            rule_no=alarm["rule_no"],
            severity=alarm["severity"],
            status="open",
        )
        db.add(spc_alarm)

        # Auto-create CAPA for critical alarms
        if alarm["severity"] == "critical":
            year = datetime.now(timezone.utc).year
            capa = CAPAEightD(
                document_no=f"8D-{year}-{str(uuid.uuid4())[:4].upper()}",
                title=f"SPC异常: {ic.ic_code} 触发规则{alarm['rule_no']}",
                product_line_code=ic.product_line,
                status="D1_TEAM",
                severity="严重",
                created_by=ic.created_by_id,
            )
            db.add(capa)
            await db.flush()
            spc_alarm.linked_capa_id = capa.report_id

    await db.commit()


async def get_chart_data(db: AsyncSession, ic_id: uuid.UUID) -> Dict[str, Any]:
    ic = await get_inspection_characteristic(db, ic_id)
    if not ic:
        raise ValueError("Inspection characteristic not found")
    return await _compute_chart_data(db, ic)


async def calculate_capability(db: AsyncSession, ic_id: uuid.UUID) -> Dict[str, Any]:
    ic = await get_inspection_characteristic(db, ic_id)
    if not ic:
        raise ValueError("Inspection characteristic not found")

    result = await db.execute(
        select(SampleValue.value)
        .join(SampleBatch, SampleValue.batch_id == SampleBatch.batch_id)
        .where(SampleBatch.ic_id == ic_id)
        .where(SampleBatch.is_locked == False)
        .order_by(SampleBatch.sampled_at, SampleValue.sequence_no)
    )
    values = [float(row[0]) for row in result.all()]

    if len(values) < 2:
        raise ValueError("Need at least 2 samples for capability analysis")

    usl = float(ic.spec_upper)
    lsl = float(ic.spec_lower)

    cp_cpk = calculate_cp_cpk(values, usl, lsl)
    pp_ppk = calculate_pp_ppk(values, usl, lsl)
    cm = calculate_cm(values, usl, lsl)
    ppm = calculate_ppm(values, usl, lsl)
    grade = get_capability_grade(cp_cpk["cpk"])
    advice = get_capability_advice(cp_cpk["cpk"])

    return {
        **cp_cpk,
        **pp_ppk,
        **cm,
        **ppm,
        "grade": grade,
        "advice": advice,
    }


async def list_alarms(
    db: AsyncSession, ic_id: Optional[uuid.UUID] = None,
    page: int = 1, page_size: int = 20
) -> Tuple[List[SPCAlarm], int]:
    query = select(SPCAlarm)
    count_query = select(func.count(SPCAlarm.alarm_id))

    if ic_id:
        query = query.where(SPCAlarm.ic_id == ic_id)
        count_query = count_query.where(SPCAlarm.ic_id == ic_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
        .order_by(SPCAlarm.triggered_at.desc())
    )
    items = result.scalars().all()
    return list(items), total


async def acknowledge_alarm(db: AsyncSession, user_id: uuid.UUID, alarm_id: uuid.UUID) -> SPCAlarm:
    alarm = await db.get(SPCAlarm, alarm_id)
    if not alarm:
        raise ValueError("Alarm not found")

    alarm.status = "acknowledged"
    alarm.acknowledged_by_id = user_id
    alarm.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(alarm)

    await _create_audit_log(
        db, user_id, "UPDATE", "spc_alarms", alarm_id,
        {"status": {"before": "open", "after": "acknowledged"}}
    )
    return alarm


async def create_capa_from_alarm(
    db: AsyncSession, user_id: uuid.UUID, alarm_id: uuid.UUID
) -> CAPAEightD:
    alarm = await db.get(SPCAlarm, alarm_id)
    if not alarm:
        raise ValueError("Alarm not found")

    ic = await get_inspection_characteristic(db, alarm.ic_id)
    if not ic:
        raise ValueError("Inspection characteristic not found")

    if alarm.linked_capa_id:
        raise ValueError("Alarm already linked to a CAPA")

    year = datetime.now(timezone.utc).year
    capa = CAPAEightD(
        document_no=f"8D-{year}-{str(uuid.uuid4())[:8].upper()}",
        title=f"SPC异常: {ic.ic_code} 触发规则{alarm.rule_no}",
        product_line_code=ic.product_line,
        status="D1_TEAM",
        severity="严重",
        created_by=user_id,
    )
    db.add(capa)
    await db.flush()

    alarm.linked_capa_id = capa.report_id
    await db.commit()
    await db.refresh(capa)

    await _create_audit_log(
        db, user_id, "CREATE", "capa_eightd", capa.report_id,
        {"alarm_id": str(alarm_id), "ic_code": ic.ic_code}
    )
    return capa


async def ingest_external_data(db: AsyncSession, data: dict) -> SampleBatch:
    ic_code = data["ic_code"]
    result = await db.execute(
        select(InspectionCharacteristic).where(InspectionCharacteristic.ic_code == ic_code)
    )
    ic = result.scalar_one_or_none()
    if not ic:
        raise ValueError(f"Inspection characteristic with code '{ic_code}' not found")

    return await add_sample_batch(db, ic.created_by_id, ic.ic_id, {
        "batch_no": data["batch_no"],
        "sampled_at": data["sampled_at"],
        "values": data["values"],
    })
