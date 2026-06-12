import logging
import uuid
from datetime import datetime, date, timezone
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.iqc_inspection import IqcInspection
from app.models.iqc_inspection_item import IqcInspectionItem, IqcItemMeasurement
from app.models.iqc_inspection_template import IqcInspectionTemplate
from app.models.audit import AuditLog
from app.models.supplier import SupplierSCAR
from app.services.aql_engine import calculate_aql_plan


async def _trigger_risk_eval(supplier_id, product_line_code):
    """Trigger incremental risk evaluation in an independent session."""
    import asyncio
    from app.database import async_session, get_tenant_aware_session
    from app.services.supplier_risk.service import evaluate_supplier_risk

    await asyncio.sleep(0.5)  # brief delay to let caller transaction settle
    try:
        async with get_tenant_aware_session() as db:
            await evaluate_supplier_risk(db, supplier_id, product_line_code)
    except Exception:
        logging.getLogger(__name__).exception("Incremental risk eval failed for supplier %s", supplier_id)


# ─── Numbering ───

async def _generate_inspection_no(db: AsyncSession) -> str:
    today = datetime.now(timezone.utc).strftime("%y%m%d")
    prefix = f"IQC-{today}"
    result = await db.execute(
        select(func.count()).where(IqcInspection.inspection_no.like(f"{prefix}-%"))
    )
    count = (result.scalar() or 0) + 1
    return f"{prefix}-{count:03d}"


# ─── State machine ───

VALID_TRANSITIONS: dict[str, dict[str, str]] = {
    "pending": {"start": "inspecting"},
    "inspecting": {"judge": "judged"},
    "judged": {"close": "closed", "request_reinspect": "pending"},
}


def _transition(current: str, action: str) -> str:
    transitions = VALID_TRANSITIONS.get(current, {})
    if action not in transitions:
        raise ValueError(f"invalid action '{action}' for status '{current}'")
    return transitions[action]


# ─── Inspection CRUD ───

async def list_inspections(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    inspection_result: str | None = None,
    supplier_id: uuid.UUID | None = None,
    material_id: uuid.UUID | None = None,
    keyword: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    product_line_code: str | None = None,
    factory_id: uuid.UUID | None = None,
    allowed_product_line_codes: list[str] | None = None,
) -> tuple[list[IqcInspection], int]:
    query = select(IqcInspection).options(
        selectinload(IqcInspection.items).selectinload(IqcInspectionItem.measurements)
    )
    count_q = select(func.count(IqcInspection.inspection_id))

    if status:
        query = query.where(IqcInspection.status == status)
        count_q = count_q.where(IqcInspection.status == status)
    if inspection_result:
        query = query.where(IqcInspection.inspection_result == inspection_result)
        count_q = count_q.where(IqcInspection.inspection_result == inspection_result)
    if supplier_id:
        query = query.where(IqcInspection.supplier_id == supplier_id)
        count_q = count_q.where(IqcInspection.supplier_id == supplier_id)
    if material_id:
        query = query.where(IqcInspection.material_id == material_id)
        count_q = count_q.where(IqcInspection.material_id == material_id)
    if keyword:
        filt = or_(
            IqcInspection.inspection_no.ilike(f"%{keyword}%"),
            IqcInspection.part_no.ilike(f"%{keyword}%"),
            IqcInspection.lot_no.ilike(f"%{keyword}%"),
        )
        query = query.where(filt)
        count_q = count_q.where(filt)
    if date_from:
        query = query.where(IqcInspection.inspection_date >= date_from)
        count_q = count_q.where(IqcInspection.inspection_date >= date_from)
    if date_to:
        query = query.where(IqcInspection.inspection_date <= date_to)
        count_q = count_q.where(IqcInspection.inspection_date <= date_to)
    if product_line_code:
        query = query.where(IqcInspection.product_line_code == product_line_code)
        count_q = count_q.where(IqcInspection.product_line_code == product_line_code)
    if factory_id:
        query = query.where(IqcInspection.factory_id == factory_id)
        count_q = count_q.where(IqcInspection.factory_id == factory_id)
    if allowed_product_line_codes is not None:
        query = query.where(IqcInspection.product_line_code.in_(allowed_product_line_codes))
        count_q = count_q.where(IqcInspection.product_line_code.in_(allowed_product_line_codes))

    total = (await db.execute(count_q)).scalar() or 0
    items = (await db.execute(
        query.order_by(IqcInspection.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return list(items), total


async def get_inspection(db: AsyncSession, inspection_id: uuid.UUID) -> IqcInspection | None:
    result = await db.execute(
        select(IqcInspection)
        .options(selectinload(IqcInspection.items).selectinload(IqcInspectionItem.measurements))
        .where(IqcInspection.inspection_id == inspection_id)
    )
    return result.scalar_one_or_none()


async def create_inspection(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    inspection_mode: str = "quick",
    material_id: uuid.UUID | None = None,
    template_id: uuid.UUID | None = None,
    part_no: str | None = None,
    part_name: str | None = None,
    lot_no: str | None = None,
    lot_qty: int | None = None,
    aql_level: float | None = None,
    inspection_level: str = "II",
    inspection_date: date | None = None,
    product_line_code: str | None = None,
    user_id: uuid.UUID | None = None,
) -> IqcInspection:
    inspection_no = await _generate_inspection_no(db)

    inspection = IqcInspection(
        inspection_no=inspection_no,
        supplier_id=supplier_id,
        inspection_mode=inspection_mode,
        material_id=material_id,
        template_id=template_id,
        part_no=part_no,
        part_name=part_name,
        lot_no=lot_no,
        lot_qty=lot_qty,
        aql_level=str(aql_level) if aql_level else None,
        inspection_level=inspection_level,
        inspection_date=inspection_date,
        product_line_code=product_line_code,
        status="pending",
        inspection_result="pending",
    )

    # Dynamic AQL injection from optimization profile
    if not aql_level and material_id and supplier_id:
        from app.services.iqc_aql_service import AqlService
        try:
            profile = await AqlService.get_profile(db, supplier_id, material_id)
            if profile:
                # frozen 状态继续使用 profile.current_aql，不降级
                aql_level = profile.current_aql
        except Exception:
            pass  # Fall through to material default

    # Fallback: load material and use default_aql if no profile set AQL
    if not aql_level and material_id:
        from app.models.iqc_material import IqcMaterial
        material = await db.get(IqcMaterial, material_id)
        if material and material.default_aql:
            aql_level = material.default_aql

    # Write resolved AQL back to inspection record
    if aql_level and not inspection.aql_level:
        inspection.aql_level = str(aql_level)

    # AQL auto-calculate
    if lot_qty and aql_level:
        try:
            plan = calculate_aql_plan(lot_qty, aql_level, inspection_level)
            inspection.code_letter = plan["code_letter"]
            inspection.sample_qty = plan["sample_size"]
            inspection.accept_number = plan["accept_number"]
            inspection.reject_number = plan["reject_number"]
        except ValueError:
            pass  # Leave AQL fields null if calculation fails

    db.add(inspection)
    await db.flush()

    # Detailed mode: instantiate items from template
    if inspection_mode == "detailed" and template_id:
        template = (await db.execute(
            select(IqcInspectionTemplate)
            .options(selectinload(IqcInspectionTemplate.items))
            .where(IqcInspectionTemplate.template_id == template_id)
        )).scalar_one_or_none()

        if template:
            for ti in sorted(template.items, key=lambda x: x.sort_order):
                item_aql = ti.aql_level or aql_level
                item_plan = None
                if lot_qty and item_aql:
                    try:
                        item_plan = calculate_aql_plan(lot_qty, item_aql, inspection_level)
                    except ValueError:
                        pass

                db.add(IqcInspectionItem(
                    inspection_id=inspection.inspection_id,
                    template_item_id=ti.item_id,
                    sort_order=ti.sort_order,
                    category=ti.category,
                    item_name=ti.item_name,
                    inspect_type=ti.inspect_type,
                    spec_upper=ti.spec_upper,
                    spec_lower=ti.spec_lower,
                    target_value=ti.target_value,
                    sample_size=item_plan["sample_size"] if item_plan else ti.sample_size,
                    accept_no=item_plan["accept_number"] if item_plan else None,
                    reject_no=item_plan["reject_number"] if item_plan else None,
                ))

    if user_id:
        db.add(AuditLog(
            table_name="iqc_inspections",
            record_id=inspection.inspection_id,
            action="CREATE",
            changed_fields={"inspection_no": inspection_no, "mode": inspection_mode},
            operated_by=user_id,
        ))

    await db.commit()
    return await get_inspection(db, inspection.inspection_id)


async def update_inspection(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    user_id: uuid.UUID,
    **kwargs,
) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    if inspection.status != "pending":
        raise ValueError("仅待检验状态可编辑")

    changed = {}
    for key, new_val in kwargs.items():
        if new_val is not None and hasattr(inspection, key):
            old_val = getattr(inspection, key)
            if new_val != old_val:
                changed[key] = {"before": old_val, "after": new_val}
                setattr(inspection, key, new_val)

    if changed:
        db.add(AuditLog(
            table_name="iqc_inspections",
            record_id=inspection_id,
            action="UPDATE",
            changed_fields=changed,
            operated_by=user_id,
        ))
        await db.commit()
    return inspection


async def delete_inspection(db: AsyncSession, inspection_id: uuid.UUID, user_id: uuid.UUID) -> None:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    if inspection.status != "pending":
        raise ValueError("仅待检验状态可删除")

    db.add(AuditLog(
        table_name="iqc_inspections",
        record_id=inspection.inspection_id,
        action="DELETE",
        changed_fields={"inspection_no": inspection.inspection_no},
        operated_by=user_id,
    ))
    await db.delete(inspection)
    await db.commit()


# ─── State transitions ───

async def start_inspection(db: AsyncSession, inspection_id: uuid.UUID, user_id: uuid.UUID) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    new_status = _transition(inspection.status, "start")
    inspection.status = new_status
    inspection.inspected_by = user_id
    db.add(AuditLog(
        table_name="iqc_inspections",
        record_id=inspection_id,
        action="UPDATE",
        changed_fields={"status": {"before": "pending", "after": new_status}},
        operated_by=user_id,
    ))
    await db.commit()
    return inspection


async def update_items(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    items_data: list[dict],
    user_id: uuid.UUID,
) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    if inspection.status != "inspecting":
        raise ValueError("仅检验中状态可录入结果")

    for item_data in items_data:
        item_id = item_data.get("item_id")
        item = next((i for i in inspection.items if str(i.item_id) == item_id), None)
        if not item:
            continue

        if "defect_qty" in item_data:
            item.defect_qty = item_data["defect_qty"]
        if "result" in item_data:
            item.result = item_data["result"]
        if "remark" in item_data:
            item.remark = item_data.get("remark")

        measurements = item_data.get("measurements")
        if measurements:
            # Clear existing measurements
            for m in item.measurements:
                await db.delete(m)
            for m_data in measurements:
                db.add(IqcItemMeasurement(
                    item_id=item.item_id,
                    sequence_no=m_data.get("sequence_no", 1),
                    measured_value=m_data.get("measured_value"),
                    attribute_result=m_data.get("attribute_result"),
                    remark=m_data.get("remark"),
                ))

    db.add(AuditLog(
        table_name="iqc_inspections",
        record_id=inspection_id,
        action="UPDATE",
        changed_fields={"items_updated": True},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_inspection(db, inspection_id)


async def judge_inspection(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    inspection_result: str,
    defect_qty: int,
    defect_description: str | None,
    sample_qty: int | None,
    user_id: uuid.UUID,
    has_safety_defect: bool = False,
    linked_customer_complaint_id: uuid.UUID | None = None,
) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    new_status = _transition(inspection.status, "judge")
    inspection.status = new_status
    inspection.inspection_result = inspection_result
    inspection.defect_qty = defect_qty
    if defect_description:
        inspection.defect_description = defect_description
    if sample_qty is not None:
        inspection.sample_qty = sample_qty
    inspection.judged_by = user_id
    inspection.judged_at = datetime.now(timezone.utc)
    inspection.has_safety_defect = has_safety_defect
    if linked_customer_complaint_id:
        inspection.linked_customer_complaint_id = linked_customer_complaint_id

    db.add(AuditLog(
        table_name="iqc_inspections",
        record_id=inspection_id,
        action="UPDATE",
        changed_fields={
            "status": {"before": "inspecting", "after": new_status},
            "inspection_result": inspection_result,
            "defect_qty": defect_qty,
        },
        operated_by=user_id,
    ))
    await db.commit()

    # Trigger AQL rule evaluation after judgment
    if inspection.material_id:
        try:
            from app.services.iqc_aql_service import AqlService
            await AqlService.on_inspection_judged(db, inspection.supplier_id, inspection.material_id, inspection_id)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logging.getLogger(__name__).warning("AQL rule evaluation failed: %s", e)

    # Trigger incremental supplier risk evaluation
    import asyncio
    asyncio.create_task(_trigger_risk_eval(inspection.supplier_id, inspection.product_line_code))

    return inspection


async def request_reinspect(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    user_id: uuid.UUID,
) -> IqcInspection:
    """Clone-and-link: creates a new inspection from the rejected one."""
    original = await get_inspection(db, inspection_id)
    if not original:
        raise ValueError("检验单不存在")
    if original.status != "judged" or original.inspection_result != "rejected":
        raise ValueError("仅已拒收的检验单可申请复检")

    # Count existing re-inspections for suffix
    count_result = await db.execute(
        select(func.count()).where(IqcInspection.parent_inspection_id == inspection_id)
    )
    suffix_num = (count_result.scalar() or 0) + 1

    new_inspection = IqcInspection(
        inspection_no=f"{original.inspection_no}-R{suffix_num}",
        supplier_id=original.supplier_id,
        inspection_mode=original.inspection_mode,
        material_id=original.material_id,
        template_id=original.template_id,
        part_no=original.part_no,
        part_name=original.part_name,
        lot_no=original.lot_no,
        lot_qty=original.lot_qty,
        aql_level=original.aql_level,
        inspection_level=original.inspection_level,
        product_line_code=original.product_line_code,
        status="pending",
        inspection_result="pending",
        re_inspection=True,
        parent_inspection_id=inspection_id,
    )
    db.add(new_inspection)
    await db.flush()

    # Clone items for detailed mode
    if original.inspection_mode == "detailed" and original.items:
        for orig_item in original.items:
            new_item = IqcInspectionItem(
                inspection_id=new_inspection.inspection_id,
                template_item_id=orig_item.template_item_id,
                sort_order=orig_item.sort_order,
                category=orig_item.category,
                item_name=orig_item.item_name,
                inspect_type=orig_item.inspect_type,
                spec_upper=orig_item.spec_upper,
                spec_lower=orig_item.spec_lower,
                target_value=orig_item.target_value,
                sample_size=orig_item.sample_size,
                accept_no=orig_item.accept_no,
                reject_no=orig_item.reject_no,
            )
            db.add(new_item)

    # Recalculate AQL
    if new_inspection.lot_qty and original.aql_level:
        try:
            aql_val = float(original.aql_level)
            plan = calculate_aql_plan(new_inspection.lot_qty, aql_val, original.inspection_level or "II")
            new_inspection.code_letter = plan["code_letter"]
            new_inspection.sample_qty = plan["sample_size"]
            new_inspection.accept_number = plan["accept_number"]
            new_inspection.reject_number = plan["reject_number"]
        except ValueError:
            pass

    db.add(AuditLog(
        table_name="iqc_inspections",
        record_id=inspection_id,
        action="CREATE",
        changed_fields={"reinspection_no": new_inspection.inspection_no},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_inspection(db, new_inspection.inspection_id)


async def approve_concession(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    reason: str,
    user_id: uuid.UUID,
) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    if inspection.status != "judged" or inspection.inspection_result != "rejected":
        raise ValueError("仅已拒收的检验单可让步接收")

    inspection.inspection_result = "concession"
    inspection.defect_description = (
        f"让步接收原因: {reason}"
        if not inspection.defect_description
        else f"{inspection.defect_description}; 让步接收: {reason}"
    )
    db.add(AuditLog(
        table_name="iqc_inspections",
        record_id=inspection_id,
        action="UPDATE",
        changed_fields={"inspection_result": {"before": "rejected", "after": "concession"}, "reason": reason},
        operated_by=user_id,
    ))
    await db.commit()
    return inspection


async def close_inspection(
    db: AsyncSession, inspection_id: uuid.UUID, user_id: uuid.UUID
) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    new_status = _transition(inspection.status, "close")
    inspection.status = new_status
    db.add(AuditLog(
        table_name="iqc_inspections",
        record_id=inspection_id,
        action="UPDATE",
        changed_fields={"status": {"before": "judged", "after": new_status}},
        operated_by=user_id,
    ))
    await db.commit()
    return inspection


async def trigger_scar(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    user_id: uuid.UUID,
) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")

    # Generate SCAR number
    today = datetime.now(timezone.utc).strftime("%y%m%d")
    prefix = f"SCAR-{today}"
    result = await db.execute(
        select(func.count()).where(SupplierSCAR.scar_no.like(f"{prefix}-%"))
    )
    count = (result.scalar() or 0) + 1
    scar_no = f"{prefix}-{count:03d}"

    scar = SupplierSCAR(
        scar_no=scar_no,
        supplier_id=inspection.supplier_id,
        source_type="iqc",
        source_id=inspection_id,
        description=f"IQC 检验 {inspection.inspection_no} 拒收 — "
                    f"物料 {inspection.part_no or 'N/A'}、批号 {inspection.lot_no or 'N/A'}、"
                    f"缺陷数 {inspection.defect_qty}",
        requested_action=inspection.defect_description or None,
        status="open",
        issued_by=user_id,
        issued_date=date.today(),
    )
    db.add(scar)
    await db.flush()
    inspection.linked_scar_id = scar.scar_id

    db.add(AuditLog(
        table_name="iqc_inspections",
        record_id=inspection_id,
        action="UPDATE",
        changed_fields={"linked_scar_id": str(scar.scar_id)},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_inspection(db, inspection_id)


# ─── Stats ───

async def get_stats(
    db: AsyncSession,
    product_line_code: str | None = None,
    factory_id: uuid.UUID | None = None,
    allowed_product_line_codes: list[str] | None = None,
) -> dict:
    base = select(func.count(IqcInspection.inspection_id))
    if product_line_code:
        base = base.where(IqcInspection.product_line_code == product_line_code)
    if factory_id:
        base = base.where(IqcInspection.factory_id == factory_id)
    if allowed_product_line_codes is not None:
        base = base.where(IqcInspection.product_line_code.in_(allowed_product_line_codes))

    total = (await db.execute(base)).scalar() or 0

    accepted_q = base.where(IqcInspection.inspection_result == "accepted")
    accepted = (await db.execute(accepted_q)).scalar() or 0

    rejected_q = base.where(IqcInspection.inspection_result == "rejected")
    rejected = (await db.execute(rejected_q)).scalar() or 0

    concession_q = base.where(IqcInspection.inspection_result == "concession")
    concession = (await db.execute(concession_q)).scalar() or 0

    return {
        "total_inspections": total,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "concession_count": concession,
        "acceptance_rate": round(accepted / total * 100, 1) if total > 0 else 0,
        "rejection_rate": round(rejected / total * 100, 1) if total > 0 else 0,
    }
