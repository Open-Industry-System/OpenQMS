import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.supplier import Supplier, SupplierSCAR
from app.models.capa import CAPAEightD
from app.models.audit import AuditLog
from app.services.embedding_outbox import enqueue_embedding


SCAR_TRANSITIONS = {
    "start":   ("open",         "in_progress"),
    "respond": ("in_progress",  "responded"),
    "verify":  ("responded",    "verified"),
    "reject":  ("responded",    "open"),
    "close":   ("verified",     "closed"),
    "reopen":  ("verified",     "in_progress"),
}

SCAR_REQUIRED_FIELDS = {
    "respond": ["supplier_response"],
    "close":   ["resolution_summary"],
}


async def _next_scar_no(db: AsyncSession) -> str:
    today = datetime.now(timezone.utc).strftime("%y%m%d")
    prefix = f"SCAR-{today}"
    result = await db.execute(
        select(SupplierSCAR.scar_no)
        .where(SupplierSCAR.scar_no.like(f"{prefix}-%"))
        .order_by(SupplierSCAR.scar_no.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if last:
        seq = int(last.split("-")[-1]) + 1
    else:
        seq = 1
    return f"{prefix}-{seq:03d}"


async def list_scars(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    statuses: list[str] | None = None,
    supplier_id: uuid.UUID | None = None,
    source_type: str | None = None,
    factory_id: uuid.UUID | None = None,
    allowed_product_line_codes: list[str] | None = None,
) -> tuple[list[SupplierSCAR], int]:
    query = select(SupplierSCAR).options(selectinload(SupplierSCAR.supplier))
    count_query = select(func.count()).select_from(SupplierSCAR)

    if factory_id:
        query = query.where(SupplierSCAR.factory_id == factory_id)
        count_query = count_query.where(SupplierSCAR.factory_id == factory_id)
    if allowed_product_line_codes is not None:
        query = query.where(SupplierSCAR.product_line_code.in_(allowed_product_line_codes))
        count_query = count_query.where(SupplierSCAR.product_line_code.in_(allowed_product_line_codes))

    if statuses:
        query = query.where(SupplierSCAR.status.in_(statuses))
        count_query = count_query.where(SupplierSCAR.status.in_(statuses))
    if supplier_id:
        query = query.where(SupplierSCAR.supplier_id == supplier_id)
        count_query = count_query.where(SupplierSCAR.supplier_id == supplier_id)
    if source_type:
        query = query.where(SupplierSCAR.source_type == source_type)
        count_query = count_query.where(SupplierSCAR.source_type == source_type)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(SupplierSCAR.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())
    return items, total


async def get_scar(db: AsyncSession, scar_id: uuid.UUID) -> SupplierSCAR | None:
    result = await db.execute(
        select(SupplierSCAR)
        .options(selectinload(SupplierSCAR.supplier))
        .where(SupplierSCAR.scar_id == scar_id)
    )
    return result.scalar_one_or_none()


async def create_scar(
    db: AsyncSession,
    *,
    supplier_id: uuid.UUID,
    source_type: str,
    description: str,
    user_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
    product_line_code: str | None = None,
    requested_action: str | None = None,
    due_date: date | None = None,
    factory_id: uuid.UUID | None = None,
) -> SupplierSCAR:
    # Validate supplier exists
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise ValueError("供应商不存在")

    # Generate SCAR number with retry on collision
    for attempt in range(3):
        scar_no = await _next_scar_no(db)
        scar = SupplierSCAR(
            scar_no=scar_no,
            supplier_id=supplier_id,
            source_type=source_type,
            source_id=source_id,
            description=description,
            product_line_code=product_line_code,
            requested_action=requested_action,
            due_date=due_date,
            factory_id=factory_id,
            issued_by=user_id,
            issued_date=date.today(),
        )
        db.add(scar)
        try:
            await db.flush()
            break
        except IntegrityError as e:
            if "supplier_scars_scar_no" not in str(e.orig):
                raise
            await db.rollback()
            if attempt == 2:
                raise ValueError("SCAR 编号生成冲突，请重试")
            continue

    db.add(AuditLog(
        table_name="supplier_scars",
        record_id=scar.scar_id,
        action="CREATE",
        changed_fields={"scar_no": scar.scar_no, "supplier_id": str(supplier_id), "source_type": source_type, "description": description},
        operated_by=user_id,
    ))
    await enqueue_embedding(db, "scar", scar.scar_id, scar.product_line_code, scar.factory_id)
    await db.commit()
    await db.refresh(scar)
    # Re-load with supplier relationship
    return await get_scar(db, scar.scar_id)


async def _create_scar_without_commit(
    db: AsyncSession,
    *,
    supplier_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    description: str,
    requested_action: str | None = None,
    due_date: date | None = None,
    issued_by: uuid.UUID,
    product_line_code: str | None = None,
    factory_id: uuid.UUID | None = None,
) -> SupplierSCAR:
    """Create SCAR without committing — caller must commit."""
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise ValueError("供应商不存在")

    # Inherit factory_id from supplier if not provided
    scar_factory_id = factory_id or supplier.factory_id

    for attempt in range(3):
        scar_no = await _next_scar_no(db)
        scar = SupplierSCAR(
            scar_no=scar_no,
            supplier_id=supplier_id,
            factory_id=scar_factory_id,
            source_type=source_type,
            source_id=source_id,
            description=description,
            product_line_code=product_line_code,
            requested_action=requested_action,
            due_date=due_date,
            issued_by=issued_by,
            issued_date=date.today(),
        )
        try:
            async with db.begin_nested():
                db.add(scar)
                await db.flush()
            break
        except IntegrityError as e:
            if "supplier_scars_scar_no" not in str(e.orig):
                raise
            if attempt == 2:
                raise ValueError("SCAR 编号生成冲突，请重试")
            continue
    return scar


async def update_scar(
    db: AsyncSession,
    scar: SupplierSCAR,
    *,
    user_id: uuid.UUID,
    description: str | None = None,
    requested_action: str | None = None,
    due_date: date | None = None,
) -> SupplierSCAR:
    if description is not None:
        scar.description = description
    if requested_action is not None:
        scar.requested_action = requested_action
    if due_date is not None:
        scar.due_date = due_date

    db.add(AuditLog(
        table_name="supplier_scars",
        record_id=scar.scar_id,
        action="UPDATE",
        changed_fields={k: v for k, v in {"description": description, "requested_action": requested_action, "due_date": str(due_date) if due_date else None}.items() if v is not None},
        operated_by=user_id,
    ))
    await enqueue_embedding(db, "scar", scar.scar_id, scar.product_line_code, scar.factory_id)
    await db.commit()
    return await get_scar(db, scar.scar_id)


async def transition_scar(
    db: AsyncSession,
    scar: SupplierSCAR,
    action: str,
    user_id: uuid.UUID,
    supplier_response: str | None = None,
    resolution_summary: str | None = None,
) -> SupplierSCAR:
    if action not in SCAR_TRANSITIONS:
        raise ValueError(f"无效动作: {action}")

    expected_from, to_status = SCAR_TRANSITIONS[action]
    if scar.status != expected_from:
        raise ValueError(f"当前状态 {scar.status} 不允许执行 {action}（需要 {expected_from}）")

    # Check required fields
    required = SCAR_REQUIRED_FIELDS.get(action, [])
    if "supplier_response" in required and not supplier_response:
        raise ValueError("供应商回复为必填项")
    if "resolution_summary" in required and not resolution_summary:
        raise ValueError("解决摘要为必填项")

    old_status = scar.status
    scar.status = to_status

    if supplier_response:
        scar.supplier_response = supplier_response
    if resolution_summary:
        scar.resolution_summary = resolution_summary
    if to_status == "closed":
        scar.closed_date = date.today()

    db.add(AuditLog(
        table_name="supplier_scars",
        record_id=scar.scar_id,
        action="TRANSITION",
        old_values={"status": old_status},
        new_values={"status": to_status},
        operated_by=user_id,
    ))

    # Close linked risk alerts
    if to_status == "closed":
        from sqlalchemy import update
        from app.models.supplier_risk import SupplierRiskAlert
        await db.execute(
            update(SupplierRiskAlert)
            .where(SupplierRiskAlert.linked_scar_id == scar.scar_id)
            .where(SupplierRiskAlert.status != "closed")
            .values(status="closed", handled_at=func.now())
        )

    await db.commit()
    return await get_scar(db, scar.scar_id)


async def link_capa(
    db: AsyncSession,
    scar: SupplierSCAR,
    capa_ref_id: uuid.UUID,
    user_id: uuid.UUID,
) -> SupplierSCAR:
    capa = await db.get(CAPAEightD, capa_ref_id)
    if not capa:
        raise ValueError("CAPA 记录不存在")

    scar.capa_ref_id = capa_ref_id

    db.add(AuditLog(
        table_name="supplier_scars",
        record_id=scar.scar_id,
        action="LINK_CAPA",
        changed_fields={"capa_ref_id": str(capa_ref_id)},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_scar(db, scar.scar_id)
