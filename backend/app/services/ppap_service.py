import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.supplier import Supplier, SupplierPPAPSubmission, SupplierPPAPElement
from app.models.audit import AuditLog


_UNSET = object()  # sentinel: distinguish omitted args from explicit None


PPAP_TRANSITIONS = {
    "submit":   ("draft",         "under_review"),
    "approve":  ("under_review",  "approved"),
    "reject":   ("under_review",  "rejected"),
    "resubmit": ("rejected",      "under_review"),
}

PPAP_ELEMENTS = [
    (1,  "设计记录", "Design Records"),
    (2,  "工程变更文件", "Authorized Engineering Change Documents"),
    (3,  "客户工程批准", "Customer Engineering Approval"),
    (4,  "设计 FMEA", "Design FMEA"),
    (5,  "过程流程图", "Process Flow Diagrams"),
    (6,  "过程 FMEA", "Process FMEA"),
    (7,  "控制计划", "Control Plan"),
    (8,  "测量系统分析", "Measurement System Analysis"),
    (9,  "尺寸结果", "Dimensional Results"),
    (10, "材料/性能试验结果", "Material / Performance Test Results"),
    (11, "初始过程研究", "Initial Process Studies"),
    (12, "合格实验室文件", "Qualified Laboratory Documentation"),
    (13, "外观批准报告", "Appearance Approval Report"),
    (14, "样件", "Sample Production Parts"),
    (15, "检具", "Checking Aids"),
    (16, "客户特殊要求", "Customer-Specific Requirements"),
    (17, "零件提交保证书", "Part Submission Warrant — PSW"),
    (18, "散装材料要求检查表", "Bulk Material Requirements Checklist"),
]

LEVEL_REQUIRED = {
    1: {17},
    2: {1, 17},
    3: set(range(1, 16)) | {17},
    4: set(range(1, 18)),
    5: set(range(1, 19)),
}


async def _next_ppap_no(db: AsyncSession) -> str:
    today = datetime.now(timezone.utc).strftime("%y%m%d")
    prefix = f"PPAP-{today}"
    result = await db.execute(
        select(SupplierPPAPSubmission.ppap_no)
        .where(SupplierPPAPSubmission.ppap_no.like(f"{prefix}-%"))
        .order_by(SupplierPPAPSubmission.ppap_no.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if last:
        seq = int(last.split("-")[-1]) + 1
    else:
        seq = 1
    return f"{prefix}-{seq:03d}"


def _build_elements(submission_id: uuid.UUID, submission_level: int) -> list[SupplierPPAPElement]:
    required_nos = LEVEL_REQUIRED.get(submission_level, set())
    elements = []
    for no, name_cn, name_en in PPAP_ELEMENTS:
        elements.append(SupplierPPAPElement(
            submission_id=submission_id,
            element_no=no,
            element_name=f"{name_cn} ({name_en})",
            required=(no in required_nos),
            status="pending",
            sort_order=no,
        ))
    return elements


async def _recalculate_elements(db: AsyncSession, submission_id: uuid.UUID, submission_level: int) -> None:
    """Update required flags on existing elements when level changes."""
    required_nos = LEVEL_REQUIRED.get(submission_level, set())
    result = await db.execute(
        select(SupplierPPAPElement).where(SupplierPPAPElement.submission_id == submission_id)
    )
    elements = result.scalars().all()
    for el in elements:
        el.required = el.element_no in required_nos


async def list_ppaps(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    statuses: list[str] | None = None,
    supplier_id: uuid.UUID | None = None,
) -> tuple[list[SupplierPPAPSubmission], int]:
    query = select(SupplierPPAPSubmission).options(
        selectinload(SupplierPPAPSubmission.supplier),
        selectinload(SupplierPPAPSubmission.elements),
    )
    count_query = select(func.count()).select_from(SupplierPPAPSubmission)

    if statuses:
        query = query.where(SupplierPPAPSubmission.status.in_(statuses))
        count_query = count_query.where(SupplierPPAPSubmission.status.in_(statuses))
    if supplier_id:
        query = query.where(SupplierPPAPSubmission.supplier_id == supplier_id)
        count_query = count_query.where(SupplierPPAPSubmission.supplier_id == supplier_id)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(SupplierPPAPSubmission.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())
    return items, total


async def get_ppap(db: AsyncSession, submission_id: uuid.UUID) -> SupplierPPAPSubmission | None:
    result = await db.execute(
        select(SupplierPPAPSubmission)
        .options(
            selectinload(SupplierPPAPSubmission.supplier),
            selectinload(SupplierPPAPSubmission.elements),
        )
        .where(SupplierPPAPSubmission.submission_id == submission_id)
    )
    return result.scalar_one_or_none()


async def create_ppap(
    db: AsyncSession,
    *,
    supplier_id: uuid.UUID,
    part_no: str,
    part_name: str,
    user_id: uuid.UUID,
    submission_level: int = 3,
    submission_date: date | None = None,
    customer_name: str | None = None,
    product_line_code: str | None = None,
    notes: str | None = None,
) -> SupplierPPAPSubmission:
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise ValueError("供应商不存在")

    for attempt in range(3):
        ppap_no = await _next_ppap_no(db)
        ppap = SupplierPPAPSubmission(
            ppap_no=ppap_no,
            supplier_id=supplier_id,
            part_no=part_no,
            part_name=part_name,
            submission_level=submission_level,
            submission_date=submission_date,
            customer_name=customer_name,
            product_line_code=product_line_code,
            notes=notes,
            created_by=user_id,
        )
        db.add(ppap)
        try:
            await db.flush()
            break
        except IntegrityError as e:
            if "uq_ppap_no" not in str(e.orig) and "ppap_no" not in str(e.orig):
                raise
            await db.rollback()
            if attempt == 2:
                raise ValueError("PPAP 编号生成冲突，请重试")
            continue

    # Auto-generate 18 elements
    for el in _build_elements(ppap.submission_id, submission_level):
        db.add(el)

    db.add(AuditLog(
        table_name="supplier_ppap_submissions",
        record_id=ppap.submission_id,
        action="CREATE",
        changed_fields={"ppap_no": ppap_no, "supplier_id": str(supplier_id), "part_no": part_no, "part_name": part_name, "submission_level": submission_level},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_ppap(db, ppap.submission_id)


async def update_ppap(
    db: AsyncSession,
    ppap: SupplierPPAPSubmission,
    *,
    user_id: uuid.UUID,
    part_no: str | None = _UNSET,
    part_name: str | None = _UNSET,
    submission_level: int | None = _UNSET,
    customer_name: str | None = _UNSET,
    product_line_code: str | None = _UNSET,
    notes: str | None = _UNSET,
) -> SupplierPPAPSubmission:
    if ppap.status != "draft":
        raise ValueError("仅草稿状态可以编辑")

    # Guard: non-nullable fields must not be explicitly None
    if part_no is not _UNSET and part_no is None:
        raise ValueError("零件号不能为空")
    if part_name is not _UNSET and part_name is None:
        raise ValueError("零件名称不能为空")
    if submission_level is not _UNSET and submission_level is None:
        raise ValueError("提交等级不能为空")

    changed: dict[str, object] = {}

    if part_no is not _UNSET:
        ppap.part_no = part_no
        changed["part_no"] = part_no
    if part_name is not _UNSET:
        ppap.part_name = part_name
        changed["part_name"] = part_name
    if submission_level is not _UNSET:
        ppap.submission_level = submission_level
        changed["submission_level"] = submission_level
        # Recalculate element required flags
        await _recalculate_elements(db, ppap.submission_id, submission_level)
    if customer_name is not _UNSET:
        ppap.customer_name = customer_name
        changed["customer_name"] = customer_name
    if product_line_code is not _UNSET:
        ppap.product_line_code = product_line_code
        changed["product_line_code"] = product_line_code
    if notes is not _UNSET:
        ppap.notes = notes
        changed["notes"] = notes

    if changed:
        db.add(AuditLog(
            table_name="supplier_ppap_submissions",
            record_id=ppap.submission_id,
            action="UPDATE",
            changed_fields={k: str(v) for k, v in changed.items()},
            operated_by=user_id,
        ))

    await db.commit()
    return await get_ppap(db, ppap.submission_id)


async def update_element(
    db: AsyncSession,
    element: SupplierPPAPElement,
    *,
    user_id: uuid.UUID,
    status: str | None = _UNSET,
    notes: str | None = _UNSET,
    file_url: str | None = _UNSET,
) -> SupplierPPAPElement:
    # Parent status guard: only allow element edits when submission is draft or under_review
    parent = await db.get(SupplierPPAPSubmission, element.submission_id)
    if parent and parent.status not in ("draft", "under_review"):
        raise ValueError(f"当前提交状态 {parent.status} 不允许编辑元素")

    # Guard: status must not be None if explicitly passed
    if status is not _UNSET and status is None:
        raise ValueError("元素状态不能为空")

    changed: dict[str, object] = {}

    if status is not _UNSET:
        old_status = element.status
        element.status = status
        changed["status"] = f"{old_status} -> {status}"
        if status == "pending":
            element.reviewed_by = None
            element.reviewed_at = None
        else:
            element.reviewed_by = user_id
            element.reviewed_at = datetime.now(timezone.utc)
            changed["reviewed_by"] = str(user_id)

    if notes is not _UNSET:
        element.notes = notes
        changed["notes"] = notes
    if file_url is not _UNSET:
        element.file_url = file_url
        changed["file_url"] = file_url

    if changed:
        db.add(AuditLog(
            table_name="supplier_ppap_elements",
            record_id=element.element_id,
            action="UPDATE",
            changed_fields={k: str(v) for k, v in changed.items()},
            operated_by=user_id,
        ))

    await db.commit()
    await db.refresh(element)
    return element


async def transition_ppap(
    db: AsyncSession,
    ppap: SupplierPPAPSubmission,
    action: str,
    user_id: uuid.UUID,
    rejection_reason: str | None = None,
) -> SupplierPPAPSubmission:
    if action not in PPAP_TRANSITIONS:
        raise ValueError(f"无效动作: {action}")

    expected_from, to_status = PPAP_TRANSITIONS[action]
    if ppap.status != expected_from:
        raise ValueError(f"当前状态 {ppap.status} 不允许执行 {action}（需要 {expected_from}）")

    # Approve gate: all required elements must be approved
    if action == "approve":
        result = await db.execute(
            select(SupplierPPAPElement).where(
                SupplierPPAPElement.submission_id == ppap.submission_id,
                SupplierPPAPElement.required == True,
            )
        )
        elements = result.scalars().all()
        not_approved = [el for el in elements if el.status != "approved"]
        if not_approved:
            raise ValueError("存在未批准的必填元素")

    # Reject requires reason
    if action == "reject" and not rejection_reason:
        raise ValueError("驳回原因不能为空")

    old_status = ppap.status
    ppap.status = to_status

    if action == "submit":
        if ppap.submission_date is None:
            ppap.submission_date = date.today()
    elif action == "approve":
        ppap.approved_by = user_id
        ppap.approved_at = datetime.now(timezone.utc)
    elif action == "reject":
        ppap.rejection_reason = rejection_reason
    elif action == "resubmit":
        ppap.revision += 1

    db.add(AuditLog(
        table_name="supplier_ppap_submissions",
        record_id=ppap.submission_id,
        action="TRANSITION",
        old_values={"status": old_status},
        new_values={"status": to_status},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_ppap(db, ppap.submission_id)


async def delete_ppap(
    db: AsyncSession,
    ppap: SupplierPPAPSubmission,
    user_id: uuid.UUID,
) -> None:
    if ppap.status != "draft":
        raise ValueError("仅草稿状态可以删除")

    db.add(AuditLog(
        table_name="supplier_ppap_submissions",
        record_id=ppap.submission_id,
        action="DELETE",
        operated_by=user_id,
    ))
    await db.delete(ppap)
    await db.commit()
