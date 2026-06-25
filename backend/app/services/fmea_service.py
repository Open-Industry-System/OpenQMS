import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.control_plan import ControlPlan
from app.models.customer_quality import CustomerComplaint, RMARecord
from app.models.fmea import FMEADocument
from app.models.graph_sync_outbox import GraphSyncOutbox
from app.models.special_characteristic import SpecialCharacteristic
from app.models.spc import SPCAlarm
from app.services.embedding_outbox import delete_embeddings_for_entity, enqueue_embedding
from app.services.product_line_service import validate_product_line
from app.services.version_service import _create_fmea_version_no_commit
from app.state_machines.fmea_state import FMEAState, can_transition


async def list_fmeas(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    product_line: str | None = None,
    high_rpn: bool = False,
    allowed_product_line_codes: list[str] | None = None,
    factory_id: uuid.UUID | None = None,
    fmea_type: str | None = None,
    search: str | None = None,
) -> tuple[list[FMEADocument], int]:
    query = select(FMEADocument)
    count_query = select(func.count(FMEADocument.fmea_id))

    if status:
        query = query.where(FMEADocument.status == status)
        count_query = count_query.where(FMEADocument.status == status)

    if product_line:
        query = query.where(FMEADocument.product_line_code == product_line)
        count_query = count_query.where(FMEADocument.product_line_code == product_line)

    if allowed_product_line_codes is not None:
        query = query.where(FMEADocument.product_line_code.in_(allowed_product_line_codes))
        count_query = count_query.where(FMEADocument.product_line_code.in_(allowed_product_line_codes))

    if factory_id is not None:
        query = query.where(FMEADocument.factory_id == factory_id)
        count_query = count_query.where(FMEADocument.factory_id == factory_id)

    if fmea_type:
        query = query.where(FMEADocument.fmea_type == fmea_type)
        count_query = count_query.where(FMEADocument.fmea_type == fmea_type)

    if search and search.strip():
        safe = re.sub(r"([%_\\])", r"\\\1", search.strip())
        like_clause = or_(
            FMEADocument.document_no.ilike(f"%{safe}%", escape="\\"),
            FMEADocument.title.ilike(f"%{safe}%", escape="\\"),
        )
        query = query.where(like_clause)
        count_query = count_query.where(like_clause)

    if high_rpn:
        from app.utils.fmea_graph import build_rpn_rows
        # TEMP: filter in Python. TODO: add max_rpn materialized column
        MAX_HIGH_RPN_SCAN = 500
        query = query.order_by(FMEADocument.created_at.desc()).limit(MAX_HIGH_RPN_SCAN)
        all_docs = (await db.execute(query)).scalars().all()
        filtered = []
        for doc in all_docs:
            nodes = doc.graph_data.get("nodes", []) if doc.graph_data else []
            edges = doc.graph_data.get("edges", []) if doc.graph_data else []
            rows = build_rpn_rows(nodes, edges)
            has_high = any(
                r.get("severity", 0) * r.get("occurrence", 0) * r.get("detection", 0) >= 100
                for r in rows
                if r.get("severity", 0) > 0
            )
            if has_high:
                filtered.append(doc)
        total = len(filtered)
        items = filtered[(page - 1) * page_size : page * page_size]
        return items, total

    query = query.order_by(FMEADocument.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return items, total


async def get_fmea(db: AsyncSession, fmea_id: uuid.UUID) -> FMEADocument | None:
    result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == fmea_id))
    return result.scalar_one_or_none()


async def create_fmea(
    db: AsyncSession, title: str, document_no: str, fmea_type: str, user_id: uuid.UUID,
    product_line_code: str = "DC-DC-100",
    factory_id: uuid.UUID | None = None,
) -> FMEADocument:
    await validate_product_line(db, product_line_code)
    # Check if duplicate document_no exists
    existing_result = await db.execute(
        select(FMEADocument).where(FMEADocument.document_no == document_no)
    )
    if existing_result.scalar_one_or_none():
        raise ValueError(f"FMEA document number '{document_no}' already exists.")

    fmea_id = uuid.uuid4()
    
    # Initialize templates based on FMEA type
    graph_data = {"nodes": [], "edges": []}
    if fmea_type == "PFMEA":
        graph_data["nodes"].append({
            "id": f"pi_{uuid.uuid4().hex[:8]}",
            "type": "ProcessItem",
            "name": "新建过程项目",
            "severity": 0,
            "occurrence": 0,
            "detection": 0
        })
    elif fmea_type == "DFMEA":
        graph_data["nodes"].append({
            "id": f"sys_{uuid.uuid4().hex[:8]}",
            "type": "System",
            "name": "新建系统",
            "severity": 0,
            "occurrence": 0,
            "detection": 0
        })

    fmea = FMEADocument(
        fmea_id=fmea_id,
        title=title,
        document_no=document_no,
        fmea_type=fmea_type,
        product_line_code=product_line_code,
        created_by=user_id,
        updated_by=user_id,
        graph_data=graph_data,  # Inject template graph
        factory_id=factory_id,
    )
    db.add(fmea)

    # Audit log
    audit_log = AuditLog(
        table_name="fmea_documents",
        record_id=fmea_id,
        action="CREATE",
        changed_fields={
            "title": title,
            "document_no": document_no,
            "fmea_type": fmea_type,
            "product_line_code": product_line_code,
            "status": fmea.status,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    # Outbox: enqueue Neo4j projection sync
    db.add(GraphSyncOutbox(
        aggregate_type="fmea",
        aggregate_id=fmea_id,
        event_type="fmea.created",
        payload={"version": 1, "product_line_code": product_line_code, "fmea_type": fmea_type},
    ))

    await enqueue_embedding(db, "fmea_node", fmea.fmea_id, fmea.product_line_code, fmea.factory_id)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"FMEA document number '{document_no}' already exists.")

    await db.refresh(fmea)
    return fmea


async def update_fmea(
    db: AsyncSession,
    fmea: FMEADocument,
    title: str | None,
    graph_data: dict | None,
    user_id: uuid.UUID,
    product_line_code: str | None = None,
    lock_version: int | None = None,
    confirmed_latest_lock_version: int | None = None,
) -> FMEADocument:
    # 原子乐观锁校验：强制刷新 + SELECT ... FOR UPDATE
    result = await db.execute(
        select(FMEADocument)
        .where(FMEADocument.fmea_id == fmea.fmea_id)
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

    changed_fields = {}
    if title is not None and title != fmea.title:
        changed_fields["title"] = title
        fmea.title = title
    if graph_data is not None:
        import json
        old_graph = json.dumps(fmea.graph_data, sort_keys=True) if fmea.graph_data else ""
        new_graph = json.dumps(graph_data, sort_keys=True)
        if new_graph != old_graph:
            changed_fields["graph_data"] = graph_data
            fmea.graph_data = graph_data
    if product_line_code is not None and product_line_code != fmea.product_line_code:
        await validate_product_line(db, product_line_code)
        changed_fields["product_line_code"] = product_line_code
        fmea.product_line_code = product_line_code
    fmea.updated_by = user_id

    if changed_fields:
        fmea.lock_version += 1  # 只在有实际变更时递增乐观锁版本
        audit_log = AuditLog(
            table_name="fmea_documents",
            record_id=fmea.fmea_id,
            action="UPDATE",
            changed_fields=changed_fields,
            operated_by=user_id,
        )
        db.add(audit_log)

        # Outbox: enqueue Neo4j projection sync
        db.add(GraphSyncOutbox(
            aggregate_type="fmea",
            aggregate_id=fmea.fmea_id,
            event_type="fmea.updated",
            payload={"version": fmea.version, "product_line_code": fmea.product_line_code},
        ))

        # 强制覆盖时记录审计日志
        if confirmed_latest_lock_version is not None:
            force_audit = AuditLog(
                table_name="fmea_documents",
                record_id=fmea.fmea_id,
                action="FORCE_SAVE_OVERRIDE",
                changed_fields={"reason": "User confirmed overwrite after conflict detection"},
                operated_by=user_id,
            )
            db.add(force_audit)

        # Invalidate recommendation cache when graph_data or product_line changes
        if graph_data is not None or product_line_code is not None:
            from app.services.recommendation_service import RecommendationService, _NullGraphRepo
            rec_service = RecommendationService(db=db, llm_provider=None, graph_repo=_NullGraphRepo())
            await rec_service.invalidate_cache_for_fmea(fmea.fmea_id)

    await enqueue_embedding(db, "fmea_node", fmea.fmea_id, fmea.product_line_code, fmea.factory_id)
    await db.commit()
    await db.refresh(fmea)
    return fmea


async def delete_fmea(db: AsyncSession, fmea_id: uuid.UUID, user_id: uuid.UUID) -> None:
    fmea = await get_fmea(db, fmea_id)
    if fmea is None:
        raise ValueError("FMEA not found")
    # Audit log for deletion
    audit_log = AuditLog(
        table_name="fmea_documents",
        record_id=fmea_id,
        action="DELETE",
        changed_fields={"title": fmea.title, "document_no": fmea.document_no, "fmea_type": fmea.fmea_type},
        operated_by=user_id,
    )
    db.add(audit_log)
    # GraphSync outbox event for Neo4j projection cleanup
    db.add(GraphSyncOutbox(
        aggregate_type="fmea",
        aggregate_id=fmea_id,
        event_type="fmea.deleted",
        payload={"product_line_code": fmea.product_line_code, "fmea_type": fmea.fmea_type},
    ))
    # document_embeddings has no FK to fmea_documents (denormalized
    # entity_type/entity_id), so the row delete does not cascade — clean the
    # FMEA's node embeddings explicitly, in the same transaction, BEFORE commit.
    await delete_embeddings_for_entity(db, "fmea_node", fmea_id)
    # Several nullable FKs to fmea_documents have no ondelete clause (Postgres
    # NO ACTION): control_plans / capa_eightd / customer_complaints /
    # rma_records / special_characteristics / spc_alarms. Null them out in the
    # same transaction so deleting a (rework) FMEA that's still referenced by a
    # ControlPlan / CAPA / etc. doesn't raise IntegrityError. Mirrors the
    # ondelete=SET NULL already used by apqp.
    await _null_out_fmea_references(db, fmea_id)
    await db.delete(fmea)
    await db.commit()


async def _null_out_fmea_references(db: AsyncSession, fmea_id: uuid.UUID) -> None:
    """Set nullable fmea_ref_id / source_fmea_id / confirmed_fmea_id columns
    that point at fmea_id to NULL, so the FMEA row can be deleted without
    tripping a NO-ACTION FK constraint."""
    for model, column in (
        (ControlPlan, ControlPlan.fmea_ref_id),
        (CAPAEightD, CAPAEightD.fmea_ref_id),
        (CustomerComplaint, CustomerComplaint.fmea_ref_id),
        (RMARecord, RMARecord.fmea_ref_id),
        (SpecialCharacteristic, SpecialCharacteristic.source_fmea_id),
        (SPCAlarm, SPCAlarm.confirmed_fmea_id),
    ):
        await db.execute(update(model).where(column == fmea_id).values({column: None}))


async def transition_fmea(
    db: AsyncSession,
    fmea: FMEADocument,
    target_status: str,
    user_id: uuid.UUID,
) -> FMEADocument:
    current = FMEAState(fmea.status)
    target = FMEAState(target_status)

    if not can_transition(current, target):
        allowed = [s.value for s in FMEAState if can_transition(current, s)]
        raise ValueError(f"Cannot transition from {fmea.status} to {target_status}. Allowed: {allowed}")

    old_status = fmea.status
    fmea.status = target_status
    fmea.updated_by = user_id

    if target == FMEAState.APPROVED:
        fmea.approved_by = user_id
        fmea.approved_at = datetime.now(UTC)

    # Create version snapshot on submit or approve
    version = None
    if target in (FMEAState.IN_REVIEW, FMEAState.APPROVED):
        change_type = "approve" if target == FMEAState.APPROVED else "submit"
        change_summary = (
            f"状态变更：{old_status} → {target_status}"
            if target == FMEAState.IN_REVIEW
            else "审批通过，版本发布"
        )
        version = await _create_fmea_version_no_commit(db, fmea, change_type, change_summary, user_id)

    # Audit log
    audit_log = AuditLog(
        table_name="fmea_documents",
        record_id=fmea.fmea_id,
        action="TRANSITION",
        changed_fields={
            "old_status": old_status,
            "new_status": target_status,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    # Outbox: enqueue Neo4j projection sync
    db.add(GraphSyncOutbox(
        aggregate_type="fmea",
        aggregate_id=fmea.fmea_id,
        event_type="fmea.approved" if target == FMEAState.APPROVED else "fmea.updated",
        payload={"version": fmea.version, "product_line_code": fmea.product_line_code, "status": target_status},
    ))

    await db.commit()

    # Trigger CP sync when FMEA is approved
    if target == FMEAState.APPROVED and version:
        from app.services.control_plan_service import mark_cp_sync_pending_on_fmea_approve
        await mark_cp_sync_pending_on_fmea_approve(db, fmea.fmea_id, version.version_id)

    await db.refresh(fmea)
    return fmea
