# PPAP 生产件批准 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement AIAG 18-element PPAP module with four-state approval workflow, auto-generated 18-element checklist, and cross-module links to APQP.

**Architecture:** Follows the SCAR/APQP module pattern exactly — flat table with state machine, async service layer with AuditLog, manual `_to_response()` mapping in API routes, and React pages with useState + Ant Design. Code placed alongside existing modules in `backend/app/` and `frontend/src/`.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 | React 18 + TypeScript 5.6 + Ant Design 5.21

**Spec:** `docs/superpowers/specs/2026-05-27-ppap-module-design.md`

---

### Task 1: Backend Model Changes

**Files:**
- Modify: `backend/app/models/supplier.py` — `SupplierPPAPSubmission` (L98-129) and `SupplierPPAPElement` (L132-147)

- [ ] **Step 1: Add fields to SupplierPPAPSubmission**

Find the `SupplierPPAPSubmission` class (starts at ~L98). Add the new fields before `supplier = relationship(...)` (L128).

```python
# backend/app/models/supplier.py — SupplierPPAPSubmission

# Add these after existing fields, before supplier relationship:

    ppap_no: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: Add fields to SupplierPPAPElement**

Find the `SupplierPPAPElement` class (starts at ~L132). Add the new fields after the existing fields, before `submission = relationship(...)` (L147).

```python
# backend/app/models/supplier.py — SupplierPPAPElement

# Add these after existing fields, before submission relationship:

    required: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
```

- [ ] **Step 3: Verify model imports compile**

Run: `cd backend && python -c "from app.models.supplier import SupplierPPAPSubmission, SupplierPPAPElement; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/supplier.py
git commit -m "feat(ppap): add ppap_no, revision, customer_name, rejection_reason to SupplierPPAPSubmission; add required, reviewed_by, reviewed_at, file_url to SupplierPPAPElement"
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/024_add_ppap_fields.py`

- [ ] **Step 1: Determine migration chain head**

Run: `cd backend && alembic heads`
Note the revision ID(s) shown. Use the one from the `apqp_projects` migration (`023_add_apqp_projects`) as `down_revision`.

- [ ] **Step 2: Create the migration file**

```python
"""add ppap_no, revision, customer_name, rejection_reason to supplier_ppap_submissions; add required, reviewed_by, reviewed_at, file_url to supplier_ppap_elements

Revision ID: 024_add_ppap_fields
Revises: 023_add_apqp_projects
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


revision = "024_add_ppap_fields"
down_revision = "023_add_apqp_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── supplier_ppap_submissions ──

    # Step 1: add nullable ppap_no
    op.add_column(
        "supplier_ppap_submissions",
        sa.Column("ppap_no", sa.String(30), nullable=True),
    )

    # Step 2: backfill ppap_no for existing rows (group by date, sequence within each date)
    conn = op.get_bind()
    rows = conn.execute(
        text("SELECT submission_id, created_at FROM supplier_ppap_submissions ORDER BY created_at, submission_id")
    ).fetchall()
    date_seq: dict[str, int] = {}
    for sub_id, created_at in rows:
        day_str = created_at.strftime("%y%m%d")
        date_seq[day_str] = date_seq.get(day_str, 0) + 1
        ppap_no = f"PPAP-{day_str}-{date_seq[day_str]:03d}"
        conn.execute(
            text("UPDATE supplier_ppap_submissions SET ppap_no = :no WHERE submission_id = :sid"),
            {"no": ppap_no, "sid": sub_id},
        )

    # Step 3: set NOT NULL
    op.alter_column("supplier_ppap_submissions", "ppap_no", nullable=False)

    # Step 4: add unique constraint
    op.create_unique_constraint("uq_ppap_no", "supplier_ppap_submissions", ["ppap_no"])

    # Step 5: add revision
    op.add_column(
        "supplier_ppap_submissions",
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
    )

    # Step 6: add customer_name
    op.add_column(
        "supplier_ppap_submissions",
        sa.Column("customer_name", sa.String(200), nullable=True),
    )

    # Step 7: add rejection_reason
    op.add_column(
        "supplier_ppap_submissions",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )

    # ── supplier_ppap_elements ──

    # Step 8: add required
    op.add_column(
        "supplier_ppap_elements",
        sa.Column("required", sa.Boolean(), server_default="true", nullable=False),
    )

    # Step 9: add reviewed_by
    op.add_column(
        "supplier_ppap_elements",
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ppap_elements_reviewed_by",
        "supplier_ppap_elements",
        "users",
        ["reviewed_by"],
        ["user_id"],
    )

    # Step 10: add reviewed_at
    op.add_column(
        "supplier_ppap_elements",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Step 11: add file_url
    op.add_column(
        "supplier_ppap_elements",
        sa.Column("file_url", sa.String(500), nullable=True),
    )

    # ── Data migration: fix old status enums ──
    op.execute("UPDATE supplier_ppap_submissions SET status = 'under_review' WHERE status = 'submitted'")
    op.execute("UPDATE supplier_ppap_elements SET status = 'in_review' WHERE status = 'submitted'")
    op.execute("UPDATE supplier_ppap_elements SET status = 'not_applicable' WHERE status = 'rejected'")


def downgrade() -> None:
    # Reverse data migration (best-effort)
    op.execute("UPDATE supplier_ppap_submissions SET status = 'submitted' WHERE status = 'under_review'")
    op.execute("UPDATE supplier_ppap_elements SET status = 'submitted' WHERE status = 'in_review'")
    op.execute("UPDATE supplier_ppap_elements SET status = 'rejected' WHERE status = 'not_applicable'")

    # supplier_ppap_elements
    op.drop_column("supplier_ppap_elements", "file_url")
    op.execute("ALTER TABLE supplier_ppap_elements DROP COLUMN IF EXISTS reviewed_at")
    op.drop_constraint("fk_ppap_elements_reviewed_by", "supplier_ppap_elements", type_="foreignkey")
    op.drop_column("supplier_ppap_elements", "reviewed_by")
    op.drop_column("supplier_ppap_elements", "required")

    # supplier_ppap_submissions
    op.drop_column("supplier_ppap_submissions", "rejection_reason")
    op.drop_column("supplier_ppap_submissions", "customer_name")
    op.drop_column("supplier_ppap_submissions", "revision")
    op.drop_constraint("uq_ppap_no", "supplier_ppap_submissions", type_="unique")
    op.drop_column("supplier_ppap_submissions", "ppap_no")
```

- [ ] **Step 3: Run the migration**

Run: `cd backend && alembic upgrade head`
Expected: success, no errors.

- [ ] **Step 4: Verify the schema**

Run: `cd backend && python -c "
from app.database import async_session
from sqlalchemy import inspect, text
async def check():
    async with async_session() as db:
        cols = await db.execute(text(
            \"SELECT column_name, is_nullable, data_type FROM information_schema.columns WHERE table_name = 'supplier_ppap_submissions' AND column_name IN ('ppap_no', 'revision', 'customer_name', 'rejection_reason') ORDER BY column_name\"
        ))
        for r in cols: print(r)
import asyncio; asyncio.run(check())
"`
Expected: 4 rows printed.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/024_add_ppap_fields.py
git commit -m "feat(ppap): add ppap_no/revision/customer_name/rejection_reason to submissions and required/reviewed_by/file_url to elements"
```

---

### Task 3: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/ppap.py`
- Modify: `backend/app/schemas/__init__.py`

- [ ] **Step 1: Create the schemas file**

```python
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class PPAPCreate(BaseModel):
    supplier_id: uuid.UUID
    part_no: str
    part_name: str
    submission_level: int = Field(ge=1, le=5, default=3)
    submission_date: date | None = None
    customer_name: str | None = None
    product_line_code: str | None = None
    notes: str | None = None


class PPAPUpdate(BaseModel):
    part_no: str | None = None
    part_name: str | None = None
    submission_level: int | None = Field(ge=1, le=5, default=None)
    customer_name: str | None = None
    product_line_code: str | None = None
    notes: str | None = None


class PPAPElementUpdate(BaseModel):
    status: Literal["pending", "in_review", "approved", "not_applicable"] | None = None
    notes: str | None = None
    file_url: str | None = None


class PPAPElementResponse(BaseModel):
    element_id: uuid.UUID
    submission_id: uuid.UUID
    element_no: int
    element_name: str
    required: bool
    status: str
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    file_url: str | None
    notes: str | None
    sort_order: int

    model_config = {"from_attributes": True}


class PPAPResponse(BaseModel):
    submission_id: uuid.UUID
    ppap_no: str
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    supplier_no: str | None = None
    part_no: str
    part_name: str
    submission_level: int
    submission_date: date | None
    customer_name: str | None
    product_line_code: str | None
    status: str
    revision: int
    rejection_reason: str | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    notes: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    elements: list[PPAPElementResponse]

    model_config = {"from_attributes": True}


class PPAPListResponse(BaseModel):
    items: list[PPAPResponse]
    total: int
    page: int
    page_size: int


class PPAPTransitionRequest(BaseModel):
    action: Literal["submit", "approve", "reject", "resubmit"]
    rejection_reason: str | None = None
```

- [ ] **Step 2: Register schemas in __init__.py**

Add to `backend/app/schemas/__init__.py`:

```python
from app.schemas import ppap
```

- [ ] **Step 3: Verify schemas import**

Run: `cd backend && python -c "from app.schemas.ppap import PPAPResponse, PPAPListResponse, PPAPCreate; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/ppap.py backend/app/schemas/__init__.py
git commit -m "feat(ppap): add PPAP Pydantic schemas"
```

---

### Task 4: Service Layer

**Files:**
- Create: `backend/app/services/ppap_service.py`

- [ ] **Step 1: Write the full service**

```python
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.supplier import Supplier, SupplierPPAPSubmission, SupplierPPAPElement
from app.models.audit import AuditLog


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
    part_no: str | None = None,
    part_name: str | None = None,
    submission_level: int | None = None,
    customer_name: str | None = None,
    product_line_code: str | None = None,
    notes: str | None = None,
) -> SupplierPPAPSubmission:
    if ppap.status != "draft":
        raise ValueError("仅草稿状态可以编辑")

    changed: dict[str, object] = {}

    if part_no is not None:
        ppap.part_no = part_no
        changed["part_no"] = part_no
    if part_name is not None:
        ppap.part_name = part_name
        changed["part_name"] = part_name
    if submission_level is not None:
        ppap.submission_level = submission_level
        changed["submission_level"] = submission_level
        # Recalculate element required flags
        await _recalculate_elements(db, ppap.submission_id, submission_level)
    if customer_name is not None:
        ppap.customer_name = customer_name
        changed["customer_name"] = customer_name
    if product_line_code is not None:
        ppap.product_line_code = product_line_code
        changed["product_line_code"] = product_line_code
    if notes is not None:
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
    status: str | None = None,
    notes: str | None = None,
    file_url: str | None = None,
) -> SupplierPPAPElement:
    changed: dict[str, object] = {}

    if status is not None:
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

    if notes is not None:
        element.notes = notes
        changed["notes"] = notes
    if file_url is not None:
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
```

- [ ] **Step 2: Verify service imports**

Run: `cd backend && python -c "from app.services import ppap_service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/ppap_service.py
git commit -m "feat(ppap): add PPAP service layer with state machine, 18-element auto-fill, and approve gate"
```

---

### Task 5: API Routes

**Files:**
- Create: `backend/app/api/ppap.py`

- [ ] **Step 1: Write the full API routes**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User
from app.schemas import ppap as ppap_schemas
from app.services import ppap_service

router = APIRouter(prefix="/api/ppap", tags=["ppap"])


def _to_response(ppap) -> ppap_schemas.PPAPResponse:
    """Convert SupplierPPAPSubmission ORM object with loaded supplier and elements to PPAPResponse."""
    return ppap_schemas.PPAPResponse(
        submission_id=ppap.submission_id,
        ppap_no=ppap.ppap_no,
        supplier_id=ppap.supplier_id,
        supplier_name=ppap.supplier.name if ppap.supplier else None,
        supplier_no=ppap.supplier.supplier_no if ppap.supplier else None,
        part_no=ppap.part_no,
        part_name=ppap.part_name,
        submission_level=ppap.submission_level,
        submission_date=ppap.submission_date,
        customer_name=ppap.customer_name,
        product_line_code=ppap.product_line_code,
        status=ppap.status,
        revision=ppap.revision,
        rejection_reason=ppap.rejection_reason,
        approved_by=ppap.approved_by,
        approved_at=ppap.approved_at,
        notes=ppap.notes,
        created_by=ppap.created_by,
        created_at=ppap.created_at,
        updated_at=ppap.updated_at,
        elements=[
            ppap_schemas.PPAPElementResponse(
                element_id=el.element_id,
                submission_id=el.submission_id,
                element_no=el.element_no,
                element_name=el.element_name,
                required=el.required,
                status=el.status,
                reviewed_by=el.reviewed_by,
                reviewed_at=el.reviewed_at,
                file_url=el.file_url,
                notes=el.notes,
                sort_order=el.sort_order,
            )
            for el in (ppap.elements or [])
        ],
    )


@router.get("", response_model=ppap_schemas.PPAPListResponse)
async def list_ppaps(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Comma-separated statuses"),
    supplier_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    statuses = status.split(",") if status else None
    items, total = await ppap_service.list_ppaps(db, page, page_size, statuses, supplier_id)
    return ppap_schemas.PPAPListResponse(
        items=[_to_response(s) for s in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{ppap_id}", response_model=ppap_schemas.PPAPResponse)
async def get_ppap(
    ppap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    ppap = await ppap_service.get_ppap(db, ppap_id)
    if not ppap:
        raise HTTPException(404, "PPAP not found")
    return _to_response(ppap)


@router.post("", response_model=ppap_schemas.PPAPResponse)
async def create_ppap(
    req: ppap_schemas.PPAPCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        ppap = await ppap_service.create_ppap(
            db,
            supplier_id=req.supplier_id,
            part_no=req.part_no,
            part_name=req.part_name,
            submission_level=req.submission_level,
            submission_date=req.submission_date,
            customer_name=req.customer_name,
            product_line_code=req.product_line_code,
            notes=req.notes,
            user_id=user.user_id,
        )
        return _to_response(ppap)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{ppap_id}", response_model=ppap_schemas.PPAPResponse)
async def update_ppap(
    ppap_id: uuid.UUID,
    req: ppap_schemas.PPAPUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    ppap = await ppap_service.get_ppap(db, ppap_id)
    if not ppap:
        raise HTTPException(404, "PPAP not found")
    try:
        ppap = await ppap_service.update_ppap(
            db, ppap,
            user_id=user.user_id,
            part_no=req.part_no,
            part_name=req.part_name,
            submission_level=req.submission_level,
            customer_name=req.customer_name,
            product_line_code=req.product_line_code,
            notes=req.notes,
        )
        return _to_response(ppap)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{ppap_id}/elements/{element_id}", response_model=ppap_schemas.PPAPElementResponse)
async def update_ppap_element(
    ppap_id: uuid.UUID,
    element_id: uuid.UUID,
    req: ppap_schemas.PPAPElementUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    from sqlalchemy import select as sa_select
    result = await db.execute(
        sa_select(ppap_service.SupplierPPAPElement).where(
            ppap_service.SupplierPPAPElement.element_id == element_id,
            ppap_service.SupplierPPAPElement.submission_id == ppap_id,
        )
    )
    element = result.scalar_one_or_none()
    if not element:
        raise HTTPException(404, "PPAP element not found")
    try:
        element = await ppap_service.update_element(
            db, element,
            user_id=user.user_id,
            status=req.status,
            notes=req.notes,
            file_url=req.file_url,
        )
        return ppap_schemas.PPAPElementResponse(
            element_id=element.element_id,
            submission_id=element.submission_id,
            element_no=element.element_no,
            element_name=element.element_name,
            required=element.required,
            status=element.status,
            reviewed_by=element.reviewed_by,
            reviewed_at=element.reviewed_at,
            file_url=element.file_url,
            notes=element.notes,
            sort_order=element.sort_order,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{ppap_id}/transition", response_model=ppap_schemas.PPAPResponse)
async def transition_ppap(
    ppap_id: uuid.UUID,
    req: ppap_schemas.PPAPTransitionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Route-level role check
    if req.action in ("approve", "reject"):
        if user.role not in ("admin", "manager"):
            raise HTTPException(403, "需要 manager 或 admin 权限")
    elif req.action in ("submit", "resubmit"):
        if user.role not in ("admin", "manager", "quality_engineer"):
            raise HTTPException(403, "需要 engineer 或更高权限")

    ppap = await ppap_service.get_ppap(db, ppap_id)
    if not ppap:
        raise HTTPException(404, "PPAP not found")
    try:
        ppap = await ppap_service.transition_ppap(
            db, ppap, req.action, user_id=user.user_id,
            rejection_reason=req.rejection_reason,
        )
        return _to_response(ppap)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{ppap_id}")
async def delete_ppap(
    ppap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    ppap = await ppap_service.get_ppap(db, ppap_id)
    if not ppap:
        raise HTTPException(404, "PPAP not found")
    try:
        await ppap_service.delete_ppap(db, ppap, user.user_id)
        return {"message": "PPAP 已删除"}
    except ValueError as e:
        raise HTTPException(400, str(e))
```

- [ ] **Step 2: Verify routes import**

Run: `cd backend && python -c "from app.api.ppap import router; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/ppap.py
git commit -m "feat(ppap): add PPAP API routes with role-gated transitions"
```

---

### Task 6: Register Router in main.py

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add import and router registration**

Add the import after the `apqp_router` import (L38):

```python
from app.api.ppap import router as ppap_router
```

Add the router registration after `app.include_router(apqp_router)` (L92):

```python
app.include_router(ppap_router)
```

- [ ] **Step 2: Verify app starts with new router**

Run: `cd backend && timeout 5 python -c "from app.main import app; print(len(app.routes))" 2>/dev/null || echo "App loaded"`
Expected: Number of routes printed (should increase by 7).

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(ppap): register PPAP router in main API"
```

---

### Task 7: Mark Old PPAP Schemas Deprecated

**Files:**
- Modify: `backend/app/schemas/supplier.py` (lines around L203-254)

- [ ] **Step 1: Add deprecation comment**

Find the PPAP section in `supplier.py` (around L203, starts with `# ─── PPAP ───`). Add a comment block above it:

```python
# ─── PPAP (DEPRECATED) ───
# 这些旧 PPAP schema 已被 schemas/ppap.py 取代，保留以兼容已有模型引用。
# 新 PPAP 模块请使用 schemas/ppap.py。
# DEPRECATED: 迁移至 schemas/ppap.py
```

- [ ] **Step 2: Verify schemas still import**

Run: `cd backend && python -c "from app.schemas.supplier import PPAPSubmissionResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/supplier.py
git commit -m "chore(ppap): mark old PPAP schemas in supplier.py as deprecated"
```

---

### Task 8: Service Layer Tests

**Files:**
- Create: `backend/tests/test_ppap_service.py`

- [ ] **Step 1: Write the tests**

```python
import pytest
import pytest_asyncio
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models.supplier import Supplier, SupplierPPAPSubmission, SupplierPPAPElement
from app.models.user import User
from app.models.audit import AuditLog
from app.models.product_line import ProductLine
from app.database import Base
from app.services import ppap_service

import app.models  # noqa: F401 — ensure all FK-referenced tables are registered
import os
from urllib.parse import urlparse


@pytest_asyncio.fixture(scope="function")
async def db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; this test requires a dedicated test database")
    db_name = urlparse(url).path.lstrip("/")
    if "_test" not in db_name:
        pytest.skip(f"Database '{db_name}' does not contain '_test'; refusing to run destructive tests")

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            ProductLine.__table__.insert().values(code="DC-DC-100", name="DC-DC Convert 100W")
        )
        await conn.commit()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _make_user(db: AsyncSession, username: str, role: str) -> User:
    user = User(
        user_id=uuid.uuid4(), username=username, display_name=username,
        role=role, password_hash="hash",
    )
    db.add(user)
    await db.commit()
    return user


async def _make_supplier(db: AsyncSession, user: User, supplier_no: str = "SUP-TEST") -> Supplier:
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=supplier_no,
        name=f"Test Supplier {supplier_no}",
        short_name=supplier_no,
        created_by=user.user_id,
    )
    db.add(supplier)
    await db.commit()
    return supplier


async def _make_ppap(db: AsyncSession, user: User, supplier_id: uuid.UUID, **kwargs) -> SupplierPPAPSubmission:
    return await ppap_service.create_ppap(
        db,
        supplier_id=supplier_id,
        part_no="TEST-PART",
        part_name="Test Part",
        user_id=user.user_id,
        **kwargs,
    )


class TestCreatePPAP:
    async def test_create_basic(self, db: AsyncSession):
        user = await _make_user(db, "ppap_create", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        assert ppap.ppap_no.startswith("PPAP-")
        assert ppap.status == "draft"
        assert ppap.revision == 1
        assert ppap.submission_level == 3
        assert len(ppap.elements) == 18

    async def test_create_with_invalid_supplier(self, db: AsyncSession):
        user = await _make_user(db, "ppap_invalid", "quality_engineer")
        with pytest.raises(ValueError, match="供应商不存在"):
            await _make_ppap(db, user, uuid.uuid4())

    async def test_create_level_1_elements(self, db: AsyncSession):
        user = await _make_user(db, "ppap_l1", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id, submission_level=1)
        assert len([e for e in ppap.elements if e.required]) == 1  # Only element 17 (PSW)


class TestTransition:
    async def test_submit_sets_submission_date(self, db: AsyncSession):
        user = await _make_user(db, "ppap_submit", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        ppap = await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        assert ppap.status == "under_review"
        assert ppap.submission_date == date.today()

    async def test_approve_requires_all_required_approved(self, db: AsyncSession):
        user = await _make_user(db, "ppap_appr", "manager")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        ppap = await ppap_service.get_ppap(db, ppap.submission_id)
        # Don't approve any elements — should fail
        with pytest.raises(ValueError, match="未批准的必填元素"):
            await ppap_service.transition_ppap(db, ppap, "approve", user.user_id)

    async def test_approve_rejects_required_not_applicable(self, db: AsyncSession):
        user = await _make_user(db, "ppap_na", "manager")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        ppap = await ppap_service.get_ppap(db, ppap.submission_id)
        # Set all required elements to not_applicable instead of approved
        for el in ppap.elements:
            if el.required:
                await ppap_service.update_element(db, el, user_id=user.user_id, status="not_applicable")
        with pytest.raises(ValueError, match="未批准的必填元素"):
            await ppap_service.transition_ppap(db, ppap, "approve", user.user_id)

    async def test_approve_succeeds_when_elements_approved(self, db: AsyncSession):
        user = await _make_user(db, "ppap_ok", "manager")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        ppap = await ppap_service.get_ppap(db, ppap.submission_id)
        # Set all required elements to approved
        for el in ppap.elements:
            if el.required:
                await ppap_service.update_element(db, el, user_id=user.user_id, status="approved")
        ppap = await ppap_service.transition_ppap(db, ppap, "approve", user.user_id)
        assert ppap.status == "approved"
        assert ppap.approved_by == user.user_id

    async def test_reject_requires_reason(self, db: AsyncSession):
        user = await _make_user(db, "ppap_rej", "manager")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        ppap = await ppap_service.get_ppap(db, ppap.submission_id)
        with pytest.raises(ValueError, match="驳回原因不能为空"):
            await ppap_service.transition_ppap(db, ppap, "reject", user.user_id)

    async def test_resubmit_increments_revision(self, db: AsyncSession):
        user = await _make_user(db, "ppap_resub", "quality_engineer")
        manager = await _make_user(db, "ppap_mgr", "manager")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        ppap = await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        ppap = await ppap_service.transition_ppap(db, ppap, "reject", manager.user_id, rejection_reason="材料不全")
        assert ppap.status == "rejected"
        assert ppap.rejection_reason == "材料不全"
        ppap = await ppap_service.transition_ppap(db, ppap, "resubmit", user.user_id)
        assert ppap.status == "under_review"
        assert ppap.revision == 2

    async def test_invalid_transition_raises(self, db: AsyncSession):
        user = await _make_user(db, "ppap_bad", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        with pytest.raises(ValueError, match="不允许"):
            await ppap_service.transition_ppap(db, ppap, "approve", user.user_id)


class TestUpdateElement:
    async def test_update_element_sets_reviewer(self, db: AsyncSession):
        user = await _make_user(db, "ppap_el", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        el = ppap.elements[0]
        el = await ppap_service.update_element(db, el, user_id=user.user_id, status="approved")
        assert el.status == "approved"
        assert el.reviewed_by == user.user_id
        assert el.reviewed_at is not None

    async def test_update_element_reset_to_pending_clears_reviewer(self, db: AsyncSession):
        user = await _make_user(db, "ppap_el2", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        el = ppap.elements[0]
        el = await ppap_service.update_element(db, el, user_id=user.user_id, status="approved")
        el = await ppap_service.update_element(db, el, user_id=user.user_id, status="pending")
        assert el.status == "pending"
        assert el.reviewed_by is None
        assert el.reviewed_at is None


class TestUpdatePPAP:
    async def test_update_level_recalculates_required(self, db: AsyncSession):
        user = await _make_user(db, "ppap_upd", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id, submission_level=3)
        # Change from level 3 to level 1 — only element 17 should be required
        ppap = await ppap_service.update_ppap(db, ppap, user_id=user.user_id, submission_level=1)
        ppap = await ppap_service.get_ppap(db, ppap.submission_id)
        required = [e for e in ppap.elements if e.required]
        assert len(required) == 1
        assert required[0].element_no == 17

    async def test_update_only_draft(self, db: AsyncSession):
        user = await _make_user(db, "ppap_upd2", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        ppap = await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        with pytest.raises(ValueError, match="草稿"):
            await ppap_service.update_ppap(db, ppap, user_id=user.user_id, part_no="NEW")


class TestDeletePPAP:
    async def test_delete_draft(self, db: AsyncSession):
        user = await _make_user(db, "ppap_del", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        await ppap_service.delete_ppap(db, ppap, user.user_id)
        deleted = await ppap_service.get_ppap(db, ppap.submission_id)
        assert deleted is None

    async def test_delete_non_draft(self, db: AsyncSession):
        user = await _make_user(db, "ppap_del2", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        ppap = await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        with pytest.raises(ValueError, match="草稿"):
            await ppap_service.delete_ppap(db, ppap, user.user_id)
```

- [ ] **Step 2: Run the specific test suite**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://sam:password@localhost:5432/openqms_test python -m pytest tests/test_ppap_service.py -v --allow-module-level=True 2>&1 | head -80`
(Adjust TEST_DATABASE_URL to your test database.)
Expected: All tests pass (or skip if no test DB).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_ppap_service.py
git commit -m "test(ppap): add service layer tests for create, transitions, element updates, and guards"
```

---

### Task 9: Frontend TypeScript Types

**Files:**
- Modify: `frontend/src/types/index.ts` — `PPAPSubmission` (L569) and `PPAPElement` (L586)

- [ ] **Step 1: Expand PPAPSubmission and PPAPElement**

Replace the existing `PPAPSubmission` and `PPAPElement` interfaces with:

```typescript
export interface PPAPSubmission {
  submission_id: string;
  ppap_no: string;
  supplier_id: string;
  supplier_name: string | null;
  supplier_no: string | null;
  part_no: string;
  part_name: string;
  submission_level: number;
  submission_date: string | null;
  customer_name: string | null;
  product_line_code: string | null;
  status: 'draft' | 'under_review' | 'approved' | 'rejected';
  revision: number;
  rejection_reason: string | null;
  approved_by: string | null;
  approved_at: string | null;
  notes: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  elements: PPAPElement[];
}

export interface PPAPElement {
  element_id: string;
  submission_id: string;
  element_no: number;
  element_name: string;
  required: boolean;
  status: 'pending' | 'in_review' | 'approved' | 'not_applicable';
  reviewed_by: string | null;
  reviewed_at: string | null;
  file_url: string | null;
  notes: string | null;
  sort_order: number;
}
```

- [ ] **Step 2: Add new request/response interfaces**

Add these new interfaces after the `PPAPElement` interface:

```typescript
export interface PPAPListResponse {
  items: PPAPSubmission[];
  total: number;
  page: number;
  page_size: number;
}

export interface PPAPCreate {
  supplier_id: string;
  part_no: string;
  part_name: string;
  submission_level: number;
  submission_date?: string;
  customer_name?: string;
  product_line_code?: string;
  notes?: string;
}

export interface PPAPElementUpdate {
  status?: 'pending' | 'in_review' | 'approved' | 'not_applicable';
  notes?: string;
  file_url?: string;
}

export interface PPAPTransitionRequest {
  action: 'submit' | 'approve' | 'reject' | 'resubmit';
  rejection_reason?: string;
}
```

- [ ] **Step 3: Verify types compile**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors from the PPAP types.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(ppap): expand PPAPSubmission/PPAPElement types, add PPAPListResponse/PPAPCreate/PPAPElementUpdate/PPAPTransitionRequest"
```

---

### Task 10: Frontend API Client

**Files:**
- Create: `frontend/src/api/ppap.ts`

- [ ] **Step 1: Write the API client**

```typescript
import client from "./client";
import type {
  PPAPListResponse,
  PPAPSubmission,
  PPAPCreate,
  PPAPElement,
  PPAPElementUpdate,
  PPAPTransitionRequest,
} from "../types";

export async function listPPAPs(params: {
  page?: number;
  page_size?: number;
  status?: string;
  supplier_id?: string;
}): Promise<PPAPListResponse> {
  const res = await client.get("/ppap", { params });
  return res.data;
}

export async function getPPAP(id: string): Promise<PPAPSubmission> {
  const res = await client.get(`/ppap/${id}`);
  return res.data;
}

export async function createPPAP(data: PPAPCreate): Promise<PPAPSubmission> {
  const res = await client.post("/ppap", data);
  return res.data;
}

export async function updatePPAP(id: string, data: Partial<PPAPCreate>): Promise<PPAPSubmission> {
  const res = await client.put(`/ppap/${id}`, data);
  return res.data;
}

export async function updatePPAPElement(
  submissionId: string,
  elementId: string,
  data: PPAPElementUpdate,
): Promise<PPAPElement> {
  const res = await client.put(`/ppap/${submissionId}/elements/${elementId}`, data);
  return res.data;
}

export async function transitionPPAP(id: string, data: PPAPTransitionRequest): Promise<PPAPSubmission> {
  const res = await client.post(`/ppap/${id}/transition`, data);
  return res.data;
}

export async function deletePPAP(id: string): Promise<void> {
  await client.delete(`/ppap/${id}`);
}
```

- [ ] **Step 2: Verify file compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/ppap.ts
git commit -m "feat(ppap): add frontend API client for PPAP module"
```

---

### Task 11: PPAP List Page

**Files:**
- Create: `frontend/src/pages/ppap/PPAPListPage.tsx`

- [ ] **Step 1: Write the list page**

```typescript
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Tag, Tabs, Button, Select, Space, Modal, Form, Input, InputNumber, message, Card, Row, Col } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { listPPAPs, createPPAP } from "../../api/ppap";
import { listSuppliers } from "../../api/supplier";
import type { PPAPSubmission, PPAPListResponse, Supplier } from "../../types";

const STATUS_TABS = [
  { key: "all", label: "全部" },
  { key: "draft", label: "草稿" },
  { key: "under_review", label: "审查中" },
  { key: "approved", label: "已批准" },
  { key: "rejected", label: "已驳回" },
];

const STATUS_MAP: Record<string, string | undefined> = {
  all: undefined,
  draft: "draft",
  under_review: "under_review",
  approved: "approved",
  rejected: "rejected",
};

export const STATUS_COLORS: Record<string, string> = {
  draft: "default",
  under_review: "processing",
  approved: "success",
  rejected: "error",
};

export const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  under_review: "审查中",
  approved: "已批准",
  rejected: "已驳回",
};

export const LEVEL_LABELS: Record<number, string> = {
  1: "Level 1",
  2: "Level 2",
  3: "Level 3",
  4: "Level 4",
  5: "Level 5",
};

export default function PPAPListPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<PPAPListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("all");
  const [supplierId, setSupplierId] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [form] = Form.useForm();
  const [kpis, setKpis] = useState({ total: 0, pending: 0, approved: 0, rejected: 0 });

  const loadData = async () => {
    setLoading(true);
    try {
      const result = await listPPAPs({ page, page_size: 20, status: STATUS_MAP[activeTab], supplier_id: supplierId });
      setData(result);
      // Load KPI counts in parallel
      const [all, draftR, underReviewR, approvedR, rejectedR] = await Promise.all([
        listPPAPs({ page: 1, page_size: 1 }),
        listPPAPs({ page: 1, page_size: 1, status: "draft" }),
        listPPAPs({ page: 1, page_size: 1, status: "under_review" }),
        listPPAPs({ page: 1, page_size: 1, status: "approved" }),
        listPPAPs({ page: 1, page_size: 1, status: "rejected" }),
      ]);
      setKpis({ total: all.total, pending: draftR.total + underReviewR.total, approved: approvedR.total, rejected: rejectedR.total });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, [activeTab, supplierId, page]);

  const handleCreate = async (values: Record<string, unknown>) => {
    await createPPAP({
      supplier_id: values.supplier_id as string,
      part_no: values.part_no as string,
      part_name: values.part_name as string,
      submission_level: (values.submission_level as number) || 3,
      customer_name: values.customer_name as string | undefined,
    });
    message.success("PPAP 创建成功");
    setCreateOpen(false);
    form.resetFields();
    loadData();
  };

  const columns = [
    { title: "PPAP编号", dataIndex: "ppap_no", key: "ppap_no" },
    { title: "供应商", dataIndex: "supplier_name", key: "supplier_name", render: (v: string | null) => v || "-" },
    { title: "零件号", dataIndex: "part_no", key: "part_no" },
    { title: "零件名称", dataIndex: "part_name", key: "part_name" },
    {
      title: "提交等级",
      dataIndex: "submission_level",
      key: "submission_level",
      render: (v: number) => <Tag>{LEVEL_LABELS[v] || v}</Tag>,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (s: string) => <Tag color={STATUS_COLORS[s]}>{STATUS_LABELS[s] || s}</Tag>,
    },
    { title: "版本", dataIndex: "revision", key: "revision" },
    { title: "创建时间", dataIndex: "created_at", key: "created_at", render: (v: string) => v?.split("T")[0] || "-" },
    {
      title: "操作",
      key: "action",
      render: (_: unknown, record: PPAPSubmission) => (
        <Button type="link" onClick={() => navigate(`/ppap/${record.submission_id}`)}>
          查看
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><div style={{ color: "#999" }}>PPAP 总数</div><div style={{ fontSize: 24, fontWeight: 600 }}>{kpis.total}</div></Card></Col>
        <Col span={6}><Card size="small"><div style={{ color: "#999" }}>待审</div><div style={{ fontSize: 24, fontWeight: 600, color: "#1677ff" }}>{kpis.pending}</div></Card></Col>
        <Col span={6}><Card size="small"><div style={{ color: "#999" }}>已批准</div><div style={{ fontSize: 24, fontWeight: 600, color: "#52c41a" }}>{kpis.approved}</div></Card></Col>
        <Col span={6}><Card size="small"><div style={{ color: "#999" }}>已驳回</div><div style={{ fontSize: 24, fontWeight: 600, color: "#ff4d4f" }}>{kpis.rejected}</div></Card></Col>
      </Row>

      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={STATUS_TABS} />
        <Space>
          <Select
            allowClear
            showSearch
            filterOption={false}
            placeholder="筛选供应商"
            style={{ width: 160 }}
            onSearch={async (search) => {
              const res = search ? await listSuppliers({ search, page_size: 20 }) : await listSuppliers({ page_size: 20 });
              setSuppliers(res.items);
            }}
            onChange={(v) => { setSupplierId(v); setPage(1); }}
            options={suppliers.map((s) => ({ value: s.supplier_id, label: s.name }))}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建 PPAP
          </Button>
        </Space>
      </div>

      <Table
        dataSource={data?.items || []}
        columns={columns}
        rowKey="submission_id"
        loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total: data?.total || 0,
          onChange: setPage,
        }}
      />

      <Modal
        title="新建 PPAP"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleCreate} initialValues={{ submission_level: 3 }}>
          <Form.Item name="supplier_id" label="供应商" rules={[{ required: true, message: "请选择供应商" }]}>
            <Select
              showSearch
              filterOption={false}
              onSearch={async (search) => {
                const res = search ? await listSuppliers({ search, page_size: 20 }) : await listSuppliers({ page_size: 20 });
                setSuppliers(res.items);
              }}
              options={suppliers.map((s) => ({ value: s.supplier_id, label: `${s.supplier_no} - ${s.name}` }))}
              placeholder="搜索供应商"
            />
          </Form.Item>
          <Form.Item name="part_no" label="零件号" rules={[{ required: true, message: "请输入零件号" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="part_name" label="零件名称" rules={[{ required: true, message: "请输入零件名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="submission_level" label="提交等级" rules={[{ required: true }]}>
            <InputNumber min={1} max={5} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="customer_name" label="客户名称">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Verify compilation**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors from list page.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ppap/PPAPListPage.tsx
git commit -m "feat(ppap): add PPAP list page with KPI cards, status tabs, and create modal"
```

---

### Task 12: PPAP Detail Page

**Files:**
- Create: `frontend/src/pages/ppap/PPAPDetailPage.tsx`

- [ ] **Step 1: Write the detail page**

```typescript
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, Tag, Button, Space, Descriptions, Modal, Input, Select, message, Spin, Row, Col, Table } from "antd";
import { getPPAP, updatePPAPElement, transitionPPAP, deletePPAP } from "../../api/ppap";
import { STATUS_COLORS, STATUS_LABELS, LEVEL_LABELS } from "./PPAPListPage";
import type { PPAPSubmission, PPAPElement } from "../../types";

const ELEMENT_STATUS_COLORS: Record<string, string> = {
  pending: "default",
  in_review: "processing",
  approved: "success",
  not_applicable: "default",
};

const ELEMENT_STATUS_LABELS: Record<string, string> = {
  pending: "待审查",
  in_review: "审查中",
  approved: "已批准",
  not_applicable: "不适用",
};

export default function PPAPDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [ppap, setPpap] = useState<PPAPSubmission | null>(null);
  const [loading, setLoading] = useState(true);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [editElementOpen, setEditElementOpen] = useState(false);
  const [editingElement, setEditingElement] = useState<PPAPElement | null>(null);
  const [editStatus, setEditStatus] = useState<string>("pending");
  const [editNotes, setEditNotes] = useState("");
  const [editFileUrl, setEditFileUrl] = useState("");

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getPPAP(id);
      setPpap(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [id]);

  const doTransition = async (action: string, extra?: Record<string, string>) => {
    if (!id) return;
    await transitionPPAP(id, { action: action as "submit" | "approve" | "reject" | "resubmit", ...extra });
    message.success("状态更新成功");
    load();
  };

  const handleReject = async () => {
    if (!rejectReason.trim()) { message.warning("请输入驳回原因"); return; }
    await doTransition("reject", { rejection_reason: rejectReason });
    setRejectModalOpen(false);
    setRejectReason("");
  };

  const handleEditElement = (el: PPAPElement) => {
    setEditingElement(el);
    setEditStatus(el.status);
    setEditNotes(el.notes || "");
    setEditFileUrl(el.file_url || "");
    setEditElementOpen(true);
  };

  const handleSaveElement = async () => {
    if (!editingElement || !id) return;
    await updatePPAPElement(id, editingElement.element_id, {
      status: editStatus as "pending" | "in_review" | "approved" | "not_applicable",
      notes: editNotes || undefined,
      file_url: editFileUrl || undefined,
    });
    message.success("元素已更新");
    setEditElementOpen(false);
    load();
  };

  const handleDelete = async () => {
    if (!id) return;
    Modal.confirm({
      title: "确认删除",
      content: "确定要删除此 PPAP 提交吗？此操作不可撤销。",
      onOk: async () => {
        await deletePPAP(id);
        message.success("PPAP 已删除");
        navigate("/ppap");
      },
    });
  };

  if (loading || !ppap) {
    return <div style={{ textAlign: "center", padding: 100 }}><Spin size="large" /></div>;
  }

  const actionButtons = () => {
    const btns: ReactNode[] = [];
    if (ppap.status === "draft") {
      btns.push(<Button key="submit" type="primary" onClick={() => doTransition("submit")}>提交审查</Button>);
      if (ppap.status === "draft") {
        btns.push(<Button key="delete" danger onClick={handleDelete}>删除</Button>);
      }
    }
    if (ppap.status === "under_review") {
      btns.push(<Button key="approve" type="primary" onClick={() => doTransition("approve")}>批准</Button>);
      btns.push(<Button key="reject" danger onClick={() => setRejectModalOpen(true)}>驳回</Button>);
    }
    if (ppap.status === "rejected") {
      btns.push(<Button key="resubmit" type="primary" onClick={() => doTransition("resubmit")}>重新提交</Button>);
    }
    return btns;
  };

  const elementColumns = [
    { title: "序号", dataIndex: "element_no", key: "element_no", width: 60 },
    { title: "元素名称", dataIndex: "element_name", key: "element_name" },
    {
      title: "是否必须",
      dataIndex: "required",
      key: "required",
      width: 80,
      render: (v: boolean) => v ? "✓" : <span style={{ color: "#ccc" }}>—</span>,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (s: string) => <Tag color={ELEMENT_STATUS_COLORS[s]}>{ELEMENT_STATUS_LABELS[s] || s}</Tag>,
    },
    { title: "审查人", dataIndex: "reviewed_by", key: "reviewed_by", width: 100, render: (v: string | null) => v || "-" },
    { title: "审查时间", dataIndex: "reviewed_at", key: "reviewed_at", width: 160, render: (v: string | null) => v ? v.split(".")[0].replace("T", " ") : "-" },
    { title: "文件", dataIndex: "file_url", key: "file_url", render: (v: string | null) => v ? <a href={v} target="_blank" rel="noopener noreferrer">查看</a> : "-" },
    { title: "备注", dataIndex: "notes", key: "notes", ellipsis: true },
    {
      title: "操作",
      key: "action",
      width: 80,
      render: (_: unknown, record: PPAPElement) => (
        <Button type="link" size="small" onClick={() => handleEditElement(record)}>编辑</Button>
      ),
    },
  ];

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space>
              <span style={{ fontSize: 20, fontWeight: 600 }}>{ppap.ppap_no}</span>
              <Tag color={STATUS_COLORS[ppap.status]}>{STATUS_LABELS[ppap.status]}</Tag>
              <span style={{ color: "#999" }}>版本 {ppap.revision}</span>
            </Space>
          </Col>
          <Col>
            <Space>{actionButtons()}</Space>
          </Col>
        </Row>
      </Card>

      <Card title="PPAP 信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="供应商">{ppap.supplier_name || ppap.supplier_id}</Descriptions.Item>
          <Descriptions.Item label="零件号">{ppap.part_no}</Descriptions.Item>
          <Descriptions.Item label="零件名称">{ppap.part_name}</Descriptions.Item>
          <Descriptions.Item label="提交等级">{LEVEL_LABELS[ppap.submission_level] || ppap.submission_level}</Descriptions.Item>
          <Descriptions.Item label="客户名称">{ppap.customer_name || "-"}</Descriptions.Item>
          <Descriptions.Item label="产品线">{ppap.product_line_code || "-"}</Descriptions.Item>
          <Descriptions.Item label="提交日期">{ppap.submission_date || "-"}</Descriptions.Item>
          <Descriptions.Item label="备注" span={2}>{ppap.notes || "-"}</Descriptions.Item>
        </Descriptions>
      </Card>

      {ppap.status === "rejected" && ppap.rejection_reason && (
        <Card title="驳回原因" style={{ marginBottom: 16, borderColor: "#ff4d4f" }}>
          <div style={{ color: "#ff4d4f", whiteSpace: "pre-wrap" }}>{ppap.rejection_reason}</div>
        </Card>
      )}

      <Card title="18 元素">
        <Table
          dataSource={ppap.elements}
          columns={elementColumns}
          rowKey="element_id"
          pagination={false}
          size="small"
          rowClassName={(record) => !record.required ? "ppap-row-optional" : ""}
        />
      </Card>

      {/* Reject Modal */}
      <Modal title="驳回 PPAP" open={rejectModalOpen} onCancel={() => setRejectModalOpen(false)} onOk={handleReject}>
        <Input.TextArea
          rows={4}
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          placeholder="请输入驳回原因"
        />
      </Modal>

      {/* Edit Element Modal */}
      <Modal title={`编辑元素: ${editingElement?.element_name || ""}`} open={editElementOpen} onCancel={() => setEditElementOpen(false)} onOk={handleSaveElement}>
        <div style={{ marginBottom: 16 }}>
          <label>状态</label>
          <Select
            style={{ width: "100%" }}
            value={editStatus}
            onChange={setEditStatus}
            options={[
              { value: "pending", label: "待审查" },
              { value: "in_review", label: "审查中" },
              { value: "approved", label: "已批准" },
              { value: "not_applicable", label: "不适用" },
            ]}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label>文件路径</label>
          <Input value={editFileUrl} onChange={(e) => setEditFileUrl(e.target.value)} placeholder="文件路径或 URL（可选）" />
        </div>
        <div>
          <label>备注</label>
          <Input.TextArea rows={2} value={editNotes} onChange={(e) => setEditNotes(e.target.value)} placeholder="备注（可选）" />
        </div>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Verify compilation**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ppap/PPAPDetailPage.tsx
git commit -m "feat(ppap): add PPAP detail page with 18-element table, action buttons, and element editing"
```

---

### Task 13: Routes and Sidebar Menu

**Files:**
- Modify: `frontend/src/App.tsx` (add routes)
- Modify: `frontend/src/components/layout/AppLayout.tsx` (add sidebar menu)

- [ ] **Step 1: Add PPAP routes to App.tsx**

Find the imports section in `App.tsx`. Add after the APQP imports (around L110 routing area):

```typescript
import PPAPListPage from "./pages/ppap/PPAPListPage";
import PPAPDetailPage from "./pages/ppap/PPAPDetailPage";
```

Inside the `<Route>` block, add after the APQP routes:

```typescript
        <Route path="/ppap" element={<PPAPListPage />} />
        <Route path="/ppap/:id" element={<PPAPDetailPage />} />
```

- [ ] **Step 2: Add PPAP to sidebar menu**

In `AppLayout.tsx`, add the PPAP menu item after the APQP entry (L33):

```typescript
  { key: "/ppap", icon: <FileProtectOutlined />, label: "PPAP" },
```

Add `FileProtectOutlined` to the import from `@ant-design/icons`:

```typescript
  FileProtectOutlined,
```

- [ ] **Step 3: Verify full frontend build**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -5`
Expected: No TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(ppap): add PPAP routes and sidebar menu item"
```

---

### Verification Checklist

- [ ] Backend starts without errors: `cd backend && timeout 5 uvicorn app.main:app --host 0.0.0.0 --port 8000 2>&1 || true`
- [ ] Backend health check: `curl -s http://localhost:8000/api/health`
- [ ] Migration applied: `cd backend && alembic current`
- [ ] Frontend builds: `cd frontend && npx tsc --noEmit`
- [ ] PPAP API endpoints accessible (after backend start)
- [ ] All PPAP service tests pass: `cd backend && TEST_DATABASE_URL=... python -m pytest tests/test_ppap_service.py -v`
