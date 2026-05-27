# SCAR 管理模块实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现供应商纠正措施请求 (SCAR) 管理模块，支持 IQC 拒收触发 SCAR、5 态生命周期、8D/CAPA 关联、独立列表+详情前端页面。

**Architecture:** 独立 `/api/scars` 路由（与 CAPA/FMEA 同级），复用现有 `SupplierSCAR` model 并扩展 2 个字段。后端遵循现有 service→API 分层，前端遵循 Ant Design 列表+详情两页式模式。

**Tech Stack:** FastAPI async + SQLAlchemy 2.0 + Pydantic v2 | React 18 + TypeScript + Ant Design 5 + @ant-design/charts

**Design Spec:** `docs/superpowers/specs/2026-05-27-scar-module-design.md`

**Note:** 本项目无自动化测试框架（无 pytest/Vitest）。验证方式为启动后端检查端点 + 前端 TypeScript 编译。

---

## 文件结构总览

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `backend/app/models/supplier.py` | 添加 `capa_ref_id`、`resolution_summary` 字段及 `capa` relationship |
| 新增 | `backend/alembic/versions/022_add_scar_capa_fields.py` | Migration |
| 新增 | `backend/app/schemas/scar.py` | Pydantic schemas |
| 修改 | `backend/app/schemas/__init__.py` | 注册 scar schemas |
| 修改 | `backend/app/schemas/supplier.py` | 标记旧 SCAR schemas 废弃 |
| 新增 | `backend/app/services/scar_service.py` | 业务逻辑 + 状态机 |
| 新增 | `backend/app/api/scar.py` | API 路由 |
| 修改 | `backend/app/main.py` | 注册 scar router |
| 修改 | `backend/app/services/supplier_quality_service.py` | `open_scar_count` 统计修正 |
| 修改 | `frontend/src/types/index.ts` | 扩展 `SupplierSCAR` 类型 |
| 新增 | `frontend/src/api/scar.ts` | API 客户端 |
| 新增 | `frontend/src/pages/scar/SCARListPage.tsx` | 列表页 |
| 新增 | `frontend/src/pages/scar/SCARDetailPage.tsx` | 详情页 |
| 修改 | `frontend/src/App.tsx` | 添加路由 |
| 修改 | `frontend/src/components/layout/AppLayout.tsx` | 侧边栏菜单 |
| 修改 | `frontend/src/pages/iqc/IqcInspectionDetailPage.tsx` | trigger-scar 后跳转 |
| 修改 | `frontend/src/pages/supplier/components/DashboardView.tsx` | 标签修正 |
| 修改 | `frontend/src/pages/supplier/components/SupplierDetailView.tsx` | 标签修正 |

---

### Task 1: 数据模型 + Alembic Migration

**Files:**
- Modify: `backend/app/models/supplier.py`
- Create: `backend/alembic/versions/022_add_scar_capa_fields.py`

- [ ] **Step 1: 修改 SupplierSCAR model**

在 `backend/app/models/supplier.py` 的 `SupplierSCAR` 类末尾（`supplier = relationship(...)` 之前）添加两个字段和一个 relationship：

```python
    capa_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="SET NULL"), nullable=True
    )
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
```

在 `supplier = relationship(...)` 行之后添加：

```python
    capa = relationship("CAPAEightD", foreign_keys=[capa_ref_id])
```

确保文件顶部 `from sqlalchemy import ForeignKey, String, Text, Date, DateTime, func` 和 `from sqlalchemy.orm import Mapped, mapped_column, relationship` 已导入（通常已有）。

- [ ] **Step 2: 创建 Alembic migration**

先运行 `alembic heads` 确认当前分支状态。如果 `021_customer_quality_core` 和 `021_iqc_module` 已被其他合并节点合并过，则 `down_revision` 改为该合并节点的 revision。

创建 `backend/alembic/versions/022_add_scar_capa_fields.py`：

```python
"""add capa_ref_id and resolution_summary to supplier_scars

Revision ID: 022_add_scar_capa
Revises: 021_customer_quality_core, 021_iqc_module (merge)
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "022_add_scar_capa"
down_revision = ("021_customer_quality_core", "021_iqc_module")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "supplier_scars",
        sa.Column("capa_ref_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_supplier_scars_capa_ref_id",
        "supplier_scars",
        "capa_eightd",
        ["capa_ref_id"],
        ["report_id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "supplier_scars",
        sa.Column("resolution_summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("supplier_scars", "resolution_summary")
    op.drop_constraint("fk_supplier_scars_capa_ref_id", "supplier_scars", type_="foreignkey")
    op.drop_column("supplier_scars", "capa_ref_id")
```

- [ ] **Step 3: 验证后端启动**

```bash
cd backend && python -c "from app.models.supplier import SupplierSCAR; print('capa_ref_id' in SupplierSCAR.__table__.columns)"
```

Expected: `True`（SQLAlchemy model 层面确认字段存在）

---

### Task 2: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/scar.py`
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/schemas/supplier.py`

- [ ] **Step 1: 创建 scar.py schemas**

创建 `backend/app/schemas/scar.py`：

```python
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class SCARCreate(BaseModel):
    supplier_id: uuid.UUID
    source_type: Literal["iqc", "complaint", "rma", "manual"]
    source_id: uuid.UUID | None = None
    description: str
    product_line_code: str | None = None
    requested_action: str | None = None
    due_date: date | None = None


class SCARUpdate(BaseModel):
    description: str | None = None
    requested_action: str | None = None
    due_date: date | None = None


class SCARResponse(BaseModel):
    scar_id: uuid.UUID
    scar_no: str
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    supplier_no: str | None = None
    source_type: str
    source_id: uuid.UUID | None
    description: str
    product_line_code: str | None
    requested_action: str | None
    supplier_response: str | None
    status: str
    capa_ref_id: uuid.UUID | None
    resolution_summary: str | None
    issued_by: uuid.UUID | None
    issued_date: date | None
    due_date: date | None
    closed_date: date | None
    created_at: datetime
    updated_at: datetime


class SCARListResponse(BaseModel):
    items: list[SCARResponse]
    total: int
    page: int
    page_size: int


class SCARTransitionRequest(BaseModel):
    action: Literal["start", "respond", "verify", "reject", "close", "reopen"]
    supplier_response: str | None = None
    resolution_summary: str | None = None


class SCARLinkCAPARequest(BaseModel):
    capa_ref_id: uuid.UUID
```

- [ ] **Step 2: 注册 schemas**

在 `backend/app/schemas/__init__.py` 末尾添加：

```python
from app.schemas import scar
```

- [ ] **Step 3: 标记旧 SCAR schemas 废弃**

在 `backend/app/schemas/supplier.py` 中找到 `# ─── SCAR ───` 部分（约 L257），在该注释行上方添加：

```python
# DEPRECATED: 以下 SCAR schemas 已被 app.schemas.scar 替代，保留仅供 trigger-scar 兼容，后续清理
```

- [ ] **Step 4: 验证 schema 导入**

```bash
cd backend && python -c "from app.schemas import scar; print(scar.SCARCreate.model_fields.keys())"
```

Expected: `dict_keys(['supplier_id', 'source_type', 'source_id', 'description', 'product_line_code', 'requested_action', 'due_date'])`

---

### Task 3: SCAR Service 层

**Files:**
- Create: `backend/app/services/scar_service.py`

- [ ] **Step 1: 创建 scar_service.py**

创建 `backend/app/services/scar_service.py`，包含完整的 CRUD + 状态机 + CAPA 关联逻辑：

```python
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.supplier import Supplier, SupplierSCAR
from app.models.capa import CAPAEightD
from app.models.audit import AuditLog


SCAR_TRANSITIONS = {
    "start":   ("open",         "in_progress"),
    "respond": ("in_progress",  "responded"),
    "verify":  ("responded",    "verified"),
    "reject":  ("responded",    "open"),
    "close":   ("verified",     "closed"),
    "reopen":  ("verified",     "in_progress"),
}

SCAR_REQUIRED_FIELDS = {
    "respond": ["supplier_response"],
    "close":   ["resolution_summary"],
}


async def _next_scar_no(db: AsyncSession) -> str:
    today = datetime.now(timezone.utc).strftime("%y%m%d")
    prefix = f"SCAR-{today}"
    result = await db.execute(
        select(SupplierSCAR.scar_no)
        .where(SupplierSCAR.scar_no.like(f"{prefix}-%"))
        .order_by(SupplierSCAR.scar_no.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if last:
        seq = int(last.split("-")[-1]) + 1
    else:
        seq = 1
    return f"{prefix}-{seq:03d}"


async def list_scars(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    statuses: list[str] | None = None,
    supplier_id: str | None = None,
    source_type: str | None = None,
) -> tuple[list[SupplierSCAR], int]:
    query = select(SupplierSCAR).options(selectinload(SupplierSCAR.supplier))
    count_query = select(func.count()).select_from(SupplierSCAR)

    if statuses:
        query = query.where(SupplierSCAR.status.in_(statuses))
        count_query = count_query.where(SupplierSCAR.status.in_(statuses))
    if supplier_id:
        query = query.where(SupplierSCAR.supplier_id == supplier_id)
        count_query = count_query.where(SupplierSCAR.supplier_id == supplier_id)
    if source_type:
        query = query.where(SupplierSCAR.source_type == source_type)
        count_query = count_query.where(SupplierSCAR.source_type == source_type)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(SupplierSCAR.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())
    return items, total


async def get_scar(db: AsyncSession, scar_id: uuid.UUID) -> SupplierSCAR | None:
    result = await db.execute(
        select(SupplierSCAR)
        .options(selectinload(SupplierSCAR.supplier))
        .where(SupplierSCAR.scar_id == scar_id)
    )
    return result.scalar_one_or_none()


async def create_scar(
    db: AsyncSession,
    *,
    supplier_id: uuid.UUID,
    source_type: str,
    description: str,
    user_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
    product_line_code: str | None = None,
    requested_action: str | None = None,
    due_date: date | None = None,
) -> SupplierSCAR:
    # Validate supplier exists
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise ValueError("供应商不存在")

    # Generate SCAR number with retry on collision
    for attempt in range(3):
        scar_no = await _next_scar_no(db)
        scar = SupplierSCAR(
            scar_no=scar_no,
            supplier_id=supplier_id,
            source_type=source_type,
            source_id=source_id,
            description=description,
            product_line_code=product_line_code,
            requested_action=requested_action,
            due_date=due_date,
            issued_by=user_id,
            issued_date=date.today(),
        )
        db.add(scar)
        try:
            await db.flush()
            break
        except IntegrityError:
            # 仅在 scar_no unique 冲突时重试；其他约束冲突（如 FK 无效）向上抛出
            await db.rollback()
            if attempt == 2:
                raise ValueError("SCAR 编号生成冲突，请重试")
            continue

    db.add(AuditLog(
        table_name="supplier_scars",
        record_id=scar.scar_id,
        action="CREATE",
        changed_fields={"scar_no": scar.scar_no, "supplier_id": str(supplier_id), "source_type": source_type, "description": description},
        operated_by=user_id,
    ))
    await db.commit()
    await db.refresh(scar)
    # Re-load with supplier relationship
    return await get_scar(db, scar.scar_id)


async def update_scar(
    db: AsyncSession,
    scar: SupplierSCAR,
    *,
    user_id: uuid.UUID,
    description: str | None = None,
    requested_action: str | None = None,
    due_date: date | None = None,
) -> SupplierSCAR:
    if description is not None:
        scar.description = description
    if requested_action is not None:
        scar.requested_action = requested_action
    if due_date is not None:
        scar.due_date = due_date

    db.add(AuditLog(
        table_name="supplier_scars",
        record_id=scar.scar_id,
        action="UPDATE",
        changed_fields={k: v for k, v in {"description": description, "requested_action": requested_action, "due_date": str(due_date) if due_date else None}.items() if v is not None},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_scar(db, scar.scar_id)


async def transition_scar(
    db: AsyncSession,
    scar: SupplierSCAR,
    action: str,
    user_id: uuid.UUID,
    supplier_response: str | None = None,
    resolution_summary: str | None = None,
) -> SupplierSCAR:
    if action not in SCAR_TRANSITIONS:
        raise ValueError(f"无效动作: {action}")

    expected_from, to_status = SCAR_TRANSITIONS[action]
    if scar.status != expected_from:
        raise ValueError(f"当前状态 {scar.status} 不允许执行 {action}（需要 {expected_from}）")

    # Check required fields
    required = SCAR_REQUIRED_FIELDS.get(action, [])
    if "supplier_response" in required and not supplier_response:
        raise ValueError("供应商回复为必填项")
    if "resolution_summary" in required and not resolution_summary:
        raise ValueError("解决摘要为必填项")

    old_status = scar.status
    scar.status = to_status

    if supplier_response:
        scar.supplier_response = supplier_response
    if resolution_summary:
        scar.resolution_summary = resolution_summary
    if to_status == "closed":
        scar.closed_date = date.today()

    db.add(AuditLog(
        table_name="supplier_scars",
        record_id=scar.scar_id,
        action="TRANSITION",
        old_values={"status": old_status},
        new_values={"status": to_status},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_scar(db, scar.scar_id)


async def link_capa(
    db: AsyncSession,
    scar: SupplierSCAR,
    capa_ref_id: uuid.UUID,
    user_id: uuid.UUID,
) -> SupplierSCAR:
    capa = await db.get(CAPAEightD, capa_ref_id)
    if not capa:
        raise ValueError("CAPA 记录不存在")

    scar.capa_ref_id = capa_ref_id

    db.add(AuditLog(
        table_name="supplier_scars",
        record_id=scar.scar_id,
        action="LINK_CAPA",
        changed_fields={"capa_ref_id": str(capa_ref_id)},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_scar(db, scar.scar_id)
```

- [ ] **Step 2: 验证 service 导入**

```bash
cd backend && python -c "from app.services.scar_service import SCAR_TRANSITIONS; print(SCAR_TRANSITIONS)"
```

Expected: dict with 6 transition entries

---

### Task 4: SCAR API 路由

**Files:**
- Create: `backend/app/api/scar.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 scar.py API 路由**

创建 `backend/app/api/scar.py`：

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin, require_manager_or_admin
from app.models.user import User
from app.schemas import scar as scar_schemas
from app.services import scar_service

router = APIRouter(prefix="/api/scars", tags=["scars"])


def _to_response(s) -> dict:
    """Convert SupplierSCAR ORM object with loaded supplier to SCARResponse dict."""
    return scar_schemas.SCARResponse(
        scar_id=s.scar_id,
        scar_no=s.scar_no,
        supplier_id=s.supplier_id,
        supplier_name=s.supplier.name if s.supplier else None,
        supplier_no=s.supplier.supplier_no if s.supplier else None,
        source_type=s.source_type,
        source_id=s.source_id,
        description=s.description,
        product_line_code=s.product_line_code,
        requested_action=s.requested_action,
        supplier_response=s.supplier_response,
        status=s.status,
        capa_ref_id=s.capa_ref_id,
        resolution_summary=s.resolution_summary,
        issued_by=s.issued_by,
        issued_date=s.issued_date,
        due_date=s.due_date,
        closed_date=s.closed_date,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.get("", response_model=scar_schemas.SCARListResponse)
async def list_scars(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Comma-separated statuses"),
    supplier_id: uuid.UUID | None = Query(None),
    source_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    statuses = status.split(",") if status else None
    items, total = await scar_service.list_scars(
        db, page, page_size, statuses, str(supplier_id) if supplier_id else None, source_type
    )
    return scar_schemas.SCARListResponse(
        items=[_to_response(s) for s in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{scar_id}", response_model=scar_schemas.SCARResponse)
async def get_scar(
    scar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    return _to_response(scar)


@router.post("", response_model=scar_schemas.SCARResponse)
async def create_scar(
    req: scar_schemas.SCARCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        scar = await scar_service.create_scar(
            db,
            supplier_id=req.supplier_id,
            source_type=req.source_type,
            source_id=req.source_id,
            description=req.description,
            product_line_code=req.product_line_code,
            requested_action=req.requested_action,
            due_date=req.due_date,
            user_id=user.user_id,
        )
        return _to_response(scar)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{scar_id}", response_model=scar_schemas.SCARResponse)
async def update_scar(
    scar_id: uuid.UUID,
    req: scar_schemas.SCARUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    try:
        scar = await scar_service.update_scar(
            db, scar,
            user_id=user.user_id,
            description=req.description,
            requested_action=req.requested_action,
            due_date=req.due_date,
        )
        return _to_response(scar)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{scar_id}/transition", response_model=scar_schemas.SCARResponse)
async def transition_scar(
    scar_id: uuid.UUID,
    req: scar_schemas.SCARTransitionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Route-level role check
    if req.action in ("verify", "reject", "close", "reopen"):
        if user.role not in ("admin", "manager"):
            raise HTTPException(403, "需要 manager 或 admin 权限")
    elif req.action in ("start", "respond"):
        if user.role not in ("admin", "manager", "quality_engineer"):
            raise HTTPException(403, "需要 engineer 或更高权限")

    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    try:
        scar = await scar_service.transition_scar(
            db, scar, req.action, user_id=user.user_id,
            supplier_response=req.supplier_response,
            resolution_summary=req.resolution_summary,
        )
        return _to_response(scar)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{scar_id}/link-capa", response_model=scar_schemas.SCARResponse)
async def link_capa(
    scar_id: uuid.UUID,
    req: scar_schemas.SCARLinkCAPARequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    try:
        scar = await scar_service.link_capa(db, scar, req.capa_ref_id, user.user_id)
        return _to_response(scar)
    except ValueError as e:
        raise HTTPException(400, str(e))
```

- [ ] **Step 2: 注册 router 到 main.py**

在 `backend/app/main.py` 的 import 区域（约 L36 之后）添加：

```python
from app.api.scar import router as scar_router
```

在 `app.include_router(customer_quality_router)` 之后添加：

```python
app.include_router(scar_router)
```

- [ ] **Step 3: 验证后端启动 + API 端点**

```bash
cd backend && python -c "
from app.api.scar import router
for route in router.routes:
    print(f'{route.methods} {route.path}')
"
```

Expected: 6 endpoints listed (GET /, GET /{scar_id}, POST /, PUT /{scar_id}, POST /{scar_id}/transition, POST /{scar_id}/link-capa)

---

### Task 5: 供应商质量看板统计修正

**Files:**
- Modify: `backend/app/services/supplier_quality_service.py`

- [ ] **Step 1: 修改 open_scar_count 统计**

在 `supplier_quality_service.py` 中找到所有 `SupplierSCAR.status == "open"` 的位置，改为 `SupplierSCAR.status != "closed"`。

具体位置（3 处）：

1. `get_quality_dashboard()` 中的总览 open SCAR count（约 L52-54）：
```python
# 修改前
select(func.count()).select_from(SupplierSCAR).where(SupplierSCAR.status == "open")
# 修改后
select(func.count()).select_from(SupplierSCAR).where(SupplierSCAR.status != "closed")
```

2. `get_quality_dashboard()` 中排名循环的 per-supplier SCAR 统计（约 L155-158）：
```python
# 修改前
.where(SupplierSCAR.supplier_id == row.supplier_id, SupplierSCAR.status == "open")
# 修改后
.where(SupplierSCAR.supplier_id == row.supplier_id, SupplierSCAR.status != "closed")
```

3. `get_supplier_quality_detail()` 中的 open_scar_count（约 L265-267）：
```python
# 修改前
.where(SupplierSCAR.supplier_id == supplier_id, SupplierSCAR.status == "open")
# 修改后
.where(SupplierSCAR.supplier_id == supplier_id, SupplierSCAR.status != "closed")
```

4. `get_supplier_compare()` — 间接调用 `get_supplier_quality_detail()`，无需额外修改。

- [ ] **Step 2: 验证导入**

```bash
cd backend && python -c "from app.services.supplier_quality_service import get_quality_dashboard; print('OK')"
```

Expected: `OK`

---

### Task 6: 前端 TypeScript 类型扩展

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: 更新 SupplierSCAR 接口**

在 `frontend/src/types/index.ts` 中找到现有的 `SupplierSCAR` interface（约 L613），替换为：

```typescript
export interface SupplierSCAR {
  scar_id: string;
  scar_no: string;
  supplier_id: string;
  supplier_name?: string;
  supplier_no?: string;
  source_type: 'iqc' | 'complaint' | 'rma' | 'manual';
  source_id?: string;
  description: string;
  product_line_code?: string;
  requested_action?: string;
  supplier_response?: string;
  status: 'open' | 'in_progress' | 'responded' | 'verified' | 'closed';
  capa_ref_id?: string;
  resolution_summary?: string;
  issued_by?: string;
  issued_date?: string;
  due_date?: string;
  closed_date?: string;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 2: 添加 SCAR 请求/响应类型**

在同一文件末尾追加（在现有类型定义之后）：

```typescript
export interface SCARListResponse {
  items: SupplierSCAR[];
  total: number;
  page: number;
  page_size: number;
}

export interface SCARCreate {
  supplier_id: string;
  source_type: 'iqc' | 'complaint' | 'rma' | 'manual';
  source_id?: string;
  description: string;
  product_line_code?: string;
  requested_action?: string;
  due_date?: string;
}

export interface SCARUpdate {
  description?: string;
  requested_action?: string;
  due_date?: string;
}

export interface SCARTransitionRequest {
  action: 'start' | 'respond' | 'verify' | 'reject' | 'close' | 'reopen';
  supplier_response?: string;
  resolution_summary?: string;
}

export interface SCARLinkCAPARequest {
  capa_ref_id: string;
}
```

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit
```

Expected: exit code 0，无新增类型错误（若有非本任务预存错误，先记录下来，最终验收必须全部通过）

Expected: 无 SupplierSCAR 相关类型错误（可能有其他已有警告）

---

### Task 7: 前端 API 客户端

**Files:**
- Create: `frontend/src/api/scar.ts`
- Modify: `frontend/src/api/capa.ts`

- [ ] **Step 1: 扩展 createCAPA 参数类型**

在 `frontend/src/api/capa.ts` 中找到 `createCAPA` 函数，将参数中的 `product_line_code` 添加为可选：

```typescript
export async function createCAPA(data: {
  title: string;
  document_no: string;
  severity: string;
  due_date?: string;
  product_line_code?: string;  // 新增
}): Promise<CAPAReport> {
```

- [ ] **Step 2: 创建 scar.ts API 客户端**

创建 `frontend/src/api/scar.ts`：

```typescript
import client from "./client";
import type {
  SCARListResponse,
  SupplierSCAR,
  SCARCreate,
  SCARUpdate,
  SCARTransitionRequest,
  SCARLinkCAPARequest,
} from "../types";

export async function listSCARs(params: {
  page?: number;
  page_size?: number;
  status?: string;
  supplier_id?: string;
  source_type?: string;
}): Promise<SCARListResponse> {
  const res = await client.get("/scars", { params });
  return res.data;
}

export async function getSCAR(id: string): Promise<SupplierSCAR> {
  const res = await client.get(`/scars/${id}`);
  return res.data;
}

export async function createSCAR(data: SCARCreate): Promise<SupplierSCAR> {
  const res = await client.post("/scars", data);
  return res.data;
}

export async function updateSCAR(id: string, data: SCARUpdate): Promise<SupplierSCAR> {
  const res = await client.put(`/scars/${id}`, data);
  return res.data;
}

export async function transitionSCAR(id: string, data: SCARTransitionRequest): Promise<SupplierSCAR> {
  const res = await client.post(`/scars/${id}/transition`, data);
  return res.data;
}

export async function linkCAPA(id: string, data: SCARLinkCAPARequest): Promise<SupplierSCAR> {
  const res = await client.post(`/scars/${id}/link-capa`, data);
  return res.data;
}
```

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 编译完成，exit code 0，无新增类型错误

---

### Task 8: SCAR 列表页

**Files:**
- Create: `frontend/src/pages/scar/SCARListPage.tsx`

- [ ] **Step 1: 创建 SCARListPage.tsx**

创建 `frontend/src/pages/scar/SCARListPage.tsx`：

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Tag, Tabs, Button, Select, Space, Modal, Form, Input, DatePicker, message } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { listSCARs, createSCAR } from "../../api/scar";
import { listSuppliers } from "../../api/supplier";
import type { SupplierSCAR, SCARListResponse, Supplier } from "../../types";

const STATUS_TABS = [
  { key: "all", label: "全部" },
  { key: "pending", label: "待处理" },
  { key: "responded", label: "已回复" },
  { key: "verified", label: "已验证" },
  { key: "closed", label: "已关闭" },
];

const STATUS_MAP: Record<string, string | undefined> = {
  all: undefined,
  pending: "open,in_progress",
  responded: "responded",
  verified: "verified",
  closed: "closed",
};

export const STATUS_COLORS: Record<string, string> = {
  open: "default",
  in_progress: "processing",
  responded: "warning",
  verified: "success",
  closed: "default",
};

export const STATUS_LABELS: Record<string, string> = {
  open: "待处理",
  in_progress: "处理中",
  responded: "已回复",
  verified: "已验证",
  closed: "已关闭",
};

export const SOURCE_LABELS: Record<string, string> = {
  iqc: "IQC拒收",
  complaint: "客诉",
  rma: "RMA",
  manual: "手动创建",
};

export default function SCARListPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<SCARListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("all");
  const [sourceType, setSourceType] = useState<string | undefined>();
  const [supplierId, setSupplierId] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [form] = Form.useForm();

  const loadData = async () => {
    setLoading(true);
    try {
      const result = await listSCARs({
        page,
        page_size: 20,
        status: STATUS_MAP[activeTab],
        source_type: sourceType,
        supplier_id: supplierId,
      });
      setData(result);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [activeTab, sourceType, supplierId, page]);

  const handleCreate = async (values: Record<string, unknown>) => {
    await createSCAR({
      supplier_id: values.supplier_id as string,
      source_type: "manual",
      description: values.description as string,
      requested_action: values.requested_action as string | undefined,
      due_date: values.due_date ? (values.due_date as { format: (f: string) => string }).format("YYYY-MM-DD") : undefined,
    });
    message.success("SCAR 创建成功");
    setCreateOpen(false);
    form.resetFields();
    loadData();
  };

  const columns = [
    { title: "SCAR编号", dataIndex: "scar_no", key: "scar_no" },
    { title: "供应商", dataIndex: "supplier_name", key: "supplier_name", render: (v: string) => v || "-" },
    {
      title: "来源",
      dataIndex: "source_type",
      key: "source_type",
      render: (v: string) => SOURCE_LABELS[v] || v,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (s: string) => <Tag color={STATUS_COLORS[s]}>{STATUS_LABELS[s] || s}</Tag>,
    },
    { title: "发出日期", dataIndex: "issued_date", key: "issued_date" },
    { title: "到期日", dataIndex: "due_date", key: "due_date", render: (v: string) => v || "-" },
    {
      title: "操作",
      key: "action",
      render: (_: unknown, record: SupplierSCAR) => (
        <Button type="link" onClick={() => navigate(`/scars/${record.scar_id}`)}>
          查看
        </Button>
      ),
    },
  ];

  return (
    <div>
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
              const res = await listSuppliers({ search, page_size: 20 });
              setSuppliers(res.items);
            }}
            onChange={(v) => { setSupplierId(v); setPage(1); }}
            options={suppliers.map((s) => ({ value: s.supplier_id, label: s.name }))}
          />
          <Select
            allowClear
            placeholder="来源类型"
            style={{ width: 120 }}
            onChange={(v) => { setSourceType(v); setPage(1); }}
            options={[
              { value: "iqc", label: "IQC拒收" },
              { value: "complaint", label: "客诉" },
              { value: "rma", label: "RMA" },
              { value: "manual", label: "手动创建" },
            ]}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建 SCAR
          </Button>
        </Space>
      </div>

      <Table
        dataSource={data?.items || []}
        columns={columns}
        rowKey="scar_id"
        loading={loading}
        pagination={{
          current: page,
          pageSize: 20,
          total: data?.total || 0,
          onChange: setPage,
        }}
      />

      <Modal
        title="新建 SCAR"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="supplier_id" label="供应商" rules={[{ required: true, message: "请选择供应商" }]}>
            <Select
              showSearch
              filterOption={false}
              onSearch={async (search) => {
                const res = await listSuppliers({ search, page_size: 20 });
                setSuppliers(res.items);
              }}
              options={suppliers.map((s) => ({ value: s.supplier_id, label: `${s.supplier_no} - ${s.name}` }))}
              placeholder="搜索供应商"
            />
          </Form.Item>
          <Form.Item name="description" label="问题描述" rules={[{ required: true, message: "请输入问题描述" }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="requested_action" label="要求措施">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="due_date" label="到期日">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 编译完成，exit code 0，无新增错误

---

### Task 9: SCAR 详情页

**Files:**
- Create: `frontend/src/pages/scar/SCARDetailPage.tsx`

- [ ] **Step 1: 创建 SCARDetailPage.tsx**

创建 `frontend/src/pages/scar/SCARDetailPage.tsx`：

```tsx
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, Tag, Button, Space, Descriptions, Input, Modal, message, Spin, Row, Col } from "antd";
import { getSCAR, transitionSCAR, linkCAPA } from "../../api/scar";
import { createCAPA, getCAPA } from "../../api/capa";
import { STATUS_COLORS, STATUS_LABELS, SOURCE_LABELS } from "./SCARListPage";
import type { SupplierSCAR } from "../../types";

export default function SCARDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [scar, setScar] = useState<SupplierSCAR | null>(null);
  const [loading, setLoading] = useState(true);
  const [respondModalOpen, setRespondModalOpen] = useState(false);
  const [closeModalOpen, setCloseModalOpen] = useState(false);
  const [capaModalOpen, setCapaModalOpen] = useState(false);
  const [responseText, setResponseText] = useState("");
  const [resolutionText, setResolutionText] = useState("");
  const [capaInfo, setCapaInfo] = useState<{ document_no: string; status: string } | null>(null);

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getSCAR(id);
      setScar(data);
      if (data.capa_ref_id) {
        try {
          const capa = await getCAPA(data.capa_ref_id);
          setCapaInfo({ document_no: capa.document_no, status: capa.status });
        } catch {
          setCapaInfo(null);
        }
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [id]);

  const doTransition = async (action: string, extra?: Record<string, string>) => {
    if (!id) return;
    await transitionSCAR(id, { action, ...extra } as Parameters<typeof transitionSCAR>[1]);
    message.success("状态更新成功");
    load();
  };

  const handleRespond = async () => {
    if (!responseText.trim()) { message.warning("请输入供应商回复"); return; }
    await doTransition("respond", { supplier_response: responseText });
    setRespondModalOpen(false);
    setResponseText("");
  };

  const handleClose = async () => {
    if (!resolutionText.trim()) { message.warning("请输入解决摘要"); return; }
    await doTransition("close", { resolution_summary: resolutionText });
    setCloseModalOpen(false);
    setResolutionText("");
  };

  const handleCreateCAPA = async () => {
    if (!id || !scar) return;
    const now = new Date();
    const seq = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}${String(now.getHours()).padStart(2, "0")}${String(now.getMinutes()).padStart(2, "0")}${String(now.getSeconds()).padStart(2, "0")}`;
    const capa = await createCAPA({
      title: `${scar.scar_no} — ${scar.description.slice(0, 50)}`,
      document_no: `8D-${seq}`,
      severity: "一般",
      due_date: scar.due_date || undefined,
      product_line_code: scar.product_line_code || "DC-DC-100",
    });
    await linkCAPA(id, { capa_ref_id: capa.report_id });
    message.success("CAPA 创建并关联成功");
    setCapaModalOpen(false);
    load();
  };

  if (loading || !scar) {
    return <div style={{ textAlign: "center", padding: 100 }}><Spin size="large" /></div>;
  }

  const actionButtons = () => {
    const btns: ReactNode[] = [];
    if (scar.status === "open") {
      btns.push(<Button key="start" type="primary" onClick={() => doTransition("start")}>开始处理</Button>);
    }
    if (scar.status === "in_progress") {
      btns.push(<Button key="respond" type="primary" onClick={() => setRespondModalOpen(true)}>提交回复</Button>);
    }
    if (scar.status === "responded") {
      btns.push(<Button key="verify" type="primary" onClick={() => doTransition("verify")}>验证通过</Button>);
      btns.push(<Button key="reject" danger onClick={() => doTransition("reject")}>退回</Button>);
    }
    if (scar.status === "verified") {
      btns.push(<Button key="close" type="primary" onClick={() => setCloseModalOpen(true)}>关闭</Button>);
      btns.push(<Button key="reopen" onClick={() => doTransition("reopen")}>重新打开</Button>);
    }
    return btns;
  };

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space>
              <span style={{ fontSize: 20, fontWeight: 600 }}>{scar.scar_no}</span>
              <Tag color={STATUS_COLORS[scar.status]}>{STATUS_LABELS[scar.status]}</Tag>
            </Space>
          </Col>
          <Col>
            <Space>{actionButtons()}</Space>
          </Col>
        </Row>
      </Card>

      <Card title="SCAR 信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="供应商">{scar.supplier_name || scar.supplier_id}</Descriptions.Item>
          <Descriptions.Item label="来源">{SOURCE_LABELS[scar.source_type] || scar.source_type}</Descriptions.Item>
          <Descriptions.Item label="产品线">{scar.product_line_code || "-"}</Descriptions.Item>
          <Descriptions.Item label="发出日期">{scar.issued_date || "-"}</Descriptions.Item>
          <Descriptions.Item label="到期日">{scar.due_date || "-"}</Descriptions.Item>
          <Descriptions.Item label="关闭日期">{scar.closed_date || "-"}</Descriptions.Item>
          <Descriptions.Item label="问题描述" span={2}>{scar.description}</Descriptions.Item>
          <Descriptions.Item label="要求措施" span={2}>{scar.requested_action || "-"}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="供应商回复" style={{ marginBottom: 16 }}>
        {scar.supplier_response ? (
          <div style={{ whiteSpace: "pre-wrap" }}>{scar.supplier_response}</div>
        ) : (
          <div style={{ color: "#999" }}>暂无回复</div>
        )}
      </Card>

      <Card title="CAPA 关联" style={{ marginBottom: 16 }}>
        {scar.capa_ref_id && capaInfo ? (
          <Space>
            <span>已关联 8D: <strong>{capaInfo.document_no}</strong></span>
            <Tag>{capaInfo.status}</Tag>
            <Button type="link" onClick={() => navigate(`/capa/${scar.capa_ref_id}`)}>查看</Button>
          </Space>
        ) : (
          <Button type="dashed" onClick={() => setCapaModalOpen(true)}>创建关联 8D</Button>
        )}
      </Card>

      {scar.resolution_summary && (
        <Card title="解决摘要">
          <div style={{ whiteSpace: "pre-wrap" }}>{scar.resolution_summary}</div>
        </Card>
      )}

      {/* Respond Modal */}
      <Modal title="提交供应商回复" open={respondModalOpen} onCancel={() => setRespondModalOpen(false)} onOk={handleRespond}>
        <Input.TextArea rows={4} value={responseText} onChange={(e) => setResponseText(e.target.value)} placeholder="请输入供应商回复内容" />
      </Modal>

      {/* Close Modal */}
      <Modal title="关闭 SCAR" open={closeModalOpen} onCancel={() => setCloseModalOpen(false)} onOk={handleClose}>
        <Input.TextArea rows={4} value={resolutionText} onChange={(e) => setResolutionText(e.target.value)} placeholder="请输入解决摘要" />
      </Modal>

      {/* Create CAPA Modal */}
      <Modal title="创建关联 8D" open={capaModalOpen} onCancel={() => setCapaModalOpen(false)} onOk={handleCreateCAPA} confirmLoading={false}>
        <p>将基于 SCAR 信息创建新的 8D/CAPA 记录并自动关联。</p>
        <p>SCAR: {scar.scar_no}</p>
        <p>描述: {scar.description.slice(0, 100)}...</p>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit
```

Expected: exit code 0，无新增类型错误

---

### Task 10: 前端路由 + 侧边栏 + 集成

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`
- Modify: `frontend/src/pages/iqc/IqcInspectionDetailPage.tsx`

- [ ] **Step 1: 添加路由到 App.tsx**

在 `frontend/src/App.tsx` 的 import 区域添加：

```tsx
import SCARListPage from "./pages/scar/SCARListPage";
import SCARDetailPage from "./pages/scar/SCARDetailPage";
```

在路由配置中（在 `/capa` 路由之后）添加：

```tsx
<Route path="/scars" element={<SCARListPage />} />
<Route path="/scars/:id" element={<SCARDetailPage />} />
```

- [ ] **Step 2: 添加侧边栏菜单项**

在 `frontend/src/components/layout/AppLayout.tsx` 的 `menuItems` 数组中，在 `8D/CAPA` 项之前添加：

```tsx
{ key: "/scars", icon: <WarningOutlined />, label: "SCAR管理" },
```

确保 `WarningOutlined` 已从 `@ant-design/icons` 导入（或使用已有的合适图标如 `BugOutlined`、`AlertOutlined`）。

- [ ] **Step 3: 修改 IQC 详情页 trigger-scar 后跳转**

在 `frontend/src/pages/iqc/IqcInspectionDetailPage.tsx` 中找到 `triggerScar` 调用的成功回调，添加 navigate 跳转。找到类似如下代码：

```tsx
await triggerScar(inspectionId);
message.success("SCAR 已触发");
// refresh inspection data
```

改为：

```tsx
const result = await triggerScar(inspectionId);
message.success("SCAR 已触发");
if (result.linked_scar_id) {
  navigate(`/scars/${result.linked_scar_id}`);
} else {
  // fallback: refresh current page data
  fetchInspection();
}
```

确保 `useNavigate` 已导入并在组件中初始化。

- [ ] **Step 4: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit
```

Expected: exit code 0，无新增错误

---

### Task 11: 供应商质量看板前端标签修正

**Files:**
- Modify: `frontend/src/pages/supplier/components/DashboardView.tsx`
- Modify: `frontend/src/pages/supplier/components/SupplierDetailView.tsx`

- [ ] **Step 1: 修改 DashboardView.tsx KPI 标签**

在 `DashboardView.tsx` 中找到「开放SCAR」文本（约 L163），改为「未关闭SCAR」。

- [ ] **Step 2: 修改 SupplierDetailView.tsx 标签**

在 `SupplierDetailView.tsx` 中找到 SCAR 相关标签：
- 「SCAR总数」保持不变
- 「开放SCAR」改为「未关闭SCAR」（约 L148）

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 编译完成，exit code 0，无新增错误

---

### Task 12: 端到端验证

- [ ] **Step 1: 运行 Alembic migration**

```bash
cd backend && alembic upgrade head
```

Expected: migration 022 applied successfully

- [ ] **Step 2: 启动后端并检查端点**

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/api/scars -H "Authorization: Bearer $(curl -s -X POST http://localhost:8000/api/auth/login -d '{"username":"admin","password":"Admin@2026"}' -H 'Content-Type: application/json' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')" | python3 -m json.tool
```

Expected: JSON response with `{"items": [], "total": 0, "page": 1, "page_size": 20}`

- [ ] **Step 3: 启动前端并检查页面**

```bash
cd frontend && npm run dev &
sleep 5
```

在浏览器中访问 `http://localhost:5173/scars`，确认：
- 列表页正常加载（空表格）
- 侧边栏显示「SCAR管理」菜单项
- 点击「新建 SCAR」弹出 Modal

- [ ] **Step 4: 创建测试 SCAR**

通过 API 创建一条测试 SCAR：

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -d '{"username":"engineer","password":"Engineer@2026"}' -H 'Content-Type: application/json' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
SUPPLIER_ID=$(curl -s http://localhost:8000/api/suppliers -H "Authorization: Bearer $TOKEN" | python3 -c 'import sys,json; items=json.load(sys.stdin)["items"]; print(items[0]["supplier_id"] if items else "none")')
curl -s -X POST http://localhost:8000/api/scars \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"supplier_id\": \"$SUPPLIER_ID\", \"source_type\": \"manual\", \"description\": \"测试 SCAR\"}" | python3 -m json.tool
```

Expected: JSON response with `scar_no` starting with `SCAR-` and `status: "open"`

- [ ] **Step 5: 测试状态流转**

```bash
SCAR_ID=$(curl -s http://localhost:8000/api/scars -H "Authorization: Bearer $TOKEN" | python3 -c 'import sys,json; print(json.load(sys.stdin)["items"][0]["scar_id"])')
# start
curl -s -X POST "http://localhost:8000/api/scars/$SCAR_ID/transition" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"action": "start"}' | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f"status: {d[\"status\"]}")'
```

Expected: `status: in_progress`

- [ ] **Step 6: 验证前端详情页**

在浏览器中访问 `http://localhost:5173/scars/{scar_id}`，确认：
- 状态显示「处理中」
- 「提交回复」按钮可见
- CAPA 关联区显示「创建关联 8D」按钮
