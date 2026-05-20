import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.fmea import FMEADocument
from app.state_machines.fmea_state import FMEAState, can_transition
from app.models.audit import AuditLog


async def list_fmeas(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[FMEADocument], int]:
    query = select(FMEADocument)
    count_query = select(func.count(FMEADocument.fmea_id))

    if status:
        query = query.where(FMEADocument.status == status)
        count_query = count_query.where(FMEADocument.status == status)

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
    db: AsyncSession, title: str, document_no: str, fmea_type: str, user_id: uuid.UUID
) -> FMEADocument:
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
) -> FMEADocument:
    changed_fields = {}
    if title is not None:
        changed_fields["title"] = title
        fmea.title = title
    if graph_data is not None:
        changed_fields["graph_data"] = graph_data
        fmea.graph_data = graph_data
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
    await db.refresh(fmea)
    return fmea
