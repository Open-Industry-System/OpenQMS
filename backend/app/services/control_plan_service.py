import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.fmea import FMEADocument
from app.models.audit import AuditLog
from app.schemas.control_plan import ControlPlanCreate, ControlPlanUpdate, ImportFromFMEARequest
from app.services.product_line_service import validate_product_line
from app.services.version_service import create_cp_version
from app.services.cp_validation.engine import CPValidationEngine
from app.database import async_session


async def _run_validation_background(cp_id: uuid.UUID, user_id: uuid.UUID, trigger: str) -> None:
    """Run CP validation in a background task with an isolated DB session."""
    async with async_session() as db:
        try:
            engine = CPValidationEngine()
            await engine.validate(db, cp_id, user_id, trigger=trigger)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Background CP validation failed for %s", cp_id)


async def create_audit_log(
    db: AsyncSession,
    user_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    detail: dict | None = None,
) -> AuditLog:
    """Create an AuditLog entry."""
    audit_log = AuditLog(
        table_name=target_type,
        record_id=target_id,
        action=action,
        changed_fields=detail or {},
        operated_by=user_id,
    )
    db.add(audit_log)
    return audit_log


async def generate_document_no(db: AsyncSession) -> str:
    """Return next CP-2026-XXX number based on count of existing control plans."""
    count_query = select(func.count(ControlPlan.cp_id))
    result = await db.execute(count_query)
    count = result.scalar() or 0
    next_num = count + 1
    return f"CP-2026-{next_num:03d}"


async def create_control_plan(
    db: AsyncSession, data: ControlPlanCreate, user_id: uuid.UUID, *, factory_id: uuid.UUID | None = None
) -> ControlPlan:
    """Create a new ControlPlan. Use provided document_no if given, else auto-generate."""
    await validate_product_line(db, data.product_line_code)
    document_no = data.document_no if data.document_no else await generate_document_no(db)

    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=document_no,
        title=data.title,
        product_line_code=data.product_line_code,
        fmea_ref_id=data.fmea_ref_id,
        phase=data.phase,
        part_no=data.part_no,
        part_name=data.part_name,
        contact_info=data.contact_info,
        drawing_rev=data.drawing_rev,
        org_factory=data.org_factory,
        core_group=data.core_group,
        created_by=user_id,
        updated_by=user_id,
        factory_id=factory_id,
    )
    db.add(cp)

    await create_audit_log(
        db,
        user_id=user_id,
        action="CREATE",
        target_type="control_plans",
        target_id=cp.cp_id,
        detail={
            "document_no": document_no,
            "title": data.title,
            "phase": data.phase,
        },
    )

    await db.commit()
    await db.refresh(cp)
    return cp


async def get_control_plan(db: AsyncSession, cp_id: uuid.UUID) -> ControlPlan | None:
    """Get a ControlPlan by UUID with items eagerly loaded."""
    result = await db.execute(
        select(ControlPlan)
        .options(selectinload(ControlPlan.items))
        .where(ControlPlan.cp_id == cp_id)
    )
    return result.scalar_one_or_none()


async def list_control_plans(
    db: AsyncSession, page: int = 1, page_size: int = 20, product_line: str | None = None,
    factory_id: uuid.UUID | None = None, allowed_product_lines: list[str] | None = None,
) -> dict:
    """Return paginated list of control plans."""
    query = (
        select(ControlPlan)
        .options(selectinload(ControlPlan.items))
        .order_by(ControlPlan.created_at.desc())
    )
    count_query = select(func.count(ControlPlan.cp_id))

    if product_line:
        query = query.where(ControlPlan.product_line_code == product_line)
        count_query = count_query.where(ControlPlan.product_line_code == product_line)
    if factory_id:
        query = query.where(ControlPlan.factory_id == factory_id)
        count_query = count_query.where(ControlPlan.factory_id == factory_id)
    if allowed_product_lines is not None:
        query = query.where(ControlPlan.product_line_code.in_(allowed_product_lines))
        count_query = count_query.where(ControlPlan.product_line_code.in_(allowed_product_lines))

    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def update_control_plan(
    db: AsyncSession,
    cp: ControlPlan,
    data: ControlPlanUpdate,
    user_id: uuid.UUID,
) -> ControlPlan:
    """Update control plan fields. Blocks update if status is approved."""
    if cp.status == "approved":
        raise ValueError("Cannot update an approved control plan.")

    lock_version = data.lock_version
    confirmed_latest_lock_version = data.confirmed_latest_lock_version

    # 原子乐观锁校验：强制刷新 + SELECT ... FOR UPDATE
    result = await db.execute(
        select(ControlPlan)
        .where(ControlPlan.cp_id == cp.cp_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    fresh = result.scalar_one()

    if confirmed_latest_lock_version is not None:
        if fresh.lock_version != confirmed_latest_lock_version:
            raise ValueError("lock_version_changed_again")
    elif lock_version is not None:
        if fresh.lock_version != lock_version:
            raise ValueError("lock_version_mismatch")

    if data.product_line_code is not None:
        await validate_product_line(db, data.product_line_code)

    changed_fields = {}

    for field in [
        "title",
        "document_no",
        "fmea_ref_id",
        "phase",
        "part_no",
        "part_name",
        "contact_info",
        "drawing_rev",
        "org_factory",
        "core_group",
        "product_line_code",
    ]:
        value = getattr(data, field, None)
        if value is not None and value != getattr(cp, field, None):
            changed_fields[field] = value
            setattr(cp, field, value)

    cp.updated_by = user_id

    # Handle items replacement if provided
    if data.items is not None:
        # Check if items actually changed before replacing
        items_result = await db.execute(
            select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id)
        )
        existing_items = list(items_result.scalars().all())
        items_changed = len(existing_items) != len(data.items)
        if not items_changed:
            import json
            for old, new in zip(existing_items, data.items):
                old_dict = {
                    k: getattr(old, k) for k in [
                        "step_no", "process_name", "equipment", "characteristic_no",
                        "product_characteristic", "process_characteristic", "special_class",
                        "specification_tolerance", "evaluation_method", "sample_size",
                        "sample_frequency", "control_method", "reaction_plan",
                        "source_fmea_node_id", "sort_order",
                    ]
                }
                new_dict = {
                    k: getattr(new, k) for k in [
                        "step_no", "process_name", "equipment", "characteristic_no",
                        "product_characteristic", "process_characteristic", "special_class",
                        "specification_tolerance", "evaluation_method", "sample_size",
                        "sample_frequency", "control_method", "reaction_plan",
                        "source_fmea_node_id", "sort_order",
                    ]
                }
                if json.dumps(old_dict, sort_keys=True) != json.dumps(new_dict, sort_keys=True):
                    items_changed = True
                    break

        if items_changed:
            for item in existing_items:
                await db.delete(item)

            for idx, item_data in enumerate(data.items):
                new_item = ControlPlanItem(
                    item_id=uuid.uuid4(),
                    cp_id=cp.cp_id,
                    step_no=item_data.step_no,
                    process_name=item_data.process_name,
                    equipment=item_data.equipment,
                    characteristic_no=item_data.characteristic_no,
                    product_characteristic=item_data.product_characteristic,
                    process_characteristic=item_data.process_characteristic,
                    special_class=item_data.special_class,
                    specification_tolerance=item_data.specification_tolerance,
                    evaluation_method=item_data.evaluation_method,
                    sample_size=item_data.sample_size,
                    sample_frequency=item_data.sample_frequency,
                    control_method=item_data.control_method,
                    reaction_plan=item_data.reaction_plan,
                    source_fmea_node_id=item_data.source_fmea_node_id,
                    sort_order=idx,
                )
                db.add(new_item)

            changed_fields["items_count"] = len(data.items)

    if changed_fields:
        cp.lock_version += 1  # 只在有实际变更时递增乐观锁版本
        await create_audit_log(
            db,
            user_id=user_id,
            action="UPDATE",
            target_type="control_plans",
            target_id=cp.cp_id,
            detail=changed_fields,
        )

        # 强制覆盖时记录审计日志
        if confirmed_latest_lock_version is not None:
            await create_audit_log(
                db,
                user_id=user_id,
                action="FORCE_SAVE_OVERRIDE",
                target_type="control_plans",
                target_id=cp.cp_id,
                detail={"reason": "User confirmed overwrite after conflict detection"},
            )

    await db.commit()
    await db.refresh(cp)

    # Trigger background validation only when fields actually changed
    if changed_fields:
        asyncio.create_task(
            _run_validation_background(cp.cp_id, user_id, trigger="auto_on_save")
        )

    return cp


async def delete_control_plan(
    db: AsyncSession, cp: ControlPlan, user_id: uuid.UUID
) -> None:
    """Delete a control plan and log the action."""
    cp_id = cp.cp_id
    await db.delete(cp)

    await create_audit_log(
        db,
        user_id=user_id,
        action="DELETE",
        target_type="control_plans",
        target_id=cp_id,
        detail={"document_no": cp.document_no, "title": cp.title},
    )

    await db.commit()


async def approve_control_plan(
    db: AsyncSession, cp: ControlPlan, user_id: uuid.UUID
) -> ControlPlan:
    """Approve a control plan. Validates all referenced gauges are active and calibrated."""
    if cp.status == "approved":
        raise ValueError("Control plan is already approved.")

    from app.services.gauge_service import validate_gauge_for_use
    for item in cp.items:
        if item.gauge_id:
            await validate_gauge_for_use(db, item.gauge_id)

    cp.status = "approved"
    cp.approved_by = user_id
    cp.approved_at = datetime.now(timezone.utc)
    cp.updated_by = user_id

    # Create version snapshot on approve
    await create_cp_version(db, cp, "approve", "审批通过，版本发布", user_id)

    await create_audit_log(
        db,
        user_id=user_id,
        action="APPROVE",
        target_type="control_plans",
        target_id=cp.cp_id,
        detail={"old_status": "draft", "new_status": "approved"},
    )

    await db.commit()
    await db.refresh(cp)
    return cp


async def import_from_fmea(
    db: AsyncSession, cp_id: uuid.UUID, req: ImportFromFMEARequest, user_id: uuid.UUID
) -> list[ControlPlanItem]:
    """Import PFMEA process step topology into control plan items.

    Traverses the PFMEA graph to map:
      ProcessStep                  → step_no, process_name
      ProcessWorkElement           → equipment
      ProcessStepFunction          → product_characteristic, specification_tolerance, special_class
      ProcessWorkElementFunction   → process_characteristic
    """
    # Validate control plan exists and is editable
    cp_result = await db.execute(select(ControlPlan).where(ControlPlan.cp_id == cp_id))
    cp = cp_result.scalar_one_or_none()
    if cp is None:
        raise ValueError("Control plan not found.")
    if cp.status == "approved":
        raise ValueError("Cannot import into an approved control plan.")

    # Validate FMEA exists and is PFMEA
    fmea_result = await db.execute(
        select(FMEADocument).where(FMEADocument.fmea_id == req.fmea_id)
    )
    fmea = fmea_result.scalar_one_or_none()
    if fmea is None:
        raise ValueError("FMEA document not found.")
    if fmea.fmea_type != "PFMEA":
        raise ValueError("Only PFMEA documents can be imported into a control plan.")

    graph = fmea.graph_data or {"nodes": [], "edges": []}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    # Filter ProcessStep nodes
    step_nodes = [n for n in nodes if n.get("type") == "ProcessStep"]

    # If step_nos provided, further filter
    if req.step_nos is not None:
        step_nodes = [
            n for n in step_nodes if n.get("process_number") in req.step_nos
        ]

    # Build edge maps: source -> [targets], target -> [sources]
    edge_map: dict[str, list[str]] = {}
    for e in edges:
        src = e.get("source")
        tgt = e.get("target")
        if src is not None:
            edge_map.setdefault(src, []).append(tgt)

    node_map = {n.get("id"): n for n in nodes if n.get("id") is not None}

    def _children(parent_id: str, node_type: str) -> list[dict]:
        """Find direct children of given type via edges."""
        return [
            node_map[t]
            for t in edge_map.get(parent_id, [])
            if node_map.get(t, {}).get("type") == node_type
        ]

    created_items: list[ControlPlanItem] = []
    sort_idx = 0

    for step in step_nodes:
        step_id = step.get("id")
        step_no = step.get("process_number") or ""
        process_name = step.get("name") or ""

        # Structural: process work elements (4M) → equipment
        work_elements = _children(step_id, "ProcessWorkElement")

        # Functional: product characteristic functions
        step_functions = _children(step_id, "ProcessStepFunction")

        # For each work element, find its process characteristic functions
        we_func_map: dict[str, list[dict]] = {}
        for we in work_elements:
            we_funcs = _children(we.get("id"), "ProcessWorkElementFunction")
            if we_funcs:
                we_func_map[we.get("id")] = we_funcs

        # Build CP items by pairing product + process characteristics
        if step_functions:
            for sf in step_functions:
                sf_id = sf.get("id")
                # Find WEFs linked to this step function via FUNCTION_MAPPED_TO
                mapped_wef_ids = set(edge_map.get(sf_id, []))

                # Match WEFs against work elements
                matched_we = None
                matched_wf = None
                for we in work_elements:
                    for wf in we_func_map.get(we.get("id"), []):
                        if wf.get("id") in mapped_wef_ids or matched_wf is None:
                            matched_we = we
                            matched_wf = wf
                            if wf.get("id") in mapped_wef_ids:
                                break
                    if matched_wf and matched_wf.get("id") in mapped_wef_ids:
                        break

                item = ControlPlanItem(
                    item_id=uuid.uuid4(),
                    cp_id=cp_id,
                    step_no=step_no,
                    process_name=process_name,
                    equipment=matched_we.get("name") if matched_we else None,
                    product_characteristic=sf.get("name") or "",
                    specification_tolerance=sf.get("specification") or "",
                    special_class=sf.get("classification") or "",
                    process_characteristic=matched_wf.get("name") if matched_wf else None,
                    source_fmea_node_id=step_id,
                    sort_order=sort_idx,
                )
                db.add(item)
                created_items.append(item)
                sort_idx += 1
        elif work_elements:
            # No step functions — create items from work element functions
            for we in work_elements:
                we_funcs = we_func_map.get(we.get("id"), [])
                if we_funcs:
                    for wf in we_funcs:
                        item = ControlPlanItem(
                            item_id=uuid.uuid4(),
                            cp_id=cp_id,
                            step_no=step_no,
                            process_name=process_name,
                            equipment=we.get("name") or "",
                            process_characteristic=wf.get("name") or "",
                            source_fmea_node_id=step_id,
                            sort_order=sort_idx,
                        )
                        db.add(item)
                        created_items.append(item)
                        sort_idx += 1
                else:
                    item = ControlPlanItem(
                        item_id=uuid.uuid4(),
                        cp_id=cp_id,
                        step_no=step_no,
                        process_name=process_name,
                        equipment=we.get("name") or "",
                        source_fmea_node_id=step_id,
                        sort_order=sort_idx,
                    )
                    db.add(item)
                    created_items.append(item)
                    sort_idx += 1
        else:
            # Minimal item with just process step info
            item = ControlPlanItem(
                item_id=uuid.uuid4(),
                cp_id=cp_id,
                step_no=step_no,
                process_name=process_name,
                source_fmea_node_id=step_id,
                sort_order=sort_idx,
            )
            db.add(item)
            created_items.append(item)
            sort_idx += 1

    # Link control plan to FMEA
    cp.fmea_ref_id = req.fmea_id
    cp.updated_by = user_id

    await create_audit_log(
        db,
        user_id=user_id,
        action="IMPORT_FMEA",
        target_type="control_plans",
        target_id=cp_id,
        detail={
            "fmea_id": str(req.fmea_id),
            "fmea_document_no": fmea.document_no,
            "items_created": len(created_items),
        },
    )

    await db.commit()
    for item in created_items:
        await db.refresh(item)
    return created_items


async def check_stale_items(
    db: AsyncSession, cp_id: uuid.UUID
) -> list[dict]:
    """Check for stale control plan items by comparing against linked FMEA graph.

    Compares process_name, step_no, and all functional/structural fields
    (product_characteristic, process_characteristic, specification_tolerance,
    special_class, equipment) derived from graph topology.
    """
    cp_result = await db.execute(
        select(ControlPlan).where(ControlPlan.cp_id == cp_id)
    )
    cp = cp_result.scalar_one_or_none()
    if cp is None:
        raise ValueError("Control plan not found.")

    if cp.fmea_ref_id is None:
        return []

    fmea_result = await db.execute(
        select(FMEADocument).where(FMEADocument.fmea_id == cp.fmea_ref_id)
    )
    fmea = fmea_result.scalar_one_or_none()
    if fmea is None:
        return []

    graph = fmea.graph_data or {"nodes": [], "edges": []}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_map = {n.get("id"): n for n in nodes if n.get("id") is not None}

    edge_map: dict[str, list[str]] = {}
    for e in edges:
        src = e.get("source")
        if src is not None:
            edge_map.setdefault(src, []).append(e.get("target"))

    items_result = await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == cp_id)
    )
    items = list(items_result.scalars().all())

    def _children(parent_id: str, node_type: str) -> list[dict]:
        return [
            node_map[t]
            for t in edge_map.get(parent_id, [])
            if node_map.get(t, {}).get("type") == node_type
        ]

    stale_items: list[dict] = []

    for item in items:
        if not item.source_fmea_node_id:
            continue

        node = node_map.get(item.source_fmea_node_id)
        if node is None:
            stale_items.append({
                "item_id": str(item.item_id),
                "step_no": item.step_no,
                "status": "deleted",
                "diff_fields": ["node_missing"],
            })
            continue

        diff_fields: list[str] = []

        # Check structural fields
        if (node.get("name") or "") != (item.process_name or ""):
            diff_fields.append("process_name")
        if (node.get("process_number") or "") != (item.step_no or ""):
            diff_fields.append("step_no")

        # Check derived product characteristic fields from ProcessStepFunction
        step_funcs = _children(item.source_fmea_node_id, "ProcessStepFunction")
        if step_funcs:
            # Match by product_characteristic name
            for sf in step_funcs:
                if sf.get("name") == item.product_characteristic:
                    if (sf.get("specification") or "") != (item.specification_tolerance or ""):
                        diff_fields.append("specification_tolerance")
                    if (sf.get("classification") or "") != (item.special_class or ""):
                        diff_fields.append("special_class")
                    break

        # Check equipment from ProcessWorkElement
        work_elements = _children(item.source_fmea_node_id, "ProcessWorkElement")
        if item.equipment and work_elements:
            if not any(we.get("name") == item.equipment for we in work_elements):
                diff_fields.append("equipment")

        # Check process characteristic from ProcessWorkElementFunction
        for we in work_elements:
            we_funcs = _children(we.get("id"), "ProcessWorkElementFunction")
            if item.process_characteristic and we_funcs:
                if not any(wf.get("name") == item.process_characteristic for wf in we_funcs):
                    diff_fields.append("process_characteristic")
                    break

        if diff_fields:
            stale_items.append({
                "item_id": str(item.item_id),
                "step_no": item.step_no,
                "status": "modified",
                "diff_fields": diff_fields,
            })

    return stale_items


async def mark_cp_sync_pending_on_fmea_approve(
    db: AsyncSession, fmea_id: uuid.UUID, fmea_version_id: uuid.UUID
) -> list[ControlPlan]:
    """Mark all linked CPs as sync pending when FMEA is approved.

    NOTE: All FMEA-CP sync logic is consolidated in version_service.py's
    build_sync_preview and apply_sync_preview. Do NOT create separate sync
    functions here to avoid architectural redundancy.
    """
    result = await db.execute(
        select(ControlPlan).where(ControlPlan.fmea_ref_id == fmea_id)
    )
    cps = list(result.scalars().all())
    for cp in cps:
        if cp.source_fmea_version_id != fmea_version_id:
            cp.sync_pending = True
    await db.commit()
    return cps


# ─── CSR Sync ───

async def sync_csr_to_control_plan(
    db: AsyncSession,
    plan_id: uuid.UUID,
    customer_ids: list[uuid.UUID],
    user_id: uuid.UUID,
):
    from app.models.audit import AuditLog
    from app.models.customer_quality import Customer
    from app.models.control_plan import ControlPlan

    # 1. Query control plan
    result = await db.execute(select(ControlPlan).where(ControlPlan.cp_id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise ValueError("控制计划不存在")

    # 2. Query customer CSR
    result = await db.execute(select(Customer).where(Customer.customer_id.in_(customer_ids)))
    customers = result.scalars().all()

    # 3. Build CSR map keyed by (source_customer_id, title)
    new_csr_map: dict[tuple, dict] = {}
    for customer in customers:
        if customer.csr_list:
            for item in customer.csr_list:
                key = (str(customer.customer_id), item.get("title", ""))
                new_csr_map[key] = {
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "source_customer_id": str(customer.customer_id),
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                    "source": "csr",
                }

    # 4. Preserve existing manual items
    existing = plan.customer_requirements or []
    manual_items = [item for item in existing if item.get("source") == "manual"]

    # 5. Merge: csr items replace, manual items preserved
    merged = list(new_csr_map.values()) + manual_items
    plan.customer_requirements = merged

    # AuditLog
    audit = AuditLog(
        table_name="control_plans",
        record_id=plan_id,
        action="SYNC_CSR",
        changed_fields={"customer_ids": [str(cid) for cid in customer_ids], "csr_count": len(new_csr_map)},
        operated_by=user_id,
    )
    db.add(audit)

    await db.commit()
    return plan
