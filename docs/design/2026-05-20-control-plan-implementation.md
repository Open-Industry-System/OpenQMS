# 控制计划编辑器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现控制计划编辑器，支持从 PFMEA 导入、13 列表格编辑、变更检测提示。

**Architecture:** 独立数据表（control_plans + control_plan_items），后端 FastAPI 分层架构，前端 React + Ant Design 表格行内编辑。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 + PostgreSQL | React 18 + TypeScript + Ant Design 5

---

## 文件结构总览

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/models/control_plan.py` | 创建 | ControlPlan + ControlPlanItem ORM 模型 |
| `backend/app/models/__init__.py` | 修改 | 导出 ControlPlan |
| `backend/app/schemas/control_plan.py` | 创建 | Pydantic v2 Schema |
| `backend/app/services/control_plan_service.py` | 创建 | 业务逻辑（CRUD + 导入 + 变更检测） |
| `backend/app/api/control_plan.py` | 创建 | FastAPI 路由 |
| `backend/app/main.py` | 修改 | 注册 /api/control-plans 路由 |
| `backend/alembic/versions/003_control_plan.py` | 创建 | 数据库迁移（新建两张表） |
| `frontend/src/types/index.ts` | 修改 | 新增 ControlPlan / ControlPlanItem 接口 |
| `frontend/src/api/controlPlan.ts` | 创建 | Axios API 函数 |
| `frontend/src/components/control-plan/ImportFromFMEAModal.tsx` | 创建 | 从 PFMEA 导入对话框 |
| `frontend/src/pages/control-plan/ControlPlanListPage.tsx` | 创建 | 列表页 |
| `frontend/src/pages/control-plan/ControlPlanEditorPage.tsx` | 创建 | 编辑页（含 13 列表格） |
| `frontend/src/App.tsx` | 修改 | 添加 /control-plans 路由 |
| `frontend/src/components/layout/AppLayout.tsx` | 修改 | 侧边栏添加控制计划菜单 |

---

## Task 1: 后端数据模型

**Files:**
- Create: `backend/app/models/control_plan.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 创建 ControlPlan + ControlPlanItem 模型**

```python
# backend/app/models/control_plan.py
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ControlPlan(Base):
    __tablename__ = "control_plans"

    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    fmea_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id"), nullable=True
    )
    product_line_code: Mapped[str] = mapped_column(String(20), default="DC-DC-100")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    phase: Mapped[str] = mapped_column(String(20), default="production")
    part_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    part_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_info: Mapped[str | None] = mapped_column(String(200), nullable=True)
    drawing_rev: Mapped[str | None] = mapped_column(String(100), nullable=True)
    org_factory: Mapped[str | None] = mapped_column(String(200), nullable=True)
    core_group: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    items = relationship("ControlPlanItem", back_populates="control_plan", cascade="all, delete-orphan")


class ControlPlanItem(Base):
    __tablename__ = "control_plan_items"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_plans.cp_id"), nullable=False
    )
    step_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    process_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    equipment: Mapped[str | None] = mapped_column(String(200), nullable=True)
    characteristic_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    product_characteristic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    process_characteristic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    special_class: Mapped[str | None] = mapped_column(String(20), nullable=True)
    specification_tolerance: Mapped[str | None] = mapped_column(String(200), nullable=True)
    evaluation_method: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sample_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sample_frequency: Mapped[str | None] = mapped_column(String(50), nullable=True)
    control_method: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reaction_plan: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_fmea_node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    control_plan = relationship("ControlPlan", back_populates="items")
```

- [ ] **Step 2: 修改 models/__init__.py 导出 ControlPlan**

```python
# backend/app/models/__init__.py
from app.models.user import User
from app.models.fmea import FMEADocument
from app.models.capa import CAPAReport
from app.models.audit import AuditLog
from app.models.control_plan import ControlPlan, ControlPlanItem

__all__ = ["User", "FMEADocument", "CAPAReport", "AuditLog", "ControlPlan", "ControlPlanItem"]
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/models/control_plan.py backend/app/models/__init__.py
git commit -m "feat: add ControlPlan and ControlPlanItem models"
```

---

## Task 2: 数据库迁移

**Files:**
- Create: `backend/alembic/versions/003_control_plan.py`

- [ ] **Step 1: 创建 Alembic 迁移文件**

```python
# backend/alembic/versions/003_control_plan.py
"""add control_plans and control_plan_items tables

Revision ID: 003
Revises: 002
Create Date: 2026-05-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'control_plans',
        sa.Column('cp_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_no', sa.String(50), unique=True, nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('fmea_ref_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('fmea_documents.fmea_id'), nullable=True),
        sa.Column('product_line_code', sa.String(20), nullable=False, server_default='DC-DC-100'),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('phase', sa.String(20), nullable=False, server_default='production'),
        sa.Column('part_no', sa.String(100), nullable=True),
        sa.Column('part_name', sa.String(200), nullable=True),
        sa.Column('contact_info', sa.String(200), nullable=True),
        sa.Column('drawing_rev', sa.String(100), nullable=True),
        sa.Column('org_factory', sa.String(200), nullable=True),
        sa.Column('core_group', sa.String(200), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('approved_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'control_plan_items',
        sa.Column('item_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cp_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('control_plans.cp_id', ondelete='CASCADE'), nullable=False),
        sa.Column('step_no', sa.String(50), nullable=True),
        sa.Column('process_name', sa.String(200), nullable=True),
        sa.Column('equipment', sa.String(200), nullable=True),
        sa.Column('characteristic_no', sa.String(50), nullable=True),
        sa.Column('product_characteristic', sa.String(200), nullable=True),
        sa.Column('process_characteristic', sa.String(200), nullable=True),
        sa.Column('special_class', sa.String(20), nullable=True),
        sa.Column('specification_tolerance', sa.String(200), nullable=True),
        sa.Column('evaluation_method', sa.String(200), nullable=True),
        sa.Column('sample_size', sa.String(50), nullable=True),
        sa.Column('sample_frequency', sa.String(50), nullable=True),
        sa.Column('control_method', sa.String(200), nullable=True),
        sa.Column('reaction_plan', sa.String(200), nullable=True),
        sa.Column('source_fmea_node_id', sa.String(100), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_table('control_plan_items')
    op.drop_table('control_plans')
```

- [ ] **Step 2: 执行迁移**

```bash
cd backend
alembic upgrade head
```

Expected: `003_control_plan.py` 执行成功，数据库中新增 `control_plans` 和 `control_plan_items` 表。

- [ ] **Step 3: 提交**

```bash
git add backend/alembic/versions/003_control_plan.py
git commit -m "chore: add alembic migration for control plan tables"
```

---

## Task 3: 后端 Schema

**Files:**
- Create: `backend/app/schemas/control_plan.py`

- [ ] **Step 1: 创建 Pydantic Schema**

```python
# backend/app/schemas/control_plan.py
import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class ControlPlanItemBase(BaseModel):
    step_no: str | None = None
    process_name: str | None = None
    equipment: str | None = None
    characteristic_no: str | None = None
    product_characteristic: str | None = None
    process_characteristic: str | None = None
    special_class: str | None = None
    specification_tolerance: str | None = None
    evaluation_method: str | None = None
    sample_size: str | None = None
    sample_frequency: str | None = None
    control_method: str | None = None
    reaction_plan: str | None = None
    source_fmea_node_id: str | None = None
    sort_order: int = 0


class ControlPlanItemCreate(ControlPlanItemBase):
    pass


class ControlPlanItemUpdate(ControlPlanItemBase):
    item_id: str | None = None


class ControlPlanItemResponse(ControlPlanItemBase):
    item_id: uuid.UUID

    model_config = {"from_attributes": True}


class ControlPlanBase(BaseModel):
    title: str
    document_no: str
    fmea_ref_id: uuid.UUID | None = None
    phase: str = "production"
    part_no: str | None = None
    part_name: str | None = None
    contact_info: str | None = None
    drawing_rev: str | None = None
    org_factory: str | None = None
    core_group: str | None = None


class ControlPlanCreate(ControlPlanBase):
    pass


class ControlPlanUpdate(BaseModel):
    title: str | None = None
    document_no: str | None = None
    fmea_ref_id: uuid.UUID | None = None
    phase: str | None = None
    part_no: str | None = None
    part_name: str | None = None
    contact_info: str | None = None
    drawing_rev: str | None = None
    org_factory: str | None = None
    core_group: str | None = None
    items: list[ControlPlanItemCreate] | None = None


class ControlPlanResponse(ControlPlanBase):
    cp_id: uuid.UUID
    product_line_code: str
    status: str
    version: int
    items: list[ControlPlanItemResponse] = []
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
    approved_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None = None

    model_config = {"from_attributes": True}


class ControlPlanListResponse(BaseModel):
    items: list[ControlPlanResponse]
    total: int
    page: int
    page_size: int


class ImportFromFMEARequest(BaseModel):
    fmea_id: uuid.UUID
    step_nos: list[str] | None = None


class StaleCheckResult(BaseModel):
    item_id: uuid.UUID
    step_no: str | None = None
    status: str
    diff_fields: list[str] | None = None
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/schemas/control_plan.py
git commit -m "feat: add ControlPlan pydantic schemas"
```

---

## Task 4: 后端 Service

**Files:**
- Create: `backend/app/services/control_plan_service.py`

- [ ] **Step 1: 创建 Service 层**

```python
# backend/app/services/control_plan_service.py
import uuid
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.fmea import FMEADocument
from app.models.audit import AuditLog
from app.schemas.control_plan import ControlPlanCreate, ControlPlanUpdate, ImportFromFMEARequest


async def create_audit_log(db: AsyncSession, user_id: uuid.UUID, action: str, target_type: str, target_id: str, detail: str):
    log = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
    db.add(log)
    await db.commit()


async def generate_document_no(db: AsyncSession) -> str:
    result = await db.execute(select(func.count()).select_from(ControlPlan))
    count = result.scalar() or 0
    return f"CP-2026-{count + 1:03d}"


async def create_control_plan(db: AsyncSession, data: ControlPlanCreate, user_id: uuid.UUID) -> ControlPlan:
    document_no = await generate_document_no(db)
    cp = ControlPlan(
        document_no=document_no,
        title=data.title,
        fmea_ref_id=data.fmea_ref_id,
        phase=data.phase,
        part_no=data.part_no,
        part_name=data.part_name,
        contact_info=data.contact_info,
        drawing_rev=data.drawing_rev,
        org_factory=data.org_factory,
        core_group=data.core_group,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(cp)
    await db.commit()
    await db.refresh(cp)
    await create_audit_log(db, user_id, "create", "control_plan", str(cp.cp_id), f"创建控制计划 {document_no}")
    return cp


async def get_control_plan(db: AsyncSession, cp_id: uuid.UUID) -> ControlPlan | None:
    result = await db.execute(select(ControlPlan).where(ControlPlan.cp_id == cp_id))
    return result.scalar_one_or_none()


async def list_control_plans(db: AsyncSession, page: int = 1, page_size: int = 20):
    offset = (page - 1) * page_size
    total_result = await db.execute(select(func.count()).select_from(ControlPlan))
    total = total_result.scalar() or 0

    result = await db.execute(
        select(ControlPlan).order_by(ControlPlan.created_at.desc()).offset(offset).limit(page_size)
    )
    items = result.scalars().all()
    return {"items": list(items), "total": total, "page": page, "page_size": page_size}


async def update_control_plan(db: AsyncSession, cp: ControlPlan, data: ControlPlanUpdate, user_id: uuid.UUID) -> ControlPlan:
    if cp.status == "approved":
        raise ValueError("已批准的控制计划不可编辑")

    update_fields = ["title", "document_no", "fmea_ref_id", "phase", "part_no", "part_name",
                     "contact_info", "drawing_rev", "org_factory", "core_group"]
    for field in update_fields:
        val = getattr(data, field, None)
        if val is not None:
            setattr(cp, field, val)

    cp.updated_by = user_id
    await db.commit()
    await db.refresh(cp)
    await create_audit_log(db, user_id, "update", "control_plan", str(cp.cp_id), f"更新控制计划 {cp.document_no}")
    return cp


async def delete_control_plan(db: AsyncSession, cp: ControlPlan, user_id: uuid.UUID):
    await db.delete(cp)
    await db.commit()
    await create_audit_log(db, user_id, "delete", "control_plan", str(cp.cp_id), f"删除控制计划 {cp.document_no}")


async def approve_control_plan(db: AsyncSession, cp: ControlPlan, user_id: uuid.UUID) -> ControlPlan:
    cp.status = "approved"
    cp.approved_by = user_id
    cp.approved_at = datetime.now()
    await db.commit()
    await db.refresh(cp)
    await create_audit_log(db, user_id, "approve", "control_plan", str(cp.cp_id), f"批准控制计划 {cp.document_no}")
    return cp


async def import_from_fmea(db: AsyncSession, cp_id: uuid.UUID, req: ImportFromFMEARequest) -> list[ControlPlanItem]:
    cp_result = await db.execute(select(ControlPlan).where(ControlPlan.cp_id == cp_id))
    cp = cp_result.scalar_one_or_none()
    if not cp:
        raise ValueError("控制计划不存在")

    fmea_result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == req.fmea_id))
    fmea = fmea_result.scalar_one_or_none()
    if not fmea:
        raise ValueError("FMEA 不存在")
    if fmea.fmea_type != "PFMEA":
        raise ValueError("仅支持从 PFMEA 导入")

    graph = fmea.graph_data or {"nodes": [], "edges": []}
    nodes = graph.get("nodes", [])

    step_nodes = [n for n in nodes if n.get("type") == "ProcessStep"]
    if req.step_nos:
        step_nodes = [n for n in step_nodes if n.get("process_number") in req.step_nos]

    edges = graph.get("edges", [])
    edge_map = {}
    for e in edges:
        src = e.get("source")
        if src not in edge_map:
            edge_map[src] = []
        edge_map[src].append(e.get("target"))

    node_map = {n.get("id"): n for n in nodes}
    created_items = []

    for idx, step in enumerate(step_nodes):
        step_id = step.get("id")
        step_no = step.get("process_number", "")
        process_name = step.get("name", "")
        spec = step.get("specification", "")

        targets = edge_map.get(step_id, [])
        work_elements = [node_map.get(t) for t in targets if node_map.get(t, {}).get("type") == "ProcessWorkElement"]

        if work_elements:
            for we in work_elements:
                item = ControlPlanItem(
                    cp_id=cp_id,
                    step_no=step_no,
                    process_name=process_name,
                    specification_tolerance=spec,
                    process_characteristic=we.get("name", ""),
                    special_class=we.get("classification", ""),
                    source_fmea_node_id=step_id,
                    sort_order=idx,
                )
                db.add(item)
                created_items.append(item)
        else:
            item = ControlPlanItem(
                cp_id=cp_id,
                step_no=step_no,
                process_name=process_name,
                specification_tolerance=spec,
                source_fmea_node_id=step_id,
                sort_order=idx,
            )
            db.add(item)
            created_items.append(item)

    cp.fmea_ref_id = req.fmea_id
    await db.commit()
    for item in created_items:
        await db.refresh(item)

    await create_audit_log(db, cp.created_by or uuid.uuid4(), "import", "control_plan", str(cp_id),
                           f"从 PFMEA {fmea.document_no} 导入 {len(created_items)} 行")
    return created_items


async def check_stale_items(db: AsyncSession, cp_id: uuid.UUID) -> list[dict]:
    cp_result = await db.execute(select(ControlPlan).where(ControlPlan.cp_id == cp_id))
    cp = cp_result.scalar_one_or_none()
    if not cp or not cp.fmea_ref_id:
        return []

    fmea_result = await db.execute(select(FMEADocument).where(FMEADocument.fmea_id == cp.fmea_ref_id))
    fmea = fmea_result.scalar_one_or_none()
    if not fmea:
        return []

    graph = fmea.graph_data or {"nodes": []}
    nodes = graph.get("nodes", [])
    node_map = {n.get("id"): n for n in nodes}

    items_result = await db.execute(select(ControlPlanItem).where(ControlPlanItem.cp_id == cp_id))
    items = items_result.scalars().all()

    stale = []
    for item in items:
        if not item.source_fmea_node_id:
            continue
        node = node_map.get(item.source_fmea_node_id)
        if not node:
            stale.append({
                "item_id": str(item.item_id),
                "step_no": item.step_no,
                "status": "source_deleted",
                "diff_fields": None,
            })
            continue

        diffs = []
        if node.get("name") != item.process_name:
            diffs.append("process_name")
        if node.get("process_number") != item.step_no:
            diffs.append("step_no")

        if diffs:
            stale.append({
                "item_id": str(item.item_id),
                "step_no": item.step_no,
                "status": "modified",
                "diff_fields": diffs,
            })

    return stale
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/services/control_plan_service.py
git commit -m "feat: add control plan service with import and stale check"
```

---

## Task 5: 后端 API

**Files:**
- Create: `backend/app/api/control_plan.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 API 路由**

```python
# backend/app/api/control_plan.py
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User
from app.schemas.control_plan import (
    ControlPlanCreate, ControlPlanUpdate, ControlPlanResponse,
    ControlPlanListResponse, ImportFromFMEARequest,
)
from app.services import control_plan_service

router = APIRouter(prefix="/control-plans", tags=["控制计划"])


@router.post("", response_model=ControlPlanResponse)
async def create_control_plan(
    data: ControlPlanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        cp = await control_plan_service.create_control_plan(db, data, user.user_id)
        return cp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=ControlPlanListResponse)
async def list_control_plans(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await control_plan_service.list_control_plans(db, page, page_size)


@router.get("/{cp_id}", response_model=ControlPlanResponse)
async def get_control_plan(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if not cp:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    return cp


@router.put("/{cp_id}", response_model=ControlPlanResponse)
async def update_control_plan(
    cp_id: uuid.UUID,
    data: ControlPlanUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if not cp:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    try:
        return await control_plan_service.update_control_plan(db, cp, data, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{cp_id}")
async def delete_control_plan(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if not cp:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    await control_plan_service.delete_control_plan(db, cp, user.user_id)
    return {"message": "已删除"}


@router.post("/{cp_id}/import-from-fmea")
async def import_from_fmea(
    cp_id: uuid.UUID,
    req: ImportFromFMEARequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        items = await control_plan_service.import_from_fmea(db, cp_id, req)
        return {"imported_count": len(items)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{cp_id}/stale-check")
async def stale_check(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stale = await control_plan_service.check_stale_items(db, cp_id)
    return {"stale_items": stale}


@router.post("/{cp_id}/approve")
async def approve_control_plan(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if not cp:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    if user.role not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="仅管理员或经理可批准")
    return await control_plan_service.approve_control_plan(db, cp, user.user_id)
```

- [ ] **Step 2: 修改 main.py 注册路由**

```python
# backend/app/main.py — 在现有 import 和 app.include_router 附近添加
from app.api import control_plan

app.include_router(control_plan.router)
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/api/control_plan.py backend/app/main.py
git commit -m "feat: add control plan API routes"
```

---

## Task 6: 后端验证

- [ ] **Step 1: 启动后端服务测试**

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- [ ] **Step 2: 用 curl 或浏览器测试 API**

```bash
# 测试创建
curl -X POST http://localhost:8000/api/control-plans \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"title": "测试控制计划", "document_no": "CP-TEST-001"}'

# 测试列表
curl http://localhost:8000/api/control-plans \
  -H "Authorization: Bearer <token>"
```

Expected: 200 OK，返回控制计划数据。

---

## Task 7: 前端类型和 API

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/controlPlan.ts`

- [ ] **Step 1: 在 types/index.ts 中添加接口**

```typescript
// frontend/src/types/index.ts — 在现有类型之后追加

export interface ControlPlanItem {
  item_id: string;
  step_no: string;
  process_name: string;
  equipment: string;
  characteristic_no: string;
  product_characteristic: string;
  process_characteristic: string;
  special_class: string;
  specification_tolerance: string;
  evaluation_method: string;
  sample_size: string;
  sample_frequency: string;
  control_method: string;
  reaction_plan: string;
  source_fmea_node_id: string | null;
  sort_order: number;
}

export interface ControlPlan {
  cp_id: string;
  document_no: string;
  title: string;
  fmea_ref_id: string | null;
  product_line_code: string;
  status: string;
  version: number;
  phase: string;
  part_no: string;
  part_name: string;
  contact_info: string;
  drawing_rev: string;
  org_factory: string;
  core_group: string;
  items: ControlPlanItem[];
  created_by: string | null;
  updated_by: string | null;
  approved_by: string | null;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
}

export interface ControlPlanListResponse {
  items: ControlPlan[];
  total: number;
  page: number;
  page_size: number;
}
```

- [ ] **Step 2: 创建 API 文件**

```typescript
// frontend/src/api/controlPlan.ts
import { client } from "./client";
import type { ControlPlan, ControlPlanListResponse } from "../types";

export const getControlPlans = (page = 1, page_size = 20) =>
  client.get<ControlPlanListResponse>("/control-plans", { params: { page, page_size } });

export const getControlPlan = (id: string) =>
  client.get<ControlPlan>(`/control-plans/${id}`);

export const createControlPlan = (data: Partial<ControlPlan>) =>
  client.post<ControlPlan>("/control-plans", data);

export const updateControlPlan = (id: string, data: Partial<ControlPlan>) =>
  client.put<ControlPlan>(`/control-plans/${id}`, data);

export const deleteControlPlan = (id: string) =>
  client.delete(`/control-plans/${id}`);

export const importFromFMEA = (cpId: string, fmeaId: string, stepNos?: string[]) =>
  client.post(`/control-plans/${cpId}/import-from-fmea`, { fmea_id: fmeaId, step_nos: stepNos });

export const checkStaleItems = (cpId: string) =>
  client.get<{ stale_items: Array<{ item_id: string; step_no: string | null; status: string; diff_fields: string[] | null }> }>(`/control-plans/${cpId}/stale-check`);

export const approveControlPlan = (id: string) =>
  client.post(`/control-plans/${id}/approve`);
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/types/index.ts frontend/src/api/controlPlan.ts
git commit -m "feat: add ControlPlan frontend types and API"
```

---

## Task 8: 前端导入对话框组件

**Files:**
- Create: `frontend/src/components/control-plan/ImportFromFMEAModal.tsx`

- [ ] **Step 1: 创建导入对话框**

```tsx
// frontend/src/components/control-plan/ImportFromFMEAModal.tsx
import { useState, useEffect } from "react";
import { Modal, Select, Table, Button, message } from "antd";
import type { FMEADocument } from "../../types";
import { getFMEAList } from "../../api/fmea";
import { importFromFMEA } from "../../api/controlPlan";

interface Props {
  cpId: string;
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function ImportFromFMEAModal({ cpId, open, onClose, onSuccess }: Props) {
  const [fmeas, setFmeas] = useState<FMEADocument[]>([]);
  const [selectedFmeaId, setSelectedFmeaId] = useState<string | null>(null);
  const [steps, setSteps] = useState<Array<{ id: string; name: string; process_number: string }>>([]);
  const [selectedSteps, setSelectedSteps] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      getFMEAList(1, 100).then((res) => {
        const pfmeas = res.data.items.filter((f) => f.fmea_type === "PFMEA" && f.status === "approved");
        setFmeas(pfmeas);
      });
    }
  }, [open]);

  useEffect(() => {
    if (selectedFmeaId) {
      const fmea = fmeas.find((f) => f.fmea_id === selectedFmeaId);
      if (fmea && fmea.graph_data?.nodes) {
        const stepNodes = fmea.graph_data.nodes
          .filter((n) => n.type === "ProcessStep")
          .map((n) => ({ id: n.id, name: n.name, process_number: n.process_number || "" }));
        setSteps(stepNodes);
        setSelectedSteps(stepNodes.map((s) => s.process_number));
      }
    }
  }, [selectedFmeaId, fmeas]);

  const handleImport = async () => {
    if (!selectedFmeaId) return;
    setLoading(true);
    try {
      await importFromFMEA(cpId, selectedFmeaId, selectedSteps.length > 0 ? selectedSteps : undefined);
      message.success("导入成功");
      onSuccess();
      onClose();
    } catch (e: any) {
      message.error(e.response?.data?.detail || "导入失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title="从 PFMEA 导入"
      open={open}
      onCancel={onClose}
      onOk={handleImport}
      confirmLoading={loading}
      width={700}
    >
      <div style={{ marginBottom: 16 }}>
        <span>选择 PFMEA：</span>
        <Select
          style={{ width: 400 }}
          placeholder="请选择已批准的 PFMEA"
          onChange={(val) => setSelectedFmeaId(val)}
          options={fmeas.map((f) => ({ value: f.fmea_id, label: `${f.document_no} - ${f.title}` }))}
        />
      </div>
      {selectedFmeaId && (
        <Table
          rowKey="id"
          size="small"
          dataSource={steps}
          rowSelection={{
            type: "checkbox",
            selectedRowKeys: selectedSteps,
            onChange: (_, rows) => setSelectedSteps(rows.map((r) => r.process_number)),
          }}
          columns={[
            { title: "工序号", dataIndex: "process_number" },
            { title: "工序名称", dataIndex: "name" },
          ]}
        />
      )}
    </Modal>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/components/control-plan/ImportFromFMEAModal.tsx
git commit -m "feat: add ImportFromFMEAModal component"
```

---

## Task 9: 前端列表页

**Files:**
- Create: `frontend/src/pages/control-plan/ControlPlanListPage.tsx`

- [ ] **Step 1: 创建列表页**

```tsx
// frontend/src/pages/control-plan/ControlPlanListPage.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Button, Space, Tag, message, Popconfirm } from "antd";
import type { ControlPlan } from "../../types";
import { getControlPlans, deleteControlPlan } from "../../api/controlPlan";
import { useAuthStore } from "../../store/authStore";

export default function ControlPlanListPage() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [data, setData] = useState<ControlPlan[]>([]);
  const [loading, setLoading] = useState(false);
  const isAdminOrManager = user?.role === "admin" || user?.role === "manager";

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await getControlPlans();
      setData(res.data.items);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleDelete = async (id: string) => {
    try {
      await deleteControlPlan(id);
      message.success("删除成功");
      fetchData();
    } catch {
      message.error("删除失败");
    }
  };

  const columns = [
    { title: "编号", dataIndex: "document_no" },
    { title: "标题", dataIndex: "title" },
    {
      title: "阶段",
      dataIndex: "phase",
      render: (v: string) =>
        v === "sample" ? "样件" : v === "trial" ? "试生产" : "生产",
    },
    {
      title: "状态",
      dataIndex: "status",
      render: (v: string) => (
        <Tag color={v === "approved" ? "green" : v === "draft" ? "blue" : "orange"}>
          {v === "approved" ? "已批准" : v === "draft" ? "草稿" : v}
        </Tag>
      ),
    },
    { title: "版本", dataIndex: "version" },
    {
      title: "操作",
      render: (_: any, record: ControlPlan) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/control-plans/${record.cp_id}`)}>
            编辑
          </Button>
          {isAdminOrManager && (
            <Button size="small" type="primary" onClick={() => navigate(`/control-plans/${record.cp_id}`)}>
              批准
            </Button>
          )}
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.cp_id)}>
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between" }}>
        <h2>控制计划</h2>
        <Button type="primary" onClick={() => navigate("/control-plans/new")}>
          新建控制计划
        </Button>
      </div>
      <Table rowKey="cp_id" loading={loading} dataSource={data} columns={columns} />
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/pages/control-plan/ControlPlanListPage.tsx
git commit -m "feat: add ControlPlanListPage"
```

---

## Task 10: 前端编辑页

**Files:**
- Create: `frontend/src/pages/control-plan/ControlPlanEditorPage.tsx`

- [ ] **Step 1: 创建编辑页**

```tsx
// frontend/src/pages/control-plan/ControlPlanEditorPage.tsx
import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, Input, Select, Button, Table, message, Alert, Space } from "antd";
import type { ControlPlan, ControlPlanItem } from "../../types";
import {
  getControlPlan, updateControlPlan, createControlPlan,
  checkStaleItems, approveControlPlan,
} from "../../api/controlPlan";
import { useAuthStore } from "../../store/authStore";
import ImportFromFMEAModal from "../../components/control-plan/ImportFromFMEAModal";

const PHASE_OPTIONS = [
  { value: "sample", label: "样件" },
  { value: "trial", label: "试生产" },
  { value: "production", label: "生产" },
];

export default function ControlPlanEditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const isNew = id === "new";
  const isViewer = user?.role === "viewer";
  const isAdminOrManager = user?.role === "admin" || user?.role === "manager";

  const [cp, setCp] = useState<Partial<ControlPlan>>({ phase: "production", items: [] });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [staleAlert, setStaleAlert] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (isNew) return;
    setLoading(true);
    try {
      const res = await getControlPlan(id!);
      setCp(res.data);
    } finally {
      setLoading(false);
    }
  }, [id, isNew]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSave = async () => {
    setSaving(true);
    try {
      if (isNew) {
        const res = await createControlPlan(cp);
        message.success("创建成功");
        navigate(`/control-plans/${res.data.cp_id}`);
      } else {
        await updateControlPlan(id!, cp);
        message.success("保存成功");
      }
    } catch (e: any) {
      message.error(e.response?.data?.detail || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleCheckStale = async () => {
    if (!id || isNew) return;
    try {
      const res = await checkStaleItems(id);
      const stale = res.data.stale_items;
      if (stale.length === 0) {
        setStaleAlert(null);
        message.success("暂无变更");
      } else {
        const steps = stale.map((s: any) => s.step_no || "未知").join(", ");
        setStaleAlert(`关联的 PFMEA 已发生变更，以下行可能已过期：${steps}，建议重新导入或手动核对。`);
      }
    } catch {
      message.error("检测失败");
    }
  };

  const handleApprove = async () => {
    if (!id || isNew) return;
    try {
      await approveControlPlan(id);
      message.success("批准成功");
      fetchData();
    } catch (e: any) {
      message.error(e.response?.data?.detail || "批准失败");
    }
  };

  const updateItem = (index: number, field: keyof ControlPlanItem, value: any) => {
    const items = [...(cp.items || [])];
    items[index] = { ...items[index], [field]: value };
    setCp({ ...cp, items });
  };

  const addItem = () => {
    const items = [...(cp.items || [])];
    items.push({
      item_id: `temp-${Date.now()}`,
      step_no: "",
      process_name: "",
      equipment: "",
      characteristic_no: "",
      product_characteristic: "",
      process_characteristic: "",
      special_class: "",
      specification_tolerance: "",
      evaluation_method: "",
      sample_size: "",
      sample_frequency: "",
      control_method: "",
      reaction_plan: "",
      source_fmea_node_id: null,
      sort_order: items.length,
    });
    setCp({ ...cp, items });
  };

  const removeItem = (index: number) => {
    const items = [...(cp.items || [])];
    items.splice(index, 1);
    setCp({ ...cp, items });
  };

  const columns = [
    { title: "零件/过程编号", dataIndex: "step_no", width: 100, render: (_: any, __: any, idx: number) => (
      <Input disabled={isViewer} value={cp.items?.[idx]?.step_no || ""} onChange={(e) => updateItem(idx, "step_no", e.target.value)} size="small" />
    )},
    { title: "过程名称/操作描述", dataIndex: "process_name", width: 140, render: (_: any, __: any, idx: number) => (
      <Input disabled={isViewer} value={cp.items?.[idx]?.process_name || ""} onChange={(e) => updateItem(idx, "process_name", e.target.value)} size="small" />
    )},
    { title: "设备/工装/夹具", dataIndex: "equipment", width: 120, render: (_: any, __: any, idx: number) => (
      <Input disabled={isViewer} value={cp.items?.[idx]?.equipment || ""} onChange={(e) => updateItem(idx, "equipment", e.target.value)} size="small" />
    )},
    {
      title: "特性",
      children: [
        { title: "编号", dataIndex: "characteristic_no", width: 70, render: (_: any, __: any, idx: number) => (
          <Input disabled={isViewer} value={cp.items?.[idx]?.characteristic_no || ""} onChange={(e) => updateItem(idx, "characteristic_no", e.target.value)} size="small" />
        )},
        { title: "产品特性", dataIndex: "product_characteristic", width: 100, render: (_: any, __: any, idx: number) => (
          <Input disabled={isViewer} value={cp.items?.[idx]?.product_characteristic || ""} onChange={(e) => updateItem(idx, "product_characteristic", e.target.value)} size="small" />
        )},
        { title: "过程特性", dataIndex: "process_characteristic", width: 100, render: (_: any, __: any, idx: number) => (
          <Input disabled={isViewer} value={cp.items?.[idx]?.process_characteristic || ""} onChange={(e) => updateItem(idx, "process_characteristic", e.target.value)} size="small" />
        )},
      ],
    },
    { title: "特殊特性分类", dataIndex: "special_class", width: 90, render: (_: any, __: any, idx: number) => (
      <Select disabled={isViewer} value={cp.items?.[idx]?.special_class || ""} onChange={(v) => updateItem(idx, "special_class", v)} size="small" style={{ width: 80 }}
        options={[{ value: "", label: "-" }, { value: "CC", label: "CC" }, { value: "SC", label: "SC" }]} />
    )},
    { title: "产品/过程/规格/公差", dataIndex: "specification_tolerance", width: 140, render: (_: any, __: any, idx: number) => (
      <Input disabled={isViewer} value={cp.items?.[idx]?.specification_tolerance || ""} onChange={(e) => updateItem(idx, "specification_tolerance", e.target.value)} size="small" />
    )},
    {
      title: "方法",
      children: [
        { title: "评价/测量技术", dataIndex: "evaluation_method", width: 120, render: (_: any, __: any, idx: number) => (
          <Input disabled={isViewer} value={cp.items?.[idx]?.evaluation_method || ""} onChange={(e) => updateItem(idx, "evaluation_method", e.target.value)} size="small" />
        )},
      ],
    },
    {
      title: "样本",
      children: [
        { title: "大小", dataIndex: "sample_size", width: 70, render: (_: any, __: any, idx: number) => (
          <Input disabled={isViewer} value={cp.items?.[idx]?.sample_size || ""} onChange={(e) => updateItem(idx, "sample_size", e.target.value)} size="small" />
        )},
        { title: "频次", dataIndex: "sample_frequency", width: 70, render: (_: any, __: any, idx: number) => (
          <Input disabled={isViewer} value={cp.items?.[idx]?.sample_frequency || ""} onChange={(e) => updateItem(idx, "sample_frequency", e.target.value)} size="small" />
        )},
      ],
    },
    { title: "控制方法", dataIndex: "control_method", width: 120, render: (_: any, __: any, idx: number) => (
      <Input disabled={isViewer} value={cp.items?.[idx]?.control_method || ""} onChange={(e) => updateItem(idx, "control_method", e.target.value)} size="small" />
    )},
    { title: "反应计划", dataIndex: "reaction_plan", width: 120, render: (_: any, __: any, idx: number) => (
      <Input disabled={isViewer} value={cp.items?.[idx]?.reaction_plan || ""} onChange={(e) => updateItem(idx, "reaction_plan", e.target.value)} size="small" />
    )},
    {
      title: "操作",
      width: 60,
      render: (_: any, __: any, idx: number) => (
        !isViewer && <Button size="small" danger onClick={() => removeItem(idx)}>删除</Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      {staleAlert && <Alert message={staleAlert} type="warning" showIcon closable onClose={() => setStaleAlert(null)} style={{ marginBottom: 16 }} />}

      <Card title="控制计划信息" style={{ marginBottom: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <div style={{ marginBottom: 8 }}>
              <span>零件编号：</span>
              <Input disabled={isViewer} value={cp.part_no || ""} onChange={(e) => setCp({ ...cp, part_no: e.target.value })} style={{ width: 300 }} />
            </div>
            <div style={{ marginBottom: 8 }}>
              <span>零件名称：</span>
              <Input disabled={isViewer} value={cp.part_name || ""} onChange={(e) => setCp({ ...cp, part_name: e.target.value })} style={{ width: 300 }} />
            </div>
            <div style={{ marginBottom: 8 }}>
              <span>联系人：</span>
              <Input disabled={isViewer} value={cp.contact_info || ""} onChange={(e) => setCp({ ...cp, contact_info: e.target.value })} style={{ width: 300 }} />
            </div>
            <div style={{ marginBottom: 8 }}>
              <span>核心小组：</span>
              <Input disabled={isViewer} value={cp.core_group || ""} onChange={(e) => setCp({ ...cp, core_group: e.target.value })} style={{ width: 300 }} />
            </div>
          </div>
          <div>
            <div style={{ marginBottom: 8 }}>
              <span>组织/工厂：</span>
              <Input disabled={isViewer} value={cp.org_factory || ""} onChange={(e) => setCp({ ...cp, org_factory: e.target.value })} style={{ width: 300 }} />
            </div>
            <div style={{ marginBottom: 8 }}>
              <span>图纸版本：</span>
              <Input disabled={isViewer} value={cp.drawing_rev || ""} onChange={(e) => setCp({ ...cp, drawing_rev: e.target.value })} style={{ width: 300 }} />
            </div>
            <div style={{ marginBottom: 8 }}>
              <span>阶段：</span>
              <Select disabled={isViewer} value={cp.phase || "production"} onChange={(v) => setCp({ ...cp, phase: v })} style={{ width: 200 }}
                options={PHASE_OPTIONS} />
            </div>
            <div style={{ marginBottom: 8 }}>
              <span>关联 PFMEA：</span>
              <Input value={cp.fmea_ref_id || "未关联"} disabled style={{ width: 300 }} />
            </div>
          </div>
        </div>
      </Card>

      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" loading={saving} onClick={handleSave} disabled={isViewer}>保存</Button>
        {!isNew && !isViewer && (
          <Button onClick={() => setImportOpen(true)}>从 PFMEA 导入</Button>
        )}
        {!isNew && (
          <Button onClick={handleCheckStale}>检查 PFMEA 变更</Button>
        )}
        {!isNew && isAdminOrManager && cp.status !== "approved" && (
          <Button type="primary" onClick={handleApprove}>批准</Button>
        )}
        {!isNew && (
          <span>状态：<strong>{cp.status === "approved" ? "已批准" : cp.status === "draft" ? "草稿" : cp.status}</strong></span>
        )}
      </Space>

      <Table
        loading={loading}
        dataSource={cp.items || []}
        columns={columns}
        rowKey="item_id"
        scroll={{ x: 1600 }}
        pagination={false}
        footer={() => !isViewer && <Button onClick={addItem}>新增行</Button>}
      />

      {!isNew && (
        <ImportFromFMEAModal
          cpId={id!}
          open={importOpen}
          onClose={() => setImportOpen(false)}
          onSuccess={fetchData}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/pages/control-plan/ControlPlanEditorPage.tsx
git commit -m "feat: add ControlPlanEditorPage with 13-column table"
```

---

## Task 11: 前端路由和导航

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: 修改 App.tsx 添加路由**

```tsx
// frontend/src/App.tsx — 在现有路由中追加
import ControlPlanListPage from "./pages/control-plan/ControlPlanListPage";
import ControlPlanEditorPage from "./pages/control-plan/ControlPlanEditorPage";

// 在 Route 配置中添加：
<Route path="/control-plans" element={<ControlPlanListPage />} />
<Route path="/control-plans/:id" element={<ControlPlanEditorPage />} />
```

- [ ] **Step 2: 修改 AppLayout.tsx 添加侧边栏菜单**

```tsx
// frontend/src/components/layout/AppLayout.tsx — 在 items 数组中添加
{
  key: "/control-plans",
  icon: <FileTextOutlined />,
  label: <Link to="/control-plans">控制计划</Link>,
}
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat: add control plan routes and sidebar navigation"
```

---

## Task 12: 前端构建验证

- [ ] **Step 1: 运行构建**

```bash
cd frontend
npm run build
```

Expected: `tsc -b` 无类型错误，`vite build` 成功生成 dist。

- [ ] **Step 2: 运行 lint**

```bash
cd frontend
npm run lint
```

Expected: 无 ESLint 错误。

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: complete control plan editor MVP"
```

---

## 自检清单

| 规格要求 | 对应任务 |
|----------|----------|
| 独立数据表（control_plans + control_plan_items） | Task 1, 2 |
| PFMEA-only 关联校验 | Task 4 (`import_from_fmea`) |
| source_fmea_node_id 引用跟踪 | Task 1, 4 |
| 变更检测（stale-check） | Task 4, 10 |
| 13 列表格（含特性/方法/样本分组） | Task 10 |
| 阶段支持（样件/试生产/生产） | Task 1, 10 |
| 表头信息（零件编号/名称等） | Task 1, 10 |
| 权限控制（viewer/engineer/manager） | Task 5, 10 |
| approved 状态不可编辑 | Task 4, 10 |
| AuditLog 自动写入 | Task 4 |
