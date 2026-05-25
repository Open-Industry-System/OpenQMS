"""Version management service for FMEA documents and Control Plans.

Provides SHA-256 integrity hashing, version CRUD, rollback, and FMEA-to-CP sync.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.control_plan_version import ControlPlanVersion
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion


# ---------------------------------------------------------------------------
# SHA-256 helpers
# ---------------------------------------------------------------------------

def _canonical_json(data: dict | list) -> str:
    """Produce a deterministic JSON string for hashing.

    Sorts keys, uses ensure_ascii=False for Chinese text, and strips
    trailing whitespace to avoid platform-dependent differences.
    """
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_snapshot_hash(snapshot: dict | list) -> str:
    """Return hex SHA-256 digest of *snapshot*."""
    return hashlib.sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()


def verify_snapshot_hash(snapshot: dict | list, stored_hash: str) -> bool:
    """Return True when the snapshot matches the stored SHA-256 hash."""
    return compute_snapshot_hash(snapshot) == stored_hash


# ---------------------------------------------------------------------------
# FMEA version helpers
# ---------------------------------------------------------------------------

async def get_latest_fmea_version(db: AsyncSession, fmea_id: uuid.UUID) -> FMEAVersion | None:
    """Return the latest (highest major.minor) version for an FMEA document."""
    result = await db.execute(
        select(FMEAVersion)
        .where(FMEAVersion.fmea_id == fmea_id)
        .order_by(FMEAVersion.major_no.desc(), FMEAVersion.minor_no.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_fmea_version(
    db: AsyncSession,
    fmea: FMEADocument,
    change_type: str,
    change_summary: str | None,
    user_id: uuid.UUID,
) -> FMEAVersion:
    """Snapshot the current FMEA graph_data as a new version.

    * ``change_type == "approve"`` bumps major_no, resets minor_no to 0.
    * All other types bump minor_no.
    """
    latest = await get_latest_fmea_version(db, fmea.fmea_id)
    if latest is None:
        major_no, minor_no = 0, 0
    else:
        major_no, minor_no = latest.major_no, latest.minor_no

    if change_type == "approve":
        major_no += 1
        minor_no = 0
    else:
        minor_no += 1

    snapshot = fmea.graph_data
    sha256_hash = compute_snapshot_hash(snapshot)

    version = FMEAVersion(
        version_id=uuid.uuid4(),
        fmea_id=fmea.fmea_id,
        major_no=major_no,
        minor_no=minor_no,
        snapshot=snapshot,
        sha256_hash=sha256_hash,
        change_summary=change_summary,
        change_type=change_type,
        created_by=user_id,
    )
    db.add(version)

    # Audit log
    db.add(AuditLog(
        table_name="fmea_versions",
        record_id=version.version_id,
        action="CREATE",
        changed_fields={
            "fmea_id": str(fmea.fmea_id),
            "version": f"v{major_no}.{minor_no}",
            "change_type": change_type,
            "change_summary": change_summary or "",
        },
        operated_by=user_id,
    ))

    await db.commit()
    await db.refresh(version)
    return version


async def list_fmea_versions(
    db: AsyncSession,
    fmea_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
    major_only: bool = False,
) -> tuple[list[FMEAVersion], int]:
    """Return paginated list of FMEA versions, optionally minor_no==0 only."""
    query = select(FMEAVersion).where(FMEAVersion.fmea_id == fmea_id)
    count_query = select(func.count(FMEAVersion.version_id)).where(
        FMEAVersion.fmea_id == fmea_id
    )

    if major_only:
        query = query.where(FMEAVersion.minor_no == 0)
        count_query = count_query.where(FMEAVersion.minor_no == 0)

    query = query.order_by(FMEAVersion.major_no.desc(), FMEAVersion.minor_no.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return items, total


async def get_fmea_version(
    db: AsyncSession,
    fmea_id: uuid.UUID,
    major_no: int,
    minor_no: int,
) -> FMEAVersion | None:
    """Return a specific FMEA version by fmea_id + major.minor."""
    result = await db.execute(
        select(FMEAVersion).where(
            FMEAVersion.fmea_id == fmea_id,
            FMEAVersion.major_no == major_no,
            FMEAVersion.minor_no == minor_no,
        )
    )
    return result.scalar_one_or_none()


async def verify_fmea_version(db: AsyncSession, version_id: uuid.UUID) -> bool:
    """Verify the SHA-256 hash of a stored FMEA version snapshot."""
    result = await db.execute(
        select(FMEAVersion).where(FMEAVersion.version_id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise ValueError(f"FMEA version {version_id} not found.")
    return verify_snapshot_hash(version.snapshot, version.sha256_hash)


# ---------------------------------------------------------------------------
# Control Plan version helpers
# ---------------------------------------------------------------------------

async def get_latest_cp_version(db: AsyncSession, cp_id: uuid.UUID) -> ControlPlanVersion | None:
    """Return the latest (highest major.minor) version for a Control Plan."""
    result = await db.execute(
        select(ControlPlanVersion)
        .where(ControlPlanVersion.cp_id == cp_id)
        .order_by(ControlPlanVersion.major_no.desc(), ControlPlanVersion.minor_no.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_cp_version(
    db: AsyncSession,
    cp: ControlPlan,
    change_type: str,
    change_summary: str | None,
    user_id: uuid.UUID,
    source_fmea_version_id: uuid.UUID | None = None,
) -> ControlPlanVersion:
    """Snapshot the current Control Plan (header + items) as a new version.

    Header snapshot captures scalar CP fields.  Items snapshot is a list of
    dicts, each preserving the ``item_id`` UUID string for identity tracking.

    * ``change_type == "approve"`` bumps major_no, resets minor_no to 0.
    * All other types bump minor_no.
    """
    latest = await get_latest_cp_version(db, cp.cp_id)
    if latest is None:
        major_no, minor_no = 0, 0
    else:
        major_no, minor_no = latest.major_no, latest.minor_no

    if change_type == "approve":
        major_no += 1
        minor_no = 0
    else:
        minor_no += 1

    # Build header snapshot (scalar fields only)
    header_snapshot = {
        "document_no": cp.document_no,
        "title": cp.title,
        "fmea_ref_id": str(cp.fmea_ref_id) if cp.fmea_ref_id else None,
        "product_line_code": cp.product_line_code,
        "status": cp.status,
        "phase": cp.phase,
        "part_no": cp.part_no,
        "part_name": cp.part_name,
        "contact_info": cp.contact_info,
        "drawing_rev": cp.drawing_rev,
        "org_factory": cp.org_factory,
        "core_group": cp.core_group,
    }

    # Build items snapshot — preserve item_id as string for identity tracking
    items_result = await db.execute(
        select(ControlPlanItem)
        .where(ControlPlanItem.cp_id == cp.cp_id)
        .order_by(ControlPlanItem.sort_order)
    )
    items = list(items_result.scalars().all())

    items_snapshot = []
    for item in items:
        items_snapshot.append({
            "item_id": str(item.item_id),
            "step_no": item.step_no,
            "process_name": item.process_name,
            "equipment": item.equipment,
            "characteristic_no": item.characteristic_no,
            "product_characteristic": item.product_characteristic,
            "process_characteristic": item.process_characteristic,
            "special_class": item.special_class,
            "specification_tolerance": item.specification_tolerance,
            "evaluation_method": item.evaluation_method,
            "sample_size": item.sample_size,
            "sample_frequency": item.sample_frequency,
            "control_method": item.control_method,
            "reaction_plan": item.reaction_plan,
            "source_fmea_node_id": item.source_fmea_node_id,
            "sort_order": item.sort_order,
        })

    # Compute hash over combined data
    combined = {"header": header_snapshot, "items": items_snapshot}
    sha256_hash = compute_snapshot_hash(combined)

    version = ControlPlanVersion(
        version_id=uuid.uuid4(),
        cp_id=cp.cp_id,
        major_no=major_no,
        minor_no=minor_no,
        header_snapshot=header_snapshot,
        items_snapshot=items_snapshot,
        sha256_hash=sha256_hash,
        source_fmea_version_id=source_fmea_version_id,
        change_summary=change_summary,
        change_type=change_type,
        created_by=user_id,
    )
    db.add(version)

    # Audit log
    db.add(AuditLog(
        table_name="control_plan_versions",
        record_id=version.version_id,
        action="CREATE",
        changed_fields={
            "cp_id": str(cp.cp_id),
            "version": f"v{major_no}.{minor_no}",
            "change_type": change_type,
            "change_summary": change_summary or "",
            "items_count": len(items_snapshot),
        },
        operated_by=user_id,
    ))

    await db.commit()
    await db.refresh(version)
    return version


async def list_cp_versions(
    db: AsyncSession,
    cp_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
    major_only: bool = False,
) -> tuple[list[ControlPlanVersion], int]:
    """Return paginated list of CP versions, optionally minor_no==0 only."""
    query = select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp_id)
    count_query = select(func.count(ControlPlanVersion.version_id)).where(
        ControlPlanVersion.cp_id == cp_id
    )

    if major_only:
        query = query.where(ControlPlanVersion.minor_no == 0)
        count_query = count_query.where(ControlPlanVersion.minor_no == 0)

    query = query.order_by(
        ControlPlanVersion.major_no.desc(), ControlPlanVersion.minor_no.desc()
    )
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return items, total


async def get_cp_version(
    db: AsyncSession,
    cp_id: uuid.UUID,
    major_no: int,
    minor_no: int,
) -> ControlPlanVersion | None:
    """Return a specific CP version by cp_id + major.minor."""
    result = await db.execute(
        select(ControlPlanVersion).where(
            ControlPlanVersion.cp_id == cp_id,
            ControlPlanVersion.major_no == major_no,
            ControlPlanVersion.minor_no == minor_no,
        )
    )
    return result.scalar_one_or_none()


async def verify_cp_version(db: AsyncSession, version_id: uuid.UUID) -> bool:
    """Verify the SHA-256 hash of a stored CP version snapshot."""
    result = await db.execute(
        select(ControlPlanVersion).where(ControlPlanVersion.version_id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise ValueError(f"Control Plan version {version_id} not found.")
    combined = {"header": version.header_snapshot, "items": version.items_snapshot}
    return verify_snapshot_hash(combined, version.sha256_hash)


# ---------------------------------------------------------------------------
# Rollback functions
# ---------------------------------------------------------------------------

async def rollback_fmea(
    db: AsyncSession,
    fmea: FMEADocument,
    target_major: int,
    target_minor: int,
    reason: str,
    user_id: uuid.UUID,
    expected_lock_version: int | None = None,
) -> FMEAVersion:
    """Roll back an FMEA document's graph_data to a previous version.

    Only allowed when the FMEA status is ``draft``.
    Creates a new version recording the rollback.
    """
    if fmea.status != "draft":
        raise ValueError("Rollback is only allowed when FMEA status is draft.")

    if expected_lock_version is not None and fmea.lock_version != expected_lock_version:
        raise ValueError(
            "文档已被他人修改，请刷新后再试。"
        )

    target = await get_fmea_version(db, fmea.fmea_id, target_major, target_minor)
    if target is None:
        raise ValueError(f"Version v{target_major}.{target_minor} not found.")

    # Guard: check for active downstream references before overwriting graph_data
    cascade_refs: list[str] = []

    capa_result = await db.execute(
        select(CAPAEightD.report_id, CAPAEightD.document_no)
        .where(CAPAEightD.fmea_ref_id == fmea.fmea_id)
        .where(CAPAEightD.status != "D8_CLOSURE")
    )
    for row in capa_result.all():
        cascade_refs.append(f"8D/CAPA {row.document_no}")

    cp_result = await db.execute(
        select(ControlPlan.cp_id, ControlPlan.document_no)
        .where(ControlPlan.fmea_ref_id == fmea.fmea_id)
        .where(ControlPlan.status != "archived")
    )
    for row in cp_result.all():
        cascade_refs.append(f"控制计划 {row.document_no}")

    if cascade_refs:
        raise ValueError(
            f"无法回退：以下 {len(cascade_refs)} 个关联文档仍在使用当前 FMEA 的节点数据，"
            f"请先处理或归档这些文档：{'、'.join(cascade_refs)}"
        )

    # Restore graph_data
    fmea.graph_data = target.snapshot
    fmea.updated_by = user_id
    fmea.lock_version = (fmea.lock_version or 0) + 1

    # Create rollback version
    summary = f"回退原因：{reason}。从 v{target_major}.{target_minor} 回退"
    version = await create_fmea_version(
        db, fmea, change_type="rollback", change_summary=summary, user_id=user_id,
    )

    # Audit log on the FMEA document itself
    db.add(AuditLog(
        table_name="fmea_documents",
        record_id=fmea.fmea_id,
        action="ROLLBACK",
        changed_fields={
            "target_version": f"v{target_major}.{target_minor}",
            "reason": reason,
            "new_version": f"v{version.major_no}.{version.minor_no}",
        },
        operated_by=user_id,
    ))

    await db.commit()
    await db.refresh(fmea)
    await db.refresh(version)
    return version


async def rollback_control_plan(
    db: AsyncSession,
    cp: ControlPlan,
    target_major: int,
    target_minor: int,
    reason: str,
    user_id: uuid.UUID,
    expected_lock_version: int | None = None,
) -> ControlPlanVersion:
    """Roll back a Control Plan to a previous version.

    Only allowed when status is ``draft``.
    Restores header fields and upserts items preserving original item_id UUIDs.
    """
    if cp.status != "draft":
        raise ValueError("Rollback is only allowed when control plan status is draft.")

    if expected_lock_version is not None and cp.lock_version != expected_lock_version:
        raise ValueError(
            "文档已被他人修改，请刷新后再试。"
        )

    target = await get_cp_version(db, cp.cp_id, target_major, target_minor)
    if target is None:
        raise ValueError(f"Version v{target_major}.{target_minor} not found.")

    header = target.header_snapshot
    items_snapshot = target.items_snapshot

    # Restore header fields
    for field in (
        "title", "phase", "part_no", "part_name", "contact_info",
        "drawing_rev", "org_factory", "core_group",
    ):
        if field in header:
            setattr(cp, field, header[field])
    cp.updated_by = user_id
    cp.lock_version = (cp.lock_version or 0) + 1
    target_item_ids = set()
    for snap in items_snapshot:
        item_uid = uuid.UUID(snap["item_id"])
        target_item_ids.add(item_uid)

        # Try to find existing item with this ID
        existing_result = await db.execute(
            select(ControlPlanItem).where(ControlPlanItem.item_id == item_uid)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # Update in place — preserve item_id
            existing.step_no = snap.get("step_no")
            existing.process_name = snap.get("process_name")
            existing.equipment = snap.get("equipment")
            existing.characteristic_no = snap.get("characteristic_no")
            existing.product_characteristic = snap.get("product_characteristic")
            existing.process_characteristic = snap.get("process_characteristic")
            existing.special_class = snap.get("special_class")
            existing.specification_tolerance = snap.get("specification_tolerance")
            existing.evaluation_method = snap.get("evaluation_method")
            existing.sample_size = snap.get("sample_size")
            existing.sample_frequency = snap.get("sample_frequency")
            existing.control_method = snap.get("control_method")
            existing.reaction_plan = snap.get("reaction_plan")
            existing.source_fmea_node_id = snap.get("source_fmea_node_id")
            existing.sort_order = snap.get("sort_order", 0)
        else:
            # Re-create with original item_id
            new_item = ControlPlanItem(
                item_id=item_uid,
                cp_id=cp.cp_id,
                step_no=snap.get("step_no"),
                process_name=snap.get("process_name"),
                equipment=snap.get("equipment"),
                characteristic_no=snap.get("characteristic_no"),
                product_characteristic=snap.get("product_characteristic"),
                process_characteristic=snap.get("process_characteristic"),
                special_class=snap.get("special_class"),
                specification_tolerance=snap.get("specification_tolerance"),
                evaluation_method=snap.get("evaluation_method"),
                sample_size=snap.get("sample_size"),
                sample_frequency=snap.get("sample_frequency"),
                control_method=snap.get("control_method"),
                reaction_plan=snap.get("reaction_plan"),
                source_fmea_node_id=snap.get("source_fmea_node_id"),
                sort_order=snap.get("sort_order", 0),
            )
            db.add(new_item)

    # Delete items that exist in current CP but not in the target snapshot
    current_items_result = await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id)
    )
    current_items = list(current_items_result.scalars().all())
    for item in current_items:
        if item.item_id not in target_item_ids:
            await db.delete(item)

    # Create rollback version
    summary = f"回退原因：{reason}。从 v{target_major}.{target_minor} 回退"
    version = await create_cp_version(
        db, cp, change_type="rollback", change_summary=summary, user_id=user_id,
    )

    # Audit log on the control plan itself
    db.add(AuditLog(
        table_name="control_plans",
        record_id=cp.cp_id,
        action="ROLLBACK",
        changed_fields={
            "target_version": f"v{target_major}.{target_minor}",
            "reason": reason,
            "new_version": f"v{version.major_no}.{version.minor_no}",
        },
        operated_by=user_id,
    ))

    await db.commit()
    await db.refresh(cp)
    await db.refresh(version)
    return version


# ---------------------------------------------------------------------------
# FMEA-CP sync functions
# ---------------------------------------------------------------------------

# Fields on ControlPlanItem that can be synced from FMEA graph nodes
_SYNCABLE_ITEM_FIELDS = (
    "process_name",
    "equipment",
    "product_characteristic",
    "process_characteristic",
    "special_class",
    "specification_tolerance",
)


async def get_fmea_version_by_id(
    db: AsyncSession, version_id: uuid.UUID,
) -> FMEAVersion | None:
    """Return an FMEA version by its version_id."""
    result = await db.execute(
        select(FMEAVersion).where(FMEAVersion.version_id == version_id)
    )
    return result.scalar_one_or_none()


async def build_sync_preview(
    db: AsyncSession,
    cp: ControlPlan,
    fmea_version: FMEAVersion,
) -> list[dict]:
    """Build a preview of changes that would result from syncing a CP with an FMEA version.

    Returns a list of preview dicts, each with:
        item_id:          existing item UUID string, or pre-generated UUID for "add"
        source_fmea_node_id: FMEA graph node_id (always present)
        step_no:          process step number
        action:           "add" | "sync" | "delete"
        current_value:    dict of current CP item fields (None for "add")
        fmea_new_value:   dict of FMEA-derived field values
        merged_value:     proposed merged values (FMEA overwrites where non-empty)
    """
    graph = fmea_version.snapshot or {"nodes": [], "edges": []}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    node_map: dict[str, dict] = {n["id"]: n for n in nodes if "id" in n}
    edge_map: dict[str, list[str]] = {}
    for e in edges:
        src = e.get("source")
        tgt = e.get("target")
        if src:
            edge_map.setdefault(src, []).append(tgt)

    # Load current CP items
    items_result = await db.execute(
        select(ControlPlanItem)
        .where(ControlPlanItem.cp_id == cp.cp_id)
        .order_by(ControlPlanItem.sort_order)
    )
    current_items = list(items_result.scalars().all())

    # Index existing items by source_fmea_node_id
    existing_by_node: dict[str, ControlPlanItem] = {}
    for item in current_items:
        if item.source_fmea_node_id:
            existing_by_node[item.source_fmea_node_id] = item

    # Identify FMEA ProcessStep nodes as sync sources
    step_nodes = [n for n in nodes if n.get("type") == "ProcessStep"]

    def _children(parent_id: str, node_type: str) -> list[dict]:
        return [
            node_map[t]
            for t in edge_map.get(parent_id, [])
            if node_map.get(t, {}).get("type") == node_type
        ]

    def _derive_item_fields(step_node: dict) -> dict:
        """Derive CP item fields from an FMEA ProcessStep and its children."""
        step_id = step_node["id"]
        work_elements = _children(step_id, "ProcessWorkElement")
        step_functions = _children(step_id, "ProcessStepFunction")

        fields: dict = {
            "step_no": step_node.get("process_number", ""),
            "process_name": step_node.get("name", ""),
            "equipment": None,
            "product_characteristic": None,
            "process_characteristic": None,
            "special_class": None,
            "specification_tolerance": None,
        }

        if work_elements:
            fields["equipment"] = work_elements[0].get("name")

        if step_functions:
            sf = step_functions[0]
            fields["product_characteristic"] = sf.get("name")
            fields["specification_tolerance"] = sf.get("specification")
            fields["special_class"] = sf.get("classification")

        # Process characteristic from work element functions
        for we in work_elements:
            we_funcs = _children(we["id"], "ProcessWorkElementFunction")
            if we_funcs:
                fields["process_characteristic"] = we_funcs[0].get("name")
                break

        return fields

    preview: list[dict] = []
    seen_node_ids: set[str] = set()

    for step in step_nodes:
        node_id = step["id"]
        seen_node_ids.add(node_id)
        fmea_fields = _derive_item_fields(step)

        if node_id in existing_by_node:
            # Existing item — check for field differences
            item = existing_by_node[node_id]
            current_value: dict = {}
            merged_value: dict = {}
            has_changes = False

            for field in _SYNCABLE_ITEM_FIELDS:
                cur = getattr(item, field, None) or ""
                new = fmea_fields.get(field) or ""
                current_value[field] = cur or None
                # FMEA overwrites where it has data; keep current where FMEA is empty
                merged = new if new else cur
                merged_value[field] = merged or None
                if cur != new:
                    has_changes = True

            if has_changes:
                preview.append({
                    "item_id": str(item.item_id),
                    "source_fmea_node_id": node_id,
                    "step_no": fmea_fields["step_no"],
                    "action": "sync",
                    "current_value": current_value,
                    "fmea_new_value": fmea_fields,
                    "merged_value": merged_value,
                })
        else:
            # New FMEA node — propose "add" with pre-generated UUID
            preview.append({
                "item_id": str(uuid.uuid4()),
                "source_fmea_node_id": node_id,
                "step_no": fmea_fields["step_no"],
                "action": "add",
                "current_value": None,
                "fmea_new_value": fmea_fields,
                "merged_value": fmea_fields,
            })

    # Items with source_fmea_node_id that no longer exist in the FMEA graph
    for item in current_items:
        if item.source_fmea_node_id and item.source_fmea_node_id not in seen_node_ids:
            preview.append({
                "item_id": str(item.item_id),
                "source_fmea_node_id": item.source_fmea_node_id,
                "step_no": item.step_no,
                "action": "delete",
                "current_value": {
                    f: getattr(item, f, None) for f in _SYNCABLE_ITEM_FIELDS
                },
                "fmea_new_value": None,
                "merged_value": None,
            })

    return preview


async def apply_sync_preview(
    db: AsyncSession,
    cp: ControlPlan,
    fmea_version: FMEAVersion,
    accepted_item_ids: list[str],
    user_id: uuid.UUID,
) -> ControlPlanVersion:
    """Apply accepted sync preview items to the control plan.

    For each preview_item:
      - "add": create ControlPlanItem with the pre-generated UUID and source_fmea_node_id
      - "sync": update existing item fields
      - "delete": remove the item

    Then create a CP version with change_type="fmea_sync".
    """
    preview = await build_sync_preview(db, cp, fmea_version)
    accepted_set = set(accepted_item_ids)

    for preview_item in preview:
        item_id_str = preview_item["item_id"]
        if item_id_str not in accepted_set:
            continue

        action = preview_item["action"]
        merged = preview_item["merged_value"] or {}

        if action == "add":
            new_item = ControlPlanItem(
                item_id=uuid.UUID(item_id_str),  # use pre-generated UUID
                cp_id=cp.cp_id,
                step_no=preview_item.get("step_no"),
                process_name=merged.get("process_name"),
                equipment=merged.get("equipment"),
                product_characteristic=merged.get("product_characteristic"),
                process_characteristic=merged.get("process_characteristic"),
                special_class=merged.get("special_class"),
                specification_tolerance=merged.get("specification_tolerance"),
                source_fmea_node_id=preview_item["source_fmea_node_id"],
            )
            db.add(new_item)

        elif action == "sync":
            result = await db.execute(
                select(ControlPlanItem).where(
                    ControlPlanItem.item_id == uuid.UUID(item_id_str)
                )
            )
            item = result.scalar_one_or_none()
            if item:
                for field in _SYNCABLE_ITEM_FIELDS:
                    val = merged.get(field)
                    if val is not None:
                        setattr(item, field, val)

        elif action == "delete":
            result = await db.execute(
                select(ControlPlanItem).where(
                    ControlPlanItem.item_id == uuid.UUID(item_id_str)
                )
            )
            item = result.scalar_one_or_none()
            if item:
                await db.delete(item)

    # Update CP sync tracking
    cp.source_fmea_version_id = fmea_version.version_id
    cp.sync_pending = False
    cp.updated_by = user_id

    # Create a CP version snapshot
    version = await create_cp_version(
        db,
        cp,
        change_type="fmea_sync",
        change_summary=f"从FMEA版本 v{fmea_version.major_no}.{fmea_version.minor_no} 同步",
        user_id=user_id,
        source_fmea_version_id=fmea_version.version_id,
    )

    # Audit log
    db.add(AuditLog(
        table_name="control_plans",
        record_id=cp.cp_id,
        action="SYNC_FMEA",
        changed_fields={
            "fmea_version_id": str(fmea_version.version_id),
            "accepted_items": len(accepted_item_ids),
            "new_cp_version": f"v{version.major_no}.{version.minor_no}",
        },
        operated_by=user_id,
    ))

    await db.commit()
    await db.refresh(cp)
    await db.refresh(version)
    return version
