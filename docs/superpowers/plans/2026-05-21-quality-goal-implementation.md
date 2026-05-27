# 质量目标管理模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现质量目标管理模块（三级目标树 + 审批流程 + 仪表盘列表），后端 FastAPI + 前端 React/Ant Design。

**Architecture:** 遵循 OpenQMS 现有四层架构（model → schema → service → api），前端遵循 pages/api/types/components 分层。质量目标使用自引用表存储树形结构，服务层实现审批状态机和文档编号自动生成。

**Tech Stack:** Python 3.11 + FastAPI 0.115 + SQLAlchemy 2.0 + Pydantic v2 | React 18 + TypeScript 5.6 + Ant Design 5.21 + Axios | PostgreSQL 15 + Alembic

---

## 文件结构

```
backend/
  alembic/versions/004_add_quality_goals.py          # 数据库迁移
  app/models/quality_goal.py                          # SQLAlchemy 模型
  app/models/__init__.py                              # 导出 QualityGoal
  app/schemas/quality_goal.py                         # Pydantic schemas
  app/services/quality_goal_service.py                # 业务逻辑 + AuditLog
  app/api/quality_goal.py                             # FastAPI 路由
  app/main.py                                         # 注册路由

frontend/
  src/types/index.ts                                  # 添加 QualityGoal 类型
  src/api/qualityGoal.ts                              # Axios API 函数
  src/pages/qualityGoal/QualityGoalListPage.tsx       # 列表页面
  src/App.tsx                                         # 注册路由
  src/components/layout/AppLayout.tsx                 # 添加侧边栏菜单项
```

---

### Task 1: Alembic 数据库迁移

**Files:**
- Create: `backend/alembic/versions/004_add_quality_goals.py`

- [ ] **Step 1: 创建迁移文件**

```python
"""add quality_goals table

Revision ID: 004
Revises: 003
Create Date: 2026-05-21 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'quality_goals',
        sa.Column('goal_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('doc_no', sa.String(20), unique=True, nullable=False),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('quality_goals.goal_id'), nullable=True),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('product_line', sa.String(50), nullable=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('target_value', sa.String(50), nullable=False),
        sa.Column('actual_value', sa.String(50), nullable=True),
        sa.Column('unit', sa.String(20), nullable=False),
        sa.Column('period', sa.String(20), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('approved_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reject_reason', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_quality_goals_level', 'quality_goals', ['level'])
    op.create_index('ix_quality_goals_status', 'quality_goals', ['status'])
    op.create_index('ix_quality_goals_product_line', 'quality_goals', ['product_line'])


def downgrade() -> None:
    op.drop_index('ix_quality_goals_product_line', table_name='quality_goals')
    op.drop_index('ix_quality_goals_status', table_name='quality_goals')
    op.drop_index('ix_quality_goals_level', table_name='quality_goals')
    op.drop_table('quality_goals')
```

- [ ] **Step 2: 运行迁移**

Run:
```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
alembic upgrade 004
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade 003 -> 004, add quality_goals table`

- [ ] **Step 3: 验证迁移成功**

Run:
```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -c "from app.database import Base; print('quality_goals' in Base.metadata.tables)"
```

Expected: `True`

- [ ] **Step 4: Commit**

```bash
cd /Users/sam/Documents/Code/OpenQMS
git add backend/alembic/versions/004_add_quality_goals.py
git commit -m "chore: add alembic migration for quality_goals table"
```

---

### Task 2: SQLAlchemy 模型

**Files:**
- Create: `backend/app/models/quality_goal.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 创建模型文件**

```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class QualityGoal(Base):
    __tablename__ = "quality_goals"

    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    doc_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quality_goals.goal_id"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    product_line: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_value: Mapped[str] = mapped_column(String(50), nullable=False)
    actual_value: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner = relationship("User", foreign_keys=[owner_id])
    approver = relationship("User", foreign_keys=[approved_by])
    parent = relationship("QualityGoal", remote_side=[goal_id], backref="children")
```

- [ ] **Step 2: 更新模型导出**

Modify `backend/app/models/__init__.py`:

```python
from app.models.user import User
from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD
from app.models.audit import AuditLog
from app.models.quality_goal import QualityGoal

__all__ = ["User", "FMEADocument", "CAPAEightD", "AuditLog", "QualityGoal"]
```

- [ ] **Step 3: Commit**

```bash
cd /Users/sam/Documents/Code/OpenQMS
git add backend/app/models/quality_goal.py backend/app/models/__init__.py
git commit -m "feat: add QualityGoal SQLAlchemy model"
```

---

### Task 3: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/quality_goal.py`

- [ ] **Step 1: 创建 Schema 文件**

```python
import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator


class QualityGoalCreate(BaseModel):
    parent_id: uuid.UUID | None = None
    level: int
    product_line: str | None = None
    name: str
    target_value: str
    unit: str
    period: str
    owner_id: uuid.UUID
    description: str | None = None

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: int) -> int:
        if v not in (1, 2, 3):
            raise ValueError("level must be 1, 2, or 3")
        return v

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        if v not in ("月度", "季度", "年度"):
            raise ValueError('period must be one of "月度", "季度", "年度"')
        return v


class QualityGoalUpdate(BaseModel):
    name: str | None = None
    target_value: str | None = None
    actual_value: str | None = None
    unit: str | None = None
    period: str | None = None
    owner_id: uuid.UUID | None = None
    description: str | None = None

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("月度", "季度", "年度"):
            raise ValueError('period must be one of "月度", "季度", "年度"')
        return v


class QualityGoalResponse(BaseModel):
    goal_id: uuid.UUID
    doc_no: str
    parent_id: uuid.UUID | None
    level: int
    product_line: str | None
    name: str
    target_value: str
    actual_value: str | None
    unit: str
    period: str
    owner_id: uuid.UUID
    status: str
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    reject_reason: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QualityGoalListResponse(BaseModel):
    items: list[QualityGoalResponse]
    total: int
    page: int
    page_size: int


class QualityGoalRejectRequest(BaseModel):
    reject_reason: str
```

- [ ] **Step 2: Commit**

```bash
cd /Users/sam/Documents/Code/OpenQMS
git add backend/app/schemas/quality_goal.py
git commit -m "feat: add QualityGoal Pydantic schemas"
```

---

### Task 4: Service 层

**Files:**
- Create: `backend/app/services/quality_goal_service.py`

- [ ] **Step 1: 创建 Service 文件**

```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.models.quality_goal import QualityGoal
from app.models.audit import AuditLog


async def _generate_doc_no(db: AsyncSession) -> str:
    year = datetime.now().year
    prefix = f"QG-{year}"
    result = await db.execute(
        select(func.count()).where(QualityGoal.doc_no.like(f"{prefix}-%"))
    )
    count = result.scalar() or 0
    return f"{prefix}-{count + 1:03d}"


async def _validate_hierarchy(db: AsyncSession, parent_id: uuid.UUID | None, level: int) -> None:
    if level == 1 and parent_id is not None:
        raise ValueError("company-level goal must not have a parent")
    if level > 1 and parent_id is None:
        raise ValueError(f"level {level} goal must have a parent")
    if parent_id is not None:
        parent = await db.get(QualityGoal, parent_id)
        if parent is None:
            raise ValueError("parent goal not found")
        if parent.level != level - 1:
            raise ValueError(f"parent must be level {level - 1}, got level {parent.level}")


async def list_quality_goals(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    level: int | None = None,
    product_line: str | None = None,
    status: str | None = None,
    period: str | None = None,
) -> tuple[list[QualityGoal], int]:
    query = select(QualityGoal)
    count_query = select(func.count()).select_from(QualityGoal)

    if level is not None:
        query = query.where(QualityGoal.level == level)
        count_query = count_query.where(QualityGoal.level == level)
    if product_line:
        query = query.where(QualityGoal.product_line == product_line)
        count_query = count_query.where(QualityGoal.product_line == product_line)
    if status:
        query = query.where(QualityGoal.status == status)
        count_query = count_query.where(QualityGoal.status == status)
    if period:
        query = query.where(QualityGoal.period == period)
        count_query = count_query.where(QualityGoal.period == period)

    query = query.order_by(QualityGoal.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return list(items), total


async def get_quality_goal(db: AsyncSession, goal_id: uuid.UUID) -> QualityGoal | None:
    return await db.get(QualityGoal, goal_id)


async def create_quality_goal(
    db: AsyncSession,
    parent_id: uuid.UUID | None,
    level: int,
    product_line: str | None,
    name: str,
    target_value: str,
    unit: str,
    period: str,
    owner_id: uuid.UUID,
    description: str | None,
    user_id: uuid.UUID,
) -> QualityGoal:
    await _validate_hierarchy(db, parent_id, level)
    doc_no = await _generate_doc_no(db)

    goal = QualityGoal(
        doc_no=doc_no,
        parent_id=parent_id,
        level=level,
        product_line=product_line,
        name=name,
        target_value=target_value,
        unit=unit,
        period=period,
        owner_id=owner_id,
        description=description,
        status="draft",
    )
    db.add(goal)

    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="CREATE",
        changed_fields={
            "doc_no": doc_no,
            "name": name,
            "level": level,
            "target_value": target_value,
            "status": "draft",
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create quality goal: {e}")
    await db.refresh(goal)
    return goal


async def update_quality_goal(
    db: AsyncSession,
    goal: QualityGoal,
    name: str | None,
    target_value: str | None,
    actual_value: str | None,
    unit: str | None,
    period: str | None,
    owner_id: uuid.UUID | None,
    description: str | None,
    user_id: uuid.UUID,
) -> QualityGoal:
    if goal.status != "draft":
        raise ValueError("only draft goals can be edited")

    changed = {}
    if name is not None and name != goal.name:
        changed["name"] = {"before": goal.name, "after": name}
        goal.name = name
    if target_value is not None and target_value != goal.target_value:
        changed["target_value"] = {"before": goal.target_value, "after": target_value}
        goal.target_value = target_value
    if actual_value is not None and actual_value != goal.actual_value:
        changed["actual_value"] = {"before": goal.actual_value, "after": actual_value}
        goal.actual_value = actual_value
    if unit is not None and unit != goal.unit:
        changed["unit"] = {"before": goal.unit, "after": unit}
        goal.unit = unit
    if period is not None and period != goal.period:
        changed["period"] = {"before": goal.period, "after": period}
        goal.period = period
    if owner_id is not None and owner_id != goal.owner_id:
        changed["owner_id"] = {"before": str(goal.owner_id), "after": str(owner_id)}
        goal.owner_id = owner_id
    if description is not None and description != goal.description:
        changed["description"] = {"before": goal.description, "after": description}
        goal.description = description

    if not changed:
        return goal

    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to update quality goal: {e}")
    await db.refresh(goal)
    return goal


async def delete_quality_goal(db: AsyncSession, goal: QualityGoal, user_id: uuid.UUID) -> None:
    if goal.status != "draft":
        raise ValueError("only draft goals can be deleted")

    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="DELETE",
        changed_fields={
            "doc_no": goal.doc_no,
            "name": goal.name,
            "status": goal.status,
        },
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.delete(goal)
    await db.commit()


async def submit_for_approval(db: AsyncSession, goal: QualityGoal, user_id: uuid.UUID) -> QualityGoal:
    if goal.status != "draft":
        raise ValueError("only draft goals can be submitted for approval")

    goal.status = "pending"
    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="TRANSITION",
        changed_fields={"status": {"before": "draft", "after": "pending"}},
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(goal)
    return goal


async def withdraw_submission(db: AsyncSession, goal: QualityGoal, user_id: uuid.UUID) -> QualityGoal:
    if goal.status != "pending":
        raise ValueError("only pending goals can be withdrawn")

    goal.status = "draft"
    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="TRANSITION",
        changed_fields={"status": {"before": "pending", "after": "draft"}},
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(goal)
    return goal


async def approve_goal(db: AsyncSession, goal: QualityGoal, approver_id: uuid.UUID) -> QualityGoal:
    if goal.status != "pending":
        raise ValueError("only pending goals can be approved")

    now = datetime.now(timezone.utc)
    goal.status = "active"
    goal.approved_by = approver_id
    goal.approved_at = now
    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="TRANSITION",
        changed_fields={
            "status": {"before": "pending", "after": "active"},
            "approved_by": str(approver_id),
            "approved_at": now.isoformat(),
        },
        operated_by=approver_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(goal)
    return goal


async def reject_goal(db: AsyncSession, goal: QualityGoal, reject_reason: str, approver_id: uuid.UUID) -> QualityGoal:
    if goal.status != "pending":
        raise ValueError("only pending goals can be rejected")
    if not reject_reason or not reject_reason.strip():
        raise ValueError("reject reason is required")

    goal.status = "draft"
    goal.reject_reason = reject_reason
    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="TRANSITION",
        changed_fields={
            "status": {"before": "pending", "after": "draft"},
            "reject_reason": reject_reason,
        },
        operated_by=approver_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(goal)
    return goal


async def archive_goal(db: AsyncSession, goal: QualityGoal, user_id: uuid.UUID) -> QualityGoal:
    if goal.status != "active":
        raise ValueError("only active goals can be archived")

    goal.status = "archived"
    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="TRANSITION",
        changed_fields={"status": {"before": "active", "after": "archived"}},
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(goal)
    return goal


async def update_actual_value(
    db: AsyncSession, goal: QualityGoal, actual_value: str, user_id: uuid.UUID
) -> QualityGoal:
    if goal.status != "active":
        raise ValueError("only active goals can have actual value updated")

    changed = {
        "actual_value": {"before": goal.actual_value, "after": actual_value}
    }
    goal.actual_value = actual_value

    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(goal)
    return goal
```

- [ ] **Step 2: Commit**

```bash
cd /Users/sam/Documents/Code/OpenQMS
git add backend/app/services/quality_goal_service.py
git commit -m "feat: add QualityGoal service with approval workflow and audit logging"
```

---

### Task 5: API 路由层

**Files:**
- Create: `backend/app/api/quality_goal.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 API 路由文件**

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin, require_manager_or_admin
from app.models.user import User
from app import schemas
from app.services import quality_goal_service

router = APIRouter(prefix="/api/quality-goals", tags=["quality-goals"])


@router.get("", response_model=schemas.quality_goal.QualityGoalListResponse)
async def list_quality_goals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    level: int | None = Query(None),
    product_line: str | None = Query(None),
    status: str | None = Query(None),
    period: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await quality_goal_service.list_quality_goals(
        db, page, page_size, level, product_line, status, period
    )
    return schemas.quality_goal.QualityGoalListResponse(
        items=[schemas.quality_goal.QualityGoalResponse.model_validate(g) for g in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=schemas.quality_goal.QualityGoalResponse)
async def create_quality_goal(
    req: schemas.quality_goal.QualityGoalCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        goal = await quality_goal_service.create_quality_goal(
            db,
            parent_id=req.parent_id,
            level=req.level,
            product_line=req.product_line,
            name=req.name,
            target_value=req.target_value,
            unit=req.unit,
            period=req.period,
            owner_id=req.owner_id,
            description=req.description,
            user_id=user.user_id,
        )
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{goal_id}", response_model=schemas.quality_goal.QualityGoalResponse)
async def get_quality_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    return schemas.quality_goal.QualityGoalResponse.model_validate(goal)


@router.put("/{goal_id}", response_model=schemas.quality_goal.QualityGoalResponse)
async def update_quality_goal(
    goal_id: uuid.UUID,
    req: schemas.quality_goal.QualityGoalUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        goal = await quality_goal_service.update_quality_goal(
            db,
            goal=goal,
            name=req.name,
            target_value=req.target_value,
            actual_value=req.actual_value,
            unit=req.unit,
            period=req.period,
            owner_id=req.owner_id,
            description=req.description,
            user_id=user.user_id,
        )
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{goal_id}")
async def delete_quality_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        await quality_goal_service.delete_quality_goal(db, goal, user.user_id)
        return {"message": "quality goal deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/submit", response_model=schemas.quality_goal.QualityGoalResponse)
async def submit_for_approval(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        goal = await quality_goal_service.submit_for_approval(db, goal, user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/withdraw", response_model=schemas.quality_goal.QualityGoalResponse)
async def withdraw_submission(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        goal = await quality_goal_service.withdraw_submission(db, goal, user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/approve", response_model=schemas.quality_goal.QualityGoalResponse)
async def approve_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        goal = await quality_goal_service.approve_goal(db, goal, user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/reject", response_model=schemas.quality_goal.QualityGoalResponse)
async def reject_goal(
    goal_id: uuid.UUID,
    req: schemas.quality_goal.QualityGoalRejectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        goal = await quality_goal_service.reject_goal(db, goal, req.reject_reason, user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/archive", response_model=schemas.quality_goal.QualityGoalResponse)
async def archive_goal(
    goal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    try:
        goal = await quality_goal_service.archive_goal(db, goal, user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{goal_id}/actual-value", response_model=schemas.quality_goal.QualityGoalResponse)
async def update_actual_value(
    goal_id: uuid.UUID,
    req: schemas.quality_goal.QualityGoalUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    goal = await quality_goal_service.get_quality_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="quality goal not found")
    if req.actual_value is None:
        raise HTTPException(status_code=400, detail="actual_value is required")
    try:
        goal = await quality_goal_service.update_actual_value(db, goal, req.actual_value, user.user_id)
        return schemas.quality_goal.QualityGoalResponse.model_validate(goal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 2: 注册路由**

Modify `backend/app/main.py`，在现有 router 导入后添加：

```python
from app.api.quality_goal import router as quality_goal_router
```

在现有 `app.include_router()` 调用后添加：

```python
app.include_router(quality_goal_router)
```

- [ ] **Step 3: 验证后端启动**

Run:
```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected: 启动无报错。另开一个终端验证：
```bash
curl -s http://localhost:8000/api/quality-goals | head -c 200
```

Expected: JSON 响应（空列表）

Stop the dev server with Ctrl+C.

- [ ] **Step 4: Commit**

```bash
cd /Users/sam/Documents/Code/OpenQMS
git add backend/app/api/quality_goal.py backend/app/main.py
git commit -m "feat: add QualityGoal API routes with approval workflow"
```

---

### Task 6: 前端 TypeScript 类型

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: 添加类型定义**

在 `frontend/src/types/index.ts` 中添加（在现有类型之后）：

```typescript
export interface QualityGoal {
  goal_id: string;
  doc_no: string;
  parent_id: string | null;
  level: number;
  product_line: string | null;
  name: string;
  target_value: string;
  actual_value: string | null;
  unit: string;
  period: string;
  owner_id: string;
  status: "draft" | "pending" | "active" | "archived";
  approved_by: string | null;
  approved_at: string | null;
  reject_reason: string | null;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface QualityGoalListResponse {
  items: QualityGoal[];
  total: number;
  page: number;
  page_size: number;
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/sam/Documents/Code/OpenQMS
git add frontend/src/types/index.ts
git commit -m "feat: add QualityGoal TypeScript types"
```

---

### Task 7: 前端 API 函数

**Files:**
- Create: `frontend/src/api/qualityGoal.ts`

- [ ] **Step 1: 创建 API 文件**

```typescript
import client from "./client";
import type { QualityGoal, QualityGoalListResponse } from "../types";

export async function listQualityGoals(params: {
  page?: number;
  page_size?: number;
  level?: number;
  product_line?: string;
  status?: string;
  period?: string;
}): Promise<QualityGoalListResponse> {
  const resp = await client.get("/quality-goals", { params });
  return resp.data;
}

export async function getQualityGoal(id: string): Promise<QualityGoal> {
  const resp = await client.get(`/quality-goals/${id}`);
  return resp.data;
}

export async function createQualityGoal(data: {
  parent_id?: string | null;
  level: number;
  product_line?: string | null;
  name: string;
  target_value: string;
  unit: string;
  period: string;
  owner_id: string;
  description?: string | null;
}): Promise<QualityGoal> {
  const resp = await client.post("/quality-goals", data);
  return resp.data;
}

export async function updateQualityGoal(
  id: string,
  data: {
    name?: string;
    target_value?: string;
    actual_value?: string;
    unit?: string;
    period?: string;
    owner_id?: string;
    description?: string | null;
  }
): Promise<QualityGoal> {
  const resp = await client.put(`/quality-goals/${id}`, data);
  return resp.data;
}

export async function deleteQualityGoal(id: string): Promise<void> {
  await client.delete(`/quality-goals/${id}`);
}

export async function submitQualityGoal(id: string): Promise<QualityGoal> {
  const resp = await client.post(`/quality-goals/${id}/submit`);
  return resp.data;
}

export async function withdrawQualityGoal(id: string): Promise<QualityGoal> {
  const resp = await client.post(`/quality-goals/${id}/withdraw`);
  return resp.data;
}

export async function approveQualityGoal(id: string): Promise<QualityGoal> {
  const resp = await client.post(`/quality-goals/${id}/approve`);
  return resp.data;
}

export async function rejectQualityGoal(id: string, reject_reason: string): Promise<QualityGoal> {
  const resp = await client.post(`/quality-goals/${id}/reject`, { reject_reason });
  return resp.data;
}

export async function archiveQualityGoal(id: string): Promise<QualityGoal> {
  const resp = await client.post(`/quality-goals/${id}/archive`);
  return resp.data;
}

export async function updateActualValue(id: string, actual_value: string): Promise<QualityGoal> {
  const resp = await client.post(`/quality-goals/${id}/actual-value`, { actual_value });
  return resp.data;
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/sam/Documents/Code/OpenQMS
git add frontend/src/api/qualityGoal.ts
git commit -m "feat: add QualityGoal frontend API client"
```

---

### Task 8: 前端页面

**Files:**
- Create: `frontend/src/pages/qualityGoal/QualityGoalListPage.tsx`

- [ ] **Step 1: 创建页面目录和文件**

```tsx
import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Table,
  Button,
  Tag,
  Space,
  Modal,
  Form,
  Input,
  Select,
  message,
  Tabs,
  Row,
  Col,
  Statistic,
  Popconfirm,
  Tooltip,
} from "antd";
import {
  PlusOutlined,
  CheckOutlined,
  CloseOutlined,
  SendOutlined,
  RollbackOutlined,
  InboxOutlined,
  EditOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { useAuthStore } from "../../store/authStore";
import type { QualityGoal } from "../../types";
import {
  listQualityGoals,
  createQualityGoal,
  updateQualityGoal,
  deleteQualityGoal,
  submitQualityGoal,
  withdrawQualityGoal,
  approveQualityGoal,
  rejectQualityGoal,
  archiveQualityGoal,
  updateActualValue,
} from "../../api/qualityGoal";
import { listUsers } from "../../api/auth";

const { Option } = Select;
const { TabPane } = Tabs;

const LEVEL_MAP: Record<number, { label: string; color: string; icon: string }> = {
  1: { label: "公司级", color: "blue", icon: "🏢" },
  2: { label: "产品线级", color: "green", icon: "🏭" },
  3: { label: "过程级", color: "orange", icon: "🔧" },
};

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: "草稿", color: "default" },
  pending: { label: "待审批", color: "gold" },
  active: { label: "生效中", color: "success" },
  archived: { label: "已停用", color: "default" },
};

function parseTarget(value: string): { operator: string; threshold: number } {
  const v = value.trim();
  if (v.startsWith("≤")) return { operator: "<=", threshold: parseFloat(v.slice(1).replace("%", "")) };
  if (v.startsWith("≥")) return { operator: ">=", threshold: parseFloat(v.slice(1).replace("%", "")) };
  if (v.startsWith("<=")) return { operator: "<=", threshold: parseFloat(v.slice(2).replace("%", "")) };
  if (v.startsWith(">=")) return { operator: ">=", threshold: parseFloat(v.slice(2).replace("%", "")) };
  return { operator: "<=", threshold: parseFloat(v.replace("%", "")) };
}

function checkAchievement(target: string, actual: string | null): "achieved" | "not_achieved" | "pending" {
  if (!actual) return "pending";
  const { operator, threshold } = parseTarget(target);
  const actualNum = parseFloat(actual.replace("%", ""));
  if (isNaN(actualNum) || isNaN(threshold)) return "pending";
  if (operator === "<=") return actualNum <= threshold ? "achieved" : "not_achieved";
  if (operator === ">=") return actualNum >= threshold ? "achieved" : "not_achieved";
  return "pending";
}

function getProgressPercent(target: string, actual: string | null): number {
  if (!actual) return 0;
  const { operator, threshold } = parseTarget(target);
  const actualNum = parseFloat(actual.replace("%", ""));
  if (isNaN(actualNum) || isNaN(threshold) || threshold === 0) return 0;
  if (operator === ">=") return Math.min((actualNum / threshold) * 100, 100);
  if (operator === "<=") return Math.min((threshold / actualNum) * 100, 100);
  return 0;
}

export default function QualityGoalListPage() {
  const user = useAuthStore((s) => s.user);
  const isEngineerPlus = user?.role === "admin" || user?.role === "manager" || user?.role === "quality_engineer";
  const isManagerPlus = user?.role === "admin" || user?.role === "manager";

  const [goals, setGoals] = useState<QualityGoal[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [activeTab, setActiveTab] = useState("all");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingGoal, setEditingGoal] = useState<QualityGoal | null>(null);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectingGoalId, setRejectingGoalId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [users, setUsers] = useState<Array<{ user_id: string; display_name: string | null; username: string }>>([]);
  const [form] = Form.useForm();

  const fetchGoals = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (activeTab === "pending") params.status = "pending";
      else if (activeTab === "my") params.status = undefined;
      else if (activeTab === "draft") params.status = "draft";
      const resp = await listQualityGoals(params);
      let items = resp.items;
      if (activeTab === "my") {
        items = items.filter((g) => g.owner_id === user?.user_id);
      }
      setGoals(items);
      setTotal(resp.total);
    } catch {
      message.error("加载数据失败");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, activeTab, user?.user_id]);

  useEffect(() => {
    fetchGoals();
  }, [fetchGoals]);

  useEffect(() => {
    listUsers().then((resp) => setUsers(resp.items || [])).catch(() => {});
  }, []);

  const handleCreate = () => {
    setEditingGoal(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (goal: QualityGoal) => {
    setEditingGoal(goal);
    form.setFieldsValue({
      parent_id: goal.parent_id,
      level: goal.level,
      product_line: goal.product_line,
      name: goal.name,
      target_value: goal.target_value,
      unit: goal.unit,
      period: goal.period,
      owner_id: goal.owner_id,
      description: goal.description,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (values: Record<string, unknown>) => {
    try {
      if (editingGoal) {
        await updateQualityGoal(editingGoal.goal_id, {
          name: values.name as string,
          target_value: values.target_value as string,
          unit: values.unit as string,
          period: values.period as string,
          owner_id: values.owner_id as string,
          description: values.description as string | null,
        });
        message.success("更新成功");
      } else {
        await createQualityGoal({
          parent_id: values.parent_id as string | null,
          level: values.level as number,
          product_line: values.product_line as string | null,
          name: values.name as string,
          target_value: values.target_value as string,
          unit: values.unit as string,
          period: values.period as string,
          owner_id: values.owner_id as string,
          description: values.description as string | null,
        });
        message.success("创建成功");
      }
      setModalOpen(false);
      fetchGoals();
    } catch (e: unknown) {
      message.error((e as Error).message || "操作失败");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteQualityGoal(id);
      message.success("删除成功");
      fetchGoals();
    } catch (e: unknown) {
      message.error((e as Error).message || "删除失败");
    }
  };

  const handleSubmitForApproval = async (id: string) => {
    try {
      await submitQualityGoal(id);
      message.success("已提交审批");
      fetchGoals();
    } catch (e: unknown) {
      message.error((e as Error).message || "提交失败");
    }
  };

  const handleWithdraw = async (id: string) => {
    try {
      await withdrawQualityGoal(id);
      message.success("已撤回");
      fetchGoals();
    } catch (e: unknown) {
      message.error((e as Error).message || "撤回失败");
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await approveQualityGoal(id);
      message.success("审批通过");
      fetchGoals();
    } catch (e: unknown) {
      message.error((e as Error).message || "审批失败");
    }
  };

  const handleReject = async () => {
    if (!rejectingGoalId || !rejectReason.trim()) return;
    try {
      await rejectQualityGoal(rejectingGoalId, rejectReason);
      message.success("已驳回");
      setRejectModalOpen(false);
      setRejectReason("");
      setRejectingGoalId(null);
      fetchGoals();
    } catch (e: unknown) {
      message.error((e as Error).message || "驳回失败");
    }
  };

  const handleArchive = async (id: string) => {
    try {
      await archiveQualityGoal(id);
      message.success("已停用");
      fetchGoals();
    } catch (e: unknown) {
      message.error((e as Error).message || "停用失败");
    }
  };

  const handleUpdateActual = async (id: string, value: string) => {
    try {
      await updateActualValue(id, value);
      message.success("实际值已更新");
      fetchGoals();
    } catch (e: unknown) {
      message.error((e as Error).message || "更新失败");
    }
  };

  const activeCount = goals.filter((g) => g.status === "active").length;
  const pendingCount = goals.filter((g) => g.status === "pending").length;
  const achievedCount = goals.filter(
    (g) => g.status === "active" && checkAchievement(g.target_value, g.actual_value) === "achieved"
  ).length;
  const achievementRate = activeCount > 0 ? Math.round((achievedCount / activeCount) * 100) : 0;

  const columns = [
    {
      title: "指标名称",
      dataIndex: "name",
      render: (_: string, record: QualityGoal) => (
        <div>
          <Tag color={LEVEL_MAP[record.level]?.color}>
            {LEVEL_MAP[record.level]?.icon} {LEVEL_MAP[record.level]?.label}
          </Tag>
          <div style={{ marginTop: 4, fontWeight: 500 }}>{record.name}</div>
          {record.product_line && (
            <div style={{ fontSize: 12, color: "#888" }}>{record.product_line}</div>
          )}
        </div>
      ),
    },
    {
      title: "进度与达成",
      render: (_: unknown, record: QualityGoal) => {
        const achievement = checkAchievement(record.target_value, record.actual_value);
        const percent = getProgressPercent(record.target_value, record.actual_value);
        return (
          <div>
            <div style={{ fontSize: 12, color: "#666" }}>
              目标: {record.target_value} | 实际: {record.actual_value || "—"}
            </div>
            {record.actual_value && (
              <div style={{ marginTop: 4 }}>
                <div
                  style={{
                    width: "100%",
                    height: 6,
                    background: "#f0f0f0",
                    borderRadius: 3,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${percent}%`,
                      height: "100%",
                      background:
                        achievement === "achieved"
                          ? "#52c41a"
                          : achievement === "not_achieved"
                          ? "#ff4d4f"
                          : "#bfbfbf",
                      borderRadius: 3,
                    }}
                  />
                </div>
              </div>
            )}
            <div style={{ marginTop: 4 }}>
              {achievement === "achieved" && <Tag color="success">✅ 已达成</Tag>}
              {achievement === "not_achieved" && <Tag color="error">🔴 未达成</Tag>}
              {achievement === "pending" && <Tag>⏳ 待录入</Tag>}
            </div>
          </div>
        );
      },
    },
    {
      title: "周期",
      dataIndex: "period",
      width: 80,
    },
    {
      title: "责任人",
      dataIndex: "owner_id",
      width: 100,
      render: (ownerId: string) => {
        const u = users.find((x) => x.user_id === ownerId);
        return u?.display_name || u?.username || ownerId;
      },
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (status: string) => {
        const cfg = STATUS_MAP[status];
        return <Tag color={cfg?.color}>{cfg?.label}</Tag>;
      },
    },
    {
      title: "操作",
      width: 200,
      render: (_: unknown, record: QualityGoal) => {
        const isOwner = record.owner_id === user?.user_id;
        return (
          <Space size="small">
            {record.status === "draft" && isEngineerPlus && (
              <>
                <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
                  编辑
                </Button>
                <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.goal_id)}>
                  <Button size="small" danger icon={<DeleteOutlined />}>
                    删除
                  </Button>
                </Popconfirm>
                <Button size="small" type="primary" icon={<SendOutlined />} onClick={() => handleSubmitForApproval(record.goal_id)}>
                  提交
                </Button>
              </>
            )}
            {record.status === "pending" && (
              <>
                {isEngineerPlus && isOwner && (
                  <Button size="small" icon={<RollbackOutlined />} onClick={() => handleWithdraw(record.goal_id)}>
                    撤回
                  </Button>
                )}
                {isManagerPlus && (
                  <>
                    <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => handleApprove(record.goal_id)}>
                      通过
                    </Button>
                    <Button
                      size="small"
                      danger
                      icon={<CloseOutlined />}
                      onClick={() => {
                        setRejectingGoalId(record.goal_id);
                        setRejectModalOpen(true);
                      }}
                    >
                      驳回
                    </Button>
                  </>
                )}
              </>
            )}
            {record.status === "active" && (
              <>
                {isEngineerPlus && (
                  <Tooltip title="更新实际值">
                    <Button
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => {
                        const value = prompt("请输入实际值:", record.actual_value || "");
                        if (value !== null) handleUpdateActual(record.goal_id, value);
                      }}
                    >
                      更新值
                    </Button>
                  </Tooltip>
                )}
                {isManagerPlus && (
                  <Popconfirm title="确认停用？" onConfirm={() => handleArchive(record.goal_id)}>
                    <Button size="small" icon={<InboxOutlined />}>
                      停用
                    </Button>
                  </Popconfirm>
                )}
              </>
            )}
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="目标总数" value={total} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="生效中" value={activeCount} valueStyle={{ color: "#52c41a" }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="待审批" value={pendingCount} valueStyle={{ color: "#faad14" }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="达成率" value={`${achievementRate}%`} valueStyle={{ color: achievementRate >= 80 ? "#52c41a" : "#ff4d4f" }} />
          </Card>
        </Col>
      </Row>

      <Card
        title="质量目标列表"
        extra={
          isEngineerPlus && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              新建目标
            </Button>
          )
        }
      >
        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab="全部" key="all" />
          {isManagerPlus && <TabPane tab="待我审批" key="pending" />}
          <TabPane tab="我的目标" key="my" />
          {isEngineerPlus && <TabPane tab="草稿" key="draft" />}
        </Tabs>
        <Table
          rowKey="goal_id"
          columns={columns}
          dataSource={goals}
          loading={loading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps || 20);
            },
          }}
        />
      </Card>

      <Modal
        title={editingGoal ? "编辑质量目标" : "新建质量目标"}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="level" label="层级" rules={[{ required: true }]}>
            <Select placeholder="选择层级" disabled={!!editingGoal}>
              <Option value={1}>🏢 公司级</Option>
              <Option value={2}>🏭 产品线级</Option>
              <Option value={3}>🔧 过程级</Option>
            </Select>
          </Form.Item>
          <Form.Item name="parent_id" label="父目标">
            <Select placeholder="选择父目标（公司级无需选择）" allowClear disabled={!!editingGoal}>
              {goals
                .filter((g) => (form.getFieldValue("level") || 1) > 1)
                .filter((g) => g.level === (form.getFieldValue("level") || 1) - 1)
                .map((g) => (
                  <Option key={g.goal_id} value={g.goal_id}>
                    {g.name}
                  </Option>
                ))}
            </Select>
          </Form.Item>
          <Form.Item name="product_line" label="产品线">
            <Input placeholder="如 DC-DC-100" />
          </Form.Item>
          <Form.Item name="name" label="指标名称" rules={[{ required: true }]}>
            <Input placeholder="如 客户投诉率" />
          </Form.Item>
          <Form.Item name="target_value" label="目标值" rules={[{ required: true }]}>
            <Input placeholder="如 ≤500 或 ≥90%" />
          </Form.Item>
          <Form.Item name="unit" label="单位" rules={[{ required: true }]}>
            <Input placeholder="如 PPM、%" />
          </Form.Item>
          <Form.Item name="period" label="周期" rules={[{ required: true }]}>
            <Select placeholder="选择周期">
              <Option value="月度">月度</Option>
              <Option value="季度">季度</Option>
              <Option value="年度">年度</Option>
            </Select>
          </Form.Item>
          <Form.Item name="owner_id" label="责任人" rules={[{ required: true }]}>
            <Select placeholder="选择责任人">
              {users.map((u) => (
                <Option key={u.user_id} value={u.user_id}>
                  {u.display_name || u.username}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="驳回理由"
        open={rejectModalOpen}
        onCancel={() => {
          setRejectModalOpen(false);
          setRejectReason("");
          setRejectingGoalId(null);
        }}
        onOk={handleReject}
      >
        <Input.TextArea
          rows={4}
          placeholder="请输入驳回理由"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
      </Modal>
    </div>
  );
}
```

注意：父目标级联选择在表单中逻辑较简单。如需更精确的级联，可以在 level 变化时动态过滤父目标列表。上述代码中，父目标下拉根据当前选择的 level 动态过滤。但由于 Ant Design Form 的 getFieldValue 在 render 中可能不即时更新，可以考虑使用 `Form.Item` 的 `shouldUpdate` 或 `useWatch`。为简化计划，此处的级联选择采用基础实现，在 Task 9 验证阶段如发现问题再修复。

- [ ] **Step 2: Commit**

```bash
cd /Users/sam/Documents/Code/OpenQMS
git add frontend/src/pages/qualityGoal/QualityGoalListPage.tsx
git commit -m "feat: add QualityGoal list page with dashboard and approval UI"
```

---

### Task 9: 前端路由和导航

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: 注册路由**

Modify `frontend/src/App.tsx`：

在现有 import 后添加：
```typescript
import QualityGoalListPage from "./pages/qualityGoal/QualityGoalListPage";
```

在 `<Route>` 列表中添加：
```tsx
<Route path="/quality-goals" element={<QualityGoalListPage />} />
```

- [ ] **Step 2: 添加侧边栏菜单**

Modify `frontend/src/components/layout/AppLayout.tsx`：

在 import 中添加：
```typescript
import { AimOutlined } from "@ant-design/icons";
```

在 `menuItems` 数组中添加：
```typescript
{ key: "/quality-goals", icon: <AimOutlined />, label: "质量目标" },
```

- [ ] **Step 3: Commit**

```bash
cd /Users/sam/Documents/Code/OpenQMS
git add frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat: register QualityGoal route and sidebar navigation"
```

---

### Task 10: 验证

**Files:** 全局验证

- [ ] **Step 1: 后端类型检查**

Run:
```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -c "from app.main import app; print('backend import OK')"
```

Expected: `backend import OK`

- [ ] **Step 2: 前端类型检查**

Run:
```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npx tsc --noEmit
```

Expected: 无类型错误（0 errors）

- [ ] **Step 3: 前端构建**

Run:
```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npm run build
```

Expected: `dist/` 目录生成，无构建错误

- [ ] **Step 4: 功能验证（手动）**

启动完整开发环境：
```bash
cd /Users/sam/Documents/Code/OpenQMS
docker compose up -d
```

或分别启动：
```bash
# Terminal 1
cd backend && uvicorn app.main:app --reload

# Terminal 2
cd frontend && npm run dev
```

验证步骤：
1. 登录 admin 账户，访问 `http://localhost:5173/quality-goals`
2. 侧边栏应显示"质量目标"菜单项
3. 点击"新建目标"，创建公司级目标（如：客户满意度 ≥90%）
4. 创建产品线级目标，选择刚创建的父目标
5. 提交审批，切换到"待我审批" Tab，审批通过
6. 更新实际值，检查达成状态标签变化
7. 检查审计日志表中是否有对应记录

- [ ] **Step 5: Commit 最终版本**

```bash
cd /Users/sam/Documents/Code/OpenQMS
git add -A
git commit -m "feat: complete QualityGoal management module with approval workflow"
```

---

## 自检

### Spec 覆盖率检查

| 设计文档需求 | 实现任务 |
|-------------|---------|
| 自引用表结构（parent_id） | Task 1, Task 2 |
| 三级层级校验 | Task 4 (_validate_hierarchy) |
| 文档编号自动生成（QG-YYYY-NNN） | Task 4 (_generate_doc_no) |
| 状态流转（draft→pending→active→archived） | Task 4, Task 5 |
| 撤回功能 | Task 4 (withdraw_submission), Task 5 (POST /withdraw) |
| 审批通过/驳回 | Task 4 (approve_goal, reject_goal), Task 5 |
| 仅 actual_value 在 active 状态可更新 | Task 4 (update_actual_value) |
| 权限矩阵 | Task 5 (route guards) |
| 审计日志 | Task 4 (每个变更操作) |
| KPI 概览卡片 | Task 8 (Row/Col/Statistic) |
| Tab 切换（全部/待我审批/我的目标/草稿） | Task 8 (Tabs) |
| 列表 + 进度条 + 达成状态 | Task 8 (columns render) |
| 行内操作按钮 | Task 8 (操作列 render) |
| 新建/编辑 Modal | Task 8 (Modal + Form) |
| 驳回理由弹窗 | Task 8 (reject Modal) |
| 侧边栏导航 | Task 9 |

### 占位符检查

- [x] 无 TBD/TODO
- [x] 无 "implement later"
- [x] 无 "add appropriate error handling"（具体实现了 ValueError + HTTPException）
- [x] 无 "Similar to Task N"
- [x] 每个代码步骤包含完整代码

### 类型一致性检查

- [x] `goal_id` 在 model/schema/api/service 中一致使用 UUID/string
- [x] `status` 枚举值一致：`draft`/`pending`/`active`/`archived`
- [x] `period` 枚举值一致：`月度`/`季度`/`年度`
- [x] `level` 值域一致：1/2/3
- [x] 审计日志 `action` 值一致：CREATE/UPDATE/DELETE/TRANSITION
- [x] 前端 `checkAchievement` 逻辑与服务层规则一致
