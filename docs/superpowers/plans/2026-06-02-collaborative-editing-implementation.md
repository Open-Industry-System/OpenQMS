# 多人协同编辑模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现多人协同编辑模块：轻量在线状态（顶部用户列表 + 行级编辑提示）+ 乐观锁冲突检测与差异预览 + 安全覆盖保存。

**Architecture:** 后端新增通用 `collaboration` 模块（session 表 + 心跳 API + 清理协程），前端新增 `useCollaboration` Hook 和 3 个 UI 组件，FMEA/Control Plan 编辑器集成协同组件并启用 lock_version 乐观锁。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL | React 18 + TypeScript + Axios | Alembic

---

## 文件结构

### 后端新增

```
backend/app/
  models/
    collaboration_session.py     # CollaborationSession ORM 模型
  schemas/
    collaboration.py             # HeartbeatRequest, ActiveUsersResponse
  services/
    collaboration_service.py     # 会话 CRUD + 清理逻辑
  api/
    collaboration.py             # 路由: heartbeat, active-users, leave
```

### 后端修改

```
backend/app/
  main.py                        # 注册 collaboration 路由 + lifespan 清理协程
  schemas/fmea.py                # FMEAUpdate 添加 lock_version + confirmed_latest_lock_version
  api/fmea.py                    # update_fmea 添加乐观锁检查 + 冲突响应
  services/fmea_service.py       # update_fmea 添加 lock_version 校验
  schemas/control_plan.py        # ControlPlanUpdate 添加 lock_version + confirmed_latest_lock_version
  api/control_plan.py            # update_control_plan 添加乐观锁检查 + 冲突响应
  services/control_plan_service.py  # update_control_plan 添加 lock_version 校验
```

### 前端新增

```
frontend/src/
  types/collaboration.ts         # EditingArea, ActiveUser, CollaborationState 类型
  api/collaboration.ts           # heartbeat, getActiveUsers, leaveSession
  utils/graphDiff.ts             # 三方 diff 工具（base vs local vs server）
  hooks/useCollaboration.ts      # 心跳 + 轮询 + 会话管理
  components/collaboration/
    CollaborationBar.tsx         # 顶部在线用户列表
    ActiveUserIndicator.tsx      # 行/字段级编辑提示
    ConflictResolutionModal.tsx  # 冲突处理弹窗
    index.ts                     # 统一导出
```

### 前端修改

```
frontend/src/
  api/fmea.ts                    # updateFMEA 添加 confirmed_latest_lock_version
  api/controlPlan.ts             # updateControlPlan 添加 confirmed_latest_lock_version
  pages/planning/fmea/FMEAEditorPage.tsx        # 集成协同组件 + 冲突处理
  pages/planning/control-plan/ControlPlanEditorPage.tsx  # 集成协同组件 + 冲突处理
```

---

## 任务清单

### Task 1: 数据库迁移 — 创建 collaboration_sessions 表

**Files:**
- Create: `backend/alembic/versions/20260602_add_collaboration_sessions.py`

- [ ] **Step 1: 编写迁移脚本**

```python
"""add collaboration_sessions table

Revision ID: 20260602_add_collaboration_sessions
Revises: 20260602_add_vector_search
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260602_add_collaboration_sessions"
down_revision = "20260602_add_vector_search"


def upgrade():
    op.create_table(
        'collaboration_sessions',
        sa.Column('session_id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('document_type', sa.String(30), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('user_name', sa.String(100), nullable=True),
        sa.Column('action', sa.String(20), server_default='viewing'),
        sa.Column('editing_area', postgresql.JSONB(), nullable=True),
        sa.Column('last_activity', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('session_id'),
        sa.UniqueConstraint('document_type', 'document_id', 'user_id', name='uq_collab_session'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    )
    op.create_index('idx_collab_doc', 'collaboration_sessions', ['document_type', 'document_id'])
    op.create_index('idx_collab_activity', 'collaboration_sessions', ['last_activity'])


def downgrade():
    op.drop_index('idx_collab_activity', table_name='collaboration_sessions')
    op.drop_index('idx_collab_doc', table_name='collaboration_sessions')
    op.drop_table('collaboration_sessions')
```

- [ ] **Step 2: 运行迁移**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
alembic upgrade head
```

Expected: `20260602_add_collaboration_sessions` migration applied successfully.

- [ ] **Step 3: 验证表结构**

```bash
psql -d openqms -c "\d collaboration_sessions"
```

Expected: Table exists with all columns, indexes, and constraints.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/20260602_add_collaboration_sessions.py
git commit -m "feat(collaboration): add collaboration_sessions migration"
```

---

### Task 2: 后端模型 — CollaborationSession

**Files:**
- Create: `backend/app/models/collaboration_session.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 编写模型文件**

```python
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, func, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CollaborationSession(Base):
    __tablename__ = "collaboration_sessions"

    __table_args__ = (
        UniqueConstraint("document_type", "document_id", "user_id", name="uq_collab_session"),
        Index("idx_collab_doc", "document_type", "document_id"),
        Index("idx_collab_activity", "last_activity"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    user_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[str] = mapped_column(String(20), default="viewing")
    editing_area: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: 导出模型**

在 `backend/app/models/__init__.py` 中添加：

```python
from app.models.collaboration_session import CollaborationSession
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/collaboration_session.py backend/app/models/__init__.py
git commit -m "feat(collaboration): add CollaborationSession model"
```

---

### Task 3: 后端 Schema — 协同相关请求/响应

**Files:**
- Create: `backend/app/schemas/collaboration.py`

- [ ] **Step 1: 编写 schema 文件**

```python
from pydantic import BaseModel
from typing import Literal


class EditingArea(BaseModel):
    row_key: str | None = None
    field: str | None = None
    node_id: str | None = None
    section: str | None = None
    column: str | None = None


class HeartbeatRequest(BaseModel):
    document_type: str
    document_id: str
    action: Literal["viewing", "editing", "idle"] = "viewing"
    editing_area: EditingArea | None = None


class ActiveUser(BaseModel):
    user_id: str
    user_name: str
    action: Literal["viewing", "editing", "idle"]
    editing_area: EditingArea | None = None


class ActiveUsersResponse(BaseModel):
    users: list[ActiveUser]
    total: int
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/collaboration.py
git commit -m "feat(collaboration): add collaboration schemas"
```

---

### Task 4: 后端服务 — CollaborationService

**Files:**
- Create: `backend/app/services/collaboration_service.py`

- [ ] **Step 1: 编写服务文件**

```python
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration_session import CollaborationSession

SESSION_TTL_SECONDS = 60


async def upsert_session(
    db: AsyncSession,
    document_type: str,
    document_id: str,
    user_id: uuid.UUID,
    user_name: str,
    action: str,
    editing_area: dict | None,
) -> None:
    """Upsert collaboration session on heartbeat."""
    stmt = (
        insert(CollaborationSession)
        .values(
            document_type=document_type,
            document_id=uuid.UUID(document_id),
            user_id=user_id,
            user_name=user_name,
            action=action,
            editing_area=editing_area,
            last_activity=datetime.now(timezone.utc),
        )
        .on_conflict_do_update(
            index_elements=["document_type", "document_id", "user_id"],
            set_={
                "user_name": user_name,
                "action": action,
                "editing_area": editing_area,
                "last_activity": datetime.now(timezone.utc),
            },
        )
    )
    await db.execute(stmt)
    await db.commit()


async def delete_session(
    db: AsyncSession,
    document_type: str,
    document_id: str,
    user_id: uuid.UUID,
) -> None:
    """Delete session on page unload."""
    stmt = delete(CollaborationSession).where(
        CollaborationSession.document_type == document_type,
        CollaborationSession.document_id == uuid.UUID(document_id),
        CollaborationSession.user_id == user_id,
    )
    await db.execute(stmt)
    await db.commit()


async def get_active_users(
    db: AsyncSession,
    document_type: str,
    document_id: str,
    exclude_user_id: uuid.UUID | None = None,
) -> list[CollaborationSession]:
    """Get active users for a document, filtering expired sessions."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=SESSION_TTL_SECONDS)
    stmt = (
        select(CollaborationSession)
        .where(
            CollaborationSession.document_type == document_type,
            CollaborationSession.document_id == uuid.UUID(document_id),
            CollaborationSession.last_activity >= cutoff,
        )
        .order_by(CollaborationSession.last_activity.desc())
    )
    if exclude_user_id:
        stmt = stmt.where(CollaborationSession.user_id != exclude_user_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_expired_sessions(db: AsyncSession) -> int:
    """Delete expired sessions. Returns count deleted."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=SESSION_TTL_SECONDS)
    stmt = delete(CollaborationSession).where(
        CollaborationSession.last_activity < cutoff
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/collaboration_service.py
git commit -m "feat(collaboration): add CollaborationService with CRUD + cleanup"
```

---

### Task 5: 后端 API — Collaboration 路由

**Files:**
- Create: `backend/app/api/collaboration.py`

- [ ] **Step 1: 编写路由文件**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import get_current_user
from app.models.user import User
from app.schemas.collaboration import HeartbeatRequest, ActiveUsersResponse, ActiveUser
from app.services import collaboration_service

router = APIRouter(prefix="/api/collaboration", tags=["collaboration"])


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def heartbeat(
    req: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await collaboration_service.upsert_session(
        db,
        document_type=req.document_type,
        document_id=req.document_id,
        user_id=user.user_id,
        user_name=user.display_name or user.username,
        action=req.action,
        editing_area=req.editing_area.model_dump() if req.editing_area else None,
    )


@router.delete("/leave/{document_type}/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def leave(
    document_type: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await collaboration_service.delete_session(
        db,
        document_type=document_type,
        document_id=document_id,
        user_id=user.user_id,
    )


@router.get("/{document_type}/{document_id}/active-users", response_model=ActiveUsersResponse)
async def active_users(
    document_type: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sessions = await collaboration_service.get_active_users(
        db,
        document_type=document_type,
        document_id=document_id,
        exclude_user_id=user.user_id,
    )
    return ActiveUsersResponse(
        users=[
            ActiveUser(
                user_id=str(s.user_id),
                user_name=s.user_name or "未知用户",
                action=s.action,  # type: ignore[arg-type]
                editing_area=s.editing_area,
            )
            for s in sessions
        ],
        total=len(sessions),
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/collaboration.py
git commit -m "feat(collaboration): add collaboration API routes"
```

---

### Task 6: 后端 — 注册路由 + Lifespan 清理协程

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 导入 collaboration 路由**

在 `backend/app/main.py` 的导入区添加：

```python
from app.api.collaboration import router as collaboration_router
```

在 `app.include_router(...)` 列表末尾添加：

```python
app.include_router(collaboration_router)
```

- [ ] **Step 2: 在 lifespan 中添加清理协程**

在 `lifespan` 函数的 `yield` 之前添加：

```python
import asyncio
from app.services.collaboration_service import delete_expired_sessions

async def _cleanup_loop():
    while True:
        await asyncio.sleep(60)
        try:
            async with async_session() as db:
                deleted = await delete_expired_sessions(db)
                if deleted > 0:
                    print(f"[collaboration] cleaned up {deleted} expired sessions")
        except Exception as e:
            print(f"[collaboration] cleanup error: {e}")

# 在 lifespan 中 yield 之前启动
cleanup_task = asyncio.create_task(_cleanup_loop())
```

在 `yield` 之后添加取消逻辑：

```python
yield
cleanup_task.cancel()
try:
    await cleanup_task
except asyncio.CancelledError:
    pass
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(collaboration): register routes and add session cleanup coroutine"
```

---

### Task 7: 后端 — FMEA 乐观锁检查（当前缺失）

**Files:**
- Modify: `backend/app/schemas/fmea.py`
- Modify: `backend/app/api/fmea.py`
- Modify: `backend/app/services/fmea_service.py`

- [ ] **Step 1: FMEAUpdate schema添加 lock_version 字段**

在 `backend/app/schemas/fmea.py` 的 `FMEAUpdate` 类中添加：

```python
class FMEAUpdate(BaseModel):
    title: str | None = None
    graph_data: GraphDataSchema | None = None
    product_line_code: str | None = None
    lock_version: int | None = None                    # 乐观锁版本号
    confirmed_latest_lock_version: int | None = None   # 冲突弹窗中确认的最新版本
```

- [ ] **Step 2: FMEA service 添加乐观锁校验**

修改 `backend/app/services/fmea_service.py` 的 `update_fmea` 函数：

```python
async def update_fmea(
    db: AsyncSession,
    fmea: FMEADocument,
    title: str | None,
    graph_data: dict | None,
    user_id: uuid.UUID,
    product_line_code: str | None = None,
    lock_version: int | None = None,
    confirmed_latest_lock_version: int | None = None,
) -> FMEADocument:
    # 乐观锁校验（互斥分支）
    if confirmed_latest_lock_version is not None:
        # 强制保存：只校验确认的版本号，跳过常规 lock_version
        if fmea.lock_version != confirmed_latest_lock_version:
            raise ValueError("lock_version_changed_again")
    elif lock_version is not None:
        # 常规保存：检查 lock_version 是否匹配
        if fmea.lock_version != lock_version:
            raise ValueError("lock_version_mismatch")

    changed_fields = {}
    if title is not None:
        changed_fields["title"] = title
        fmea.title = title
    if graph_data is not None:
        changed_fields["graph_data"] = graph_data
        fmea.graph_data = graph_data
    if product_line_code is not None:
        await validate_product_line(db, product_line_code)
        changed_fields["product_line_code"] = product_line_code
        fmea.product_line_code = product_line_code
    fmea.updated_by = user_id
    fmea.lock_version += 1  # 递增乐观锁版本

    if changed_fields:
        audit_log = AuditLog(
            table_name="fmea_documents",
            record_id=fmea.fmea_id,
            action="UPDATE",
            changed_fields=changed_fields,
            operated_by=user_id,
        )
        db.add(audit_log)

        # 强制覆盖时记录审计日志
        if confirmed_latest_lock_version is not None:
            force_audit = AuditLog(
                table_name="fmea_documents",
                record_id=fmea.fmea_id,
                action="FORCE_SAVE_OVERRIDE",
                changed_fields={"reason": "User confirmed overwrite after conflict detection"},
                operated_by=user_id,
            )
            db.add(force_audit)

        # Outbox: enqueue Neo4j projection sync
        db.add(GraphSyncOutbox(
            aggregate_type="fmea",
            aggregate_id=fmea.fmea_id,
            event_type="fmea.updated",
            payload={"version": fmea.version, "product_line_code": fmea.product_line_code},
        ))

        # Invalidate recommendation cache when graph_data or product_line changes
        if graph_data is not None or product_line_code is not None:
            from app.services.recommendation_service import RecommendationService
            rec_service = RecommendationService(db=db, llm_provider=None)
            await rec_service.invalidate_cache_for_fmea(fmea.fmea_id)

    await db.commit()
    await db.refresh(fmea)
    await enqueue_embedding(db, "fmea_node", fmea.fmea_id, fmea.product_line_code)
    return fmea
```

- [ ] **Step 3: FMEA API 添加冲突响应**

修改 `backend/app/api/fmea.py` 的 `update_fmea` 函数：

```python
@router.put("/{fmea_id}", response_model=FMEAResponse)
async def update_fmea(
    fmea_id: uuid.UUID,
    req: FMEAUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.EDIT)),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)
    if req.product_line_code is not None and req.product_line_code != fmea.product_line_code:
        await enforce_product_line_access(user, req.product_line_code, db)
    graph_dict = req.graph_data.model_dump() if req.graph_data else None
    try:
        fmea = await fmea_service.update_fmea(
            db, fmea, req.title, graph_dict, user.user_id, req.product_line_code,
            lock_version=req.lock_version,
            confirmed_latest_lock_version=req.confirmed_latest_lock_version,
        )
    except ValueError as e:
        error_msg = str(e)
        if error_msg == "lock_version_mismatch":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "Document has been modified by another user.",
                    "conflict": {
                        "saved_by": None,
                        "saved_at": None,
                        "latest_lock_version": fmea.lock_version,
                    },
                },
            )
        if error_msg == "lock_version_changed_again":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "Document was modified again while you were reviewing. Please refresh.",
                    "conflict": {
                        "saved_by": None,
                        "saved_at": None,
                        "latest_lock_version": fmea.lock_version,
                    },
                },
            )
        raise HTTPException(status_code=400, detail=error_msg)
    return FMEAResponse.model_validate(fmea)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/fmea.py backend/app/api/fmea.py backend/app/services/fmea_service.py
git commit -m "feat(collaboration): add optimistic locking to FMEA update"
```

---

### Task 8: 后端 — Control Plan 乐观锁检查

**Files:**
- Modify: `backend/app/schemas/control_plan.py`
- Modify: `backend/app/api/control_plan.py`
- Modify: `backend/app/services/control_plan_service.py`

- [ ] **Step 1: ControlPlanUpdate schema 添加 lock_version 字段**

在 `backend/app/schemas/control_plan.py` 的 `ControlPlanUpdate` 类（或等效更新类）中添加：

```python
class ControlPlanUpdate(BaseModel):
    # ... existing fields ...
    lock_version: int | None = None
    confirmed_latest_lock_version: int | None = None
```

- [ ] **Step 2: Control Plan service 添加乐观锁校验**

在 `control_plan_service.py` 的 `update_control_plan` 函数中添加：

```python
async def update_control_plan(
    db: AsyncSession,
    cp: ControlPlan,
    data: ControlPlanUpdate,
    user_id: uuid.UUID,
) -> ControlPlan:
    lock_version = data.lock_version
    confirmed_latest_lock_version = data.confirmed_latest_lock_version

    # 乐观锁校验（互斥分支）
    if confirmed_latest_lock_version is not None:
        if cp.lock_version != confirmed_latest_lock_version:
            raise ValueError("lock_version_changed_again")
    elif lock_version is not None:
        if cp.lock_version != lock_version:
            raise ValueError("lock_version_mismatch")

    # ... existing update logic ...
    cp.lock_version += 1

    # ... existing audit log ...

    # 强制覆盖时记录审计日志
    if confirmed_latest_lock_version is not None:
        force_audit = AuditLog(
            table_name="control_plans",
            record_id=cp.cp_id,
            action="FORCE_SAVE_OVERRIDE",
            changed_fields={"reason": "User confirmed overwrite after conflict detection"},
            operated_by=user_id,
        )
        db.add(force_audit)

    await db.commit()
    await db.refresh(cp)
    return cp
```

- [ ] **Step 3: Control Plan API 添加冲突响应**

在 `api/control_plan.py` 的 `update_control_plan` 函数中添加：

```python
try:
    cp = await control_plan_service.update_control_plan(db, cp, req, user.user_id)
except ValueError as e:
    error_msg = str(e)
    if error_msg == "lock_version_mismatch":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": "Document has been modified by another user.",
                "conflict": {
                    "saved_by": None,
                    "saved_at": None,
                    "latest_lock_version": cp.lock_version,
                },
            },
        )
    if error_msg == "lock_version_changed_again":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": "Document was modified again while you were reviewing. Please refresh.",
                "conflict": {
                    "saved_by": None,
                    "saved_at": None,
                    "latest_lock_version": cp.lock_version,
                },
            },
        )
    raise HTTPException(status_code=400, detail=error_msg)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/control_plan.py backend/app/api/control_plan.py backend/app/services/control_plan_service.py
git commit -m "feat(collaboration): add optimistic locking to Control Plan update"
```

---

### Task 9: 前端类型 — 协同编辑类型定义

**Files:**
- Create: `frontend/src/types/collaboration.ts`

- [ ] **Step 1: 编写类型文件**

```typescript
export type CollaborationAction = "viewing" | "editing" | "idle";

export interface EditingArea {
  row_key?: string;
  field?: string;
  node_id?: string;
  section?: string;
  column?: string;
}

export interface ActiveUser {
  user_id: string;
  user_name: string;
  action: CollaborationAction;
  editing_area: EditingArea | null;
}

export interface CollaborationState {
  activeUsers: ActiveUser[];
  currentUserEditing: boolean;
  isSyncing: boolean;
  startEditing: (area: EditingArea) => void;
  stopEditing: () => void;
}

export interface ConflictInfo {
  saved_by: string | null;
  saved_at: string | null;
  latest_lock_version: number;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/collaboration.ts
git commit -m "feat(collaboration): add collaboration TypeScript types"
```

---

### Task 10: 前端 API — 协同相关请求

**Files:**
- Create: `frontend/src/api/collaboration.ts`

- [ ] **Step 1: 编写 API 文件**

```typescript
import client from "./client";
import type { ActiveUser, EditingArea } from "../types/collaboration";

export async function heartbeat(
  documentType: string,
  documentId: string,
  action: string,
  editingArea?: EditingArea
): Promise<void> {
  await client.post("/collaboration/heartbeat", {
    document_type: documentType,
    document_id: documentId,
    action,
    editing_area: editingArea || null,
  });
}

export async function leaveSession(
  documentType: string,
  documentId: string
): Promise<void> {
  await client.delete(`/collaboration/leave/${documentType}/${documentId}`);
}

export interface ActiveUsersResponse {
  users: ActiveUser[];
  total: number;
}

export async function getActiveUsers(
  documentType: string,
  documentId: string
): Promise<ActiveUsersResponse> {
  const resp = await client.get(`/collaboration/${documentType}/${documentId}/active-users`);
  return resp.data;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/collaboration.ts
git commit -m "feat(collaboration): add collaboration API client"
```

---

### Task 11: 前端工具 — Graph 三方 Diff

**Files:**
- Create: `frontend/src/utils/graphDiff.ts`

- [ ] **Step 1: 编写 diff 工具**

```typescript
import type { GraphNode, GraphEdge } from "../types";

export interface NodeChange {
  type: "added" | "removed" | "modified";
  node_id: string;
  field?: string;
  oldValue?: unknown;
  newValue?: unknown;
  nodeType?: string;
  name?: string;
}

export interface EdgeChange {
  type: "added" | "removed";
  source: string;
  target: string;
  edge_type: string;
}

export interface GraphDiff {
  nodeChanges: NodeChange[];
  edgeChanges: EdgeChange[];
  conflictingFields: NodeChange[];  // 双方都修改的字段
}

/**
 * Three-way diff: compare base vs latest (their changes) and base vs local (my changes).
 * Returns their changes + conflicting fields.
 */
export function diffGraphs(
  baseNodes: GraphNode[],
  baseEdges: GraphEdge[],
  latestNodes: GraphNode[],
  latestEdges: GraphEdge[],
  localNodes: GraphNode[],
  localEdges: GraphEdge[]
): GraphDiff {
  const nodeChanges: NodeChange[] = [];
  const edgeChanges: EdgeChange[] = [];
  const conflictingFields: NodeChange[] = [];

  const baseNodeMap = new Map(baseNodes.map((n) => [n.id, n]));
  const latestNodeMap = new Map(latestNodes.map((n) => [n.id, n]));
  const localNodeMap = new Map(localNodes.map((n) => [n.id, n]));

  // Check for added/removed/modified nodes (their changes: base vs latest)
  for (const [id, latestNode] of latestNodeMap) {
    const baseNode = baseNodeMap.get(id);
    if (!baseNode) {
      nodeChanges.push({
        type: "added",
        node_id: id,
        nodeType: latestNode.type,
        name: latestNode.name,
      });
    } else {
      // Check modified fields
      const diffFields = ["name", "severity", "occurrence", "detection", "specification", "requirement"];
      for (const field of diffFields) {
        const baseVal = (baseNode as Record<string, unknown>)[field] ?? null;
        const latestVal = (latestNode as Record<string, unknown>)[field] ?? null;
        const localVal = (localNodeMap.get(id) as Record<string, unknown> | undefined)?.[field] ?? null;

        if (baseVal !== latestVal) {
          nodeChanges.push({
            type: "modified",
            node_id: id,
            field,
            oldValue: baseVal,
            newValue: latestVal,
            nodeType: latestNode.type,
            name: latestNode.name,
          });

          // Check if local also modified this field (conflict)
          if (localVal !== null && baseVal !== localVal) {
            conflictingFields.push({
              type: "modified",
              node_id: id,
              field,
              oldValue: baseVal,
              newValue: latestVal,
              nodeType: latestNode.type,
              name: latestNode.name,
            });
          }
        }
      }
    }
  }

  // Check for removed nodes (their changes)
  for (const [id, baseNode] of baseNodeMap) {
    if (!latestNodeMap.has(id)) {
      nodeChanges.push({
        type: "removed",
        node_id: id,
        nodeType: baseNode.type,
        name: baseNode.name,
      });
    }
  }

  // Edge changes
  const edgeKey = (e: GraphEdge) => `${e.source}:${e.target}:${e.type}`;
  const baseEdgeSet = new Set(baseEdges.map(edgeKey));
  const latestEdgeSet = new Set(latestEdges.map(edgeKey));

  for (const e of latestEdges) {
    const key = edgeKey(e);
    if (!baseEdgeSet.has(key)) {
      edgeChanges.push({ type: "added", source: e.source, target: e.target, edge_type: e.type });
    }
  }
  for (const e of baseEdges) {
    const key = edgeKey(e);
    if (!latestEdgeSet.has(key)) {
      edgeChanges.push({ type: "removed", source: e.source, target: e.target, edge_type: e.type });
    }
  }

  return { nodeChanges, edgeChanges, conflictingFields };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/utils/graphDiff.ts
git commit -m "feat(collaboration): add graph three-way diff utility"
```

---

### Task 12: 前端 Hook — useCollaboration

**Files:**
- Create: `frontend/src/hooks/useCollaboration.ts`

- [ ] **Step 1: 编写 Hook**

```typescript
import { useCallback, useEffect, useRef, useState } from "react";
import { heartbeat, getActiveUsers, leaveSession } from "../api/collaboration";
import type { ActiveUser, EditingArea, CollaborationState } from "../types/collaboration";

const HEARTBEAT_INTERVAL = 15000;      // 15s normal
const EDITING_INTERVAL = 8000;         // 8s when editing
const BLURRED_INTERVAL = 30000;        // 30s when tab not focused

export function useCollaboration(
  documentType: string,
  documentId: string
): CollaborationState {
  const [activeUsers, setActiveUsers] = useState<ActiveUser[]>([]);
  const [isSyncing, setIsSyncing] = useState(true);
  const [currentUserEditing, setCurrentUserEditing] = useState(false);
  const editingAreaRef = useRef<EditingArea | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastHeartbeatRef = useRef<number>(0);

  const sendHeartbeat = useCallback(async () => {
    if (!documentId) return;
    try {
      await heartbeat(
        documentType,
        documentId,
        editingAreaRef.current ? "editing" : "viewing",
        editingAreaRef.current || undefined
      );
      lastHeartbeatRef.current = Date.now();
      setIsSyncing(true);
    } catch {
      setIsSyncing(false);
    }
  }, [documentType, documentId]);

  const fetchActiveUsers = useCallback(async () => {
    if (!documentId) return;
    try {
      const resp = await getActiveUsers(documentType, documentId);
      setActiveUsers(resp.users);
      setIsSyncing(true);
    } catch {
      setIsSyncing(false);
    }
  }, [documentType, documentId]);

  const schedule = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    const interval = document.hidden
      ? BLURRED_INTERVAL
      : editingAreaRef.current
      ? EDITING_INTERVAL
      : HEARTBEAT_INTERVAL;
    intervalRef.current = setInterval(() => {
      sendHeartbeat();
      fetchActiveUsers();
    }, interval);
  }, [sendHeartbeat, fetchActiveUsers]);

  const startEditing = useCallback((area: EditingArea) => {
    editingAreaRef.current = area;
    setCurrentUserEditing(true);
    sendHeartbeat();
    schedule();  // 立即切换到 editing 间隔（8s）
  }, [sendHeartbeat, schedule]);

  const stopEditing = useCallback(() => {
    editingAreaRef.current = null;
    setCurrentUserEditing(false);
    sendHeartbeat();
    schedule();  // 切回 viewing 间隔（15s）
  }, [sendHeartbeat, schedule]);

  // Setup intervals
  useEffect(() => {
    if (!documentId) return;

    schedule();

    // Immediate first fetch
    fetchActiveUsers();

    const handleVisibility = () => {
      schedule();
      if (!document.hidden) {
        fetchActiveUsers();
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [documentId, schedule, fetchActiveUsers]);

  // Page unload: send fetch with keepalive + auth header to clean up session
  useEffect(() => {
    if (!documentId) return;

    const token = localStorage.getItem("access_token");

    const handleUnload = () => {
      const url = `/api/collaboration/leave/${documentType}/${documentId}`;
      fetch(url, {
        method: "DELETE",
        keepalive: true,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      }).catch(() => {});
    };

    window.addEventListener("beforeunload", handleUnload);
    return () => {
      window.removeEventListener("beforeunload", handleUnload);
      // Normal unmount: use axios client (has auth interceptor)
      leaveSession(documentType, documentId).catch(() => {});
    };
  }, [documentType, documentId]);

  return {
    activeUsers,
    currentUserEditing,
    isSyncing,
    startEditing,
    stopEditing,
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useCollaboration.ts
git commit -m "feat(collaboration): add useCollaboration hook"
```

---

### Task 13: 前端组件 — CollaborationBar

**Files:**
- Create: `frontend/src/components/collaboration/CollaborationBar.tsx`

- [ ] **Step 1: 编写组件**

```tsx
import { Avatar, Badge, Tooltip } from "antd";
import type { ActiveUser } from "../../types/collaboration";

interface CollaborationBarProps {
  activeUsers: ActiveUser[];
  isSyncing: boolean;
}

export default function CollaborationBar({ activeUsers, isSyncing }: CollaborationBarProps) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", borderBottom: "1px solid #f0f0f0" }}>
      <Avatar.Group max={{ count: 5 }}>
        {activeUsers.map((u) => (
          <Tooltip
            key={u.user_id}
            title={`${u.user_name} (${u.action === "editing" ? "编辑中" : "查看中"})`}
          >
            <Avatar
              style={{
                backgroundColor: u.action === "editing" ? "#52c41a" : "#bfbfbf",
                border: u.action === "editing" ? "2px solid #237804" : undefined,
              }}
            >
              {u.user_name?.[0] || "?"}
            </Avatar>
          </Tooltip>
        ))}
      </Avatar.Group>
      <span style={{ fontSize: 13, color: "#595959" }}>
        {activeUsers.length === 0
          ? "仅你一人"
          : `${activeUsers.length} 人在线`}
      </span>
      {!isSyncing && (
        <Badge
          status="warning"
          text={<span style={{ fontSize: 12 }}>协同状态同步失败</span>}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/collaboration/CollaborationBar.tsx
git commit -m "feat(collaboration): add CollaborationBar component"
```

---

### Task 14: 前端组件 — ActiveUserIndicator

**Files:**
- Create: `frontend/src/components/collaboration/ActiveUserIndicator.tsx`

- [ ] **Step 1: 编写组件**

```tsx
import { Badge } from "antd";
import type { ActiveUser, EditingArea } from "../../types/collaboration";

interface ActiveUserIndicatorProps {
  activeUsers: ActiveUser[];
  rowKey?: string;
  field?: string;
  nodeId?: string;
}

export default function ActiveUserIndicator({
  activeUsers,
  rowKey,
  field,
  nodeId,
}: ActiveUserIndicatorProps) {
  const editors = activeUsers.filter((u) => {
    if (u.action !== "editing" || !u.editing_area) return false;
    const area = u.editing_area as EditingArea;
    // Support both row_key (FMEA) and rowId mapped to row_key (Control Plan)
    const areaRowKey = area.row_key || (area as Record<string, string>).rowId;
    if (rowKey && areaRowKey === rowKey) {
      return !field || area.field === field;
    }
    if (nodeId && area.node_id === nodeId) {
      return !field || area.field === field;
    }
    return false;
  });

  if (editors.length === 0) return null;

  return (
    <span style={{ fontSize: 11, color: "#52c41a", marginLeft: 4, whiteSpace: "nowrap" }}>
      <Badge color="green" style={{ marginRight: 4 }} />
      {editors.map((e) => e.user_name).join("、")} 正在编辑
    </span>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/collaboration/ActiveUserIndicator.tsx
git commit -m "feat(collaboration): add ActiveUserIndicator component"
```

---

### Task 15: 前端组件 — ConflictResolutionModal

**Files:**
- Create: `frontend/src/components/collaboration/ConflictResolutionModal.tsx`

- [ ] **Step 1: 编写组件**

```tsx
import { Modal, Alert, Button, List, Tag } from "antd";
import type { ConflictInfo } from "../../types/collaboration";
import type { GraphDiff } from "../../utils/graphDiff";

interface ConflictResolutionModalProps {
  visible: boolean;
  conflictInfo: ConflictInfo | null;
  diff: GraphDiff | null;
  onRefresh: () => void;
  onForceSave: () => void;
}

export default function ConflictResolutionModal({
  visible,
  conflictInfo,
  diff,
  onRefresh,
  onForceSave,
}: ConflictResolutionModalProps) {
  return (
    <Modal
      title="保存冲突"
      open={visible}
      closable={false}
      footer={null}
      width={600}
    >
      <Alert
        type="warning"
        message="文档已被他人修改"
        description={
          conflictInfo?.saved_by
            ? `${conflictInfo.saved_by} 保存了更改`
            : "文档在您编辑期间已被其他用户保存"
        }
        style={{ marginBottom: 16 }}
      />

      {diff && (
        <div style={{ marginBottom: 16 }}>
          <p style={{ fontWeight: 600, marginBottom: 8 }}>
            对方修改了 {diff.nodeChanges.length} 处内容
            {diff.conflictingFields.length > 0 && (
              <Tag color="red" style={{ marginLeft: 8 }}>
                {diff.conflictingFields.length} 处冲突
              </Tag>
            )}
          </p>
          <List
            size="small"
            dataSource={diff.nodeChanges.slice(0, 10)}
            renderItem={(change) => (
              <List.Item>
                {change.type === "added" && (
                  <span>
                    新增 <Tag>{change.nodeType}</Tag> {change.name}
                  </span>
                )}
                {change.type === "removed" && (
                  <span style={{ color: "#cf1322" }}>
                    删除 <Tag>{change.nodeType}</Tag> {change.name}
                  </span>
                )}
                {change.type === "modified" && (
                  <span>
                    修改 <Tag>{change.nodeType}</Tag> {change.name} 的{" "}
                    <Tag color="blue">{change.field}</Tag>
                    {diff.conflictingFields.some(
                      (c) => c.node_id === change.node_id && c.field === change.field
                    ) && (
                      <Tag color="red" style={{ marginLeft: 4 }}>
                        冲突
                      </Tag>
                    )}
                  </span>
                )}
              </List.Item>
            )}
          />
          {diff.nodeChanges.length > 10 && (
            <p style={{ color: "#8c8c8c", fontSize: 12 }}>
              还有 {diff.nodeChanges.length - 10} 处修改...
            </p>
          )}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <Button onClick={onRefresh}>放弃我的更改，刷新页面</Button>
        <Button type="primary" danger onClick={onForceSave}>
          强制保存（覆盖对方更改）
        </Button>
      </div>
    </Modal>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/collaboration/ConflictResolutionModal.tsx
git commit -m "feat(collaboration): add ConflictResolutionModal component"
```

---

### Task 16: 前端组件 — 统一导出

**Files:**
- Create: `frontend/src/components/collaboration/index.ts`

- [ ] **Step 1: 编写导出文件**

```typescript
export { default as CollaborationBar } from "./CollaborationBar";
export { default as ActiveUserIndicator } from "./ActiveUserIndicator";
export { default as ConflictResolutionModal } from "./ConflictResolutionModal";
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/collaboration/index.ts
git commit -m "feat(collaboration): add collaboration components index"
```

---

### Task 17: 前端 — FMEA API 更新参数

**Files:**
- Modify: `frontend/src/api/fmea.ts`

- [ ] **Step 1: 修改 updateFMEA 函数签名**

```typescript
export async function updateFMEA(
  id: string,
  data: {
    title?: string;
    graph_data?: GraphData;
    lock_version?: number;
    confirmed_latest_lock_version?: number;
  }
): Promise<FMEADocument> {
  const resp = await client.put(`/fmea/${id}`, data);
  return resp.data;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/fmea.ts
git commit -m "feat(collaboration): add lock_version params to FMEA update API"
```

---

### Task 18: 前端 — FMEA 编辑器集成协同功能

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`

- [ ] **Step 1: 导入协同组件和 Hook**

在文件顶部添加导入：

```typescript
import { useCollaboration } from "../../../hooks/useCollaboration";
import { CollaborationBar, ActiveUserIndicator, ConflictResolutionModal } from "../../../components/collaboration";
import { diffGraphs } from "../../../utils/graphDiff";
import type { ConflictInfo } from "../../../types/collaboration";
import type { GraphDiff } from "../../../utils/graphDiff";
```

- [ ] **Step 2: 在组件内使用 Hook 和状态**

在 `FMEAEditorPage` 函数体内添加：

```typescript
const { activeUsers, startEditing, stopEditing, isSyncing } = useCollaboration("fmea", fmeaId);

// Base snapshot for three-way diff
const baseGraphRef = useRef<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);

// Conflict resolution state
const [conflictVisible, setConflictVisible] = useState(false);
const [conflictInfo, setConflictInfo] = useState<ConflictInfo | null>(null);
const [conflictDiff, setConflictDiff] = useState<GraphDiff | null>(null);
```

在 `useEffect` 加载 FMEA 数据时保存 base snapshot：

```typescript
useEffect(() => {
  if (!id) return;
  getFMEA(id)
    .then((doc) => {
      setFmea(doc);
      const loadedNodes = doc.graph_data?.nodes || [];
      const loadedEdges = doc.graph_data?.edges || [];
      setNodes(loadedNodes);
      setEdges(loadedEdges);
      // Save base snapshot for conflict diff
      baseGraphRef.current = {
        nodes: JSON.parse(JSON.stringify(loadedNodes)),
        edges: JSON.parse(JSON.stringify(loadedEdges)),
      };
      // ... rest of existing logic
    })
    .finally(() => setLoading(false));
}, [id]);
```

- [ ] **Step 3: 修改 save 函数处理冲突**

修改 `save` 函数：

```typescript
const save = useCallback(async () => {
  if (!id || !fmea) return;
  setSaving(true);
  try {
    const updated = await updateFMEA(id, {
      title: fmea.title,
      graph_data: { nodes, edges },
      lock_version: fmea.lock_version,
    });
    setFmea(updated);
    // Update base snapshot after successful save
    baseGraphRef.current = {
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    };
    graphDataRef.current = null;
    message.success("保存成功");
  } catch (e: unknown) {
    const err = e as { response?: { status?: number; data?: { detail?: string | object } } };
    if (err.response?.status === 409) {
      const detail = err.response.data?.detail;
      const conflictData = typeof detail === "string" ? JSON.parse(detail) : detail;
      setConflictInfo({
        saved_by: conflictData.conflict?.saved_by || null,
        saved_at: conflictData.conflict?.saved_at || null,
        latest_lock_version: conflictData.conflict?.latest_lock_version || 0,
      });

      // Fetch latest data and compute three-way diff
      try {
        const latestDoc = await getFMEA(id);
        const base = baseGraphRef.current;
        if (base) {
          const diff = diffGraphs(
            base.nodes, base.edges,
            latestDoc.graph_data?.nodes || [], latestDoc.graph_data?.edges || [],
            nodes, edges
          );
          setConflictDiff(diff);
        }
      } catch {
        /* silently ignore diff failure */
      }
      setConflictVisible(true);
    } else {
      message.error("保存失败");
    }
  } finally {
    setSaving(false);
  }
}, [id, fmea, nodes, edges]);
```

- [ ] **Step 4: 添加冲突处理回调**

```typescript
const handleConflictRefresh = () => {
  setConflictVisible(false);
  window.location.reload();
};

const handleConflictForceSave = async () => {
  if (!id || !fmea || !conflictInfo) return;
  setSaving(true);
  try {
    const updated = await updateFMEA(id, {
      title: fmea.title,
      graph_data: { nodes, edges },
      lock_version: fmea.lock_version,
      confirmed_latest_lock_version: conflictInfo.latest_lock_version,
    });
    setFmea(updated);
    baseGraphRef.current = {
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    };
    setConflictVisible(false);
    message.success("强制保存成功");
  } catch (e: unknown) {
    const err = e as { response?: { status?: number; data?: { detail?: string } } };
    if (err.response?.status === 409) {
      message.error("文档又被修改了，请刷新后重试");
    } else {
      message.error("强制保存失败");
    }
  } finally {
    setSaving(false);
  }
};
```

- [ ] **Step 5: 渲染协同组件**

在 JSX 中，在编辑器内容之前添加 `CollaborationBar`：

```tsx
<>
  <CollaborationBar activeUsers={activeUsers} isSyncing={isSyncing} />
  {/* 现有编辑器内容 */}
  ...
  <ConflictResolutionModal
    visible={conflictVisible}
    conflictInfo={conflictInfo}
    diff={conflictDiff}
    onRefresh={handleConflictRefresh}
    onForceSave={handleConflictForceSave}
  />
</>
```

- [ ] **Step 6: 在表格单元格添加编辑提示**

在 severity 等可编辑列的 render 中添加 `ActiveUserIndicator` 和 `onFocus`/`onBlur`：

```tsx
{
  title: "严重度(S)",
  render: (_, row) => {
    const node = nodeMap.get(row.failureModeNodeId);
    return (
      <div>
        <InputNumber
          value={node?.severity || 0}
          min={1}
          max={10}
          onFocus={() => startEditing({ row_key: row.key, field: "severity", node_id: row.failureModeNodeId })}
          onBlur={stopEditing}
          onChange={(val) => updateNode(row.failureModeNodeId, "severity", val)}
          disabled={!canEdit('fmea')}
        />
        <ActiveUserIndicator
          activeUsers={activeUsers}
          rowKey={row.key}
          field="severity"
        />
      </div>
    );
  },
}
```

对 occurrence、detection 等其他可编辑列重复同样模式。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx
git commit -m "feat(collaboration): integrate collaboration into FMEA editor"
```

---

### Task 19: 前端 — Control Plan 编辑器集成协同功能

**Files:**
- Modify: `frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx`
- Modify: `frontend/src/api/controlPlan.ts`

- [ ] **Step 1: Control Plan API 添加 lock_version 参数**

参照 Task 17，修改 `updateControlPlan` 函数签名添加 `lock_version` 和 `confirmed_latest_lock_version`。

- [ ] **Step 2: Control Plan 编辑器集成协同组件**

参照 Task 18 的模式：
- 导入 `useCollaboration`、`CollaborationBar`、`ConflictResolutionModal`
- 使用 `useCollaboration("control_plan", cpId)`
- 添加 base snapshot ref
- 修改 save 函数处理 409 冲突
- 渲染 `CollaborationBar`
- 在可编辑单元格添加 `onFocus`/`onBlur`（Control Plan 的 editing_area 也用 `{ row_key, field }`，与 FMEA 统一命名）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/controlPlan.ts frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx
git commit -m "feat(collaboration): integrate collaboration into Control Plan editor"
```

---

### Task 20: 后端行为测试

**Files:**
- Create: `backend/tests/test_collaboration.py`

**说明：** 项目现有测试风格使用 mock DB（不依赖真实 PostgreSQL），fixtures 定义在测试文件内。

- [ ] **Step 1: 编写 mock DB helper**

```python
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-collaboration-tests")

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.collaboration_service import (
    upsert_session,
    delete_session,
    get_active_users,
    delete_expired_sessions,
)
from app.models.collaboration_session import CollaborationSession


def _create_mock_db():
    """创建 mock AsyncSession，与 test_audit.py 风格一致。"""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_session_result(sessions: list):
    """构造 db.execute().scalars().all() 的 mock 链。"""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = sessions
    mock_result.scalars.return_value = mock_scalars
    return mock_result


DOC_ID = "123e4567-e89b-12d3-a456-426614174000"
USER_ID = uuid.uuid4()
```

- [ ] **Step 2: 编写 Service 测试**

```python
@pytest.mark.asyncio
async def test_upsert_session_calls_execute_and_commit():
    """验证 heartbeat 会执行 SQL 并提交。"""
    db = _create_mock_db()
    db.execute.return_value = MagicMock()

    await upsert_session(
        db, "fmea", DOC_ID,
        user_id=USER_ID, user_name="张三", action="viewing", editing_area=None
    )

    db.execute.assert_called_once()
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_active_users_filters_expired():
    """验证 TTL 过滤：只返回 60 秒内活跃的用户。"""
    db = _create_mock_db()

    active_session = CollaborationSession(
        document_type="fmea", document_id=uuid.UUID(DOC_ID),
        user_id=USER_ID, user_name="张三", action="viewing",
        last_activity=datetime.now(timezone.utc),
    )
    db.execute.return_value = _mock_session_result([active_session])

    users = await get_active_users(db, "fmea", DOC_ID)

    assert len(users) == 1
    assert users[0].user_name == "张三"
    # 验证查询条件包含 last_activity >= cutoff
    executed_stmt = db.execute.call_args[0][0]
    assert "last_activity" in str(executed_stmt)


@pytest.mark.asyncio
async def test_delete_expired_sessions():
    """验证清理函数执行 delete 并返回删除计数。"""
    db = _create_mock_db()
    mock_result = MagicMock()
    mock_result.rowcount = 3
    db.execute.return_value = mock_result

    deleted = await delete_expired_sessions(db)

    assert deleted == 3
    db.commit.assert_called_once()
```

- [ ] **Step 3: 编写 API 测试**

```python
from httpx import AsyncClient, ASGITransport
from fastapi import status

from app.main import app
from app.core.permissions import get_current_user


async def _override_get_current_user():
    from app.models.user import User
    return User(
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        username="tester",
        display_name="测试员",
        email="tester@openqms.local",
        password_hash="hashed",
        is_active=True,
        legacy_role="admin",
    )


@pytest.fixture
async def client():
    """ASGI transport 测试客户端，注入 mock user。"""
    app.dependency_overrides[get_current_user] = _override_get_current_user
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_heartbeat_endpoint(client: AsyncClient):
    """验证心跳端点返回 204。"""
    with patch("app.api.collaboration.collaboration_service.upsert_session") as mock_upsert:
        mock_upsert.return_value = None
        resp = await client.post(
            "/api/collaboration/heartbeat",
            json={
                "document_type": "fmea",
                "document_id": "123e4567-e89b-12d3-a456-426614174000",
                "action": "editing",
                "editing_area": {"row_key": "r1", "field": "severity"},
            },
        )
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        mock_upsert.assert_called_once()


@pytest.mark.asyncio
async def test_active_users_endpoint_returns_list(client: AsyncClient):
    """验证 active-users 端点返回正确结构。"""
    mock_session = CollaborationSession(
        document_type="fmea",
        document_id=uuid.UUID("123e4567-e89b-12d3-a456-426614174001"),
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        user_name="李四",
        action="editing",
        editing_area={"row_key": "r1", "field": "severity"},
        last_activity=datetime.now(timezone.utc),
    )
    with patch("app.api.collaboration.collaboration_service.get_active_users", return_value=[mock_session]):
        resp = await client.get("/api/collaboration/fmea/123e4567-e89b-12d3-a456-426614174001/active-users")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["total"] == 1
        assert len(data["users"]) == 1
        assert data["users"][0]["user_name"] == "李四"
        assert data["users"][0]["action"] == "editing"


@pytest.mark.asyncio
async def test_leave_endpoint(client: AsyncClient):
    """验证 leave 端点返回 204。"""
    with patch("app.api.collaboration.collaboration_service.delete_session") as mock_delete:
        mock_delete.return_value = None
        resp = await client.delete("/api/collaboration/leave/fmea/123e4567-e89b-12d3-a456-426614174002")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once()
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m pytest tests/test_collaboration.py -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_collaboration.py
git commit -m "test(collaboration): add service and API tests"
```

---

### Task 21: 构建验证

- [ ] **Step 1: 后端类型检查**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m py_compile app/main.py app/api/collaboration.py app/services/collaboration_service.py app/models/collaboration_session.py app/schemas/collaboration.py
```

Expected: No syntax errors.

- [ ] **Step 2: 后端行为测试**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m pytest tests/test_collaboration.py -v
```

Expected: All tests pass (see Task 20).

- [ ] **Step 3: 前端构建**

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npm run build
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 4: 前端 lint**

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npm run lint
```

Expected: No lint errors.

- [ ] **Step 5: Commit**

```bash
git commit --allow-empty -m "feat(collaboration): MVP complete — build, test and lint verified"
```

---

## Self-Review

### Spec Coverage Checklist

| Spec Section | 实现任务 |
|-------------|---------|
| collaboration_sessions 表 | Task 1 (migration), Task 2 (model) ✅ |
| 心跳 API | Task 5 (heartbeat endpoint) ✅ |
| active-users API + TTL 过滤 | Task 4 (get_active_users), Task 5 (route) ✅ |
| 会话清理（asyncio） | Task 6 (lifespan cleanup) ✅ |
| FMEA 乐观锁 | Task 7 ✅ |
| Control Plan 乐观锁 | Task 8 ✅ |
| 强制保存二次校验 | Task 7 Step 2, Task 8 Step 2 ✅ |
| 前端 useCollaboration Hook | Task 12 ✅ |
| CollaborationBar | Task 13 ✅ |
| ActiveUserIndicator | Task 14 ✅ |
| ConflictResolutionModal | Task 15 ✅ |
| Client-side three-way diff | Task 11 ✅ |
| FMEA 编辑器集成 | Task 18 ✅ |
| Control Plan 编辑器集成 | Task 19 ✅ |
| fetch keepalive + auth header 清理 | Task 12 (useEffect cleanup) ✅ |
| 后端行为测试 | Task 20 ✅ |

### Placeholder Scan

- 无 "TBD", "TODO", "implement later" ✅
- 所有代码块包含完整实现 ✅
- Task 8/19 参照 Task 7/18 模式，但每处都重复了完整代码或明确指令，不存在"详见 Task X"的悬空引用 ✅

### Type Consistency

- `editing_area` JSONB ↔ `EditingArea` 接口字段一致 ✅
- `lock_version` 在后端模型、schema、service、API 中命名一致 ✅
- `confirmed_latest_lock_version` 在 FMEA 和 Control Plan 中命名一致 ✅
- `CollaborationSession` 模型字段与 migration 一致 ✅
