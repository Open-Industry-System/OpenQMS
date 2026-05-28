# 客户审核管理模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build customer audit management on top of existing audit infrastructure, adding customer-specific fields, transition-based finding status management, and customer confirmation workflows.

**Architecture:** Extends existing `audit_plans`/`audit_findings` tables with new columns. Adds a dedicated `customer_audit_service.py` (to avoid bloating the existing 885-line `audit_service.py`). Frontend follows the InternalAuditListPage/DetailPage pattern with two new pages.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + Alembic | React 18 + TypeScript + Ant Design 5.21

**Spec:** `docs/superpowers/specs/2026-05-28-customer-audit-design.md`

---

### Task 1: Database Migration 025

**Files:**
- Create: `backend/alembic/versions/025_add_customer_audit_fields.py`

**当前 Alembic head**: `024_add_ppap_fields`

- [ ] **Step 1: Create the migration file**

```python
"""add customer audit fields

Revision ID: 025
Revises: 024_add_ppap_fields
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "025"
down_revision = "024_add_ppap_fields"


def upgrade() -> None:
    # audit_plans new columns
    op.add_column("audit_plans", sa.Column(
        "audit_category", sa.String(20), server_default="internal", nullable=False,
    ))
    op.add_column("audit_plans", sa.Column(
        "customer_name", sa.String(200), nullable=True,
    ))
    op.add_column("audit_plans", sa.Column(
        "customer_type", sa.String(50), nullable=True,
    ))
    op.add_column("audit_plans", sa.Column(
        "audit_mode", sa.String(20), nullable=True,
    ))
    op.add_column("audit_plans", sa.Column(
        "customer_confirmation_doc", JSONB, server_default="[]", nullable=False,
    ))

    # CHECK constraints
    op.execute(
        "ALTER TABLE audit_plans ADD CONSTRAINT chk_audit_category "
        "CHECK (audit_category IN ('internal', 'customer', 'supplier'))"
    )
    op.execute(
        "ALTER TABLE audit_plans ADD CONSTRAINT chk_audit_mode "
        "CHECK (audit_mode IS NULL OR audit_mode IN ('on_site', 'remote'))"
    )
    op.execute(
        "ALTER TABLE audit_plans ADD CONSTRAINT chk_customer_type "
        "CHECK (customer_type IS NULL OR customer_type IN ('OEM', 'Tier 1', 'Tier 2', '其他'))"
    )

    op.create_index("idx_audit_plans_category", "audit_plans", ["audit_category"])
    op.create_index("idx_audit_plans_customer_type", "audit_plans", ["customer_type"])

    # audit_findings new columns
    op.add_column("audit_findings", sa.Column(
        "customer_confirmed", sa.Boolean, server_default="false", nullable=False,
    ))
    op.add_column("audit_findings", sa.Column(
        "customer_confirmation_date", sa.Date, nullable=True,
    ))
    op.add_column("audit_findings", sa.Column(
        "customer_confirmation_attachments", JSONB, server_default="[]", nullable=False,
    ))

    op.create_index("idx_audit_findings_confirmed", "audit_findings", ["customer_confirmed"])

    # capa_ref_id → real FK
    op.execute(
        "UPDATE audit_findings SET capa_ref_id = NULL "
        "WHERE capa_ref_id IS NOT NULL "
        "AND capa_ref_id NOT IN (SELECT report_id FROM capa_eightd)"
    )
    op.create_foreign_key(
        "fk_audit_findings_capa", "audit_findings", "capa_eightd",
        ["capa_ref_id"], ["report_id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_audit_findings_capa", "audit_findings", type_="foreignkey")

    op.drop_index("idx_audit_findings_confirmed", table_name="audit_findings")
    op.drop_column("audit_findings", "customer_confirmation_attachments")
    op.drop_column("audit_findings", "customer_confirmation_date")
    op.drop_column("audit_findings", "customer_confirmed")

    op.drop_constraint("chk_customer_type", "audit_plans", type_="check")
    op.drop_constraint("chk_audit_mode", "audit_plans", type_="check")
    op.drop_constraint("chk_audit_category", "audit_plans", type_="check")

    op.drop_index("idx_audit_plans_customer_type", table_name="audit_plans")
    op.drop_index("idx_audit_plans_category", table_name="audit_plans")
    op.drop_column("audit_plans", "customer_confirmation_doc")
    op.drop_column("audit_plans", "audit_mode")
    op.drop_column("audit_plans", "customer_type")
    op.drop_column("audit_plans", "customer_name")
    op.drop_column("audit_plans", "audit_category")
```

- [ ] **Step 2: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: `Running upgrade 020 -> 021, add customer audit fields`

- [ ] **Step 3: Verify columns exist**

Run: `cd backend && python -c "from app.models import *; print('Models loaded OK')"`
Expected: `Models loaded OK`

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/021_add_customer_audit_fields.py
git commit -m "feat(db): add customer audit migration 021"
```

---

### Task 2: Extend ORM Models

**Files:**
- Modify: `backend/app/models/audit_plan.py`
- Modify: `backend/app/models/audit_finding.py`

- [ ] **Step 1: Add fields to AuditPlan model**

In `backend/app/models/audit_plan.py`, add these imports and columns after the existing `product_line_code` field (line 37):

```python
# Add to existing imports at top:
from sqlalchemy import Boolean

# Add after product_line_code (line 37):
    audit_category: Mapped[str] = mapped_column(String(20), default="internal", nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    audit_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    customer_confirmation_doc: Mapped[list] = mapped_column(JSONB, default=list)
```

- [ ] **Step 2: Add fields to AuditFinding model**

In `backend/app/models/audit_finding.py`, add these imports and columns after `closed_at` (line 33):

```python
# Add to existing imports at top:
from sqlalchemy import Boolean
from sqlalchemy.dialects.postgresql import JSONB

# Add after closed_at (line 33):
    customer_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    customer_confirmation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer_confirmation_attachments: Mapped[list] = mapped_column(JSONB, default=list)
```

Also update the `capa_ref_id` field (line 26) to add an explicit ForeignKey:
```python
# Change this line:
    capa_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
# To:
    capa_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capa_eightd.report_id"), nullable=True
    )
```

- [ ] **Step 3: Verify models load**

Run: `cd backend && python -c "from app.models import *; print('Models loaded OK')"`
Expected: `Models loaded OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/audit_plan.py backend/app/models/audit_finding.py
git commit -m "feat(models): add customer audit fields to AuditPlan and AuditFinding"
```

---

### Task 3: Extend Pydantic Schemas

**Files:**
- Modify: `backend/app/schemas/audit.py`

- [ ] **Step 1: Add customer audit schemas to audit.py**

Append the following at the end of `backend/app/schemas/audit.py` (after `AuditStatsResponse`, line 204):

```python
# ── Customer Audit Schemas ──


class AuditPlanCreate(BaseModel):  # existing class already exists, this extends it
    pass
```

**首先，扩展 AuditProgram 校验**：现有 `AuditProgramCreate` (line 13) 的 `audit_type` validator 只接受 `"system"`、`"process"`、`"product"`。需增加 `"customer"`。同时 `_generate_program_no` 的 type_map 需增加 `"customer": "CUS"`。

替换 `AuditProgramCreate` validator (line 13-18):
```python
    @field_validator("audit_type")
    @classmethod
    def validate_audit_type(cls, v: str) -> str:
        if v not in ("system", "process", "product", "customer"):
            raise ValueError('audit_type must be one of "system", "process", "product", "customer"')
        return v
```

同样替换 `AuditProgramUpdate` validator (line 29-36):
```python
    @field_validator("audit_type")
    @classmethod
    def validate_audit_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("system", "process", "product", "customer"):
            raise ValueError('audit_type must be one of "system", "process", "product", "customer"')
        return v
```

**然后，修改 AuditPlanCreate** (line 61) 添加客户审核字段。替换为:

```python
class AuditPlanCreate(BaseModel):
    program_id: uuid.UUID
    audit_scope: str
    audit_criteria: str
    planned_date: date
    lead_auditor: uuid.UUID | None = None
    team_members: list | None = None
    checklist: list | None = None
    product_line_code: str | None = None
    # Customer audit fields
    audit_category: str = "internal"
    customer_name: str | None = None
    customer_type: str | None = None
    audit_mode: str | None = None

    @field_validator("audit_category")
    @classmethod
    def validate_audit_category(cls, v: str) -> str:
        if v not in ("internal", "customer", "supplier"):
            raise ValueError('audit_category must be one of "internal", "customer", "supplier"')
        return v

    @field_validator("audit_mode")
    @classmethod
    def validate_audit_mode(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("on_site", "remote"):
            raise ValueError('audit_mode must be one of "on_site", "remote"')
        return v

    @field_validator("customer_type")
    @classmethod
    def validate_customer_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("OEM", "Tier 1", "Tier 2", "其他"):
            raise ValueError('customer_type must be one of "OEM", "Tier 1", "Tier 2", "其他"')
        return v
```

Replace existing `AuditPlanUpdate` (line 72) with:

```python
class AuditPlanUpdate(BaseModel):
    audit_scope: str | None = None
    audit_criteria: str | None = None
    planned_date: date | None = None
    actual_date: date | None = None
    lead_auditor: uuid.UUID | None = None
    team_members: list | None = None
    checklist: list | None = None
    status: str | None = None
    product_line_code: str | None = None
    customer_name: str | None = None
    customer_type: str | None = None
    audit_mode: str | None = None
```

Replace existing `AuditPlanResponse` (line 84) with:

```python
class AuditPlanResponse(BaseModel):
    audit_id: uuid.UUID
    plan_no: str
    program_id: uuid.UUID
    audit_scope: str
    audit_criteria: str
    planned_date: date
    actual_date: date | None
    lead_auditor: uuid.UUID | None
    team_members: list
    checklist: list
    status: str
    product_line_code: str | None = None
    audit_category: str = "internal"
    customer_name: str | None = None
    customer_type: str | None = None
    audit_mode: str | None = None
    customer_confirmation_doc: list = []
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

Add `customer_confirmed` fields to `AuditFindingResponse` (line 148). Replace it with:

```python
class AuditFindingResponse(BaseModel):
    finding_id: uuid.UUID
    audit_id: uuid.UUID
    clause_ref: str | None
    finding_type: str
    description: str
    root_cause: str | None
    correction: str | None
    corrective_action: str | None
    capa_ref_id: uuid.UUID | None
    status: str
    due_date: date | None
    closed_at: datetime | None
    customer_confirmed: bool = False
    customer_confirmation_date: date | None = None
    customer_confirmation_attachments: list = []
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

Add these new schemas at the end of the file:

```python
class FindingTransitionRequest(BaseModel):
    action: str
    customer_confirmed: bool | None = None
    customer_confirmation_date: date | None = None
    customer_confirmation_attachments: list | None = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in ("start_progress", "close"):
            raise ValueError('action must be one of "start_progress", "close"')
        return v


class CustomerAuditAttachment(BaseModel):
    file_name: str
    file_url: str
    file_size: int | None = None
    file_type: str | None = None
    uploaded_at: str | None = None
    uploaded_by: str | None = None


class CustomerAuditStatsResponse(BaseModel):
    total_customer_audits: int
    planned: int
    in_progress: int
    completed: int
    open_findings: int
    major_nc_count: int
    customer_confirmed_count: int
    pending_confirmation_count: int


class CustomerConfirmationRequest(BaseModel):
    confirmation_date: date
    attachments: list[CustomerAuditAttachment] = []
```

- [ ] **Step 2: Verify schemas load**

Run: `cd backend && python -c "from app.schemas.audit import *; print('Schemas OK')"`
Expected: `Schemas OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/audit.py
git commit -m "feat(schemas): add customer audit fields and transition request schemas"
```

---

### Task 4: Customer Audit Service

**Files:**
- Create: `backend/app/services/customer_audit_service.py`

- [ ] **Step 1: Create the service file**

```python
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.audit_finding import AuditFinding
from app.models.audit_plan import AuditPlan
from app.models.audit_program import AuditProgram
from app.models.capa import CAPAEightD

VALID_CUSTOMER_TYPES = {"OEM", "Tier 1", "Tier 2", "其他"}
VALID_AUDIT_MODES = {"on_site", "remote"}


async def _ensure_customer_program(db: AsyncSession, year: int) -> AuditProgram:
    """Return the default customer audit program for a year, creating if needed."""
    result = await db.execute(
        select(AuditProgram).where(
            AuditProgram.audit_type == "customer",
            AuditProgram.program_year == year,
        )
    )
    program = result.scalar_one_or_none()
    if program:
        return program

    prefix = f"AP-{year}-CUS"
    count_result = await db.execute(
        select(func.count()).where(AuditProgram.program_no.like(f"{prefix}-%"))
    )
    count = count_result.scalar() or 0

    program = AuditProgram(
        program_no=f"{prefix}-{count + 1:03d}",
        program_year=year,
        audit_type="customer",
        scope="客户审核方案",
        criteria="客户审核标准",
        status="active",
    )
    db.add(program)
    await db.flush()
    return program


编号按 `CA-YYYY-%` 单独计数，与 `PL-YYYY-%` 互不影响。

```python
async def _generate_customer_audit_no(db: AsyncSession, year: int) -> str:
    prefix = f"CA-{year}"
    result = await db.execute(
        select(func.count()).where(AuditPlan.plan_no.like(f"{prefix}-%"))
    )
    count = result.scalar() or 0
    return f"{prefix}-{count + 1:03d}"


async def create_customer_audit(
    db: AsyncSession,
    *,
    audit_scope: str,
    audit_criteria: str,
    planned_date: date,
    customer_name: str,
    customer_type: str,
    audit_mode: str | None,
    lead_auditor: uuid.UUID | None,
    team_members: list | None,
    checklist: list | None,
    product_line_code: str | None,
    user_id: uuid.UUID,
) -> AuditPlan:
    if customer_type not in VALID_CUSTOMER_TYPES:
        raise ValueError(f"invalid customer_type: {customer_type}")
    if audit_mode and audit_mode not in VALID_AUDIT_MODES:
        raise ValueError(f"invalid audit_mode: {audit_mode}")

    program = await _ensure_customer_program(db, planned_date.year)
    plan_no = await _generate_customer_audit_no(db, planned_date.year)

    plan = AuditPlan(
        plan_no=plan_no,
        program_id=program.program_id,
        audit_scope=audit_scope,
        audit_criteria=audit_criteria,
        planned_date=planned_date,
        lead_auditor=lead_auditor,
        team_members=team_members or [],
        checklist=checklist or [],
        status="planned",
        audit_category="customer",
        customer_name=customer_name,
        customer_type=customer_type,
        audit_mode=audit_mode,
        created_by=user_id,
        product_line_code=product_line_code,
    )
    db.add(plan)

    audit_log = AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id if hasattr(plan, "audit_id") else uuid.uuid4(),
        action="CREATE",
        changed_fields={"audit_category": "customer", "customer_name": customer_name},
        operated_by=user_id,
    )
    db.add(audit_log)

    await db.commit()
    await db.refresh(plan)
    return plan


async def list_customer_audits(
    db: AsyncSession,
    page: int,
    page_size: int,
    customer_type: str | None = None,
    audit_mode: str | None = None,
    customer_name: str | None = None,
    status: str | None = None,
) -> tuple[list[AuditPlan], int]:
    query = select(AuditPlan).where(AuditPlan.audit_category == "customer")
    count_query = select(func.count()).select_from(AuditPlan).where(AuditPlan.audit_category == "customer")

    if customer_type:
        query = query.where(AuditPlan.customer_type == customer_type)
        count_query = count_query.where(AuditPlan.customer_type == customer_type)
    if audit_mode:
        query = query.where(AuditPlan.audit_mode == audit_mode)
        count_query = count_query.where(AuditPlan.audit_mode == audit_mode)
    if customer_name:
        query = query.where(AuditPlan.customer_name.ilike(f"%{customer_name}%"))
        count_query = count_query.where(AuditPlan.customer_name.ilike(f"%{customer_name}%"))
    if status:
        query = query.where(AuditPlan.status == status)
        count_query = count_query.where(AuditPlan.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(AuditPlan.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def update_customer_audit(
    db: AsyncSession,
    plan: AuditPlan,
    *,
    user_id: uuid.UUID,
    customer_name: str | None = None,
    customer_type: str | None = None,
    audit_mode: str | None = None,
    audit_scope: str | None = None,
    audit_criteria: str | None = None,
    planned_date: date | None = None,
    lead_auditor: uuid.UUID | None = None,
    team_members: list | None = None,
    checklist: list | None = None,
    product_line_code: str | None = None,
) -> AuditPlan:
    changed: dict = {}
    if customer_name is not None and customer_name != plan.customer_name:
        changed["customer_name"] = {"before": plan.customer_name, "after": customer_name}
        plan.customer_name = customer_name
    if customer_type is not None and customer_type != plan.customer_type:
        if customer_type not in VALID_CUSTOMER_TYPES:
            raise ValueError(f"invalid customer_type: {customer_type}")
        changed["customer_type"] = {"before": plan.customer_type, "after": customer_type}
        plan.customer_type = customer_type
    if audit_mode is not None and audit_mode != plan.audit_mode:
        if audit_mode not in VALID_AUDIT_MODES:
            raise ValueError(f"invalid audit_mode: {audit_mode}")
        changed["audit_mode"] = {"before": plan.audit_mode, "after": audit_mode}
        plan.audit_mode = audit_mode
    if audit_scope is not None:
        plan.audit_scope = audit_scope
    if audit_criteria is not None:
        plan.audit_criteria = audit_criteria
    if planned_date is not None:
        plan.planned_date = planned_date
    if lead_auditor is not None:
        plan.lead_auditor = lead_auditor
    if team_members is not None:
        plan.team_members = team_members
    if checklist is not None:
        plan.checklist = checklist
    if product_line_code is not None:
        plan.product_line_code = product_line_code

    if changed:
        audit_log = AuditLog(
            table_name="audit_plans",
            record_id=plan.audit_id,
            action="UPDATE",
            changed_fields=changed,
            operated_by=user_id,
        )
        db.add(audit_log)

    await db.commit()
    await db.refresh(plan)
    return plan


async def complete_customer_audit(db: AsyncSession, plan: AuditPlan, user_id: uuid.UUID) -> AuditPlan:
    if plan.status != "in_progress":
        raise ValueError("only in-progress audits can be completed")

    # For customer audits, check all findings are closed and confirmed
    if plan.audit_category == "customer":
        result = await db.execute(
            select(AuditFinding.finding_id, AuditFinding.status, AuditFinding.customer_confirmed)
            .where(AuditFinding.audit_id == plan.audit_id, AuditFinding.status != "closed")
        )
        unclosed = result.all()
        if unclosed:
            raise ValueError(f"cannot complete: {len(unclosed)} finding(s) not closed")

        # Check all findings are customer-confirmed
        result = await db.execute(
            select(AuditFinding.finding_id)
            .where(
                AuditFinding.audit_id == plan.audit_id,
                AuditFinding.status == "closed",
                AuditFinding.customer_confirmed == False,
            )
        )
        unconfirmed = result.all()
        if unconfirmed:
            raise ValueError(f"cannot complete: {len(unconfirmed)} finding(s) not customer-confirmed")

    plan.status = "completed"
    plan.actual_date = datetime.now(timezone.utc).date()

    audit_log = AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="TRANSITION",
        changed_fields={"status": {"before": "in_progress", "after": "completed"}},
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(plan)
    return plan


async def transition_finding(
    db: AsyncSession,
    finding: AuditFinding,
    *,
    action: str,
    user_id: uuid.UUID,
    customer_confirmed: bool | None = None,
    customer_confirmation_date: date | None = None,
    customer_confirmation_attachments: list | None = None,
) -> AuditFinding:
    old_status = finding.status

    if action == "start_progress":
        if finding.status != "open":
            raise ValueError("only open findings can start progress")
        finding.status = "in_progress"

    elif action == "close":
        if finding.status not in ("open", "in_progress"):
            raise ValueError("only open or in_progress findings can be closed")
        if not finding.root_cause:
            raise ValueError("root_cause is required before closing")
        if not finding.corrective_action:
            raise ValueError("corrective_action is required before closing")

        # Check CAPA completion if linked
        if finding.capa_ref_id:
            capa_result = await db.execute(
                select(CAPAEightD.status).where(CAPAEightD.report_id == finding.capa_ref_id)
            )
            capa_status = capa_result.scalar_one_or_none()
            if capa_status != "D8_CLOSURE":
                raise ValueError(f"linked CAPA status is '{capa_status}', must be 'D8_CLOSURE'")

        # Check customer confirmation if this is a customer audit finding
        plan_result = await db.execute(
            select(AuditPlan.audit_category).where(AuditPlan.audit_id == finding.audit_id)
        )
        audit_category = plan_result.scalar_one_or_none()
        if audit_category == "customer" and not finding.customer_confirmed:
            raise ValueError("customer confirmation is required before closing customer audit finding")

        finding.status = "closed"
        finding.closed_at = datetime.now(timezone.utc)

    else:
        raise ValueError(f"invalid action: {action}")

    # Handle customer confirmation fields
    if customer_confirmed is not None:
        finding.customer_confirmed = customer_confirmed
    if customer_confirmation_date is not None:
        finding.customer_confirmation_date = customer_confirmation_date
    if customer_confirmation_attachments is not None:
        finding.customer_confirmation_attachments = customer_confirmation_attachments

    audit_log = AuditLog(
        table_name="audit_findings",
        record_id=finding.finding_id,
        action="TRANSITION",
        changed_fields={
            "status": {"before": old_status, "after": finding.status},
            "action": action,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    await db.commit()
    await db.refresh(finding)
    return finding


async def customer_confirm_finding(
    db: AsyncSession,
    finding: AuditFinding,
    *,
    confirmation_date: date,
    attachments: list,
    user_id: uuid.UUID,
) -> AuditFinding:
    """Mark a finding as customer-confirmed without changing its workflow status."""
    finding.customer_confirmed = True
    finding.customer_confirmation_date = confirmation_date
    finding.customer_confirmation_attachments = attachments

    audit_log = AuditLog(
        table_name="audit_findings",
        record_id=finding.finding_id,
        action="CUSTOMER_CONFIRM",
        changed_fields={
            "customer_confirmed": {"before": False, "after": True},
            "customer_confirmation_date": confirmation_date.isoformat(),
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    await db.commit()
    await db.refresh(finding)
    return finding


async def get_customer_audit_stats(db: AsyncSession) -> dict:
    base = select(AuditPlan).where(AuditPlan.audit_category == "customer")

    total_result = await db.execute(
        select(func.count()).select_from(AuditPlan).where(AuditPlan.audit_category == "customer")
    )
    total = total_result.scalar() or 0

    planned_result = await db.execute(
        select(func.count()).select_from(AuditPlan).where(
            and_(AuditPlan.audit_category == "customer", AuditPlan.status == "planned")
        )
    )
    planned = planned_result.scalar() or 0

    in_progress_result = await db.execute(
        select(func.count()).select_from(AuditPlan).where(
            and_(AuditPlan.audit_category == "customer", AuditPlan.status == "in_progress")
        )
    )
    in_progress = in_progress_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count()).select_from(AuditPlan).where(
            and_(AuditPlan.audit_category == "customer", AuditPlan.status == "completed")
        )
    )
    completed = completed_result.scalar() or 0

    # Findings stats via JOIN
    open_findings_result = await db.execute(
        select(func.count())
        .select_from(AuditFinding)
        .join(AuditPlan, AuditFinding.audit_id == AuditPlan.audit_id)
        .where(
            and_(
                AuditPlan.audit_category == "customer",
                AuditFinding.status.in_(["open", "in_progress"]),
            )
        )
    )
    open_findings = open_findings_result.scalar() or 0

    major_nc_result = await db.execute(
        select(func.count())
        .select_from(AuditFinding)
        .join(AuditPlan, AuditFinding.audit_id == AuditPlan.audit_id)
        .where(
            and_(
                AuditPlan.audit_category == "customer",
                AuditFinding.finding_type == "major_nc",
                AuditFinding.status.in_(["open", "in_progress"]),
            )
        )
    )
    major_nc = major_nc_result.scalar() or 0

    confirmed_result = await db.execute(
        select(func.count())
        .select_from(AuditFinding)
        .join(AuditPlan, AuditFinding.audit_id == AuditPlan.audit_id)
        .where(
            and_(
                AuditPlan.audit_category == "customer",
                AuditFinding.customer_confirmed == True,
            )
        )
    )
    confirmed = confirmed_result.scalar() or 0

    pending_result = await db.execute(
        select(func.count())
        .select_from(AuditFinding)
        .join(AuditPlan, AuditFinding.audit_id == AuditPlan.audit_id)
        .where(
            and_(
                AuditPlan.audit_category == "customer",
                AuditFinding.customer_confirmed == False,
                AuditFinding.status.in_(["open", "in_progress"]),
            )
        )
    )
    pending = pending_result.scalar() or 0

    return {
        "total_customer_audits": total,
        "planned": planned,
        "in_progress": in_progress,
        "completed": completed,
        "open_findings": open_findings,
        "major_nc_count": major_nc,
        "customer_confirmed_count": confirmed,
        "pending_confirmation_count": pending,
    }
```

- [ ] **Step 2: Verify service loads**

Run: `cd backend && python -c "from app.services.customer_audit_service import *; print('Service OK')"`
Expected: `Service OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/customer_audit_service.py
git commit -m "feat(service): add customer audit service with transition and confirmation logic"
```

---

### Task 5: Customer Audit API Routes

**Files:**
- Modify: `backend/app/api/audit_plan.py` (add customer-specific filters and customer-confirm endpoint)
- Modify: `backend/app/api/audit_finding.py` (add transition endpoint, customer-confirm endpoint)
- Modify: `backend/app/main.py` (no new router needed — routes go on existing routers)

- [ ] **Step 1: Add customer fields to audit plan creation in audit_plan.py**

In `backend/app/api/audit_plan.py`, update the `create_audit_plan` function (line 48) to pass the new customer fields through to the service. Replace the function:

```python
@router.post("", response_model=schemas.audit.AuditPlanResponse)
async def create_audit_plan(
    req: schemas.audit.AuditPlanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        if req.audit_category == "customer":
            from app.services import customer_audit_service
            plan = await customer_audit_service.create_customer_audit(
                db,
                audit_scope=req.audit_scope,
                audit_criteria=req.audit_criteria,
                planned_date=req.planned_date,
                customer_name=req.customer_name or "",
                customer_type=req.customer_type or "",
                audit_mode=req.audit_mode,
                lead_auditor=req.lead_auditor,
                team_members=req.team_members,
                checklist=req.checklist,
                product_line_code=req.product_line_code,
                user_id=user.user_id,
            )
        else:
            plan = await audit_service.create_audit_plan(
                db,
                program_id=req.program_id,
                audit_scope=req.audit_scope,
                audit_criteria=req.audit_criteria,
                planned_date=req.planned_date,
                lead_auditor=req.lead_auditor,
                team_members=req.team_members,
                checklist=req.checklist,
                user_id=user.user_id,
                product_line_code=req.product_line_code,
            )
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 2: Add customer-stats and customer-confirm routes to audit_plan.py**

Add these routes. The `/customer-stats` route MUST be registered BEFORE the `/{audit_id}` route to avoid 422 conflicts. Insert after the `list_audit_plans` function (after line 45) and before `create_audit_plan`:

```python
@router.get("/customer-stats", response_model=schemas.audit.CustomerAuditStatsResponse)
async def get_customer_audit_stats(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    from app.services import customer_audit_service
    stats = await customer_audit_service.get_customer_audit_stats(db)
    return schemas.audit.CustomerAuditStatsResponse(**stats)
```

Add this route after the `cancel_audit_plan` function:

```python
@router.put("/{audit_id}/customer-confirm")
async def confirm_customer_audit(
    audit_id: uuid.UUID,
    req: schemas.audit.CustomerConfirmationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    if plan.audit_category != "customer":
        raise HTTPException(status_code=400, detail="not a customer audit")

    plan.customer_confirmation_doc = [
        a.model_dump() for a in req.attachments
    ] if req.attachments else []

    from app.models.audit import AuditLog
    audit_log = AuditLog(
        table_name="audit_plans",
        record_id=audit_id,
        action="CUSTOMER_CONFIRM",
        changed_fields={"customer_confirmation_date": req.confirmation_date.isoformat()},
        operated_by=user.user_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(plan)
    return schemas.audit.AuditPlanResponse.model_validate(plan)
```

- [ ] **Step 3: Add transition and customer-confirm routes to audit_finding.py**

In `backend/app/api/audit_finding.py`, add these new routes. Insert BEFORE the existing `/{finding_id}` GET route (line 58) to avoid routing conflicts, or append after `create_capa_from_finding`:

```python
@router.post("/{finding_id}/transition", response_model=schemas.audit.AuditFindingResponse)
async def transition_audit_finding(
    finding_id: uuid.UUID,
    req: schemas.audit.FindingTransitionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    finding = await audit_service.get_audit_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="audit finding not found")
    try:
        from app.services import customer_audit_service
        finding = await customer_audit_service.transition_finding(
            db,
            finding,
            action=req.action,
            user_id=user.user_id,
            customer_confirmed=req.customer_confirmed,
            customer_confirmation_date=req.customer_confirmation_date,
            customer_confirmation_attachments=req.customer_confirmation_attachments,
        )
        return schemas.audit.AuditFindingResponse.model_validate(finding)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{finding_id}/customer-confirm", response_model=schemas.audit.AuditFindingResponse)
async def confirm_customer_finding(
    finding_id: uuid.UUID,
    req: schemas.audit.CustomerConfirmationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    finding = await audit_service.get_audit_finding(db, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="audit finding not found")
    try:
        from app.services import customer_audit_service
        finding = await customer_audit_service.customer_confirm_finding(
            db,
            finding,
            confirmation_date=req.confirmation_date,
            attachments=[a.model_dump() for a in req.attachments] if req.attachments else [],
            user_id=user.user_id,
        )
        return schemas.audit.AuditFindingResponse.model_validate(finding)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 4: Verify backend starts**

Run: `cd backend && python -c "from app.main import app; print('App OK')"`
Expected: `App OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/audit_plan.py backend/app/api/audit_finding.py
git commit -m "feat(api): add customer audit routes, transition API, and customer confirmation"
```

---

### Task 6: Frontend TypeScript Types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Extend AuditPlan interface**

In `frontend/src/types/index.ts`, update the `AuditPlan` interface (line 251) to add customer fields:

```typescript
export interface AuditPlan {
  audit_id: string;
  plan_no: string;
  program_id: string;
  audit_scope: string;
  audit_criteria: string;
  planned_date: string;
  actual_date: string | null;
  lead_auditor: string | null;
  team_members: { user_id: string; username: string }[];
  checklist: AuditChecklistItem[];
  status: "planned" | "in_progress" | "completed" | "cancelled";
  product_line_code?: string;
  audit_category: string;
  customer_name?: string;
  customer_type?: string;
  audit_mode?: string;
  customer_confirmation_doc?: CustomerAuditAttachment[];
  created_by: string;
  created_at: string;
}
```

Update `AuditFinding` interface (line 268) to add customer fields:

```typescript
export interface AuditFinding {
  finding_id: string;
  audit_id: string;
  clause_ref: string | null;
  finding_type: "major_nc" | "minor_nc" | "ofi" | "observation";
  description: string;
  root_cause: string | null;
  correction: string | null;
  corrective_action: string | null;
  capa_ref_id: string | null;
  status: "open" | "in_progress" | "verified" | "closed";
  due_date: string | null;
  closed_at: string | null;
  customer_confirmed: boolean;
  customer_confirmation_date: string | null;
  customer_confirmation_attachments: CustomerAuditAttachment[];
  created_by: string | null;
  created_at: string;
}
```

Add new interfaces after the existing `AuditStats` interface (around line 318):

```typescript
export interface CustomerAuditAttachment {
  file_name: string;
  file_url: string;
  file_size?: number;
  file_type?: string;
  uploaded_at?: string;
  uploaded_by?: string;
}

export interface CustomerAuditStats {
  total_customer_audits: number;
  planned: number;
  in_progress: number;
  completed: number;
  open_findings: number;
  major_nc_count: number;
  customer_confirmed_count: number;
  pending_confirmation_count: number;
}

export interface FindingTransitionRequest {
  action: "start_progress" | "close";
  customer_confirmed?: boolean;
  customer_confirmation_date?: string;
  customer_confirmation_attachments?: CustomerAuditAttachment[];
}

export interface CustomerConfirmationRequest {
  confirmation_date: string;
  attachments?: CustomerAuditAttachment[];
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors (or pre-existing errors only)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add customer audit TypeScript interfaces"
```

---

### Task 7: Frontend API Client

**Files:**
- Modify: `frontend/src/api/audit.ts`

- [ ] **Step 1: Add customer audit API functions**

Append these functions at the end of `frontend/src/api/audit.ts` (after line 110):

```typescript
// ── Customer Audit API ──

export async function getCustomerAuditStats(): Promise<CustomerAuditStats> {
  const resp = await client.get("/audit-plans/customer-stats");
  return resp.data;
}

export async function listCustomerAudits(params?: Record<string, unknown>): Promise<AuditPlanListResponse> {
  const resp = await client.get("/audit-plans", { params: { audit_category: "customer", ...params } });
  return resp.data;
}

export async function createCustomerAudit(data: {
  audit_scope: string;
  audit_criteria: string;
  planned_date: string;
  customer_name: string;
  customer_type: string;
  audit_mode?: string;
  lead_auditor?: string;
  team_members?: { user_id: string; username: string }[];
  checklist?: AuditChecklistItem[];
  product_line_code?: string;
  program_id: string;
}): Promise<AuditPlan> {
  const resp = await client.post("/audit-plans", { audit_category: "customer", ...data });
  return resp.data;
}

export async function updateCustomerAudit(id: string, data: Partial<AuditPlan>): Promise<AuditPlan> {
  const resp = await client.put(`/audit-plans/${id}`, data);
  return resp.data;
}

export async function confirmCustomerAudit(
  id: string,
  data: CustomerConfirmationRequest
): Promise<AuditPlan> {
  const resp = await client.put(`/audit-plans/${id}/customer-confirm`, data);
  return resp.data;
}

export async function transitionFinding(
  id: string,
  data: FindingTransitionRequest
): Promise<AuditFinding> {
  const resp = await client.post(`/audit-findings/${id}/transition`, data);
  return resp.data;
}

export async function confirmCustomerFinding(
  id: string,
  data: CustomerConfirmationRequest
): Promise<AuditFinding> {
  const resp = await client.post(`/audit-findings/${id}/customer-confirm`, data);
  return resp.data;
}
```

Update the import at the top (line 2) to include the new types:

```typescript
import type {
  AuditProgram, AuditPlan, AuditFinding,
  AuditProgramListResponse, AuditPlanListResponse, AuditFindingListResponse,
  AuditStats, AuditChecklistItem, User,
  CustomerAuditStats, CustomerConfirmationRequest, FindingTransitionRequest,
} from "../types";
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/audit.ts
git commit -m "feat(api-client): add customer audit frontend API functions"
```

---

### Task 8: Customer Audit List Page

**Files:**
- Create: `frontend/src/pages/customerAudit/CustomerAuditListPage.tsx`

- [ ] **Step 1: Create the list page**

Create directory `frontend/src/pages/customerAudit/` and the page file following the InternalAuditListPage pattern:

```tsx
import { useState, useEffect, useCallback } from "react";
import {
  Card, Table, Button, Tag, Space, Modal, Form, Input, Select,
  DatePicker, App, Row, Col, Statistic,
} from "antd";
import { PlusOutlined, ReloadOutlined, EyeOutlined, PlayCircleOutlined, CheckCircleOutlined, StopOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { useProductLineStore } from "../../store/productLineStore";
import type { AuditPlan, CustomerAuditStats } from "../../types";
import {
  listCustomerAudits, createCustomerAudit, getCustomerAuditStats,
  startAuditPlan, completeAuditPlan, cancelAuditPlan,
} from "../../api/audit";
import { listAuditPrograms } from "../../api/audit";
import { listUsers } from "../../api/auth";
import dayjs from "dayjs";

const { Option } = Select;

const statusLabel: Record<string, string> = {
  planned: "已计划", in_progress: "进行中", completed: "已完成", cancelled: "已取消",
};
const statusColor: Record<string, string> = {
  planned: "blue", in_progress: "processing", completed: "success", cancelled: "default",
};
const customerTypeLabel: Record<string, string> = {
  OEM: "OEM", "Tier 1": "Tier 1", "Tier 2": "Tier 2", 其他: "其他",
};
const auditModeLabel: Record<string, string> = {
  on_site: "现场", remote: "远程",
};

export default function CustomerAuditListPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { currentProductLine } = useProductLineStore();
  const isViewer = user?.role === "viewer";
  const isManager = user?.role === "admin" || user?.role === "manager";

  const [audits, setAudits] = useState<AuditPlan[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<CustomerAuditStats | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm();
  const [users, setUsers] = useState<{ user_id: string; username: string }[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [auditsResp, statsResp] = await Promise.all([
        listCustomerAudits({ page, page_size: 20, product_line_code: currentProductLine }),
        getCustomerAuditStats(),
      ]);
      setAudits(auditsResp.items);
      setTotal(auditsResp.total);
      setStats(statsResp);
    } catch {
      message.error("加载失败");
    } finally {
      setLoading(false);
    }
  }, [page, currentProductLine]);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    listUsers().then((r) => setUsers(r.items || r)).catch(() => {});
  }, []);

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      const defaultProgram = (await listAuditPrograms({ status: "active" })).items[0];
      await createCustomerAudit({
        ...values,
        planned_date: values.planned_date.format("YYYY-MM-DD"),
        product_line_code: currentProductLine,
        program_id: defaultProgram?.program_id || "",
      });
      message.success("创建成功");
      setCreateOpen(false);
      form.resetFields();
      fetchData();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message || "创建失败");
    }
  };

  const handleAction = async (action: string, id: string) => {
    try {
      if (action === "start") await startAuditPlan(id);
      else if (action === "complete") await completeAuditPlan(id);
      else if (action === "cancel") await cancelAuditPlan(id);
      message.success("操作成功");
      fetchData();
    } catch (e: unknown) {
      message.error((e as Error).message || "操作失败");
    }
  };

  const columns = [
    { title: "编号", dataIndex: "plan_no", key: "plan_no", width: 130 },
    { title: "客户名称", dataIndex: "customer_name", key: "customer_name", width: 120 },
    { title: "客户类型", dataIndex: "customer_type", key: "customer_type", width: 90,
      render: (v: string) => customerTypeLabel[v] || v },
    { title: "审核方式", dataIndex: "audit_mode", key: "audit_mode", width: 80,
      render: (v: string) => v ? auditModeLabel[v] || v : "-" },
    { title: "审核范围", dataIndex: "audit_scope", key: "audit_scope", ellipsis: true },
    { title: "计划日期", dataIndex: "planned_date", key: "planned_date", width: 110,
      render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD") : "-" },
    { title: "状态", dataIndex: "status", key: "status", width: 90,
      render: (v: string) => <Tag color={statusColor[v]}>{statusLabel[v]}</Tag> },
    {
      title: "操作", key: "actions", width: 180,
      render: (_: unknown, record: AuditPlan) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => navigate(`/customer-audits/${record.audit_id}`)}>查看</Button>
          {record.status === "planned" && !isViewer && (
            <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => handleAction("start", record.audit_id)}>开始</Button>
          )}
          {record.status === "in_progress" && isManager && (
            <>
              <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => handleAction("complete", record.audit_id)}>完成</Button>
              <Button size="small" danger icon={<StopOutlined />} onClick={() => handleAction("cancel", record.audit_id)}>取消</Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={3}><Card><Statistic title="总计" value={stats?.total_customer_audits ?? 0} /></Card></Col>
        <Col span={3}><Card><Statistic title="已计划" value={stats?.planned ?? 0} valueStyle={{ color: "#1890ff" }} /></Card></Col>
        <Col span={3}><Card><Statistic title="进行中" value={stats?.in_progress ?? 0} valueStyle={{ color: "#faad14" }} /></Card></Col>
        <Col span={3}><Card><Statistic title="已完成" value={stats?.completed ?? 0} valueStyle={{ color: "#52c41a" }} /></Card></Col>
        <Col span={3}><Card><Statistic title="未关闭发现项" value={stats?.open_findings ?? 0} valueStyle={{ color: "#ff4d4f" }} /></Card></Col>
        <Col span={3}><Card><Statistic title="严重不符合" value={stats?.major_nc_count ?? 0} valueStyle={{ color: "#ff4d4f" }} /></Card></Col>
        <Col span={3}><Card><Statistic title="已确认" value={stats?.customer_confirmed_count ?? 0} valueStyle={{ color: "#52c41a" }} /></Card></Col>
        <Col span={3}><Card><Statistic title="待确认" value={stats?.pending_confirmation_count ?? 0} valueStyle={{ color: "#faad14" }} /></Card></Col>
      </Row>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>客户审核管理</h3>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
            {!isViewer && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建客户审核</Button>
            )}
          </Space>
        </div>

        <Table
          rowKey="audit_id"
          columns={columns}
          dataSource={audits}
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: setPage,
            showTotal: (t) => `共 ${t} 条`,
          }}
        />
      </Card>

      <Modal
        title="新建客户审核"
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateOpen(false); form.resetFields(); }}
        width={640}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="customer_name" label="客户名称" rules={[{ required: true, message: "请输入客户名称" }]}>
            <Input placeholder="如 Tesla、BYD" />
          </Form.Item>
          <Form.Item name="customer_type" label="客户类型" rules={[{ required: true, message: "请选择客户类型" }]}>
            <Select placeholder="选择客户类型">
              <Option value="OEM">OEM</Option>
              <Option value="Tier 1">Tier 1</Option>
              <Option value="Tier 2">Tier 2</Option>
              <Option value="其他">其他</Option>
            </Select>
          </Form.Item>
          <Form.Item name="audit_mode" label="审核方式">
            <Select placeholder="选择审核方式" allowClear>
              <Option value="on_site">现场</Option>
              <Option value="remote">远程</Option>
            </Select>
          </Form.Item>
          <Form.Item name="audit_scope" label="审核范围" rules={[{ required: true, message: "请输入审核范围" }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="audit_criteria" label="审核准则" rules={[{ required: true, message: "请输入审核准则" }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="planned_date" label="计划日期" rules={[{ required: true, message: "请选择日期" }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="lead_auditor" label="审核组长">
            <Select placeholder="选择审核组长" allowClear>
              {users.map((u) => (
                <Option key={u.user_id} value={u.user_id}>{u.username}</Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/customerAudit/CustomerAuditListPage.tsx
git commit -m "feat(frontend): add customer audit list page with stats cards"
```

---

### Task 9: Customer Audit Detail Page

**Files:**
- Create: `frontend/src/pages/customerAudit/CustomerAuditDetailPage.tsx`

- [ ] **Step 1: Create the detail page**

```tsx
import { useState, useEffect, useCallback } from "react";
import {
  Card, Button, Tag, Space, Form, Input, Select, DatePicker, App,
  Tabs, Table, Modal, Popconfirm, Row, Col, Statistic, Descriptions,
  Upload, Typography,
} from "antd";
import {
  ArrowLeftOutlined, PlayCircleOutlined, CheckCircleOutlined, StopOutlined,
  PlusOutlined, DeleteOutlined, LinkOutlined, CheckOutlined, UploadOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import type { AuditPlan, AuditFinding, User } from "../../types";
import {
  getAuditPlan, startAuditPlan, completeAuditPlan, cancelAuditPlan,
  listAuditFindings, createAuditFinding, updateAuditFinding,
  createCAPAFromFinding, transitionFinding, confirmCustomerFinding,
  confirmCustomerAudit,
} from "../../api/audit";
import { listUsers } from "../../api/auth";
import dayjs from "dayjs";

const { Option } = Select;
const { Text } = Typography;

const statusLabel: Record<string, string> = {
  planned: "已计划", in_progress: "进行中", completed: "已完成", cancelled: "已取消",
};
const statusColor: Record<string, string> = {
  planned: "blue", in_progress: "processing", completed: "success", cancelled: "default",
};
const findingStatusLabel: Record<string, string> = {
  open: "已开立", in_progress: "整改中", closed: "已关闭", verified: "已验证",
};
const findingStatusColor: Record<string, string> = {
  open: "error", in_progress: "processing", closed: "success", verified: "success",
};
const findingTypeLabel: Record<string, string> = {
  major_nc: "严重不符合", minor_nc: "一般不符合", ofi: "改进机会", observation: "观察项",
};
const auditModeLabel: Record<string, string> = { on_site: "现场", remote: "远程" };

export default function CustomerAuditDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const isViewer = user?.role === "viewer";
  const isManager = user?.role === "admin" || user?.role === "manager";

  const [plan, setPlan] = useState<AuditPlan | null>(null);
  const [findings, setFindings] = useState<AuditFinding[]>([]);
  const [loading, setLoading] = useState(false);
  const [findingModalOpen, setFindingModalOpen] = useState(false);
  const [editingFinding, setEditingFinding] = useState<AuditFinding | null>(null);
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [confirmFindingId, setConfirmFindingId] = useState<string | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [findingForm] = Form.useForm();
  const [confirmForm] = Form.useForm();

  const fetchPlan = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [p, f] = await Promise.all([
        getAuditPlan(id),
        listAuditFindings({ audit_id: id, page_size: 1000 }),
      ]);
      setPlan(p);
      setFindings(f.items);
    } catch {
      message.error("加载失败");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { fetchPlan(); }, [fetchPlan]);
  useEffect(() => { listUsers().then((r) => setUsers(r.items || r)).catch(() => {}); }, []);

  const handlePlanAction = async (action: string) => {
    if (!id) return;
    try {
      if (action === "start") await startAuditPlan(id);
      else if (action === "complete") await completeAuditPlan(id);
      else if (action === "cancel") await cancelAuditPlan(id);
      message.success("操作成功");
      fetchPlan();
    } catch (e: unknown) {
      message.error((e as Error).message || "操作失败");
    }
  };

  const handleCreateFinding = async () => {
    try {
      const values = await findingForm.validateFields();
      if (editingFinding) {
        await updateAuditFinding(editingFinding.finding_id, values);
        message.success("更新成功");
      } else {
        await createAuditFinding({ ...values, audit_id: id });
        message.success("创建成功");
      }
      setFindingModalOpen(false);
      findingForm.resetFields();
      setEditingFinding(null);
      fetchPlan();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message || "操作失败");
    }
  };

  const handleTransition = async (findingId: string, action: string) => {
    try {
      await transitionFinding(findingId, { action });
      message.success("操作成功");
      fetchPlan();
    } catch (e: unknown) {
      message.error((e as Error).message || "操作失败");
    }
  };

  const handleCustomerConfirm = async () => {
    try {
      const values = await confirmForm.validateFields();
      const date = values.confirmation_date.format("YYYY-MM-DD");
      if (confirmFindingId) {
        await confirmCustomerFinding(confirmFindingId, {
          confirmation_date: date,
          attachments: [],
        });
      }
      message.success("确认成功");
      setConfirmModalOpen(false);
      confirmForm.resetFields();
      setConfirmFindingId(null);
      fetchPlan();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message || "确认失败");
    }
  };

  const handlePlanConfirm = async () => {
    if (!id) return;
    try {
      await confirmCustomerAudit(id, { confirmation_date: dayjs().format("YYYY-MM-DD"), attachments: [] });
      message.success("审核确认成功");
      fetchPlan();
    } catch (e: unknown) {
      message.error((e as Error).message || "确认失败");
    }
  };

  const openEditFinding = (f: AuditFinding) => {
    setEditingFinding(f);
    findingForm.setFieldsValue({
      clause_ref: f.clause_ref,
      finding_type: f.finding_type,
      description: f.description,
      root_cause: f.root_cause,
      correction: f.correction,
      corrective_action: f.corrective_action,
      due_date: f.due_date ? dayjs(f.due_date) : undefined,
    });
    setFindingModalOpen(true);
  };

  const findingColumns = [
    { title: "条款", dataIndex: "clause_ref", key: "clause_ref", width: 100, render: (v: string) => v || "-" },
    { title: "类型", dataIndex: "finding_type", key: "finding_type", width: 110,
      render: (v: string) => findingTypeLabel[v] || v },
    { title: "描述", dataIndex: "description", key: "description", ellipsis: true },
    { title: "根本原因", dataIndex: "root_cause", key: "root_cause", ellipsis: true, render: (v: string) => v || "-" },
    { title: "纠正措施", dataIndex: "corrective_action", key: "corrective_action", ellipsis: true, render: (v: string) => v || "-" },
    { title: "状态", dataIndex: "status", key: "status", width: 90,
      render: (v: string) => <Tag color={findingStatusColor[v]}>{findingStatusLabel[v]}</Tag> },
    { title: "客户确认", dataIndex: "customer_confirmed", key: "customer_confirmed", width: 90,
      render: (v: boolean) => v ? <Tag color="success">已确认</Tag> : <Tag color="warning">待确认</Tag> },
    { title: "CAPA", dataIndex: "capa_ref_id", key: "capa_ref_id", width: 80,
      render: (v: string) => v ? <Tag color="blue" style={{ cursor: "pointer" }} onClick={() => navigate(`/capa/${v}`)}>查看</Tag> : "-" },
    {
      title: "操作", key: "finding_actions", width: 280,
      render: (_: unknown, record: AuditFinding) => (
        <Space size="small">
          {!isViewer && <Button size="small" onClick={() => openEditFinding(record)}>编辑</Button>}
          {record.status === "open" && !isViewer && (
            <Button size="small" type="default" onClick={() => handleTransition(record.finding_id, "start_progress")}>开始整改</Button>
          )}
          {record.status === "in_progress" && !isViewer && (
            <Popconfirm title="确认关闭？需满足所有关闭条件" onConfirm={() => handleTransition(record.finding_id, "close")}>
              <Button size="small" type="primary">关闭</Button>
            </Popconfirm>
          )}
          {!record.customer_confirmed && !isViewer && (
            <Button size="small" icon={<CheckOutlined />}
              onClick={() => { setConfirmFindingId(record.finding_id); setConfirmModalOpen(true); }}>
              客户确认
            </Button>
          )}
          {!record.capa_ref_id && !isViewer && record.finding_type === "major_nc" && (
            <Popconfirm title="是否创建 CAPA？" onConfirm={async () => {
              try { await createCAPAFromFinding(record.finding_id); message.success("CAPA 已创建"); fetchPlan(); }
              catch (e: unknown) { message.error((e as Error).message || "创建失败"); }
            }}>
              <Button size="small" icon={<LinkOutlined />}>CAPA</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  if (!plan) return null;

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/customer-audits")}>返回列表</Button>
      </div>

      <Card loading={loading}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>{plan.plan_no} - {plan.customer_name}</h3>
          <Space>
            {plan.status === "planned" && !isViewer && (
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => handlePlanAction("start")}>开始审核</Button>
            )}
            {plan.status === "in_progress" && isManager && (
              <>
                <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => handlePlanAction("complete")}>完成审核</Button>
                <Button danger icon={<StopOutlined />} onClick={() => handlePlanAction("cancel")}>取消</Button>
              </>
            )}
            <Tag color={statusColor[plan.status]} style={{ fontSize: 14, padding: "4px 12px" }}>
              {statusLabel[plan.status]}
            </Tag>
          </Space>
        </div>

        <Descriptions column={3} bordered size="small">
          <Descriptions.Item label="客户名称">{plan.customer_name}</Descriptions.Item>
          <Descriptions.Item label="客户类型">{plan.customer_type}</Descriptions.Item>
          <Descriptions.Item label="审核方式">{plan.audit_mode ? auditModeLabel[plan.audit_mode] : "-"}</Descriptions.Item>
          <Descriptions.Item label="审核范围" span={2}>{plan.audit_scope}</Descriptions.Item>
          <Descriptions.Item label="计划日期">{plan.planned_date}</Descriptions.Item>
          <Descriptions.Item label="审核准则" span={3}>{plan.audit_criteria}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card style={{ marginTop: 16 }}>
        <Tabs items={[
          {
            key: "findings",
            label: `发现项 (${findings.length})`,
            children: (
              <>
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
                  {!isViewer && (
                    <Button type="primary" icon={<PlusOutlined />}
                      onClick={() => { setEditingFinding(null); findingForm.resetFields(); setFindingModalOpen(true); }}>
                      新增发现项
                    </Button>
                  )}
                </div>
                <Table
                  rowKey="finding_id"
                  columns={findingColumns}
                  dataSource={findings}
                  pagination={false}
                  size="small"
                  scroll={{ x: 1200 }}
                />
              </>
            ),
          },
          {
            key: "confirmation",
            label: "确认凭证",
            children: (
              <div>
                <Row gutter={16}>
                  <Col span={8}>
                    <Statistic
                      title="已确认发现项"
                      value={findings.filter((f) => f.customer_confirmed).length}
                      suffix={`/ ${findings.length}`}
                      valueStyle={{ color: "#52c41a" }}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="待确认发现项"
                      value={findings.filter((f) => !f.customer_confirmed && f.status !== "closed").length}
                      valueStyle={{ color: "#faad14" }}
                    />
                  </Col>
                  <Col span={8}>
                    <div style={{ marginTop: 32 }}>
                      {!isViewer && (
                        <Button type="primary" icon={<UploadOutlined />} onClick={handlePlanConfirm}>
                          上传审核级确认函
                        </Button>
                      )}
                    </div>
                  </Col>
                </Row>
                {plan.customer_confirmation_doc && plan.customer_confirmation_doc.length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <Text strong>审核确认附件：</Text>
                    <ul>
                      {plan.customer_confirmation_doc.map((a, i) => (
                        <li key={i}>{a.file_name}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ),
          },
        ]} />
      </Card>

      {/* Create/Edit Finding Modal */}
      <Modal
        title={editingFinding ? "编辑发现项" : "新增发现项"}
        open={findingModalOpen}
        onOk={handleCreateFinding}
        onCancel={() => { setFindingModalOpen(false); findingForm.resetFields(); setEditingFinding(null); }}
        width={640}
      >
        <Form form={findingForm} layout="vertical">
          <Form.Item name="finding_type" label="发现类型" rules={[{ required: true }]}>
            <Select>
              <Option value="major_nc">严重不符合</Option>
              <Option value="minor_nc">一般不符合</Option>
              <Option value="ofi">改进机会</Option>
              <Option value="observation">观察项</Option>
            </Select>
          </Form.Item>
          <Form.Item name="clause_ref" label="条款号">
            <Input placeholder="如 8.5.1" />
          </Form.Item>
          <Form.Item name="description" label="不符合描述" rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="root_cause" label="根本原因">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="correction" label="纠正">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="corrective_action" label="纠正措施">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="due_date" label="截止日期">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Customer Confirm Modal */}
      <Modal
        title="客户确认整改完成"
        open={confirmModalOpen}
        onOk={handleCustomerConfirm}
        onCancel={() => { setConfirmModalOpen(false); confirmForm.resetFields(); setConfirmFindingId(null); }}
      >
        <Form form={confirmForm} layout="vertical">
          <Form.Item name="confirmation_date" label="确认日期" rules={[{ required: true }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/customerAudit/CustomerAuditDetailPage.tsx
git commit -m "feat(frontend): add customer audit detail page with findings and confirmation"
```

---

### Task 10: Routes and Sidebar Registration

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Add routes to App.tsx**

In `frontend/src/App.tsx`, add imports (near line 30 where other page imports are):

```typescript
import CustomerAuditListPage from "./pages/customerAudit/CustomerAuditListPage";
import CustomerAuditDetailPage from "./pages/customerAudit/CustomerAuditDetailPage";
```

Add routes (after the internal-audits routes, around line 88):

```tsx
<Route path="/customer-audits" element={<CustomerAuditListPage />} />
<Route path="/customer-audits/:id" element={<CustomerAuditDetailPage />} />
```

- [ ] **Step 2: Add sidebar menu item to AppLayout.tsx**

In `frontend/src/components/layout/AppLayout.tsx`, add the customer audit menu item. Insert after the "内部审核" entry (line 37):

```typescript
{ key: "/customer-audits", icon: <AuditOutlined />, label: "客户审核" },
```

If `AuditOutlined` is not already imported from `@ant-design/icons`, add it to the import.

- [ ] **Step 3: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No new errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(frontend): add customer audit routes and sidebar menu item"
```

---

### Task 11: Integration Verification

- [ ] **Step 1: Start backend and run migration**

Run:
```bash
cd backend && alembic upgrade head
```
Expected: Migration 021 applied successfully

- [ ] **Step 2: Verify backend starts cleanly**

Run:
```bash
cd backend && python -c "from app.main import app; print('App OK')"
```
Expected: `App OK`

- [ ] **Step 3: Verify frontend builds**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds with no new errors

- [ ] **Step 4: Start dev servers and test manually**

Run `docker compose up` or start backend/frontend separately. Login and verify:
1. Sidebar shows "客户审核" menu item
2. Customer audit list page loads with empty stats
3. Create a new customer audit (fill customer name, type, scope, criteria, date)
4. View detail page, add a finding
5. Transition finding through open → in_progress → close flow
6. Verify customer confirmation modal works

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A && git commit -m "fix(customer-audit): integration fixes after manual testing"
```
