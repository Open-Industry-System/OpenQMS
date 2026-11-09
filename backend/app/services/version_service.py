"""Version management service for FMEA documents and Control Plans.

Provides SHA-256 integrity hashing, version CRUD, rollback, and FMEA-to-CP sync.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Iterable

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.control_plan_version import ControlPlanVersion
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.state_machines.eightd_state import capa_open_clause

# ---------------------------------------------------------------------------
# SHA-256 helpers
# ---------------------------------------------------------------------------

def _canonical_json(data: dict | list) -> str:
    """Legacy compact JSON (kept for non-DB callers / tests).

    Version-table integrity uses compute_pg_jsonb_hash (matches the
    verify_version_hash trigger: encode(digest(jsonb::text,'sha256'),'hex')).
    """
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_snapshot_hash(snapshot: dict | list) -> str:
    """Legacy compact-JSON hash. Prefer compute_pg_jsonb_hash for version rows."""
    return hashlib.sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()


async def compute_pg_jsonb_hash(db: AsyncSession, payload: dict | list) -> str:
    """SHA-256 of PostgreSQL jsonb::text — matches verify_version_hash trigger.

    Trigger sets sha256_hash = encode(digest(payload::text, 'sha256'), 'hex')
    where payload is NEW.snapshot (FMEA) or jsonb_build_object('header',...,'items',...)
    (CP). App must use the same digest so pre-insert values and post-insert
    verification agree.
    """
    result = await db.execute(
        text("SELECT encode(public.digest(CAST(:p AS JSONB)::text, 'sha256'), 'hex')"),
        {"p": json.dumps(payload, ensure_ascii=False)},
    )
    return result.scalar_one()


def verify_snapshot_hash(snapshot: dict | list, stored_hash: str) -> bool:
    """Legacy compact-JSON verify. Version rows should use verify_version_row_hash."""
    return compute_snapshot_hash(snapshot) == stored_hash


async def lock_version_parent(
    db: AsyncSession, doc_type: str, doc_id: uuid.UUID
) -> None:
    """Serialize version creation and audit-bound waiver decisions per document."""
    if doc_type == "control_plan":
        stmt = select(ControlPlan.cp_id).where(ControlPlan.cp_id == doc_id)
    elif doc_type == "fmea":
        stmt = select(FMEADocument.fmea_id).where(FMEADocument.fmea_id == doc_id)
    else:
        raise ValueError(f"Unsupported versioned document type: {doc_type}")
    if await db.scalar(stmt.with_for_update()) is None:
        raise ValueError(f"Version parent not found: {doc_type}/{doc_id}")


async def lock_version_parents_in_order(
    db: AsyncSession,
    documents: Iterable[tuple[str, uuid.UUID | str]],
) -> None:
    """Lock a document set deterministically for cross-service serialization."""
    try:
        identities = {
            (str(doc_type), uuid.UUID(str(doc_id)))
            for doc_type, doc_id in documents
        }
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Invalid version parent identity") from exc
    for doc_type, doc_id in sorted(identities, key=lambda row: (row[0], str(row[1]))):
        await lock_version_parent(db, doc_type, doc_id)


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


async def _create_fmea_version_no_commit(
    db: AsyncSession,
    fmea: FMEADocument,
    change_type: str,
    change_summary: str | None,
    user_id: uuid.UUID,
) -> FMEAVersion:
    """Build and stage a new FMEA version (flush, no commit).

    Callers must commit the session themselves.
    """
    await lock_version_parent(db, "fmea", fmea.fmea_id)
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
    # Content-bound hash via PG jsonb::text (matches verify_version_hash trigger)
    sha256_hash = await compute_pg_jsonb_hash(db, snapshot)

    version = FMEAVersion(
        version_id=uuid.uuid4(),
        fmea_id=fmea.fmea_id,
        factory_id=fmea.factory_id,
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

    await db.flush()
    await db.refresh(version)
    return version


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
    version = await _create_fmea_version_no_commit(db, fmea, change_type, change_summary, user_id)
    await db.commit()
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
    """Verify stored FMEA version hash (accepts PG jsonb::text or legacy compact JSON)."""
    result = await db.execute(
        select(FMEAVersion).where(FMEAVersion.version_id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise ValueError(f"FMEA version {version_id} not found.")
    if not version.sha256_hash:
        return False
    pg_hash = await compute_pg_jsonb_hash(db, version.snapshot)
    if version.sha256_hash == pg_hash:
        return True
    # Historical rows written with compact JSON before PG-aligned trigger
    return version.sha256_hash == compute_snapshot_hash(version.snapshot)


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


async def stage_cp_version(
    db: AsyncSession,
    cp: ControlPlan,
    change_type: str,
    change_summary: str | None,
    user_id: uuid.UUID,
    source_fmea_version_id: uuid.UUID | None = None,
) -> ControlPlanVersion:
    """Stage a CP snapshot and audit; flush only, never commit or refresh.

    Header snapshot captures scalar CP fields.  Items snapshot is a list of
    dicts, each preserving the ``item_id`` UUID string for identity tracking.

    * ``change_type == "approve"`` bumps major_no, resets minor_no to 0.
    * All other types bump minor_no.
    """
    await lock_version_parent(db, "control_plan", cp.cp_id)
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
            "source_characteristic_ref": item.source_characteristic_ref,
            "sort_order": item.sort_order,
        })

    # Content-bound hash via PG jsonb::text (matches verify_version_hash trigger)
    combined = {"header": header_snapshot, "items": items_snapshot}
    sha256_hash = await compute_pg_jsonb_hash(db, combined)

    version = ControlPlanVersion(
        version_id=uuid.uuid4(),
        cp_id=cp.cp_id,
        factory_id=cp.factory_id,
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

    await db.flush()
    return version


async def create_cp_version(
    db: AsyncSession,
    cp: ControlPlan,
    change_type: str,
    change_summary: str | None,
    user_id: uuid.UUID,
    source_fmea_version_id: uuid.UUID | None = None,
) -> ControlPlanVersion:
    """Compatibility wrapper retaining the existing committing behavior."""
    version = await stage_cp_version(
        db, cp, change_type, change_summary, user_id, source_fmea_version_id,
    )
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
    """Verify stored CP version hash (accepts PG jsonb::text or legacy compact JSON)."""
    result = await db.execute(
        select(ControlPlanVersion).where(ControlPlanVersion.version_id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise ValueError(f"Control Plan version {version_id} not found.")
    if not version.sha256_hash:
        return False
    combined = {"header": version.header_snapshot, "items": version.items_snapshot}
    pg_hash = await compute_pg_jsonb_hash(db, combined)
    if version.sha256_hash == pg_hash:
        return True
    # Historical rows written with compact JSON before PG-aligned trigger
    return version.sha256_hash == compute_snapshot_hash(combined)


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
        .where(capa_open_clause(CAPAEightD.status))  # P2: 仅「未关闭」CAPA 阻断回滚；ARCHIVED 不算活动
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
    version = await _create_fmea_version_no_commit(
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
            existing.source_characteristic_ref = snap.get("source_characteristic_ref")
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
                source_characteristic_ref=snap.get("source_characteristic_ref"),
                factory_id=cp.factory_id,
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

# Source-owned fields, projected by the same mapper as initial import.
_SYNCABLE_ITEM_FIELDS = ('step_no', 'process_name', 'equipment', 'product_characteristic',
                         'process_characteristic', 'special_class', 'specification_tolerance')


async def get_fmea_version_by_id(db: AsyncSession, version_id: uuid.UUID) -> FMEAVersion | None:
    """Return an FMEA version by its version_id (existing compatibility helper)."""
    return await db.scalar(select(FMEAVersion).where(FMEAVersion.version_id == version_id))


async def _sync_context(db, cp_id, source_version_id, scope, *, expected_lock=None, lock=False):
    from types import SimpleNamespace
    from app.services import control_plan_service as cps
    await cps._import_tenant_boundary(db, extra_tables=(
        "capa_eightd", "capa_docg_analysis", "capa_docg_audit", "capa_docg_decision", "special_characteristics"))
    cp = await db.scalar(select(ControlPlan).where(ControlPlan.cp_id == cp_id)
                         .execution_options(populate_existing=True))
    if cp is None or cp.fmea_ref_id is None:
        raise cps.CharacteristicImportError('控制计划或关联来源不存在', 404)
    factory_scope, pl_scope = await cps._import_authority(db, scope, lock=False)
    cps._import_check_access(cp, scope, factory_scope, pl_scope)
    if source_version_id is None:
        versions = list((await db.scalars(select(FMEAVersion).where(
            FMEAVersion.fmea_id == cp.fmea_ref_id, FMEAVersion.factory_id == cp.factory_id,
            FMEAVersion.change_type == 'approve', FMEAVersion.minor_no == 0,
            FMEAVersion.major_no >= 1).order_by(FMEAVersion.major_no.desc()))).all())
        if not versions or (len(versions) > 1 and versions[0].major_no == versions[1].major_no):
            raise cps.CharacteristicImportError('无法唯一确定批准来源，请明确选择版本')
        source_version_id = versions[0].version_id
    req = SimpleNamespace(fmea_id=cp.fmea_ref_id, source_fmea_version_id=source_version_id,
                          expected_lock_version=cp.lock_version if expected_lock is None else expected_lock)
    return await cps._characteristic_import_context(db, cp_id, req, scope, lock=lock)


def _mapped_snapshot(fmea_id, snapshot):
    from app.services.cp_characteristic_mapping import derive_cp_items, MappingResult
    steps = tuple(str(n['id']) for n in snapshot.get('nodes', []) if n.get('type') == 'ProcessStep')
    return derive_cp_items(fmea_id=fmea_id, fmea_type='PFMEA', graph=snapshot, step_ids=steps) if steps else MappingResult((), ())


async def _sync_projection(db, cp, fmea, version, tenant, *, lock=False):
    from dataclasses import asdict
    from app.schemas.characteristic import CharacteristicSourceRef
    from app.services.fmea_characteristics import source_key
    from app.services.cp_characteristic_mapping import candidate_key
    from app.services.cp_sync_protection import sync_protection, row_material
    from app.services.control_plan_service import CharacteristicImportError
    query = select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id).order_by(
        ControlPlanItem.sort_order, ControlPlanItem.item_id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    existing = list((await db.scalars(query)).all())
    if any(i.factory_id != cp.factory_id for i in existing):
        raise CharacteristicImportError('控制计划行范围不一致')
    mapped = _mapped_snapshot(fmea.fmea_id, version.snapshot)
    issues = [asdict(i) for i in mapped.issues]
    target = {source_key(i.source_ref): i for i in mapped.items}
    blocking_mapping = any(i.blocking for i in mapped.issues)
    codes, execution, protection_digest = await sync_protection(db, cp, existing)
    baselines, seen, candidates = {}, set(), []
    for row in existing:
        iid = str(row.item_id)
        current = {f: getattr(row, f) for f in _SYNCABLE_ITEM_FIELDS}
        try:
            ref = CharacteristicSourceRef.model_validate(row.source_characteristic_ref)
            if ref.fmea_id != fmea.fmea_id or ref.mapping_version != 1 or ref.step_id != row.source_fmea_node_id:
                raise ValueError('source mismatch')
        except (ValueError, TypeError):
            issues.append({'code': 'manual_or_legacy_source', 'item_id': iid, 'blocking': True,
                           'message': '人工或历史混合来源需人工确认，不重绑或删除'})
            continue
        key = source_key(ref)
        seen.add(key)
        new = target.get(key)
        baseline_id = ref.accepted_source_version_id
        if baseline_id not in baselines:
            v = await db.scalar(select(FMEAVersion).where(
                FMEAVersion.version_id == baseline_id, FMEAVersion.fmea_id == fmea.fmea_id,
                FMEAVersion.factory_id == cp.factory_id)) if baseline_id else None
            if (v is not None and v.change_type == 'approve' and v.major_no >= 1 and v.minor_no == 0
                    and await verify_fmea_version(db, v.version_id)):
                bm = _mapped_snapshot(fmea.fmea_id, v.snapshot)
                baselines[baseline_id] = ({source_key(i.source_ref): i for i in bm.items}
                                          if not any(i.blocking for i in bm.issues) else {})
            else:
                baselines[baseline_id] = {}
        base = baselines[baseline_id].get(key)
        conflict = []
        if base is None or base.source_ref.work_element_id != ref.work_element_id:
            conflict.append({'code': 'baseline_unavailable', 'message': '无可信逐行接受基线，需人工复核'})
        action = 'sync' if new else 'delete'
        merged = dict(current) if new else None
        if new and base:
            for field in _SYNCABLE_ITEM_FIELDS:
                b, n, c = base.fields[field], new.fields[field], current[field]
                source_changed, local_changed = n != b, c != b
                if source_changed and local_changed and c != n:
                    conflict.append({'code': 'three_way_conflict', 'field': field, 'base': b, 'current': c, 'source': n})
                if source_changed:
                    merged[field] = n
        elif base and not new and any(current[f] != base.fields[f] for f in _SYNCABLE_ITEM_FIELDS):
            conflict.append({'code': 'local_change_on_delete', 'message': '本地源字段已修改，不自动删除'})
        new_ref = new.source_ref.model_copy(update={'accepted_source_version_id': version.version_id}) if new else ref
        source_changed = not new or not base or any(new.fields[f] != base.fields[f] for f in _SYNCABLE_ITEM_FIELDS)
        if new and base and not conflict and not source_changed and new_ref.work_element_id == ref.work_element_id:
            local_fields = [f for f in _SYNCABLE_ITEM_FIELDS if current[f] != new.fields[f]]
            if local_fields:
                issues.append({'code': 'local_source_override', 'item_id': iid, 'blocking': False,
                               'diff_fields': local_fields, 'current_value': current,
                               'fmea_new_value': new.fields, 'message': '保留本地源字段修改，请复核'})
            continue  # no source change: never rebase protected material solely for metadata
        row_issues = []
        if blocking_mapping:
            row_issues.append({'code': 'source_projection_blocked', 'blocking': True})
        for code in codes[iid]:
            row_issues.append({'code': code, 'blocking': True, 'message': '存在受控流程引用，需复核'})
        if action == 'delete' and iid in execution:
            row_issues.append({'code': 'linked_execution_reference', 'blocking': True,
                               'message': '执行或特殊特性关联禁止自动删除'})
        elif iid in execution:
            row_issues.append({'code': 'review_execution_applicability', 'blocking': False,
                               'message': '保留执行关联，请复核适用性'})
        candidates.append({'candidate_key': candidate_key(action, ref, row.item_id), 'item_id': iid,
                           'source_fmea_node_id': ref.step_id, 'source_ref': new_ref.model_dump(mode='json'),
                           'step_no': new.fields['step_no'] if new else row.step_no, 'action': action,
                           'current_value': current, 'base_value': base.fields if base else None,
                           'fmea_new_value': new.fields if new else None, 'merged_value': merged,
                           'diff_fields': [f for f in _SYNCABLE_ITEM_FIELDS if not new or current[f] != new.fields[f]],
                           'issues': row_issues, 'conflicts': conflict,
                           'applicable': not conflict and not any(i['blocking'] for i in row_issues)})
    for key, new in target.items():
        if key in seen:
            continue
        ref = new.source_ref.model_copy(update={'accepted_source_version_id': version.version_id})
        candidates.append({'candidate_key': candidate_key('add', ref, None), 'item_id': None,
                           'source_fmea_node_id': ref.step_id, 'source_ref': ref.model_dump(mode='json'),
                           'step_no': new.fields['step_no'], 'action': 'add', 'current_value': None,
                           'base_value': None, 'fmea_new_value': new.fields, 'merged_value': new.fields,
                           'diff_fields': list(_SYNCABLE_ITEM_FIELDS), 'issues': [], 'conflicts': [],
                           'applicable': not blocking_mapping})
    preview = {'source_fmea_version_id': str(version.version_id), 'fmea_version_id': str(version.version_id),
               'fmea_version': f'v{version.major_no}.{version.minor_no}',
               'expected_lock_version': cp.lock_version, 'mapping_version': 1,
               'items': candidates, 'issues': issues,
               'summary': {'add_count': sum(i['action'] == 'add' for i in candidates),
                           'update_count': sum(i['action'] == 'sync' for i in candidates),
                           'delete_count': sum(i['action'] == 'delete' for i in candidates)}}
    preview['preview_digest'] = compute_snapshot_hash({**preview, 'tenant': tenant, 'cp_id': str(cp.cp_id),
        'status': cp.status, 'factory': str(cp.factory_id), 'product_line': cp.product_line_code,
        'source_hash': version.sha256_hash, 'accepted_global': str(cp.source_fmea_version_id),
        'protection': protection_digest, 'rows': [row_material(i) for i in existing]})
    return preview, existing


async def build_sync_preview(db, cp_id, source_fmea_version_id=None, *, scope):
    """Fresh-authority read-only preview of an immutable approved target."""
    with db.no_autoflush:
        context = await _sync_context(db, cp_id, source_fmea_version_id, scope)
        preview, _ = await _sync_projection(db, *context)
        return preview


async def apply_sync_preview(db, cp_id, req, user_id, *, scope):
    """Apply stable candidate selections atomically; own the sole outer commit."""
    from app.services.control_plan_service import CharacteristicImportError, _cp_has_handled_latest_approval
    from app.schemas.version import ControlPlanVersionListItem
    if scope is None or scope.user.user_id != user_id:
        raise CharacteristicImportError('需要当前请求授权上下文', 403)
    if (req.source_fmea_version_id is None or req.expected_lock_version is None
            or not req.preview_digest or req.selected_candidate_keys is None or req.selected_item_ids):
        raise CharacteristicImportError('缺少稳定预览上下文，请重新预览')
    keys = req.selected_candidate_keys
    if len(keys) != len(set(keys)):
        raise CharacteristicImportError('重复候选选择')
    savepoint = await db.begin_nested()
    released = False
    try:
        context = await _sync_context(db, cp_id, req.source_fmea_version_id, scope,
                                      expected_lock=req.expected_lock_version, lock=True)
        cp, fmea, version, tenant = context
        preview, existing = await _sync_projection(db, *context, lock=True)
        if preview['preview_digest'] != req.preview_digest:
            logging.getLogger(__name__).warning('CP_SYNC_REJECTED cp=%s actor=%s reason=stale_preview basis=%s',
                                                cp_id, user_id, preview['preview_digest'])
            raise CharacteristicImportError('预览已过期，请重新预览')
        candidates = {i['candidate_key']: i for i in preview['items']}
        if not set(keys) <= candidates.keys() or any(not candidates[k]['applicable'] for k in keys):
            reasons = [{'item_id': candidates[k]['item_id'], 'action': candidates[k]['action'],
                        'codes': [i['code'] for i in candidates[k]['issues'] + candidates[k]['conflicts']]}
                       for k in keys if k in candidates and not candidates[k]['applicable']]
            logging.getLogger(__name__).warning('CP_SYNC_REJECTED cp=%s actor=%s reason=blocked_selection basis=%s rows=%s',
                                                cp_id, user_id, preview['preview_digest'], reasons)
            raise CharacteristicImportError('所选候选存在冲突或保护，需复核')
        if any(i['blocking'] for i in preview['issues'] if i['code'] != 'manual_or_legacy_source'):
            raise CharacteristicImportError('来源投影存在阻塞问题')
        if not keys:
            if preview['items'] or any(i['blocking'] for i in preview['issues']):
                raise CharacteristicImportError('仍有待处理项，请选择可应用候选')
            if (cp.source_fmea_version_id == version.version_id and not cp.sync_pending
                    and await _cp_has_handled_latest_approval(db, cp)):
                latest = await get_latest_cp_version(db, cp_id)
                if latest is not None:
                    response = ControlPlanVersionListItem.model_validate(latest)
                    await savepoint.commit()
                    released = True
                    await db.commit()
                    return response
        by_id = {str(i.item_id): i for i in existing}
        order = max((i.sort_order for i in existing), default=-1) + 1
        for key in keys:
            candidate = candidates[key]
            action = candidate['action']
            if action == 'add':
                db.add(ControlPlanItem(item_id=uuid.uuid4(), cp_id=cp_id, factory_id=cp.factory_id,
                    sort_order=order, item_source='fmea', source_fmea_node_id=candidate['source_ref']['step_id'],
                    source_characteristic_ref=candidate['source_ref'], **candidate['merged_value']))
                order += 1
            elif action == 'sync':
                row = by_id[candidate['item_id']]
                for field in _SYNCABLE_ITEM_FIELDS:
                    setattr(row, field, candidate['merged_value'][field])
                row.source_characteristic_ref = candidate['source_ref']
            else:
                await db.delete(by_id[candidate['item_id']])
        await db.flush()
        remaining, _ = await _sync_projection(db, *context, lock=True)
        selected_pending = bool(remaining['items'] or any(i['blocking'] for i in remaining['issues']))
        if not selected_pending:
            cp.source_fmea_version_id = version.version_id
        cp.sync_pending = selected_pending or not await _cp_has_handled_latest_approval(db, cp)
        cp.updated_by = user_id
        cp.lock_version += 1
        staged = await stage_cp_version(db, cp, 'fmea_sync', 'PFMEA 逐特性同步', user_id,
                                        source_fmea_version_id=version.version_id)
        db.add(AuditLog(table_name='control_plans', record_id=cp_id, action='SYNC_FMEA',
            operated_by=user_id, factory_id=cp.factory_id, changed_fields={
                'source_fmea_version_id': str(version.version_id), 'selected_candidate_keys': keys,
                'preview_digest': req.preview_digest, 'sync_pending': cp.sync_pending}))
        await db.flush()
        response = ControlPlanVersionListItem.model_validate(staged)
        await savepoint.commit()
        released = True
        await db.commit()
        return response
    except Exception:
        if released:
            await db.rollback()
        else:
            await savepoint.rollback()
        raise
