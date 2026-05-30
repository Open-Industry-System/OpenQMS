import uuid
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.customer_quality import Customer, CustomerComplaint, RMARecord
from app.models.fmea import FMEADocument
from app.services import scar_service
from app.services.product_line_service import validate_product_line


class ComplaintStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESPONDED = "responded"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class RMAStatus(StrEnum):
    OPEN = "open"
    ANALYSIS = "analysis"
    ACTION_PENDING = "action_pending"
    CLOSED = "closed"
    CANCELLED = "cancelled"


COMPLAINT_TRANSITIONS = {
    (ComplaintStatus.OPEN, "start_investigation"): ComplaintStatus.INVESTIGATING,
    (ComplaintStatus.INVESTIGATING, "mark_responded"): ComplaintStatus.RESPONDED,
    (ComplaintStatus.RESPONDED, "close"): ComplaintStatus.CLOSED,
    (ComplaintStatus.OPEN, "cancel"): ComplaintStatus.CANCELLED,
    (ComplaintStatus.INVESTIGATING, "cancel"): ComplaintStatus.CANCELLED,
    (ComplaintStatus.RESPONDED, "start_investigation"): ComplaintStatus.INVESTIGATING,
}

RMA_TRANSITIONS = {
    (RMAStatus.OPEN, "start_analysis"): RMAStatus.ANALYSIS,
    (RMAStatus.ANALYSIS, "mark_action_pending"): RMAStatus.ACTION_PENDING,
    (RMAStatus.ACTION_PENDING, "close"): RMAStatus.CLOSED,
    (RMAStatus.OPEN, "cancel"): RMAStatus.CANCELLED,
    (RMAStatus.ANALYSIS, "cancel"): RMAStatus.CANCELLED,
}

VALID_CATEGORIES = {"safety", "function", "appearance", "delivery"}
VALID_SEVERITIES = {"致命", "严重", "一般", "轻微"}
VALID_RESPONSIBILITIES = {"supplier", "internal", "transport", "customer_misuse", "unknown"}


def transition_complaint_status(status: str, action: str) -> str:
    try:
        next_status = COMPLAINT_TRANSITIONS[(ComplaintStatus(status), action)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid complaint transition: {status} + {action}") from exc
    return next_status.value


def transition_rma_status(status: str, action: str) -> str:
    try:
        next_status = RMA_TRANSITIONS[(RMAStatus(status), action)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid RMA transition: {status} + {action}") from exc
    return next_status.value


def complaint_is_overdue(status: str, due_date: date | None, today: date | None = None) -> bool:
    if due_date is None or status in {ComplaintStatus.CLOSED.value, ComplaintStatus.CANCELLED.value}:
        return False
    return due_date < (today or date.today())


def calculate_customer_ppm(
    *,
    impact_qty: int,
    independent_rma_qty: int,
    shipment_qty: int | None,
    annual_shipment_qty: int | None,
    date_from: date | None,
    date_to: date | None,
) -> float | None:
    if shipment_qty is not None:
        denominator = shipment_qty
    elif annual_shipment_qty is not None:
        window_end = date_to or date.today()
        window_start = date_from or (window_end - timedelta(days=89))
        window_days = (window_end - window_start).days + 1
        if window_days <= 0:
            return None
        denominator = annual_shipment_qty * window_days / 365
    else:
        return None

    if denominator <= 0:
        return None

    return round(((impact_qty + independent_rma_qty) / denominator) * 1_000_000, 2)


def _normalize_window(
    date_from: date | None,
    date_to: date | None,
    *,
    today: date | None = None,
) -> tuple[date, date]:
    window_end = date_to or today or date.today()
    window_start = date_from or (window_end - timedelta(days=89))
    if window_start > window_end:
        raise ValueError("date_from cannot be after date_to")
    return window_start, window_end


def calculate_risk_light(
    *,
    open_fatal_count: int,
    overdue_count: int,
    open_count: int,
    ppm: float | None,
    ppm_target: float | None,
) -> str:
    if open_fatal_count > 0 or overdue_count > 0:
        return "red"
    if ppm is not None and ppm_target is not None and ppm_target > 0:
        if ppm > ppm_target * 2:
            return "red"
        if ppm > ppm_target:
            return "yellow"
    if open_count > 0:
        return "yellow"
    return "green"


def _as_dict(data, *, exclude_unset: bool = False) -> dict:
    if isinstance(data, dict):
        return dict(data)
    if hasattr(data, "model_dump"):
        return data.model_dump(exclude_unset=exclude_unset)
    return dict(data)


def _jsonable(value):
    if isinstance(value, (uuid.UUID, date, datetime)):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


async def _audit(
    db: AsyncSession,
    table_name: str,
    record_id: uuid.UUID,
    action: str,
    user_id: uuid.UUID,
    changed_fields: dict,
) -> None:
    db.add(
        AuditLog(
            table_name=table_name,
            record_id=record_id,
            action=action,
            changed_fields=_jsonable(changed_fields),
            operated_by=user_id,
        )
    )


def _apply_updates(instance, update_data: dict, allowed_fields: set[str]) -> dict:
    changed_fields = {}
    for key, value in update_data.items():
        if key not in allowed_fields or not hasattr(instance, key):
            continue
        old_value = getattr(instance, key)
        if old_value != value:
            changed_fields[key] = {
                "before": _jsonable(old_value),
                "after": _jsonable(value),
            }
            setattr(instance, key, value)
    return changed_fields


async def _ensure_customer(db: AsyncSession, customer_id: uuid.UUID) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise ValueError("customer not found")
    return customer


async def _ensure_complaint(db: AsyncSession, complaint_id: uuid.UUID) -> CustomerComplaint:
    complaint = await db.get(CustomerComplaint, complaint_id)
    if complaint is None:
        raise ValueError("complaint not found")
    return complaint


async def _ensure_capa(db: AsyncSession, capa_ref_id: uuid.UUID) -> CAPAEightD:
    capa = await db.get(CAPAEightD, capa_ref_id)
    if capa is None:
        raise ValueError("CAPA not found")
    return capa


async def _ensure_fmea(db: AsyncSession, fmea_ref_id: uuid.UUID) -> FMEADocument:
    fmea = await db.get(FMEADocument, fmea_ref_id)
    if fmea is None:
        raise ValueError("FMEA not found")
    return fmea


def _validate_choice(value: str | None, valid_values: set[str], field_name: str) -> None:
    if value is not None and value not in valid_values:
        raise ValueError(f"invalid {field_name}")


def _valid_direct_complaint_status_change(current: str, target: str) -> bool:
    return current == target or any(
        old_status.value == current and new_status.value == target
        for (old_status, _action), new_status in COMPLAINT_TRANSITIONS.items()
    )


def _valid_direct_rma_status_change(current: str, target: str) -> bool:
    return current == target or any(
        old_status.value == current and new_status.value == target
        for (old_status, _action), new_status in RMA_TRANSITIONS.items()
    )


def _validate_direct_status_update(
    current: str,
    target: str,
    valid_statuses: set[str],
    terminal_statuses: set[str],
    entity_name: str,
) -> None:
    _validate_choice(target, valid_statuses, "status")
    if target != current and target in terminal_statuses:
        raise ValueError(f"{entity_name} terminal status changes must use transition endpoint")


def _validate_initial_status(
    status: str,
    valid_statuses: set[str],
    terminal_statuses: set[str],
    entity_name: str,
) -> None:
    _validate_choice(status, valid_statuses, "status")
    if status in terminal_statuses:
        raise ValueError(f"{entity_name} initial status cannot be terminal")


def _validate_rma_complaint_link(
    rma_customer_id: uuid.UUID,
    rma_product_line_code: str,
    complaint: CustomerComplaint,
) -> None:
    if str(complaint.customer_id) != str(rma_customer_id):
        raise ValueError("RMA and complaint must belong to the same customer")
    if complaint.product_line_code != rma_product_line_code:
        raise ValueError("RMA and complaint must belong to the same product line")


def _effective_rma_link_tuple(rma: RMARecord, update_data: dict) -> tuple | None:
    complaint_id = update_data.get("complaint_id", rma.complaint_id)
    if complaint_id is None:
        return None
    customer_id = update_data.get("customer_id") or rma.customer_id
    product_line_code = update_data.get("product_line_code") or rma.product_line_code
    return complaint_id, customer_id, product_line_code


def _complaint_link_identity_changed(complaint: CustomerComplaint, update_data: dict) -> bool:
    customer_changed = (
        "customer_id" in update_data
        and update_data["customer_id"] is not None
        and update_data["customer_id"] != complaint.customer_id
    )
    product_line_changed = (
        "product_line_code" in update_data
        and update_data["product_line_code"] is not None
        and update_data["product_line_code"] != complaint.product_line_code
    )
    return customer_changed or product_line_changed


async def _complaint_has_rmas(db: AsyncSession, complaint_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(func.count()).select_from(RMARecord).where(RMARecord.complaint_id == complaint_id)
    )
    return (result.scalar() or 0) > 0


async def _complaint_has_other_rmas(
    db: AsyncSession,
    complaint_id: uuid.UUID,
    exclude_rma_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(func.count())
        .select_from(RMARecord)
        .where(RMARecord.complaint_id == complaint_id, RMARecord.rma_id != exclude_rma_id)
    )
    return (result.scalar() or 0) > 0


async def list_customers(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    segment: str | None = None,
) -> tuple[list[Customer], int]:
    conditions = []
    if q:
        pattern = f"%{q}%"
        conditions.append(or_(Customer.customer_code.ilike(pattern), Customer.name.ilike(pattern)))
    if segment:
        conditions.append(Customer.segment == segment)

    query = select(Customer)
    count_query = select(func.count()).select_from(Customer)
    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)

    query = query.order_by(Customer.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    total = (await db.execute(count_query)).scalar() or 0
    return list(result.scalars().all()), total


async def get_customer(db: AsyncSession, customer_id: uuid.UUID) -> Customer | None:
    return await db.get(Customer, customer_id)


async def create_customer(db: AsyncSession, data, user_id: uuid.UUID) -> Customer:
    values = _as_dict(data)
    customer_code = values.get("customer_code")
    existing = await db.execute(select(Customer).where(Customer.customer_code == customer_code))
    if existing.scalar_one_or_none():
        raise ValueError(f"customer code '{customer_code}' already exists")

    allowed = {
        "customer_code",
        "name",
        "segment",
        "contact_name",
        "contact_email",
        "contact_phone",
        "csr_list",
        "ppm_target",
        "annual_shipment_qty",
        "notes",
    }
    customer = Customer(
        customer_id=uuid.uuid4(),
        **{key: value for key, value in values.items() if key in allowed},
    )
    customer.created_by = user_id
    db.add(customer)
    await _audit(
        db,
        "customers",
        customer.customer_id,
        "CREATE",
        user_id,
        {key: _jsonable(getattr(customer, key)) for key in allowed if hasattr(customer, key)},
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"customer code '{customer_code}' already exists")
    await db.refresh(customer)
    return customer


async def update_customer(
    db: AsyncSession,
    customer: Customer,
    update_data,
    user_id: uuid.UUID,
) -> Customer:
    values = _as_dict(update_data, exclude_unset=True)
    if "customer_code" in values and values["customer_code"] != customer.customer_code:
        existing = await db.execute(
            select(Customer).where(Customer.customer_code == values["customer_code"])
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"customer code '{values['customer_code']}' already exists")

    allowed = {
        "customer_code",
        "name",
        "segment",
        "contact_name",
        "contact_email",
        "contact_phone",
        "csr_list",
        "ppm_target",
        "annual_shipment_qty",
        "notes",
    }
    changed_fields = _apply_updates(customer, values, allowed)
    if not changed_fields:
        return customer

    await _audit(db, "customers", customer.customer_id, "UPDATE", user_id, changed_fields)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("customer update violates a database constraint")
    await db.refresh(customer)
    return customer


async def customer_summary(
    db: AsyncSession,
    customer_id: uuid.UUID,
    product_line: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    shipment_qty: int | None = None,
) -> dict:
    customer = await _ensure_customer(db, customer_id)
    window_start, window_end = _normalize_window(date_from, date_to)

    complaint_conditions = [
        CustomerComplaint.customer_id == customer_id,
        CustomerComplaint.received_date >= window_start,
        CustomerComplaint.received_date <= window_end,
    ]
    rma_conditions = [
        RMARecord.customer_id == customer_id,
        RMARecord.received_date >= window_start,
        RMARecord.received_date <= window_end,
    ]
    if product_line:
        complaint_conditions.append(CustomerComplaint.product_line_code == product_line)
        rma_conditions.append(RMARecord.product_line_code == product_line)

    complaints_result = await db.execute(select(CustomerComplaint).where(*complaint_conditions))
    rma_result = await db.execute(select(RMARecord).where(*rma_conditions))
    complaints = list(complaints_result.scalars().all())
    rma_records = list(rma_result.scalars().all())

    open_statuses = {
        ComplaintStatus.OPEN.value,
        ComplaintStatus.INVESTIGATING.value,
        ComplaintStatus.RESPONDED.value,
    }
    open_complaints = [complaint for complaint in complaints if complaint.status in open_statuses]
    overdue_count = sum(
        1 for complaint in complaints if complaint_is_overdue(complaint.status, complaint.due_date)
    )
    open_fatal_count = sum(
        1 for complaint in open_complaints if complaint.severity == "致命"
    )
    impact_qty = sum(complaint.impact_qty or 0 for complaint in complaints)
    independent_rma_qty = sum(
        rma.return_qty or 0 for rma in rma_records if rma.complaint_id is None
    )
    ppm = calculate_customer_ppm(
        impact_qty=impact_qty,
        independent_rma_qty=independent_rma_qty,
        shipment_qty=shipment_qty,
        annual_shipment_qty=customer.annual_shipment_qty,
        date_from=window_start,
        date_to=window_end,
    )

    return {
        "customer_id": customer.customer_id,
        "customer_code": customer.customer_code,
        "name": customer.name,
        "segment": customer.segment,
        "complaint_count": len(complaints),
        "open_complaint_count": len(open_complaints),
        "overdue_count": overdue_count,
        "open_fatal_count": open_fatal_count,
        "rma_count": len(rma_records),
        "independent_rma_qty": independent_rma_qty,
        "impact_qty": impact_qty,
        "ppm": ppm,
        "ppm_target": customer.ppm_target,
        "risk_light": calculate_risk_light(
            open_fatal_count=open_fatal_count,
            overdue_count=overdue_count,
            open_count=len(open_complaints),
            ppm=ppm,
            ppm_target=customer.ppm_target,
        ),
    }


async def list_complaints(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    product_line: str | None = None,
    customer_id: uuid.UUID | None = None,
    status: str | None = None,
    severity: str | None = None,
    overdue: bool | None = None,
    assignee_id: uuid.UUID | None = None,
) -> tuple[list[CustomerComplaint], int]:
    conditions = []
    if product_line:
        conditions.append(CustomerComplaint.product_line_code == product_line)
    if customer_id:
        conditions.append(CustomerComplaint.customer_id == customer_id)
    if status:
        conditions.append(CustomerComplaint.status == status)
    if severity:
        conditions.append(CustomerComplaint.severity == severity)
    if assignee_id:
        conditions.append(CustomerComplaint.assignee_id == assignee_id)
    if overdue is True:
        conditions.append(CustomerComplaint.due_date < date.today())
        conditions.append(
            CustomerComplaint.status.notin_(
                [ComplaintStatus.CLOSED.value, ComplaintStatus.CANCELLED.value]
            )
        )
    elif overdue is False:
        conditions.append(
            or_(
                CustomerComplaint.due_date.is_(None),
                CustomerComplaint.due_date >= date.today(),
                CustomerComplaint.status.in_(
                    [ComplaintStatus.CLOSED.value, ComplaintStatus.CANCELLED.value]
                ),
            )
        )

    query = select(CustomerComplaint)
    count_query = select(func.count()).select_from(CustomerComplaint)
    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)
    query = query.order_by(CustomerComplaint.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    total = (await db.execute(count_query)).scalar() or 0
    return list(result.scalars().all()), total


async def get_complaint(
    db: AsyncSession,
    complaint_id: uuid.UUID,
) -> CustomerComplaint | None:
    return await db.get(CustomerComplaint, complaint_id)


async def create_complaint(db: AsyncSession, data, user_id: uuid.UUID) -> CustomerComplaint:
    values = _as_dict(data)
    await validate_product_line(db, values["product_line_code"])
    await _ensure_customer(db, values["customer_id"])
    if values.get("capa_ref_id") is not None:
        await _ensure_capa(db, values["capa_ref_id"])
    if values.get("fmea_ref_id") is not None:
        await _ensure_fmea(db, values["fmea_ref_id"])
    values.setdefault("impact_qty", 0)
    values.setdefault("status", ComplaintStatus.OPEN.value)
    values.setdefault("has_rma", False)
    values.setdefault("supplier_responsibility", False)
    _validate_choice(values.get("category"), VALID_CATEGORIES, "category")
    _validate_choice(values.get("severity"), VALID_SEVERITIES, "severity")
    _validate_initial_status(
        values.get("status", ComplaintStatus.OPEN.value),
        {status.value for status in ComplaintStatus},
        {ComplaintStatus.CLOSED.value, ComplaintStatus.CANCELLED.value},
        "complaint",
    )

    existing = await db.execute(
        select(CustomerComplaint).where(CustomerComplaint.complaint_no == values["complaint_no"])
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"complaint number '{values['complaint_no']}' already exists")

    allowed = {
        "complaint_no",
        "product_line_code",
        "customer_id",
        "product_id",
        "batch_no",
        "serial_number",
        "category",
        "severity",
        "defect_desc",
        "impact_qty",
        "occurred_date",
        "received_date",
        "due_date",
        "status",
        "fmea_ref_id",
        "capa_ref_id",
        "has_rma",
        "preliminary_response",
        "root_cause",
        "corrective_action",
        "attachments",
        "assignee_id",
        "supplier_responsibility",
        "scar_ref_id",
        "supplier_id",
    }
    complaint = CustomerComplaint(
        complaint_id=uuid.uuid4(),
        **{key: value for key, value in values.items() if key in allowed},
    )
    complaint.created_by = user_id
    db.add(complaint)
    await _audit(
        db,
        "customer_complaints",
        complaint.complaint_id,
        "CREATE",
        user_id,
        {key: _jsonable(getattr(complaint, key)) for key in allowed if hasattr(complaint, key)},
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"complaint number '{values['complaint_no']}' already exists")
    await db.refresh(complaint)
    return complaint


async def update_complaint(
    db: AsyncSession,
    complaint: CustomerComplaint,
    update_data,
    user_id: uuid.UUID,
) -> CustomerComplaint:
    values = _as_dict(update_data, exclude_unset=True)
    if "product_line_code" in values and values["product_line_code"] is not None:
        await validate_product_line(db, values["product_line_code"])
    if "customer_id" in values and values["customer_id"] is not None:
        await _ensure_customer(db, values["customer_id"])
    if _complaint_link_identity_changed(complaint, values) and await _complaint_has_rmas(
        db, complaint.complaint_id
    ):
        raise ValueError("cannot change customer or product line while complaint has linked RMAs")
    if "capa_ref_id" in values and values["capa_ref_id"] is not None:
        await _ensure_capa(db, values["capa_ref_id"])
    if "fmea_ref_id" in values and values["fmea_ref_id"] is not None:
        await _ensure_fmea(db, values["fmea_ref_id"])
    if "complaint_no" in values and values["complaint_no"] != complaint.complaint_no:
        existing = await db.execute(
            select(CustomerComplaint).where(
                CustomerComplaint.complaint_no == values["complaint_no"]
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"complaint number '{values['complaint_no']}' already exists")
    if "status" in values and values["status"] is not None:
        _validate_direct_status_update(
            complaint.status,
            values["status"],
            {status.value for status in ComplaintStatus},
            {ComplaintStatus.CLOSED.value, ComplaintStatus.CANCELLED.value},
            "complaint",
        )
        if not _valid_direct_complaint_status_change(complaint.status, values["status"]):
            raise ValueError(
                f"invalid complaint status change: {complaint.status} -> {values['status']}"
            )
    if "category" in values:
        _validate_choice(values["category"], VALID_CATEGORIES, "category")
    if "severity" in values:
        _validate_choice(values["severity"], VALID_SEVERITIES, "severity")

    allowed = {
        "complaint_no",
        "product_line_code",
        "customer_id",
        "product_id",
        "batch_no",
        "serial_number",
        "category",
        "severity",
        "defect_desc",
        "impact_qty",
        "occurred_date",
        "received_date",
        "due_date",
        "status",
        "fmea_ref_id",
        "capa_ref_id",
        "has_rma",
        "preliminary_response",
        "root_cause",
        "corrective_action",
        "attachments",
        "assignee_id",
        "supplier_responsibility",
        "scar_ref_id",
        "supplier_id",
    }
    changed_fields = _apply_updates(complaint, values, allowed)
    if not changed_fields:
        return complaint

    await _audit(
        db, "customer_complaints", complaint.complaint_id, "UPDATE", user_id, changed_fields
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("complaint update violates a database constraint")
    await db.refresh(complaint)
    return complaint


async def transition_complaint(
    db: AsyncSession,
    complaint: CustomerComplaint,
    action: str,
    user_id: uuid.UUID,
) -> CustomerComplaint:
    old_status = complaint.status
    new_status = transition_complaint_status(complaint.status, action)
    complaint.status = new_status
    changed_fields = {"action": action, "status": {"before": old_status, "after": new_status}}
    if new_status == ComplaintStatus.CLOSED.value:
        complaint.closed_at = datetime.now(timezone.utc)
        changed_fields["closed_at"] = _jsonable(complaint.closed_at)

    await _audit(
        db,
        "customer_complaints",
        complaint.complaint_id,
        "TRANSITION",
        user_id,
        changed_fields,
    )
    await db.commit()
    await db.refresh(complaint)
    return complaint


async def link_complaint_capa(
    db: AsyncSession,
    complaint: CustomerComplaint,
    capa_ref_id: uuid.UUID,
    user_id: uuid.UUID,
) -> CustomerComplaint:
    await _ensure_capa(db, capa_ref_id)
    old_value = complaint.capa_ref_id
    complaint.capa_ref_id = capa_ref_id
    await _audit(
        db,
        "customer_complaints",
        complaint.complaint_id,
        "LINK_CAPA",
        user_id,
        {"capa_ref_id": {"before": _jsonable(old_value), "after": _jsonable(capa_ref_id)}},
    )
    await db.commit()
    await db.refresh(complaint)
    return complaint


async def link_complaint_fmea(
    db: AsyncSession,
    complaint: CustomerComplaint,
    fmea_ref_id: uuid.UUID,
    user_id: uuid.UUID,
) -> CustomerComplaint:
    await _ensure_fmea(db, fmea_ref_id)
    old_value = complaint.fmea_ref_id
    complaint.fmea_ref_id = fmea_ref_id
    await _audit(
        db,
        "customer_complaints",
        complaint.complaint_id,
        "LINK_FMEA",
        user_id,
        {"fmea_ref_id": {"before": _jsonable(old_value), "after": _jsonable(fmea_ref_id)}},
    )
    await db.commit()
    await db.refresh(complaint)
    return complaint


async def create_capa_from_complaint(
    db: AsyncSession,
    complaint: CustomerComplaint,
    document_no: str,
    user_id: uuid.UUID,
):
    await validate_product_line(db, complaint.product_line_code)
    existing = await db.execute(select(CAPAEightD).where(CAPAEightD.document_no == document_no))
    if existing.scalar_one_or_none():
        raise ValueError(f"CAPA report number '{document_no}' already exists.")

    summary = " ".join(complaint.defect_desc.split())[:80]
    title = f"{complaint.complaint_no} {summary}".strip()
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        title=title,
        document_no=document_no,
        status="D1_TEAM",
        severity=complaint.severity,
        due_date=complaint.due_date,
        product_line_code=complaint.product_line_code,
        created_by=user_id,
    )
    db.add(capa)
    await _audit(
        db,
        "capa_eightd",
        capa.report_id,
        "CREATE",
        user_id,
        {
            "title": title,
            "document_no": document_no,
            "severity": complaint.severity,
            "due_date": _jsonable(complaint.due_date),
            "product_line_code": complaint.product_line_code,
            "status": capa.status,
            "source_complaint_id": _jsonable(complaint.complaint_id),
        },
    )
    old_capa_ref_id = complaint.capa_ref_id
    old_status = complaint.status
    complaint.capa_ref_id = capa.report_id
    complaint.status = ComplaintStatus.INVESTIGATING.value
    await _audit(
        db,
        "customer_complaints",
        complaint.complaint_id,
        "CREATE_CAPA",
        user_id,
        {
            "capa_ref_id": {
                "before": _jsonable(old_capa_ref_id),
                "after": _jsonable(capa.report_id),
            },
            "status": {"before": old_status, "after": complaint.status},
        },
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"CAPA report number '{document_no}' already exists.")
    await db.refresh(capa)
    await db.refresh(complaint)
    return capa


async def list_rma_records(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    product_line: str | None = None,
    customer_id: uuid.UUID | None = None,
    complaint_id: uuid.UUID | None = None,
    status: str | None = None,
    responsibility: str | None = None,
    assignee_id: uuid.UUID | None = None,
) -> tuple[list[RMARecord], int]:
    conditions = []
    if product_line:
        conditions.append(RMARecord.product_line_code == product_line)
    if customer_id:
        conditions.append(RMARecord.customer_id == customer_id)
    if complaint_id:
        conditions.append(RMARecord.complaint_id == complaint_id)
    if status:
        conditions.append(RMARecord.status == status)
    if responsibility:
        conditions.append(RMARecord.responsibility == responsibility)
    if assignee_id:
        conditions.append(RMARecord.assignee_id == assignee_id)

    query = select(RMARecord)
    count_query = select(func.count()).select_from(RMARecord)
    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)
    query = query.order_by(RMARecord.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    total = (await db.execute(count_query)).scalar() or 0
    return list(result.scalars().all()), total


async def get_rma_record(db: AsyncSession, rma_id: uuid.UUID) -> RMARecord | None:
    return await db.get(RMARecord, rma_id)


async def create_rma_record(db: AsyncSession, data, user_id: uuid.UUID) -> RMARecord:
    values = _as_dict(data)
    await validate_product_line(db, values["product_line_code"])
    await _ensure_customer(db, values["customer_id"])
    if values.get("capa_ref_id") is not None:
        await _ensure_capa(db, values["capa_ref_id"])
    if values.get("fmea_ref_id") is not None:
        await _ensure_fmea(db, values["fmea_ref_id"])
    linked_complaint = None
    if values.get("complaint_id"):
        linked_complaint = await _ensure_complaint(db, values["complaint_id"])
        _validate_rma_complaint_link(
            values["customer_id"],
            values["product_line_code"],
            linked_complaint,
        )
    values.setdefault("status", RMAStatus.OPEN.value)
    _validate_initial_status(
        values.get("status", RMAStatus.OPEN.value),
        {status.value for status in RMAStatus},
        {RMAStatus.CLOSED.value, RMAStatus.CANCELLED.value},
        "RMA",
    )
    _validate_choice(
        values.get("responsibility"),
        VALID_RESPONSIBILITIES,
        "responsibility",
    )

    existing = await db.execute(select(RMARecord).where(RMARecord.rma_no == values["rma_no"]))
    if existing.scalar_one_or_none():
        raise ValueError(f"RMA number '{values['rma_no']}' already exists")

    allowed = {
        "rma_no",
        "product_line_code",
        "customer_id",
        "complaint_id",
        "product_id",
        "batch_no",
        "serial_number",
        "return_qty",
        "defect_type",
        "responsibility",
        "analysis_result",
        "corrective_action",
        "status",
        "fmea_ref_id",
        "capa_ref_id",
        "scar_ref_id",
        "attachments",
        "assignee_id",
        "tracking_number",
        "received_date",
    }
    rma = RMARecord(
        rma_id=uuid.uuid4(),
        **{key: value for key, value in values.items() if key in allowed},
    )
    rma.created_by = user_id
    old_has_rma = linked_complaint.has_rma if linked_complaint is not None else None
    if linked_complaint is not None:
        linked_complaint.has_rma = True
    db.add(rma)
    await _audit(
        db,
        "rma_records",
        rma.rma_id,
        "CREATE",
        user_id,
        {key: _jsonable(getattr(rma, key)) for key in allowed if hasattr(rma, key)},
    )
    if linked_complaint is not None:
        await _audit(
            db,
            "customer_complaints",
            linked_complaint.complaint_id,
            "LINK_RMA",
            user_id,
            {"has_rma": {"before": old_has_rma, "after": True}, "rma_id": _jsonable(rma.rma_id)},
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"RMA number '{values['rma_no']}' already exists")
    await db.refresh(rma)
    return rma


async def update_rma_record(
    db: AsyncSession,
    rma: RMARecord,
    update_data,
    user_id: uuid.UUID,
) -> RMARecord:
    values = _as_dict(update_data, exclude_unset=True)
    if "product_line_code" in values and values["product_line_code"] is not None:
        await validate_product_line(db, values["product_line_code"])
    if "customer_id" in values and values["customer_id"] is not None:
        await _ensure_customer(db, values["customer_id"])
    linked_complaint = None
    effective_link = _effective_rma_link_tuple(rma, values)
    if (
        effective_link is not None
        and {"complaint_id", "customer_id", "product_line_code"} & values.keys()
    ):
        complaint_id, customer_id, product_line_code = effective_link
        linked_complaint = await _ensure_complaint(db, complaint_id)
        _validate_rma_complaint_link(customer_id, product_line_code, linked_complaint)
    if "capa_ref_id" in values and values["capa_ref_id"] is not None:
        await _ensure_capa(db, values["capa_ref_id"])
    if "fmea_ref_id" in values and values["fmea_ref_id"] is not None:
        await _ensure_fmea(db, values["fmea_ref_id"])
    if "rma_no" in values and values["rma_no"] != rma.rma_no:
        existing = await db.execute(select(RMARecord).where(RMARecord.rma_no == values["rma_no"]))
        if existing.scalar_one_or_none():
            raise ValueError(f"RMA number '{values['rma_no']}' already exists")
    if "status" in values and values["status"] is not None:
        _validate_direct_status_update(
            rma.status,
            values["status"],
            {status.value for status in RMAStatus},
            {RMAStatus.CLOSED.value, RMAStatus.CANCELLED.value},
            "RMA",
        )
        if not _valid_direct_rma_status_change(rma.status, values["status"]):
            raise ValueError(f"invalid RMA status change: {rma.status} -> {values['status']}")
    if "responsibility" in values:
        _validate_choice(
            values["responsibility"],
            VALID_RESPONSIBILITIES,
            "responsibility",
        )

    allowed = {
        "rma_no",
        "product_line_code",
        "customer_id",
        "complaint_id",
        "product_id",
        "batch_no",
        "serial_number",
        "return_qty",
        "defect_type",
        "responsibility",
        "analysis_result",
        "corrective_action",
        "status",
        "fmea_ref_id",
        "capa_ref_id",
        "scar_ref_id",
        "attachments",
        "assignee_id",
        "tracking_number",
        "received_date",
        "closed_at",
    }
    old_complaint = None
    if "complaint_id" in values and values["complaint_id"] != rma.complaint_id and rma.complaint_id:
        old_complaint = await _ensure_complaint(db, rma.complaint_id)

    changed_fields = _apply_updates(rma, values, allowed)
    if linked_complaint is not None and not linked_complaint.has_rma:
        old_has_rma = linked_complaint.has_rma
        linked_complaint.has_rma = True
        changed_fields["linked_complaint_has_rma"] = {
            "before": old_has_rma,
            "after": True,
        }
    if old_complaint is not None:
        old_has_rma = old_complaint.has_rma
        old_complaint.has_rma = await _complaint_has_other_rmas(
            db, old_complaint.complaint_id, rma.rma_id
        )
        if old_has_rma != old_complaint.has_rma:
            changed_fields["old_complaint_has_rma"] = {
                "before": old_has_rma,
                "after": old_complaint.has_rma,
            }
    if not changed_fields:
        return rma

    await _audit(db, "rma_records", rma.rma_id, "UPDATE", user_id, changed_fields)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("RMA update violates a database constraint")
    await db.refresh(rma)
    return rma


async def transition_rma(
    db: AsyncSession,
    rma: RMARecord,
    action: str,
    user_id: uuid.UUID,
) -> RMARecord:
    old_status = rma.status
    new_status = transition_rma_status(rma.status, action)
    rma.status = new_status
    changed_fields = {"action": action, "status": {"before": old_status, "after": new_status}}
    if new_status == RMAStatus.CLOSED.value:
        rma.closed_at = datetime.now(timezone.utc)
        changed_fields["closed_at"] = _jsonable(rma.closed_at)

    await _audit(db, "rma_records", rma.rma_id, "TRANSITION", user_id, changed_fields)
    await db.commit()
    await db.refresh(rma)
    return rma


async def link_rma_complaint(
    db: AsyncSession,
    rma: RMARecord,
    complaint_id: uuid.UUID,
    user_id: uuid.UUID,
) -> RMARecord:
    complaint = await _ensure_complaint(db, complaint_id)
    _validate_rma_complaint_link(rma.customer_id, rma.product_line_code, complaint)
    old_complaint_id = rma.complaint_id
    old_has_rma = complaint.has_rma
    old_complaint = None
    if old_complaint_id and old_complaint_id != complaint_id:
        old_complaint = await _ensure_complaint(db, old_complaint_id)
    rma.complaint_id = complaint_id
    complaint.has_rma = True
    changed_fields = {
        "complaint_id": {
            "before": _jsonable(old_complaint_id),
            "after": _jsonable(complaint_id),
        },
        "complaint_has_rma": {"before": old_has_rma, "after": True},
    }
    if old_complaint is not None:
        old_complaint_has_rma = old_complaint.has_rma
        old_complaint.has_rma = await _complaint_has_other_rmas(
            db, old_complaint.complaint_id, rma.rma_id
        )
        changed_fields["old_complaint_has_rma"] = {
            "before": old_complaint_has_rma,
            "after": old_complaint.has_rma,
        }
    await _audit(
        db,
        "rma_records",
        rma.rma_id,
        "LINK_COMPLAINT",
        user_id,
        changed_fields,
    )
    await db.commit()
    await db.refresh(rma)
    return rma


async def link_rma_capa(
    db: AsyncSession,
    rma: RMARecord,
    capa_ref_id: uuid.UUID,
    user_id: uuid.UUID,
) -> RMARecord:
    await _ensure_capa(db, capa_ref_id)
    old_value = rma.capa_ref_id
    rma.capa_ref_id = capa_ref_id
    await _audit(
        db,
        "rma_records",
        rma.rma_id,
        "LINK_CAPA",
        user_id,
        {"capa_ref_id": {"before": _jsonable(old_value), "after": _jsonable(capa_ref_id)}},
    )
    await db.commit()
    await db.refresh(rma)
    return rma


async def link_rma_fmea(
    db: AsyncSession,
    rma: RMARecord,
    fmea_ref_id: uuid.UUID,
    user_id: uuid.UUID,
) -> RMARecord:
    await _ensure_fmea(db, fmea_ref_id)
    old_value = rma.fmea_ref_id
    rma.fmea_ref_id = fmea_ref_id
    await _audit(
        db,
        "rma_records",
        rma.rma_id,
        "LINK_FMEA",
        user_id,
        {"fmea_ref_id": {"before": _jsonable(old_value), "after": _jsonable(fmea_ref_id)}},
    )
    await db.commit()
    await db.refresh(rma)
    return rma


async def dashboard(
    db: AsyncSession,
    product_line: str | None = None,
    customer_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    shipment_qty: int | None = None,
) -> dict:
    window_start, window_end = _normalize_window(date_from, date_to)
    complaint_conditions = []
    rma_conditions = []
    if product_line:
        complaint_conditions.append(CustomerComplaint.product_line_code == product_line)
        rma_conditions.append(RMARecord.product_line_code == product_line)
    if customer_id:
        complaint_conditions.append(CustomerComplaint.customer_id == customer_id)
        rma_conditions.append(RMARecord.customer_id == customer_id)
    complaint_conditions.append(CustomerComplaint.received_date >= window_start)
    complaint_conditions.append(CustomerComplaint.received_date <= window_end)
    rma_conditions.append(RMARecord.received_date >= window_start)
    rma_conditions.append(RMARecord.received_date <= window_end)

    complaints_result = await db.execute(select(CustomerComplaint).where(*complaint_conditions))
    rma_result = await db.execute(select(RMARecord).where(*rma_conditions))
    complaints = list(complaints_result.scalars().all())
    rma_records = list(rma_result.scalars().all())

    complaints_by_status = {status.value: 0 for status in ComplaintStatus}
    complaints_by_severity = {"致命": 0, "严重": 0, "一般": 0, "轻微": 0}
    rma_by_status = {status.value: 0 for status in RMAStatus}
    rma_by_responsibility = {
        "supplier": 0,
        "internal": 0,
        "transport": 0,
        "customer_misuse": 0,
        "unknown": 0,
    }
    trend_map: dict[str, dict] = {}

    for complaint in complaints:
        complaints_by_status[complaint.status] = complaints_by_status.get(complaint.status, 0) + 1
        complaints_by_severity[complaint.severity] = (
            complaints_by_severity.get(complaint.severity, 0) + 1
        )
        key = complaint.received_date.strftime("%Y-%m")
        trend_map.setdefault(key, {"period": key, "complaints": 0, "rma": 0, "rma_qty": 0})
        trend_map[key]["complaints"] += 1

    for rma in rma_records:
        rma_by_status[rma.status] = rma_by_status.get(rma.status, 0) + 1
        responsibility = rma.responsibility or "unknown"
        rma_by_responsibility[responsibility] = rma_by_responsibility.get(responsibility, 0) + 1
        if rma.received_date:
            key = rma.received_date.strftime("%Y-%m")
            trend_map.setdefault(key, {"period": key, "complaints": 0, "rma": 0, "rma_qty": 0})
            trend_map[key]["rma"] += 1
            trend_map[key]["rma_qty"] += rma.return_qty or 0

    open_complaint_count = sum(
        1
        for complaint in complaints
        if complaint.status
        in {
            ComplaintStatus.OPEN.value,
            ComplaintStatus.INVESTIGATING.value,
            ComplaintStatus.RESPONDED.value,
        }
    )
    overdue_count = sum(
        1 for complaint in complaints if complaint_is_overdue(complaint.status, complaint.due_date)
    )
    independent_rma_qty = sum(
        rma.return_qty or 0 for rma in rma_records if rma.complaint_id is None
    )
    impact_qty = sum(complaint.impact_qty or 0 for complaint in complaints)

    customer_conditions = []
    if customer_id:
        customer_conditions.append(Customer.customer_id == customer_id)
    customers_result = await db.execute(
        select(Customer).where(*customer_conditions).order_by(Customer.name)
    )
    customers = list(customers_result.scalars().all())
    customer_summaries = [
        await customer_summary(
            db,
            customer.customer_id,
            product_line=product_line,
            date_from=window_start,
            date_to=window_end,
            shipment_qty=shipment_qty if customer_id else None,
        )
        for customer in customers
    ]

    return {
        "kpi": {
            "complaint_count": len(complaints),
            "open_complaint_count": open_complaint_count,
            "overdue_count": overdue_count,
            "rma_count": len(rma_records),
            "return_qty": sum(rma.return_qty or 0 for rma in rma_records),
            "independent_rma_qty": independent_rma_qty,
            "impact_qty": impact_qty,
        },
        "customers": customer_summaries,
        "trend": [trend_map[key] for key in sorted(trend_map)],
        "complaints_by_status": complaints_by_status,
        "complaints_by_severity": complaints_by_severity,
        "rma_by_status": rma_by_status,
        "rma_by_responsibility": rma_by_responsibility,
    }


async def get_complaints_by_supplier(
    db: AsyncSession, supplier_id: str
) -> list[dict]:
    q = select(CustomerComplaint).where(
        CustomerComplaint.supplier_id == supplier_id
    )
    result = await db.execute(q)
    return [
        {
            "complaint_id": str(c.complaint_id),
            "complaint_no": c.complaint_no,
            "severity": c.severity,
            "status": c.status,
            "defect_desc": c.defect_desc,
        }
        for c in result.scalars().all()
    ]


# ─── SCAR creation from complaint / RMA ───

async def create_scar_from_complaint(
    db: AsyncSession,
    complaint_id: uuid.UUID,
    req_data: dict,
    user_id: uuid.UUID,
):
    # 1. Query complaint
    result = await db.execute(
        select(CustomerComplaint).where(CustomerComplaint.complaint_id == complaint_id)
    )
    complaint = result.scalar_one_or_none()
    if not complaint:
        raise ValueError("客诉不存在")

    # 2. Verify supplier responsibility
    if not complaint.supplier_responsibility:
        raise ValueError("该客诉未判定为供应商责任，无法创建 SCAR")

    # 3. Verify not already linked
    if complaint.scar_ref_id:
        raise ValueError("该客诉已关联 SCAR，无法重复创建")

    # 4. Determine supplier_id
    supplier_id = req_data.get("supplier_id") or complaint.supplier_id
    if not supplier_id:
        raise ValueError("缺少责任供应商信息")

    # 5. Determine description
    description = req_data.get("description") or complaint.defect_desc or "客诉关联 SCAR"

    # 6. Create SCAR + backfill in same transaction
    scar = await scar_service._create_scar_without_commit(
        db,
        supplier_id=supplier_id,
        source_type="complaint",
        source_id=complaint_id,
        description=description,
        requested_action=req_data.get("requested_action"),
        due_date=req_data.get("due_date"),
        issued_by=user_id,
        product_line_code=complaint.product_line_code,
    )

    complaint.scar_ref_id = scar.scar_id

    audit = AuditLog(
        table_name="customer_complaints",
        record_id=complaint_id,
        action="CREATE_SCAR",
        changed_fields={"scar_id": str(scar.scar_id), "scar_no": scar.scar_no},
        operated_by=user_id,
    )
    db.add(audit)
    await db.commit()
    return scar


async def create_scar_from_rma(
    db: AsyncSession,
    rma_id: uuid.UUID,
    req_data: dict,
    user_id: uuid.UUID,
):
    result = await db.execute(
        select(RMARecord).where(RMARecord.rma_id == rma_id)
    )
    rma = result.scalar_one_or_none()
    if not rma:
        raise ValueError("RMA 不存在")

    if rma.responsibility != "supplier":
        raise ValueError('该 RMA 责任判定不是"供应商"，无法创建 SCAR')

    if rma.scar_ref_id:
        raise ValueError("该 RMA 已关联 SCAR，无法重复创建")

    supplier_id = req_data.get("supplier_id")
    if not supplier_id:
        raise ValueError("缺少责任供应商信息（RMA 未记录供应商，请手动指定）")

    description = req_data.get("description")
    if not description:
        parts = [rma.defect_type or "RMA"]
        if rma.analysis_result:
            parts.append(rma.analysis_result)
        description = " — ".join(parts)

    scar = await scar_service._create_scar_without_commit(
        db,
        supplier_id=supplier_id,
        source_type="rma",
        source_id=rma_id,
        description=description,
        requested_action=req_data.get("requested_action"),
        due_date=req_data.get("due_date"),
        issued_by=user_id,
        product_line_code=rma.product_line_code,
    )

    rma.scar_ref_id = scar.scar_id

    audit = AuditLog(
        table_name="rma_records",
        record_id=rma_id,
        action="CREATE_SCAR",
        changed_fields={"scar_id": str(scar.scar_id), "scar_no": scar.scar_no},
        operated_by=user_id,
    )
    db.add(audit)
    await db.commit()
    return scar
