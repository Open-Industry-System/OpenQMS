import uuid
from datetime import datetime
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from app.models.special_characteristic import SpecialCharacteristic
from app.models.fmea import FMEADocument
from app.models.control_plan import ControlPlanItem, ControlPlan
from app.models.audit import AuditLog
from app.schemas.special_characteristic import (
    SCCreate, SCUpdate, SCResponse, SCListResponse,
    MatrixRow, MatrixResponse, SeverityWarning, CPSyncStatusItem, CPSyncStatusResponse,
    SafetySubmitRequest, SafetyApprovalAction,
)


from enum import Enum


class SafetyApprovalStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


SAFETY_APPROVAL_TRANSITIONS: dict[SafetyApprovalStatus, list[SafetyApprovalStatus]] = {
    SafetyApprovalStatus.PENDING: [SafetyApprovalStatus.SUBMITTED],
    SafetyApprovalStatus.SUBMITTED: [SafetyApprovalStatus.APPROVED, SafetyApprovalStatus.REJECTED],
    SafetyApprovalStatus.APPROVED: [SafetyApprovalStatus.PENDING],
    SafetyApprovalStatus.REJECTED: [SafetyApprovalStatus.SUBMITTED],
}


def _can_safety_transition(current: SafetyApprovalStatus | None, target: SafetyApprovalStatus) -> bool:
    if current is None:
        return target == SafetyApprovalStatus.PENDING
    return target in SAFETY_APPROVAL_TRANSITIONS.get(current, [])


async def generate_sc_code(db: AsyncSession) -> str:
    year = datetime.utcnow().year
    prefix = f"SC-{year}-"
    result = await db.execute(
        select(func.max(SpecialCharacteristic.sc_code))
        .where(SpecialCharacteristic.sc_code.like(f"{prefix}%"))
    )
    max_code = result.scalar()
    if max_code:
        next_num = int(max_code.replace(prefix, "")) + 1
    else:
        next_num = 1
    return f"{prefix}{next_num:03d}"


async def list_special_characteristics(
    db: AsyncSession, sc_type: str | None = None,
    product_line: str | None = None, source_type: str | None = None,
    page: int = 1, page_size: int = 20,
    safety_related_only: bool = False,
    approval_status: str | None = None,
    suggested_only: bool = False,
) -> SCListResponse:
    query = select(SpecialCharacteristic).order_by(SpecialCharacteristic.created_at.desc())
    if sc_type:
        query = query.where(SpecialCharacteristic.sc_type == sc_type)
    if product_line:
        query = query.where(SpecialCharacteristic.product_line_code == product_line)
    if source_type:
        query = query.where(SpecialCharacteristic.source_type == source_type)
    if safety_related_only:
        query = query.where(SpecialCharacteristic.is_safety_related == True)
    if approval_status:
        query = query.where(SpecialCharacteristic.safety_approval_status == approval_status)
    if suggested_only:
        query = query.where(SpecialCharacteristic.is_safety_suggested == True)
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = result.scalars().all()
    return SCListResponse(items=[_to_response(i) for i in items], total=total, page=page, page_size=page_size)


async def get_special_characteristic(db: AsyncSession, sc_id: uuid.UUID) -> SCResponse | None:
    result = await db.execute(select(SpecialCharacteristic).where(SpecialCharacteristic.sc_id == sc_id))
    item = result.scalar_one_or_none()
    return _to_response(item) if item else None


async def create_special_characteristic(db: AsyncSession, data: SCCreate, user_id: uuid.UUID) -> SCResponse:
    sc_code = await generate_sc_code(db)
    item = SpecialCharacteristic(
        sc_code=sc_code, sc_name=data.sc_name, sc_type=data.sc_type,
        customer_symbol=data.customer_symbol, sc_category=data.sc_category,
        spec_requirement=data.spec_requirement, source_fmea_id=data.source_fmea_id,
        source_node_id=data.source_node_id or "", source_type=data.source_type or "PFMEA",
        sop_ref=data.sop_ref, product_line_code=data.product_line_code, created_by=user_id,
    )
    db.add(item)
    await _create_audit(db, "CREATE", item.sc_id, user_id, {"sc_code": sc_code, "sc_name": data.sc_name})
    await db.commit()
    await db.refresh(item)
    return _to_response(item)


async def update_special_characteristic(
    db: AsyncSession, sc_id: uuid.UUID, data: SCUpdate, user_id: uuid.UUID,
) -> SCResponse | None:
    result = await db.execute(select(SpecialCharacteristic).where(SpecialCharacteristic.sc_id == sc_id))
    item = result.scalar_one_or_none()
    if not item:
        return None
    changes = {}
    for field, value in data.model_dump(exclude_unset=True).items():
        if getattr(item, field) != value:
            changes[field] = {"old": getattr(item, field), "new": value}
            setattr(item, field, value)
    if changes:
        await _create_audit(db, "UPDATE", sc_id, user_id, changes)
    await db.commit()
    await db.refresh(item)
    return _to_response(item)


async def delete_special_characteristic(db: AsyncSession, sc_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await db.execute(select(SpecialCharacteristic).where(SpecialCharacteristic.sc_id == sc_id))
    item = result.scalar_one_or_none()
    if not item:
        return False
    if item.source_fmea_id and item.source_node_id:
        fmea_result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == item.source_fmea_id))
        fmea = fmea_result.scalar_one_or_none()
        if fmea and fmea.graph_data:
            graph = fmea.graph_data if isinstance(fmea.graph_data, dict) else {}
            nodes = graph.get("nodes", [])
            for node in nodes:
                if node.get("id") == item.source_node_id:
                    node["classification"] = ""
                    break
            fmea.graph_data = graph
            flag_modified(fmea, "graph_data")
    await _create_audit(db, "DELETE", sc_id, user_id, {"sc_code": item.sc_code})
    await db.delete(item)
    await db.commit()
    return True


async def sync_from_fmea(db: AsyncSession, fmea_id: uuid.UUID, user_id: uuid.UUID) -> list[SCResponse]:
    fmea_result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
    fmea = fmea_result.scalar_one_or_none()
    if not fmea:
        raise ValueError("FMEA document not found")
    graph = fmea.graph_data if isinstance(fmea.graph_data, dict) else {}
    nodes = graph.get("nodes", [])
    source_type = "DFMEA" if fmea.fmea_type == "DFMEA" else "PFMEA"
    nodes_to_sync = {n["id"]: n for n in nodes if n.get("classification") in ("CC", "SC") or n.get("severity", 0) >= 9}
    existing_result = await db.execute(
        select(SpecialCharacteristic).where(SpecialCharacteristic.source_fmea_id == fmea_id)
    )
    existing = {sc.source_node_id: sc for sc in existing_result.scalars().all()}
    # Severity drop detection: find existing safety SCs whose node severity dropped below 9
    for node_id, sc in existing.items():
        node = nodes_to_sync.get(node_id)
        if sc.is_safety_related and node and node.get("severity", 0) < 9:
            if sc.safety_approval_status == SafetyApprovalStatus.APPROVED.value:
                await _create_audit(db, "SAFETY_SEVERITY_DROP", sc.sc_id, user_id, {
                    "sc_code": sc.sc_code,
                    "warning": "FMEA严重度已下降至8，请手动评估是否保留安全属性",
                    "previous_severity": 9,
                    "current_severity": node.get("severity", 0),
                })
            elif sc.safety_approval_status in (SafetyApprovalStatus.PENDING.value, SafetyApprovalStatus.SUBMITTED.value, SafetyApprovalStatus.REJECTED.value):
                await _create_audit(db, "SAFETY_SEVERITY_DROP", sc.sc_id, user_id, {
                    "sc_code": sc.sc_code,
                    "warning": "FMEA严重度已下降至8，但该安全特性处于审批流程中，请人工评估",
                })
    created_or_updated = []
    for node_id, node in nodes_to_sync.items():
        sc_type = node.get("classification") or "CC"
        if node_id in existing:
            sc = existing[node_id]
            if sc.sc_type != sc_type:
                sc.sc_type = sc_type
            if sc.sc_name != node.get("name", ""):
                sc.sc_name = node.get("name", "")
            # Auto-suggest safety for severity >= 9 CC nodes not yet safety-related
            if node.get("severity", 0) >= 9 and sc_type == "CC" and not sc.is_safety_related:
                sc.is_safety_suggested = True
            created_or_updated.append(_to_response(sc))
        else:
            sc_code = await generate_sc_code(db)
            parent_sc_id = None
            if source_type == "PFMEA":
                parent_result = await db.execute(
                    select(SpecialCharacteristic).where(
                        and_(SpecialCharacteristic.source_type == "DFMEA",
                             SpecialCharacteristic.sc_name == node.get("name", ""))
                    ).limit(1)
                )
                parent_sc = parent_result.scalar_one_or_none()
                if parent_sc:
                    parent_sc_id = parent_sc.sc_id
            sc = SpecialCharacteristic(
                sc_code=sc_code, sc_name=node.get("name", ""), sc_type=sc_type,
                source_fmea_id=fmea_id, source_node_id=node_id, source_type=source_type,
                parent_sc_id=parent_sc_id, product_line_code=fmea.product_line_code,
                created_by=user_id,
                is_safety_suggested=node.get("severity", 0) >= 9 and sc_type == "CC",
            )
            db.add(sc)
            created_or_updated.append(_to_response(sc))
    for node_id, sc in existing.items():
        if node_id not in nodes_to_sync:
            if sc.is_safety_related:
                # Intercept: don't auto-delete safety characteristics
                await _create_audit(db, "SAFETY_DELETE_WARNING", sc.sc_id, user_id, {
                    "sc_code": sc.sc_code,
                    "warning": "FMEA中关联节点已变更，但该特性为安全特性，系统已拦截自动删除，请人工评估并处理",
                })
            else:
                await db.delete(sc)
    await _create_audit(db, "SYNC", fmea_id, user_id, {
        "action": "sync_from_fmea",
        "classified_count": len(nodes_to_sync),
        "deleted_count": len([n for n in existing if n not in nodes_to_sync]),
    })
    await db.commit()
    return created_or_updated


async def sync_to_cp(db: AsyncSession, cp_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
    """Sync special_class from characteristics table to CP items.

    CRITICAL: CP items store source_fmea_node_id = ProcessStep node ID,
    but special_characteristics store source_node_id = FailureMode node ID.
    Must traverse FMEA graph edges: ProcessStep -> ... -> FailureMode
    """
    cp_result = await db.execute(select(ControlPlan).where(ControlPlan.cp_id == cp_id))
    cp = cp_result.scalar_one_or_none()
    if not cp:
        raise ValueError("Control plan not found")
    if not cp.fmea_ref_id:
        return []

    # Get characteristics indexed by FailureMode node ID
    scs_result = await db.execute(
        select(SpecialCharacteristic).where(SpecialCharacteristic.source_fmea_id == cp.fmea_ref_id)
    )
    scs = {sc.source_node_id: sc for sc in scs_result.scalars().all()}

    # Build FMEA graph: ProcessStep node ID -> FailureMode node IDs
    fmea_result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == cp.fmea_ref_id))
    fmea = fmea_result.scalar_one_or_none()
    graph = fmea.graph_data if fmea and fmea.graph_data and isinstance(fmea.graph_data, dict) else {}
    step_to_fms: dict[str, list[str]] = {}
    for edge in graph.get("edges", []):
        if edge.get("type") == "HAS_FAILURE_MODE":
            func_node_id = edge.get("source", "")
            fm_node_id = edge.get("target", "")
            for e2 in graph.get("edges", []):
                if e2.get("target") == func_node_id and e2.get("type") in ("HAS_FUNCTION", "FUNCTION_MAPPED_TO"):
                    step_node_id = e2.get("source", "")
                    step_to_fms.setdefault(step_node_id, []).append(fm_node_id)

    items_result = await db.execute(select(ControlPlanItem).where(ControlPlanItem.cp_id == cp_id))
    items = items_result.scalars().all()

    updated = []
    for item in items:
        step_node_id = item.source_fmea_node_id or ""
        matched = False
        for fm_id in step_to_fms.get(step_node_id, []):
            if fm_id in scs:
                sc = scs[fm_id]
                new_special_class = sc.sc_type
                if item.special_class != new_special_class:
                    item.special_class = new_special_class
                    sc.cp_item_id = item.item_id
                    updated.append({
                        "item_id": str(item.item_id), "step_no": item.step_no,
                        "old": item.special_class, "new": new_special_class,
                    })
                matched = True
                break
        if not matched and step_node_id in scs:
            sc = scs[step_node_id]
            new_special_class = sc.sc_type
            if item.special_class != new_special_class:
                item.special_class = new_special_class
                sc.cp_item_id = item.item_id
                updated.append({
                    "item_id": str(item.item_id), "step_no": item.step_no,
                    "old": item.special_class, "new": new_special_class,
                })

    await _create_audit(db, "SYNC", cp_id, user_id, {
        "action": "sync_to_cp", "updated_count": len(updated),
    })
    await db.commit()
    return updated


async def get_matrix(db: AsyncSession, product_line: str | None = None) -> MatrixResponse:
    query = select(SpecialCharacteristic).order_by(SpecialCharacteristic.created_at)
    if product_line:
        query = query.where(SpecialCharacteristic.product_line_code == product_line)
    result = await db.execute(query)
    all_scs = result.scalars().all()
    roots = [sc for sc in all_scs if sc.parent_sc_id is None]
    children_map: dict[uuid.UUID, list] = {}
    for sc in all_scs:
        if sc.parent_sc_id:
            children_map.setdefault(sc.parent_sc_id, []).append(sc)
    rows = []
    for root in roots:
        children = children_map.get(root.sc_id, [])
        dfmea_sc = root if root.source_type == "DFMEA" else None
        pfmea_scs = [c for c in children if c.source_type == "PFMEA"]
        pfmea_sc = pfmea_scs[0] if pfmea_scs else None
        has_cp = any(sc.cp_item_id is not None for sc in [root] + children)
        has_sop = any(sc.sop_ref for sc in [root] + children)
        msa_statuses = [sc.msa_status or "PENDING" for sc in [root] + children]
        overall_msa = "PASS" if any(s == "PASS" for s in msa_statuses) else ("FAIL" if any(s == "FAIL" for s in msa_statuses) else "PENDING")
        rows.append(MatrixRow(
            sc_id=root.sc_id, sc_code=root.sc_code, sc_name=root.sc_name,
            sc_type=root.sc_type, customer_symbol=root.customer_symbol,
            product_line_code=root.product_line_code,
            is_safety_related=root.is_safety_related,
            has_dfmea=dfmea_sc is not None or root.source_type == "DFMEA",
            has_pfmea=pfmea_sc is not None or root.source_type == "PFMEA",
            has_cp=has_cp, msa_status=overall_msa, has_sop=has_sop,
            dfmea_link=f"/fmea/{root.source_fmea_id}" if root.source_type == "DFMEA" and root.source_fmea_id else (f"/fmea/{dfmea_sc.source_fmea_id}" if dfmea_sc and dfmea_sc.source_fmea_id else None),
            pfmea_link=f"/fmea/{pfmea_sc.source_fmea_id}" if pfmea_sc and pfmea_sc.source_fmea_id else None,
            cp_link=f"/control-plans/{root.cp_item_id}" if root.cp_item_id else None,
            msa_link=None,
        ))
    for sc in all_scs:
        if sc.parent_sc_id is None:
            continue
        if sc not in [c for cs in children_map.values() for c in cs]:
            rows.append(MatrixRow(
                sc_id=sc.sc_id, sc_code=sc.sc_code, sc_name=sc.sc_name,
                sc_type=sc.sc_type, customer_symbol=sc.customer_symbol,
                product_line_code=sc.product_line_code,
                is_safety_related=sc.is_safety_related,
                has_dfmea=False, has_pfmea=sc.source_type == "PFMEA",
                has_cp=sc.cp_item_id is not None, msa_status=sc.msa_status or "PENDING",
                has_sop=bool(sc.sop_ref), dfmea_link=None,
                pfmea_link=f"/fmea/{sc.source_fmea_id}" if sc.source_fmea_id else None,
                cp_link=f"/control-plans/{sc.cp_item_id}" if sc.cp_item_id else None,
                msa_link=None,
            ))
    return MatrixResponse(characteristics=rows)


async def check_severity_compliance(db: AsyncSession, fmea_id: uuid.UUID) -> list[SeverityWarning]:
    fmea_result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
    fmea = fmea_result.scalar_one_or_none()
    if not fmea:
        return []
    graph = fmea.graph_data if isinstance(fmea.graph_data, dict) else {}
    nodes = graph.get("nodes", [])
    warnings = []
    for node in nodes:
        severity = node.get("severity", 0)
        classification = node.get("classification", "")
        if severity >= 8 and classification not in ("CC", "SC"):
            warnings.append(SeverityWarning(
                node_id=node["id"], node_name=node.get("name", ""),
                severity=severity, fmea_id=fmea_id, fmea_title=fmea.title,
            ))
    return warnings


async def update_msa_status(db: AsyncSession, sc_id: uuid.UUID, grr_percent: float) -> SCResponse | None:
    result = await db.execute(select(SpecialCharacteristic).where(SpecialCharacteristic.sc_id == sc_id))
    sc = result.scalar_one_or_none()
    if not sc:
        return None
    if grr_percent < 10:
        sc.msa_status = "PASS"
    elif grr_percent < 30:
        sc.msa_status = "PASS"
    else:
        sc.msa_status = "FAIL"
    await db.commit()
    await db.refresh(sc)
    return _to_response(sc)


async def check_cp_sync_status(db: AsyncSession, cp_id: uuid.UUID) -> CPSyncStatusResponse:
    """Check CP items vs FMEA FailureMode classifications (edge-based mapping)."""
    cp_result = await db.execute(select(ControlPlan).where(ControlPlan.cp_id == cp_id))
    cp = cp_result.scalar_one_or_none()
    if not cp or not cp.fmea_ref_id:
        return CPSyncStatusResponse(items=[], total_out_of_sync=0)

    fmea_result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == cp.fmea_ref_id))
    fmea = fmea_result.scalar_one_or_none()
    if not fmea:
        return CPSyncStatusResponse(items=[], total_out_of_sync=0)

    graph = fmea.graph_data if isinstance(fmea.graph_data, dict) else {}

    # Build ProcessStep -> FailureMode node mapping via graph edges
    step_to_fms: dict[str, list[str]] = {}
    for edge in graph.get("edges", []):
        if edge.get("type") == "HAS_FAILURE_MODE":
            func_node_id = edge.get("source", "")
            fm_node_id = edge.get("target", "")
            for e2 in graph.get("edges", []):
                if e2.get("target") == func_node_id and e2.get("type") in ("HAS_FUNCTION", "FUNCTION_MAPPED_TO"):
                    step_node_id = e2.get("source", "")
                    step_to_fms.setdefault(step_node_id, []).append(fm_node_id)

    scs_result = await db.execute(
        select(SpecialCharacteristic).where(SpecialCharacteristic.source_fmea_id == cp.fmea_ref_id)
    )
    sc_map = {sc.source_node_id: sc for sc in scs_result.scalars().all()}

    items_result = await db.execute(select(ControlPlanItem).where(ControlPlanItem.cp_id == cp_id))
    items = items_result.scalars().all()

    sync_items = []
    for item in items:
        if not item.source_fmea_node_id:
            continue
        step_node_id = item.source_fmea_node_id or ""
        expected_class = ""
        for fm_id in step_to_fms.get(step_node_id, []):
            if fm_id in sc_map:
                expected_class = sc_map[fm_id].sc_type
                break
        if not expected_class and step_node_id in sc_map:
            expected_class = sc_map[step_node_id].sc_type
        current = item.special_class or ""
        is_out = expected_class != current
        sync_items.append(CPSyncStatusItem(
            item_id=item.item_id, step_no=item.step_no,
            process_name=item.process_name,
            current_special_class=current or None,
            expected_special_class=expected_class or None,
            is_out_of_sync=is_out,
        ))

    return CPSyncStatusResponse(
        items=sync_items,
        total_out_of_sync=sum(1 for i in sync_items if i.is_out_of_sync),
    )


def _to_response(sc: SpecialCharacteristic) -> SCResponse:
    fmea_title = fmea_doc_no = None
    if sc.source_fmea:
        fmea_title = sc.source_fmea.title
        fmea_doc_no = sc.source_fmea.document_no
    return SCResponse(
        sc_id=sc.sc_id, sc_code=sc.sc_code, sc_name=sc.sc_name,
        sc_type=sc.sc_type, customer_symbol=sc.customer_symbol,
        sc_category=sc.sc_category, spec_requirement=sc.spec_requirement,
        parent_sc_id=sc.parent_sc_id, source_fmea_id=sc.source_fmea_id,
        source_fmea_title=fmea_title, source_fmea_document_no=fmea_doc_no,
        source_node_id=sc.source_node_id, source_type=sc.source_type,
        cp_item_id=sc.cp_item_id, msa_study_id=sc.msa_study_id,
        msa_status=sc.msa_status or "PENDING", sop_ref=sc.sop_ref,
        product_line_code=sc.product_line_code,
        is_supplier_shared=sc.is_supplier_shared or False,
        supplier_code=sc.supplier_code, created_by=sc.created_by,
        created_at=sc.created_at,
        # Safety fields
        is_safety_related=sc.is_safety_related,
        is_safety_suggested=sc.is_safety_suggested,
        safety_approval_status=sc.safety_approval_status,
        safety_submitted_by=sc.safety_submitted_by,
        safety_submitted_at=sc.safety_submitted_at,
        safety_approved_by=sc.safety_approved_by,
        safety_approved_at=sc.safety_approved_at,
        safety_approval_comment=sc.safety_approval_comment,
        safety_regulation_ref=sc.safety_regulation_ref,
        safety_verification_method=sc.safety_verification_method,
        updated_at=sc.updated_at,
    )


async def safety_submit(
    db: AsyncSession, sc_id: uuid.UUID, data: SafetySubmitRequest, user_id: uuid.UUID
) -> SCResponse:
    result = await db.execute(select(SpecialCharacteristic).where(SpecialCharacteristic.sc_id == sc_id))
    sc = result.scalar_one_or_none()
    if not sc:
        raise ValueError("Special characteristic not found")
    if not sc.is_safety_related:
        sc.is_safety_related = True
        sc.safety_approval_status = SafetyApprovalStatus.PENDING.value
    if not _can_safety_transition(
        SafetyApprovalStatus(sc.safety_approval_status) if sc.safety_approval_status else None,
        SafetyApprovalStatus.SUBMITTED,
    ):
        raise ValueError(f"Cannot transition from {sc.safety_approval_status} to submitted")
    if not data.safety_regulation_ref or not data.safety_regulation_ref.strip():
        raise ValueError("提交审批时必须填写法规引用")
    if not data.safety_verification_method or not data.safety_verification_method.strip():
        raise ValueError("提交审批时必须填写安全验证方法")

    sc.safety_approval_status = SafetyApprovalStatus.SUBMITTED.value
    sc.safety_regulation_ref = data.safety_regulation_ref.strip()
    sc.safety_verification_method = data.safety_verification_method.strip()
    sc.safety_submitted_by = user_id
    sc.safety_submitted_at = datetime.utcnow()
    await _create_audit(db, "SAFETY_SUBMIT", sc_id, user_id, {
        "sc_code": sc.sc_code,
        "safety_regulation_ref": sc.safety_regulation_ref,
        "notification_type": "safety_circular",
        "required_roles": ["manager", "quality_engineer"],
        "read_by_users": [],
        "auto_roles": ["质量经理", "工艺工程师"] + (["供应链管理员"] if sc.is_supplier_shared else []),
    })
    await db.commit()
    await db.refresh(sc)
    return _to_response(sc)


async def safety_approve(
    db: AsyncSession, sc_id: uuid.UUID, data: SafetyApprovalAction, user_id: uuid.UUID
) -> SCResponse:
    result = await db.execute(select(SpecialCharacteristic).where(SpecialCharacteristic.sc_id == sc_id))
    sc = result.scalar_one_or_none()
    if not sc:
        raise ValueError("Special characteristic not found")
    if sc.safety_approval_status != SafetyApprovalStatus.SUBMITTED.value:
        raise ValueError("Can only approve submitted safety characteristics")
    sc.safety_approval_status = SafetyApprovalStatus.APPROVED.value
    sc.safety_approved_by = user_id
    sc.safety_approved_at = datetime.utcnow()
    sc.safety_approval_comment = data.comment
    await _create_audit(db, "SAFETY_APPROVE", sc_id, user_id, {
        "sc_code": sc.sc_code,
        "comment": data.comment,
    })
    await db.commit()
    await db.refresh(sc)
    return _to_response(sc)


async def safety_reject(
    db: AsyncSession, sc_id: uuid.UUID, data: SafetyApprovalAction, user_id: uuid.UUID
) -> SCResponse:
    result = await db.execute(select(SpecialCharacteristic).where(SpecialCharacteristic.sc_id == sc_id))
    sc = result.scalar_one_or_none()
    if not sc:
        raise ValueError("Special characteristic not found")
    if sc.safety_approval_status != SafetyApprovalStatus.SUBMITTED.value:
        raise ValueError("Can only reject submitted safety characteristics")
    sc.safety_approval_status = SafetyApprovalStatus.REJECTED.value
    sc.safety_approved_by = user_id
    sc.safety_approved_at = datetime.utcnow()
    sc.safety_approval_comment = data.comment
    await _create_audit(db, "SAFETY_REJECT", sc_id, user_id, {
        "sc_code": sc.sc_code,
        "comment": data.comment,
    })
    await db.commit()
    await db.refresh(sc)
    return _to_response(sc)


async def safety_confirm(
    db: AsyncSession, sc_id: uuid.UUID, user_id: uuid.UUID
) -> SCResponse:
    result = await db.execute(select(SpecialCharacteristic).where(SpecialCharacteristic.sc_id == sc_id))
    sc = result.scalar_one_or_none()
    if not sc:
        raise ValueError("Special characteristic not found")
    if not sc.is_safety_suggested:
        raise ValueError("Not a safety suggestion")
    sc.is_safety_related = True
    sc.is_safety_suggested = False
    sc.safety_approval_status = SafetyApprovalStatus.PENDING.value
    await _create_audit(db, "SAFETY_CONFIRM", sc_id, user_id, {"sc_code": sc.sc_code})
    await db.commit()
    await db.refresh(sc)
    return _to_response(sc)


async def safety_dismiss(
    db: AsyncSession, sc_id: uuid.UUID, user_id: uuid.UUID
) -> SCResponse:
    result = await db.execute(select(SpecialCharacteristic).where(SpecialCharacteristic.sc_id == sc_id))
    sc = result.scalar_one_or_none()
    if not sc:
        raise ValueError("Special characteristic not found")
    if not sc.is_safety_suggested:
        raise ValueError("Not a safety suggestion")
    sc.is_safety_suggested = False
    await _create_audit(db, "SAFETY_DISMISS", sc_id, user_id, {"sc_code": sc.sc_code})
    await db.commit()
    await db.refresh(sc)
    return _to_response(sc)


async def safety_cancel(
    db: AsyncSession, sc_id: uuid.UUID, user_id: uuid.UUID
) -> SCResponse:
    result = await db.execute(select(SpecialCharacteristic).where(SpecialCharacteristic.sc_id == sc_id))
    sc = result.scalar_one_or_none()
    if not sc:
        raise ValueError("Special characteristic not found")
    if not sc.is_safety_related:
        raise ValueError("Not a safety characteristic")
    sc.is_safety_related = False
    sc.is_safety_suggested = False
    sc.safety_approval_status = None
    sc.safety_submitted_by = None
    sc.safety_submitted_at = None
    sc.safety_approved_by = None
    sc.safety_approved_at = None
    sc.safety_approval_comment = None
    sc.safety_regulation_ref = None
    sc.safety_verification_method = None
    await _create_audit(db, "SAFETY_CANCEL", sc_id, user_id, {"sc_code": sc.sc_code})
    await db.commit()
    await db.refresh(sc)
    return _to_response(sc)


async def mark_audit_log_read(
    db: AsyncSession, log_id: uuid.UUID, user_id: uuid.UUID, username: str
) -> AuditLog:
    result = await db.execute(select(AuditLog).where(AuditLog.log_id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise ValueError("Audit log not found")
    changed = log.changed_fields or {}
    read_by = changed.get("read_by_users", [])
    if any(r["user_id"] == str(user_id) for r in read_by):
        return log
    read_by.append({
        "user_id": str(user_id),
        "username": username,
        "read_at": datetime.utcnow().isoformat(),
    })
    changed["read_by_users"] = read_by
    log.changed_fields = changed
    # SQLAlchemy JSONB 原位修改陷阱：必须显式标记字段已变，否则 commit 不会触发 UPDATE
    flag_modified(log, "changed_fields")
    await db.commit()
    await db.refresh(log)
    return log


async def _create_audit(db: AsyncSession, action: str, record_id: uuid.UUID, user_id: uuid.UUID, detail: dict):
    log = AuditLog(
        table_name="special_characteristics", record_id=record_id,
        action=action, changed_fields=detail, operated_by=user_id,
    )
    db.add(log)
