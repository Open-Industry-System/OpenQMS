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
    premium_freight_count: int = 0,
    customer_disruption_count: int = 0,
) -> tuple[float, float, float, float, float, float, str]:
    base = quality_score * 0.35 + delivery_score * 0.30 + service_score * 0.15
    capa_penalty = min(capa_count * 2, 10)
    finding_penalty = min(finding_count * 3, 10)
    premium_freight_penalty = min(premium_freight_count * 5, 10)
    customer_disruption_penalty = min(customer_disruption_count * 5, 10)
    total_score = max(0.0, base - capa_penalty - finding_penalty - premium_freight_penalty - customer_disruption_penalty)

    if total_score >= 72:
        grade = "A"
    elif total_score >= 60:
        grade = "B"
    elif total_score >= 48:
        grade = "C"
    else:
        grade = "D"

    return base, capa_penalty, finding_penalty, premium_freight_penalty, customer_disruption_penalty, total_score, grade


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
    allowed_product_line_codes: list[str] | None = None,
    factory_id: uuid.UUID | None = None,
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

    if factory_id is not None:
        query = query.where(Supplier.factory_id == factory_id)
        count_query = count_query.where(Supplier.factory_id == factory_id)

    if allowed_product_line_codes is not None:
        query = query.where(Supplier.product_scope.in_(allowed_product_line_codes))
        count_query = count_query.where(Supplier.product_scope.in_(allowed_product_line_codes))

    query = query.order_by(Supplier.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return list(items), total


async def export_suppliers_excel(
    db: AsyncSession,
    status: str | None = None,
    grade: str | None = None,
    search: str | None = None,
    allowed_product_line_codes: list[str] | None = None,
    factory_id: uuid.UUID | None = None,
) -> bytes:
    from app.utils.excel import create_workbook, append_row, workbook_to_bytes, MAX_EXPORT_ROWS
    items, _ = await list_suppliers(
        db, page=1, page_size=MAX_EXPORT_ROWS, status=status, grade=grade, search=search,
        allowed_product_line_codes=allowed_product_line_codes, factory_id=factory_id,
    )
    headers = ["供应商编号", "名称", "简称", "联系人", "电话", "邮箱", "地址", "供货范围", "状态", "创建时间"]
    wb, ws = create_workbook("供应商", headers)
    for s in items:
        append_row(ws, [
            s.supplier_no, s.name, s.short_name,
            s.contact_name or "", s.contact_phone or "", s.contact_email or "",
            s.address or "", s.product_scope or "",
            s.status, s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "",
        ])
    return workbook_to_bytes(wb)


async def bulk_import_suppliers(
    db: AsyncSession,
    rows: list[dict],
    user_id: uuid.UUID,
) -> "ImportResult":  # noqa: F821
    from app.utils.excel import ImportError as ExcelImportError, ImportResult, MAX_IMPORT_ROWS

    if len(rows) > MAX_IMPORT_ROWS:
        return ImportResult(0, [ExcelImportError(0, "", f"导入行数超过上限 {MAX_IMPORT_ROWS}")])

    if not rows:
        return ImportResult(0, [ExcelImportError(0, "", "没有可导入的数据行")])

    # 预检查 DB 已存在
    existing_names: set[str] = set()
    existing_short: set[str] = set()
    for row in rows:
        name = row.get("name")
        short = row.get("short_name")
        if name:
            r = await db.execute(select(Supplier.supplier_id).where(Supplier.name == name))
            if r.scalar_one_or_none():
                existing_names.add(name)
        if short:
            r = await db.execute(select(Supplier.supplier_id).where(Supplier.short_name == short))
            if r.scalar_one_or_none():
                existing_short.add(short)

    # 逐行校验
    errors = []
    seen_names: set[str] = set()
    seen_short: set[str] = set()
    validated = []
    for row in rows:
        row_no = row["_row"]
        errs = []
        if not row.get("name"):
            errs.append(ExcelImportError(row_no, "name", "名称为必填项"))
        if not row.get("short_name"):
            errs.append(ExcelImportError(row_no, "short_name", "简称为必填项"))
        name = row.get("name")
        short = row.get("short_name")
        if name and name in seen_names:
            errs.append(ExcelImportError(row_no, "name", f"批次内重复: {name}"))
        if short and short in seen_short:
            errs.append(ExcelImportError(row_no, "short_name", f"批次内重复: {short}"))
        if name and name in existing_names:
            errs.append(ExcelImportError(row_no, "name", f"数据库已存在: {name}"))
        if short and short in existing_short:
            errs.append(ExcelImportError(row_no, "short_name", f"数据库已存在: {short}"))
        if errs:
            errors.extend(errs)
        else:
            seen_names.add(name)
            seen_short.add(short)
            validated.append((row_no, row))

    if errors:
        return ImportResult(0, errors)

    # 批量创建
    created = []
    try:
        from datetime import datetime as dt
        for row_no, row in validated:
            supplier_no = await _generate_supplier_no(db, dt.now().year)
            supplier = Supplier(
                supplier_no=supplier_no, name=row["name"], short_name=row["short_name"],
                contact_name=row.get("contact_name"), contact_phone=row.get("contact_phone"),
                contact_email=row.get("contact_email"), address=row.get("address"),
                product_scope=row.get("product_scope"), status="pending_review", created_by=user_id,
            )
            db.add(supplier)
            await db.flush()
            db.add(AuditLog(
                table_name="suppliers", record_id=supplier.supplier_id,
                action="CREATE", changed_fields={"supplier_no": supplier_no, "name": row["name"]},
                operated_by=user_id,
            ))
            created.append(supplier)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return ImportResult(0, [ExcelImportError(0, "", "数据库写入冲突，请重试")])
    return ImportResult(len(created), [])


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
    await db.flush()

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
    await db.flush()

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
    premium_freight_count: int,
    customer_disruption_count: int,
    notes: str | None,
    user_id: uuid.UUID,
) -> SupplierEvaluation:
    base_score, capa_penalty, finding_penalty, premium_freight_penalty, customer_disruption_penalty, total_score, grade = _calculate_evaluation(
        quality_score, delivery_score, service_score, capa_count, finding_count,
        premium_freight_count, customer_disruption_count
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
        premium_freight_count=premium_freight_count,
        customer_disruption_count=customer_disruption_count,
        capa_penalty=capa_penalty,
        finding_penalty=finding_penalty,
        premium_freight_penalty=premium_freight_penalty,
        customer_disruption_penalty=customer_disruption_penalty,
        total_score=total_score,
        grade=grade,
        notes=notes,
        evaluated_by=user_id,
    )
    db.add(evaluation)
    await db.flush()

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
            "premium_freight_count": premium_freight_count,
            "customer_disruption_count": customer_disruption_count,
            "capa_penalty": capa_penalty,
            "finding_penalty": finding_penalty,
            "premium_freight_penalty": premium_freight_penalty,
            "customer_disruption_penalty": customer_disruption_penalty,
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

async def get_supplier_stats(db: AsyncSession, factory_id: uuid.UUID | None = None, allowed_product_line_codes: list[str] | None = None) -> dict:
    from sqlalchemy import case

    base_query = select(
        func.count().label("total_count"),
        func.count(case((Supplier.status == "pending_review", 1))).label("pending_review_count"),
        func.count(case((Supplier.status == "approved", 1))).label("approved_count"),
    ).select_from(Supplier)
    if factory_id is not None:
        base_query = base_query.where(Supplier.factory_id == factory_id)
    result = await db.execute(base_query)
    row = result.one()

    today = date.today()
    cert_query = select(func.count()).select_from(SupplierCertification).where(
        SupplierCertification.expiry_date >= today,
        SupplierCertification.expiry_date <= today + timedelta(days=30),
    )
    if factory_id is not None:
        cert_query = cert_query.where(SupplierCertification.factory_id == factory_id)
    expiry_result = await db.execute(cert_query)
    cert_expiry_30d_count = expiry_result.scalar() or 0

    return {
        "total_count": row.total_count,
        "pending_review_count": row.pending_review_count,
        "approved_count": row.approved_count,
        "cert_expiry_30d_count": cert_expiry_30d_count,
    }


# ─── Expiry alerts ───

async def get_expiry_alerts(db: AsyncSession, days: int = 90, factory_id: uuid.UUID | None = None, allowed_product_line_codes: list[str] | None = None) -> list[dict]:
    today = date.today()
    cutoff = today + timedelta(days=days)

    query = (
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
    if factory_id is not None:
        query = query.where(SupplierCertification.factory_id == factory_id)
    result = await db.execute(query)

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


async def get_supplier_related(
    db: AsyncSession, supplier_id: str
) -> dict:
    from app.models.customer_quality import CustomerComplaint
    from app.models.iqc_inspection import IqcInspection
    from app.models.supplier import SupplierSCAR

    complaints_q = select(CustomerComplaint).where(
        CustomerComplaint.supplier_id == supplier_id
    )
    complaints = (await db.execute(complaints_q)).scalars().all()

    iqc_q = select(IqcInspection).where(
        IqcInspection.supplier_id == supplier_id,
        IqcInspection.inspection_result == "reject",
    )
    iqc_rejects = (await db.execute(iqc_q)).scalars().all()

    scar_q = select(SupplierSCAR).where(
        SupplierSCAR.supplier_id == supplier_id
    )
    scars = (await db.execute(scar_q)).scalars().all()

    return {
        "complaints": [
            {"id": str(c.complaint_id), "no": c.complaint_no, "status": c.status}
            for c in complaints
        ],
        "iqc_rejects": [
            {"id": str(i.inspection_id), "no": i.inspection_no, "result": i.inspection_result}
            for i in iqc_rejects
        ],
        "scars": [
            {"id": str(s.scar_id), "no": s.scar_no, "status": s.status}
            for s in scars
        ],
    }
