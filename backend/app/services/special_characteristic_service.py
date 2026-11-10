import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.services.fmea_characteristics import criteria_with_unit
from app.models.audit import AuditLog
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.fmea import FMEADocument
from app.models.spc import InspectionCharacteristic
from app.models.special_characteristic import SpecialCharacteristic
from app.schemas.special_characteristic import (
    CPSyncStatusItem,
    CPSyncStatusResponse,
    MatrixResponse,
    MatrixRow,
    SafetyApprovalAction,
    SafetySubmitRequest,
    SCCreate,
    SCListResponse,
    SCResponse,
    SCUpdate,
    SeverityWarning,
)


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
    factory_id: uuid.UUID | None = None,
    allowed_product_lines: list[str] | None = None,
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
    if factory_id:
        query = query.where(SpecialCharacteristic.factory_id == factory_id)
    if allowed_product_lines is not None:
        query = query.where(SpecialCharacteristic.product_line_code.in_(allowed_product_lines))
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = result.scalars().all()
    return SCListResponse(items=[_to_response(i) for i in items], total=total, page=page, page_size=page_size)


async def get_special_characteristic(db: AsyncSession, sc_id: uuid.UUID) -> SCResponse | None:
    result = await db.execute(select(SpecialCharacteristic).where(SpecialCharacteristic.sc_id == sc_id))
    item = result.scalar_one_or_none()
    return _to_response(item) if item else None


async def create_special_characteristic(db: AsyncSession, data: SCCreate, user_id: uuid.UUID, *, factory_id: uuid.UUID | None = None) -> SCResponse:
    sc_code = await generate_sc_code(db)
    item = SpecialCharacteristic(
        sc_code=sc_code, sc_name=data.sc_name, sc_type=data.sc_type,
        customer_symbol=data.customer_symbol, sc_category=data.sc_category,
        spec_requirement=data.spec_requirement, source_fmea_id=data.source_fmea_id,
        source_node_id=data.source_node_id or "", source_type=data.source_type or "PFMEA",
        sop_ref=data.sop_ref, product_line_code=data.product_line_code, created_by=user_id,
        factory_id=factory_id,
    )
    db.add(item)
    await _create_audit(db, "CREATE", item.sc_id, user_id, {"sc_code": sc_code, "sc_name": data.sc_name})
    await db.commit()
    await db.refresh(item)
    return _to_response(item)


async def prepare_special_characteristic(
    db: AsyncSession,
    data: SCCreate,
    user_id: uuid.UUID,
) -> SpecialCharacteristic:
    """Stage a SpecialCharacteristic without committing.

    Explicitly flushes so the caller can safely reference the newly created
    ``sc_id`` before any follow-on writes (e.g., PLM SC link confirmation).
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('special_characteristics_sc_code'))"))
    sc_code = await generate_sc_code(db)
    item = SpecialCharacteristic(
        sc_code=sc_code,
        sc_name=data.sc_name,
        sc_type=data.sc_type,
        customer_symbol=data.customer_symbol,
        sc_category=data.sc_category,
        spec_requirement=data.spec_requirement,
        source_fmea_id=data.source_fmea_id,
        source_node_id=data.source_node_id or "",
        source_type=data.source_type or "PFMEA",
        sop_ref=data.sop_ref,
        product_line_code=data.product_line_code,
        created_by=user_id,
    )
    db.add(item)
    await db.flush()
    await _create_audit(
        db,
        "CREATE",
        item.sc_id,
        user_id,
        {"sc_code": sc_code, "sc_name": data.sc_name},
    )
    return item


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


def _require_scope(entity, scope):
    # Optional only for existing internal callers; HTTP consumers always pass it.
    if scope is None:
        return
    if (scope.effective_factory_id and entity.factory_id != scope.effective_factory_id
            or scope.factory_scope.accessible_factory_ids is not None
            and entity.factory_id not in scope.factory_scope.accessible_factory_ids
            or scope.pl_scope.mode == "NONE"
            or scope.pl_scope.mode == "EXPLICIT"
            and entity.product_line_code not in (scope.pl_scope.codes or [])):
        raise ValueError("对象不存在或不在请求作用域内")


def _frozen_safety(sc):
    return sc.safety_approval_status in ("submitted", "approved")


def _characteristic_records(fmea, *, graph=None):
    # Validated canonical material; absent/None and explicit [] differ.
    from app.schemas.characteristic import Characteristic, CharacteristicSourceRef
    from app.services.fmea_characteristics import validate_characteristics

    graph = (fmea.graph_data or {}) if graph is None else graph
    validate_characteristics(fmea.fmea_type, graph)
    nodes = graph.get("nodes", [])
    node_map = {n["id"]: n for n in nodes}
    edges = graph.get("edges", [])
    records = {}
    for node in nodes:
        if node.get("characteristics") is None:
            continue
        for raw in node["characteristics"]:
            char = Characteristic.model_validate(raw)
            ref = None
            if fmea.fmea_type == "PFMEA":
                owner = next(node_map[e["source"]] for e in edges
                             if e.get("type") == "HAS_FUNCTION" and e.get("target") == node["id"])
                work_element_id = owner["id"] if owner["type"] == "ProcessWorkElement" else None
                step_id = (next(e["source"] for e in edges if e.get("type") == "HAS_WORK_ELEMENT"
                                and e.get("target") == work_element_id) if work_element_id else owner["id"])
                ref = CharacteristicSourceRef(mapping_version=1, fmea_id=fmea.fmea_id,
                    step_id=step_id, function_id=node["id"], work_element_id=work_element_id,
                    characteristic_id=char.id)
            records[str(char.id)] = (node, char, ref)
    return records


async def sync_from_fmea(db: AsyncSession, fmea_id: uuid.UUID, user_id: uuid.UUID, *, scope=None) -> list[SCResponse]:
    fmea = await db.scalar(select(FMEADocument).where(FMEADocument.fmea_id == fmea_id)
                          .with_for_update().execution_options(populate_existing=True))
    if not fmea:
        raise ValueError("FMEA document not found")
    _require_scope(fmea, scope)
    canonical = _characteristic_records(fmea)
    graph = fmea.graph_data or {}
    nodes = graph.get("nodes", [])
    canonical_functions = {n["id"] for n in nodes if n.get("characteristics") is not None}
    canonical_failures = {e.get("target") for e in graph.get("edges", [])
                          if e.get("type") == "HAS_FAILURE_MODE" and e.get("source") in canonical_functions}
    legacy = {n["id"]: n for n in nodes
              if n["id"] not in canonical_functions | canonical_failures
              and (n.get("classification") in ("CC", "SC") or n.get("severity", 0) >= 9)}
    existing = list((await db.scalars(select(SpecialCharacteristic).where(
        SpecialCharacteristic.source_fmea_id == fmea_id).with_for_update()
        .execution_options(populate_existing=True))).all())
    if any(sc.factory_id != fmea.factory_id or sc.product_line_code != fmea.product_line_code for sc in existing):
        raise ValueError("特殊特性来源范围不一致，请人工复核")
    by_identity = {(str(sc.source_characteristic_id) if sc.source_characteristic_id else sc.source_node_id,
                    sc.source_characteristic_id is not None): sc for sc in existing}
    desired = {}
    for cid, (node, char, _) in canonical.items():
        if char.classification in ("CC", "SC"):
            desired[(cid, True)] = dict(sc_name=char.name, sc_type=char.classification,
                sc_category=char.kind, spec_requirement=criteria_with_unit(char.specification, char.unit) or char.reference,
                source_node_id=node["id"], source_characteristic_id=char.id)
    for node_id, node in legacy.items():
        desired[(node_id, False)] = dict(sc_name=node.get("name", ""),
            sc_type=node.get("classification") or "CC", source_node_id=node_id,
            source_characteristic_id=None)
    output = []
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                     {"key": "special_characteristics_sc_code"})
    for identity, material in desired.items():
        sc = by_identity.get(identity)
        if sc is not None:
            changes = {k: v for k, v in material.items() if getattr(sc, k) != v}
            scope_changed = sc.factory_id != fmea.factory_id or sc.product_line_code != fmea.product_line_code
            legacy_severity_drop = (not identity[1] and sc.is_safety_related
                                    and legacy[identity[0]].get("severity", 0) < 9)
            if scope_changed or _frozen_safety(sc) and (changes or legacy_severity_drop):
                await _create_audit(db, "SAFETY_SEVERITY_DROP" if legacy_severity_drop else "SAFETY_SOURCE_REVIEW_REQUIRED", sc.sc_id, user_id,
                                    {"warning": "来源材料已变化，保留受控特殊特性，请人工复核"})
                response = _to_response(sc)
                response.review_required = True
                response.review_message = "来源材料已变化，保留受控特殊特性，请人工复核"
                output.append(response)
                continue
            for k, v in changes.items():
                setattr(sc, k, v)
            if not identity[1] and not _frozen_safety(sc):
                node = legacy[identity[0]]
                if node.get("severity", 0) >= 9 and sc.sc_type == "CC" and not sc.is_safety_related:
                    sc.is_safety_suggested = True
                if sc.is_safety_related and node.get("severity", 0) < 9:
                    await _create_audit(db, "SAFETY_SEVERITY_DROP", sc.sc_id, user_id,
                                        {"warning": "FMEA严重度已下降，请人工评估是否保留安全属性"})
        else:
            sc = SpecialCharacteristic(sc_id=uuid.uuid4(), sc_code=await generate_sc_code(db),
                **material, source_fmea_id=fmea_id, source_type=fmea.fmea_type,
                factory_id=fmea.factory_id, product_line_code=fmea.product_line_code,
                created_by=user_id, is_safety_related=False,
                is_safety_suggested=not identity[1] and legacy[identity[0]].get("severity", 0) >= 9
                    and material["sc_type"] == "CC")
            db.add(sc)
            await db.flush()
            await _create_audit(db, "CREATE", sc.sc_id, user_id, {
                "action": "sync_from_fmea", "source_fmea_id": str(fmea_id),
                "source_characteristic_id": str(sc.source_characteristic_id) if sc.source_characteristic_id else None,
                "source_node_id": sc.source_node_id,
            })
        output.append(_to_response(sc))
    for identity, sc in by_identity.items():
        if identity in desired:
            continue
        legacy_adopted = (sc.source_characteristic_id is None
                          and sc.source_node_id in canonical_functions | canonical_failures)
        if sc.is_safety_related or sc.safety_approval_status or legacy_adopted:
            message = "来源取消分类、删除或已结构化；保留历史记录，请人工复核"
            await _create_audit(db, "SAFETY_DELETE_WARNING" if not legacy_adopted else "LEGACY_SOURCE_REVIEW_REQUIRED",
                                sc.sc_id, user_id, {"warning": message})
            response = _to_response(sc)
            response.review_required = True
            response.review_message = message
            output.append(response)
        else:
            await db.delete(sc)
    await _create_audit(db, "SYNC", fmea_id, user_id,
                        {"action": "sync_from_fmea", "classified_count": len(desired)})
    await db.commit()
    return output


async def _lock_cp_link_target(db, sc, cp, item_id):
    # CP parent is already held by sync_to_cp. Recheck the target after waits.
    target = await db.scalar(select(ControlPlanItem).where(
        ControlPlanItem.item_id == item_id, ControlPlanItem.cp_id == cp.cp_id,
        ControlPlanItem.factory_id == cp.factory_id).with_for_update(read=True, key_share=True)
        .execution_options(populate_existing=True))
    if (target is None or sc.factory_id != cp.factory_id
            or sc.product_line_code != cp.product_line_code):
        raise ValueError("特殊特性控制计划链接目标不存在或范围不一致")
    # Recheck review state after waiting, before any automatic SC rebinding.
    locked_sc = await db.scalar(select(SpecialCharacteristic).where(
        SpecialCharacteristic.sc_id == sc.sc_id).with_for_update()
        .execution_options(populate_existing=True))
    return locked_sc is not None and not _frozen_safety(locked_sc)


def _source_review_required(sc, record):
    if sc is None or not _frozen_safety(sc):
        return False
    if record is None:
        return True
    node, char, _ = record
    return (sc.source_node_id, sc.sc_name, sc.sc_type, sc.sc_category, sc.spec_requirement) != (
        node["id"], char.name, char.classification, char.kind,
        criteria_with_unit(char.specification, char.unit) or char.reference)


_VERSION_SYNC_GUIDANCE = "请使用已批准 FMEA 版本的正式同步预览与确认；此入口不改写来源字段"


def _cp_source_record(fmea, cp, item, records):
    from app.schemas.characteristic import CharacteristicSourceRef
    from app.services.fmea_characteristics import source_key

    if (fmea is None or fmea.fmea_id != cp.fmea_ref_id
            or item.factory_id != cp.factory_id or fmea.factory_id != cp.factory_id
            or fmea.product_line_code != cp.product_line_code):
        return None
    try:
        ref = CharacteristicSourceRef.model_validate(item.source_characteristic_ref)
    except ValueError:
        return None
    record = records.get(str(ref.characteristic_id))
    if record is None or record[2] is None:
        return None
    expected = record[2]
    if (ref.mapping_version == expected.mapping_version
            and ref.work_element_id == expected.work_element_id
            and item.source_fmea_node_id == ref.step_id
            and source_key(ref) == source_key(expected)):
        return record
    return None


async def _accepted_trace_records(db, fmea, cp, item, cache):
    """Read an immutable per-row baseline; never fall back to the working graph."""
    from app.models.fmea_version import FMEAVersion
    from app.schemas.characteristic import CharacteristicSourceRef
    from app.services.version_service import verify_fmea_version

    if (fmea is None or fmea.fmea_id != cp.fmea_ref_id
            or fmea.factory_id != cp.factory_id or item.factory_id != cp.factory_id
            or fmea.product_line_code != cp.product_line_code):
        return {}
    try:
        ref = CharacteristicSourceRef.model_validate(item.source_characteristic_ref)
    except ValueError:
        return {}
    if ref.fmea_id != fmea.fmea_id or ref.accepted_source_version_id is None:
        return {}
    key = (ref.accepted_source_version_id, fmea.fmea_id, cp.factory_id)
    if key not in cache:
        cache[key] = {}
        version = await db.scalar(select(FMEAVersion).where(
            FMEAVersion.version_id == ref.accepted_source_version_id,
            FMEAVersion.fmea_id == fmea.fmea_id, FMEAVersion.factory_id == cp.factory_id))
        if (version is not None and isinstance(version.snapshot, dict)
                and version.change_type == "approve" and version.major_no >= 1
                and version.minor_no == 0 and await verify_fmea_version(db, version.version_id)):
            try:
                cache[key] = _characteristic_records(fmea, graph=version.snapshot)
            except (ValueError, TypeError, KeyError):
                # An untrustworthy historical graph is not coverage evidence.
                pass
    return cache[key]


def _matches_source(sc, fmea, cp, item, records):
    if (sc.source_fmea_id != cp.fmea_ref_id or fmea is None
            or sc.factory_id != cp.factory_id or item.factory_id != cp.factory_id
            or fmea.factory_id != cp.factory_id or fmea.product_line_code != cp.product_line_code
            or sc.product_line_code != cp.product_line_code):
        return False
    if sc.source_characteristic_id is None:
        # Legacy trace uses only an explicit link, never name/class similarity.
        return sc.cp_item_id == item.item_id and not item.source_characteristic_ref
    record = _cp_source_record(fmea, cp, item, records)
    # SC identity is document + characteristic UUID. The row's full historical
    # owner identity was verified against its accepted snapshot above; a newer
    # SC/working-function binding must not erase still-existing older controls.
    return record is not None and record[1].id == sc.source_characteristic_id


async def sync_to_cp(db: AsyncSession, cp_id: uuid.UUID, user_id: uuid.UUID, *, scope=None) -> list[dict]:
    """Report canonical mismatches without bypassing approved-version sync.

    Only legacy rows without a source ref retain the guarded node-based sync.
    Canonical multi-control coverage is derived by the read-only trace query.
    """
    cp_result = await db.execute(select(ControlPlan).where(ControlPlan.cp_id == cp_id).with_for_update().execution_options(populate_existing=True))
    cp = cp_result.scalar_one_or_none()
    if not cp:
        raise ValueError("Control plan not found")
    _require_scope(cp, scope)
    if not cp.fmea_ref_id:
        return []

    # Get characteristics indexed by FailureMode node ID
    scs_result = await db.execute(
        select(SpecialCharacteristic).where(SpecialCharacteristic.source_fmea_id == cp.fmea_ref_id)
    )
    all_scs = list(scs_result.scalars().all())
    scs = {sc.source_node_id: sc for sc in all_scs if sc.source_characteristic_id is None
           and sc.factory_id == cp.factory_id and sc.product_line_code == cp.product_line_code}

    # Build FMEA graph: ProcessStep node ID -> FailureMode node IDs
    fmea_result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == cp.fmea_ref_id))
    fmea = fmea_result.scalar_one_or_none()
    if fmea:
        _require_scope(fmea, scope)
        if fmea.factory_id != cp.factory_id or fmea.product_line_code != cp.product_line_code:
            raise ValueError("FMEA与控制计划范围不一致")
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

    items_result = await db.execute(select(ControlPlanItem).where(ControlPlanItem.cp_id == cp_id).order_by(ControlPlanItem.sort_order, ControlPlanItem.item_id).with_for_update().execution_options(populate_existing=True))
    items = items_result.scalars().all()

    records = _characteristic_records(fmea) if fmea else {}
    updated = []
    for item in items:
        if item.source_characteristic_ref is not None:
            record = _cp_source_record(fmea, cp, item, records)
            sc = next((sc for sc in all_scs if record is not None
                       and sc.source_characteristic_id == record[1].id
                       and sc.factory_id == cp.factory_id and sc.product_line_code == cp.product_line_code), None)
            expected = record[1].classification if record else None
            if record is None or _source_review_required(sc, record) or (item.special_class or "") != (expected or ""):
                updated.append({"item_id": str(item.item_id), "step_no": item.step_no,
                    "old": item.special_class, "new": expected, "updated": False,
                    "requires_version_sync": True, "guidance": _VERSION_SYNC_GUIDANCE})
            continue
        step_node_id = item.source_fmea_node_id or ""
        sc = next((scs[fm_id] for fm_id in step_to_fms.get(step_node_id, []) if fm_id in scs), None)
        sc = sc or scs.get(step_node_id)
        if sc is None or item.special_class == sc.sc_type:
            continue
        outcome = {"item_id": str(item.item_id), "step_no": item.step_no,
                   "old": item.special_class, "new": sc.sc_type}
        if cp.status == "approved" or _frozen_safety(sc) or not await _lock_cp_link_target(db, sc, cp, item.item_id):
            updated.append({**outcome, "updated": False, "requires_version_sync": True,
                            "guidance": "受控材料保留不变，请通过正式版本同步或人工复核"})
            continue
        item.special_class = sc.sc_type
        sc.cp_item_id = item.item_id
        updated.append({**outcome, "updated": True})

    await _create_audit(db, "SYNC", cp_id, user_id, {
        "action": "sync_to_cp", "updated_count": sum(i.get("updated", False) for i in updated),
    })
    await db.commit()
    return updated


async def get_matrix(db: AsyncSession, product_line: str | None = None, factory_id: uuid.UUID | None = None) -> MatrixResponse:
    query = select(SpecialCharacteristic).order_by(SpecialCharacteristic.created_at)
    if product_line:
        query = query.where(SpecialCharacteristic.product_line_code == product_line)
    if factory_id:
        query = query.where(SpecialCharacteristic.factory_id == factory_id)
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
    if grr_percent < 10 or grr_percent < 30:
        sc.msa_status = "PASS"
    else:
        sc.msa_status = "FAIL"
    await db.commit()
    await db.refresh(sc)
    return _to_response(sc)


async def check_cp_sync_status(db: AsyncSession, cp_id: uuid.UUID, *, scope=None) -> CPSyncStatusResponse:
    """Check CP items vs FMEA FailureMode classifications (edge-based mapping)."""
    cp_result = await db.execute(select(ControlPlan).where(ControlPlan.cp_id == cp_id))
    cp = cp_result.scalar_one_or_none()
    if cp is None:
        raise ValueError("Control plan not found")
    _require_scope(cp, scope)
    if not cp.fmea_ref_id:
        return CPSyncStatusResponse(items=[], total_out_of_sync=0)

    fmea_result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == cp.fmea_ref_id))
    fmea = fmea_result.scalar_one_or_none()
    if not fmea:
        return CPSyncStatusResponse(items=[], total_out_of_sync=0)

    _require_scope(fmea, scope)
    if fmea.factory_id != cp.factory_id or fmea.product_line_code != cp.product_line_code:
        raise ValueError("FMEA与控制计划范围不一致")
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
    all_scs = list(scs_result.scalars().all())
    sc_map = {sc.source_node_id: sc for sc in all_scs if sc.source_characteristic_id is None
              and sc.factory_id == cp.factory_id and sc.product_line_code == cp.product_line_code}
    records = _characteristic_records(fmea)

    items_result = await db.execute(select(ControlPlanItem).where(ControlPlanItem.cp_id == cp_id))
    items = items_result.scalars().all()

    sync_items = []
    for item in items:
        if item.source_characteristic_ref is not None:
            record = _cp_source_record(fmea, cp, item, records)
            sc = next((sc for sc in all_scs if record is not None
                       and sc.source_characteristic_id == record[1].id
                       and sc.factory_id == cp.factory_id and sc.product_line_code == cp.product_line_code), None)
            expected = record[1].classification if record else None
            mismatch = (record is None or _source_review_required(sc, record)
                        or (item.special_class or "") != (expected or ""))
            sync_items.append(CPSyncStatusItem(item_id=item.item_id, step_no=item.step_no or "",
                process_name=item.process_name or "", current_special_class=item.special_class,
                expected_special_class=expected, is_out_of_sync=mismatch,
                requires_version_sync=mismatch, guidance=_VERSION_SYNC_GUIDANCE if mismatch else None))
            continue
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



async def _trace_msa_evidence(db, sc):
    # The historical SC cache/callback is not itself a measurement result.
    if sc.msa_study_id is None:
        return None, "PENDING"
    from app.models.grr import GrrStudy, GrrResult
    from app.models.bias import BiasStudy, BiasResult
    from app.models.linearity import LinearityStudy, LinearityResult
    from app.models.stability import StabilityStudy, StabilityResult
    from app.models.attribute import AttributeStudy, AttributeResult

    for study_model, result_model in ((GrrStudy, GrrResult), (BiasStudy, BiasResult),
            (LinearityStudy, LinearityResult), (StabilityStudy, StabilityResult), (AttributeStudy, AttributeResult)):
        study = await db.scalar(select(study_model).where(study_model.study_id == sc.msa_study_id,
            study_model.factory_id == sc.factory_id, study_model.product_line_code == sc.product_line_code))
        if study is None:
            continue
        result = await db.scalar(select(result_model).where(result_model.study_id == study.study_id,
                                                           result_model.factory_id == sc.factory_id))
        return str(study.study_id), result.conclusion if result else "PENDING"
    return None, "PENDING"


async def get_traceability_chain(db: AsyncSession, sc_id: uuid.UUID, *, scope=None) -> dict:
    # All CP controls are derived read-only from provenance, not the last link.
    sc = await db.get(SpecialCharacteristic, sc_id)
    if not sc:
        raise ValueError("特殊特性不存在")
    _require_scope(sc, scope)
    fmea = await db.get(FMEADocument, sc.source_fmea_id) if sc.source_fmea_id else None
    if fmea and (fmea.factory_id != sc.factory_id or fmea.product_line_code != sc.product_line_code):
        fmea = None
    try:
        records = _characteristic_records(fmea) if fmea else {}
    except (ValueError, TypeError, KeyError):
        # Current-source comparison is advisory, never the historical trust root.
        records = {}
    msa_study_id, msa_status = await _trace_msa_evidence(db, sc)
    review_required = (sc.source_characteristic_id is not None
                       and _source_review_required(sc, records.get(str(sc.source_characteristic_id))))
    chain = {
        "sc_code": sc.sc_code, "sc_name": sc.sc_name, "sc_type": sc.sc_type,
        "sc_category": sc.sc_category,
        "review_required": review_required,
        "review_message": "来源材料已变化，保留受控特殊特性，请人工复核" if review_required else None,
        "source_characteristic_id": str(sc.source_characteristic_id) if sc.source_characteristic_id else None,
        "spec_requirement": sc.spec_requirement, "product_line_code": sc.product_line_code,
        "msa_study_id": msa_study_id, "msa_status": msa_status,
        "fmea_source": None, "control_plan_items": [], "spc_characteristics": [],
    }
    if fmea:
        graph = fmea.graph_data or {}
        node_map = {n["id"]: n for n in graph.get("nodes", [])}
        node = node_map.get(sc.source_node_id)
        if node:
            connected = [node_map[e["target"]] for e in graph.get("edges", [])
                         if e.get("source") == sc.source_node_id and e.get("type") == "HAS_FAILURE_MODE"
                         and e.get("target") in node_map]
            chain["fmea_source"] = dict(fmea_id=str(fmea.fmea_id), document_no=fmea.document_no,
                title=fmea.title, fmea_type=fmea.fmea_type, node_id=sc.source_node_id,
                node_name=node.get("name", ""), node_type=node.get("type", ""),
                connected_failure_modes=[dict(id=n["id"], name=n.get("name", ""), type=n.get("type", "")) for n in connected])
    query = select(ControlPlanItem, ControlPlan).join(ControlPlan, ControlPlan.cp_id == ControlPlanItem.cp_id).where(
        ControlPlan.factory_id == sc.factory_id, ControlPlanItem.factory_id == sc.factory_id,
        ControlPlan.product_line_code == sc.product_line_code,
        ControlPlan.fmea_ref_id == sc.source_fmea_id).order_by(ControlPlan.document_no, ControlPlanItem.sort_order, ControlPlanItem.item_id)
    spc_ids = set()
    accepted_cache = {}
    for item, cp in (await db.execute(query)).all():
        accepted_records = (await _accepted_trace_records(db, fmea, cp, item, accepted_cache)
                            if sc.source_characteristic_id is not None else {})
        if not _matches_source(sc, fmea, cp, item, accepted_records):
            continue
        _require_scope(cp, scope)
        gauge_id = None
        if item.gauge_id:
            from app.models.gauge import Gauge
            gauge = await db.get(Gauge, item.gauge_id)
            if gauge and gauge.factory_id == sc.factory_id and gauge.product_line_code == sc.product_line_code:
                gauge_id = str(gauge.gauge_id)
        record = records.get(str(sc.source_characteristic_id))
        accepted_record = accepted_records.get(str(sc.source_characteristic_id))
        diverged = (accepted_record is not None and (record is None
                    or accepted_record[1] != record[1] or accepted_record[2] != record[2]))
        if diverged:
            chain["review_required"] = True
            chain["review_message"] = "当前 FMEA 来源与已接受批准版本不同；保留控制行追溯，请人工复核"
        expected = record[1].classification if record else sc.sc_type
        mismatch = review_required or diverged or (item.special_class or "") != (expected or "")
        chain["control_plan_items"].append(dict(item_id=str(item.item_id), cp_id=str(cp.cp_id),
            step_no=item.step_no, process_name=item.process_name, characteristic_no=item.characteristic_no,
            special_class=item.special_class, specification_tolerance=item.specification_tolerance,
            cp_document_no=cp.document_no, cp_title=cp.title, gauge_id=gauge_id,
            requires_version_sync=mismatch, guidance=_VERSION_SYNC_GUIDANCE if mismatch else None))
        if item.spc_chart_id:
            spc_ids.add(item.spc_chart_id)
    if spc_ids:
        spcs = await db.scalars(select(InspectionCharacteristic).where(
            InspectionCharacteristic.ic_id.in_(spc_ids), InspectionCharacteristic.factory_id == sc.factory_id,
            InspectionCharacteristic.product_line == sc.product_line_code).order_by(InspectionCharacteristic.ic_id))
        for ic in spcs:
            chain["spc_characteristics"].append(dict(ic_id=str(ic.ic_id), characteristic_name=ic.characteristic_name,
                chart_type=ic.chart_type, spec_target=float(ic.target_value) if ic.target_value is not None else None,
                spec_upper=float(ic.spec_upper) if ic.spec_upper is not None else None,
                spec_lower=float(ic.spec_lower) if ic.spec_lower is not None else None))
    return chain

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
        source_node_id=sc.source_node_id,
        source_characteristic_id=sc.source_characteristic_id,
        source_type=sc.source_type, cp_item_id=sc.cp_item_id, msa_study_id=sc.msa_study_id,
        msa_status=sc.msa_status or "PENDING", sop_ref=sc.sop_ref,
        product_line_code=sc.product_line_code,
        factory_id=sc.factory_id,
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


async def get_sc_references(
    db: AsyncSession, sc_id: str
) -> list[dict]:
    from app.models.special_characteristic_link import SpecialCharacteristicLink
    q = select(SpecialCharacteristicLink).where(
        SpecialCharacteristicLink.sc_id == sc_id
    )
    result = await db.execute(q)
    return [
        {
            "source_type": link.source_type,
            "source_id": str(link.source_id),
            "source_item_id": link.source_item_id,
        }
        for link in result.scalars().all()
    ]


async def add_sc_reference(
    db: AsyncSession,
    sc_id: str,
    source_type: str,
    source_id: str,
    source_item_id: str,
) -> None:
    from app.models.special_characteristic_link import SpecialCharacteristicLink
    link = SpecialCharacteristicLink(
        sc_id=sc_id,
        source_type=source_type,
        source_id=source_id,
        source_item_id=source_item_id,
    )
    db.add(link)
    await db.commit()
