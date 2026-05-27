# APQP 项目质量策划 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the AIAG five-phase APQP module with gate approval workflow and cross-module links (DFMEA, PFMEA, Control Plan, PPAP).

**Architecture:** Follows the SCAR module pattern exactly — flat table with state machine, async service layer with AuditLog, manual `_to_response()` mapping in API routes, and React pages with useState + Ant Design. Code placed alongside existing modules in `backend/app/` and `frontend/src/`.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 | React 18 + TypeScript 5.6 + Ant Design 5.21

**Spec:** `docs/superpowers/specs/2026-05-27-apqp-module-design.md`

---

### Task 1: Backend Model

**Files:**
- Create: `backend/app/models/apqp.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the APQP model file**

```python
# backend/app/models/apqp.py
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class APQPProject(Base):
    __tablename__ = "apqp_projects"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_line_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("product_lines.code"), nullable=False
    )
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_sop_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    team_members: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Phase management
    current_phase: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    phase_status: Mapped[str | None] = mapped_column(String(20), default="in_progress", nullable=True)
    project_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    # Phase completion timestamps
    phase_1_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_2_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_3_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_4_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_5_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Gate info (latest approval)
    gate_approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    gate_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gate_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate_history: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Cross-module links
    dfmea_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id", ondelete="SET NULL"), nullable=True
    )
    pfmea_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id", ondelete="SET NULL"), nullable=True
    )
    control_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_plans.cp_id", ondelete="SET NULL"), nullable=True
    )
    ppap_submission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_ppap_submissions.submission_id", ondelete="SET NULL"), nullable=True
    )

    # Audit
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    gate_approver = relationship("User", foreign_keys=[gate_approved_by])
    dfmea = relationship("FMEADocument", foreign_keys=[dfmea_id])
    pfmea = relationship("FMEADocument", foreign_keys=[pfmea_id])
    control_plan = relationship("ControlPlan", foreign_keys=[control_plan_id])
    ppap_submission = relationship("SupplierPPAPSubmission", foreign_keys=[ppap_submission_id])
    product_line = relationship("ProductLine", foreign_keys=[product_line_code])
```

- [ ] **Step 2: Update models __init__.py**

In `backend/app/models/__init__.py`, add the import after the `customer_quality` import:

```python
from app.models.apqp import APQPProject
```

And add `"APQPProject"` to the `__all__` list after `"Customer", "CustomerComplaint", "RMARecord"`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/apqp.py backend/app/models/__init__.py
git commit -m "feat(apqp): add APQPProject ORM model"
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/023_add_apqp_projects.py`

- [ ] **Step 1: Create migration file**

```python
# backend/alembic/versions/023_add_apqp_projects.py
"""add apqp_projects table

Revision ID: 023_add_apqp_projects
Revises: 022_add_scar_capa
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "023_add_apqp_projects"
down_revision = "022_add_scar_capa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "apqp_projects",
        sa.Column("project_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_code", sa.String(30), unique=True, nullable=False),
        sa.Column("project_name", sa.String(200), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("product_line_code", sa.String(20), nullable=False),
        sa.Column("customer_name", sa.String(200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_sop_date", sa.Date(), nullable=True),
        sa.Column("team_members", JSONB(), nullable=True),
        sa.Column("current_phase", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("phase_status", sa.String(20), nullable=True, server_default="in_progress"),
        sa.Column("project_status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("phase_1_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_2_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_3_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_4_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_5_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gate_approved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("gate_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gate_comments", sa.Text(), nullable=True),
        sa.Column("gate_history", JSONB(), nullable=True),
        sa.Column("dfmea_id", UUID(as_uuid=True), nullable=True),
        sa.Column("pfmea_id", UUID(as_uuid=True), nullable=True),
        sa.Column("control_plan_id", UUID(as_uuid=True), nullable=True),
        sa.Column("ppap_submission_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indexes
    op.create_index("ix_apqp_projects_project_status", "apqp_projects", ["project_status"])
    op.create_index("ix_apqp_projects_current_phase", "apqp_projects", ["current_phase"])

    # Foreign keys
    op.create_foreign_key("fk_apqp_projects_product_line", "apqp_projects", "product_lines", ["product_line_code"], ["code"])
    op.create_foreign_key("fk_apqp_projects_gate_approved_by", "apqp_projects", "users", ["gate_approved_by"], ["user_id"])
    op.create_foreign_key("fk_apqp_projects_created_by", "apqp_projects", "users", ["created_by"], ["user_id"])
    op.create_foreign_key("fk_apqp_projects_dfmea_id", "apqp_projects", "fmea_documents", ["dfmea_id"], ["fmea_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_apqp_projects_pfmea_id", "apqp_projects", "fmea_documents", ["pfmea_id"], ["fmea_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_apqp_projects_control_plan_id", "apqp_projects", "control_plans", ["control_plan_id"], ["cp_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_apqp_projects_ppap_submission_id", "apqp_projects", "supplier_ppap_submissions", ["ppap_submission_id"], ["submission_id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_table("apqp_projects")
```

- [ ] **Step 2: Run migration**

```bash
cd backend && alembic upgrade head
```

Expected: migration runs successfully, `apqp_projects` table created.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/023_add_apqp_projects.py
git commit -m "feat(apqp): add apqp_projects migration"
```

---

### Task 3: Backend Schemas

**Files:**
- Create: `backend/app/schemas/apqp.py`

- [ ] **Step 1: Create schemas file**

```python
# backend/app/schemas/apqp.py
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class APQPProjectCreate(BaseModel):
    project_name: str
    product_name: str
    product_line_code: str
    customer_name: str | None = None
    description: str | None = None
    target_sop_date: date | None = None
    team_members: list[dict] | None = None
    dfmea_id: uuid.UUID | None = None
    pfmea_id: uuid.UUID | None = None
    control_plan_id: uuid.UUID | None = None
    ppap_submission_id: uuid.UUID | None = None


class APQPProjectUpdate(BaseModel):
    project_name: str | None = None
    product_name: str | None = None
    product_line_code: str | None = None
    customer_name: str | None = None
    description: str | None = None
    target_sop_date: date | None = None
    team_members: list[dict] | None = None
    dfmea_id: uuid.UUID | None = None
    pfmea_id: uuid.UUID | None = None
    control_plan_id: uuid.UUID | None = None
    ppap_submission_id: uuid.UUID | None = None


class APQPProjectResponse(BaseModel):
    project_id: uuid.UUID
    project_code: str
    project_name: str
    product_name: str
    product_line_code: str
    customer_name: str | None = None
    description: str | None = None
    target_sop_date: date | None = None
    team_members: list | None = None

    current_phase: int
    phase_name: str
    phase_status: str | None = None
    project_status: str

    phase_1_completed_at: datetime | None = None
    phase_2_completed_at: datetime | None = None
    phase_3_completed_at: datetime | None = None
    phase_4_completed_at: datetime | None = None
    phase_5_completed_at: datetime | None = None

    gate_approved_by: uuid.UUID | None = None
    gate_approved_by_name: str | None = None
    gate_approved_at: datetime | None = None
    gate_comments: str | None = None
    gate_history: list | None = None

    dfmea_id: uuid.UUID | None = None
    dfmea_document_no: str | None = None
    pfmea_id: uuid.UUID | None = None
    pfmea_document_no: str | None = None
    control_plan_id: uuid.UUID | None = None
    control_plan_document_no: str | None = None
    ppap_submission_id: uuid.UUID | None = None
    ppap_submission_part_no: str | None = None
    ppap_submission_part_name: str | None = None

    created_by: uuid.UUID
    created_by_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class APQPProjectListResponse(BaseModel):
    items: list[APQPProjectResponse]
    total: int
    page: int
    page_size: int


class APQPGateTransitionRequest(BaseModel):
    action: Literal["submit_gate", "approve_gate", "reject_gate", "cancel"]
    comments: str | None = None


class APQPProjectStatsResponse(BaseModel):
    total_projects: int
    active_count: int
    pending_approval_count: int
    completed_count: int
    cancelled_count: int
    overdue_count: int
    phase_distribution: dict[int, int]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/apqp.py
git commit -m "feat(apqp): add APQP Pydantic schemas"
```

---

### Task 4: Backend Service Layer

**Files:**
- Create: `backend/app/services/apqp_service.py`

- [ ] **Step 1: Create service file**

```python
# backend/app/services/apqp_service.py
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.apqp import APQPProject
from app.models.audit import AuditLog
from app.models.fmea import FMEADocument
from app.models.control_plan import ControlPlan
from app.models.supplier import SupplierPPAPSubmission
from app.models.product_line import ProductLine


PHASE_NAMES = {
    1: "策划与定义",
    2: "产品设计与开发",
    3: "过程设计与开发",
    4: "产品与过程确认",
    5: "量产启动与反馈",
}

DELIVERABLE_CHECKS = {
    2: [{"field": "dfmea_id", "label": "DFMEA"}],
    3: [{"field": "pfmea_id", "label": "PFMEA"}, {"field": "control_plan_id", "label": "控制计划"}],
    4: [{"field": "ppap_submission_id", "label": "PPAP"}],
}


async def _next_project_code(db: AsyncSession) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"APQP-{year}-"
    result = await db.execute(
        select(APQPProject.project_code)
        .where(APQPProject.project_code.like(f"{prefix}%"))
        .order_by(APQPProject.project_code.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    seq = int(last.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{seq:03d}"


def _append_gate_history(project: APQPProject, action: str, user_id: uuid.UUID, user_name: str, comments: str | None):
    entry = {
        "phase": project.current_phase,
        "action": action,
        "user_id": str(user_id),
        "user_name": user_name,
        "comments": comments,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if project.gate_history is None:
        project.gate_history = [entry]
    else:
        project.gate_history = project.gate_history + [entry]


async def list_projects(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    project_status: str | None = None,
    current_phase: int | None = None,
) -> tuple[list[APQPProject], int]:
    query = select(APQPProject).options(
        selectinload(APQPProject.creator),
        selectinload(APQPProject.gate_approver),
        selectinload(APQPProject.dfmea),
        selectinload(APQPProject.pfmea),
        selectinload(APQPProject.control_plan),
        selectinload(APQPProject.ppap_submission),
    )
    count_query = select(func.count()).select_from(APQPProject)

    if project_status:
        query = query.where(APQPProject.project_status == project_status)
        count_query = count_query.where(APQPProject.project_status == project_status)
    if current_phase is not None:
        query = query.where(APQPProject.current_phase == current_phase)
        count_query = count_query.where(APQPProject.current_phase == current_phase)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(APQPProject.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())
    return items, total


async def get_project(db: AsyncSession, project_id: uuid.UUID) -> APQPProject | None:
    result = await db.execute(
        select(APQPProject)
        .options(
            selectinload(APQPProject.creator),
            selectinload(APQPProject.gate_approver),
            selectinload(APQPProject.dfmea),
            selectinload(APQPProject.pfmea),
            selectinload(APQPProject.control_plan),
            selectinload(APQPProject.ppap_submission),
        )
        .where(APQPProject.project_id == project_id)
    )
    return result.scalar_one_or_none()


async def create_project(
    db: AsyncSession,
    *,
    project_name: str,
    product_name: str,
    product_line_code: str,
    user_id: uuid.UUID,
    customer_name: str | None = None,
    description: str | None = None,
    target_sop_date: date | None = None,
    team_members: list | None = None,
    dfmea_id: uuid.UUID | None = None,
    pfmea_id: uuid.UUID | None = None,
    control_plan_id: uuid.UUID | None = None,
    ppap_submission_id: uuid.UUID | None = None,
) -> APQPProject:
    # Validate linked IDs if provided
    if product_line_code:
        if not await db.get(ProductLine, product_line_code):
            raise ValueError("产品线记录不存在")
    if dfmea_id:
        if not await db.get(FMEADocument, dfmea_id):
            raise ValueError("DFMEA 记录不存在")
    if pfmea_id:
        if not await db.get(FMEADocument, pfmea_id):
            raise ValueError("PFMEA 记录不存在")
    if control_plan_id:
        if not await db.get(ControlPlan, control_plan_id):
            raise ValueError("控制计划记录不存在")
    if ppap_submission_id:
        if not await db.get(SupplierPPAPSubmission, ppap_submission_id):
            raise ValueError("PPAP 提交记录不存在")

    for attempt in range(3):
        project_code = await _next_project_code(db)
        project = APQPProject(
            project_code=project_code,
            project_name=project_name,
            product_name=product_name,
            product_line_code=product_line_code,
            customer_name=customer_name,
            description=description,
            target_sop_date=target_sop_date,
            team_members=team_members,
            dfmea_id=dfmea_id,
            pfmea_id=pfmea_id,
            control_plan_id=control_plan_id,
            ppap_submission_id=ppap_submission_id,
            created_by=user_id,
        )
        db.add(project)
        try:
            await db.flush()
            break
        except IntegrityError as e:
            if "apqp_projects_project_code" not in str(e.orig):
                raise
            await db.rollback()
            if attempt == 2:
                raise ValueError("项目编号生成冲突，请重试")
            continue

    db.add(AuditLog(
        table_name="apqp_projects",
        record_id=project.project_id,
        action="CREATE",
        changed_fields={"project_code": project.project_code, "project_name": project_name, "product_name": product_name},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_project(db, project.project_id)


async def update_project(
    db: AsyncSession,
    project: APQPProject,
    *,
    user_id: uuid.UUID,
    # All other fields come via **kwargs (populated by API from exclude_unset=True dict)
    # "key": None means clear the field; missing key means don't touch
    **kwargs,
) -> APQPProject:
    # Validate linked IDs if being updated (non-None key with value means set to that ID)
    fk_fields = {
        "product_line_code": (ProductLine, "产品线"),
        "dfmea_id": (FMEADocument, "DFMEA"),
        "pfmea_id": (FMEADocument, "PFMEA"),
        "control_plan_id": (ControlPlan, "控制计划"),
        "ppap_submission_id": (SupplierPPAPSubmission, "PPAP"),
    }
    for key, (model, label) in fk_fields.items():
        val = kwargs.get(key)
        if val is not None and not await db.get(model, val):
            raise ValueError(f"{label} 记录不存在")

    changed = {}
    field_map = {
        "project_name": "project_name",
        "product_name": "product_name",
        "product_line_code": "product_line_code",
        "customer_name": "customer_name",
        "description": "description",
        "target_sop_date": "target_sop_date",
        "team_members": "team_members",
        "dfmea_id": "dfmea_id",
        "pfmea_id": "pfmea_id",
        "control_plan_id": "control_plan_id",
        "ppap_submission_id": "ppap_submission_id",
    }
    for key, attr in field_map.items():
        if key in kwargs:
            val = kwargs[key]
            setattr(project, attr, val)
            if attr in ("target_sop_date", "dfmea_id", "pfmea_id", "control_plan_id", "ppap_submission_id"):
                changed[key] = str(val) if val is not None else None
            elif attr == "team_members":
                changed[key] = str(val) if val is not None else None
            else:
                changed[key] = val

    if changed:
        db.add(AuditLog(
            table_name="apqp_projects",
            record_id=project.project_id,
            action="UPDATE",
            changed_fields=changed,
            operated_by=user_id,
        ))
    await db.commit()
    return await get_project(db, project.project_id)


async def get_stats(db: AsyncSession) -> dict:
    today = date.today()

    total = (await db.execute(select(func.count()).select_from(APQPProject))).scalar() or 0
    active = (await db.execute(select(func.count()).where(APQPProject.project_status == "active"))).scalar() or 0
    pending = (await db.execute(
        select(func.count()).where(
            APQPProject.phase_status == "pending_approval",
            APQPProject.project_status == "active",
        )
    )).scalar() or 0
    completed = (await db.execute(select(func.count()).where(APQPProject.project_status == "completed"))).scalar() or 0
    cancelled = (await db.execute(select(func.count()).where(APQPProject.project_status == "cancelled"))).scalar() or 0
    overdue = (await db.execute(
        select(func.count()).where(
            APQPProject.target_sop_date < today,
            APQPProject.project_status == "active",
        )
    )).scalar() or 0

    # Phase distribution for active projects
    phase_rows = (await db.execute(
        select(APQPProject.current_phase, func.count())
        .where(APQPProject.project_status == "active")
        .group_by(APQPProject.current_phase)
    )).all()
    phase_dist = {row[0]: row[1] for row in phase_rows}

    return {
        "total_projects": total,
        "active_count": active,
        "pending_approval_count": pending,
        "completed_count": completed,
        "cancelled_count": cancelled,
        "overdue_count": overdue,
        "phase_distribution": phase_dist,
    }


async def transition_project(
    db: AsyncSession,
    project: APQPProject,
    action: str,
    user_id: uuid.UUID,
    user_name: str,
    comments: str | None = None,
) -> APQPProject:
    if project.project_status != "active":
        raise ValueError("项目不在进行中，无法操作")

    if action == "submit_gate":
        if project.phase_status != "in_progress":
            raise ValueError("当前阶段不在进行中")
        project.phase_status = "pending_approval"
        _append_gate_history(project, "submit", user_id, user_name, comments)

    elif action == "approve_gate":
        if project.phase_status != "pending_approval":
            raise ValueError("当前阶段未提交审批")
        checks = DELIVERABLE_CHECKS.get(project.current_phase, [])
        for check in checks:
            if not getattr(project, check["field"]):
                raise ValueError(f"Phase {project.current_phase} 需关联 {check['label']} 后方可审批通过")
        now = datetime.now(timezone.utc)
        project.gate_approved_by = user_id
        project.gate_approved_at = now
        project.gate_comments = comments
        setattr(project, f"phase_{project.current_phase}_completed_at", now)
        _append_gate_history(project, "approve", user_id, user_name, comments)
        if project.current_phase < 5:
            project.current_phase += 1
            project.phase_status = "in_progress"
        else:
            project.project_status = "completed"
            project.phase_status = "completed"

    elif action == "reject_gate":
        if project.phase_status != "pending_approval":
            raise ValueError("当前阶段未提交审批")
        project.phase_status = "in_progress"
        project.gate_comments = comments
        _append_gate_history(project, "reject", user_id, user_name, comments)

    elif action == "cancel":
        project.project_status = "cancelled"

    else:
        raise ValueError(f"无效动作: {action}")

    db.add(AuditLog(
        table_name="apqp_projects",
        record_id=project.project_id,
        action="TRANSITION",
        changed_fields={"action": action, "comments": comments},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_project(db, project.project_id)
```

- [ ] **Step 2: Verify the service compiles**

```bash
cd backend && python -c "from app.services.apqp_service import list_projects, get_project, create_project, update_project, transition_project, get_stats; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/apqp_service.py
git commit -m "feat(apqp): add APQP service layer with gate transitions"
```

---

### Task 5: Backend API Routes

**Files:**
- Create: `backend/app/api/apqp.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create API routes file**

```python
# backend/app/api/apqp.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User
from app.schemas import apqp as apqp_schemas
from app.services import apqp_service

router = APIRouter(prefix="/api/apqp-projects", tags=["apqp"])

PHASE_NAMES = {
    1: "策划与定义",
    2: "产品设计与开发",
    3: "过程设计与开发",
    4: "产品与过程确认",
    5: "量产启动与反馈",
}


def _to_response(p) -> apqp_schemas.APQPProjectResponse:
    return apqp_schemas.APQPProjectResponse(
        project_id=p.project_id,
        project_code=p.project_code,
        project_name=p.project_name,
        product_name=p.product_name,
        product_line_code=p.product_line_code,
        customer_name=p.customer_name,
        description=p.description,
        target_sop_date=p.target_sop_date,
        team_members=p.team_members,
        current_phase=p.current_phase,
        phase_name=PHASE_NAMES.get(p.current_phase, ""),
        phase_status=p.phase_status,
        project_status=p.project_status,
        phase_1_completed_at=p.phase_1_completed_at,
        phase_2_completed_at=p.phase_2_completed_at,
        phase_3_completed_at=p.phase_3_completed_at,
        phase_4_completed_at=p.phase_4_completed_at,
        phase_5_completed_at=p.phase_5_completed_at,
        gate_approved_by=p.gate_approved_by,
        gate_approved_by_name=p.gate_approver.display_name if p.gate_approver else None,
        gate_approved_at=p.gate_approved_at,
        gate_comments=p.gate_comments,
        gate_history=p.gate_history,
        dfmea_id=p.dfmea_id,
        dfmea_document_no=p.dfmea.document_no if p.dfmea else None,
        pfmea_id=p.pfmea_id,
        pfmea_document_no=p.pfmea.document_no if p.pfmea else None,
        control_plan_id=p.control_plan_id,
        control_plan_document_no=p.control_plan.document_no if p.control_plan else None,
        ppap_submission_id=p.ppap_submission_id,
        ppap_submission_part_no=p.ppap_submission.part_no if p.ppap_submission else None,
        ppap_submission_part_name=p.ppap_submission.part_name if p.ppap_submission else None,
        created_by=p.created_by,
        created_by_name=p.creator.display_name if p.creator else "",
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("", response_model=apqp_schemas.APQPProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    project_status: str | None = Query(None),
    current_phase: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await apqp_service.list_projects(
        db, page, page_size, project_status, current_phase,
    )
    return apqp_schemas.APQPProjectListResponse(
        items=[_to_response(p) for p in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/stats", response_model=apqp_schemas.APQPProjectStatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await apqp_service.get_stats(db)


@router.get("/{project_id}", response_model=apqp_schemas.APQPProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    project = await apqp_service.get_project(db, project_id)
    if not project:
        raise HTTPException(404, "APQP project not found")
    return _to_response(project)


@router.post("", response_model=apqp_schemas.APQPProjectResponse)
async def create_project(
    req: apqp_schemas.APQPProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        project = await apqp_service.create_project(
            db,
            project_name=req.project_name,
            product_name=req.product_name,
            product_line_code=req.product_line_code,
            user_id=user.user_id,
            customer_name=req.customer_name,
            description=req.description,
            target_sop_date=req.target_sop_date,
            team_members=req.team_members,
            dfmea_id=req.dfmea_id,
            pfmea_id=req.pfmea_id,
            control_plan_id=req.control_plan_id,
            ppap_submission_id=req.ppap_submission_id,
        )
        return _to_response(project)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{project_id}", response_model=apqp_schemas.APQPProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    req: apqp_schemas.APQPProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    project = await apqp_service.get_project(db, project_id)
    if not project:
        raise HTTPException(404, "APQP project not found")
    if project.project_status != "active":
        raise HTTPException(400, "只能编辑进行中的项目")
    try:
        # Use exclude_unset=True so None means "clear this field" vs missing key means "don't touch"
        update_data = req.model_dump(exclude_unset=True)
        project = await apqp_service.update_project(db, project, user_id=user.user_id, **update_data)
        return _to_response(project)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{project_id}/transition", response_model=apqp_schemas.APQPProjectResponse)
async def transition_project(
    project_id: uuid.UUID,
    req: apqp_schemas.APQPGateTransitionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Route-level role check (FMEA-style pattern)
    if req.action in ("approve_gate", "reject_gate"):
        if user.role not in ("admin", "manager"):
            raise HTTPException(403, "需要经理或管理员权限")
    elif req.action in ("submit_gate",):
        if user.role not in ("admin", "manager", "quality_engineer"):
            raise HTTPException(403, "需要工程师或更高权限")
    elif req.action == "cancel":
        if user.role != "admin":
            raise HTTPException(403, "仅管理员可取消项目")

    project = await apqp_service.get_project(db, project_id)
    if not project:
        raise HTTPException(404, "APQP project not found")
    try:
        project = await apqp_service.transition_project(
            db, project, req.action, user.user_id, user.display_name, req.comments,
        )
        return _to_response(project)
    except ValueError as e:
        raise HTTPException(400, str(e))
```

- [ ] **Step 2: Register router in main.py**

In `backend/app/main.py`, add the import after the scar import:

```python
from app.api.apqp import router as apqp_router
```

And add `app.include_router(apqp_router)` after the scar_router line.

- [ ] **Step 3: Verify the app starts**

```bash
cd backend && timeout 5 uvicorn app.main:app --port 8000 2>&1 || true
```

Expected: no import errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/apqp.py backend/app/main.py
git commit -m "feat(apqp): add APQP API routes with role-gated transitions"
```

---

### Task 6: Frontend Types + API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/apqp.ts`

- [ ] **Step 1: Add TypeScript types**

Append to `frontend/src/types/index.ts` after the SCAR types:

```typescript
// APQP 项目质量策划
export interface APQPProject {
  project_id: string;
  project_code: string;
  project_name: string;
  product_name: string;
  product_line_code: string;
  customer_name: string | null;
  description: string | null;
  target_sop_date: string | null;
  team_members: { name: string; role: string; department: string }[] | null;
  current_phase: number;
  phase_name: string;
  phase_status: string | null;
  project_status: string;
  phase_1_completed_at: string | null;
  phase_2_completed_at: string | null;
  phase_3_completed_at: string | null;
  phase_4_completed_at: string | null;
  phase_5_completed_at: string | null;
  gate_approved_by: string | null;
  gate_approved_by_name: string | null;
  gate_approved_at: string | null;
  gate_comments: string | null;
  gate_history: APQPGateHistoryEntry[] | null;
  dfmea_id: string | null;
  dfmea_document_no: string | null;
  pfmea_id: string | null;
  pfmea_document_no: string | null;
  control_plan_id: string | null;
  control_plan_document_no: string | null;
  ppap_submission_id: string | null;
  ppap_submission_part_no: string | null;
  ppap_submission_part_name: string | null;
  created_by: string;
  created_by_name: string;
  created_at: string;
  updated_at: string;
}

export interface APQPGateHistoryEntry {
  phase: number;
  action: string;
  user_id: string;
  user_name: string;
  comments: string | null;
  timestamp: string;
}

export interface APQPListResponse {
  items: APQPProject[];
  total: number;
  page: number;
  page_size: number;
}

export interface APQPProjectCreate {
  project_name: string;
  product_name: string;
  product_line_code: string;
  customer_name?: string;
  description?: string;
  target_sop_date?: string;
  team_members?: { name: string; role: string; department: string }[];
  dfmea_id?: string;
  pfmea_id?: string;
  control_plan_id?: string;
  ppap_submission_id?: string;
}

export interface APQPProjectUpdate {
  project_name?: string;
  product_name?: string;
  product_line_code?: string;
  customer_name?: string | null;
  description?: string | null;
  target_sop_date?: string | null;
  team_members?: { name: string; role: string; department: string }[] | null;
  dfmea_id?: string | null;
  pfmea_id?: string | null;
  control_plan_id?: string | null;
  ppap_submission_id?: string | null;
}

export interface APQPGateTransition {
  action: "submit_gate" | "approve_gate" | "reject_gate" | "cancel";
  comments?: string;
}

export interface APQPProjectStats {
  total_projects: number;
  active_count: number;
  pending_approval_count: number;
  completed_count: number;
  cancelled_count: number;
  overdue_count: number;
  phase_distribution: Record<number, number>;
}
```

- [ ] **Step 2: Create API client**

```typescript
// frontend/src/api/apqp.ts
import client from "./client";
import type {
  APQPListResponse,
  APQPProject,
  APQPProjectCreate,
  APQPProjectUpdate,
  APQPGateTransition,
  APQPProjectStats,
} from "../types";

export async function listAPQPProjects(params: {
  page?: number;
  page_size?: number;
  project_status?: string;
  current_phase?: number;
}): Promise<APQPListResponse> {
  const res = await client.get("/apqp-projects", { params });
  return res.data;
}

export async function getAPQPProject(id: string): Promise<APQPProject> {
  const res = await client.get(`/apqp-projects/${id}`);
  return res.data;
}

export async function createAPQPProject(data: APQPProjectCreate): Promise<APQPProject> {
  const res = await client.post("/apqp-projects", data);
  return res.data;
}

export async function updateAPQPProject(id: string, data: APQPProjectUpdate): Promise<APQPProject> {
  const res = await client.put(`/apqp-projects/${id}`, data);
  return res.data;
}

export async function transitionAPQPProject(id: string, data: APQPGateTransition): Promise<APQPProject> {
  const res = await client.post(`/apqp-projects/${id}/transition`, data);
  return res.data;
}

export async function getAPQPProjectStats(): Promise<APQPProjectStats> {
  const res = await client.get("/apqp-projects/stats");
  return res.data;
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no new type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/apqp.ts
git commit -m "feat(apqp): add frontend types and API client"
```

---

### Task 7: Frontend List Page

**Files:**
- Create: `frontend/src/pages/apqp/APQPListPage.tsx`

- [ ] **Step 1: Create list page**

```typescript
// frontend/src/pages/apqp/APQPListPage.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Tag, Tabs, Button, Select, Space, Modal, Form, Input, DatePicker, message, Card, Row, Col, Spin } from "antd";
import { PlusOutlined, ProjectOutlined, ClockCircleOutlined, CheckCircleOutlined, ExclamationCircleOutlined } from "@ant-design/icons";
import { listAPQPProjects, createAPQPProject, getAPQPProjectStats } from "../../api/apqp";
import type { APQPProject, APQPListResponse, APQPProjectStats } from "../../types";

const PROJECT_STATUS_TABS = [
  { key: "all", label: "全部" },
  { key: "active", label: "进行中" },
  { key: "completed", label: "已完成" },
  { key: "cancelled", label: "已取消" },
];

const PHASE_NAMES: Record<number, string> = {
  1: "策划与定义",
  2: "产品设计与开发",
  3: "过程设计与开发",
  4: "产品与过程确认",
  5: "量产启动与反馈",
};

const PHASE_COLORS: Record<number, string> = {
  1: "blue",
  2: "cyan",
  3: "geekblue",
  4: "purple",
  5: "green",
};

const PROJECT_STATUS_LABELS: Record<string, string> = {
  active: "进行中",
  completed: "已完成",
  cancelled: "已取消",
};

function KPICard({ title, value, icon, color }: { title: string; value: number; icon: React.ReactNode; color: string }) {
  return (
    <Card size="small">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ fontSize: 24, color }}>{icon}</div>
        <div>
          <div style={{ fontSize: 12, color: "#999" }}>{title}</div>
          <div style={{ fontSize: 24, fontWeight: 600 }}>{value}</div>
        </div>
      </div>
    </Card>
  );
}

export default function APQPListPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<APQPListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("all");
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm();
  const [stats, setStats] = useState<APQPProjectStats | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [result, s] = await Promise.all([
        listAPQPProjects({
          page,
          page_size: 20,
          project_status: activeTab === "all" ? undefined : activeTab,
        }),
        getAPQPProjectStats(),
      ]);
      setData(result);
      setStats(s);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [activeTab, page]);

  const handleCreate = async (values: Record<string, unknown>) => {
    await createAPQPProject({
      project_name: values.project_name as string,
      product_name: values.product_name as string,
      product_line_code: values.product_line_code as string,
      customer_name: values.customer_name as string | undefined,
      description: values.description as string | undefined,
      target_sop_date: values.target_sop_date
        ? (values.target_sop_date as { format: (f: string) => string }).format("YYYY-MM-DD")
        : undefined,
      dfmea_id: values.dfmea_id as string | undefined,
      pfmea_id: values.pfmea_id as string | undefined,
      control_plan_id: values.control_plan_id as string | undefined,
      ppap_submission_id: values.ppap_submission_id as string | undefined,
    });
    message.success("项目创建成功");
    setCreateOpen(false);
    form.resetFields();
    loadData();
  };

  const columns = [
    { title: "项目编号", dataIndex: "project_code", key: "project_code", render: (_v: string, record: APQPProject) => <a onClick={() => navigate(`/apqp/${record.project_id}`)}>{record.project_code}</a> },
    { title: "项目名称", dataIndex: "project_name", key: "project_name" },
    { title: "产品", dataIndex: "product_name", key: "product_name" },
    { title: "客户", dataIndex: "customer_name", key: "customer_name", render: (v: string | null) => v || "-" },
    {
      title: "当前阶段",
      dataIndex: "current_phase",
      key: "current_phase",
      render: (p: number) => <Tag color={PHASE_COLORS[p]}>{PHASE_NAMES[p]}</Tag>,
    },
    {
      title: "阶段状态",
      dataIndex: "phase_status",
      key: "phase_status",
      render: (s: string | null) => {
        if (s === "pending_approval") return <Tag color="orange">待审批</Tag>;
        if (s === "in_progress") return <Tag color="blue">进行中</Tag>;
        if (s === "completed") return <Tag color="green">已完成</Tag>;
        return s || "-";
      },
    },
    {
      title: "目标SOP",
      dataIndex: "target_sop_date",
      key: "target_sop_date",
      render: (v: string | null) => {
        if (!v) return "-";
        const isOverdue = new Date(v) < new Date(new Date().toDateString());
        return <span style={{ color: isOverdue ? "red" : undefined }}>{v}{isOverdue ? " ⚠" : ""}</span>;
      },
    },
    {
      title: "项目状态",
      dataIndex: "project_status",
      key: "project_status",
      render: (s: string) => {
        const colors: Record<string, string> = { active: "processing", completed: "success", cancelled: "default" };
        return <Tag color={colors[s]}>{PROJECT_STATUS_LABELS[s] || s}</Tag>;
      },
    },
    {
      title: "操作",
      key: "action",
      render: (_: unknown, record: APQPProject) => (
        <Button type="link" onClick={() => navigate(`/apqp/${record.project_id}`)}>查看</Button>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}><KPICard title="进行中" value={stats?.active_count ?? 0} icon={<ProjectOutlined />} color="#1677ff" /></Col>
        <Col span={4}><KPICard title="待审批" value={stats?.pending_approval_count ?? 0} icon={<ClockCircleOutlined />} color="#fa8c16" /></Col>
        <Col span={4}><KPICard title="已完成" value={stats?.completed_count ?? 0} icon={<CheckCircleOutlined />} color="#52c41a" /></Col>
        <Col span={4}><KPICard title="逾期" value={stats?.overdue_count ?? 0} icon={<ExclamationCircleOutlined />} color="#ff4d4f" /></Col>
      </Row>

      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Tabs activeKey={activeTab} onChange={(k) => { setActiveTab(k); setPage(1); }} items={PROJECT_STATUS_TABS} />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          新建项目
        </Button>
      </div>

      <Table
        dataSource={data?.items || []}
        columns={columns}
        rowKey="project_id"
        loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total: data?.total || 0,
          onChange: setPage,
        }}
      />

      <Modal
        title="新建 APQP 项目"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        destroyOnClose
        width={640}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="project_name" label="项目名称" rules={[{ required: true, message: "请输入项目名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="product_name" label="产品名称" rules={[{ required: true, message: "请输入产品名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="product_line_code" label="产品线" rules={[{ required: true, message: "请输入产品线" }]}>
            <Input placeholder="例: DC-DC-100" />
          </Form.Item>
          <Form.Item name="customer_name" label="客户名称">
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="target_sop_date" label="目标SOP日期">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Space style={{ width: "100%" }}>
            {/* v1 使用文本输入，FK 校验由后端返回 400 兜底；后续改为 Select 组件 */}
            <Form.Item name="dfmea_id" label="DFMEA">
              <Input placeholder="FMEA ID（可选，v1 文本输入）" style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="pfmea_id" label="PFMEA">
              <Input placeholder="FMEA ID（可选，v1 文本输入）" style={{ width: 200 }} />
            </Form.Item>
          </Space>
          <Space style={{ width: "100%" }}>
            <Form.Item name="control_plan_id" label="控制计划">
              <Input placeholder="CP ID（可选，v1 文本输入）" style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="ppap_submission_id" label="PPAP">
              <Input placeholder="PPAP ID（可选，v1 文本输入）" style={{ width: 200 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no new type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/apqp/APQPListPage.tsx
git commit -m "feat(apqp): add APQP list page with KPI cards"
```

---

### Task 8: Frontend Detail Page

**Files:**
- Create: `frontend/src/pages/apqp/APQPDetailPage.tsx`

- [ ] **Step 1: Create detail page**

```typescript
// frontend/src/pages/apqp/APQPDetailPage.tsx
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, Tag, Button, Space, Descriptions, Input, Modal, message, Spin, Row, Col, Steps, Timeline } from "antd";
import { EditOutlined } from "@ant-design/icons";
import { getAPQPProject, updateAPQPProject, transitionAPQPProject } from "../../api/apqp";
import type { APQPProject } from "../../types";
import { useAuthStore } from "../../store/authStore";

const PHASE_NAMES: Record<number, string> = {
  1: "策划与定义",
  2: "产品设计与开发",
  3: "过程设计与开发",
  4: "产品与过程确认",
  5: "量产启动与反馈",
};

const PROJECT_STATUS_LABELS: Record<string, string> = {
  active: "进行中",
  completed: "已完成",
  cancelled: "已取消",
};

const PROJECT_STATUS_COLORS: Record<string, string> = {
  active: "processing",
  completed: "success",
  cancelled: "default",
};

export default function APQPDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [project, setProject] = useState<APQPProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [editForm, setEditForm] = useState<Record<string, string>>({});
  const [gateComment, setGateComment] = useState("");

  const isAdmin = user?.role === "admin";
  const isManager = user?.role === "admin" || user?.role === "manager";
  const isEngineer = user?.role === "admin" || user?.role === "manager" || user?.role === "quality_engineer";

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getAPQPProject(id);
      setProject(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [id]);

  const handleTransition = async (action: string, comments?: string) => {
    if (!id) return;
    await transitionAPQPProject(id, { action: action as "submit_gate" | "approve_gate" | "reject_gate" | "cancel", comments });
    message.success("操作成功");
    setGateComment("");
    load();
  };

  const handleEdit = async () => {
    if (!id) return;
    // Convert empty strings to null for nullable fields
    const nullableFields = ["dfmea_id", "pfmea_id", "control_plan_id", "ppap_submission_id", "customer_name", "description"];
    const payload: Record<string, string | null> = {};
    for (const [k, v] of Object.entries(editForm)) {
      payload[k] = nullableFields.includes(k) ? (v || null) : v;
    }
    await updateAPQPProject(id, payload as APQPProjectUpdate);
    message.success("更新成功");
    setEditOpen(false);
    load();
  };

  if (loading || !project) {
    return <div style={{ textAlign: "center", padding: 100 }}><Spin size="large" /></div>;
  }

  const stepItems = [1, 2, 3, 4, 5].map((phase) => {
    const completedAt = (project as Record<string, string | null>)[`phase_${phase}_completed_at`];
    let status: "wait" | "process" | "finish" | "error" = "wait";
    let description = "";

    if (completedAt) {
      status = "finish";
      description = completedAt.slice(0, 10);
    } else if (project.current_phase === phase) {
      status = project.phase_status === "pending_approval" ? "error" : "process";
      description = project.phase_status === "pending_approval" ? "待审批" : "进行中";
    }

    return {
      title: `Phase ${phase}`,
      subTitle: PHASE_NAMES[phase],
      status,
      description,
    };
  });

  const actionButtons = (): ReactNode[] => {
    if (project.project_status !== "active") return [];
    const btns: ReactNode[] = [];
    if (project.phase_status === "in_progress" && isEngineer) {
      btns.push(
        <Button key="submit" type="primary" onClick={() => handleTransition("submit_gate")}>
          提交审批
        </Button>
      );
    }
    if (project.phase_status === "pending_approval") {
      if (isManager) {
        btns.push(
          <Button key="approve" type="primary" onClick={() => handleTransition("approve_gate", gateComment)}>
            审批通过
          </Button>
        );
        btns.push(
          <Button key="reject" danger onClick={() => handleTransition("reject_gate", gateComment)}>
            驳回
          </Button>
        );
      }
    }
    if (isAdmin && project.project_status === "active") {
      btns.push(
        <Button key="cancel" danger onClick={() => handleTransition("cancel")}>
          取消项目
        </Button>
      );
    }
    return btns;
  };

  return (
    <div>
      {/* Header */}
      <Card style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space>
              <span style={{ fontSize: 20, fontWeight: 600 }}>{project.project_code}</span>
              <span style={{ fontSize: 16 }}>{project.project_name}</span>
              <Tag color={PROJECT_STATUS_COLORS[project.project_status]}>
                {PROJECT_STATUS_LABELS[project.project_status]}
              </Tag>
            </Space>
          </Col>
          <Col>
            <Space>
              {isEngineer && project.project_status === "active" && (
                <Button icon={<EditOutlined />} onClick={() => {
                  setEditForm({
                    project_name: project.project_name,
                    product_name: project.product_name,
                    customer_name: project.customer_name || "",
                    description: project.description || "",
                    dfmea_id: project.dfmea_id || "",
                    pfmea_id: project.pfmea_id || "",
                    control_plan_id: project.control_plan_id || "",
                    ppap_submission_id: project.ppap_submission_id || "",
                  });
                  setEditOpen(true);
                }}>
                  编辑
                </Button>
              )}
              {actionButtons()}
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Project Info */}
      <Card title="项目信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="项目编号">{project.project_code}</Descriptions.Item>
          <Descriptions.Item label="项目名称">{project.project_name}</Descriptions.Item>
          <Descriptions.Item label="产品">{project.product_name}</Descriptions.Item>
          <Descriptions.Item label="产品线">{project.product_line_code}</Descriptions.Item>
          <Descriptions.Item label="客户">{project.customer_name || "-"}</Descriptions.Item>
          <Descriptions.Item label="目标SOP">{project.target_sop_date || "-"}</Descriptions.Item>
          <Descriptions.Item label="创建人">{project.created_by_name}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{project.created_at ? new Date(project.created_at).toLocaleString() : "-"}</Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>{project.description || "-"}</Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Phase Progress */}
      <Card title="阶段进度" style={{ marginBottom: 16 }}>
        <Steps items={stepItems} current={project.current_phase - 1} status={project.phase_status === "pending_approval" ? "error" : undefined} />
      </Card>

      {/* Current Phase Actions */}
      {project.project_status === "active" && (
        <Card title="阶段操作" style={{ marginBottom: 16 }}>
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="当前阶段">
              <Tag color="blue">Phase {project.current_phase} — {PHASE_NAMES[project.current_phase]}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="阶段状态">
              {project.phase_status === "pending_approval" ? <Tag color="orange">待审批</Tag> : <Tag color="blue">进行中</Tag>}
            </Descriptions.Item>
          </Descriptions>
          <div style={{ marginTop: 12 }}>
            <Input.TextArea
              rows={3}
              value={gateComment}
              onChange={(e) => setGateComment(e.target.value)}
              placeholder="门控审批意见（可选）"
              style={{ marginBottom: 8 }}
            />
            <Space>{actionButtons()}</Space>
          </div>
        </Card>
      )}

      {/* Cross-module Links */}
      <Card title="关联交付物" style={{ marginBottom: 16 }}>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="DFMEA（Phase 2）">
            {project.dfmea_id ? (
              <Space>
                <span>{project.dfmea_document_no || project.dfmea_id}</span>
                <Button size="small" type="link" onClick={() => navigate(`/fmea/${project.dfmea_id}`)}>查看</Button>
              </Space>
            ) : <span style={{ color: "#999" }}>未关联</span>}
          </Descriptions.Item>
          <Descriptions.Item label="PFMEA（Phase 3）">
            {project.pfmea_id ? (
              <Space>
                <span>{project.pfmea_document_no || project.pfmea_id}</span>
                <Button size="small" type="link" onClick={() => navigate(`/fmea/${project.pfmea_id}`)}>查看</Button>
              </Space>
            ) : <span style={{ color: "#999" }}>未关联</span>}
          </Descriptions.Item>
          <Descriptions.Item label="控制计划（Phase 3）">
            {project.control_plan_id ? (
              <Space>
                <span>{project.control_plan_document_no || project.control_plan_id}</span>
                <Button size="small" type="link" onClick={() => navigate(`/control-plans/${project.control_plan_id}`)}>查看</Button>
              </Space>
            ) : <span style={{ color: "#999" }}>未关联</span>}
          </Descriptions.Item>
          <Descriptions.Item label="PPAP（Phase 4）">
            {project.ppap_submission_id ? (
              <Space>
                <span>{project.ppap_submission_part_no} — {project.ppap_submission_part_name}</span>
              </Space>
            ) : <span style={{ color: "#999" }}>未关联</span>}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Phase Timeline */}
      <Card title="阶段时间线" style={{ marginBottom: 16 }}>
        <Timeline
          items={[1, 2, 3, 4, 5].map((phase) => {
            const completedAt = (project as Record<string, string | null>)[`phase_${phase}_completed_at`];
            return {
              color: completedAt ? "green" : project.current_phase === phase ? "blue" : "gray",
              children: (
                <div>
                  <strong>Phase {phase} — {PHASE_NAMES[phase]}</strong>
                  <div style={{ color: "#999", fontSize: 12 }}>{completedAt || "未完成"}</div>
                </div>
              ),
            };
          })}
        />
      </Card>

      {/* Gate History */}
      {project.gate_history && project.gate_history.length > 0 && (
        <Card title="门控审批记录">
          <Timeline
            items={project.gate_history.map((entry) => ({
              color: entry.action === "approve" ? "green" : entry.action === "reject" ? "red" : "blue",
              children: (
                <div>
                  <strong>
                    Phase {entry.phase} — {entry.action === "approve" ? "审批通过" : entry.action === "reject" ? "驳回" : "提交审批"}
                  </strong>
                  <span style={{ marginLeft: 8, color: "#999", fontSize: 12 }}>
                    by {entry.user_name} · {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : ""}
                  </span>
                  {entry.comments && (
                    <div style={{ color: "#666", fontSize: 13, marginTop: 4 }}>
                      {entry.comments}
                    </div>
                  )}
                </div>
              ),
            }))}
          />
        </Card>
      )}

      {/* Edit Modal */}
      <Modal
        title="编辑项目"
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleEdit}
        width={640}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <label>项目名称</label>
            <Input value={editForm.project_name} onChange={(e) => setEditForm({ ...editForm, project_name: e.target.value })} />
          </div>
          <div>
            <label>产品名称</label>
            <Input value={editForm.product_name} onChange={(e) => setEditForm({ ...editForm, product_name: e.target.value })} />
          </div>
          <div>
            <label>客户名称</label>
            <Input value={editForm.customer_name} onChange={(e) => setEditForm({ ...editForm, customer_name: e.target.value })} />
          </div>
          <div>
            <label>描述</label>
            <Input.TextArea rows={3} value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} />
          </div>
          <div>
            <label>DFMEA ID</label>
            <Input value={editForm.dfmea_id} onChange={(e) => setEditForm({ ...editForm, dfmea_id: e.target.value })} />
          </div>
          <div>
            <label>PFMEA ID</label>
            <Input value={editForm.pfmea_id} onChange={(e) => setEditForm({ ...editForm, pfmea_id: e.target.value })} />
          </div>
          <div>
            <label>控制计划 ID</label>
            <Input value={editForm.control_plan_id} onChange={(e) => setEditForm({ ...editForm, control_plan_id: e.target.value })} />
          </div>
          <div>
            <label>PPAP ID</label>
            <Input value={editForm.ppap_submission_id} onChange={(e) => setEditForm({ ...editForm, ppap_submission_id: e.target.value })} />
          </div>
        </div>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/apqp/APQPDetailPage.tsx
git commit -m "feat(apqp): add APQP detail page with gate workflow"
```

---

### Task 9: Frontend Router + Sidebar

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Add routes to App.tsx**

In `frontend/src/App.tsx`, add the import:

```typescript
import APQPListPage from "./pages/apqp/APQPListPage";
import APQPDetailPage from "./pages/apqp/APQPDetailPage";
```

Add routes inside the protected layout `<Route>` block (after the SCAR routes):

```tsx
<Route path="/apqp" element={<APQPListPage />} />
<Route path="/apqp/:id" element={<APQPDetailPage />} />
```

- [ ] **Step 2: Add sidebar menu item**

In `frontend/src/components/layout/AppLayout.tsx`, add `ProjectOutlined` to the icons import from `@ant-design/icons`:

```typescript
ProjectOutlined,
```

Add the menu item after the control-plans entry:

```typescript
{ key: "/apqp", icon: <ProjectOutlined />, label: "APQP 质量策划" },
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no new type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(apqp): add APQP routes and sidebar menu item"
```

---

### Task 10: Verify End-to-End

- [ ] **Step 1: Start the backend**

```bash
cd backend && uvicorn app.main:app --port 8000 &
sleep 2
```

- [ ] **Step 2: Test the API with curl**

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"Admin@2026"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Stats
curl -s http://localhost:8000/api/apqp-projects/stats -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Create project
curl -s -X POST http://localhost:8000/api/apqp-projects -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"project_name":"Test APQP","product_name":"Test Product","product_line_code":"DC-DC-100"}' | python3 -m json.tool

# List projects
curl -s http://localhost:8000/api/apqp-projects -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: all endpoints return valid JSON without errors.

- [ ] **Step 3: Stop server with PID**

```bash
kill $(lsof -ti:8000) 2>/dev/null || true
```

---

### Task 11: Backend Tests (State Machine + Service)

**Files:**
- Create: `backend/tests/test_apqp_service.py`

- [ ] **Step 1: Create test file**

```python
# backend/tests/test_apqp_service.py
import pytest
import pytest_asyncio
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models.apqp import APQPProject
from app.models.user import User
from app.models.audit import AuditLog
from app.models.fmea import FMEADocument
from app.models.control_plan import ControlPlan
from app.models.supplier import Supplier, SupplierPPAPSubmission
from app.models.product_line import ProductLine
from app.database import Base
from app.services import apqp_service


TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/openqms_test"


@pytest_asyncio.fixture(scope="function")
async def db():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        # Seed required FK target
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


async def _make_project(db: AsyncSession, user: User, current_phase: int = 1, **kwargs) -> APQPProject:
    code = f"APQP-2026-TEST-{uuid.uuid4().hex[:6]}"
    proj = APQPProject(
        project_id=uuid.uuid4(), project_code=code,
        project_name="Test", product_name="TestProduct", product_line_code="DC-DC-100",
        created_by=user.user_id, current_phase=current_phase, **kwargs,
    )
    db.add(proj)
    await db.commit()
    return await apqp_service.get_project(db, proj.project_id)


class TestCreateProject:
    async def test_create_basic(self, db: AsyncSession):
        user = await _make_user(db, "test_create", "quality_engineer")
        proj = await apqp_service.create_project(
            db, project_name="APQP Test", product_name="Product X",
            product_line_code="DC-DC-100", user_id=user.user_id,
        )
        assert proj.project_code.startswith("APQP-2026-")
        assert proj.current_phase == 1
        assert proj.phase_status == "in_progress"
        assert proj.project_status == "active"

    async def test_create_with_invalid_dfmea(self, db: AsyncSession):
        user = await _make_user(db, "test_invalid_fk", "quality_engineer")
        fake_id = uuid.uuid4()
        with pytest.raises(ValueError, match="DFMEA"):
            await apqp_service.create_project(
                db, project_name="X", product_name="Y", product_line_code="DC-DC-100",
                user_id=user.user_id, dfmea_id=fake_id,
            )


class TestGateTransitions:
    async def test_submit_gate(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_submit", "manager")
        proj = await _make_project(db, manager)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        assert proj.phase_status == "pending_approval"
        assert proj.gate_history[-1]["action"] == "submit"

    async def test_approve_gate_advances_phase(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_advance", "manager")
        proj = await _make_project(db, manager)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        proj = await apqp_service.transition_project(
            db, proj, "approve_gate", manager.user_id, manager.display_name,
        )
        assert proj.current_phase == 2
        assert proj.phase_status == "in_progress"
        assert proj.phase_1_completed_at is not None

    async def test_approve_gate_requires_submit_first(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_require", "manager")
        proj = await _make_project(db, manager)
        with pytest.raises(ValueError, match="未提交审批"):
            await apqp_service.transition_project(
                db, proj, "approve_gate", manager.user_id, manager.display_name,
            )

    async def test_reject_gate_returns_to_in_progress(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_reject", "manager")
        proj = await _make_project(db, manager)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        proj = await apqp_service.transition_project(
            db, proj, "reject_gate", manager.user_id, manager.display_name,
        )
        assert proj.phase_status == "in_progress"
        assert proj.gate_history[-1]["action"] == "reject"

    async def test_phase_5_approve_completes_project(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_p5", "manager")
        proj = await _make_project(db, manager, current_phase=5)
        await db.commit()
        proj = await apqp_service.get_project(db, proj.project_id)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        proj = await apqp_service.transition_project(
            db, proj, "approve_gate", manager.user_id, manager.display_name,
        )
        assert proj.project_status == "completed"
        assert proj.phase_status == "completed"


class TestDeliverableChecks:
    async def _make_fmea(self, db: AsyncSession, fmea_type: str) -> FMEADocument:
        fmea = FMEADocument(
            fmea_id=uuid.uuid4(), document_no=f"FMEA-TEST-{uuid.uuid4().hex[:6]}",
            title=f"Test {fmea_type}", fmea_type=fmea_type,
            graph_data={"nodes": [], "edges": []},
        )
        db.add(fmea)
        await db.commit()
        return fmea

    async def test_phase_2_missing_dfmea(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_p2_check", "manager")
        proj = await _make_project(db, manager, current_phase=2, dfmea_id=None)
        # Submit gate for Phase 2
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        # Approve should fail because dfmea_id is None
        with pytest.raises(ValueError, match="DFMEA"):
            await apqp_service.transition_project(
                db, proj, "approve_gate", manager.user_id, manager.display_name,
            )

    async def test_phase_2_with_dfmea_passes(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_p2_ok", "manager")
        fmea = await self._make_fmea(db, "DFMEA")
        proj = await _make_project(db, manager, current_phase=2, dfmea_id=fmea.fmea_id)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        proj = await apqp_service.transition_project(
            db, proj, "approve_gate", manager.user_id, manager.display_name,
        )
        assert proj.current_phase == 3

    async def test_phase_3_missing_pfmea(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_p3_check", "manager")
        cp = ControlPlan(cp_id=uuid.uuid4(), document_no=f"CP-TEST-{uuid.uuid4().hex[:6]}",
                         title="Test CP", phase="production")
        db.add(cp)
        await db.commit()
        proj = await _make_project(db, manager, current_phase=3, pfmea_id=None, control_plan_id=cp.cp_id)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        with pytest.raises(ValueError, match="PFMEA"):
            await apqp_service.transition_project(
                db, proj, "approve_gate", manager.user_id, manager.display_name,
            )

    async def test_phase_4_missing_ppap(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_p4_check", "manager")
        proj = await _make_project(db, manager, current_phase=4, ppap_submission_id=None)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        with pytest.raises(ValueError, match="PPAP"):
            await apqp_service.transition_project(
                db, proj, "approve_gate", manager.user_id, manager.display_name,
            )


class TestGuardClauses:
    async def test_completed_project_cannot_transition(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_guard_c", "manager")
        proj = await _make_project(db, manager, project_status="completed", phase_status="completed")
        with pytest.raises(ValueError, match="不在进行中"):
            await apqp_service.transition_project(
                db, proj, "submit_gate", manager.user_id, manager.display_name,
            )

    async def test_cancelled_project_cannot_transition(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_guard_x", "manager")
        proj = await _make_project(db, manager, project_status="cancelled", phase_status="in_progress")
        with pytest.raises(ValueError, match="不在进行中"):
            await apqp_service.transition_project(
                db, proj, "submit_gate", manager.user_id, manager.display_name,
            )


class TestStats:
    async def test_stats_counts(self, db: AsyncSession):
        user = await _make_user(db, "test_stats", "quality_engineer")
        await _make_project(db, user)
        s = await apqp_service.get_stats(db)
        assert s["total_projects"] >= 1
        assert "phase_distribution" in s
```

- [ ] **Step 2: Run tests**

```bash
cd backend && python -m pytest tests/test_apqp_service.py -v 2>&1
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_apqp_service.py
git commit -m "test(apqp): add service layer tests for gate transitions and guards"
```

---

## Self-Review Summary

1. **Spec coverage**: All spec sections covered — model (Task 1), migration (Task 2), schemas (Task 3), service (Task 4), API routes (Task 5), types + API client (Task 6), list page (Task 7), detail page (Task 8), router + sidebar (Task 9), verification (Task 10), tests (Task 11).

2. **Field names corrected**: `document_no` (FMEA/CP), `part_no`/`part_name` (PPAP). `cp_code` → `document_no`. `submission_code` → `part_no`+`part_name`. Schema, _to_response(), TS types, and detail page all aligned.

3. **Update nullable fix**: `update_project` uses `**kwargs` with `exclude_unset=True` — "None" clears field, missing key skips.

4. **FK validation**: `create_project` validates linked IDs exist before insert, returns 400s.

5. **Navigation fix**: List page link uses `record.project_id` not `record.project_code`.
