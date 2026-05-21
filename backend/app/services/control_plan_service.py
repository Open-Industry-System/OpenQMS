import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.fmea import FMEADocument
from app.models.audit import AuditLog
from app.schemas.control_plan import ControlPlanCreate, ControlPlanUpdate, ImportFromFMEARequest


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
    db: AsyncSession, data: ControlPlanCreate, user_id: uuid.UUID
) -> ControlPlan:
    """Create a new ControlPlan with auto-generated document number."""
    document_no = await generate_document_no(db)

    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=document_no,
        title=data.title,
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
    """Get a ControlPlan by UUID."""
    result = await db.execute(select(ControlPlan).where(ControlPlan.cp_id == cp_id))
    return result.scalar_one_or_none()


async def list_control_plans(
    db: AsyncSession, page: int = 1, page_size: int = 20
) -> dict:
    """Return paginated list of control plans."""
    query = select(ControlPlan).order_by(ControlPlan.created_at.desc())
    count_query = select(func.count(ControlPlan.cp_id))

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
    ]:
        value = getattr(data, field, None)
        if value is not None:
            changed_fields[field] = value
            setattr(cp, field, value)

    cp.updated_by = user_id

    # Handle items replacement if provided
    if data.items is not None:
        # Delete existing items
        items_result = await db.execute(
            select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id)
        )
        existing_items = list(items_result.scalars().all())
        for item in existing_items:
            await db.delete(item)

        # Create new items
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
        await create_audit_log(
            db,
            user_id=user_id,
            action="UPDATE",
            target_type="control_plans",
            target_id=cp.cp_id,
            detail=changed_fields,
        )

    await db.commit()
    await db.refresh(cp)
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
    """Approve a control plan."""
    if cp.status == "approved":
        raise ValueError("Control plan is already approved.")

    cp.status = "approved"
    cp.approved_by = user_id
    cp.approved_at = datetime.now(timezone.utc)
    cp.updated_by = user_id

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
    """Import ProcessStep nodes from a PFMEA into control plan items."""
    # Validate control plan exists
    cp_result = await db.execute(select(ControlPlan).where(ControlPlan.cp_id == cp_id))
    cp = cp_result.scalar_one_or_none()
    if cp is None:
        raise ValueError("Control plan not found.")

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

    # Build edge map: source -> [targets]
    edge_map: dict[str, list[str]] = {}
    for e in edges:
        src = e.get("source")
        tgt = e.get("target")
        if src is not None:
            edge_map.setdefault(src, []).append(tgt)

    node_map = {n.get("id"): n for n in nodes if n.get("id") is not None}

    created_items: list[ControlPlanItem] = []

    for idx, step in enumerate(step_nodes):
        step_id = step.get("id")
        step_no = step.get("process_number") or ""
        process_name = step.get("name") or ""

        targets = edge_map.get(step_id, [])
        work_elements = [
            node_map.get(t)
            for t in targets
            if node_map.get(t, {}).get("type") == "ProcessWorkElement"
        ]
        work_elements = [w for w in work_elements if w is not None]

        if work_elements:
            for w in work_elements:
                item = ControlPlanItem(
                    item_id=uuid.uuid4(),
                    cp_id=cp_id,
                    step_no=step_no,
                    process_name=process_name,
                    equipment=w.get("name") or "",
                    source_fmea_node_id=step_id,
                    sort_order=idx,
                )
                db.add(item)
                created_items.append(item)
        else:
            # Create item even if no work elements found
            item = ControlPlanItem(
                item_id=uuid.uuid4(),
                cp_id=cp_id,
                step_no=step_no,
                process_name=process_name,
                source_fmea_node_id=step_id,
                sort_order=idx,
            )
            db.add(item)
            created_items.append(item)

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

    Returns list of dicts with item_id, step_no, status, diff_fields.
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
    node_map = {n.get("id"): n for n in nodes if n.get("id") is not None}

    items_result = await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == cp_id)
    )
    items = list(items_result.scalars().all())

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

        node_name = node.get("name") or ""
        if node_name != (item.process_name or ""):
            diff_fields.append("process_name")

        node_process_number = node.get("process_number") or ""
        if node_process_number != (item.step_no or ""):
            diff_fields.append("step_no")

        if diff_fields:
            stale_items.append({
                "item_id": str(item.item_id),
                "step_no": item.step_no,
                "status": "modified",
                "diff_fields": diff_fields,
            })

    return stale_items
