import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.fmea import FMEADocument
from app.state_machines.fmea_state import FMEAState, can_transition
from app.models.audit import AuditLog
from app.services.product_line_service import validate_product_line
from app.services.version_service import create_fmea_version


async def list_fmeas(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    product_line: str | None = None,
    high_rpn: bool = False,
) -> tuple[list[FMEADocument], int]:
    query = select(FMEADocument)
    count_query = select(func.count(FMEADocument.fmea_id))

    if status:
        query = query.where(FMEADocument.status == status)
        count_query = count_query.where(FMEADocument.status == status)

    if product_line:
        query = query.where(FMEADocument.product_line_code == product_line)
        count_query = count_query.where(FMEADocument.product_line_code == product_line)

    if high_rpn:
        from app.utils.fmea_graph import build_rpn_rows
        query = query.order_by(FMEADocument.created_at.desc())
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
) -> FMEADocument:
    changed_fields = {}
    if title is not None:
        changed_fields["title"] = title
        fmea.title = title
    if graph_data is not None:
        changed_fields["graph_data"] = graph_data
        fmea.graph_data = graph_data
    if product_line_code is not None:
        await validate_product_line(db, product_line_code)
        changed_fields["product_line_code"] = product_line_code
        fmea.product_line_code = product_line_code
    fmea.updated_by = user_id

    if changed_fields:
        audit_log = AuditLog(
            table_name="fmea_documents",
            record_id=fmea.fmea_id,
            action="UPDATE",
            changed_fields=changed_fields,
            operated_by=user_id,
        )
        db.add(audit_log)

    await db.commit()
    await db.refresh(fmea)
    return fmea


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
        fmea.approved_at = datetime.now(timezone.utc)

    # Create version snapshot on submit or approve
    version = None
    if target in (FMEAState.IN_REVIEW, FMEAState.APPROVED):
        change_type = "approve" if target == FMEAState.APPROVED else "submit"
        change_summary = (
            f"状态变更：{old_status} → {target_status}"
            if target == FMEAState.IN_REVIEW
            else "审批通过，版本发布"
        )
        version = await create_fmea_version(db, fmea, change_type, change_summary, user_id)

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

    await db.commit()

    # Trigger CP sync when FMEA is approved
    if target == FMEAState.APPROVED and version:
        from app.services.control_plan_service import mark_cp_sync_pending_on_fmea_approve
        await mark_cp_sync_pending_on_fmea_approve(db, fmea.fmea_id, version.version_id)

    await db.refresh(fmea)
    return fmea
