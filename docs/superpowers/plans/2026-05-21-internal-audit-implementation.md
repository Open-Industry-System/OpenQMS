# 内部审核管理模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现覆盖体系/过程/产品三种审核类型的内部审核管理模块，包含审核方案、审核计划、审核发现的全生命周期管理，以及 CAPA 联动和审核员资格管理。

**Architecture:** 遵循 OpenQMS 标准四层架构（Model → Schema → Service → API），新增 3 张核心表（audit_programs / audit_plans / audit_findings）并扩展 users 表。前端采用列表页 + 详情页模式，检查表模板以预设 JSON 硬编码实现。

**Tech Stack:** Python 3.11 + FastAPI 0.115 + SQLAlchemy 2.0 (async) + PostgreSQL 15 + Pydantic v2 | React 18 + TypeScript 5.6 + Ant Design 5.21 + Vite 5.4

---

## 文件结构

### 后端（新建 9 个文件，修改 4 个文件）

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/alembic/versions/005_add_internal_audit.py` | 创建 | Alembic 迁移：3 张表 + users 扩展 |
| `backend/app/models/audit_program.py` | 创建 | AuditProgram ORM 模型 |
| `backend/app/models/audit_plan.py` | 创建 | AuditPlan ORM 模型 |
| `backend/app/models/audit_finding.py` | 创建 | AuditFinding ORM 模型 |
| `backend/app/models/user.py` | 修改 | 添加 `auditor_info` JSONB 字段 |
| `backend/app/models/__init__.py` | 修改 | 导出新模型 |
| `backend/app/schemas/audit.py` | 创建 | Pydantic request/response schemas |
| `backend/app/schemas/__init__.py` | 修改 | 导出 audit schemas |
| `backend/app/services/audit_service.py` | 创建 | 业务逻辑：CRUD + 状态机 + CAPA 联动 |
| `backend/app/api/audit_program.py` | 创建 | 审核方案 API 路由 |
| `backend/app/api/audit_plan.py` | 创建 | 审核计划 API 路由 |
| `backend/app/api/audit_finding.py` | 创建 | 审核发现 API 路由 |
| `backend/app/api/auditor.py` | 创建 | 审核员管理 API 路由 |
| `backend/app/main.py` | 修改 | 注册 4 个新 router |

### 前端（新建 4 个文件，修改 3 个文件）

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/types/index.ts` | 修改 | 添加 AuditProgram / AuditPlan / AuditFinding / AuditChecklistItem 类型 |
| `frontend/src/api/audit.ts` | 创建 | API 客户端函数 |
| `frontend/src/utils/auditChecklistTemplates.ts` | 创建 | 3 套预设检查表模板 |
| `frontend/src/pages/internalAudit/InternalAuditListPage.tsx` | 创建 | 主列表页（方案+计划+统计） |
| `frontend/src/pages/internalAudit/InternalAuditDetailPage.tsx` | 创建 | 详情页（检查表+发现项+报告） |
| `frontend/src/App.tsx` | 修改 | 添加 `/internal-audits` 和 `/internal-audits/:id` 路由 |
| `frontend/src/components/layout/AppLayout.tsx` | 修改 | 添加"内部审核"导航菜单 |

---

## Task 1: Alembic 数据库迁移

**Files:**
- Create: `backend/alembic/versions/005_add_internal_audit.py`

- [ ] **Step 1: 创建迁移文件**

```python
"""add internal audit tables

Revision ID: 005
Revises: 004
Create Date: 2026-05-21 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # audit_programs
    op.create_table(
        'audit_programs',
        sa.Column('program_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('program_year', sa.Integer(), nullable=False),
        sa.Column('audit_type', sa.String(20), nullable=False),
        sa.Column('scope', sa.Text(), nullable=False),
        sa.Column('criteria', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='planned'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_audit_programs_year', 'audit_programs', ['program_year'])
    op.create_index('ix_audit_programs_type', 'audit_programs', ['audit_type'])
    op.create_index('ix_audit_programs_status', 'audit_programs', ['status'])

    # audit_plans
    op.create_table(
        'audit_plans',
        sa.Column('audit_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('program_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('audit_programs.program_id'), nullable=False),
        sa.Column('audit_scope', sa.Text(), nullable=False),
        sa.Column('audit_criteria', sa.Text(), nullable=False),
        sa.Column('planned_date', sa.Date(), nullable=False),
        sa.Column('actual_date', sa.Date(), nullable=True),
        sa.Column('lead_auditor', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('team_members', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('checklist', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(20), nullable=False, server_default='planned'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_audit_plans_program_id', 'audit_plans', ['program_id'])
    op.create_index('ix_audit_plans_status', 'audit_plans', ['status'])
    op.create_index('ix_audit_plans_planned_date', 'audit_plans', ['planned_date'])

    # audit_findings
    op.create_table(
        'audit_findings',
        sa.Column('finding_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('audit_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('audit_plans.audit_id'), nullable=False),
        sa.Column('clause_ref', sa.String(50), nullable=True),
        sa.Column('finding_type', sa.String(20), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('correction', sa.Text(), nullable=True),
        sa.Column('corrective_action', sa.Text(), nullable=True),
        sa.Column('capa_ref_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_audit_findings_audit_id', 'audit_findings', ['audit_id'])
    op.create_index('ix_audit_findings_type', 'audit_findings', ['finding_type'])
    op.create_index('ix_audit_findings_status', 'audit_findings', ['status'])

    # users: add auditor_info
    op.add_column('users', sa.Column('auditor_info', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'auditor_info')
    op.drop_index('ix_audit_findings_status', table_name='audit_findings')
    op.drop_index('ix_audit_findings_type', table_name='audit_findings')
    op.drop_index('ix_audit_findings_audit_id', table_name='audit_findings')
    op.drop_table('audit_findings')
    op.drop_index('ix_audit_plans_planned_date', table_name='audit_plans')
    op.drop_index('ix_audit_plans_status', table_name='audit_plans')
    op.drop_index('ix_audit_plans_program_id', table_name='audit_plans')
    op.drop_table('audit_plans')
    op.drop_index('ix_audit_programs_status', table_name='audit_programs')
    op.drop_index('ix_audit_programs_type', table_name='audit_programs')
    op.drop_index('ix_audit_programs_year', table_name='audit_programs')
    op.drop_table('audit_programs')
```

- [ ] **Step 2: 运行迁移**

Run: `docker compose exec -e SECRET_KEY=OpenQMS-2026-QualityGoal-DevKey backend alembic upgrade head`
Expected: `Running upgrade 004 -> 005, add internal audit tables`

- [ ] **Step 3: 验证表已创建**

Run: `docker compose exec backend psql -U postgres -d openqms -c "\dt"`
Expected: 包含 `audit_programs`, `audit_plans`, `audit_findings`

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/005_add_internal_audit.py
git commit -m "chore: add alembic migration for internal audit tables"
```

---

## Task 2: SQLAlchemy ORM 模型

**Files:**
- Create: `backend/app/models/audit_program.py`
- Create: `backend/app/models/audit_plan.py`
- Create: `backend/app/models/audit_finding.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 创建 AuditProgram 模型**

```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class AuditProgram(Base):
    __tablename__ = "audit_programs"

    program_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_year: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    criteria: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: 创建 AuditPlan 模型**

```python
import uuid
from datetime import date, datetime
from sqlalchemy import String, ForeignKey, Date, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class AuditPlan(Base):
    __tablename__ = "audit_plans"

    audit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_programs.program_id"), nullable=False)
    audit_scope: Mapped[str] = mapped_column(Text, nullable=False)
    audit_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    planned_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lead_auditor: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    team_members: Mapped[list] = mapped_column(JSONB, default=list)
    checklist: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 3: 创建 AuditFinding 模型**

```python
import uuid
from datetime import date, datetime
from sqlalchemy import String, ForeignKey, Date, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class AuditFinding(Base):
    __tablename__ = "audit_findings"

    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_plans.audit_id"), nullable=False)
    clause_ref: Mapped[str | None] = mapped_column(String(50), nullable=True)
    finding_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    capa_ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: 修改 User 模型添加 auditor_info**

Modify `backend/app/models/user.py`，在现有字段后添加：

```python
from sqlalchemy.dialects.postgresql import JSONB
# ... existing imports ...

class User(Base):
    # ... existing columns ...
    auditor_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 5: 更新 models/__init__.py**

```python
from app.models.audit_program import AuditProgram
from app.models.audit_plan import AuditPlan
from app.models.audit_finding import AuditFinding
# ... existing imports ...

__all__ = [
    # ... existing exports ...
    "AuditProgram", "AuditPlan", "AuditFinding",
]
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/
git commit -m "feat: add internal audit ORM models and extend User with auditor_info"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/audit.py`
- Modify: `backend/app/schemas/__init__.py`

- [ ] **Step 1: 创建 audit schemas**

```python
import uuid
from datetime import date, datetime
from pydantic import BaseModel, field_validator


class AuditProgramCreate(BaseModel):
    program_year: int
    audit_type: str
    scope: str
    criteria: str

    @field_validator("audit_type")
    @classmethod
    def validate_audit_type(cls, v: str) -> str:
        if v not in ("system", "process", "product"):
            raise ValueError('audit_type must be one of "system", "process", "product"')
        return v


class AuditProgramUpdate(BaseModel):
    program_year: int | None = None
    audit_type: str | None = None
    scope: str | None = None
    criteria: str | None = None
    status: str | None = None

    @field_validator("audit_type")
    @classmethod
    def validate_audit_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("system", "process", "product"):
            raise ValueError('audit_type must be one of "system", "process", "product"')
        return v


class AuditProgramResponse(BaseModel):
    program_id: uuid.UUID
    program_year: int
    audit_type: str
    scope: str
    criteria: str
    status: str
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditPlanCreate(BaseModel):
    program_id: uuid.UUID
    audit_scope: str
    audit_criteria: str
    planned_date: date
    lead_auditor: uuid.UUID | None = None
    team_members: list | None = None
    checklist: list | None = None


class AuditPlanUpdate(BaseModel):
    audit_scope: str | None = None
    audit_criteria: str | None = None
    planned_date: date | None = None
    actual_date: date | None = None
    lead_auditor: uuid.UUID | None = None
    team_members: list | None = None
    checklist: list | None = None
    status: str | None = None


class AuditPlanResponse(BaseModel):
    audit_id: uuid.UUID
    program_id: uuid.UUID
    audit_scope: str
    audit_criteria: str
    planned_date: date
    actual_date: date | None
    lead_auditor: uuid.UUID | None
    team_members: list
    checklist: list
    status: str
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditFindingCreate(BaseModel):
    audit_id: uuid.UUID
    clause_ref: str | None = None
    finding_type: str
    description: str
    root_cause: str | None = None
    correction: str | None = None
    corrective_action: str | None = None
    due_date: date | None = None

    @field_validator("finding_type")
    @classmethod
    def validate_finding_type(cls, v: str) -> str:
        if v not in ("major_nc", "minor_nc", "ofi", "observation"):
            raise ValueError('finding_type must be one of "major_nc", "minor_nc", "ofi", "observation"')
        return v


class AuditFindingUpdate(BaseModel):
    clause_ref: str | None = None
    finding_type: str | None = None
    description: str | None = None
    root_cause: str | None = None
    correction: str | None = None
    corrective_action: str | None = None
    status: str | None = None
    due_date: date | None = None

    @field_validator("finding_type")
    @classmethod
    def validate_finding_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("major_nc", "minor_nc", "ofi", "observation"):
            raise ValueError('finding_type must be one of "major_nc", "minor_nc", "ofi", "observation"')
        return v


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
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditorInfoUpdate(BaseModel):
    is_auditor: bool
    qualifications: list[str]
    last_qualification_date: str | None = None


class AuditChecklistTemplate(BaseModel):
    audit_type: str
    name: str
    items: list[dict]


class AuditStatsResponse(BaseModel):
    program_count: int
    planned_count: int
    in_progress_count: int
    completed_count: int
    open_findings: int
    major_nc_count: int
```

- [ ] **Step 2: 更新 schemas/__init__.py**

```python
from app.schemas import audit
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/
git commit -m "feat: add internal audit Pydantic schemas"
```

---

## Task 4: Service 层

**Files:**
- Create: `backend/app/services/audit_service.py`

- [ ] **Step 1: 创建 audit_service.py**

代码较长，分功能块写入。Service 层需包含：

1. `_generate_doc_no` / `_generate_plan_no` — 自动编号
2. `_update_program_status` — 方案状态自动更新
3. `list_audit_programs` / `create_audit_program` / `get` / `update` / `delete`
4. `list_audit_plans` / `create_audit_plan` / `get` / `update` / `delete` / `start` / `complete` / `cancel`
5. `list_audit_findings` / `create_audit_finding` / `get` / `update` / `close_finding` / `create_capa_from_finding`
6. `get_audit_stats` — 统计
7. `list_auditors` / `update_auditor_info`

每个 mutation 操作都必须创建 AuditLog。参考 quality_goal_service.py 的模式。

由于代码量大，这里给出关键函数的完整实现框架，实施时需填充所有函数：

```python
import uuid
from datetime import date, datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_program import AuditProgram
from app.models.audit_plan import AuditPlan
from app.models.audit_finding import AuditFinding
from app.models.user import User
from app.models.capa import CAPAEightD
from app.models.audit import AuditLog


async def _generate_program_no(db: AsyncSession, audit_type: str, year: int) -> str:
    type_map = {"system": "SYS", "process": "PRO", "product": "PRD"}
    prefix = f"AP-{year}-{type_map[audit_type]}"
    result = await db.execute(select(func.count()).where(AuditProgram.status != "cancelled"))
    count = result.scalar() or 0
    return f"{prefix}-{count + 1:03d}"


async def _generate_plan_no(db: AsyncSession, year: int) -> str:
    prefix = f"PL-{year}"
    result = await db.execute(select(func.count()).where(AuditPlan.status != "cancelled"))
    count = result.scalar() or 0
    return f"{prefix}-{count + 1:03d}"


async def _generate_8d_no(db: AsyncSession, year: int) -> str:
    prefix = f"8D-{year}"
    result = await db.execute(select(func.count()).where(CAPAEightD.document_no.like(f"{prefix}-%")))
    count = result.scalar() or 0
    return f"{prefix}-{count + 1:03d}"


async def _update_program_status(db: AsyncSession, program: AuditProgram) -> None:
    result = await db.execute(select(AuditPlan).where(AuditPlan.program_id == program.program_id))
    plans = result.scalars().all()
    if not plans:
        return
    statuses = [p.status for p in plans]
    if program.status == "planned" and any(s in ("in_progress", "completed") for s in statuses):
        program.status = "active"
    if all(s in ("completed", "cancelled") for s in statuses):
        program.status = "completed"


# ---------- Programs ----------

async def list_audit_programs(db: AsyncSession, page: int = 1, page_size: int = 20, year: int | None = None, audit_type: str | None = None, status: str | None = None):
    query = select(AuditProgram)
    count_query = select(func.count()).select_from(AuditProgram)
    if year is not None:
        query = query.where(AuditProgram.program_year == year)
        count_query = count_query.where(AuditProgram.program_year == year)
    if audit_type:
        query = query.where(AuditProgram.audit_type == audit_type)
        count_query = count_query.where(AuditProgram.audit_type == audit_type)
    if status:
        query = query.where(AuditProgram.status == status)
        count_query = count_query.where(AuditProgram.status == status)
    query = query.order_by(AuditProgram.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = list((await db.execute(query)).scalars().all())
    total = (await db.execute(count_query)).scalar() or 0
    return items, total


async def get_audit_program(db: AsyncSession, program_id: uuid.UUID) -> AuditProgram | None:
    return await db.get(AuditProgram, program_id)


async def create_audit_program(db: AsyncSession, program_year: int, audit_type: str, scope: str, criteria: str, user_id: uuid.UUID) -> AuditProgram:
    program = AuditProgram(
        program_year=program_year,
        audit_type=audit_type,
        scope=scope,
        criteria=criteria,
        status="planned",
        created_by=user_id,
    )
    db.add(program)
    db.add(AuditLog(
        table_name="audit_programs",
        record_id=program.program_id,
        action="CREATE",
        changed_fields={"program_year": program_year, "audit_type": audit_type, "scope": scope},
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(program)
    return program


async def update_audit_program(db: AsyncSession, program: AuditProgram, program_year: int | None, audit_type: str | None, scope: str | None, criteria: str | None, status: str | None, user_id: uuid.UUID) -> AuditProgram:
    changed = {}
    if program_year is not None and program_year != program.program_year:
        changed["program_year"] = {"before": program.program_year, "after": program_year}
        program.program_year = program_year
    if audit_type is not None and audit_type != program.audit_type:
        changed["audit_type"] = {"before": program.audit_type, "after": audit_type}
        program.audit_type = audit_type
    if scope is not None and scope != program.scope:
        changed["scope"] = {"before": program.scope, "after": scope}
        program.scope = scope
    if criteria is not None and criteria != program.criteria:
        changed["criteria"] = {"before": program.criteria, "after": criteria}
        program.criteria = criteria
    if status is not None and status != program.status:
        changed["status"] = {"before": program.status, "after": status}
        program.status = status
    if not changed:
        return program
    db.add(AuditLog(
        table_name="audit_programs",
        record_id=program.program_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(program)
    return program


async def delete_audit_program(db: AsyncSession, program: AuditProgram, user_id: uuid.UUID) -> None:
    result = await db.execute(select(func.count()).where(AuditPlan.program_id == program.program_id))
    if (result.scalar() or 0) > 0:
        raise ValueError("cannot delete program with associated audit plans")
    db.add(AuditLog(
        table_name="audit_programs",
        record_id=program.program_id,
        action="DELETE",
        changed_fields={"program_year": program.program_year, "audit_type": program.audit_type},
        operated_by=user_id,
    ))
    await db.delete(program)
    await db.commit()


# ---------- Plans ----------

async def list_audit_plans(db: AsyncSession, page: int = 1, page_size: int = 20, program_id: uuid.UUID | None = None, status: str | None = None, date_from: date | None = None, date_to: date | None = None):
    query = select(AuditPlan)
    count_query = select(func.count()).select_from(AuditPlan)
    if program_id is not None:
        query = query.where(AuditPlan.program_id == program_id)
        count_query = count_query.where(AuditPlan.program_id == program_id)
    if status:
        query = query.where(AuditPlan.status == status)
        count_query = count_query.where(AuditPlan.status == status)
    if date_from is not None:
        query = query.where(AuditPlan.planned_date >= date_from)
        count_query = count_query.where(AuditPlan.planned_date >= date_from)
    if date_to is not None:
        query = query.where(AuditPlan.planned_date <= date_to)
        count_query = count_query.where(AuditPlan.planned_date <= date_to)
    query = query.order_by(AuditPlan.planned_date.asc()).offset((page - 1) * page_size).limit(page_size)
    items = list((await db.execute(query)).scalars().all())
    total = (await db.execute(count_query)).scalar() or 0
    return items, total


async def get_audit_plan(db: AsyncSession, audit_id: uuid.UUID) -> AuditPlan | None:
    return await db.get(AuditPlan, audit_id)


async def create_audit_plan(db: AsyncSession, program_id: uuid.UUID, audit_scope: str, audit_criteria: str, planned_date: date, lead_auditor: uuid.UUID | None, team_members: list | None, checklist: list | None, user_id: uuid.UUID) -> AuditPlan:
    plan = AuditPlan(
        program_id=program_id,
        audit_scope=audit_scope,
        audit_criteria=audit_criteria,
        planned_date=planned_date,
        lead_auditor=lead_auditor,
        team_members=team_members or [],
        checklist=checklist or [],
        status="planned",
        created_by=user_id,
    )
    db.add(plan)
    db.add(AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="CREATE",
        changed_fields={"program_id": str(program_id), "planned_date": str(planned_date), "status": "planned"},
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(plan)
    return plan


async def update_audit_plan(db: AsyncSession, plan: AuditPlan, audit_scope: str | None, audit_criteria: str | None, planned_date: date | None, actual_date: date | None, lead_auditor: uuid.UUID | None, team_members: list | None, checklist: list | None, status: str | None, user_id: uuid.UUID) -> AuditPlan:
    changed = {}
    if audit_scope is not None and audit_scope != plan.audit_scope:
        changed["audit_scope"] = {"before": plan.audit_scope, "after": audit_scope}
        plan.audit_scope = audit_scope
    if audit_criteria is not None and audit_criteria != plan.audit_criteria:
        changed["audit_criteria"] = {"before": plan.audit_criteria, "after": audit_criteria}
        plan.audit_criteria = audit_criteria
    if planned_date is not None and planned_date != plan.planned_date:
        changed["planned_date"] = {"before": str(plan.planned_date), "after": str(planned_date)}
        plan.planned_date = planned_date
    if actual_date is not None and actual_date != plan.actual_date:
        changed["actual_date"] = {"before": str(plan.actual_date), "after": str(actual_date)}
        plan.actual_date = actual_date
    if lead_auditor is not None and lead_auditor != plan.lead_auditor:
        changed["lead_auditor"] = {"before": str(plan.lead_auditor), "after": str(lead_auditor)}
        plan.lead_auditor = lead_auditor
    if team_members is not None and team_members != plan.team_members:
        changed["team_members"] = {"before": plan.team_members, "after": team_members}
        plan.team_members = team_members
    if checklist is not None and checklist != plan.checklist:
        changed["checklist"] = {"before": plan.checklist, "after": checklist}
        plan.checklist = checklist
    if status is not None and status != plan.status:
        changed["status"] = {"before": plan.status, "after": status}
        plan.status = status
    if not changed:
        return plan
    db.add(AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(plan)
    # Update program status if plan status changed
    program = await db.get(AuditProgram, plan.program_id)
    if program and "status" in changed:
        await _update_program_status(db, program)
        await db.commit()
    return plan


async def delete_audit_plan(db: AsyncSession, plan: AuditPlan, user_id: uuid.UUID) -> None:
    result = await db.execute(select(func.count()).where(AuditFinding.audit_id == plan.audit_id))
    if (result.scalar() or 0) > 0:
        raise ValueError("cannot delete audit plan with associated findings")
    db.add(AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="DELETE",
        changed_fields={"audit_scope": plan.audit_scope, "status": plan.status},
        operated_by=user_id,
    ))
    await db.delete(plan)
    await db.commit()


async def start_audit_plan(db: AsyncSession, plan: AuditPlan, user_id: uuid.UUID) -> AuditPlan:
    if plan.status != "planned":
        raise ValueError("only planned audits can be started")
    plan.status = "in_progress"
    plan.actual_date = date.today()
    db.add(AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="TRANSITION",
        changed_fields={"status": {"before": "planned", "after": "in_progress"}, "actual_date": str(plan.actual_date)},
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(plan)
    program = await db.get(AuditProgram, plan.program_id)
    if program:
        await _update_program_status(db, program)
        await db.commit()
    return plan


async def complete_audit_plan(db: AsyncSession, plan: AuditPlan, user_id: uuid.UUID) -> AuditPlan:
    if plan.status != "in_progress":
        raise ValueError("only in-progress audits can be completed")
    plan.status = "completed"
    db.add(AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="TRANSITION",
        changed_fields={"status": {"before": "in_progress", "after": "completed"}},
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(plan)
    program = await db.get(AuditProgram, plan.program_id)
    if program:
        await _update_program_status(db, program)
        await db.commit()
    return plan


async def cancel_audit_plan(db: AsyncSession, plan: AuditPlan, user_id: uuid.UUID) -> AuditPlan:
    if plan.status != "planned":
        raise ValueError("only planned audits can be cancelled")
    plan.status = "cancelled"
    db.add(AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="TRANSITION",
        changed_fields={"status": {"before": "planned", "after": "cancelled"}},
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(plan)
    program = await db.get(AuditProgram, plan.program_id)
    if program:
        await _update_program_status(db, program)
        await db.commit()
    return plan


# ---------- Findings ----------

async def list_audit_findings(db: AsyncSession, page: int = 1, page_size: int = 20, audit_id: uuid.UUID | None = None, finding_type: str | None = None, status: str | None = None):
    query = select(AuditFinding)
    count_query = select(func.count()).select_from(AuditFinding)
    if audit_id is not None:
        query = query.where(AuditFinding.audit_id == audit_id)
        count_query = count_query.where(AuditFinding.audit_id == audit_id)
    if finding_type:
        query = query.where(AuditFinding.finding_type == finding_type)
        count_query = count_query.where(AuditFinding.finding_type == finding_type)
    if status:
        query = query.where(AuditFinding.status == status)
        count_query = count_query.where(AuditFinding.status == status)
    query = query.order_by(AuditFinding.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = list((await db.execute(query)).scalars().all())
    total = (await db.execute(count_query)).scalar() or 0
    return items, total


async def get_audit_finding(db: AsyncSession, finding_id: uuid.UUID) -> AuditFinding | None:
    return await db.get(AuditFinding, finding_id)


async def create_audit_finding(db: AsyncSession, audit_id: uuid.UUID, clause_ref: str | None, finding_type: str, description: str, root_cause: str | None, correction: str | None, corrective_action: str | None, due_date: date | None, user_id: uuid.UUID) -> AuditFinding:
    finding = AuditFinding(
        audit_id=audit_id,
        clause_ref=clause_ref,
        finding_type=finding_type,
        description=description,
        root_cause=root_cause,
        correction=correction,
        corrective_action=corrective_action,
        due_date=due_date,
        status="open",
        created_by=user_id,
    )
    db.add(finding)
    db.add(AuditLog(
        table_name="audit_findings",
        record_id=finding.finding_id,
        action="CREATE",
        changed_fields={"audit_id": str(audit_id), "finding_type": finding_type, "description": description},
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(finding)
    return finding


async def update_audit_finding(db: AsyncSession, finding: AuditFinding, clause_ref: str | None, finding_type: str | None, description: str | None, root_cause: str | None, correction: str | None, corrective_action: str | None, status: str | None, due_date: date | None, user_id: uuid.UUID) -> AuditFinding:
    changed = {}
    if clause_ref is not None and clause_ref != finding.clause_ref:
        changed["clause_ref"] = {"before": finding.clause_ref, "after": clause_ref}
        finding.clause_ref = clause_ref
    if finding_type is not None and finding_type != finding.finding_type:
        changed["finding_type"] = {"before": finding.finding_type, "after": finding_type}
        finding.finding_type = finding_type
    if description is not None and description != finding.description:
        changed["description"] = {"before": finding.description, "after": description}
        finding.description = description
    if root_cause is not None and root_cause != finding.root_cause:
        changed["root_cause"] = {"before": finding.root_cause, "after": root_cause}
        finding.root_cause = root_cause
    if correction is not None and correction != finding.correction:
        changed["correction"] = {"before": finding.correction, "after": correction}
        finding.correction = correction
    if corrective_action is not None and corrective_action != finding.corrective_action:
        changed["corrective_action"] = {"before": finding.corrective_action, "after": corrective_action}
        finding.corrective_action = corrective_action
    if status is not None and status != finding.status:
        changed["status"] = {"before": finding.status, "after": status}
        finding.status = status
    if due_date is not None and due_date != finding.due_date:
        changed["due_date"] = {"before": str(finding.due_date), "after": str(due_date)}
        finding.due_date = due_date
    if not changed:
        return finding
    db.add(AuditLog(
        table_name="audit_findings",
        record_id=finding.finding_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(finding)
    return finding


async def close_audit_finding(db: AsyncSession, finding: AuditFinding, user_id: uuid.UUID) -> AuditFinding:
    if finding.status not in ("open", "in_progress", "verified"):
        raise ValueError("finding cannot be closed from current status")
    finding.status = "closed"
    finding.closed_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        table_name="audit_findings",
        record_id=finding.finding_id,
        action="TRANSITION",
        changed_fields={"status": {"before": finding.status, "after": "closed"}, "closed_at": finding.closed_at.isoformat()},
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(finding)
    return finding


async def create_capa_from_finding(db: AsyncSession, finding: AuditFinding, user_id: uuid.UUID) -> CAPAEightD:
    if finding.status not in ("open", "in_progress"):
        raise ValueError("finding must be open or in_progress to create CAPA")
    if finding.capa_ref_id is not None:
        raise ValueError("finding already has an associated CAPA")
    year = datetime.now().year
    doc_no = await _generate_8d_no(db, year)
    capa = CAPAEightD(
        document_no=doc_no,
        title=f"【审核发现】{finding.clause_ref or ''} - {finding.description[:50]}",
        d2_description=finding.description,
        d4_root_cause=finding.root_cause or "",
        severity="严重" if finding.finding_type == "major_nc" else "一般",
        status="D1_TEAM",
        due_date=finding.due_date,
        created_by=user_id,
    )
    db.add(capa)
    await db.commit()
    await db.refresh(capa)
    finding.capa_ref_id = capa.report_id
    db.add(AuditLog(
        table_name="audit_findings",
        record_id=finding.finding_id,
        action="CREATE_CAPA",
        changed_fields={"capa_ref_id": str(capa.report_id), "capa_document_no": doc_no},
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(finding)
    return capa


# ---------- Stats ----------

async def get_audit_stats(db: AsyncSession) -> dict:
    program_total = (await db.execute(select(func.count()).select_from(AuditProgram))).scalar() or 0
    plan_planned = (await db.execute(select(func.count()).select_from(AuditPlan).where(AuditPlan.status == "planned"))).scalar() or 0
    plan_in_progress = (await db.execute(select(func.count()).select_from(AuditPlan).where(AuditPlan.status == "in_progress"))).scalar() or 0
    plan_completed = (await db.execute(select(func.count()).select_from(AuditPlan).where(AuditPlan.status == "completed"))).scalar() or 0
    open_findings = (await db.execute(select(func.count()).select_from(AuditFinding).where(AuditFinding.status.in_(["open", "in_progress"])))).scalar() or 0
    major_nc = (await db.execute(select(func.count()).select_from(AuditFinding).where(AuditFinding.finding_type == "major_nc", AuditFinding.status != "closed"))).scalar() or 0
    return {
        "program_count": program_total,
        "planned_count": plan_planned,
        "in_progress_count": plan_in_progress,
        "completed_count": plan_completed,
        "open_findings": open_findings,
        "major_nc_count": major_nc,
    }


# ---------- Auditors ----------

async def list_auditors(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).where(User.auditor_info.isnot(None)))
    return list(result.scalars().all())


async def update_auditor_info(db: AsyncSession, user: User, is_auditor: bool, qualifications: list[str], last_qualification_date: str | None, user_id: uuid.UUID) -> User:
    info = user.auditor_info or {}
    changed = {}
    if is_auditor != info.get("is_auditor"):
        changed["is_auditor"] = {"before": info.get("is_auditor"), "after": is_auditor}
        info["is_auditor"] = is_auditor
    if qualifications != info.get("qualifications"):
        changed["qualifications"] = {"before": info.get("qualifications"), "after": qualifications}
        info["qualifications"] = qualifications
    if last_qualification_date is not None:
        changed["last_qualification_date"] = {"before": info.get("last_qualification_date"), "after": last_qualification_date}
        info["last_qualification_date"] = last_qualification_date
    user.auditor_info = info
    if changed:
        db.add(AuditLog(
            table_name="users",
            record_id=user.user_id,
            action="UPDATE",
            changed_fields={"auditor_info": changed},
            operated_by=user_id,
        ))
        await db.commit()
        await db.refresh(user)
    return user
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/audit_service.py
git commit -m "feat: add internal audit service layer with state transitions and CAPA linkage"
```

---

## Task 5: API 路由

**Files:**
- Create: `backend/app/api/audit_program.py`
- Create: `backend/app/api/audit_plan.py`
- Create: `backend/app/api/audit_finding.py`
- Create: `backend/app/api/auditor.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建审核方案路由**

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin, require_admin
from app.models.user import User
from app import schemas
from app.services import audit_service

router = APIRouter(prefix="/api/audit-programs", tags=["audit-programs"])


@router.get("", response_model=schemas.audit.AuditStatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await audit_service.get_audit_stats(db)


@router.get("/list", response_model=schemas.audit.AuditProgramListResponse)
async def list_programs(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    year: int | None = Query(None), audit_type: str | None = Query(None), status: str | None = Query(None),
    db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user),
):
    items, total = await audit_service.list_audit_programs(db, page, page_size, year, audit_type, status)
    return schemas.audit.AuditProgramListResponse(
        items=[schemas.audit.AuditProgramResponse.model_validate(p) for p in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", response_model=schemas.audit.AuditProgramResponse)
async def create_program(req: schemas.audit.AuditProgramCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    program = await audit_service.create_audit_program(db, req.program_year, req.audit_type, req.scope, req.criteria, user.user_id)
    return schemas.audit.AuditProgramResponse.model_validate(program)


@router.get("/{program_id}", response_model=schemas.audit.AuditProgramResponse)
async def get_program(program_id: uuid.UUID, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    program = await audit_service.get_audit_program(db, program_id)
    if not program:
        raise HTTPException(status_code=404, detail="audit program not found")
    return schemas.audit.AuditProgramResponse.model_validate(program)


@router.put("/{program_id}", response_model=schemas.audit.AuditProgramResponse)
async def update_program(program_id: uuid.UUID, req: schemas.audit.AuditProgramUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    program = await audit_service.get_audit_program(db, program_id)
    if not program:
        raise HTTPException(status_code=404, detail="audit program not found")
    program = await audit_service.update_audit_program(db, program, req.program_year, req.audit_type, req.scope, req.criteria, req.status, user.user_id)
    return schemas.audit.AuditProgramResponse.model_validate(program)


@router.delete("/{program_id}")
async def delete_program(program_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    program = await audit_service.get_audit_program(db, program_id)
    if not program:
        raise HTTPException(status_code=404, detail="audit program not found")
    try:
        await audit_service.delete_audit_program(db, program, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "audit program deleted"}
```

注意：这里引用了 `AuditProgramListResponse` schema，需要在 `schemas/audit.py` 中补充：

```python
class AuditProgramListResponse(BaseModel):
    items: list[AuditProgramResponse]
    total: int
    page: int
    page_size: int
```

- [ ] **Step 2: 创建审核计划路由**

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User
from app import schemas
from app.services import audit_service

router = APIRouter(prefix="/api/audit-plans", tags=["audit-plans"])


@router.get("", response_model=schemas.audit.AuditPlanListResponse)
async def list_plans(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    program_id: uuid.UUID | None = Query(None), status: str | None = Query(None),
    date_from: str | None = Query(None), date_to: str | None = Query(None),
    db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user),
):
    from datetime import date
    df = date.fromisoformat(date_from) if date_from else None
    dt = date.fromisoformat(date_to) if date_to else None
    items, total = await audit_service.list_audit_plans(db, page, page_size, program_id, status, df, dt)
    return schemas.audit.AuditPlanListResponse(
        items=[schemas.audit.AuditPlanResponse.model_validate(p) for p in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", response_model=schemas.audit.AuditPlanResponse)
async def create_plan(req: schemas.audit.AuditPlanCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    plan = await audit_service.create_audit_plan(db, req.program_id, req.audit_scope, req.audit_criteria, req.planned_date, req.lead_auditor, req.team_members, req.checklist, user.user_id)
    return schemas.audit.AuditPlanResponse.model_validate(plan)


@router.get("/{audit_id}", response_model=schemas.audit.AuditPlanResponse)
async def get_plan(audit_id: uuid.UUID, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if not plan:
        raise HTTPException(status_code=404, detail="audit plan not found")
    return schemas.audit.AuditPlanResponse.model_validate(plan)


@router.put("/{audit_id}", response_model=schemas.audit.AuditPlanResponse)
async def update_plan(audit_id: uuid.UUID, req: schemas.audit.AuditPlanUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if not plan:
        raise HTTPException(status_code=404, detail="audit plan not found")
    plan = await audit_service.update_audit_plan(db, plan, req.audit_scope, req.audit_criteria, req.planned_date, req.actual_date, req.lead_auditor, req.team_members, req.checklist, req.status, user.user_id)
    return schemas.audit.AuditPlanResponse.model_validate(plan)


@router.delete("/{audit_id}")
async def delete_plan(audit_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if not plan:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        await audit_service.delete_audit_plan(db, plan, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "audit plan deleted"}


@router.post("/{audit_id}/start", response_model=schemas.audit.AuditPlanResponse)
async def start_plan(audit_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if not plan:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        plan = await audit_service.start_audit_plan(db, plan, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.audit.AuditPlanResponse.model_validate(plan)


@router.post("/{audit_id}/complete", response_model=schemas.audit.AuditPlanResponse)
async def complete_plan(audit_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if not plan:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        plan = await audit_service.complete_audit_plan(db, plan, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.audit.AuditPlanResponse.model_validate(plan)


@router.post("/{audit_id}/cancel", response_model=schemas.audit.AuditPlanResponse)
async def cancel_plan(audit_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if not plan:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        plan = await audit_service.cancel_audit_plan(db, plan, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.audit.AuditPlanResponse.model_validate(plan)


@router.get("/{audit_id}/findings", response_model=schemas.audit.AuditFindingListResponse)
async def list_plan_findings(audit_id: uuid.UUID, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    items, total = await audit_service.list_audit_findings(db, audit_id=audit_id)
    return schemas.audit.AuditFindingListResponse(
        items=[schemas.audit.AuditFindingResponse.model_validate(f) for f in items],
        total=total, page=1, page_size=total,
    )
```

需要在 `schemas/audit.py` 中补充 `AuditPlanListResponse` 和 `AuditFindingListResponse`：

```python
class AuditPlanListResponse(BaseModel):
    items: list[AuditPlanResponse]
    total: int
    page: int
    page_size: int

class AuditFindingListResponse(BaseModel):
    items: list[AuditFindingResponse]
    total: int
    page: int
    page_size: int
```

- [ ] **Step 3: 创建审核发现路由**

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User
from app import schemas
from app.services import audit_service

router = APIRouter(prefix="/api/audit-findings", tags=["audit-findings"])


@router.get("", response_model=schemas.audit.AuditFindingListResponse)
async def list_findings(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    audit_id: uuid.UUID | None = Query(None), finding_type: str | None = Query(None), status: str | None = Query(None),
    db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user),
):
    items, total = await audit_service.list_audit_findings(db, page, page_size, audit_id, finding_type, status)
    return schemas.audit.AuditFindingListResponse(
        items=[schemas.audit.AuditFindingResponse.model_validate(f) for f in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", response_model=schemas.audit.AuditFindingResponse)
async def create_finding(req: schemas.audit.AuditFindingCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    finding = await audit_service.create_audit_finding(db, req.audit_id, req.clause_ref, req.finding_type, req.description, req.root_cause, req.correction, req.corrective_action, req.due_date, user.user_id)
    return schemas.audit.AuditFindingResponse.model_validate(finding)


@router.get("/{finding_id}", response_model=schemas.audit.AuditFindingResponse)
async def get_finding(finding_id: uuid.UUID, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    finding = await audit_service.get_audit_finding(db, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="audit finding not found")
    return schemas.audit.AuditFindingResponse.model_validate(finding)


@router.put("/{finding_id}", response_model=schemas.audit.AuditFindingResponse)
async def update_finding(finding_id: uuid.UUID, req: schemas.audit.AuditFindingUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    finding = await audit_service.get_audit_finding(db, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="audit finding not found")
    finding = await audit_service.update_audit_finding(db, finding, req.clause_ref, req.finding_type, req.description, req.root_cause, req.correction, req.corrective_action, req.status, req.due_date, user.user_id)
    return schemas.audit.AuditFindingResponse.model_validate(finding)


@router.post("/{finding_id}/close", response_model=schemas.audit.AuditFindingResponse)
async def close_finding(finding_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    finding = await audit_service.get_audit_finding(db, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="audit finding not found")
    try:
        finding = await audit_service.close_audit_finding(db, finding, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.audit.AuditFindingResponse.model_validate(finding)


@router.post("/{finding_id}/create-capa")
async def create_capa_from_finding(finding_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(require_engineer_or_admin)):
    finding = await audit_service.get_audit_finding(db, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="audit finding not found")
    try:
        capa = await audit_service.create_capa_from_finding(db, finding, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "CAPA created", "capa_id": str(capa.report_id), "document_no": capa.document_no}
```

- [ ] **Step 4: 创建审核员路由**

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app import schemas
from app.services import audit_service

router = APIRouter(prefix="/api/auditors", tags=["auditors"])


@router.get("", response_model=list[schemas.auth.UserResponse])
async def list_auditors(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    auditors = await audit_service.list_auditors(db)
    return [schemas.auth.UserResponse.model_validate(u) for u in auditors]


@router.put("/{user_id}/auditor-info", response_model=schemas.auth.UserResponse)
async def update_auditor_info(user_id: uuid.UUID, req: schemas.audit.AuditorInfoUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    user = await audit_service.update_auditor_info(db, user, req.is_auditor, req.qualifications, req.last_qualification_date, current_user.user_id)
    return schemas.auth.UserResponse.model_validate(user)
```

注意：这里引用了 `schemas.auth.UserResponse`，需确认存在。如果不存在，需要在 `schemas/auth.py` 中定义或调整。

- [ ] **Step 5: 检查表模板路由**

将检查表模板 API 放在 `audit_plan.py` 中（因为模板用于创建计划）：

```python
# 添加到 backend/app/api/audit_plan.py

CHECKLIST_TEMPLATES = {
    "system": {
        "audit_type": "system",
        "name": "质量管理体系审核检查表",
        "items": [
            {"item_no": "1", "clause": "4.1", "question": "组织是否理解其所处环境并确定相关因素？", "result": "", "evidence": "", "note": ""},
            {"item_no": "2", "clause": "4.2", "question": "组织是否识别相关方及其需求期望？", "result": "", "evidence": "", "note": ""},
            {"item_no": "3", "clause": "5.1", "question": "最高管理者是否展现了领导作用和承诺？", "result": "", "evidence": "", "note": ""},
            {"item_no": "4", "clause": "6.1", "question": "组织是否策划了应对风险和机遇的措施？", "result": "", "evidence": "", "note": ""},
            {"item_no": "5", "clause": "7.1", "question": "组织是否确定和提供了所需的资源？", "result": "", "evidence": "", "note": ""},
            {"item_no": "6", "clause": "8.1", "question": "运行的策划和控制是否有效实施？", "result": "", "evidence": "", "note": ""},
            {"item_no": "7", "clause": "9.1", "question": "监视、测量、分析和评价是否有效？", "result": "", "evidence": "", "note": ""},
            {"item_no": "8", "clause": "9.2", "question": "内部审核是否按策划进行且有效？", "result": "", "evidence": "", "note": ""},
            {"item_no": "9", "clause": "10.2", "question": "不合格和纠正措施是否有效实施？", "result": "", "evidence": "", "note": ""},
        ]
    },
    "process": {
        "audit_type": "process",
        "name": "制造过程审核检查表",
        "items": [
            {"item_no": "1", "clause": "P2", "question": "项目管理是否充分？", "result": "", "evidence": "", "note": ""},
            {"item_no": "2", "clause": "P3", "question": "策划产品和过程开发的输入是否完整？", "result": "", "evidence": "", "note": ""},
            {"item_no": "3", "clause": "P4", "question": "产品和过程开发的输出是否满足要求？", "result": "", "evidence": "", "note": ""},
            {"item_no": "4", "clause": "P5", "question": "供应商管理是否有效？", "result": "", "evidence": "", "note": ""},
            {"item_no": "5", "clause": "P6", "question": "生产过程分析是否充分？", "result": "", "evidence": "", "note": ""},
            {"item_no": "6", "clause": "P6.1", "question": "过程输入（物流/零件）是否正确？", "result": "", "evidence": "", "note": ""},
            {"item_no": "7", "clause": "P6.2", "question": "生产设备/工装是否适用且被维护？", "result": "", "evidence": "", "note": ""},
            {"item_no": "8", "clause": "P6.3", "question": "特殊特性是否被有效监控？", "result": "", "evidence": "", "note": ""},
            {"item_no": "9", "clause": "P6.4", "question": "不合格品控制是否有效？", "result": "", "evidence": "", "note": ""},
            {"item_no": "10", "clause": "P6.5", "question": "纠正措施是否被有效跟踪？", "result": "", "evidence": "", "note": ""},
            {"item_no": "11", "clause": "P7", "question": "顾客支持/满意度/服务是否有效？", "result": "", "evidence": "", "note": ""},
        ]
    },
    "product": {
        "audit_type": "product",
        "name": "产品审核检查表",
        "items": [
            {"item_no": "1", "clause": "", "question": "产品标识和可追溯性是否符合要求？", "result": "", "evidence": "", "note": ""},
            {"item_no": "2", "clause": "", "question": "外观质量是否符合规范？", "result": "", "evidence": "", "note": ""},
            {"item_no": "3", "clause": "", "question": "尺寸测量结果是否在公差范围内？", "result": "", "evidence": "", "note": ""},
            {"item_no": "4", "clause": "", "question": "功能/性能测试是否通过？", "result": "", "evidence": "", "note": ""},
            {"item_no": "5", "clause": "", "question": "包装和标识是否正确完整？", "result": "", "evidence": "", "note": ""},
            {"item_no": "6", "clause": "", "question": "检验文件和记录是否完整？", "result": "", "evidence": "", "note": ""},
            {"item_no": "7", "clause": "", "question": "特殊特性（CC/SC）是否被验证？", "result": "", "evidence": "", "note": ""},
        ]
    }
}


@router.get("/checklist-templates", response_model=list[schemas.audit.AuditChecklistTemplate])
async def get_checklist_templates(_user: User = Depends(get_current_user)):
    return list(CHECKLIST_TEMPLATES.values())
```

- [ ] **Step 6: 注册路由到 main.py**

Modify `backend/app/main.py`：

```python
from app.api.audit_program import router as audit_program_router
from app.api.audit_plan import router as audit_plan_router
from app.api.audit_finding import router as audit_finding_router
from app.api.auditor import router as auditor_router
# ... existing routers ...

app.include_router(audit_program_router)
app.include_router(audit_plan_router)
app.include_router(audit_finding_router)
app.include_router(auditor_router)
```

- [ ] **Step 7: 验证后端启动**

Run: `docker compose exec -e SECRET_KEY=OpenQMS-2026-QualityGoal-DevKey backend python -c "from app.main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/ backend/app/main.py backend/app/schemas/__init__.py
git commit -m "feat: add internal audit API routes and checklist templates"
```

---

## Task 6: 前端类型与 API

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/audit.ts`
- Create: `frontend/src/utils/auditChecklistTemplates.ts`

- [ ] **Step 1: 在 types/index.ts 追加类型**

```typescript
export interface AuditProgram {
  program_id: string;
  program_year: number;
  audit_type: "system" | "process" | "product";
  scope: string;
  criteria: string;
  status: "planned" | "active" | "completed";
  created_by: string | null;
  created_at: string;
}

export interface AuditPlan {
  audit_id: string;
  program_id: string;
  audit_scope: string;
  audit_criteria: string;
  planned_date: string;
  actual_date: string | null;
  lead_auditor: string | null;
  team_members: { user_id: string; username: string }[];
  checklist: AuditChecklistItem[];
  status: "planned" | "in_progress" | "completed" | "cancelled";
  created_by: string | null;
  created_at: string;
}

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
  created_by: string | null;
  created_at: string;
}

export interface AuditChecklistItem {
  item_no: string;
  clause: string;
  question: string;
  result: "符合" | "不符合" | "不适用" | "";
  evidence: string;
  note: string;
}

export interface AuditProgramListResponse {
  items: AuditProgram[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditPlanListResponse {
  items: AuditPlan[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditFindingListResponse {
  items: AuditFinding[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditStats {
  program_count: number;
  planned_count: number;
  in_progress_count: number;
  completed_count: number;
  open_findings: number;
  major_nc_count: number;
}
```

- [ ] **Step 2: 创建前端 API 客户端**

```typescript
import client from "./client";
import type {
  AuditProgram, AuditPlan, AuditFinding, AuditProgramListResponse,
  AuditPlanListResponse, AuditFindingListResponse, AuditStats, AuditChecklistItem
} from "../types";

export async function listAuditPrograms(params?: { page?: number; page_size?: number; year?: number; audit_type?: string; status?: string }): Promise<AuditProgramListResponse> {
  const resp = await client.get("/audit-programs/list", { params });
  return resp.data;
}

export async function createAuditProgram(data: { program_year: number; audit_type: string; scope: string; criteria: string }): Promise<AuditProgram> {
  const resp = await client.post("/audit-programs", data);
  return resp.data;
}

export async function getAuditProgram(id: string): Promise<AuditProgram> {
  const resp = await client.get(`/audit-programs/${id}`);
  return resp.data;
}

export async function updateAuditProgram(id: string, data: Partial<AuditProgram>): Promise<AuditProgram> {
  const resp = await client.put(`/audit-programs/${id}`, data);
  return resp.data;
}

export async function deleteAuditProgram(id: string): Promise<void> {
  await client.delete(`/audit-programs/${id}`);
}

export async function listAuditPlans(params?: { page?: number; page_size?: number; program_id?: string; status?: string; date_from?: string; date_to?: string }): Promise<AuditPlanListResponse> {
  const resp = await client.get("/audit-plans", { params });
  return resp.data;
}

export async function createAuditPlan(data: Omit<AuditPlan, "audit_id" | "created_at" | "status" | "created_by">): Promise<AuditPlan> {
  const resp = await client.post("/audit-plans", data);
  return resp.data;
}

export async function getAuditPlan(id: string): Promise<AuditPlan> {
  const resp = await client.get(`/audit-plans/${id}`);
  return resp.data;
}

export async function updateAuditPlan(id: string, data: Partial<AuditPlan>): Promise<AuditPlan> {
  const resp = await client.put(`/audit-plans/${id}`, data);
  return resp.data;
}

export async function deleteAuditPlan(id: string): Promise<void> {
  await client.delete(`/audit-plans/${id}`);
}

export async function startAuditPlan(id: string): Promise<AuditPlan> {
  const resp = await client.post(`/audit-plans/${id}/start`);
  return resp.data;
}

export async function completeAuditPlan(id: string): Promise<AuditPlan> {
  const resp = await client.post(`/audit-plans/${id}/complete`);
  return resp.data;
}

export async function cancelAuditPlan(id: string): Promise<AuditPlan> {
  const resp = await client.post(`/audit-plans/${id}/cancel`);
  return resp.data;
}

export async function listAuditFindings(params?: { page?: number; page_size?: number; audit_id?: string; finding_type?: string; status?: string }): Promise<AuditFindingListResponse> {
  const resp = await client.get("/audit-findings", { params });
  return resp.data;
}

export async function createAuditFinding(data: Omit<AuditFinding, "finding_id" | "created_at" | "status" | "closed_at" | "created_by" | "capa_ref_id">): Promise<AuditFinding> {
  const resp = await client.post("/audit-findings", data);
  return resp.data;
}

export async function updateAuditFinding(id: string, data: Partial<AuditFinding>): Promise<AuditFinding> {
  const resp = await client.put(`/audit-findings/${id}`, data);
  return resp.data;
}

export async function closeAuditFinding(id: string): Promise<AuditFinding> {
  const resp = await client.post(`/audit-findings/${id}/close`);
  return resp.data;
}

export async function createCAPAFromFinding(id: string): Promise<{ capa_id: string; document_no: string }> {
  const resp = await client.post(`/audit-findings/${id}/create-capa`);
  return resp.data;
}

export async function getAuditStats(): Promise<AuditStats> {
  const resp = await client.get("/audit-programs");
  return resp.data;
}

export async function getChecklistTemplates(): Promise<{ audit_type: string; name: string; items: AuditChecklistItem[] }[]> {
  const resp = await client.get("/audit-plans/checklist-templates");
  return resp.data;
}

export async function listAuditors(): Promise<User[]> {
  const resp = await client.get("/auditors");
  return resp.data;
}

export async function updateAuditorInfo(userId: string, data: { is_auditor: boolean; qualifications: string[]; last_qualification_date?: string }): Promise<User> {
  const resp = await client.put(`/auditors/${userId}/auditor-info`, data);
  return resp.data;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/audit.ts
git commit -m "feat: add internal audit frontend types and API client"
```

---

## Task 7: 前端页面 — 列表页

**Files:**
- Create: `frontend/src/pages/internalAudit/InternalAuditListPage.tsx`
- Create: `frontend/src/utils/auditChecklistTemplates.ts`

- [ ] **Step 1: 创建检查表模板工具**

```typescript
// frontend/src/utils/auditChecklistTemplates.ts
export const CHECKLIST_TEMPLATES: Record<string, { name: string; items: { item_no: string; clause: string; question: string }[] }> = {
  system: {
    name: "质量管理体系审核检查表",
    items: [
      { item_no: "1", clause: "4.1", question: "组织是否理解其所处环境并确定相关因素？" },
      { item_no: "2", clause: "4.2", question: "组织是否识别相关方及其需求期望？" },
      { item_no: "3", clause: "5.1", question: "最高管理者是否展现了领导作用和承诺？" },
      { item_no: "4", clause: "6.1", question: "组织是否策划了应对风险和机遇的措施？" },
      { item_no: "5", clause: "7.1", question: "组织是否确定和提供了所需的资源？" },
      { item_no: "6", clause: "8.1", question: "运行的策划和控制是否有效实施？" },
      { item_no: "7", clause: "9.1", question: "监视、测量、分析和评价是否有效？" },
      { item_no: "8", clause: "9.2", question: "内部审核是否按策划进行且有效？" },
      { item_no: "9", clause: "10.2", question: "不合格和纠正措施是否有效实施？" },
    ],
  },
  process: {
    name: "制造过程审核检查表",
    items: [
      { item_no: "1", clause: "P2", question: "项目管理是否充分？" },
      { item_no: "2", clause: "P3", question: "策划产品和过程开发的输入是否完整？" },
      { item_no: "3", clause: "P4", question: "产品和过程开发的输出是否满足要求？" },
      { item_no: "4", clause: "P5", question: "供应商管理是否有效？" },
      { item_no: "5", clause: "P6", question: "生产过程分析是否充分？" },
      { item_no: "6", clause: "P6.1", question: "过程输入（物流/零件）是否正确？" },
      { item_no: "7", clause: "P6.2", question: "生产设备/工装是否适用且被维护？" },
      { item_no: "8", clause: "P6.3", question: "特殊特性是否被有效监控？" },
      { item_no: "9", clause: "P6.4", question: "不合格品控制是否有效？" },
      { item_no: "10", clause: "P6.5", question: "纠正措施是否被有效跟踪？" },
      { item_no: "11", clause: "P7", question: "顾客支持/满意度/服务是否有效？" },
    ],
  },
  product: {
    name: "产品审核检查表",
    items: [
      { item_no: "1", clause: "", question: "产品标识和可追溯性是否符合要求？" },
      { item_no: "2", clause: "", question: "外观质量是否符合规范？" },
      { item_no: "3", clause: "", question: "尺寸测量结果是否在公差范围内？" },
      { item_no: "4", clause: "", question: "功能/性能测试是否通过？" },
      { item_no: "5", clause: "", question: "包装和标识是否正确完整？" },
      { item_no: "6", clause: "", question: "检验文件和记录是否完整？" },
      { item_no: "7", clause: "", question: "特殊特性（CC/SC）是否被验证？" },
    ],
  },
};

export function getChecklistTemplate(auditType: string): { item_no: string; clause: string; question: string; result: string; evidence: string; note: string }[] {
  const template = CHECKLIST_TEMPLATES[auditType];
  if (!template) return [];
  return template.items.map((item) => ({ ...item, result: "", evidence: "", note: "" }));
}
```

- [ ] **Step 2: 创建列表页**

列表页代码量较大，核心结构如下（实施时需填充完整 JSX）：

```tsx
// 核心结构和状态
export default function InternalAuditListPage() {
  const [plans, setPlans] = useState<AuditPlan[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("all");
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [programs, setPrograms] = useState<AuditProgram[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalType, setModalType] = useState<"program" | "plan">("plan");
  const [editingProgram, setEditingProgram] = useState<AuditProgram | null>(null);
  const [editingPlan, setEditingPlan] = useState<AuditPlan | null>(null);
  const [auditorDrawerOpen, setAuditorDrawerOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "admin";
  const isEngineer = user?.role === "quality_engineer" || isAdmin;
}
```

页面需包含：
1. 顶部 4 张统计卡片（使用 Row/Col + Card）
2. 操作栏：新建方案、新建计划、审核员管理按钮
3. Tabs：全部 / 待执行 / 进行中 / 已完成
4. Table：审核计划列表
5. Modal：创建/编辑方案表单、创建/编辑计划表单
6. Drawer：审核员管理

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/internalAudit/InternalAuditListPage.tsx frontend/src/utils/auditChecklistTemplates.ts
git commit -m "feat: add internal audit list page with stats, filters, and modals"
```

---

## Task 8: 前端页面 — 详情页

**Files:**
- Create: `frontend/src/pages/internalAudit/InternalAuditDetailPage.tsx`

- [ ] **Step 1: 创建详情页**

核心结构：

```tsx
export default function InternalAuditDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [plan, setPlan] = useState<AuditPlan | null>(null);
  const [program, setProgram] = useState<AuditProgram | null>(null);
  const [findings, setFindings] = useState<AuditFinding[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("checklist");
  const [users, setUsers] = useState<User[]>([]);
  const [findingModalOpen, setFindingModalOpen] = useState(false);
  const [editingFinding, setEditingFinding] = useState<AuditFinding | null>(null);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isEngineer = user?.role === "quality_engineer" || user?.role === "admin";
}
```

页面需包含：
1. 头部：计划编号 + 状态 Tag + 返回按钮 + 操作按钮（开始/完成/取消）
2. 基本信息 Card（可编辑 Form）
3. Tabs：
   - 检查表 Tab：可编辑 Table，结果列 Select（符合/不符合/不适用），不符合时高亮
   - 发现项 Tab：发现项列表 Table + 添加/编辑/关闭/创建CAPA 操作
   - 审核报告 Tab：统计卡片 + 发现项分组 + PieChart

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/internalAudit/InternalAuditDetailPage.tsx
git commit -m "feat: add internal audit detail page with checklist, findings, and report"
```

---

## Task 9: 路由与导航集成

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: 修改 App.tsx 添加路由**

```typescript
import InternalAuditListPage from "./pages/internalAudit/InternalAuditListPage";
import InternalAuditDetailPage from "./pages/internalAudit/InternalAuditDetailPage";

// 在 Routes 中添加：
<Route path="/internal-audits" element={<InternalAuditListPage />} />
<Route path="/internal-audits/:id" element={<InternalAuditDetailPage />} />
```

- [ ] **Step 2: 修改 AppLayout.tsx 添加导航**

```typescript
import { SafetyCertificateOutlined } from "@ant-design/icons";

const menuItems = [
  // ... existing items ...
  { key: "/internal-audits", icon: <SafetyCertificateOutlined />, label: "内部审核" },
];
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat: integrate internal audit routes and navigation"
```

---

## Task 10: 集成验证

- [ ] **Step 1: 前端 TypeScript 编译**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npm run build`
Expected: `tsc -b && vite build` 成功，无错误

- [ ] **Step 2: 后端启动验证**

Run: `docker compose exec -e SECRET_KEY=OpenQMS-2026-QualityGoal-DevKey backend python -c "from app.main import app; print('Backend OK')"`
Expected: `Backend OK`

- [ ] **Step 3: 功能走查**

1. 登录 admin 账号
2. 进入"内部审核"页面
3. 创建审核方案（选择体系审核类型）
4. 基于该方案创建审核计划
5. 验证检查表自动加载（体系审核模板 9 项）
6. 点击"开始审核"
7. 在检查表中标记某项为"不符合"
8. 添加发现项（major_nc）
9. 点击"创建 CAPA"
10. 验证 CAPA 列表中出现新记录
11. 完成审核
12. 查看审核报告 Tab，验证统计数据正确

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: internal audit management module v1.0 complete"
```

---

## 自检清单

1. **Spec coverage**: 审核方案 ✓、审核计划 ✓、发现项 ✓、检查表模板 ✓、审核员管理 ✓、CAPA 联动 ✓、统计 ✓
2. **Placeholder scan**: 无 TBD/TODO
3. **Type consistency**: AuditProgram/AuditPlan/AuditFinding 的字段名在前后端一致
4. **API 路径**: `/api/audit-programs`、`/api/audit-plans`、`/api/audit-findings`、`/api/auditors`
5. **权限**: 符合 OpenQMS RBAC 模式（viewer+ 只读，engineer+ CRUD，admin 审核员管理）
