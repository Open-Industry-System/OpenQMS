import uuid
from datetime import date, datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.supplier import Supplier, SupplierCertification, SupplierEvaluation
from app.models.audit import AuditLog
from app.models.audit_plan import AuditPlan


# ─── Numbering generator ───

async def _generate_supplier_no(db: AsyncSession, year: int) -> str:
    prefix = f"SUP-{year}"
    result = await db.execute(
        select(func.count()).where(Supplier.supplier_no.like(f"{prefix}-%"))
    )
    count = result.scalar() or 0
    return f"{prefix}-{count + 1:03d}"


# ─── Scoring formula ───

def _calculate_evaluation(
    quality_score: float,
    delivery_score: float,
    service_score: float,
    capa_count: int,
    finding_count: int,
) -> tuple[float, float, float, float, str]:
    base = quality_score * 0.35 + delivery_score * 0.30 + service_score * 0.15
    capa_penalty = min(capa_count * 2, 10)
    finding_penalty = min(finding_count * 3, 10)
    total_score = max(0.0, base - capa_penalty - finding_penalty)

    if total_score >= 72:
        grade = "A"
    elif total_score >= 60:
        grade = "B"
    elif total_score >= 48:
        grade = "C"
    else:
        grade = "D"

    return base, capa_penalty, finding_penalty, total_score, grade


# ─── State machine ───

VALID_TRANSITIONS = {
    "pending_review": {"approve": "audit_required", "reject": "rejected"},
    "audit_required": {"confirm_approved": "approved", "reject": "rejected"},
    "approved": {"suspend": "suspended"},
    "suspended": {"reinstate": "approved"},
    "rejected": {},
}


def _transition_status(current: str, action: str) -> str:
    transitions = VALID_TRANSITIONS.get(current, {})
    if action not in transitions:
        raise ValueError(
            f"invalid action '{action}' for supplier in status '{current}'"
        )
    return transitions[action]


# ─── Supplier CRUD ───

async def list_suppliers(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    grade: str | None = None,
    search: str | None = None,
) -> tuple[list[Supplier], int]:
    query = select(Supplier)
    count_query = select(func.count()).select_from(Supplier)

    if status:
        query = query.where(Supplier.status == status)
        count_query = count_query.where(Supplier.status == status)
    if search:
        pattern = f"%{search}%"
        search_filter = Supplier.name.like(pattern) | Supplier.short_name.like(pattern) | Supplier.supplier_no.like(pattern)
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
    if grade:
        # Filter by latest evaluation grade — join subquery for latest eval per supplier
        subq = (
            select(SupplierEvaluation.supplier_id, SupplierEvaluation.grade)
            .distinct(SupplierEvaluation.supplier_id)
            .order_by(SupplierEvaluation.supplier_id, SupplierEvaluation.created_at.desc())
            .subquery()
        )
        query = query.join(subq, Supplier.supplier_id == subq.c.supplier_id).where(
            subq.c.grade == grade
        )
        count_query = count_query.join(subq, Supplier.supplier_id == subq.c.supplier_id).where(
            subq.c.grade == grade
        )

    query = query.order_by(Supplier.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return list(items), total


async def get_supplier(db: AsyncSession, supplier_id: uuid.UUID) -> Supplier | None:
    return await db.get(Supplier, supplier_id)


async def create_supplier(
    db: AsyncSession,
    name: str,
    short_name: str,
    contact_name: str | None,
    contact_phone: str | None,
    contact_email: str | None,
    address: str | None,
    product_scope: str | None,
    user_id: uuid.UUID,
) -> Supplier:
    year = datetime.now().year
    supplier_no = await _generate_supplier_no(db, year)

    supplier = Supplier(
        supplier_no=supplier_no,
        name=name,
        short_name=short_name,
        contact_name=contact_name,
        contact_phone=contact_phone,
        contact_email=contact_email,
        address=address,
        product_scope=product_scope,
        status="pending_review",
        created_by=user_id,
    )
    db.add(supplier)

    audit_log = AuditLog(
        table_name="suppliers",
        record_id=supplier.supplier_id,
        action="CREATE",
        changed_fields={
            "supplier_no": supplier_no,
            "name": name,
            "short_name": short_name,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "contact_email": contact_email,
            "address": address,
            "product_scope": product_scope,
            "status": "pending_review",
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create supplier: {e}")
    await db.refresh(supplier)
    return supplier


async def update_supplier(
    db: AsyncSession,
    supplier: Supplier,
    name: str | None,
    short_name: str | None,
    contact_name: str | None,
    contact_phone: str | None,
    contact_email: str | None,
    address: str | None,
    product_scope: str | None,
    audit_plan_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> Supplier:
    changed = {}

    if name is not None and name != supplier.name:
        changed["name"] = {"before": supplier.name, "after": name}
        supplier.name = name
    if short_name is not None and short_name != supplier.short_name:
        changed["short_name"] = {"before": supplier.short_name, "after": short_name}
        supplier.short_name = short_name
    if contact_name is not None and contact_name != supplier.contact_name:
        changed["contact_name"] = {"before": supplier.contact_name, "after": contact_name}
        supplier.contact_name = contact_name
    if contact_phone is not None and contact_phone != supplier.contact_phone:
        changed["contact_phone"] = {"before": supplier.contact_phone, "after": contact_phone}
        supplier.contact_phone = contact_phone
    if contact_email is not None and contact_email != supplier.contact_email:
        changed["contact_email"] = {"before": supplier.contact_email, "after": contact_email}
        supplier.contact_email = contact_email
    if address is not None and address != supplier.address:
        changed["address"] = {"before": supplier.address, "after": address}
        supplier.address = address
    if product_scope is not None and product_scope != supplier.product_scope:
        changed["product_scope"] = {"before": supplier.product_scope, "after": product_scope}
        supplier.product_scope = product_scope
    if audit_plan_id is not None and audit_plan_id != supplier.audit_plan_id:
        changed["audit_plan_id"] = {
            "before": str(supplier.audit_plan_id) if supplier.audit_plan_id else None,
            "after": str(audit_plan_id),
        }
        supplier.audit_plan_id = audit_plan_id

    if not changed:
        return supplier

    audit_log = AuditLog(
        table_name="suppliers",
        record_id=supplier.supplier_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to update supplier: {e}")
    await db.refresh(supplier)
    return supplier


async def delete_supplier(
    db: AsyncSession,
    supplier: Supplier,
    user_id: uuid.UUID,
) -> None:
    audit_log = AuditLog(
        table_name="suppliers",
        record_id=supplier.supplier_id,
        action="DELETE",
        changed_fields={"supplier_no": supplier.supplier_no, "name": supplier.name},
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.delete(supplier)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to delete supplier: {e}")


# ─── State transitions ───

async def transition_supplier(
    db: AsyncSession,
    supplier: Supplier,
    action: str,
    user_id: uuid.UUID,
    reason: str | None = None,
) -> Supplier:
    new_status = _transition_status(supplier.status, action)
    old_status = supplier.status

    supplier.status = new_status

    if action in ("reject", "suspend"):
        supplier.reject_reason = reason or ""
    else:
        supplier.reject_reason = None

    audit_log = AuditLog(
        table_name="suppliers",
        record_id=supplier.supplier_id,
        action="TRANSITION",
        changed_fields={
            "action": action,
            "status": {"before": old_status, "after": new_status},
            "reason": reason,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to transition supplier: {e}")
    await db.refresh(supplier)
    return supplier


# ─── Certification CRUD ───

async def list_certifications(
    db: AsyncSession,
    supplier_id: uuid.UUID,
) -> list[SupplierCertification]:
    result = await db.execute(
        select(SupplierCertification)
        .where(SupplierCertification.supplier_id == supplier_id)
        .order_by(SupplierCertification.created_at.desc())
    )
    return list(result.scalars().all())


async def get_certification(
    db: AsyncSession,
    cert_id: uuid.UUID,
) -> SupplierCertification | None:
    return await db.get(SupplierCertification, cert_id)


async def create_certification(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    cert_type: str,
    cert_no: str,
    issued_by: str | None,
    issue_date: date | None,
    expiry_date: date | None,
    user_id: uuid.UUID,
) -> SupplierCertification:
    cert = SupplierCertification(
        supplier_id=supplier_id,
        cert_type=cert_type,
        cert_no=cert_no,
        issued_by=issued_by,
        issue_date=issue_date,
        expiry_date=expiry_date,
    )
    db.add(cert)

    audit_log = AuditLog(
        table_name="supplier_certifications",
        record_id=cert.cert_id,
        action="CREATE",
        changed_fields={
            "supplier_id": str(supplier_id),
            "cert_type": cert_type,
            "cert_no": cert_no,
            "issued_by": issued_by,
            "issue_date": issue_date.isoformat() if issue_date else None,
            "expiry_date": expiry_date.isoformat() if expiry_date else None,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create certification: {e}")
    await db.refresh(cert)
    return cert


async def update_certification(
    db: AsyncSession,
    cert: SupplierCertification,
    cert_type: str | None,
    cert_no: str | None,
    issued_by: str | None,
    issue_date: date | None,
    expiry_date: date | None,
    user_id: uuid.UUID,
) -> SupplierCertification:
    changed = {}

    if cert_type is not None and cert_type != cert.cert_type:
        changed["cert_type"] = {"before": cert.cert_type, "after": cert_type}
        cert.cert_type = cert_type
    if cert_no is not None and cert_no != cert.cert_no:
        changed["cert_no"] = {"before": cert.cert_no, "after": cert_no}
        cert.cert_no = cert_no
    if issued_by is not None and issued_by != cert.issued_by:
        changed["issued_by"] = {"before": cert.issued_by, "after": issued_by}
        cert.issued_by = issued_by
    if issue_date is not None and issue_date != cert.issue_date:
        changed["issue_date"] = {
            "before": cert.issue_date.isoformat() if cert.issue_date else None,
            "after": issue_date.isoformat(),
        }
        cert.issue_date = issue_date
    if expiry_date is not None and expiry_date != cert.expiry_date:
        changed["expiry_date"] = {
            "before": cert.expiry_date.isoformat() if cert.expiry_date else None,
            "after": expiry_date.isoformat(),
        }
        cert.expiry_date = expiry_date

    if not changed:
        return cert

    audit_log = AuditLog(
        table_name="supplier_certifications",
        record_id=cert.cert_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to update certification: {e}")
    await db.refresh(cert)
    return cert


async def delete_certification(
    db: AsyncSession,
    cert: SupplierCertification,
    user_id: uuid.UUID,
) -> None:
    audit_log = AuditLog(
        table_name="supplier_certifications",
        record_id=cert.cert_id,
        action="DELETE",
        changed_fields={"cert_type": cert.cert_type, "cert_no": cert.cert_no},
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.delete(cert)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to delete certification: {e}")


# ─── Evaluation CRUD ───

async def list_evaluations(
    db: AsyncSession,
    supplier_id: uuid.UUID,
) -> list[SupplierEvaluation]:
    result = await db.execute(
        select(SupplierEvaluation)
        .where(SupplierEvaluation.supplier_id == supplier_id)
        .order_by(SupplierEvaluation.created_at.desc())
    )
    return list(result.scalars().all())


async def get_evaluation(
    db: AsyncSession,
    eval_id: uuid.UUID,
) -> SupplierEvaluation | None:
    return await db.get(SupplierEvaluation, eval_id)


async def create_evaluation(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    eval_period: str,
    eval_type: str,
    quality_score: float,
    delivery_score: float,
    service_score: float,
    capa_count: int,
    finding_count: int,
    notes: str | None,
    user_id: uuid.UUID,
) -> SupplierEvaluation:
    base_score, capa_penalty, finding_penalty, total_score, grade = _calculate_evaluation(
        quality_score, delivery_score, service_score, capa_count, finding_count
    )

    evaluation = SupplierEvaluation(
        supplier_id=supplier_id,
        eval_period=eval_period,
        eval_type=eval_type,
        quality_score=quality_score,
        delivery_score=delivery_score,
        service_score=service_score,
        capa_count=capa_count,
        finding_count=finding_count,
        capa_penalty=capa_penalty,
        finding_penalty=finding_penalty,
        total_score=total_score,
        grade=grade,
        notes=notes,
        evaluated_by=user_id,
    )
    db.add(evaluation)

    audit_log = AuditLog(
        table_name="supplier_evaluations",
        record_id=evaluation.eval_id,
        action="CREATE",
        changed_fields={
            "supplier_id": str(supplier_id),
            "eval_period": eval_period,
            "eval_type": eval_type,
            "quality_score": quality_score,
            "delivery_score": delivery_score,
            "service_score": service_score,
            "capa_count": capa_count,
            "finding_count": finding_count,
            "capa_penalty": capa_penalty,
            "finding_penalty": finding_penalty,
            "total_score": total_score,
            "grade": grade,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create evaluation: {e}")
    await db.refresh(evaluation)
    return evaluation


# ─── Stats ───

async def get_supplier_stats(db: AsyncSession) -> dict:
    from sqlalchemy import case

    result = await db.execute(
        select(
            func.count().label("total_count"),
            func.count(case((Supplier.status == "pending_review", 1))).label("pending_review_count"),
            func.count(case((Supplier.status == "approved", 1))).label("approved_count"),
        ).select_from(Supplier)
    )
    row = result.one()

    today = date.today()
    expiry_result = await db.execute(
        select(func.count()).select_from(SupplierCertification).where(
            SupplierCertification.expiry_date >= today,
            SupplierCertification.expiry_date <= today + timedelta(days=30),
        )
    )
    cert_expiry_30d_count = expiry_result.scalar() or 0

    return {
        "total_count": row.total_count,
        "pending_review_count": row.pending_review_count,
        "approved_count": row.approved_count,
        "cert_expiry_30d_count": cert_expiry_30d_count,
    }


# ─── Expiry alerts ───

async def get_expiry_alerts(db: AsyncSession, days: int = 90) -> list[dict]:
    today = date.today()
    cutoff = today + timedelta(days=days)

    result = await db.execute(
        select(
            SupplierCertification.cert_id,
            SupplierCertification.supplier_id,
            Supplier.name.label("supplier_name"),
            Supplier.short_name.label("supplier_short_name"),
            SupplierCertification.cert_type,
            SupplierCertification.cert_no,
            SupplierCertification.expiry_date,
        )
        .join(Supplier, SupplierCertification.supplier_id == Supplier.supplier_id)
        .where(
            SupplierCertification.expiry_date >= today,
            SupplierCertification.expiry_date <= cutoff,
        )
        .order_by(SupplierCertification.expiry_date.asc())
    )

    rows = result.all()
    alerts = []
    for row in rows:
        days_remaining = (row.expiry_date - today).days
        alerts.append({
            "cert_id": row.cert_id,
            "supplier_id": row.supplier_id,
            "supplier_name": row.supplier_name,
            "supplier_short_name": row.supplier_short_name,
            "cert_type": row.cert_type,
            "cert_no": row.cert_no,
            "expiry_date": row.expiry_date,
            "days_remaining": days_remaining,
        })

    return alerts
