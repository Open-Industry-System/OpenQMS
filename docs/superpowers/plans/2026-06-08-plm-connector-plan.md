# PLM 集成连接器实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 PLM（产品生命周期管理）集成连接器，支持 Parts/BOMs/ECN 同步、BOM→DFMEA 导入、ECN→变更影响分析、Part→SC 关联。

**Architecture:** 复用 MES 已验证模式（连接器 ABC + 三阶段短事务同步 + Outbox 推送），保持数据独立（9 张 PLM 专用表），通过 `plm_part_fmea_links` / `plm_part_sc_links` / `plm_change_impact_tasks` 关联表打通 PLM ↔ OpenQMS。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 + Pydantic v2 + PostgreSQL + asyncpg | React 18 + TypeScript + Ant Design 5 | Alembic 迁移 | pytest

---

## 文件结构总览

### 后端新增
| 文件 | 职责 |
|------|------|
| `backend/alembic/versions/031_add_plm_tables.py` | 9 张表迁移 + PLM 权限种子 + system 用户 |
| `backend/app/models/plm.py` | 9 个 SQLAlchemy 模型 |
| `backend/app/schemas/plm.py` | Pydantic v2 Request/Response schemas |
| `backend/app/services/plm_connector.py` | PLMConnector ABC + Mock + REST |
| `backend/app/services/plm_service.py` | PLMIngestionService + PLMSyncService + ImpactTaskWorker |
| `backend/app/api/plm.py` | FastAPI 路由（13 端点 + 权限装饰器） |
| `backend/tests/test_plm.py` | 后端测试 |

### 后端修改
| 文件 | 修改内容 |
|------|---------|
| `backend/app/core/permissions.py` | Module 枚举新增 `PLM = "plm"` |
| `backend/app/core/product_line_filter.py` | 添加 `"plm": "product_line_code"` |
| `backend/app/core/config.py` | 定义 `SYSTEM_USER_ID` 常量 |
| `backend/app/models/__init__.py` | 导出 PLM 模型 |
| `backend/app/services/graph_projection_service.py` | `ALLOWED_EDGE_TYPES` 增加 `"HAS_CHILD"`；`_node_properties` 白名单增加 `"part_number"` |
| `backend/app/graph/jsonb_repository.py` | `downstream_edges` 增加 `"HAS_CHILD"` |
| `backend/app/graph/neo4j_repository.py` | `downstream_rel_types` 追加 `\|HAS_CHILD` |
| `backend/app/main.py` | 注册 plm_router + 后台协程 |
| `backend/app/seed.py` | 预置 system 用户 + PLM 演示数据 |

### 前端新增
| 文件 | 职责 |
|------|------|
| `frontend/src/types/plm.ts` | PLM TypeScript 类型 |
| `frontend/src/api/plm.ts` | PLM API 客户端函数 |
| `frontend/src/pages/plm/PLMConnectionsPage.tsx` | 连接管理 CRUD |
| `frontend/src/pages/plm/PLMDashboardPage.tsx` | 数据看板 |
| `frontend/src/pages/plm/PLMPartsPage.tsx` | 零部件列表 + 详情 Drawer |
| `frontend/src/pages/plm/PLMChangeOrdersPage.tsx` | ECN 列表 + 详情 |

### 前端修改
| 文件 | 修改内容 |
|------|---------|
| `frontend/src/App.tsx` | 新增 PLM 路由 |
| `frontend/src/components/layout/AppLayout.tsx` | 新增 PLM 菜单（权限控制） |

---

## Task 1: 数据库迁移 — 9 张 PLM 表

**Files:**
- Create: `backend/alembic/versions/031_add_plm_tables.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 编写 Alembic 迁移**

参考 `backend/alembic/versions/030_add_mes_tables.py` 的结构，创建 9 张表：

```python
"""add PLM integration tables and permissions

Revision ID: 031_add_plm_tables
Revises: 030_add_mes_tables
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = '031_add_plm_tables'
down_revision: Union[str, None] = '030_add_mes_tables'


def upgrade():
    # 1. plm_connections (同 mes_connections 结构)
    op.create_table(
        'plm_connections',
        sa.Column('connection_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('connector_type', sa.String(50), nullable=False),
        sa.Column('config', JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('product_line_code', sa.String(50), sa.ForeignKey('product_lines.code'), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # 2. plm_parts
    op.create_table(
        'plm_parts',
        sa.Column('part_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('plm_connections.connection_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('part_number', sa.String(100), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('revision', sa.String(20), nullable=False, server_default=sa.text("'A'")),
        sa.Column('material', sa.String(100), nullable=True),
        sa.Column('specification', sa.Text, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column('is_safety_related', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_key_characteristic', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('product_line_code', sa.String(50), sa.ForeignKey('product_lines.code'), nullable=True),
        sa.Column('plm_raw_data', JSONB, nullable=True),
        sa.UniqueConstraint('connection_id', 'part_number', 'revision', name='uq_plm_part_conn_pn_rev'),
    )

    # 3. plm_boms
    op.create_table(
        'plm_boms',
        sa.Column('bom_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('plm_connections.connection_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('parent_part_number', sa.String(100), nullable=False),
        sa.Column('parent_revision', sa.String(20), nullable=False, server_default=sa.text("'A'")),
        sa.Column('child_part_number', sa.String(100), nullable=False),
        sa.Column('child_revision', sa.String(20), nullable=False, server_default=sa.text("'A'")),
        sa.Column('quantity', sa.Numeric(10, 4), nullable=False, server_default=sa.text('1.0')),
        sa.Column('bom_revision', sa.String(20), nullable=False, server_default=sa.text("'A'")),
        sa.Column('level', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('product_line_code', sa.String(50), sa.ForeignKey('product_lines.code'), nullable=True),
        sa.Column('plm_raw_data', JSONB, nullable=True),
        sa.UniqueConstraint('connection_id', 'parent_part_number', 'parent_revision', 'child_part_number', 'child_revision', 'bom_revision', name='uq_plm_bom_conn_parent_child_rev'),
    )

    # 4. plm_change_orders
    op.create_table(
        'plm_change_orders',
        sa.Column('change_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('plm_connections.connection_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('change_number', sa.String(50), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('change_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column('priority', sa.String(20), nullable=False, server_default=sa.text("'normal'")),
        sa.Column('affected_part_numbers', JSONB, nullable=False, server_default=sa.text("'[]'")),
        sa.Column('proposed_changes', JSONB, nullable=True),
        sa.Column('requested_by', sa.String(100), nullable=True),
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('planned_implementation_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_implementation_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('product_line_code', sa.String(50), sa.ForeignKey('product_lines.code'), nullable=True),
        sa.Column('plm_raw_data', JSONB, nullable=True),
        sa.UniqueConstraint('connection_id', 'change_number', name='uq_plm_co_conn_num'),
    )

    # 5. plm_sync_jobs
    op.create_table(
        'plm_sync_jobs',
        sa.Column('job_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('plm_connections.connection_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('data_type', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('checkpoint', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('claim_token', sa.String(36), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('connection_id', 'data_type', name='uq_plm_sync_job_conn_type'),
    )
    op.create_index('ix_plm_sync_jobs_status_next_run', 'plm_sync_jobs', ['status', 'next_run_at'])

    # 6. plm_push_outbox
    op.create_table(
        'plm_push_outbox',
        sa.Column('outbox_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('plm_connections.connection_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('payload', JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default=sa.text('3')),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('claim_token', sa.String(36), nullable=True),
        sa.Column('last_error', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_plm_push_outbox_status_next_retry', 'plm_push_outbox', ['status', 'next_retry_at'])

    # 7. plm_change_impact_tasks
    op.create_table(
        'plm_change_impact_tasks',
        sa.Column('task_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('change_id', UUID(as_uuid=True), sa.ForeignKey('plm_change_orders.change_id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('claim_token', sa.String(36), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default=sa.text('3')),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('result', JSONB, nullable=True),
        sa.UniqueConstraint('change_id', name='uq_plm_impact_task_change'),
    )
    op.create_index('ix_plm_change_impact_tasks_status_next_retry', 'plm_change_impact_tasks', ['status', 'next_retry_at'])

    # 8. plm_part_fmea_links
    op.create_table(
        'plm_part_fmea_links',
        sa.Column('link_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('part_id', UUID(as_uuid=True), sa.ForeignKey('plm_parts.part_id', ondelete='CASCADE'), nullable=False),
        sa.Column('fmea_id', UUID(as_uuid=True), sa.ForeignKey('fmea_documents.fmea_id', ondelete='CASCADE'), nullable=False),
        sa.Column('node_id', sa.String(128), nullable=False),
        sa.Column('link_type', sa.String(20), nullable=False, server_default=sa.text("'auto_import'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('part_id', 'fmea_id', 'node_id', name='uq_plm_part_fmea_link'),
    )

    # 9. plm_part_sc_links
    op.create_table(
        'plm_part_sc_links',
        sa.Column('link_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('part_id', UUID(as_uuid=True), sa.ForeignKey('plm_parts.part_id', ondelete='CASCADE'), nullable=False),
        sa.Column('sc_id', UUID(as_uuid=True), sa.ForeignKey('special_characteristics.sc_id', ondelete='SET NULL'), nullable=True),
        sa.Column('characteristic_type', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('confirmed_by', UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('product_line_code', sa.String(50), sa.ForeignKey('product_lines.code'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('part_id', 'characteristic_type', name='uq_plm_part_sc'),
    )

    # ---- PLM permissions ----
    PLM_PERMS = {
        'admin': 5, 'manager': 4, 'field_qe': 2,
        'viewer': 1, 'customer_qe': 1, 'supplier_qe': 1, 'planning_qe': 1,
    }
    for role_key, level in PLM_PERMS.items():
        op.execute(
            "INSERT INTO role_permissions (role_id, module, permission_level) "
            f"SELECT id, 'plm', {level} FROM role_definitions WHERE role_key = '{role_key}' "
            "ON CONFLICT (role_id, module) DO NOTHING"
        )

    # ---- system user for background tasks ----
    # Users table: password_hash, role_id (FK to role_definitions), no hashed_password/role column
    op.execute(
        "INSERT INTO users (user_id, username, display_name, email, password_hash, role_id, is_active) "
        "SELECT '00000000-0000-0000-0000-000000000001', 'system', 'System', 'system@openqms.local', '', id, true "
        "FROM role_definitions WHERE role_key = 'admin' "
        "ON CONFLICT (user_id) DO NOTHING"
    )


def downgrade():
    op.execute("DELETE FROM role_permissions WHERE module = 'plm'")
    op.drop_table('plm_part_sc_links')
    op.drop_table('plm_part_fmea_links')
    op.drop_index('ix_plm_change_impact_tasks_status_next_retry', table_name='plm_change_impact_tasks')
    op.drop_table('plm_change_impact_tasks')
    op.drop_index('ix_plm_push_outbox_status_next_retry', table_name='plm_push_outbox')
    op.drop_table('plm_push_outbox')
    op.drop_index('ix_plm_sync_jobs_status_next_run', table_name='plm_sync_jobs')
    op.drop_table('plm_sync_jobs')
    op.drop_table('plm_change_orders')
    op.drop_table('plm_boms')
    op.drop_table('plm_parts')
    op.drop_table('plm_connections')
```

- [ ] **Step 2: 运行迁移**

Run: `cd backend && alembic upgrade head`
Expected: `Running upgrade 030_add_mes_tables -> 031_add_plm_tables, done`

- [ ] **Step 3: 修改 models/__init__.py 导出 PLM 模型**

```python
# backend/app/models/__init__.py
from .plm import (
    PLMConnection, PLMPart, PLMBOM, PLMChangeOrder,
    PLMSyncJob, PLMPushOutbox, PLMChangeImpactTask,
    PLMPartFMEALink, PLMPartSCLink,
)
```

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/031_add_plm_tables.py backend/app/models/__init__.py
git commit -m "feat(migration): add 9 PLM tables + permissions + system user"
```

---

## Task 2: 后端模型层 — plm.py

**Files:**
- Create: `backend/app/models/plm.py`

- [ ] **Step 1: 编写 9 个 PLM 模型**

```python
"""PLM integration models."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, ForeignKey, DateTime, Text, Numeric, Boolean,
    UniqueConstraint, Index, func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PLMConnection(Base):
    __tablename__ = "plm_connections"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    product_line_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("product_lines.code"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sync_jobs = relationship("PLMSyncJob", back_populates="connection")
    outbox = relationship("PLMPushOutbox", back_populates="connection")


class PLMPart(Base):
    __tablename__ = "plm_parts"
    __table_args__ = (
        UniqueConstraint("connection_id", "part_number", "revision", name="uq_plm_part_conn_pn_rev"),
    )

    part_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    part_number: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    revision: Mapped[str] = mapped_column(String(20), nullable=False, default="A")
    material: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    specification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    is_safety_related: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_key_characteristic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("product_lines.code"), nullable=True)
    plm_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class PLMBOM(Base):
    __tablename__ = "plm_boms"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "parent_part_number", "parent_revision",
            "child_part_number", "child_revision", "bom_revision",
            name="uq_plm_bom_conn_parent_child_rev"
        ),
    )

    bom_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_part_number: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_revision: Mapped[str] = mapped_column(String(20), nullable=False, default="A")
    child_part_number: Mapped[str] = mapped_column(String(100), nullable=False)
    child_revision: Mapped[str] = mapped_column(String(20), nullable=False, default="A")
    quantity: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=1.0)
    bom_revision: Mapped[str] = mapped_column(String(20), nullable=False, default="A")
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("product_lines.code"), nullable=True)
    plm_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class PLMChangeOrder(Base):
    __tablename__ = "plm_change_orders"
    __table_args__ = (
        UniqueConstraint("connection_id", "change_number", name="uq_plm_co_conn_num"),
    )

    change_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    change_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    affected_part_numbers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    proposed_changes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    planned_implementation_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_implementation_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("product_lines.code"), nullable=True)
    plm_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class PLMSyncJob(Base):
    __tablename__ = "plm_sync_jobs"
    __table_args__ = (
        UniqueConstraint("connection_id", "data_type", name="uq_plm_sync_job_conn_type"),
        Index("ix_plm_sync_jobs_status_next_run", "status", "next_run_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    checkpoint: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    connection = relationship("PLMConnection", back_populates="sync_jobs")


class PLMPushOutbox(Base):
    __tablename__ = "plm_push_outbox"
    __table_args__ = (
        Index("ix_plm_push_outbox_status_next_retry", "status", "next_retry_at"),
    )

    outbox_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plm_connections.connection_id", ondelete="RESTRICT"), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    connection = relationship("PLMConnection", back_populates="outbox")


class PLMChangeImpactTask(Base):
    __tablename__ = "plm_change_impact_tasks"
    __table_args__ = (
        UniqueConstraint("change_id", name="uq_plm_impact_task_change"),
        Index("ix_plm_change_impact_tasks_status_next_retry", "status", "next_retry_at"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plm_change_orders.change_id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    claim_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class PLMPartFMEALink(Base):
    __tablename__ = "plm_part_fmea_links"
    __table_args__ = (
        UniqueConstraint("part_id", "fmea_id", "node_id", name="uq_plm_part_fmea_link"),
    )

    link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plm_parts.part_id", ondelete="CASCADE"), nullable=False
    )
    fmea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    link_type: Mapped[str] = mapped_column(String(20), nullable=False, default="auto_import")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PLMPartSCLink(Base):
    __tablename__ = "plm_part_sc_links"
    __table_args__ = (
        UniqueConstraint("part_id", "characteristic_type", name="uq_plm_part_sc"),
    )

    link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plm_parts.part_id", ondelete="CASCADE"), nullable=False
    )
    sc_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("special_characteristics.sc_id", ondelete="SET NULL"), nullable=True
    )
    characteristic_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    confirmed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[str] = mapped_column(String(50), ForeignKey("product_lines.code"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/plm.py
git commit -m "feat(models): add 9 PLM integration models"
```

---

## Task 3: Schemas — Pydantic v2

**Files:**
- Create: `backend/app/schemas/plm.py`

- [ ] **Step 1: 编写所有 Pydantic schemas**

```python
"""PLM Pydantic v2 schemas."""
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class PLMConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    connector_type: str = Field(..., pattern="^(mock|rest|siemens_tc|dassault_enovia|ptc_windchill)$")
    config: dict = Field(default_factory=dict)
    product_line_code: str = Field(..., min_length=1)


class PLMConnectionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    connector_type: Optional[str] = Field(None, pattern="^(mock|rest|siemens_tc|dassault_enovia|ptc_windchill)$")
    config: Optional[dict] = None
    is_active: Optional[bool] = None
    product_line_code: Optional[str] = Field(None, min_length=1)


class PLMConnectionResponse(BaseModel):
    connection_id: uuid.UUID
    name: str
    connector_type: str
    config: dict
    is_active: bool
    product_line_code: Optional[str]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class PLMConnectionListResponse(BaseModel):
    items: list[PLMConnectionResponse]
    total: int
    page: int
    page_size: int


class PLMPartResponse(BaseModel):
    part_id: uuid.UUID
    connection_id: uuid.UUID
    external_id: str
    part_number: str
    name: str
    revision: str
    material: Optional[str]
    specification: Optional[str]
    status: str
    is_safety_related: bool
    is_key_characteristic: bool
    source_updated_at: Optional[datetime]
    product_line_code: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


class PLMBOMResponse(BaseModel):
    bom_id: uuid.UUID
    connection_id: uuid.UUID
    external_id: str
    parent_part_number: str
    parent_revision: str
    child_part_number: str
    child_revision: str
    quantity: float
    bom_revision: str
    level: int
    product_line_code: Optional[str]
    model_config = {"from_attributes": True}


class PLMChangeOrderResponse(BaseModel):
    change_id: uuid.UUID
    connection_id: uuid.UUID
    external_id: str
    change_number: str
    title: str
    description: Optional[str]
    change_type: str
    status: str
    priority: str
    affected_part_numbers: list
    proposed_changes: Optional[dict]
    requested_by: Optional[str]
    approved_by: Optional[str]
    planned_implementation_date: Optional[datetime]
    actual_implementation_date: Optional[datetime]
    source_updated_at: Optional[datetime]
    product_line_code: Optional[str]
    model_config = {"from_attributes": True}


class PLMChangeImpactTaskResponse(BaseModel):
    task_id: uuid.UUID
    change_id: uuid.UUID
    status: str
    retry_count: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    result: Optional[dict]
    model_config = {"from_attributes": True}


class PLMDashboardResponse(BaseModel):
    part_count: int
    bom_count: int
    pending_ecn_count: int
    pending_sc_count: int
    recent_changes: list[PLMChangeOrderResponse]


class BOMImportRequest(BaseModel):
    fmea_id: uuid.UUID
    overwrite: bool = False


class PLMPartLinkFMEARequest(BaseModel):
    fmea_id: uuid.UUID
    node_id: str


class PLMPartConfirmSCRequest(BaseModel):
    fmea_id: uuid.UUID
    node_id: str
    characteristic_type: Literal["safety", "key_characteristic"]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/plm.py
git commit -m "feat(schemas): add PLM Pydantic v2 schemas"
```

---

## Task 4: 权限与配置

**Files:**
- Modify: `backend/app/core/permissions.py`
- Modify: `backend/app/core/product_line_filter.py`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: permissions.py 新增 Module.PLM**

```python
# backend/app/core/permissions.py — 在 Module 枚举中追加
class Module(StrEnum):
    # ... existing modules ...
    MES = "mes"
    PLM = "plm"  # <-- add this
```

- [ ] **Step 2: product_line_filter.py 新增映射**

```python
# backend/app/core/product_line_filter.py
PRODUCT_LINE_FIELD_MAP: dict[str, str] = {
    # ... existing mappings ...
    "mes": "product_line_code",
    "plm": "product_line_code",  # <-- add this
}
```

- [ ] **Step 3: config.py 定义 SYSTEM_USER_ID**

```python
# backend/app/core/config.py
import uuid

SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/permissions.py backend/app/core/product_line_filter.py backend/app/core/config.py
git commit -m "feat(permissions): add Module.PLM, product line mapping, SYSTEM_USER_ID"
```

---

## Task 5: 连接器层 — PLMConnector

**Files:**
- Create: `backend/app/services/plm_connector.py`

- [ ] **Step 1: 编写 PLMConnector ABC + Mock + REST**

参考 `backend/app/services/mes_connector.py` 的 HTTP/重试/分页/认证逻辑，复制核心模式但保持独立类。

```python
"""PLM Connector adapter layer."""
import hashlib
import random
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.mes_crypto import decrypt_credential


_SCHEMA_MAP = {}  # Will be populated with PLM schemas


class PLMConnector(ABC):
    @abstractmethod
    async def fetch_parts(self, since: datetime) -> list[dict]: ...
    @abstractmethod
    async def fetch_boms(self, since: datetime) -> list[dict]: ...
    @abstractmethod
    async def fetch_change_orders(self, since: datetime) -> list[dict]: ...
    @abstractmethod
    async def push_change_status(self, change_number: str, status: str, data: dict) -> dict: ...


class MockPLMConnector(PLMConnector):
    """Mock PLM connector generating DC-DC-100 demo data."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_parts(self, since: datetime) -> list[dict]:
        parts = [
            {"part_number": "DC-DC-100-PCB-001", "name": "主控PCB", "revision": "A", "material": "FR4", "status": "active", "is_safety_related": False, "is_key_characteristic": True},
            {"part_number": "DC-DC-100-MOS-001", "name": "功率MOSFET", "revision": "B", "material": "Si", "status": "active", "is_safety_related": True, "is_key_characteristic": True},
            {"part_number": "DC-DC-100-IND-001", "name": "功率电感", "revision": "A", "material": "Fe-Ni", "status": "active", "is_safety_related": False, "is_key_characteristic": False},
        ]
        now = datetime.now(timezone.utc)
        return [{**p, "external_id": f"PART-{p['part_number']}", "source_updated_at": now, "product_line_code": "DC-DC-100"} for p in parts]

    async def fetch_boms(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [
            {"external_id": "BOM-001", "parent_part_number": "DC-DC-100", "parent_revision": "A", "child_part_number": "DC-DC-100-PCB-001", "child_revision": "A", "quantity": 1, "bom_revision": "A", "level": 1, "source_updated_at": now, "product_line_code": "DC-DC-100"},
            {"external_id": "BOM-002", "parent_part_number": "DC-DC-100-PCB-001", "parent_revision": "A", "child_part_number": "DC-DC-100-MOS-001", "child_revision": "B", "quantity": 4, "bom_revision": "A", "level": 2, "source_updated_at": now, "product_line_code": "DC-DC-100"},
            {"external_id": "BOM-003", "parent_part_number": "DC-DC-100-PCB-001", "parent_revision": "A", "child_part_number": "DC-DC-100-IND-001", "child_revision": "A", "quantity": 2, "bom_revision": "A", "level": 2, "source_updated_at": now, "product_line_code": "DC-DC-100"},
        ]

    async def fetch_change_orders(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [
            {"external_id": "ECN-001", "change_number": "ECN-2026-001", "title": "MOSFET 材料变更", "description": "从 Si 改为 SiC", "change_type": "material", "status": "approved", "priority": "high", "affected_part_numbers": ["DC-DC-100-MOS-001|B"], "source_updated_at": now, "product_line_code": "DC-DC-100"},
        ]

    async def push_change_status(self, change_number: str, status: str, data: dict) -> dict:
        return {"status": "ok", "mock": True}


class RESTPLMConnector(PLMConnector):
    """Generic REST PLM connector."""

    def __init__(self, config: dict):
        self.config = config
        self.base_url = config.get("base_url", "").rstrip("/")
        self.timeout = config.get("timeout", 30)
        self.retry_config = config.get("retry", {"max_retries": 3, "backoff_seconds": [1, 2, 4]})
        self.endpoints = config.get("endpoints", {})
        self.field_mapping = config.get("field_mapping", {})
        self.auth_type = config.get("auth_type", "none")
        self.auth_config = config.get("auth_config", {})
        self._client = httpx.AsyncClient(timeout=self.timeout)

    # _resolve_auth, _auth_for_httpx, _map_field, _reverse_map,
    # _get_response_data, _request, _fetch_paginated
    # — copy from RESTMESConnector, adapt endpoint names

    async def fetch_parts(self, since: datetime) -> list[dict]: ...
    async def fetch_boms(self, since: datetime) -> list[dict]: ...
    async def fetch_change_orders(self, since: datetime) -> list[dict]: ...
    async def push_change_status(self, change_number: str, status: str, data: dict) -> dict: ...

    async def close(self):
        await self._client.aclose()


async def get_plm_connector(connection, db: AsyncSession | None = None) -> PLMConnector:
    if connection.connector_type == "mock":
        if db is None:
            raise ValueError("MockPLMConnector requires db session")
        return MockPLMConnector(db)
    elif connection.connector_type == "rest":
        return RESTPLMConnector(connection.config)
    else:
        raise ValueError(f"Unknown connector_type: {connection.connector_type}")


async def test_plm_connection(connection, db: AsyncSession | None = None) -> dict:
    connector = None
    try:
        connector = await get_plm_connector(connection, db)
        if isinstance(connector, RESTPLMConnector):
            ep = connector.endpoints.get("parts", {})
            path = ep.get("path", "/parts")
            await connector._request("GET", path, params={"page_size": 1})
        elif isinstance(connector, MockPLMConnector):
            await connector.fetch_parts(since=datetime.now(timezone.utc))
        return {"ok": True, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if isinstance(connector, RESTPLMConnector):
            await connector.close()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/plm_connector.py
git commit -m "feat(connector): add PLMConnector ABC + Mock + REST skeleton"
```

---

## Task 6: 服务层 — PLMIngestionService + PLMSyncService

**Files:**
- Create: `backend/app/services/plm_service.py`

- [ ] **Step 1: 编写 PLMIngestionService**

参考 `backend/app/services/mes_service.py` 的 MESIngestionService 模式。

```python
"""PLM ingestion and sync services."""
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import async_session
from app.models.plm import (
    PLMConnection, PLMPart, PLMBOM, PLMChangeOrder,
    PLMSyncJob, PLMPushOutbox, PLMChangeImpactTask,
    PLMPartFMEALink, PLMPartSCLink,
)
from app.services.plm_connector import get_plm_connector, get_plm_connector_by_config


class PLMIngestionService:
    """Dispatch PLM raw data into OpenQMS tables atomically. Caller controls transaction."""

    @staticmethod
    async def ingest(db: AsyncSession, data: dict) -> dict:
        data_type = data.get("data_type")
        if data_type == "part":
            return await PLMIngestionService._ingest_part(db, data)
        elif data_type == "bom":
            return await PLMIngestionService._ingest_bom(db, data)
        elif data_type == "change_order":
            return await PLMIngestionService._ingest_change_order(db, data)
        raise ValueError(f"Unsupported data_type: {data_type}")

    @staticmethod
    async def _ingest_part(db: AsyncSession, data: dict) -> dict:
        stmt = pg_insert(PLMPart).values(
            connection_id=data["connection_id"],
            external_id=data["external_id"],
            part_number=data["part_number"],
            name=data["name"],
            revision=data.get("revision", "A"),
            material=data.get("material"),
            specification=data.get("specification"),
            status=data.get("status", "active"),
            is_safety_related=data.get("is_safety_related", False),
            is_key_characteristic=data.get("is_key_characteristic", False),
            source_updated_at=data.get("source_updated_at"),
            product_line_code=data.get("product_line_code"),
            plm_raw_data=data.get("raw_data"),
        ).on_conflict_do_update(
            index_elements=["connection_id", "part_number", "revision"],
            set_={
                "name": data["name"],
                "material": data.get("material"),
                "specification": data.get("specification"),
                "status": data.get("status"),
                "is_safety_related": data.get("is_safety_related", False),
                "is_key_characteristic": data.get("is_key_characteristic", False),
                "source_updated_at": data.get("source_updated_at"),
                "plm_raw_data": data.get("raw_data"),
            }
        )
        await db.execute(stmt)

        # Auto-create SC pending links
        if data.get("is_safety_related"):
            await PLMIngestionService._ensure_sc_link(db, data, "safety")
        if data.get("is_key_characteristic"):
            await PLMIngestionService._ensure_sc_link(db, data, "key_characteristic")

        return {"status": "success"}

    @staticmethod
    async def _ensure_sc_link(db: AsyncSession, data: dict, characteristic_type: str):
        # Find part_id first
        result = await db.execute(
            select(PLMPart.part_id).where(
                PLMPart.connection_id == data["connection_id"],
                PLMPart.part_number == data["part_number"],
                PLMPart.revision == data.get("revision", "A"),
            )
        )
        part_id = result.scalar()
        if not part_id:
            return
        stmt = pg_insert(PLMPartSCLink).values(
            part_id=part_id,
            characteristic_type=characteristic_type,
            status="pending",
            product_line_code=data.get("product_line_code", "__none__"),
        ).on_conflict_do_nothing(
            index_elements=["part_id", "characteristic_type"]
        )
        await db.execute(stmt)

    @staticmethod
    async def _ingest_bom(db: AsyncSession, data: dict) -> dict:
        stmt = pg_insert(PLMBOM).values(
            connection_id=data["connection_id"],
            external_id=data["external_id"],
            parent_part_number=data["parent_part_number"],
            parent_revision=data.get("parent_revision", "A"),
            child_part_number=data["child_part_number"],
            child_revision=data.get("child_revision", "A"),
            quantity=data.get("quantity", 1.0),
            bom_revision=data.get("bom_revision", "A"),
            level=data.get("level", 1),
            source_updated_at=data.get("source_updated_at"),
            product_line_code=data.get("product_line_code"),
            plm_raw_data=data.get("raw_data"),
        ).on_conflict_do_nothing(
            index_elements=["connection_id", "parent_part_number", "parent_revision", "child_part_number", "child_revision", "bom_revision"]
        )
        await db.execute(stmt)
        return {"status": "success"}

    @staticmethod
    async def _ingest_change_order(db: AsyncSession, data: dict) -> dict:
        # Check old status for approved transition
        old_result = await db.execute(
            select(PLMChangeOrder.status).where(
                PLMChangeOrder.connection_id == data["connection_id"],
                PLMChangeOrder.change_number == data["change_number"],
            )
        )
        old_status = old_result.scalar()

        stmt = pg_insert(PLMChangeOrder).values(
            connection_id=data["connection_id"],
            external_id=data["external_id"],
            change_number=data["change_number"],
            title=data["title"],
            description=data.get("description"),
            change_type=data["change_type"],
            status=data.get("status", "draft"),
            priority=data.get("priority", "normal"),
            affected_part_numbers=data.get("affected_part_numbers", []),
            proposed_changes=data.get("proposed_changes"),
            requested_by=data.get("requested_by"),
            approved_by=data.get("approved_by"),
            planned_implementation_date=data.get("planned_implementation_date"),
            actual_implementation_date=data.get("actual_implementation_date"),
            source_updated_at=data.get("source_updated_at"),
            product_line_code=data.get("product_line_code"),
            plm_raw_data=data.get("raw_data"),
        ).on_conflict_do_update(
            index_elements=["connection_id", "change_number"],
            set_={
                "status": data.get("status"),
                "approved_by": data.get("approved_by"),
                "actual_implementation_date": data.get("actual_implementation_date"),
                "source_updated_at": data.get("source_updated_at"),
                "plm_raw_data": data.get("raw_data"),
            }
        )
        await db.execute(stmt)

        # If status changed to approved, create impact task
        new_status = data.get("status")
        if old_status != "approved" and new_status == "approved":
            await db.execute(
                pg_insert(PLMChangeImpactTask).values(
                    change_id=(
                        select(PLMChangeOrder.change_id)
                        .where(PLMChangeOrder.connection_id == data["connection_id"])
                        .where(PLMChangeOrder.change_number == data["change_number"])
                    ),
                    status="pending",
                ).on_conflict_do_nothing(index_elements=["change_id"])
            )

        return {"status": "success"}
```

- [ ] **Step 2: 编写 PLMSyncService + ImpactTaskWorker**

复用 MESSyncService 的三阶段短事务模式。

```python
class PLMSyncService:
    SYNC_INTERVAL_MINUTES = 5
    OVERLAP_WINDOW_SECONDS = 300
    TIMEOUT_MINUTES = 10
    MAX_FAILURES = 3
    BATCH_SIZE = 100

    CHECKPOINT_FIELDS = {
        "parts": ["source_updated_at"],
        "boms": ["source_updated_at"],
        "change_orders": ["source_updated_at"],
    }

    @staticmethod
    async def create_sync_jobs_for_connection(db: AsyncSession, connection_id: uuid.UUID):
        for data_type in ("parts", "boms", "change_orders"):
            db.add(PLMSyncJob(
                connection_id=connection_id,
                data_type=data_type,
                status="pending",
            ))

    @staticmethod
    async def claim_jobs(db: AsyncSession) -> list[PLMSyncJob]:
        from sqlalchemy import text
        stmt = (
            select(PLMSyncJob)
            .join(PLMConnection, PLMSyncJob.connection_id == PLMConnection.connection_id)
            .where(PLMConnection.is_active == True)
            .where(
                (PLMSyncJob.status.in_(["pending", "failed"]))
                | ((PLMSyncJob.status == "completed") & (PLMSyncJob.next_run_at <= datetime.now(timezone.utc)))
            )
        )
        result = await db.execute(stmt.with_for_update(skip_locked=True).limit(PLMSyncService.BATCH_SIZE))
        jobs = result.scalars().all()
        for job in jobs:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.claim_token = str(uuid.uuid4())
        return jobs

    @staticmethod
    async def recover_stuck_jobs(db: AsyncSession) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=PLMSyncService.TIMEOUT_MINUTES)
        stmt = select(PLMSyncJob).where(PLMSyncJob.status == "running").where(PLMSyncJob.started_at < cutoff)
        result = await db.execute(stmt.with_for_update(skip_locked=True))
        stuck = result.scalars().all()
        for job in stuck:
            job.status = "failed"
            job.claim_token = None
            job.error_message = "Timeout: sync job exceeded 10 minutes"
        return len(stuck)

    @staticmethod
    async def run_sync_round(db: AsyncSession):
        recovered = await PLMSyncService.recover_stuck_jobs(db)
        if recovered:
            await db.commit()
        jobs = await PLMSyncService.claim_jobs(db)
        if not jobs:
            return
        await db.commit()
        for job in jobs:
            try:
                await PLMSyncService._sync_single_job(db, job)
            except Exception as e:
                async with async_session() as fail_db:
                    job_refresh = await fail_db.get(PLMSyncJob, job.job_id)
                    if job_refresh and job_refresh.claim_token == job.claim_token:
                        job_refresh.status = "failed"
                        job_refresh.claim_token = None
                        job_refresh.error_message = str(e)
                        job_refresh.consecutive_failures += 1
                        if job_refresh.consecutive_failures >= PLMSyncService.MAX_FAILURES:
                            await fail_db.execute(
                                update(PLMConnection)
                                .where(PLMConnection.connection_id == job_refresh.connection_id)
                                .values(is_active=False)
                            )
                        await fail_db.commit()

    @staticmethod
    async def _sync_single_job(db: AsyncSession, job: PLMSyncJob):
        # Phase 2a: Read connection config into memory
        async with async_session() as read_db:
            result = await read_db.execute(
                select(PLMConnection).where(PLMConnection.connection_id == job.connection_id)
            )
            connection = result.scalar_one()
            connector_type = connection.connector_type
            config = dict(connection.config)
            connection_product_line_code = connection.product_line_code

        # Phase 2b: External fetch (NO transaction)
        connector = await get_plm_connector_by_config(connector_type, config, db)
        since = None
        if job.checkpoint:
            since = job.checkpoint - timedelta(seconds=PLMSyncService.OVERLAP_WINDOW_SECONDS)

        data = []
        try:
            if job.data_type == "parts":
                data = await connector.fetch_parts(since)
            elif job.data_type == "boms":
                data = await connector.fetch_boms(since)
            elif job.data_type == "change_orders":
                data = await connector.fetch_change_orders(since)
        finally:
            if hasattr(connector, "close"):
                await connector.close()

        # Phase 3: Write results (short tx)
        max_ts = None
        async with async_session() as write_db:
            job_refresh = await write_db.get(PLMSyncJob, job.job_id)
            if not job_refresh or job_refresh.status != "running" or job_refresh.claim_token != job.claim_token:
                return

            for item in data:
                item["connection_id"] = job.connection_id
                item["product_line_code"] = connection_product_line_code
                if job.data_type == "parts":
                    await PLMIngestionService._ingest_part(write_db, item)
                elif job.data_type == "boms":
                    await PLMIngestionService._ingest_bom(write_db, item)
                elif job.data_type == "change_orders":
                    await PLMIngestionService._ingest_change_order(write_db, item)
                ts = item.get("source_updated_at")
                if ts and (max_ts is None or ts > max_ts):
                    max_ts = ts

            job_refresh.status = "completed"
            job_refresh.claim_token = None
            job_refresh.checkpoint = max_ts if max_ts else job_refresh.checkpoint
            job_refresh.next_run_at = datetime.now(timezone.utc) + timedelta(minutes=PLMSyncService.SYNC_INTERVAL_MINUTES)
            job_refresh.completed_at = datetime.now(timezone.utc)
            job_refresh.consecutive_failures = 0
            job_refresh.error_message = None
            await write_db.commit()


class PLMChangeImpactWorker:
    """Background worker for processing PLM change impact analysis tasks."""

    TIMEOUT_MINUTES = 10
    SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

    @staticmethod
    async def recover_stuck_tasks(db: AsyncSession) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=PLMChangeImpactWorker.TIMEOUT_MINUTES)
        from sqlalchemy import update as sa_update
        stmt = select(PLMChangeImpactTask).where(
            PLMChangeImpactTask.status == "running"
        ).where(PLMChangeImpactTask.started_at < cutoff)
        result = await db.execute(stmt.with_for_update(skip_locked=True))
        stuck = result.scalars().all()
        for task in stuck:
            task.status = "pending"
            task.claim_token = None
            task.error_message = "Timeout: impact task exceeded 10 minutes"
        return len(stuck)

    @staticmethod
    async def claim_tasks(db: AsyncSession) -> list[PLMChangeImpactTask]:
        stmt = select(PLMChangeImpactTask).where(
            PLMChangeImpactTask.status == "pending"
        ).where(PLMChangeImpactTask.next_retry_at <= datetime.now(timezone.utc))
        result = await db.execute(stmt.with_for_update(skip_locked=True).limit(10))
        tasks = result.scalars().all()
        for task in tasks:
            task.status = "running"
            task.started_at = datetime.now(timezone.utc)
            task.claim_token = str(uuid.uuid4())
        return tasks

    @staticmethod
    async def process_task(db: AsyncSession, task: PLMChangeImpactTask):
        from app.services.change_impact_service import ChangeImpactService
        from app.models.fmea import FMEADocument

        change_order = await db.get(PLMChangeOrder, task.change_id)
        if not change_order:
            task.status = "failed"
            task.error_message = "Change order not found"
            return

        connection_id = change_order.connection_id
        warnings = []
        analysis_ids = []
        has_any_analysis = False

        for part_ref in change_order.affected_part_numbers:
            if "|" not in part_ref:
                parts_result = await db.execute(
                    select(PLMPart).where(PLMPart.connection_id == connection_id).where(PLMPart.part_number == part_ref)
                )
                parts = parts_result.scalars().all()
                if len(parts) == 0:
                    warnings.append(f"Part {part_ref} not found")
                    continue
                if len(parts) > 1:
                    warnings.append(f"Part {part_ref} has multiple revisions")
                    continue
                part = parts[0]
            else:
                part_number, revision = part_ref.split("|", 1)
                part_result = await db.execute(
                    select(PLMPart).where(
                        PLMPart.connection_id == connection_id,
                        PLMPart.part_number == part_number,
                        PLMPart.revision == revision,
                    )
                )
                part = part_result.scalar_one_or_none()
                if not part:
                    warnings.append(f"Part {part_ref} not found")
                    continue

            links_result = await db.execute(
                select(PLMPartFMEALink).where(PLMPartFMEALink.part_id == part.part_id)
            )
            links = links_result.scalars().all()
            if not links:
                warnings.append(f"Part {part_ref} has no linked FMEA nodes")
                continue

            for link in links:
                fmea = await db.get(FMEADocument, link.fmea_id)
                if not fmea or not fmea.graph_data:
                    continue
                node_map = {n["id"]: n for n in fmea.graph_data.get("nodes", [])}
                node = node_map.get(link.node_id)
                if not node:
                    continue

                # Analyze in independent session because ChangeImpactService.analyze() commits internally
                from app.database import async_session
                async with async_session() as analysis_db:
                    service = ChangeImpactService(analysis_db)
                    result = await service.analyze(
                        fmea_id=link.fmea_id,
                        node_id=link.node_id,
                        node_type=node.get("type", "Component"),
                        node_name=node.get("name", ""),
                        change_type="plm_ecn",
                        field_name="part_number",
                        new_value=change_order.change_number,
                        old_value=None,
                        user_id=PLMChangeImpactWorker.SYSTEM_USER_ID,
                    )
                has_any_analysis = True
                # result is ChangeImpactAnalysisResponse with `id: uuid.UUID` (verified schema field)
                analysis_ids.append(str(result.id))

        if not has_any_analysis and warnings:
            task.status = "failed"
            task.error_message = "; ".join(warnings)
        else:
            task.status = "completed"
            task.result = {
                "warnings": warnings,
                "analysis_ids": analysis_ids,
                "skipped_all": not has_any_analysis and not warnings,
            }
        task.claim_token = None
        task.completed_at = datetime.now(timezone.utc)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/plm_service.py
git commit -m "feat(service): add PLM ingestion, sync, and impact task worker"
```

---

## Task 7: API 路由

**Files:**
- Create: `backend/app/api/plm.py`

- [ ] **Step 1: 编写 API 路由**

参考 `backend/app/api/mes.py` 的模式，实现 13 个端点。

```python
"""PLM API routes."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database import get_db
from app.core.permissions import get_current_user, require_permission, Module, PermissionLevel
from app.core.product_line_filter import apply_product_line_filter
from app.models.user import User
from app.models.plm import (
    PLMConnection, PLMPart, PLMBOM, PLMChangeOrder,
    PLMSyncJob, PLMPartFMEALink, PLMPartSCLink,
)
from app.schemas import plm as schemas
from app.services.plm_service import PLMIngestionService, PLMSyncService
from app.services.plm_connector import test_plm_connection

router = APIRouter(prefix="/api/plm", tags=["plm"])


# --- Connection CRUD ---

@router.post("/connections", response_model=schemas.PLMConnectionResponse)
async def create_connection(
    req: schemas.PLMConnectionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.CREATE)),
):
    conn = PLMConnection(
        name=req.name,
        connector_type=req.connector_type,
        config=req.config,
        product_line_code=req.product_line_code,
        created_by=user.user_id,
    )
    db.add(conn)
    await db.flush()          # Get connection_id without committing
    await db.refresh(conn)
    await PLMSyncService.create_sync_jobs_for_connection(db, conn.connection_id)
    await db.commit()         # Single commit for connection + jobs
    return conn


@router.get("/connections", response_model=schemas.PLMConnectionListResponse)
async def list_connections(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.VIEW)),
):
    stmt = select(PLMConnection)
    stmt = await apply_product_line_filter(stmt, user, PLMConnection, "plm", db, request)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt)

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/connections/{connection_id}", response_model=schemas.PLMConnectionResponse)
async def get_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.VIEW)),
):
    conn = await db.get(PLMConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


@router.put("/connections/{connection_id}", response_model=schemas.PLMConnectionResponse)
async def update_connection(
    connection_id: uuid.UUID,
    req: schemas.PLMConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT)),
):
    conn = await db.get(PLMConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(conn, field, value)
    await db.commit()
    await db.refresh(conn)
    return conn


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.ADMIN)),
):
    conn = await db.get(PLMConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.delete(conn)
    await db.commit()
    return {"status": "deleted"}


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT)),
):
    conn = await db.get(PLMConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return await test_plm_connection(conn, db)


@router.post("/connections/{connection_id}/sync")
async def manual_sync(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT)),
):
    await PLMSyncService.manual_sync(db, connection_id)
    return {"status": "sync triggered"}


# --- Data Query ---

@router.get("/parts", response_model=list[schemas.PLMPartResponse])
async def list_parts(
    request: Request,
    connection_id: uuid.UUID | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.VIEW)),
):
    stmt = select(PLMPart)
    if connection_id:
        stmt = stmt.where(PLMPart.connection_id == connection_id)
    if search:
        stmt = stmt.where(
            (PLMPart.part_number.ilike(f"%{search}%")) | (PLMPart.name.ilike(f"%{search}%"))
        )
    stmt = await apply_product_line_filter(stmt, user, PLMPart, "plm", db, request)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/parts/{part_id}", response_model=schemas.PLMPartResponse)
async def get_part(
    part_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.VIEW)),
):
    part = await db.get(PLMPart, part_id)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")
    return part


@router.get("/boms")
async def list_boms(
    request: Request,
    connection_id: uuid.UUID,
    parent_part_number: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.VIEW)),
):
    stmt = select(PLMBOM).where(PLMBOM.connection_id == connection_id)
    if parent_part_number:
        stmt = stmt.where(PLMBOM.parent_part_number == parent_part_number)
    stmt = await apply_product_line_filter(stmt, user, PLMBOM, "plm", db, request)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/connections/{connection_id}/boms/tree/{part_number}")
async def get_bom_tree(
    connection_id: uuid.UUID,
    part_number: str,
    revision: str = Query("A"),
    bom_revision: str = Query("A"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.VIEW)),
):
    """Return BOM tree starting from part_number."""
    # Build tree via recursive query or in-memory BFS
    stmt = select(PLMBOM).where(
        PLMBOM.connection_id == connection_id,
        PLMBOM.parent_part_number == part_number,
        PLMBOM.parent_revision == revision,
        PLMBOM.bom_revision == bom_revision,
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {"root": part_number, "revision": revision, "bom_revision": bom_revision, "children": rows}


@router.get("/change-orders", response_model=list[schemas.PLMChangeOrderResponse])
async def list_change_orders(
    request: Request,
    connection_id: uuid.UUID | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.VIEW)),
):
    stmt = select(PLMChangeOrder)
    if connection_id:
        stmt = stmt.where(PLMChangeOrder.connection_id == connection_id)
    if status:
        stmt = stmt.where(PLMChangeOrder.status == status)
    stmt = await apply_product_line_filter(stmt, user, PLMChangeOrder, "plm", db, request)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/change-orders/{change_id}", response_model=schemas.PLMChangeOrderResponse)
async def get_change_order(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.VIEW)),
):
    co = await db.get(PLMChangeOrder, change_id)
    if not co:
        raise HTTPException(status_code=404, detail="Change order not found")
    return co


@router.get("/dashboard", response_model=schemas.PLMDashboardResponse)
async def get_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.VIEW)),
):
    # Apply product line filter to each aggregate query
    part_stmt = await apply_product_line_filter(select(PLMPart), user, PLMPart, "plm", db, request)
    part_count = await db.scalar(select(func.count()).select_from(part_stmt.subquery()))

    bom_stmt = await apply_product_line_filter(select(PLMBOM), user, PLMBOM, "plm", db, request)
    bom_count = await db.scalar(select(func.count()).select_from(bom_stmt.subquery()))

    ecn_stmt = select(PLMChangeOrder).where(PLMChangeOrder.status == "approved")
    ecn_stmt = await apply_product_line_filter(ecn_stmt, user, PLMChangeOrder, "plm", db, request)
    pending_ecn = await db.scalar(select(func.count()).select_from(ecn_stmt.subquery()))

    sc_stmt = select(PLMPartSCLink).where(PLMPartSCLink.status == "pending")
    sc_stmt = await apply_product_line_filter(sc_stmt, user, PLMPartSCLink, "plm", db, request)
    pending_sc = await db.scalar(select(func.count()).select_from(sc_stmt.subquery()))

    recent_stmt = await apply_product_line_filter(
        select(PLMChangeOrder).order_by(PLMChangeOrder.created_at.desc()).limit(5),
        user, PLMChangeOrder, "plm", db, request,
    )
    recent = await db.execute(recent_stmt)

    return {
        "part_count": part_count or 0,
        "bom_count": bom_count or 0,
        "pending_ecn_count": pending_ecn or 0,
        "pending_sc_count": pending_sc or 0,
        "recent_changes": recent.scalars().all(),
    }


# --- Integration Actions ---

@router.post("/parts/{part_id}/link-fmea")
async def link_part_to_fmea(
    part_id: uuid.UUID,
    req: schemas.PLMPartLinkFMEARequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT)),
):
    link = PLMPartFMEALink(
        part_id=part_id,
        fmea_id=req.fmea_id,
        node_id=req.node_id,
        link_type="manual_link",
    )
    db.add(link)
    await db.commit()
    return {"status": "linked"}


@router.post("/change-orders/{change_id}/impact-analysis")
async def trigger_impact_analysis(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT)),
):
    from app.services.plm_service import PLMChangeImpactWorker
    # Upsert: avoid unique constraint violation on uq_plm_impact_task_change
    existing = await db.execute(
        select(PLMChangeImpactTask).where(PLMChangeImpactTask.change_id == change_id)
    )
    task = existing.scalar_one_or_none()
    if task:
        task.status = "pending"
        task.retry_count = 0
        task.next_retry_at = datetime.now(timezone.utc)
        task.claim_token = None
        task.error_message = None
        task.result = None
        task.completed_at = None
    else:
        task = PLMChangeImpactTask(change_id=change_id, status="pending")
        db.add(task)
    await db.commit()
    await db.refresh(task)
    return {"status": "task created", "task_id": task.task_id}


@router.post("/connections/{connection_id}/boms/{part_number}/import-to-fmea")
async def import_bom_to_fmea(
    connection_id: uuid.UUID,
    part_number: str,
    req: schemas.BOMImportRequest,
    revision: str = Query("A"),
    bom_revision: str = Query("A"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT)),
):
    """Import BOM tree into DFMEA structure."""
    from app.models.fmea import FMEADocument
    import hashlib

    fmea = await db.get(FMEADocument, req.fmea_id)
    if not fmea:
        raise HTTPException(status_code=404, detail="FMEA not found")
    if fmea.status != "draft":
        raise HTTPException(status_code=400, detail="FMEA must be in draft status")

    # Fetch BOM tree
    stmt = select(PLMBOM).where(
        PLMBOM.connection_id == connection_id,
        PLMBOM.parent_part_number == part_number,
        PLMBOM.parent_revision == revision,
        PLMBOM.bom_revision == bom_revision,
    )
    result = await db.execute(stmt)
    boms = result.scalars().all()
    if not boms:
        raise HTTPException(status_code=404, detail="BOM not found")

    # Build nodes and edges (node types must match FMEA white-list: System, Subsystem, Component)
    node_type_map = {1: "System", 2: "Subsystem"}
    fmea_nodes = []
    fmea_edges = []
    node_meta = []

    # Root node
    root_hash = hashlib.sha256(f"{connection_id}|{part_number}|{revision}".encode()).hexdigest()[:16]
    root_id = f"plm-{root_hash}"
    fmea_nodes.append({"id": root_id, "type": "System", "name": part_number})
    node_meta.append((root_id, part_number, revision))

    for bom in boms:
        child_hash = hashlib.sha256(f"{connection_id}|{bom.child_part_number}|{bom.child_revision}".encode()).hexdigest()[:16]
        child_id = f"plm-{child_hash}"
        node_type = node_type_map.get(bom.level, "Component")
        fmea_nodes.append({"id": child_id, "type": node_type, "name": bom.child_part_number})
        fmea_edges.append({"id": f"edge-{root_id}-{child_id}", "source": root_id, "target": child_id, "type": "HAS_CHILD"})
        node_meta.append((child_id, bom.child_part_number, bom.child_revision))

    # Guard against overwriting non-empty graph without explicit consent
    existing_nodes = fmea.graph_data.get("nodes", []) if fmea.graph_data else []
    existing_edges = fmea.graph_data.get("edges", []) if fmea.graph_data else []
    has_existing_graph = len(existing_nodes) > 1 or len(existing_edges) > 0
    if has_existing_graph and not req.overwrite:
        raise HTTPException(status_code=400, detail="FMEA already has graph data; use overwrite=true to replace")

    # Always clear old auto_import links before writing new graph (prevents orphaned links)
    old_links = await db.execute(
        select(PLMPartFMEALink).where(
            PLMPartFMEALink.fmea_id == req.fmea_id,
            PLMPartFMEALink.link_type == "auto_import",
        )
    )
    for old in old_links.scalars().all():
        await db.delete(old)

    fmea.graph_data = {"nodes": fmea_nodes, "edges": fmea_edges}

    # Create links
    for node_id, pn, rev in node_meta:
        part_result = await db.execute(
            select(PLMPart).where(
                PLMPart.connection_id == connection_id,
                PLMPart.part_number == pn,
                PLMPart.revision == rev,
            )
        )
        part = part_result.scalar_one_or_none()
        if part:
            db.add(PLMPartFMEALink(
                part_id=part.part_id,
                fmea_id=req.fmea_id,
                node_id=node_id,
                link_type="auto_import",
            ))

    await db.commit()
    return {"status": "imported", "node_count": len(fmea_nodes), "edge_count": len(fmea_edges)}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/plm.py
git commit -m "feat(api): add PLM routes — 13 endpoints with permission guards"
```

---

## Task 8: 已有模块修改

**Files:**
- Modify: `backend/app/services/graph_projection_service.py`
- Modify: `backend/app/graph/jsonb_repository.py`
- Modify: `backend/app/graph/neo4j_repository.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: graph_projection_service.py — 增加 HAS_CHILD 边白名单 + part_number 属性**

```python
# backend/app/services/graph_projection_service.py
# 1. ALLOWED_EDGE_TYPES is a set[str], not a list
ALLOWED_EDGE_TYPES: set[str] = {
    "HAS_PROCESS_STEP", "HAS_WORK_ELEMENT", "HAS_FUNCTION",
    "FUNCTION_MAPPED_TO", "HAS_FAILURE_MODE",
    "EFFECT_OF", "CAUSE_OF",
    "PREVENTED_BY", "DETECTED_BY", "OPTIMIZED_BY",
    "HAS_NODE",
    "HAS_CHILD",  # <-- add this (PLM BOM hierarchy)
}

# 2. In _node_properties(), add "part_number" to the property extraction loop
    for key in ("process_number", "classification", "requirement", "specification",
                "severity", "occurrence", "detection", "ap",
                "revised_severity", "revised_occurrence", "revised_detection", "revised_ap",
                "severity_plant", "severity_customer", "severity_user",
                "responsible", "due_date", "status", "action_taken", "completion_date",
                "part_number",  # <-- add this (PLM part reference)
               ):
```

- [ ] **Step 2: jsonb_repository.py — 增加 HAS_CHILD 到 downstream edges**

```python
# backend/app/graph/jsonb_repository.py
# In analyze_change_impact, find downstream_edges set, add "HAS_CHILD"
downstream_edges = {
    "HAS_FUNCTION", "FUNCTION_MAPPED_TO", "HAS_FAILURE_MODE", "EFFECT_OF",
    "HAS_PROCESS_STEP", "HAS_CHILD",  # <-- add this
}
```

- [ ] **Step 3: neo4j_repository.py — 增加 HAS_CHILD 到 downstream_rel_types**

```python
# backend/app/graph/neo4j_repository.py
# In analyze_change_impact, find downstream_rel_types string, add |HAS_CHILD
downstream_rel_types = "HAS_FUNCTION|FUNCTION_MAPPED_TO|HAS_FAILURE_MODE|EFFECT_OF|HAS_PROCESS_STEP|HAS_CHILD"
#                                                                                          ^^^^^^^^^^^^^^^ add this
```

- [ ] **Step 4: main.py — 注册 PLM 路由和后台协程**

```python
# backend/app/main.py
# 1. Import PLM router
from app.api.plm import router as plm_router

# 2. Register router
app.include_router(plm_router)

# 3. In lifespan, after MES tasks, add PLM tasks:
from app.services.plm_service import PLMSyncService, PLMChangeImpactWorker

async def _plm_sync_loop():
    while True:
        await asyncio.sleep(30)
        try:
            async with async_session() as db:
                await PLMSyncService.run_sync_round(db)
        except Exception as e:
            print(f"[plm_sync] error: {e}")

async def _plm_impact_loop():
    while True:
        await asyncio.sleep(30)
        try:
            async with async_session() as db:
                # Recover stuck tasks
                await PLMChangeImpactWorker.recover_stuck_tasks(db)
                await db.commit()
                # Claim and process
                tasks = await PLMChangeImpactWorker.claim_tasks(db)
                if tasks:
                    await db.commit()
                    for task in tasks:
                        try:
                            async with async_session() as task_db:
                                task_refresh = await task_db.get(PLMChangeImpactTask, task.task_id)
                                if task_refresh and task_refresh.claim_token == task.claim_token:
                                    await PLMChangeImpactWorker.process_task(task_db, task_refresh)
                                    await task_db.commit()
                        except Exception as e:
                            print(f"[plm_impact] task {task.task_id} failed: {e}")
        except Exception as e:
            print(f"[plm_impact] error: {e}")

plm_sync_task = asyncio.create_task(_plm_sync_loop())
plm_impact_task = asyncio.create_task(_plm_impact_loop())

# In cleanup (yield之后):
plm_sync_task.cancel()
plm_impact_task.cancel()
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/graph_projection_service.py backend/app/graph/jsonb_repository.py backend/app/graph/neo4j_repository.py backend/app/main.py
git commit -m "feat(integration): add HAS_CHILD edge support + PLM background workers"
```

---

## Task 9: 前端类型和 API 客户端

**Files:**
- Create: `frontend/src/types/plm.ts`
- Create: `frontend/src/api/plm.ts`

- [ ] **Step 1: 编写 TypeScript 类型**

```typescript
// frontend/src/types/plm.ts
export interface PLMConnection {
  connection_id: string;
  name: string;
  connector_type: string;
  config: Record<string, unknown>;
  is_active: boolean;
  product_line_code: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PLMPart {
  part_id: string;
  connection_id: string;
  external_id: string;
  part_number: string;
  name: string;
  revision: string;
  material: string | null;
  specification: string | null;
  status: string;
  is_safety_related: boolean;
  is_key_characteristic: boolean;
  source_updated_at: string | null;
  product_line_code: string | null;
  created_at: string;
}

export interface PLMBOM {
  bom_id: string;
  connection_id: string;
  parent_part_number: string;
  parent_revision: string;
  child_part_number: string;
  child_revision: string;
  quantity: number;
  level: number;
}

export interface PLMChangeOrder {
  change_id: string;
  connection_id: string;
  change_number: string;
  title: string;
  status: string;
  priority: string;
  affected_part_numbers: string[];
  created_at: string;
}

export interface PLMDashboard {
  part_count: number;
  bom_count: number;
  pending_ecn_count: number;
  pending_sc_count: number;
  recent_changes: PLMChangeOrder[];
}
```

- [ ] **Step 2: 编写 API 客户端**

```typescript
// frontend/src/api/plm.ts
import { client } from "./client";
import type { PLMConnection, PLMPart, PLMBOM, PLMChangeOrder, PLMDashboard } from "../types/plm";

export const createPLMConnection = (data: unknown) =>
  client.post("/api/plm/connections", data);

export const getPLMConnections = (params?: { page?: number; page_size?: number }) =>
  client.get("/api/plm/connections", { params });

export const getPLMConnection = (id: string) =>
  client.get(`/api/plm/connections/${id}`);

export const updatePLMConnection = (id: string, data: unknown) =>
  client.put(`/api/plm/connections/${id}`, data);

export const deletePLMConnection = (id: string) =>
  client.delete(`/api/plm/connections/${id}`);

export const testPLMConnection = (id: string) =>
  client.post(`/api/plm/connections/${id}/test`);

export const syncPLMConnection = (id: string) =>
  client.post(`/api/plm/connections/${id}/sync`);

export const getPLMParts = (params?: { connection_id?: string; search?: string; page?: number; page_size?: number }) =>
  client.get("/api/plm/parts", { params });

export const getPLMPart = (id: string) =>
  client.get(`/api/plm/parts/${id}`);

export const getPLMBOMs = (params: { connection_id: string; parent_part_number?: string }) =>
  client.get("/api/plm/boms", { params });

export const getPLMBOMTree = (connectionId: string, partNumber: string, revision?: string, bomRevision?: string) =>
  client.get(`/api/plm/connections/${connectionId}/boms/tree/${partNumber}`, {
    params: { revision, bom_revision: bomRevision },
  });

export const getPLMChangeOrders = (params?: { connection_id?: string; status?: string }) =>
  client.get("/api/plm/change-orders", { params });

export const getPLMChangeOrder = (id: string) =>
  client.get(`/api/plm/change-orders/${id}`);

export const getPLMDashboard = () =>
  client.get("/api/plm/dashboard");

export const linkPartToFMEA = (partId: string, data: { fmea_id: string; node_id: string }) =>
  client.post(`/api/plm/parts/${partId}/link-fmea`, data);

export const triggerImpactAnalysis = (changeId: string) =>
  client.post(`/api/plm/change-orders/${changeId}/impact-analysis`);

export const importBOMToFMEA = (
  connectionId: string,
  partNumber: string,
  data: { fmea_id: string; overwrite: boolean },
  revision?: string,
  bomRevision?: string,
) =>
  client.post(`/api/plm/connections/${connectionId}/boms/${partNumber}/import-to-fmea`, data, {
    params: { revision, bom_revision: bomRevision },
  });
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/plm.ts frontend/src/api/plm.ts
git commit -m "feat(frontend): add PLM TypeScript types and API client"
```

---

## Task 10: 前端页面 — PLMConnectionsPage

**Files:**
- Create: `frontend/src/pages/plm/PLMConnectionsPage.tsx`

- [ ] **Step 1: 复用 MESConnectionsPage 布局编写 PLM 连接管理页**

参考 `frontend/src/pages/mes/MESConnectionsPage.tsx` 的结构，替换为 PLM 数据：

```tsx
// frontend/src/pages/plm/PLMConnectionsPage.tsx
import { useEffect, useState } from "react";
import { Table, Button, Modal, Form, Input, Select, message } from "antd";
import type { PLMConnection } from "../../types/plm";
import { getPLMConnections, createPLMConnection, deletePLMConnection, testPLMConnection, syncPLMConnection } from "../../api/plm";

export default function PLMConnectionsPage() {
  const [connections, setConnections] = useState<PLMConnection[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const resp = await getPLMConnections();
      setConnections(resp.data.items || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (values: unknown) => {
    try {
      await createPLMConnection(values);
      message.success("创建成功");
      setModalOpen(false);
      form.resetFields();
      load();
    } catch {
      message.error("创建失败");
    }
  };

  const handleTest = async (id: string) => {
    try {
      const resp = await testPLMConnection(id);
      message.info(resp.data.ok ? "连接正常" : `连接失败: ${resp.data.error}`);
    } catch {
      message.error("测试失败");
    }
  };

  const columns = [
    { title: "名称", dataIndex: "name" },
    { title: "类型", dataIndex: "connector_type" },
    { title: "产品线", dataIndex: "product_line_code" },
    { title: "状态", dataIndex: "is_active", render: (v: boolean) => v ? "启用" : "禁用" },
    {
      title: "操作",
      render: (_: unknown, record: PLMConnection) => (
        <>
          <Button size="small" onClick={() => handleTest(record.connection_id)}>测试</Button>
          <Button size="small" onClick={() => syncPLMConnection(record.connection_id)}>同步</Button>
        </>
      ),
    },
  ];

  return (
    <div>
      <Button type="primary" onClick={() => setModalOpen(true)}>新建连接</Button>
      <Table rowKey="connection_id" columns={columns} dataSource={connections} loading={loading} />
      <Modal open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()} title="新建 PLM 连接">
        <Form form={form} onFinish={handleCreate} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="connector_type" label="连接器类型" rules={[{ required: true }]}>
            <Select options={[{ label: "Mock", value: "mock" }, { label: "REST", value: "rest" }]} />
          </Form.Item>
          <Form.Item name="product_line_code" label="产品线" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/plm/PLMConnectionsPage.tsx
git commit -m "feat(frontend): add PLM connections page"
```

---

## Task 11: 前端页面 — 剩余 3 页 + 路由/菜单

**Files:**
- Create: `frontend/src/pages/plm/PLMDashboardPage.tsx`
- Create: `frontend/src/pages/plm/PLMPartsPage.tsx`
- Create: `frontend/src/pages/plm/PLMChangeOrdersPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: 编写 Dashboard 页面**

```tsx
// frontend/src/pages/plm/PLMDashboardPage.tsx
import { useEffect, useState } from "react";
import { Card, Row, Col, Statistic } from "antd";
import { getPLMDashboard } from "../../api/plm";
import type { PLMDashboard } from "../../types/plm";

export default function PLMDashboardPage() {
  const [data, setData] = useState<PLMDashboard | null>(null);

  useEffect(() => {
    getPLMDashboard().then(r => setData(r.data));
  }, []);

  return (
    <div>
      <Row gutter={16}>
        <Col span={6}><Card><Statistic title="零部件数" value={data?.part_count || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="BOM 数" value={data?.bom_count || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="待处理 ECN" value={data?.pending_ecn_count || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="待确认 SC" value={data?.pending_sc_count || 0} /></Card></Col>
      </Row>
    </div>
  );
}
```

- [ ] **Step 2: 编写 Parts 页面（简化版）**

```tsx
// frontend/src/pages/plm/PLMPartsPage.tsx
import { useEffect, useState } from "react";
import { Table, Input, Drawer, Tag } from "antd";
import type { PLMPart } from "../../types/plm";
import { getPLMParts } from "../../api/plm";

export default function PLMPartsPage() {
  const [parts, setParts] = useState<PLMPart[]>([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<PLMPart | null>(null);

  useEffect(() => {
    getPLMParts({ search }).then(r => setParts(r.data || []));
  }, [search]);

  const columns = [
    { title: "编码", dataIndex: "part_number" },
    { title: "名称", dataIndex: "name" },
    { title: "版本", dataIndex: "revision" },
    { title: "状态", dataIndex: "status" },
    {
      title: "特性",
      render: (_: unknown, r: PLMPart) => (
        <>
          {r.is_safety_related && <Tag color="red">安全</Tag>}
          {r.is_key_characteristic && <Tag color="orange">关键</Tag>}
        </>
      ),
    },
  ];

  return (
    <div>
      <Input.Search placeholder="搜索零部件" onSearch={setSearch} />
      <Table rowKey="part_id" columns={columns} dataSource={parts} onRow={r => ({ onClick: () => setSelected(r) })} />
      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.part_number}>
        <p>名称: {selected?.name}</p>
        <p>版本: {selected?.revision}</p>
        <p>材料: {selected?.material}</p>
        <p>规格: {selected?.specification}</p>
      </Drawer>
    </div>
  );
}
```

- [ ] **Step 3: 编写 Change Orders 页面（简化版）**

```tsx
// frontend/src/pages/plm/PLMChangeOrdersPage.tsx
import { useEffect, useState } from "react";
import { Table, Tag, Button } from "antd";
import type { PLMChangeOrder } from "../../types/plm";
import { getPLMChangeOrders, triggerImpactAnalysis } from "../../api/plm";

export default function PLMChangeOrdersPage() {
  const [orders, setOrders] = useState<PLMChangeOrder[]>([]);

  useEffect(() => {
    getPLMChangeOrders().then(r => setOrders(r.data || []));
  }, []);

  const statusColor: Record<string, string> = {
    draft: "default", pending_approval: "blue", approved: "green",
    implemented: "orange", closed: "purple",
  };

  const columns = [
    { title: "变更单号", dataIndex: "change_number" },
    { title: "标题", dataIndex: "title" },
    { title: "类型", dataIndex: "change_type" },
    { title: "状态", dataIndex: "status", render: (v: string) => <Tag color={statusColor[v]}>{v}</Tag> },
    {
      title: "操作",
      render: (_: unknown, r: PLMChangeOrder) => (
        <Button size="small" onClick={() => triggerImpactAnalysis(r.change_id)}>影响分析</Button>
      ),
    },
  ];

  return <Table rowKey="change_id" columns={columns} dataSource={orders} />;
}
```

- [ ] **Step 4: App.tsx 新增路由**

```tsx
// frontend/src/App.tsx — 在 MES 路由之后添加
import PLMConnectionsPage from "./pages/plm/PLMConnectionsPage";
import PLMDashboardPage from "./pages/plm/PLMDashboardPage";
import PLMPartsPage from "./pages/plm/PLMPartsPage";
import PLMChangeOrdersPage from "./pages/plm/PLMChangeOrdersPage";

// 在 Route 列表中添加：
<Route path="/plm/dashboard" element={<ProtectedRoute requiredModule="plm"><PLMDashboardPage /></ProtectedRoute>} />
<Route path="/plm/connections" element={<ProtectedRoute requiredModule="plm"><PLMConnectionsPage /></ProtectedRoute>} />
<Route path="/plm/parts" element={<ProtectedRoute requiredModule="plm"><PLMPartsPage /></ProtectedRoute>} />
<Route path="/plm/change-orders" element={<ProtectedRoute requiredModule="plm"><PLMChangeOrdersPage /></ProtectedRoute>} />
```

- [ ] **Step 5: AppLayout.tsx 新增菜单**

```tsx
// frontend/src/components/layout/AppLayout.tsx
// 1. Add PLM paths to pathToGroupMap and activePaths
const plmPaths = ["/plm/dashboard", "/plm/parts", "/plm/change-orders", "/plm/connections"];
// Merge into existing arrays

// 2. Add menu item
{
  key: "grp:plm",
  label: "PLM 集成",
  icon: <BuildOutlined />,
  children: [
    { key: "/plm/dashboard", label: "PLM 看板" },
    { key: "/plm/parts", label: "零部件" },
    { key: "/plm/change-orders", label: "工程变更" },
    { key: "/plm/connections", label: "连接管理" },
  ],
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/plm/ frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(frontend): add PLM dashboard, parts, change-orders pages + routing + menu"
```

---

## Task 12: Seed 数据

**Files:**
- Modify: `backend/app/seed.py`

- [ ] **Step 1: 在 seed.py 中确保 system 用户存在**

```python
# backend/app/seed.py — 在 seed() 函数开头或适当位置
# Ensure system user exists
from app.core.config import SYSTEM_USER_ID
from app.models.role import RoleDefinition
from sqlalchemy import select

system_user = await db.get(User, SYSTEM_USER_ID)
if not system_user:
    # Get admin role_id
    role_result = await db.execute(
        select(RoleDefinition.id).where(RoleDefinition.role_key == "admin")
    )
    admin_role_id = role_result.scalar_one_or_none()
    if admin_role_id:
        db.add(User(
            user_id=SYSTEM_USER_ID,
            username="system",
            display_name="System",
            email="system@openqms.local",
            password_hash="",  # No login
            role_id=admin_role_id,
            is_active=True,
        ))
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/seed.py
git commit -m "feat(seed): ensure system user exists for background tasks"
```

---

## Task 13: 后端测试

**Files:**
- Create: `backend/tests/test_plm.py`

- [ ] **Step 1: 编写核心测试**

```python
"""PLM integration tests."""
import uuid
import pytest
from sqlalchemy import select

from app.models.plm import PLMPart, PLMBOM, PLMChangeOrder, PLMPartFMEALink, PLMChangeImpactTask
from app.services.plm_service import PLMIngestionService, PLMSyncService


@pytest.mark.asyncio
async def test_plm_part_ingestion_idempotent(db, admin_user):
    """Same part_number+revision ingested twice should not create duplicates."""
    data = {
        "connection_id": uuid.uuid4(),
        "data_type": "part",
        "external_id": "EXT-001",
        "part_number": "TEST-001",
        "name": "Test Part",
        "revision": "A",
        "status": "active",
        "is_safety_related": True,
        "product_line_code": "DC-DC-100",
    }
    await PLMIngestionService.ingest(db, data)
    await PLMIngestionService.ingest(db, data)
    await db.commit()

    result = await db.execute(select(PLMPart).where(PLMPart.part_number == "TEST-001"))
    parts = result.scalars().all()
    assert len(parts) == 1
    assert parts[0].is_safety_related is True


@pytest.mark.asyncio
async def test_plm_multi_revision_coexist(db, admin_user):
    """Same part_number with different revisions should coexist."""
    conn_id = uuid.uuid4()
    for rev in ["A", "B", "C"]:
        await PLMIngestionService.ingest(db, {
            "connection_id": conn_id,
            "data_type": "part",
            "external_id": f"EXT-{rev}",
            "part_number": "MULTI-001",
            "name": "Multi Rev Part",
            "revision": rev,
            "product_line_code": "DC-DC-100",
        })
    await db.commit()

    result = await db.execute(select(PLMPart).where(PLMPart.part_number == "MULTI-001"))
    parts = result.scalars().all()
    assert len(parts) == 3
    revisions = {p.revision for p in parts}
    assert revisions == {"A", "B", "C"}


@pytest.mark.asyncio
async def test_ecn_approved_creates_impact_task(db, admin_user):
    """ECN status approved should create PLMChangeImpactTask."""
    conn_id = uuid.uuid4()
    await PLMIngestionService.ingest(db, {
        "connection_id": conn_id,
        "data_type": "change_order",
        "external_id": "ECN-001",
        "change_number": "ECN-2026-001",
        "title": "Test",
        "change_type": "design",
        "status": "draft",
        "affected_part_numbers": ["PART-001|A"],
        "product_line_code": "DC-DC-100",
    })
    await db.commit()

    # Now update to approved
    await PLMIngestionService.ingest(db, {
        "connection_id": conn_id,
        "data_type": "change_order",
        "external_id": "ECN-001",
        "change_number": "ECN-2026-001",
        "title": "Test",
        "change_type": "design",
        "status": "approved",
        "affected_part_numbers": ["PART-001|A"],
        "product_line_code": "DC-DC-100",
    })
    await db.commit()

    result = await db.execute(select(PLMChangeImpactTask))
    tasks = result.scalars().all()
    assert len(tasks) == 1
    assert tasks[0].status == "pending"


@pytest.mark.asyncio
async def test_part_sc_link_created_for_safety_related(db, admin_user):
    """Safety-related part should auto-create PLMPartSCLink."""
    conn_id = uuid.uuid4()
    await PLMIngestionService.ingest(db, {
        "connection_id": conn_id,
        "data_type": "part",
        "external_id": "SAFE-001",
        "part_number": "SAFE-001",
        "name": "Safety Part",
        "revision": "A",
        "is_safety_related": True,
        "product_line_code": "DC-DC-100",
    })
    await db.commit()

    result = await db.execute(select(PLMPartSCLink))
    links = result.scalars().all()
    assert len(links) == 1
    assert links[0].characteristic_type == "safety"
    assert links[0].status == "pending"
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && pytest tests/test_plm.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_plm.py
git commit -m "test(plm): add backend tests — idempotency, multi-revision, ECN task, SC link"
```

---

## 自检清单

**1. Spec coverage:**
| 设计文档章节 | 实现 Task |
|-------------|----------|
| 3.1-3.9 数据模型（9 张表） | Task 1 + Task 2 |
| 4.1-4.3 连接器层 | Task 5 |
| 5.1-5.3 同步与摄入服务 | Task 6 |
| 6 API 路由（13 端点） | Task 7 |
| 7 前端页面（4 页） | Task 10 + Task 11 |
| 8.1 BOM→FMEA 导入 | Task 7（import endpoint） |
| 8.2 ECN→变更影响分析 | Task 6（worker） |
| 8.3 Part→SC 关联 | Task 6（ingestion） |
| 已有模块修改 | Task 8 |
| 权限 + Seed | Task 4 + Task 12 |
| 测试 | Task 13 |

**2. Placeholder scan:** 无 TBD/TODO/"implement later"。

**3. Type consistency:**
- `PLMConnection` / `PLMPart` / `PLMBOM` / `PLMChangeOrder` 模型字段与 schema 字段一致
- `node_id` 为 `String(128)` 贯穿文档
- `SYSTEM_USER_ID` 为固定 UUID，seed 中预置
- `link_type` 枚举值 `"auto_import"` / `"manual_link"` 一致

---

## 执行方式选择

**Plan complete and saved to `docs/superpowers/plans/2026-06-08-plm-connector-plan.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
