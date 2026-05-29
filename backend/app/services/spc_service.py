import math
import uuid
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any

from sqlalchemy import select, func, and_, update
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
    calculate_histogram_data, evaluate_western_electric,
    calculate_cp_cpk, calculate_pp_ppk, calculate_cm, calculate_ppm,
    get_capability_grade, get_capability_advice,
    calculate_p_limits, calculate_np_limits, calculate_c_limits, calculate_u_limits,
)


async def _add_audit_log_no_commit(
    db: AsyncSession, user_id: uuid.UUID, action: str, table_name: str,
    record_id: uuid.UUID, changed_fields: Optional[dict] = None
) -> None:
    """db.add(AuditLog) + db.flush()，不 commit。"""
    db.add(AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        changed_fields=changed_fields or {},
        operated_by=user_id,
    ))
    await db.flush()


async def _create_audit_log(
    db: AsyncSession, user_id: uuid.UUID, action: str, table_name: str,
    record_id: uuid.UUID, changed_fields: Optional[dict] = None
) -> None:
    await _add_audit_log_no_commit(db, user_id, action, table_name, record_id, changed_fields)
    await db.commit()


async def _get_active_control_limits(
    db: AsyncSession, ic: InspectionCharacteristic
) -> Dict[str, Any]:
    """Return current control limits: read snapshot if locked, else recalculate from samples."""
    if ic.control_limits_locked:
        # First, try to get the active snapshot
        result = await db.execute(
            select(ControlLimitSnapshot)
            .where(and_(
                ControlLimitSnapshot.ic_id == ic.ic_id,
                ControlLimitSnapshot.is_locked == True,
                ControlLimitSnapshot.is_active == True,
            ))
            .order_by(ControlLimitSnapshot.calculated_at.desc())
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()

        # Fall back to latest locked snapshot if no active snapshot is found
        if not snapshot:
            result = await db.execute(
                select(ControlLimitSnapshot)
                .where(and_(
                    ControlLimitSnapshot.ic_id == ic.ic_id,
                    ControlLimitSnapshot.is_locked == True,
                ))
                .order_by(ControlLimitSnapshot.calculated_at.desc())
                .limit(1)
            )
            snapshot = result.scalar_one_or_none()

        if snapshot:
            if ic.chart_type in {"p", "u"}:
                result_batches = await db.execute(
                    select(SampleBatch)
                    .where(SampleBatch.ic_id == ic.ic_id)
                    .where(SampleBatch.is_locked == False)
                    .order_by(SampleBatch.sampled_at)
                )
                attr_batches = result_batches.scalars().all()
                cl_val = float(snapshot.cl)
                ucl_list = []
                lcl_list = []
                for b in attr_batches:
                    n = b.inspected_count
                    if n is None or n == 0:
                        ucl_list.append(None)
                        lcl_list.append(0.0)
                        continue
                    if ic.chart_type == "p":
                        spread = 3 * math.sqrt(cl_val * (1 - cl_val) / n)
                    else:  # u chart
                        spread = 3 * math.sqrt(cl_val / n)
                    ucl_list.append(round(cl_val + spread, 4))
                    lcl_list.append(max(0.0, round(cl_val - spread, 4)))
                return {
                    "cl": cl_val,
                    "ucl_list": ucl_list,
                    "lcl_list": lcl_list,
                    "ucl": cl_val,  # Nominal value to bypass the old scalar check
                    "lcl": cl_val,
                }
            else:
                return {
                    "ucl": float(snapshot.ucl),
                    "lcl": float(snapshot.lcl),
                    "cl": float(snapshot.cl),
                    "r_ucl": float(snapshot.r_ucl) if snapshot.r_ucl is not None else None,
                    "r_lcl": float(snapshot.r_lcl) if snapshot.r_lcl is not None else None,
                    "r_cl": float(snapshot.r_cl) if snapshot.r_cl is not None else None,
                }

    # Not locked (or no snapshot found) — recalculate from samples
    result = await db.execute(
        select(SampleBatch, SampleValue)
        .join(SampleValue, SampleBatch.batch_id == SampleValue.batch_id)
        .where(SampleBatch.ic_id == ic.ic_id)
        .where(SampleBatch.is_locked == False)
        .order_by(SampleBatch.sampled_at, SampleValue.sequence_no)
    )

    batches: Dict[str, Any] = {}
    for batch, value in result.all():
        bid = str(batch.batch_id)
        if bid not in batches:
            batches[bid] = {"batch": batch, "values": []}
        batches[bid]["values"].append(float(value.value))

    batch_list = sorted(batches.values(), key=lambda x: x["batch"].sampled_at)

    if ic.chart_type == "xbar_r":
        values_2d = [b["values"] for b in batch_list]
        return calculate_xbar_r_limits(values_2d) if len(values_2d) >= 2 else {}
    elif ic.chart_type in {"p", "np", "c", "u"}:
        result = await db.execute(
            select(SampleBatch)
            .where(SampleBatch.ic_id == ic.ic_id)
            .where(SampleBatch.is_locked == False)
            .order_by(SampleBatch.sampled_at)
        )
        attr_batches = result.scalars().all()
        if len(attr_batches) < 2:
            return {}
        batch_data = [
            {"inspected_count": b.inspected_count, "defect_count": b.defect_count}
            for b in attr_batches
            if b.inspected_count is not None and b.defect_count is not None
        ]
        if ic.chart_type == "p":
            return calculate_p_limits(batch_data)
        elif ic.chart_type == "np":
            return calculate_np_limits(batch_data)
        elif ic.chart_type == "c":
            return calculate_c_limits(batch_data)
        else:
            return calculate_u_limits(batch_data)
    else:
        values_1d = []
        for b in batch_list:
            values_1d.extend(b["values"])
        return calculate_imr_limits(values_1d) if len(values_1d) >= 2 else {}


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
        limits = await _get_active_control_limits(db, ic)
        # Compute next version_no for this ic
        version_result = await db.execute(
            select(func.max(ControlLimitSnapshot.version_no))
            .where(ControlLimitSnapshot.ic_id == ic_id)
        )
        max_version = version_result.scalar() or 0
        next_version = max_version + 1

        # Deactivate all existing snapshots for this ic
        await db.execute(
            update(ControlLimitSnapshot)
            .where(ControlLimitSnapshot.ic_id == ic_id)
            .values(is_active=False)
        )

        r_ucl = limits.get("r_ucl")
        r_lcl = limits.get("r_lcl")
        r_cl = limits.get("r_cl")
        snapshot = ControlLimitSnapshot(
            ic_id=ic_id,
            ucl=limits.get("ucl") or 0,
            lcl=limits.get("lcl") or 0,
            cl=limits.get("cl") or 0,
            r_ucl=r_ucl,
            r_lcl=r_lcl,
            r_cl=r_cl,
            is_locked=True,
            version_no=next_version,
            is_active=True,
        )
        db.add(snapshot)

    await db.commit()
    await db.refresh(ic)

    await _create_audit_log(
        db, user_id, "TRANSITION", "inspection_characteristics", ic_id,
        {"control_limits_locked": {"before": old_state, "after": locked}}
    )
    return ic


async def _create_sample_batch_inner(
    db: AsyncSession, user_id: uuid.UUID, ic_id: uuid.UUID, data: dict
) -> SampleBatch:
    """创建 SampleBatch + SampleValues + AuditLog，flush 但不 commit。"""
    ic = await get_inspection_characteristic(db, ic_id)
    if not ic:
        raise ValueError("Inspection characteristic not found")

    inspected_count = None
    defect_count = None
    attribute_charts = {"p", "np", "c", "u"}

    if ic.chart_type in attribute_charts:
        inspected_count = data.get("inspected_count")
        defect_count = data.get("defect_count")
        if inspected_count is None or defect_count is None:
            raise ValueError(f"计数值图（{ic.chart_type}）必须提供 inspected_count 和 defect_count")
        if defect_count > inspected_count:
            raise ValueError("defect_count 不能超过 inspected_count")
        values = []
    else:
        values = data.get("values")
        if not values:
            raise ValueError("Values cannot be empty")
        if ic.chart_type == "xbar_r" and len(values) != ic.subgroup_size:
            raise ValueError(f"Expected {ic.subgroup_size} values for xbar_r, got {len(values)}")
        if ic.chart_type == "imr" and len(values) != 1:
            raise ValueError(f"Expected 1 value for imr, got {len(values)}")

    sampled_at = data["sampled_at"]
    if isinstance(sampled_at, str):
        sampled_at = datetime.fromisoformat(sampled_at.replace("Z", "+00:00"))

    batch = SampleBatch(
        ic_id=ic_id,
        batch_no=data["batch_no"],
        sampled_at=sampled_at,
        subgroup_size=len(values),
        inspected_count=inspected_count,
        defect_count=defect_count,
    )
    db.add(batch)
    await db.flush()

    for i, val in enumerate(values):
        db.add(SampleValue(batch_id=batch.batch_id, sequence_no=i + 1, value=val))

    await _add_audit_log_no_commit(
        db, user_id, "CREATE", "sample_batches", batch.batch_id,
        {"ic_id": str(ic_id), "batch_no": data["batch_no"], "count": len(values)}
    )
    return batch


async def add_sample_batch(
    db: AsyncSession, user_id: uuid.UUID, ic_id: uuid.UUID,
    data: dict
) -> SampleBatch:
    batch = await _create_sample_batch_inner(db, user_id, ic_id, data)
    await db.commit()
    await db.refresh(batch)
    ic = await get_inspection_characteristic(db, ic_id)
    if ic:
        await _reevaluate_alarms(db, ic)
    return batch


async def _compute_chart_data(db: AsyncSession, ic: InspectionCharacteristic) -> Dict[str, Any]:
    """Compute chart data points and active control limits for an inspection characteristic."""
    # Fetch all unlocked batches with values ordered by sequence_no for determinism
    result = await db.execute(
        select(SampleBatch, SampleValue)
        .join(SampleValue, SampleBatch.batch_id == SampleValue.batch_id)
        .where(SampleBatch.ic_id == ic.ic_id)
        .where(SampleBatch.is_locked == False)
        .order_by(SampleBatch.sampled_at, SampleValue.sequence_no)
    )

    batches: Dict[str, Any] = {}
    for batch, value in result.all():
        bid = str(batch.batch_id)
        if bid not in batches:
            batches[bid] = {"batch": batch, "values": []}
        batches[bid]["values"].append(float(value.value))

    batch_list = sorted(batches.values(), key=lambda x: x["batch"].sampled_at)

    # Use the seam: locked -> snapshot, unlocked -> live calculation
    limits = await _get_active_control_limits(db, ic)

    if ic.chart_type == "xbar_r":
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
    elif ic.chart_type in {"p", "np", "c", "u"}:
        attr_result = await db.execute(
            select(SampleBatch)
            .where(SampleBatch.ic_id == ic.ic_id)
            .where(SampleBatch.is_locked == False)
            .order_by(SampleBatch.sampled_at)
        )
        attr_batches = attr_result.scalars().all()
        data_points = []
        for i, b in enumerate(attr_batches):
            if b.inspected_count is None or b.defect_count is None:
                continue
            if ic.chart_type in {"p", "u"}:
                stat = b.defect_count / b.inspected_count if b.inspected_count > 0 else 0
            else:
                stat = float(b.defect_count)
            data_points.append({
                "batch_index": i,
                "batch_no": b.batch_no,
                "sampled_at": b.sampled_at,
                "x_value": round(stat, 4),
                "r_value": None,
                "alarm_flags": [],
            })
        batch_list = []  # cleared so total uses data_points length below
    else:  # imr
        values_1d = []
        for b in batch_list:
            values_1d.extend(b["values"])
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

    total = len(batch_list) if ic.chart_type not in {"p", "np", "c", "u"} else len(data_points)
    return {
        "chart_type": ic.chart_type,
        "data_points": data_points,
        "limits": limits,
        "total_batches": total,
    }


async def _reevaluate_alarms_no_commit(db: AsyncSession, ic: InspectionCharacteristic) -> None:
    """计算告警 + 生成 SPCAlarm 记录 + db.flush()，不 commit。
    批量导入只创建 SPCAlarm，不自动创建 CAPA。"""
    chart_data = await _compute_chart_data(db, ic)
    data_points = chart_data["data_points"]
    limits = chart_data["limits"]

    if not data_points or (limits.get("ucl") is None and limits.get("ucl_list") is None):
        return

    # Evaluate rules
    subgroup_stats = [dp["x_value"] for dp in data_points if dp["x_value"] is not None]
    # Attribute charts: only Rule 1 (beyond control limits) applies
    if ic.chart_type in {"p", "np", "c", "u"}:
        effective_rules = {k: (v if k == "rule_1" else False) for k, v in ic.rules_config.items()}
    else:
        effective_rules = ic.rules_config
    alarms = evaluate_western_electric(subgroup_stats, limits, effective_rules)

    # Create alarm records for new violations
    for alarm in alarms:
        dp = data_points[alarm["batch_index"]]
        # Check if this alarm already exists (same rule, same batch)
        batch_result = await db.execute(
            select(SampleBatch).where(
                and_(SampleBatch.batch_no == dp["batch_no"], SampleBatch.ic_id == ic.ic_id)
            )
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

    await db.flush()


async def bulk_import_samples(
    db: AsyncSession,
    ic: InspectionCharacteristic,
    rows: list[dict],
    user_id: uuid.UUID,
) -> "ImportResult":
    from app.utils.excel import ImportError as ExcelImportError, ImportResult, MAX_IMPORT_ROWS
    from app.utils.excel import coerce_datetime, coerce_int_strict

    if len(rows) > MAX_IMPORT_ROWS:
        return ImportResult(0, [ExcelImportError(0, "", f"导入行数超过上限 {MAX_IMPORT_ROWS}")])

    if not rows:
        return ImportResult(0, [ExcelImportError(0, "", "没有可导入的数据行")])

    # 预检查 DB 已存在的 batch_no
    result = await db.execute(
        select(SampleBatch.batch_no).where(SampleBatch.ic_id == ic.ic_id)
    )
    existing_batch_nos = {bn for (bn,) in result.all()}

    errors = []
    seen = set()
    validated = []
    attribute_charts = {"p", "np", "c", "u"}

    for row in rows:
        row_no = row.pop("_row")
        errs = []

        if not row.get("batch_no"):
            errs.append(ExcelImportError(row_no, "batch_no", "批次号为必填项"))
        if not row.get("sampled_at"):
            errs.append(ExcelImportError(row_no, "sampled_at", "采样时间为必填项"))

        sampled_at = coerce_datetime(row.get("sampled_at"))
        if sampled_at is None and row.get("sampled_at"):
            errs.append(ExcelImportError(row_no, "sampled_at", "日期格式无效"))
        elif sampled_at:
            row["sampled_at"] = sampled_at

        batch_no = row.get("batch_no")
        if batch_no:
            if batch_no in seen:
                errs.append(ExcelImportError(row_no, "batch_no", f"批次内重复: {batch_no}"))
            if batch_no in existing_batch_nos:
                errs.append(ExcelImportError(row_no, "batch_no", f"数据库已存在: {batch_no}"))
            seen.add(batch_no)

        if ic.chart_type in attribute_charts:
            ic_val = row.get("inspected_count")
            if ic_val is None:
                errs.append(ExcelImportError(row_no, "inspected_count", "计数值图需要检验数"))
            else:
                try:
                    ic_int = coerce_int_strict(ic_val)
                    if ic_int < 0:
                        errs.append(ExcelImportError(row_no, "inspected_count", "检验数必须为非负整数"))
                    else:
                        row["inspected_count"] = ic_int
                except (ValueError, TypeError):
                    errs.append(ExcelImportError(row_no, "inspected_count", "检验数必须为整数（不能为小数）"))

            dc_val = row.get("defect_count")
            if dc_val is None:
                errs.append(ExcelImportError(row_no, "defect_count", "计数值图需要缺陷数"))
            else:
                try:
                    dc_int = coerce_int_strict(dc_val)
                    if dc_int < 0:
                        errs.append(ExcelImportError(row_no, "defect_count", "缺陷数必须为非负整数"))
                    elif "inspected_count" in row and dc_int > row["inspected_count"]:
                        errs.append(ExcelImportError(row_no, "defect_count", "缺陷数不能超过检验数"))
                    else:
                        row["defect_count"] = dc_int
                except (ValueError, TypeError):
                    errs.append(ExcelImportError(row_no, "defect_count", "缺陷数必须为整数（不能为小数）"))
        else:
            values = []
            for i in range(1, ic.subgroup_size + 1):
                key = f"value_{i}"
                val = row.get(key)
                if val is None:
                    errs.append(ExcelImportError(row_no, key, f"样本值{i}为必填项"))
                else:
                    try:
                        values.append(float(val))
                    except (ValueError, TypeError):
                        errs.append(ExcelImportError(row_no, key, f"样本值{i}必须为数字"))
            if not errs:
                row["_values"] = values

        if errs:
            errors.extend(errs)
        else:
            validated.append(row)

    if errors:
        return ImportResult(0, errors)

    created = []
    try:
        for row in validated:
            data = {"batch_no": row["batch_no"], "sampled_at": row["sampled_at"]}
            if ic.chart_type in attribute_charts:
                data["inspected_count"] = row["inspected_count"]
                data["defect_count"] = row["defect_count"]
                data["values"] = []
            else:
                data["values"] = row.pop("_values")
            batch = await _create_sample_batch_inner(db, user_id, ic.ic_id, data)
            created.append(batch)

        await _reevaluate_alarms_no_commit(db, ic)
        await db.commit()
    except Exception:
        await db.rollback()
        return ImportResult(0, [ExcelImportError(0, "", "数据库写入失败，请重试")])

    return ImportResult(len(created), [])


async def _reevaluate_alarms(db: AsyncSession, ic: InspectionCharacteristic) -> None:
    """Re-evaluate all Western Electric rules after new data is added."""
    chart_data = await _compute_chart_data(db, ic)
    data_points = chart_data["data_points"]
    limits = chart_data["limits"]

    if not data_points or (limits.get("ucl") is None and limits.get("ucl_list") is None):
        return

    # Evaluate rules
    subgroup_stats = [dp["x_value"] for dp in data_points if dp["x_value"] is not None]
    # Attribute charts: only Rule 1 (beyond control limits) applies
    if ic.chart_type in {"p", "np", "c", "u"}:
        effective_rules = {k: (v if k == "rule_1" else False) for k, v in ic.rules_config.items()}
    else:
        effective_rules = ic.rules_config
    alarms = evaluate_western_electric(subgroup_stats, limits, effective_rules)

    # Create alarm records for new violations
    for alarm in alarms:
        dp = data_points[alarm["batch_index"]]
        # Check if this alarm already exists (same rule, same batch)
        batch_result = await db.execute(
            select(SampleBatch).where(
                and_(SampleBatch.batch_no == dp["batch_no"], SampleBatch.ic_id == ic.ic_id)
            )
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


async def list_snapshots(db: AsyncSession, ic_id: uuid.UUID) -> list:
    ic = await get_inspection_characteristic(db, ic_id)
    if not ic:
        raise ValueError("Inspection characteristic not found")
    result = await db.execute(
        select(ControlLimitSnapshot)
        .where(ControlLimitSnapshot.ic_id == ic_id)
        .order_by(ControlLimitSnapshot.version_no.desc())
    )
    return result.scalars().all()


async def activate_snapshot(
    db: AsyncSession, user_id: uuid.UUID, ic_id: uuid.UUID, snapshot_id: uuid.UUID,
    change_reason: str = "",
) -> ControlLimitSnapshot:
    ic = await get_inspection_characteristic(db, ic_id)
    if not ic:
        raise ValueError("Inspection characteristic not found")
    if not change_reason.strip():
        raise ValueError("激活控制限必须提供变更原因 (change_reason)")

    snap_result = await db.execute(
        select(ControlLimitSnapshot).where(
            and_(
                ControlLimitSnapshot.snapshot_id == snapshot_id,
                ControlLimitSnapshot.ic_id == ic_id,
            )
        )
    )
    snapshot = snap_result.scalar_one_or_none()
    if not snapshot:
        raise ValueError("Snapshot not found for this characteristic")
    await db.execute(
        update(ControlLimitSnapshot)
        .where(ControlLimitSnapshot.ic_id == ic_id)
        .values(is_active=False)
    )
    snapshot.is_active = True
    await db.commit()
    await db.refresh(snapshot)
    await _create_audit_log(
        db, user_id, "TRANSITION", "control_limit_snapshots", snapshot_id,
        {"action": "activate_control_limit", "version_no": snapshot.version_no, "change_reason": change_reason}
    )
    return snapshot


async def get_spc_measurements_for_msa(
    db: AsyncSession,
    ic_id: uuid.UUID,
    limit: int | None = None,
) -> list[dict]:
    """Extract SPC sample measurements for MSA study auto-population.
    
    Returns a flat list of {value, batch_no, sampled_at, sequence_no} dicts
    suitable for populating MSA study measurements (Bias, GRR, Stability, etc.).
    """
    batches_result = await db.execute(
        select(SampleBatch)
        .where(SampleBatch.ic_id == ic_id)
        .options(selectinload(SampleBatch.values))
        .order_by(SampleBatch.sampled_at.desc())
        .limit(limit or 50)
    )
    batches = batches_result.scalars().all()
    
    measurements: list[dict] = []
    for batch in batches:
        for val in sorted(batch.values, key=lambda v: v.sequence_no or 0):
            measurements.append({
                "value": float(val.value),
                "batch_no": batch.batch_no,
                "sampled_at": batch.sampled_at.isoformat() if batch.sampled_at else None,
                "sequence_no": val.sequence_no,
            })
    return measurements
