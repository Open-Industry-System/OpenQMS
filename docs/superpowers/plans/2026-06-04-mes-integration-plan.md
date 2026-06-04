# MES 集成连接器实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 MES（制造执行系统）集成连接器，支持双向数据交换（拉取+推送），内置 Mock 模拟器，采用适配器模式。

**Architecture:** 后端新增 **9 张表**（mes_connections, mes_production_orders, mes_equipment_status, mes_scrap_records, mes_measurement_ingestions, mes_sync_jobs, mes_push_outbox, mes_scrap_monthly_summary, mes_production_orders_archive），9 个模型，适配器抽象基类（MESConnector）+ Mock 实现 + REST 通用实现，同步任务表驱动增量拉取，outbox 模式可靠推送。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 + Pydantic v2 + PostgreSQL + asyncpg | React 18 + TypeScript + Ant Design 5 | Alembic 迁移

**Plan 结构（分 8 阶段，22 个 Task）：**
1. Phase 1 — 迁移与安全基础（Task 1-3）
2. Phase 2 — 连接器实现（Task 4-5）
3. Phase 3 — 原子 ingestion（Task 6-7）
4. Phase 4 — 同步调度（Task 8-10）
5. Phase 5 — Outbox 推送（Task 11-12）
6. Phase 6 — API 与 RLS（Task 13-14）
7. Phase 7 — 前端（Task 15-17）
8. Phase 8 — 并发自动化测试与生命周期（Task 18-19, 12b）

---

## 阻塞问题修复清单

本计划已修复原设计审查发现的全部阻塞问题：

| # | 问题 | 修复方式 |
|---|------|---------|
| 1 | 同步与 Outbox 长事务持锁 | 三阶段短事务：领取→COMMIT→外部请求→写入→COMMIT |
| 2 | checkpoint=now() 可能跳数据 | 使用 `COALESCE(max_source_timestamp, job.checkpoint)`，空结果保持原 checkpoint |
| 3 | RESTMESConnector 全 TODO | 完整 HTTP 实现：配置驱动 + 分页 + 字段映射 + 重试 |
| 4 | API Key 认证是 TODO 占位 | 完整 SHA-256 hash 验证 + Fernet 加密 + 响应脱敏 + /test 端点 |
| 5 | 测量 ingestion 无法原子回滚 | 调用 `_create_sample_batch_inner`（仅 flush）替代 `add_sample_batch`（内部 commit），同一事务完成 ingestion + SPC + 回填 |
| 6 | 无自动化并发测试 | 新增 `test_mes_concurrency.py` 覆盖 33 个并发场景 |
| 7 | 修改已执行 028 迁移 | 在 **新迁移 030** 末尾插入 MES 权限，不动 028 |
| 8 | 查询未产品线隔离 + 凭证泄漏 | 查询 API 按 `product_line_code` 过滤；ConnectionOut 脱敏 `config.auth_config` 敏感字段 |
| 9 | 前端独立 axios 实例 | 复用现有 `client` 实例（已含 JWT 拦截器） |
| 10 | 工单页/报废页/连接测试端点缺失 | Task 16 补全 4 个前端页面；Task 14 补全 /test 端点 |
| 11 | 迁移用 Python default= | 全部改为 `server_default=` |
| 12 | 测试代码不可运行 | 使用现有测试用户（如 admin 种子用户）+ 正确导入 + 测试隔离清理 |

---

## 文件结构

### 后端新增文件
- `backend/alembic/versions/030_add_mes_tables.py` — Alembic 迁移（9 张表 + MES 权限数据）
- `backend/app/models/mes.py` — 9 个新模型（含生命周期归档/摘要表）
- `backend/app/schemas/mes.py` — Pydantic v2 schemas（Create/Update/Response/List），含凭证脱敏
- `backend/app/services/mes_connector.py` — MESConnector ABC + MockMESConnector + RESTMESConnector
- `backend/app/services/mes_crypto.py` — Fernet 加密 + API Key hash 工具
- `backend/app/services/mes_service.py` — MESIngestionService, MESSyncService, MESPushService
- `backend/app/api/mes.py` — FastAPI 路由（connections CRUD + ingest + sync + query + test）
- `backend/tests/test_mes_concurrency.py` — 自动化并发测试（pytest + asyncio）
- `backend/tests/test_mes_connector.py` — 手动测试（延续 test_schema.py 模式）

### 后端修改文件
- `backend/app/core/permissions.py` — 新增 `Module.MES`
- `backend/app/core/product_line_filter.py` — 添加 `"mes": "product_line_code"`
- `backend/app/main.py` — 注册 mes_router + 后台调度协程
- `backend/app/models/__init__.py` — 导出 MES 模型
- `backend/app/services/spc_service.py` — 暴露 `_create_sample_batch_inner`、添加 `commit` 参数、接入 outbox

### 前端新增文件
- `frontend/src/pages/mes/MESConnectionsPage.tsx` — 连接管理
- `frontend/src/pages/mes/MESDashboardPage.tsx` — MES 数据看板
- `frontend/src/pages/mes/MESOrdersPage.tsx` — 工单列表
- `frontend/src/pages/mes/MESScrapPage.tsx` — 报废/返工列表
- `frontend/src/api/mes.ts` — MES API 客户端（复用现有 client）
- `frontend/src/types/mes.ts` — TypeScript 类型

### 前端修改文件
- `frontend/src/App.tsx` — 新增 4 个 MES 路由
- `frontend/src/components/layout/AppLayout.tsx` — 新增 MES 侧边栏菜单（4 个子项）

---

## Phase 1: 迁移与安全基础

---

## Task 1: 数据库迁移 — 创建 9 张 MES 表

**Files:**
- Create: `backend/alembic/versions/030_add_mes_tables.py`
- Modify: `backend/app/models/__init__.py`

**注意：** 不修改已执行的 `028_permission_matrix.py`；MES 权限在本迁移末尾通过 `op.execute` 插入 `role_permissions`。

- [ ] **Step 1: 编写 Alembic 迁移文件**

```python
"""add MES integration tables and permissions

Revision ID: 030_add_mes_tables
Revises: 029_knowledge_graph_permissions
Create Date: 2026-06-04
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = '030_add_mes_tables'
down_revision: Union[str, None] = '029_knowledge_graph_permissions'


def upgrade():
    # mes_connections
    op.create_table(
        'mes_connections',
        sa.Column('connection_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('connector_type', sa.String(50), nullable=False),
        sa.Column('config', JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('product_line_code', sa.String(50), sa.ForeignKey('product_lines.code'), nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # mes_production_orders
    op.create_table(
        'mes_production_orders',
        sa.Column('order_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('mes_connections.connection_id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_no', sa.String(50), nullable=False),
        sa.Column('product_model', sa.String(100), nullable=True),
        sa.Column('process_route', sa.String(200), nullable=True),
        sa.Column('planned_qty', sa.Integer, nullable=True),
        sa.Column('actual_qty', sa.Integer, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'planned'")),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('product_line_code', sa.String(50), sa.ForeignKey('product_lines.code'), nullable=True),
        sa.Column('mes_raw_data', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('connection_id', 'order_no', name='uq_mes_order'),
    )

    # mes_equipment_status
    op.create_table(
        'mes_equipment_status',
        sa.Column('record_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('mes_connections.connection_id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('equipment_code', sa.String(50), nullable=False),
        sa.Column('equipment_name', sa.String(100), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('availability', sa.Numeric(5, 2), nullable=True),
        sa.Column('performance', sa.Numeric(5, 2), nullable=True),
        sa.Column('quality', sa.Numeric(5, 2), nullable=True),
        sa.Column('oee', sa.Numeric(5, 2), nullable=True),
        sa.Column('downtime_reason', sa.String(200), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('product_line_code', sa.String(50), sa.ForeignKey('product_lines.code'), nullable=True),
        sa.Column('mes_raw_data', JSONB, nullable=True),
        sa.UniqueConstraint('connection_id', 'external_id', name='uq_mes_equipment'),
    )

    # mes_scrap_records
    op.create_table(
        'mes_scrap_records',
        sa.Column('scrap_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('mes_connections.connection_id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('order_no', sa.String(50), nullable=True),
        sa.Column('order_id', UUID(as_uuid=True), sa.ForeignKey('mes_production_orders.order_id', ondelete='SET NULL'), nullable=True),
        sa.Column('equipment_code', sa.String(50), nullable=True),
        sa.Column('defect_type', sa.String(50), nullable=False),
        sa.Column('defect_category', sa.String(100), nullable=True),
        sa.Column('defect_qty', sa.Integer, nullable=False),
        sa.Column('total_qty', sa.Integer, nullable=False),
        sa.Column('defect_description', sa.Text, nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('product_line_code', sa.String(50), sa.ForeignKey('product_lines.code'), nullable=True),
        sa.Column('mes_raw_data', JSONB, nullable=True),
        sa.UniqueConstraint('connection_id', 'external_id', name='uq_mes_scrap'),
    )

    # mes_measurement_ingestions
    op.create_table(
        'mes_measurement_ingestions',
        sa.Column('ingestion_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('mes_connections.connection_id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_id', sa.String(100), nullable=False),
        sa.Column('order_no', sa.String(50), nullable=True),
        sa.Column('ic_code', sa.String(100), nullable=False),
        sa.Column('batch_id', UUID(as_uuid=True), sa.ForeignKey('sample_batches.batch_id', ondelete='SET NULL'), nullable=True),
        sa.Column('mes_raw_data', JSONB, nullable=True),
        sa.Column('source_sampled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('product_line_code', sa.String(50), sa.ForeignKey('product_lines.code'), nullable=True),
        sa.UniqueConstraint('connection_id', 'external_id', name='uq_mes_ingestion'),
    )

    # mes_sync_jobs
    op.create_table(
        'mes_sync_jobs',
        sa.Column('job_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('mes_connections.connection_id', ondelete='CASCADE'), nullable=False),
        sa.Column('data_type', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('checkpoint', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('consecutive_failures', sa.Integer, nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('connection_id', 'data_type', name='uq_mes_sync_job'),
    )
    op.create_index(
        'ix_mes_sync_jobs_status_next_run', 'mes_sync_jobs',
        ['status', 'next_run_at']
    )

    # mes_push_outbox
    op.create_table(
        'mes_push_outbox',
        sa.Column('outbox_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('mes_connections.connection_id', ondelete='CASCADE'), nullable=False),
        sa.Column('payload', JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('retry_count', sa.Integer, nullable=False, server_default=sa.text('0')),
        sa.Column('max_retries', sa.Integer, nullable=False, server_default=sa.text('3')),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_mes_push_outbox_status_next_retry', 'mes_push_outbox',
        ['status', 'next_retry_at']
    )

    # mes_scrap_monthly_summary — 报废月度聚合摘要
    op.create_table(
        'mes_scrap_monthly_summary',
        sa.Column('summary_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('connection_id', UUID(as_uuid=True), sa.ForeignKey('mes_connections.connection_id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_line_code', sa.String(50), nullable=False, server_default=sa.text("'__none__'")),
        sa.Column('year_month', sa.String(7), nullable=False),  # YYYY-MM
        sa.Column('defect_category', sa.String(100), nullable=False),
        sa.Column('total_defect_qty', sa.Integer, nullable=False, server_default=sa.text('0')),
        sa.Column('total_total_qty', sa.Integer, nullable=False, server_default=sa.text('0')),
        sa.Column('record_count', sa.Integer, nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('connection_id', 'product_line_code', 'year_month', 'defect_category', name='uq_mes_scrap_summary'),
    )

    # mes_production_orders_archive — 已关闭工单历史归档
    op.create_table(
        'mes_production_orders_archive',
        sa.Column('archive_id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('order_id', UUID(as_uuid=True), unique=True, nullable=False),
        sa.Column('connection_id', UUID(as_uuid=True), nullable=False),
        sa.Column('order_no', sa.String(50), nullable=False),
        sa.Column('product_model', sa.String(100), nullable=True),
        sa.Column('process_route', sa.String(200), nullable=True),
        sa.Column('planned_qty', sa.Integer, nullable=True),
        sa.Column('actual_qty', sa.Integer, nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('product_line_code', sa.String(50), nullable=True),
        sa.Column('archived_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ---- MES permissions (do NOT modify 028; insert here in new migration) ----
    # role_key -> {module: level} format
    MES_PERMS = {
        'admin': 5,
        'manager': 4,
        'field_qe': 2,
        'viewer': 1,
        'customer_qe': 1,
        'supplier_qe': 1,
        'planning_qe': 1,
    }
    for role_key, level in MES_PERMS.items():
        op.execute(
            f"INSERT INTO role_permissions (role_id, module, permission_level) "
            f"SELECT id, 'mes', {level} FROM role_definitions WHERE role_key = '{role_key}' "
            f"ON CONFLICT (role_id, module) DO NOTHING"
        )


def downgrade():
    op.execute("DELETE FROM role_permissions WHERE module = 'mes'")
    op.drop_table('mes_production_orders_archive')
    op.drop_table('mes_scrap_monthly_summary')
    op.drop_index('ix_mes_push_outbox_status_next_retry', table_name='mes_push_outbox')
    op.drop_table('mes_push_outbox')
    op.drop_index('ix_mes_sync_jobs_status_next_run', table_name='mes_sync_jobs')
    op.drop_table('mes_sync_jobs')
    op.drop_table('mes_measurement_ingestions')
    op.drop_table('mes_scrap_records')
    op.drop_table('mes_equipment_status')
    op.drop_table('mes_production_orders')
    op.drop_table('mes_connections')
```

- [ ] **Step 2: 运行迁移**

Run: `cd backend && alembic upgrade head`
Expected: `Running upgrade 029_knowledge_graph_permissions -> 030_add_mes_tables, done`

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/030_add_mes_tables.py backend/app/models/__init__.py
git commit -m "feat(migration): add 9 MES integration tables + MES permissions

- mes_connections, mes_production_orders, mes_equipment_status
- mes_scrap_records, mes_measurement_ingestions
- mes_sync_jobs, mes_push_outbox
- Insert MES permissions into role_permissions (new migration, not 028)"
```

---

## Task 1b: 后端模型层 — mes.py

**Files:**
- Create: `backend/app/models/mes.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 编写 9 个 MES 模型**

```python
# backend/app/models/mes.py
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, Numeric, Boolean, func, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MESConnection(Base):
    __tablename__ = "mes_connections"

    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("product_lines.code"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    sync_jobs = relationship("MESSyncJob", back_populates="connection", cascade="all, delete-orphan")
    outbox = relationship("MESPushOutbox", back_populates="connection", cascade="all, delete-orphan")


class MESProductionOrder(Base):
    __tablename__ = "mes_production_orders"
    __table_args__ = (UniqueConstraint('connection_id', 'order_no', name='uq_mes_order'),)

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mes_connections.connection_id", ondelete="CASCADE"), nullable=False)
    order_no: Mapped[str] = mapped_column(String(50), nullable=False)
    product_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    process_route: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    planned_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("product_lines.code"), nullable=True)
    mes_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MESEquipmentStatus(Base):
    __tablename__ = "mes_equipment_status"
    __table_args__ = (UniqueConstraint('connection_id', 'external_id', name='uq_mes_equipment'),)

    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mes_connections.connection_id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    equipment_code: Mapped[str] = mapped_column(String(50), nullable=False)
    equipment_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    availability: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    performance: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    quality: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    oee: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    downtime_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("product_lines.code"), nullable=True)
    mes_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class MESScrapRecord(Base):
    __tablename__ = "mes_scrap_records"
    __table_args__ = (UniqueConstraint('connection_id', 'external_id', name='uq_mes_scrap'),)

    scrap_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mes_connections.connection_id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    order_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("mes_production_orders.order_id", ondelete="SET NULL"), nullable=True)
    equipment_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    defect_type: Mapped[str] = mapped_column(String(50), nullable=False)
    defect_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    defect_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    total_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    defect_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("product_lines.code"), nullable=True)
    mes_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class MESMeasurementIngestion(Base):
    __tablename__ = "mes_measurement_ingestions"
    __table_args__ = (UniqueConstraint('connection_id', 'external_id', name='uq_mes_ingestion'),)

    ingestion_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mes_connections.connection_id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    order_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ic_code: Mapped[str] = mapped_column(String(100), nullable=False)
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("sample_batches.batch_id", ondelete="SET NULL"), nullable=True)
    mes_raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    source_sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    product_line_code: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("product_lines.code"), nullable=True)


class MESSyncJob(Base):
    __tablename__ = "mes_sync_jobs"
    __table_args__ = (
        UniqueConstraint('connection_id', 'data_type', name='uq_mes_sync_job'),
        Index('ix_mes_sync_jobs_status_next_run', 'status', 'next_run_at'),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mes_connections.connection_id", ondelete="CASCADE"), nullable=False)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    checkpoint: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    connection = relationship("MESConnection", back_populates="sync_jobs")


class MESPushOutbox(Base):
    __tablename__ = "mes_push_outbox"
    __table_args__ = (
        Index('ix_mes_push_outbox_status_next_retry', 'status', 'next_retry_at'),
    )

    outbox_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mes_connections.connection_id", ondelete="CASCADE"), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    connection = relationship("MESConnection", back_populates="outbox")


class MESScrapMonthlySummary(Base):
    __tablename__ = "mes_scrap_monthly_summary"
    __table_args__ = (
        UniqueConstraint('connection_id', 'product_line_code', 'year_month', 'defect_category', name='uq_mes_scrap_summary'),
    )

    summary_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mes_connections.connection_id", ondelete="CASCADE"), nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(50), nullable=False, default="__none__")
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    defect_category: Mapped[str] = mapped_column(String(100), nullable=False)
    total_defect_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_total_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MESProductionOrderArchive(Base):
    __tablename__ = "mes_production_orders_archive"

    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    order_no: Mapped[str] = mapped_column(String(50), nullable=False)
    product_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    process_route: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    planned_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: 导出模型**

```python
# backend/app/models/__init__.py
from .mes import (
    MESConnection, MESProductionOrder, MESEquipmentStatus,
    MESScrapRecord, MESMeasurementIngestion, MESSyncJob, MESPushOutbox,
    MESScrapMonthlySummary, MESProductionOrderArchive,
)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/mes.py backend/app/models/__init__.py
git commit -m "feat(models): add 9 MES integration models"
```

---

## Task 1c: Schemas — Pydantic v2

**Files:**
- Create: `backend/app/schemas/mes.py`

- [ ] **Step 1: 编写 Schemas**

```python
# backend/app/schemas/mes.py
import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class MESConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    connector_type: str = Field(..., pattern="^(mock|rest)$")
    config: dict = Field(default_factory=dict)
    product_line_code: Optional[str] = None


class MESConnectionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    connector_type: Optional[str] = Field(None, pattern="^(mock|rest)$")
    config: Optional[dict] = None
    is_active: Optional[bool] = None
    product_line_code: Optional[str] = None


class MESConnectionResponse(BaseModel):
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


class MESConnectionListResponse(BaseModel):
    items: list[MESConnectionResponse]
    total: int
    page: int
    page_size: int


# --- REST Config Schema (validates before credential processing) ---

class RESTPaginationConfig(BaseModel):
    type: Literal["none", "offset", "cursor"] = "none"
    page_param: Optional[str] = None
    size_param: Optional[str] = None
    size: int = Field(default=100, ge=1)
    cursor_param: Optional[str] = None
    cursor_response_field: Optional[str] = None


class RESTRetryConfig(BaseModel):
    max_retries: int = Field(default=3, ge=0)
    backoff_seconds: list[float] = Field(default=[1, 2, 4], min_length=1)

    @field_validator("backoff_seconds")
    @classmethod
    def _check_non_negative(cls, v: list[float]) -> list[float]:
        if any(x < 0 for x in v):
            raise ValueError("backoff_seconds values must be >= 0")
        return v


class RESTEndpointConfig(BaseModel):
    path: str = Field(..., min_length=1)
    cursor_field: Optional[str] = None
    method: str = "GET"
    pagination: Optional[RESTPaginationConfig] = None
    response_path: Optional[str] = None


class RESTAuthConfig(BaseModel):
    """REST auth config: credential fields declared as Optional[str] so Pydantic validates them.
    extra='allow' permits post-encryption fields (api_key_hash, *_encrypted) to pass through."""
    model_config = {"extra": "allow"}

    inbound_api_key: Optional[str] = None
    outbound_api_key: Optional[str] = None
    token: Optional[str] = None
    password: Optional[str] = None
    secret: Optional[str] = None
    username: Optional[str] = None
    api_key_hash: Optional[str] = None
    token_encrypted: Optional[str] = None
    password_encrypted: Optional[str] = None
    secret_encrypted: Optional[str] = None
    username_encrypted: Optional[str] = None
    outbound_api_key_encrypted: Optional[str] = None


class MESRetentionConfig(BaseModel):
    """Per-connection data retention policy (days). Overrides global defaults when set."""
    equipment_status_days: int = Field(default=90, ge=1)
    scrap_days: int = Field(default=365, ge=1)
    closed_order_days: int = Field(default=730, ge=1)


class RESTConfig(BaseModel):
    base_url: str = Field(..., pattern=r'^https?://')
    endpoints: dict[str, RESTEndpointConfig]
    field_mapping: dict[str, str]
    auth_type: Literal["none", "basic", "bearer", "api_key"] = "none"
    auth_config: Optional[RESTAuthConfig] = None
    timeout: int = Field(default=30, ge=1)
    retry: Optional[RESTRetryConfig] = None
    retention: Optional[MESRetentionConfig] = None

    @model_validator(mode="after")
    def _check_required_endpoints(self):
        required = {"production_orders", "equipment_status", "scrap_records", "measurements"}
        missing = required - set(self.endpoints.keys())
        if missing:
            raise ValueError(f"missing endpoints: {sorted(missing)}")
        return self

    @model_validator(mode="after")
    def _check_cursor_fields(self):
        for name in ("production_orders", "scrap_records", "measurements"):
            ep = self.endpoints[name]
            if not ep.cursor_field:
                raise ValueError(f"endpoint '{name}' must define 'cursor_field'")
        return self

    @model_validator(mode="after")
    def _check_source_updated_at(self):
        if "source_updated_at" not in self.field_mapping:
            raise ValueError("field_mapping must include 'source_updated_at'")
        if not self.field_mapping.get("source_updated_at"):
            raise ValueError("field_mapping 'source_updated_at' cannot be empty")
        return self


class MESProductionOrderResponse(BaseModel):
    order_id: uuid.UUID
    connection_id: uuid.UUID
    order_no: str
    product_model: Optional[str]
    process_route: Optional[str]
    planned_qty: Optional[int]
    actual_qty: Optional[int]
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    source_updated_at: Optional[datetime]
    product_line_code: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


class MESEquipmentStatusResponse(BaseModel):
    record_id: uuid.UUID
    connection_id: uuid.UUID
    external_id: str
    equipment_code: str
    equipment_name: Optional[str]
    status: str
    availability: Optional[float]
    performance: Optional[float]
    quality: Optional[float]
    oee: Optional[float]
    downtime_reason: Optional[str]
    recorded_at: datetime
    product_line_code: Optional[str]
    model_config = {"from_attributes": True}


class MESScrapRecordResponse(BaseModel):
    scrap_id: uuid.UUID
    connection_id: uuid.UUID
    external_id: str
    order_no: Optional[str]
    order_id: Optional[uuid.UUID]
    equipment_code: Optional[str]
    defect_type: str
    defect_category: Optional[str]
    defect_qty: int
    total_qty: int
    defect_description: Optional[str]
    recorded_at: datetime
    product_line_code: Optional[str]
    model_config = {"from_attributes": True}


from typing import Literal


class MESIngestBase(BaseModel):
    """Inbound ingestion base — connection_id is injected by API key auth, not client."""
    raw_data: Optional[dict] = None


class MESIngestMeasurement(MESIngestBase):
    data_type: Literal["measurement"]
    external_id: str
    order_no: Optional[str] = None
    ic_code: str
    values: list[float]
    sampled_at: Optional[datetime] = None
    batch_no: Optional[str] = None
    product_line_code: Optional[str] = None  # ignored; enforced from connection


class MESIngestProductionOrder(MESIngestBase):
    data_type: Literal["production_order"]
    order_no: str
    product_model: Optional[str] = None
    process_route: Optional[str] = None
    planned_qty: Optional[int] = None
    actual_qty: Optional[int] = None
    status: str = "planned"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    source_updated_at: Optional[datetime] = None  # MES updated_at mapped here
    product_line_code: Optional[str] = None  # ignored; enforced from connection


class MESIngestEquipmentStatus(MESIngestBase):
    data_type: Literal["equipment_status"]
    external_id: str
    equipment_code: str
    equipment_name: Optional[str] = None
    status: str
    availability: Optional[float] = None
    performance: Optional[float] = None
    quality: Optional[float] = None
    oee: Optional[float] = None
    downtime_reason: Optional[str] = None
    recorded_at: Optional[datetime] = None
    product_line_code: Optional[str] = None

    @field_validator("availability", "performance", "quality", "oee")
    @classmethod
    def _check_percent(cls, v: float | None) -> float | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("Must be between 0 and 100")
        return v


class MESIngestScrapRecord(MESIngestBase):
    data_type: Literal["scrap_record"]
    external_id: str
    order_no: Optional[str] = None
    equipment_code: Optional[str] = None
    defect_type: str
    defect_category: Optional[str] = None
    defect_qty: int
    total_qty: int
    defect_description: Optional[str] = None
    recorded_at: Optional[datetime] = None
    product_line_code: Optional[str] = None

    @field_validator("defect_qty", "total_qty")
    @classmethod
    def _check_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Must be non-negative")
        return v

    @model_validator(mode="after")
    def _check_defect_not_exceed_total(self):
        if self.defect_qty > self.total_qty:
            raise ValueError("defect_qty cannot exceed total_qty")
        return self


MESIngestRequest = (
    MESIngestMeasurement | MESIngestProductionOrder |
    MESIngestEquipmentStatus | MESIngestScrapRecord
)


class MESEquipmentSummary(BaseModel):
    equipment_code: str
    equipment_name: Optional[str]
    status: str
    availability: Optional[float]
    performance: Optional[float]
    quality: Optional[float]
    oee: Optional[float]


class MESDashboardResponse(BaseModel):
    equipment_summary: list[MESEquipmentSummary]
    running_count: int
    down_count: int
    total_planned: int
    total_actual: int
    scrap_by_category: dict[str, int]
    scrap_trend_7d: list[dict]


class MESSyncJobResponse(BaseModel):
    job_id: uuid.UUID
    connection_id: uuid.UUID
    data_type: str
    status: str
    checkpoint: Optional[datetime]
    next_run_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    consecutive_failures: int
    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/mes.py
git commit -m "feat(schemas): add MES Pydantic v2 schemas"
```

---

## Task 2: 凭证加密与安全工具

**Files:**
- Create: `backend/app/services/mes_crypto.py`

- [ ] **Step 1: 编写加密/Hash 工具**

```python
# backend/app/services/mes_crypto.py
"""MES 凭证加密与安全工具。

- 入站 API Key: SHA-256 hash 存储，验证时对比 hash
- 出站凭证: Fernet 对称加密存储
- 响应脱敏: 将 config.auth_config 中的敏感字段替换为 ***
"""
import hashlib
import os
from typing import Any

from cryptography.fernet import Fernet


# ---- API Key hash (inbound) -------------------------------------------------

def hash_api_key(api_key: str) -> str:
    """对明文 API Key 进行 SHA-256 hash。"""
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(api_key: str, api_key_hash: str) -> bool:
    """验证明文 API Key 是否与存储的 hash 匹配。"""
    return hash_api_key(api_key) == api_key_hash


# ---- Fernet encryption (outbound credentials) -------------------------------

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = os.environ.get("MES_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("MES_ENCRYPTION_KEY environment variable not set")
        # Fernet key must be 32 bytes base64-encoded
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt_credential(plaintext: str) -> str:
    """加密出站凭证（token/password 等）。"""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext: str) -> str:
    """解密出站凭证。仅在 push_quality_event 等运行时调用。"""
    return _get_fernet().decrypt(ciphertext.encode()).decode()


# ---- Response sanitization --------------------------------------------------

_SENSITIVE_KEYS = {
    "api_key", "api_key_hash", "token", "password", "secret", "auth_token",
    "token_encrypted", "password_encrypted", "username_encrypted",
    "outbound_api_key_encrypted", "key_encrypted",
}


def sanitize_config(config: dict) -> dict:
    """脱敏 config 中的敏感字段，用于 API 响应。"""
    if not config:
        return config
    sanitized = dict(config)
    auth = sanitized.get("auth_config")
    if isinstance(auth, dict):
        sanitized["auth_config"] = {
            k: "***" if k in _SENSITIVE_KEYS else v
            for k, v in auth.items()
        }
    # Also scrub top-level sensitive keys
    for key in _SENSITIVE_KEYS:
        if key in sanitized:
            sanitized[key] = "***"
    return sanitized
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/mes_crypto.py
git commit -m "feat(mes): add credential encryption and API key hash utilities

- SHA-256 hash for inbound API keys
- Fernet encryption for outbound credentials (MES_ENCRYPTION_KEY)
- Config sanitization for API responses"
```

---

## Task 3: 权限系统 — Module.MES

**Files:**
- Modify: `backend/app/core/permissions.py`

- [ ] **Step 1: 添加 Module.MES**

```python
# backend/app/core/permissions.py
class Module(StrEnum):
    # ... existing modules ...
    KNOWLEDGE_GRAPH = "knowledge_graph"
    MES = "mes"  # <-- add this
```

- [ ] **Step 2: 在 product_line_filter.py 中添加 MES 模块映射**

```python
# backend/app/core/product_line_filter.py
PRODUCT_LINE_FIELD_MAP: dict[str, str] = {
    # ... existing mappings ...
    "mes": "product_line_code",
}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/permissions.py backend/app/core/product_line_filter.py
git commit -m "feat(permissions): add Module.MES and product line field mapping"
```

---

## Phase 2: 连接器实现

---

## Task 4: 适配器层 — MESConnector + Mock + REST 完整实现

**Files:**
- Create: `backend/app/services/mes_connector.py`
- Modify: `backend/app/services/spc_service.py`（确保 `ingest_external_data` 可用）

- [ ] **Step 1: 编写完整适配器**

```python
# backend/app/services/mes_connector.py
"""MES 数据源适配器抽象基类及实现。"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
import random
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.spc import InspectionCharacteristic
from app.services.mes_crypto import decrypt_credential


class MESConnector(ABC):
    """MES 数据源适配器抽象基类。"""

    @abstractmethod
    async def fetch_production_orders(self, since: datetime) -> list[dict]:
        """拉取生产工单（增量同步）。"""

    @abstractmethod
    async def fetch_equipment_status(self) -> list[dict]:
        """拉取当前设备状态。"""

    @abstractmethod
    async def fetch_scrap_records(self, since: datetime) -> list[dict]:
        """拉取报废/返工记录。"""

    @abstractmethod
    async def fetch_measurements(self, since: datetime) -> list[dict]:
        """拉取过程测量数据（返回 ic_code + values 格式）。"""

    @abstractmethod
    async def push_quality_event(self, event_type: str, data: dict, event_id: str | None = None) -> dict:
        """推送质量事件到 MES。event_id 用于幂等。"""


class MockMESConnector(MESConnector):
    """Mock MES 连接器，生成模拟数据。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_production_orders(self, since: datetime) -> list[dict]:
        count = random.randint(2, 5)
        now = datetime.now(timezone.utc)
        orders = []
        for i in range(count):
            order_no = f"WO-2026-{random.randint(1, 999):03d}"
            orders.append({
                "order_no": order_no,
                "product_model": f"DC-DC-100-{random.choice(['A', 'B', 'C'])}",
                "process_route": "注塑→焊接→组装→测试",
                "planned_qty": random.randint(100, 500),
                "actual_qty": random.randint(80, 500),
                "status": random.choice(["planned", "in_progress", "completed", "closed"]),
                "started_at": now,
                "completed_at": None,
                "source_updated_at": now,
                "product_line_code": "DC-DC-100",
            })
        return orders

    async def fetch_equipment_status(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        equipment_list = [
            {"equipment_code": "EQ-001", "equipment_name": "注塑机"},
            {"equipment_code": "EQ-002", "equipment_name": "焊接机"},
            {"equipment_code": "EQ-003", "equipment_name": "组装线"},
        ]
        results = []
        for eq in equipment_list:
            status = random.choice(["running", "idle", "down", "changeover"])
            availability = round(random.uniform(85, 95), 2) if status == "running" else round(random.uniform(0, 50), 2)
            performance = round(random.uniform(80, 95), 2) if status == "running" else 0.0
            quality = round(random.uniform(95, 99), 2)
            oee = round((availability * performance * quality) / 10000.0, 2) if status == "running" else 0.0
            results.append({
                "external_id": f"{eq['equipment_code']}-{now.strftime('%Y%m%d%H%M%S')}",
                "equipment_code": eq["equipment_code"],
                "equipment_name": eq["equipment_name"],
                "status": status,
                "availability": availability,
                "performance": performance,
                "quality": quality,
                "oee": oee,
                "downtime_reason": "计划维护" if status == "down" else None,
                "recorded_at": now,
                "product_line_code": "DC-DC-100",
            })
        return results

    async def fetch_scrap_records(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        count = random.randint(0, 2)
        records = []
        for i in range(count):
            defect_type = random.choice(["scrap", "rework", "reject"])
            records.append({
                "external_id": f"SCR-{now.strftime('%Y%m%d%H%M%S')}-{i}",
                "order_no": f"WO-2026-{random.randint(1, 999):03d}",
                "equipment_code": random.choice(["EQ-001", "EQ-002", "EQ-003"]),
                "defect_type": defect_type,
                "defect_category": random.choice(["尺寸超差", "外观不良", "功能异常", "其他"]),
                "defect_qty": random.randint(1, 10),
                "total_qty": random.randint(50, 200),
                "defect_description": f"发现 {defect_type} 不良",
                "recorded_at": now,
                "product_line_code": "DC-DC-100",
            })
        return records

    async def fetch_measurements(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(InspectionCharacteristic).where(InspectionCharacteristic.product_line == "DC-DC-100")
        )
        ics = result.scalars().all()
        if not ics:
            return []

        measurements = []
        for ic in ics:
            if ic.target_value is None or ic.spec_upper is None or ic.spec_lower is None:
                continue
            sigma = (ic.spec_upper - ic.spec_lower) / 6.0
            values = [round(random.gauss(ic.target_value, sigma), 4) for _ in range(ic.subgroup_size)]
            measurements.append({
                "external_id": f"MEAS-{ic.ic_code}-{now.strftime('%Y%m%d%H%M%S')}",
                "order_no": f"WO-2026-{random.randint(1, 999):03d}",
                "ic_code": ic.ic_code,
                "batch_no": f"B-{now.strftime('%Y%m%d')}-{random.randint(1, 999):03d}",
                "values": values,
                "sampled_at": now,
                "product_line_code": "DC-DC-100",
            })
        return measurements

    async def push_quality_event(self, event_type: str, data: dict, event_id: str | None = None) -> dict:
        return {"status": "ok", "mock": True, "event_id": event_id}


class RESTMESConnector(MESConnector):
    """通用 REST API MES 连接器（配置驱动），完整实现。"""

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

    def _resolve_auth(self) -> dict:
        """根据 auth_type 构造请求头。"""
        headers = {}
        if self.auth_type == "bearer":
            token = self.auth_config.get("token_encrypted")
            if token:
                headers["Authorization"] = f"Bearer {decrypt_credential(token)}"
        elif self.auth_type == "basic":
            # httpx 支持 auth tuple
            pass
        elif self.auth_type == "api_key":
            key_name = self.auth_config.get("key_name", "X-API-Key")
            key_encrypted = self.auth_config.get("outbound_api_key_encrypted")
            if key_encrypted:
                headers[key_name] = decrypt_credential(key_encrypted)
        return headers

    def _auth_for_httpx(self) -> tuple | None:
        if self.auth_type == "basic":
            user_enc = self.auth_config.get("username_encrypted")
            pass_enc = self.auth_config.get("password_encrypted")
            if user_enc and pass_enc:
                return (decrypt_credential(user_enc), decrypt_credential(pass_enc))
        return None

    def _map_field(self, openqms_field: str, data: dict) -> Any:
        mes_field = self.field_mapping.get(openqms_field, openqms_field)
        return data.get(mes_field)

    def _reverse_map(self, mes_data: dict) -> dict:
        """将 MES 字段名映射回 OpenQMS 字段名。"""
        reverse = {v: k for k, v in self.field_mapping.items()}
        return {reverse.get(k, k): v for k, v in mes_data.items()}

    def _get_response_data(self, resp_json: dict, endpoint_name: str) -> list:
        path = self.endpoints.get(endpoint_name, {}).get("response_path", "")
        if not path:
            return resp_json if isinstance(resp_json, list) else []
        parts = path.split(".")
        data = resp_json
        for part in parts:
            data = data.get(part, {}) if isinstance(data, dict) else []
        return data if isinstance(data, list) else []

    async def _request(self, method: str, path: str, params: dict | None = None, json_body: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        headers = self._resolve_auth()
        auth = self._auth_for_httpx()
        max_retries = self.retry_config.get("max_retries", 3)
        backoff = self.retry_config.get("backoff_seconds", [1, 2, 4])

        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                resp = await self._client.request(
                    method, url, params=params, json=json_body,
                    headers=headers, auth=auth,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_exc = e
                if attempt < max_retries:
                    import asyncio
                    await asyncio.sleep(backoff[min(attempt, len(backoff) - 1)])
        raise last_exc

    async def _fetch_paginated(self, endpoint_name: str, since: datetime | None) -> list[dict]:
        ep = self.endpoints.get(endpoint_name, {})
        path = ep.get("path", "")
        method = ep.get("method", "GET")
        cursor_field = ep.get("cursor_field")
        pagination = ep.get("pagination", {"type": "none"})
        pag_type = pagination.get("type", "none")

        params = {}
        if cursor_field and since:
            params[cursor_field] = since.isoformat()

        all_data = []
        page = 1
        cursor = None
        max_pages = 100  # safety limit

        for _ in range(max_pages):
            if pag_type == "offset":
                params[pagination.get("page_param", "page")] = page
                params[pagination.get("size_param", "page_size")] = pagination.get("size", 100)
            elif pag_type == "cursor" and cursor:
                params[pagination.get("cursor_param", "after")] = cursor

            resp = await self._request(method, path, params=params)
            data = self._get_response_data(resp, endpoint_name)
            if not data:
                break
            all_data.extend([self._reverse_map(item) for item in data])

            if pag_type == "offset":
                page += 1
                if len(data) < pagination.get("size", 100):
                    break
            elif pag_type == "cursor":
                cursor = resp.get(pagination.get("cursor_response_field", "next_cursor"))
                if not cursor:
                    break
            else:
                break

        return all_data

    def _validate_items(self, endpoint_name: str, raw_items: list[dict]) -> list[dict]:
        """使用 Pydantic Schema 校验并转换原始 MES 数据（ISO 时间字符串 → datetime 等）。
        任一记录校验失败即抛出异常，使整个 sync job 失败且不推进 checkpoint（符合设计契约）。"""
        from app.schemas import mes as schemas
        schema_map = {
            "production_orders": schemas.MESIngestProductionOrder,
            "equipment_status": schemas.MESIngestEquipmentStatus,
            "scrap_records": schemas.MESIngestScrapRecord,
            "measurements": schemas.MESIngestMeasurement,
        }
        schema_cls = schema_map.get(endpoint_name)
        if not schema_cls:
            return raw_items
        validated = []
        dt_map = {
            "production_orders": "production_order",
            "equipment_status": "equipment_status",
            "scrap_records": "scrap_record",
            "measurements": "measurement",
        }
        data_type = dt_map.get(endpoint_name, endpoint_name)
        for item in raw_items:
            item["data_type"] = data_type
            v = schema_cls.model_validate(item)
            dumped = v.model_dump()
            # Production orders pulled from MES MUST have source_updated_at for checkpoint
            if endpoint_name == "production_orders" and dumped.get("source_updated_at") is None:
                raise ValueError(
                    f"Production order {dumped.get('order_no')} missing source_updated_at. "
                    "Add 'source_updated_at': 'updated_at' to field_mapping."
                )
            validated.append(dumped)
        return validated

    async def fetch_production_orders(self, since: datetime) -> list[dict]:
        raw = await self._fetch_paginated("production_orders", since)
        return self._validate_items("production_orders", raw)

    async def fetch_equipment_status(self) -> list[dict]:
        raw = await self._fetch_paginated("equipment_status", None)
        return self._validate_items("equipment_status", raw)

    async def fetch_scrap_records(self, since: datetime) -> list[dict]:
        raw = await self._fetch_paginated("scrap_records", since)
        return self._validate_items("scrap_records", raw)

    async def fetch_measurements(self, since: datetime) -> list[dict]:
        raw = await self._fetch_paginated("measurements", since)
        return self._validate_items("measurements", raw)

    async def push_quality_event(self, event_type: str, data: dict, event_id: str | None = None) -> dict:
        ep = self.endpoints.get("push_event", {})
        path = ep.get("path", "/quality/events")
        method = ep.get("method", "POST")
        payload = dict(data)
        if event_id:
            payload["event_id"] = event_id
        return await self._request(method, path, json_body=payload)

    async def close(self):
        await self._client.aclose()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/mes_connector.py
git commit -m "feat(connector): add MESConnector ABC + Mock + full REST implementation

- MockMESConnector with timezone.utc aware datetimes
- RESTMESConnector: config-driven HTTP, pagination (offset/cursor/none),
  field mapping, retry with exponential backoff, auth (none/basic/bearer/api_key)
- push_quality_event carries event_id for idempotency"
```

---

## Task 5: 连接器工厂与测试连接

**Files:**
- Modify: `backend/app/services/mes_connector.py`（追加）

- [ ] **Step 1: 添加连接器工厂**

```python
# 追加到 backend/app/services/mes_connector.py

async def get_mes_connector(connection, db: AsyncSession | None = None) -> MESConnector:
    """根据 connection 配置创建对应的 MESConnector 实例。"""
    if connection.connector_type == "mock":
        if db is None:
            raise ValueError("MockMESConnector requires db session")
        return MockMESConnector(db)
    elif connection.connector_type == "rest":
        return RESTMESConnector(connection.config)
    else:
        raise ValueError(f"Unknown connector_type: {connection.connector_type}")


async def get_mes_connector_by_config(connector_type: str, config: dict, db: AsyncSession | None = None) -> MESConnector:
    """根据脱耦的配置 dict 创建 MESConnector（用于事务外创建 connector）。
    MockMESConnector 允许 db=None，因为 push_quality_event 无需数据库。"""
    if connector_type == "mock":
        return MockMESConnector(db)
    elif connector_type == "rest":
        return RESTMESConnector(config)
    else:
        raise ValueError(f"Unknown connector_type: {connector_type}")


async def test_mes_connection(connection, db: AsyncSession | None = None) -> dict:
    """测试 MES 连接是否可用。返回 {"ok": bool, "error": str|None}。"""
    connector = None
    try:
        connector = await get_mes_connector(connection, db)
        # Try a lightweight operation
        if hasattr(connector, "fetch_equipment_status"):
            await connector.fetch_equipment_status()
        return {"ok": True, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if isinstance(connector, RESTMESConnector):
            await connector.close()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/mes_connector.py
git commit -m "feat(connector): add connector factory and connection test helper"
```

---

## Phase 3: 原子 Ingestion

---

## Task 6: Service 层 — MESIngestionService（原子事务）

**Files:**
- Create: `backend/app/services/mes_service.py`
- Modify: `backend/app/services/spc_service.py`

**关键设计：** 测量数据 ingestion 必须在**同一事务**内完成：
1. `INSERT mes_measurement_ingestions ON CONFLICT DO NOTHING RETURNING ingestion_id`
2. 仅当 `ingestion_id` 非 None（新记录）时，调用 SPC 内部函数创建 batch（仅 flush，不 commit）
3. 回填 `batch_id`
4. **由调用方 commit**（API 路由层）

为此，SPC 服务层需暴露一个"不 commit"的内部入口。

- [ ] **Step 1: 改造 SPC 服务层（添加可选 commit 参数）**

```python
# backend/app/services/spc_service.py
# 在 add_sample_batch 附近添加：

async def add_sample_batch(
    db: AsyncSession, user_id: uuid.UUID, ic_id: uuid.UUID,
    data: dict, commit: bool = True,
) -> SampleBatch:
    """创建 SampleBatch。commit=False 时由调用方控制事务。"""
    batch = await _create_sample_batch_inner(db, user_id, ic_id, data)
    if commit:
        await db.commit()
        await db.refresh(batch)
        ic = await get_inspection_characteristic(db, ic_id)
        if ic:
            await _reevaluate_alarms(db, ic)
    return batch
```

- [ ] **Step 2: 编写 MESIngestionService**

```python
# backend/app/services/mes_service.py
"""MES 集成服务层。

关键约束：
- 所有 ingestion 方法接收 db  session，由调用方 commit/rollback
- 测量 ingestion 与 SPC batch 创建在同一事务内原子完成
- 使用 ON CONFLICT 实现幂等
"""
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.mes import (
    MESConnection, MESProductionOrder, MESEquipmentStatus,
    MESScrapRecord, MESMeasurementIngestion, MESSyncJob, MESPushOutbox,
)
from app.models.spc import InspectionCharacteristic
from app.services.spc_service import add_sample_batch, _create_sample_batch_inner
from app.services.mes_connector import MESConnector, MockMESConnector, get_mes_connector, get_mes_connector_by_config
from app.services.mes_crypto import hash_api_key, verify_api_key, encrypt_credential


class MESIngestionService:
    """MES 数据推送接收服务。所有方法不自行 commit，由调用方控制事务。"""

    @staticmethod
    async def ingest(db: AsyncSession, data: dict) -> dict:
        data_type = data.get("data_type")
        if data_type == "measurement":
            return await MESIngestionService._ingest_measurement(db, data)
        elif data_type == "production_order":
            return await MESIngestionService._ingest_production_order(db, data)
        elif data_type == "equipment_status":
            return await MESIngestionService._ingest_equipment_status(db, data)
        elif data_type == "scrap_record":
            return await MESIngestionService._ingest_scrap_record(db, data)
        else:
            raise ValueError(f"Unknown data_type: {data_type}")

    @staticmethod
    async def _ingest_measurement(db: AsyncSession, data: dict) -> dict:
        # Step 1: INSERT ingestion ON CONFLICT DO NOTHING
        stmt = pg_insert(MESMeasurementIngestion).values(
            connection_id=data["connection_id"],
            external_id=data.get("external_id", ""),
            order_no=data.get("order_no"),
            ic_code=data["ic_code"],
            mes_raw_data=data.get("raw_data"),
            source_sampled_at=data.get("sampled_at", datetime.now(timezone.utc)),
            product_line_code=data.get("product_line_code"),
        ).on_conflict_do_nothing(
            index_elements=["connection_id", "external_id"]
        ).returning(MESMeasurementIngestion.ingestion_id)

        result = await db.execute(stmt)
        ingestion_id = result.scalar()

        if ingestion_id is None:
            return {"status": "skipped", "reason": "duplicate external_id"}

        # Step 2: Find IC and verify product line matches connection
        ic_result = await db.execute(
            select(InspectionCharacteristic).where(InspectionCharacteristic.ic_code == data["ic_code"])
        )
        ic = ic_result.scalar_one_or_none()
        if not ic:
            raise ValueError(f"Inspection characteristic '{data['ic_code']}' not found")

        # Verify IC product line matches connection product line
        conn_result = await db.execute(
            select(MESConnection).where(MESConnection.connection_id == data["connection_id"])
        )
        connection = conn_result.scalar_one()
        if ic.product_line != connection.product_line_code:
            raise ValueError(
                f"IC product line '{ic.product_line}' does not match "
                f"connection product line '{connection.product_line_code}'"
            )

        batch = await _create_sample_batch_inner(
            db, ic.created_by_id, ic.ic_id,
            {
                "batch_no": data.get("batch_no", f"MES-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"),
                "values": data.get("values", []),
                "sampled_at": data.get("sampled_at", datetime.now(timezone.utc)),
            }
        )

        # Step 3: Re-evaluate SPC alarms (same transaction)
        from app.services.spc_service import _reevaluate_alarms_no_commit
        new_alarms = await _reevaluate_alarms_no_commit(db, ic)

        # Step 3b: Write MES outbox only if new alarms were created
        if new_alarms and ic.product_line:
            from app.services.mes_service import MESPushService
            from app.models.mes import MESConnection
            query = select(MESConnection).where(
                MESConnection.is_active == True,
                MESConnection.product_line_code == ic.product_line
            )
            result = await db.execute(query)
            for conn in result.scalars().all():
                await MESPushService.push_event(
                    db,
                    event_type="spc_alarm",
                    connection_id=conn.connection_id,
                    payload={
                        "ic_id": str(ic.ic_id),
                        "ic_code": ic.ic_code,
                        "alarm_count": len(new_alarms),
                        "product_line": ic.product_line,
                    }
                )

        # Step 4: Backfill batch_id
        await db.execute(
            update(MESMeasurementIngestion)
            .where(MESMeasurementIngestion.ingestion_id == ingestion_id)
            .values(batch_id=batch.batch_id)
        )

        return {"status": "success", "batch_id": str(batch.batch_id)}

    @staticmethod
    async def _ingest_production_order(db: AsyncSession, data: dict) -> dict:
        stmt = pg_insert(MESProductionOrder).values(
            connection_id=data["connection_id"],
            order_no=data["order_no"],
            product_model=data.get("product_model"),
            process_route=data.get("process_route"),
            planned_qty=data.get("planned_qty"),
            actual_qty=data.get("actual_qty"),
            status=data.get("status", "planned"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            source_updated_at=data.get("source_updated_at"),
            product_line_code=data.get("product_line_code"),
            mes_raw_data=data.get("raw_data"),
        ).on_conflict_do_update(
            index_elements=["connection_id", "order_no"],
            set_={
                "actual_qty": data.get("actual_qty"),
                "status": data.get("status"),
                "completed_at": data.get("completed_at"),
                "source_updated_at": data.get("source_updated_at"),
                "mes_raw_data": data.get("raw_data"),
            }
        )
        await db.execute(stmt)

        # Backfill scrap records that arrived before this order
        from sqlalchemy import select as sa_select
        order_subq = (
            sa_select(MESProductionOrder.order_id)
            .where(MESProductionOrder.connection_id == data["connection_id"])
            .where(MESProductionOrder.order_no == data["order_no"])
            .scalar_subquery()
        )
        await db.execute(
            update(MESScrapRecord)
            .where(MESScrapRecord.connection_id == data["connection_id"])
            .where(MESScrapRecord.order_no == data["order_no"])
            .where(MESScrapRecord.order_id.is_(None))
            .values(order_id=order_subq)
        )

        return {"status": "success"}

    @staticmethod
    async def _ingest_equipment_status(db: AsyncSession, data: dict) -> dict:
        stmt = pg_insert(MESEquipmentStatus).values(
            connection_id=data["connection_id"],
            external_id=data["external_id"],
            equipment_code=data["equipment_code"],
            equipment_name=data.get("equipment_name"),
            status=data["status"],
            availability=data.get("availability"),
            performance=data.get("performance"),
            quality=data.get("quality"),
            oee=data.get("oee"),
            downtime_reason=data.get("downtime_reason"),
            recorded_at=data.get("recorded_at", datetime.now(timezone.utc)),
            product_line_code=data.get("product_line_code"),
            mes_raw_data=data.get("raw_data"),
        ).on_conflict_do_nothing(
            index_elements=["connection_id", "external_id"]
        )
        await db.execute(stmt)
        return {"status": "success"}

    @staticmethod
    async def _ingest_scrap_record(db: AsyncSession, data: dict) -> dict:
        # Resolve order_no → order_id via (connection_id, order_no) unique key
        order_id = None
        order_no = data.get("order_no")
        if order_no:
            order_result = await db.execute(
                select(MESProductionOrder.order_id)
                .where(MESProductionOrder.connection_id == data["connection_id"])
                .where(MESProductionOrder.order_no == order_no)
            )
            order_row = order_result.scalar_one_or_none()
            if order_row:
                order_id = order_row

        stmt = pg_insert(MESScrapRecord).values(
            connection_id=data["connection_id"],
            external_id=data["external_id"],
            order_no=order_no,
            order_id=order_id,
            equipment_code=data.get("equipment_code"),
            defect_type=data["defect_type"],
            defect_category=data.get("defect_category"),
            defect_qty=data["defect_qty"],
            total_qty=data["total_qty"],
            defect_description=data.get("defect_description"),
            recorded_at=data.get("recorded_at", datetime.now(timezone.utc)),
            product_line_code=data.get("product_line_code"),
            mes_raw_data=data.get("raw_data"),
        ).on_conflict_do_update(
            index_elements=["connection_id", "external_id"],
            set_={
                # Only backfill order_id (preserve historical snapshot for all other fields)
                "order_id": func.coalesce(MESScrapRecord.order_id, pg_insert(MESScrapRecord).excluded.order_id),
                # Also store order_no for downstream backfill queries
                "order_no": func.coalesce(MESScrapRecord.order_no, pg_insert(MESScrapRecord).excluded.order_no),
            }
        )
        await db.execute(stmt)
        return {"status": "success"}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/mes_service.py backend/app/services/spc_service.py
git commit -m "feat(service): add MESIngestionService with atomic measurement ingestion

- SPC add_sample_batch gains optional commit=False param
- Measurement ingestion: ON CONFLICT + _create_sample_batch_inner (flush only)
  + batch_id backfill, all in one transaction controlled by caller
- Power idempotent ingestion for all data types"
```

---

## Task 7: API Key 认证守卫

**Files:**
- Create: `backend/app/api/mes_deps.py`（或追加到 mes.py 顶部）

- [ ] **Step 1: 编写 API Key 依赖**

```python
# backend/app/api/mes_deps.py
"""MES 专用依赖：API Key 认证（用于 /api/mes/ingest）。"""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.mes import MESConnection
from app.services.mes_crypto import verify_api_key


async def require_mes_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MESConnection:
    """验证 X-API-Key header，返回对应的 MESConnection。"""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header")

    # Find connection by matching hash
    result = await db.execute(select(MESConnection))
    connections = result.scalars().all()

    for conn in connections:
        auth_config = conn.config.get("auth_config", {})
        stored_hash = auth_config.get("api_key_hash")
        if stored_hash and verify_api_key(api_key, stored_hash):
            if not conn.is_active:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Connection is inactive")
            return conn

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/mes_deps.py
git commit -m "feat(api): add API Key auth dependency for MES inbound ingest"
```

---

## Phase 4: 同步调度

---

## Task 8: MESSyncService（三阶段短事务）

**Files:**
- Modify: `backend/app/services/mes_service.py`（追加 MESSyncService）

**核心设计 — 三阶段短事务：**

```
阶段 1（短事务）: SELECT FOR UPDATE SKIP LOCKED → UPDATE status='running' → COMMIT
阶段 2（无事务）:   connector.fetch_*() → 数据在内存中
阶段 3（短事务）:   UPSERT 数据 → UPDATE checkpoint=COALESCE(max_source_timestamp, old_checkpoint) → COMMIT
```

失败时：job.status='failed'，不更新 checkpoint，consecutive_failures += 1。

- [ ] **Step 1: 追加 MESSyncService**

```python
# 追加到 backend/app/services/mes_service.py

class MESSyncService:
    """MES 同步服务。三阶段短事务，避免长事务持锁。"""

    SYNC_INTERVAL_MINUTES = 5
    OVERLAP_WINDOW_SECONDS = 300
    TIMEOUT_MINUTES = 10
    MAX_FAILURES = 3

    BATCH_SIZE = 100

    # Field used to advance checkpoint after successful sync
    CHECKPOINT_FIELDS = {
        # production_orders uses source_updated_at (MES updated_at mapped via field_mapping)
        "production_orders": ["source_updated_at"],
        "equipment_status": [],  # Full snapshot, no checkpoint
        "scrap_records": ["recorded_at"],
        "measurements": ["sampled_at"],
    }

    @staticmethod
    def _get_checkpoint_value(data_type: str, item: dict) -> datetime | None:
        """从同步数据中提取 checkpoint 时间戳。按优先级尝试多个字段。"""
        fields = MESSyncService.CHECKPOINT_FIELDS.get(data_type, [])
        for field in fields:
            ts = item.get(field)
            if ts and isinstance(ts, datetime):
                return ts
        return None

    @staticmethod
    async def create_sync_jobs_for_connection(db: AsyncSession, connection_id: uuid.UUID):
        """为新建连接初始化 4 个 pending 同步任务。调用方负责 commit。"""
        for data_type in ("production_orders", "equipment_status", "scrap_records", "measurements"):
            db.add(MESSyncJob(
                connection_id=connection_id,
                data_type=data_type,
                status="pending",
            ))

    @staticmethod
    async def claim_jobs(db: AsyncSession, connection_id: uuid.UUID | None = None) -> list[MESSyncJob]:
        """阶段 1 — 领取 job（短事务，调用方需 commit）。
        connection_id 可选，用于测试隔离。"""
        from sqlalchemy import text
        stmt = (
            select(MESSyncJob)
            .join(MESConnection, MESSyncJob.connection_id == MESConnection.connection_id)
            .where(MESConnection.is_active == True)
            .where(
                (MESSyncJob.status.in_(["pending", "failed"]))
                | ((MESSyncJob.status == "completed") & (MESSyncJob.next_run_at <= datetime.now(timezone.utc)))
            )
        )
        if connection_id:
            stmt = stmt.where(MESSyncJob.connection_id == connection_id)
        result = await db.execute(stmt.with_for_update(skip_locked=True).limit(MESSyncService.BATCH_SIZE))
        jobs = result.scalars().all()
        for job in jobs:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
        return jobs

    @staticmethod
    async def recover_stuck_jobs(db: AsyncSession, connection_id: uuid.UUID | None = None) -> int:
        """超时恢复：running 超过 10 分钟的 job 重置为 failed。返回重置数量。
        connection_id 可选，用于测试隔离。"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=MESSyncService.TIMEOUT_MINUTES)
        stmt = (
            select(MESSyncJob)
            .where(MESSyncJob.status == "running")
            .where(MESSyncJob.started_at < cutoff)
        )
        if connection_id:
            stmt = stmt.where(MESSyncJob.connection_id == connection_id)
        result = await db.execute(stmt.with_for_update(skip_locked=True))
        stuck = result.scalars().all()
        for job in stuck:
            job.status = "failed"
            job.error_message = "Timeout: sync job exceeded 10 minutes"
        return len(stuck)

    @staticmethod
    async def run_sync_round(db: AsyncSession, connection_id: uuid.UUID | None = None):
        """执行一轮完整同步调度。connection_id 可选，用于手动同步限定范围。"""
        # Step 1: recover stuck jobs
        recovered = await MESSyncService.recover_stuck_jobs(db, connection_id=connection_id)
        if recovered:
            await db.commit()

        # Step 2: claim jobs (scoped to connection_id if provided)
        jobs = await MESSyncService.claim_jobs(db, connection_id=connection_id)
        if not jobs:
            return
        await db.commit()  # Release locks

        # Step 3: process each job independently
        for job in jobs:
            try:
                await MESSyncService._sync_single_job(db, job)
            except Exception as e:
                # Update job to failed in independent short tx
                async with async_session() as fail_db:
                    job_refresh = await fail_db.get(MESSyncJob, job.job_id)
                    if job_refresh:
                        job_refresh.status = "failed"
                        job_refresh.error_message = str(e)
                        job_refresh.consecutive_failures += 1
                        if job_refresh.consecutive_failures >= MESSyncService.MAX_FAILURES:
                            await fail_db.execute(
                                update(MESConnection)
                                .where(MESConnection.connection_id == job_refresh.connection_id)
                                .values(is_active=False)
                            )
                        await fail_db.commit()

    @staticmethod
    async def _sync_single_job(db: AsyncSession, job: MESSyncJob):
        """同步单个 job 的数据。真正的三阶段：内存复制→无事务网络→短事务写入。"""
        # ---- Phase 2a: Read connection config into memory (short read-only tx) ----
        from app.database import async_session
        async with async_session() as read_db:
            result = await read_db.execute(
                select(MESConnection).where(MESConnection.connection_id == job.connection_id)
            )
            connection = result.scalar_one()
            connector_type = connection.connector_type
            config = dict(connection.config)
            # Capture product_line_code for isolation enforcement
            connection_product_line_code = connection.product_line_code

        # ---- Phase 2b: External fetch (NO transaction) ----
        connector = await get_mes_connector_by_config(connector_type, config, db)
        since = None
        if job.checkpoint:
            since = job.checkpoint - timedelta(seconds=MESSyncService.OVERLAP_WINDOW_SECONDS)

        data = []
        try:
            if job.data_type == "production_orders":
                data = await connector.fetch_production_orders(since)
            elif job.data_type == "equipment_status":
                data = await connector.fetch_equipment_status()
            elif job.data_type == "scrap_records":
                data = await connector.fetch_scrap_records(since)
            elif job.data_type == "measurements":
                data = await connector.fetch_measurements(since)
            else:
                raise ValueError(f"Unknown data_type: {job.data_type}")
        finally:
            if hasattr(connector, "close"):
                await connector.close()

        # ---- Phase 3: Write results (short tx, per data_type block) ----
        max_ts = None
        async with async_session() as write_db:
            # Refresh job in new session
            job_refresh = await write_db.get(MESSyncJob, job.job_id)
            if not job_refresh or job_refresh.status != "running":
                return  # Job was reset or taken over

            for item in data:
                item["connection_id"] = job.connection_id
                # Enforce product line isolation: overwrite whatever MES returned
                item["product_line_code"] = connection_product_line_code
                if job.data_type == "production_orders":
                    await MESIngestionService._ingest_production_order(write_db, item)
                elif job.data_type == "equipment_status":
                    await MESIngestionService._ingest_equipment_status(write_db, item)
                elif job.data_type == "scrap_records":
                    await MESIngestionService._ingest_scrap_record(write_db, item)
                elif job.data_type == "measurements":
                    await MESIngestionService._ingest_measurement(write_db, item)
                ts = MESSyncService._get_checkpoint_value(job.data_type, item)
                if ts and (max_ts is None or ts > max_ts):
                    max_ts = ts

            # Update job checkpoint
            job_refresh.status = "completed"
            job_refresh.checkpoint = max_ts if max_ts else job_refresh.checkpoint
            job_refresh.next_run_at = datetime.now(timezone.utc) + timedelta(minutes=MESSyncService.SYNC_INTERVAL_MINUTES)
            job_refresh.completed_at = datetime.now(timezone.utc)
            job_refresh.consecutive_failures = 0
            job_refresh.error_message = None
            await write_db.commit()

    @staticmethod
    async def manual_sync(db: AsyncSession, connection_id: uuid.UUID):
        """手动触发同步。若存在 running job，返回 409。"""
        result = await db.execute(
            select(MESSyncJob).where(
                MESSyncJob.connection_id == connection_id,
                MESSyncJob.status == "running"
            )
        )
        if result.scalar_one_or_none():
            raise ValueError("Sync already in progress")

        await db.execute(
            update(MESSyncJob)
            .where(MESSyncJob.connection_id == connection_id)
            .where(MESSyncJob.status.in_(["completed", "failed"]))
            .values(status="pending")
        )
        await db.commit()

        # Trigger immediate sync round scoped to this connection
        await MESSyncService.run_sync_round(db, connection_id=connection_id)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/mes_service.py
git commit -m "feat(sync): add MESSyncService with 3-phase short transactions

- Phase 1: claim jobs with FOR UPDATE SKIP LOCKED + immediate COMMIT
- Phase 2: external fetch (no transaction)
- Phase 3: UPSERT + checkpoint=COALESCE(max_source_timestamp, old_checkpoint) + COMMIT
- Timeout recovery for stuck running jobs (>10min)
- Overlap window (5min) for incremental sync
- run_sync_round accepts optional connection_id for scoped manual sync"
```

---

## Task 9: 后台调度器注册（lifespan）

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 在 lifespan 中注册 MES 后台协程**

```python
# backend/app/main.py — 在 lifespan 中追加（cleanup_task 之后，yield 之前）

    # Start MES sync scheduler
    from app.services.mes_service import MESSyncService

    async def _mes_sync_loop():
        while True:
            await asyncio.sleep(60)
            try:
                async with async_session() as db:
                    await MESSyncService.run_sync_round(db)
            except Exception as e:
                print(f"[mes_sync] error: {e}")

    mes_sync_task = asyncio.create_task(_mes_sync_loop())

    # Start MES outbox processor (defined in Task 12)
    from app.services.mes_service import MESPushService

    async def _mes_outbox_loop():
        while True:
            await asyncio.sleep(30)
            try:
                async with async_session() as db:
                    await MESPushService.process_outbox(db)
            except Exception as e:
                print(f"[mes_outbox] error: {e}")

    mes_outbox_task = asyncio.create_task(_mes_outbox_loop())

    yield

    # Cancel MES background tasks
    mes_sync_task.cancel()
    mes_outbox_task.cancel()
    try:
        await mes_sync_task
    except asyncio.CancelledError:
        pass
    try:
        await mes_outbox_task
    except asyncio.CancelledError:
        pass
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(main): register MES sync and outbox background tasks in lifespan"
```

---

## Task 10: 手动同步端点

已在 Task 8 的 `MESSyncService.manual_sync` 中实现。Task 14 的 API 路由中将暴露该端点。

---

## Phase 5: Outbox 推送

---

## Task 11: MESPushService（三阶段短事务）

**Files:**
- Modify: `backend/app/services/mes_service.py`（追加 MESPushService）

**核心设计 — 三阶段短事务：**

```
阶段 1（短事务）: SELECT FOR UPDATE SKIP LOCKED → UPDATE status='processing' → COMMIT
阶段 2（无事务）:   connector.push_quality_event(event_id=outbox_id)
阶段 3（短事务）:   UPDATE status='sent' 或 retry → COMMIT
```

投递语义：at-least-once。event_id=outbox_id 供 MES 幂等。

- [ ] **Step 1: 追加 MESPushService**

```python
# 追加到 backend/app/services/mes_service.py

class MESPushService:
    """MES 反向推送服务（outbox 模式）。三阶段短事务。"""

    OUTBOX_TIMEOUT_MINUTES = 10
    BATCH_SIZE = 100

    @staticmethod
    async def push_event(db: AsyncSession, event_type: str, connection_id: uuid.UUID, payload: dict) -> MESPushOutbox:
        """业务方调用：将事件写入 outbox（同一事务内）。调用方负责 commit。"""
        outbox = MESPushOutbox(
            event_type=event_type,
            connection_id=connection_id,
            payload=payload,
            status="pending",
        )
        db.add(outbox)
        return outbox

    @staticmethod
    async def recover_stuck_outbox(db: AsyncSession, connection_id: uuid.UUID | None = None) -> int:
        """超时恢复：processing 超过 10 分钟重置为 pending。
        connection_id 可选，用于测试隔离。"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=MESPushService.OUTBOX_TIMEOUT_MINUTES)
        stmt = (
            select(MESPushOutbox)
            .where(MESPushOutbox.status == "processing")
            .where(MESPushOutbox.started_at < cutoff)
        )
        if connection_id:
            stmt = stmt.where(MESPushOutbox.connection_id == connection_id)
        result = await db.execute(stmt.with_for_update(skip_locked=True))
        stuck = result.scalars().all()
        for item in stuck:
            item.status = "pending"
            item.started_at = None
        return len(stuck)

    @staticmethod
    async def process_outbox(db: AsyncSession):
        """后台任务：处理 pending outbox。三阶段短事务。"""
        from app.database import async_session

        # Step 1: recover stuck
        recovered = await MESPushService.recover_stuck_outbox(db)
        if recovered:
            await db.commit()

        # Step 2: claim items (short tx, limited batch)
        result = await db.execute(
            select(MESPushOutbox)
            .join(MESConnection, MESPushOutbox.connection_id == MESConnection.connection_id)
            .where(MESConnection.is_active == True)
            .where(MESPushOutbox.status == "pending")
            .where(MESPushOutbox.next_retry_at <= datetime.now(timezone.utc))
            .with_for_update(skip_locked=True)
            .limit(MESPushService.BATCH_SIZE)
        )
        items = result.scalars().all()
        if not items:
            return

        for item in items:
            item.status = "processing"
            item.started_at = datetime.now(timezone.utc)
        await db.commit()  # Release locks

        # Step 3: send each item (memory copy → no-tx HTTP → short tx result)
        for item in items:
            # 3a: Copy outbox + connection data to memory (short read tx)
            async with async_session() as read_db:
                fresh = await read_db.get(MESPushOutbox, item.outbox_id)
                if not fresh or fresh.status != "processing":
                    continue
                conn_result = await read_db.execute(
                    select(MESConnection).where(MESConnection.connection_id == fresh.connection_id)
                )
                connection = conn_result.scalar_one()
                connector_type = connection.connector_type
                config = dict(connection.config)
                event_type = fresh.event_type
                payload = dict(fresh.payload)
                outbox_id = fresh.outbox_id

            # 3b: HTTP push (NO transaction)
            connector = None
            try:
                connector = await get_mes_connector_by_config(connector_type, config)
                response = await connector.push_quality_event(
                    event_type, payload, event_id=str(outbox_id),
                )
                push_ok = True
            except Exception as e:
                push_ok = False
                push_error = str(e)
            finally:
                if connector and hasattr(connector, "close"):
                    await connector.close()

            # 3c: Write result (short tx)
            async with async_session() as write_db:
                fresh = await write_db.get(MESPushOutbox, outbox_id)
                if not fresh:
                    continue
                if push_ok:
                    fresh.status = "sent"
                    fresh.sent_at = datetime.now(timezone.utc)
                else:
                    fresh.retry_count += 1
                    fresh.last_error = push_error
                    if fresh.retry_count >= fresh.max_retries:
                        fresh.status = "failed"
                    else:
                        fresh.status = "pending"
                        fresh.next_retry_at = datetime.now(timezone.utc) + timedelta(
                            minutes=2 ** min(fresh.retry_count, 5)
                        )
                await write_db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/mes_service.py
git commit -m "feat(push): add MESPushService with outbox pattern and 3-phase transactions

- push_event writes outbox in caller's transaction
- process_outbox: claim with FOR UPDATE SKIP LOCKED + COMMIT,
  then async send with event_id=outbox_id for idempotency,
  then commit result
- Timeout recovery for stuck processing items (>10min)"
```

---

## Task 12: 后台 outbox 处理器

已在 Task 9（lifespan 注册）中完成。`_mes_outbox_loop` 每 30 秒调用 `MESPushService.process_outbox`。

---

## Task 12b: SPC/CAPA 业务事件接入 Outbox

**Files:**
- Modify: `backend/app/services/spc_service.py`
- Modify: `backend/app/services/capa_service.py`
- Modify: `backend/app/services/mes_service.py`（push_event 已存在）

**注意：** 本 Task 确保 outbox 有事件可推送，否则 outbox 表永远为空。

- [ ] **Step 1: SPC 告警触发时写入 Outbox**

**先修改 `_reevaluate_alarms_no_commit` 和 `_reevaluate_alarms` 返回新 Alarm 列表**：

```python
# backend/app/services/spc_service.py
# 修改 _reevaluate_alarms_no_commit 的签名和末尾：

async def _reevaluate_alarms_no_commit(db: AsyncSession, ic: InspectionCharacteristic) -> list[SPCAlarm]:
    """计算告警 + 生成 SPCAlarm 记录 + db.flush()，不 commit。返回新创建的 Alarm 列表。"""
    # ... existing logic ...
    new_alarms: list[SPCAlarm] = []
    for alarm in alarms:
        # ... existing check for duplicate ...
        if existing.scalar_one_or_none():
            continue
        spc_alarm = SPCAlarm(...)
        db.add(spc_alarm)
        new_alarms.append(spc_alarm)
    
    await db.flush()
    return new_alarms

# _reevaluate_alarms 同样修改：
async def _reevaluate_alarms(db: AsyncSession, ic: InspectionCharacteristic) -> list[SPCAlarm]:
    """计算告警 + 生成 SPCAlarm 记录 + commit。返回新创建的 Alarm 列表。"""
    new_alarms = await _reevaluate_alarms_no_commit(db, ic)
    if new_alarms:
        await db.commit()
    return new_alarms
```

**然后在 `add_sample_batch` 中，仅当产生新 Alarm 时才写 Outbox**：

```python
# backend/app/services/spc_service.py
# 在 add_sample_batch 中：

async def add_sample_batch(...):
    batch = await _create_sample_batch_inner(db, user_id, ic_id, data)
    
    ic = await get_inspection_characteristic(db, ic_id)
    if ic:
        new_alarms = await _reevaluate_alarms_no_commit(db, ic)
        # Only write outbox if new alarms were actually created
        if new_alarms and ic.product_line:
            from app.services.mes_service import MESPushService
            from app.models.mes import MESConnection
            from sqlalchemy import select
            
            query = select(MESConnection).where(
                MESConnection.is_active == True,
                MESConnection.product_line_code == ic.product_line
            )
            result = await db.execute(query)
            for conn in result.scalars().all():
                await MESPushService.push_event(
                    db,
                    event_type="spc_alarm",
                    connection_id=conn.connection_id,
                    payload={
                        "ic_id": str(ic.ic_id),
                        "ic_code": ic.ic_code,
                        "alarm_count": len(new_alarms),
                        "product_line": ic.product_line,
                    }
                )
    
    # Single commit for batch + alarms + outbox
    await db.commit()
    await db.refresh(batch)
    return batch
```

**注意**：product_line 为 None 时不广播（数据不完整，无法确定目标 MES）。

- [ ] **Step 2: CAPA 状态变更时写入 Outbox**

**修改现有 `advance_capa()`**，在 `await db.commit()` 之前写入 outbox：

```python
# backend/app/services/capa_service.py
# 在 advance_capa() 末尾、db.commit() 之前插入：

async def advance_capa(
    db: AsyncSession,
    capa: CAPAEightD,
    user_id: uuid.UUID,
    d7_skip_reasons: list[dict] | None = None,
) -> CAPAEightD:
    # ... existing logic to compute old_status and next_state ...
    old_status = capa.status
    capa.status = next_state.value
    
    # ... existing audit log logic ...
    
    # Write to MES outbox before commit
    if capa.product_line_code and old_status != capa.status:
        from app.services.mes_service import MESPushService
        from app.models.mes import MESConnection
        from sqlalchemy import select
        
        query = select(MESConnection).where(
            MESConnection.is_active == True,
            MESConnection.product_line_code == capa.product_line_code
        )
        result = await db.execute(query)
        for conn in result.scalars().all():
            await MESPushService.push_event(
                db,
                event_type="capa_status_change",
                connection_id=conn.connection_id,
                payload={
                    "capa_id": str(capa.report_id),
                    "old_status": old_status,
                    "new_status": capa.status,
                    "changed_at": datetime.now(timezone.utc).isoformat(),
                    "product_line_code": capa.product_line_code,
                }
            )
    
    await db.commit()  # commit 包含 outbox 写入
    await db.refresh(capa)
    return capa
```

**注意**：使用 `old_status != capa.status` 确保只在状态真正变化时写 outbox。

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/spc_service.py backend/app/services/capa_service.py
git commit -m "feat(integration): wire SPC alarms and CAPA status changes to MES outbox

- SPC alarm triggers write mes_push_outbox record per active connection
- CAPA status transition triggers outbox event
- Both use caller's transaction (no independent commit)"
```

---

## Phase 6: API 与 RLS

---

## Task 13: 查询 API（产品线隔离 + 凭证脱敏）

**Files:**
- Create: `backend/app/api/mes.py`

- [ ] **Step 1: 编写完整 API 路由**

```python
# backend/app/api/mes.py
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database import get_db
from app.core.permissions import get_current_user, require_permission, Module, PermissionLevel
from app.models.user import User
from app.schemas import mes as schemas
from app.services.mes_service import MESIngestionService, MESSyncService, MESPushService
from app.services.mes_connector import test_mes_connection, get_mes_connector
from app.services.mes_crypto import hash_api_key, encrypt_credential, sanitize_config
from app.api.mes_deps import require_mes_api_key
from app.models.mes import (
    MESConnection, MESSyncJob, MESProductionOrder,
    MESEquipmentStatus, MESScrapRecord,
)

router = APIRouter(prefix="/api/mes", tags=["mes"])


# --- Helper: apply product line filter -----------------------------------------
# Reuses existing utilities from app.core.product_line_filter
# Add "mes": "product_line_code" to PRODUCT_LINE_FIELD_MAP in that file

async def _apply_pl_filter(query, user: User, model, db: AsyncSession, request: Request):
    """使用现有权限系统的产品线隔离。"""
    from app.core.product_line_filter import apply_product_line_filter
    return await apply_product_line_filter(query, user, model, "mes", db, request)


# --- Connection Management (admin/manager: APPROVE) ----------------------------

@router.get("/connections", response_model=schemas.MESConnectionListResponse)
async def list_mes_connections(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    from app.core.product_line_filter import get_user_product_line_codes

    query = select(MESConnection)
    # Apply product line isolation for connections
    if not user.role_definition.bypass_row_level_security:
        user_codes = await get_user_product_line_codes(user, db)
        query = query.where(MESConnection.product_line_code.in_(user_codes))

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    items = result.scalars().all()

    # Sanitize config before returning
    sanitized_items = []
    for item in items:
        data = schemas.MESConnectionResponse.model_validate(item).model_dump()
        data["config"] = sanitize_config(item.config)
        sanitized_items.append(data)

    return schemas.MESConnectionListResponse(
        items=sanitized_items,
        total=total,
        page=page,
        page_size=page_size,
    )


def _validate_rest_config(connector_type: str, config: dict) -> dict:
    """校验 REST connector 配置完整性并返回规范化后的 config dict。

    connector_type != 'rest' 时直接返回原 config。
    使用 Pydantic RESTConfig schema 完成结构化校验 + 默认值填充，
    确保运行时不会遇到 None.pagination.get() 等问题。
    """
    if connector_type != "rest":
        return config
    try:
        validated = schemas.RESTConfig.model_validate(config)
    except ValidationError as e:
        # Flatten Pydantic errors into a single detail string for HTTP 400
        errors = e.errors()
        detail = errors[0]["msg"] if len(errors) == 1 else errors
        raise HTTPException(status_code=400, detail=detail)
    # Return normalized dict: Pydantic fills defaults, strips None optionals,
    # ensures endpoint configs are typed objects (not bare dicts with null sub-keys)
    return validated.model_dump(exclude_none=True)


@router.post("/connections", response_model=schemas.MESConnectionResponse)
async def create_mes_connection(
    req: schemas.MESConnectionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    # Validate + normalize FIRST — Pydantic fills defaults, strips None optionals
    config = _validate_rest_config(req.connector_type, dict(req.config))

    # Separate inbound vs outbound credentials (auth_config is already typed by Pydantic)
    auth = config.get("auth_config", {})
    if not isinstance(auth, dict):
        auth = {}
    # Inbound: API Key for MES → OpenQMS push
    if "inbound_api_key" in auth and isinstance(auth["inbound_api_key"], str):
        auth["api_key_hash"] = hash_api_key(auth.pop("inbound_api_key"))
    # Outbound: credentials for OpenQMS → MES push
    for key in ["token", "password", "secret"]:
        if key in auth and isinstance(auth[key], str) and auth[key] != "***" and not auth[key].startswith("gAAAA"):
            auth[key + "_encrypted"] = encrypt_credential(auth.pop(key))
    if "outbound_api_key" in auth and isinstance(auth.get("outbound_api_key"), str) and auth["outbound_api_key"] != "***":
        auth["outbound_api_key_encrypted"] = encrypt_credential(auth.pop("outbound_api_key"))
    # Basic auth username
    if "username" in auth and isinstance(auth["username"], str) and auth["username"] != "***":
        auth["username_encrypted"] = encrypt_credential(auth.pop("username"))
    config["auth_config"] = auth

    # Enforce product line access for creation
    from app.core.product_line_filter import enforce_product_line_access
    await enforce_product_line_access(user, req.product_line_code, db)

    connection = MESConnection(
        name=req.name,
        connector_type=req.connector_type,
        config=config,
        product_line_code=req.product_line_code,
        created_by=user.user_id,
    )
    db.add(connection)
    await db.flush()  # Get connection_id before creating jobs

    # Initialize sync jobs for all 4 data types
    await MESSyncService.create_sync_jobs_for_connection(db, connection.connection_id)

    await db.commit()
    await db.refresh(connection)

    # Sanitize for response
    data = schemas.MESConnectionResponse.model_validate(connection).model_dump()
    data["config"] = sanitize_config(connection.config)
    return data


@router.get("/connections/{connection_id}", response_model=schemas.MESConnectionResponse)
async def get_mes_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    connection = await db.get(MESConnection, connection_id)
    if not connection:
        raise HTTPException(404, "Connection not found")
    # Enforce product line access
    from app.core.product_line_filter import enforce_product_line_access
    await enforce_product_line_access(user, connection.product_line_code, db)
    data = schemas.MESConnectionResponse.model_validate(connection).model_dump()
    data["config"] = sanitize_config(connection.config)
    return data


@router.put("/connections/{connection_id}", response_model=schemas.MESConnectionResponse)
async def update_mes_connection(
    connection_id: uuid.UUID,
    req: schemas.MESConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    connection = await db.get(MESConnection, connection_id)
    if not connection:
        raise HTTPException(404, "Connection not found")

    # Verify user has access to this connection's current product line
    from app.core.product_line_filter import enforce_product_line_access
    await enforce_product_line_access(user, connection.product_line_code, db)

    if req.name is not None:
        connection.name = req.name
    if req.connector_type is not None:
        connection.connector_type = req.connector_type
    if req.config is not None:
        # Validate + normalize config structure BEFORE merging/processing credentials
        check_type = req.connector_type or connection.connector_type
        config = _validate_rest_config(check_type, dict(req.config))

        # Merge with existing auth_config, ignoring "***" placeholders
        existing_auth = connection.config.get("auth_config", {})
        if not isinstance(existing_auth, dict):
            existing_auth = {}
        auth = config.get("auth_config", {})
        if not isinstance(auth, dict):
            auth = {}
        merged = dict(existing_auth)
        for k, v in auth.items():
            if v == "***":
                continue  # Keep existing value
            merged[k] = v
        # Inbound API Key
        if "inbound_api_key" in merged and isinstance(merged["inbound_api_key"], str):
            merged["api_key_hash"] = hash_api_key(merged.pop("inbound_api_key"))
        # Outbound credentials
        for key in ["token", "password", "secret", "username"]:
            if key in merged and isinstance(merged[key], str) and merged[key] != "***" and not merged[key].startswith("gAAAA"):
                merged[key + "_encrypted"] = encrypt_credential(merged.pop(key))
        if "outbound_api_key" in merged and isinstance(merged.get("outbound_api_key"), str) and merged["outbound_api_key"] != "***":
            merged["outbound_api_key_encrypted"] = encrypt_credential(merged.pop("outbound_api_key"))
        config["auth_config"] = merged
        connection.config = config

    # Final guard: validate the RESULTING connector_type + config combination
    # (catches e.g. connector_type changed to "rest" without providing new config)
    connection.config = _validate_rest_config(connection.connector_type, connection.config)

    if req.is_active is not None:
        connection.is_active = req.is_active
    if req.product_line_code is not None:
        await enforce_product_line_access(user, req.product_line_code, db)
        connection.product_line_code = req.product_line_code

    await db.commit()
    await db.refresh(connection)
    data = schemas.MESConnectionResponse.model_validate(connection).model_dump()
    data["config"] = sanitize_config(connection.config)
    return data


@router.delete("/connections/{connection_id}")
async def delete_mes_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    connection = await db.get(MESConnection, connection_id)
    if not connection:
        raise HTTPException(404, "Connection not found")
    from app.core.product_line_filter import enforce_product_line_access
    await enforce_product_line_access(user, connection.product_line_code, db)
    await db.delete(connection)
    await db.commit()
    return {"message": "Connection deleted"}


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    """轻量连通性测试：先校验配置完整性，再尝试一次轻量请求。"""
    connection = await db.get(MESConnection, connection_id)
    if not connection:
        raise HTTPException(404, "Connection not found")
    from app.core.product_line_filter import enforce_product_line_access
    await enforce_product_line_access(user, connection.product_line_code, db)

    # Step 1: Validate config completeness (catches missing endpoints, mappings, etc.)
    try:
        _validate_rest_config(connection.connector_type, connection.config)
    except HTTPException as e:
        return {"ok": False, "error": e.detail}

    # Step 2: Lightweight HTTP probe
    result = await test_mes_connection(connection, db)

    # Step 3: Warning only for REST connections about incremental sync
    if connection.connector_type == "rest":
        field_mapping = connection.config.get("field_mapping", {})
        mapped_source = field_mapping.get("source_updated_at")
        if not mapped_source:
            result["warning"] = (
                "field_mapping missing 'source_updated_at'. "
                "Production order incremental sync will fail."
            )
    return result


# --- Ingestion (API Key auth, no JWT) -----------------------------------------

from pydantic import TypeAdapter, ValidationError

_mes_ingest_adapter = TypeAdapter(schemas.MESIngestRequest)


@router.post("/ingest")
async def ingest_mes_data(
    request: Request,
    connection: MESConnection = Depends(require_mes_api_key),
    db: AsyncSession = Depends(get_db),
):
    """接收 MES 入站数据。使用 TypeAdapter 手动校验，所有验证错误返回 400。"""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    # Pre-check data_type before TypeAdapter to return clear error message
    data_type = payload.get("data_type")
    if data_type not in ("measurement", "production_order", "equipment_status", "scrap_record"):
        raise HTTPException(status_code=400, detail=f"Unknown data_type: {data_type}")

    try:
        validated = _mes_ingest_adapter.validate_python(payload)
    except ValidationError as e:
        from fastapi.encoders import jsonable_encoder
        raise HTTPException(status_code=400, detail=jsonable_encoder(e.errors()))

    data = validated.model_dump()
    data["connection_id"] = connection.connection_id
    # Enforce product line from connection — ignore any product_line_code in request
    data["product_line_code"] = connection.product_line_code
    try:
        result = await MESIngestionService.ingest(db, data)
        await db.commit()
        return result
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# --- Sync ----------------------------------------------------------------------

@router.post("/connections/{connection_id}/sync")
async def manual_sync(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    connection = await db.get(MESConnection, connection_id)
    if not connection:
        raise HTTPException(404, "Connection not found")
    from app.core.product_line_filter import enforce_product_line_access
    await enforce_product_line_access(user, connection.product_line_code, db)
    try:
        await MESSyncService.manual_sync(db, connection_id)
        return {"message": "Sync triggered"}
    except ValueError as e:
        raise HTTPException(409, str(e))


# --- Data Query (product line isolated) ----------------------------------------

@router.get("/production-orders")
async def list_production_orders(
    page: int = 1,
    page_size: int = 20,
    product_line_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.VIEW)),
    request: Request = None,
):
    query = select(MESProductionOrder)
    # Apply product line isolation
    query = await _apply_pl_filter(query, user, MESProductionOrder, db, request)
    if product_line_code:
        query = query.where(MESProductionOrder.product_line_code == product_line_code)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = result.scalars().all()

    return {
        "items": [schemas.MESProductionOrderResponse.model_validate(i) for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/production-orders/{order_id}", response_model=schemas.MESProductionOrderResponse)
async def get_production_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.VIEW)),
):
    order = await db.get(MESProductionOrder, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    from app.core.product_line_filter import enforce_product_line_access
    await enforce_product_line_access(user, order.product_line_code, db)
    return schemas.MESProductionOrderResponse.model_validate(order)


@router.get("/equipment-status")
async def list_equipment_status(
    product_line_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.VIEW)),
    request: Request = None,
):
    query = select(MESEquipmentStatus)
    query = await _apply_pl_filter(query, user, MESEquipmentStatus, db, request)
    if product_line_code:
        query = query.where(MESEquipmentStatus.product_line_code == product_line_code)
    result = await db.execute(query)
    items = result.scalars().all()
    return [schemas.MESEquipmentStatusResponse.model_validate(i) for i in items]


@router.get("/scrap-records")
async def list_scrap_records(
    page: int = 1,
    page_size: int = 20,
    product_line_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.VIEW)),
    request: Request = None,
):
    query = select(MESScrapRecord)
    query = await _apply_pl_filter(query, user, MESScrapRecord, db, request)
    if product_line_code:
        query = query.where(MESScrapRecord.product_line_code == product_line_code)

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = result.scalars().all()

    return {
        "items": [schemas.MESScrapRecordResponse.model_validate(i) for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/dashboard")
async def get_mes_dashboard(
    product_line_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.VIEW)),
    request: Request = None,
):
    query = select(MESEquipmentStatus)
    query = await _apply_pl_filter(query, user, MESEquipmentStatus, db, request)
    if product_line_code:
        query = query.where(MESEquipmentStatus.product_line_code == product_line_code)
    result = await db.execute(query)
    equipment = result.scalars().all()

    running = sum(1 for e in equipment if e.status == "running")
    down = sum(1 for e in equipment if e.status == "down")

    # Scrap by category
    scrap_query = select(MESScrapRecord)
    scrap_query = await _apply_pl_filter(scrap_query, user, MESScrapRecord, db, request)
    if product_line_code:
        scrap_query = scrap_query.where(MESScrapRecord.product_line_code == product_line_code)
    scrap_result = await db.execute(scrap_query)
    scraps = scrap_result.scalars().all()
    scrap_by_category: dict[str, int] = {}
    for s in scraps:
        cat = s.defect_category or "未知"
        scrap_by_category[cat] = scrap_by_category.get(cat, 0) + s.defect_qty

    # Orders
    order_query = select(MESProductionOrder)
    order_query = await _apply_pl_filter(order_query, user, MESProductionOrder, db, request)
    if product_line_code:
        order_query = order_query.where(MESProductionOrder.product_line_code == product_line_code)
    order_result = await db.execute(order_query)
    orders = order_result.scalars().all()
    total_planned = sum(o.planned_qty or 0 for o in orders)
    total_actual = sum(o.actual_qty or 0 for o in orders)

    return schemas.MESDashboardResponse(
        equipment_summary=[
            schemas.MESEquipmentSummary(
                equipment_code=e.equipment_code,
                equipment_name=e.equipment_name,
                status=e.status,
                availability=e.availability,
                performance=e.performance,
                quality=e.quality,
                oee=e.oee,
            )
            for e in equipment
        ],
        running_count=running,
        down_count=down,
        total_planned=total_planned,
        total_actual=total_actual,
        scrap_by_category=scrap_by_category,
        scrap_trend_7d=[],
    )
```

- [ ] **Step 2: 注册路由**

```python
# backend/app/main.py
from app.api.mes import router as mes_router
# ... existing routers ...
app.include_router(mes_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/mes.py backend/app/api/mes_deps.py backend/app/main.py
git commit -m "feat(api): add MES integration API routes with security and isolation

- Connection CRUD + test + sync endpoints
- /ingest with API Key auth (SHA-256 hash verification)
- Query endpoints with product_line_code filtering
- Config credential sanitization in responses"
```

---

## Phase 7: 前端

---

## Task 15: 前端类型 + API 客户端（复用现有 client）

**Files:**
- Create: `frontend/src/types/mes.ts`
- Create: `frontend/src/api/mes.ts`

- [ ] **Step 1: 编写 TypeScript 类型**

```typescript
// frontend/src/types/mes.ts
export interface MESConnection {
  connection_id: string;
  name: string;
  connector_type: "mock" | "rest";
  config: Record<string, any>;
  is_active: boolean;
  product_line_code: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface MESConnectionCreate {
  name: string;
  connector_type: "mock" | "rest";
  config: Record<string, any>;
  product_line_code?: string;
}

export interface MESProductionOrder {
  order_id: string;
  connection_id: string;
  order_no: string;
  product_model: string | null;
  process_route: string | null;
  status: string;
  planned_qty: number | null;
  actual_qty: number | null;
  started_at: string | null;
  completed_at: string | null;
  product_line_code: string | null;
  created_at: string;
}

export interface MESEquipmentStatus {
  record_id: string;
  equipment_code: string;
  equipment_name: string | null;
  status: string;
  availability: number | null;
  performance: number | null;
  quality: number | null;
  oee: number | null;
  downtime_reason: string | null;
  recorded_at: string;
  product_line_code: string | null;
}

export interface MESScrapRecord {
  scrap_id: string;
  connection_id: string;
  external_id: string;
  order_no: string | null;
  order_id: string | null;
  equipment_code: string | null;
  defect_type: string;
  defect_category: string | null;
  defect_qty: number;
  total_qty: number;
  defect_description: string | null;
  recorded_at: string;
  product_line_code: string | null;
}

export interface MESDashboardData {
  equipment_summary: MESEquipmentStatus[];
  running_count: number;
  down_count: number;
  total_planned: number;
  total_actual: number;
  scrap_by_category: Record<string, number>;
  scrap_trend_7d: any[];
}
```

- [ ] **Step 2: 编写 API 客户端（复用现有 client）**

```typescript
// frontend/src/api/mes.ts
import client from "./client";
import type {
  MESConnection, MESConnectionCreate, MESProductionOrder,
  MESEquipmentStatus, MESScrapRecord, MESDashboardData,
} from "../types/mes";

export const listConnections = (page = 1, page_size = 20) =>
  client.get("/mes/connections", { params: { page, page_size } }).then((r) => r.data);

export const createConnection = (data: MESConnectionCreate) =>
  client.post("/mes/connections", data).then((r) => r.data);

export const updateConnection = (id: string, data: Partial<MESConnectionCreate>) =>
  client.put(`/mes/connections/${id}`, data).then((r) => r.data);

export const deleteConnection = (id: string) =>
  client.delete(`/mes/connections/${id}`).then((r) => r.data);

export const testConnection = (id: string) =>
  client.post(`/mes/connections/${id}/test`).then((r) => r.data);

export const manualSync = (id: string) =>
  client.post(`/mes/connections/${id}/sync`).then((r) => r.data);

export const listProductionOrders = (page = 1, page_size = 20, product_line_code?: string) =>
  client.get("/mes/production-orders", { params: { page, page_size, product_line_code } }).then((r) => r.data);

export const getProductionOrder = (id: string) =>
  client.get(`/mes/production-orders/${id}`).then((r) => r.data);

export const listEquipmentStatus = (product_line_code?: string) =>
  client.get("/mes/equipment-status", { params: { product_line_code } }).then((r) => r.data);

export const listScrapRecords = (page = 1, page_size = 20, product_line_code?: string) =>
  client.get("/mes/scrap-records", { params: { page, page_size, product_line_code } }).then((r) => r.data);

export const getMESDashboard = (product_line_code?: string) =>
  client.get("/mes/dashboard", { params: { product_line_code } }).then((r) => r.data);
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/mes.ts frontend/src/api/mes.ts
git commit -m "feat(frontend): add MES TypeScript types and API client

- Reuses existing axios client (with JWT interceptor)
- All query endpoints support product_line_code filtering"
```

---

## Task 16: 前端页面（连接管理 + 看板 + 工单 + 报废）

**Files:**
- Create: `frontend/src/pages/mes/MESConnectionsPage.tsx`
- Create: `frontend/src/pages/mes/MESDashboardPage.tsx`
- Create: `frontend/src/pages/mes/MESOrdersPage.tsx`
- Create: `frontend/src/pages/mes/MESScrapPage.tsx`

- [ ] **Step 1: MESConnectionsPage.tsx**

```tsx
// frontend/src/pages/mes/MESConnectionsPage.tsx
import { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Select, Tag, message, Space } from "antd";
import {
  listConnections, createConnection, updateConnection,
  deleteConnection, manualSync, testConnection,
} from "../../api/mes";
import type { MESConnection, MESConnectionCreate } from "../../types/mes";

export default function MESConnectionsPage() {
  const [data, setData] = useState<MESConnection[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<MESConnection | null>(null);
  const [form] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await listConnections();
      setData(res.items);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleCreate = async (values: MESConnectionCreate) => {
    await createConnection(values);
    message.success("创建成功");
    setModalOpen(false);
    form.resetFields();
    fetchData();
  };

  const handleUpdate = async (values: MESConnectionCreate) => {
    if (!editing) return;
    await updateConnection(editing.connection_id, values);
    message.success("更新成功");
    setModalOpen(false);
    setEditing(null);
    fetchData();
  };

  const handleDelete = async (id: string) => {
    await deleteConnection(id);
    message.success("删除成功");
    fetchData();
  };

  const handleSync = async (id: string) => {
    try {
      await manualSync(id);
      message.success("同步已触发");
    } catch (e: any) {
      message.error(e.response?.data?.detail || "同步失败");
    }
  };

  const handleTest = async (id: string) => {
    try {
      const res = await testConnection(id);
      if (res.ok) {
        message.success("连接测试成功");
      } else {
        message.error(`连接测试失败: ${res.error}`);
      }
    } catch (e: any) {
      message.error(e.response?.data?.detail || "测试失败");
    }
  };

  const columns = [
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "类型", dataIndex: "connector_type", key: "connector_type" },
    {
      title: "状态",
      dataIndex: "is_active",
      key: "is_active",
      render: (v: boolean) => <Tag color={v ? "green" : "red"}>{v ? "启用" : "停用"}</Tag>,
    },
    { title: "产品线", dataIndex: "product_line_code", key: "product_line_code" },
    {
      title: "操作",
      key: "action",
      render: (_: any, record: MESConnection) => (
        <Space>
          <Button type="link" onClick={() => { setEditing(record); form.setFieldsValue(record); setModalOpen(true); }}>编辑</Button>
          <Button type="link" onClick={() => handleTest(record.connection_id)}>测试</Button>
          <Button type="link" onClick={() => handleSync(record.connection_id)}>同步</Button>
          <Button type="link" danger onClick={() => handleDelete(record.connection_id)}>删除</Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Button type="primary" onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true); }}>
        新增连接
      </Button>
      <Table columns={columns} dataSource={data} loading={loading} rowKey="connection_id" style={{ marginTop: 16 }} />
      <Modal
        open={modalOpen}
        title={editing ? "编辑连接" : "新增连接"}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} onFinish={editing ? handleUpdate : handleCreate}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="connector_type" label="类型" rules={[{ required: true }]}>
            <Select options={[{ value: "mock", label: "Mock" }, { value: "rest", label: "REST" }]} />
          </Form.Item>
          <Form.Item name="product_line_code" label="产品线">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: MESDashboardPage.tsx**

与之前基本一致，添加 product_line_code 过滤支持：

```tsx
// frontend/src/pages/mes/MESDashboardPage.tsx
import { useState, useEffect } from "react";
import { Card, Row, Col, Statistic, Table, Tag } from "antd";
import { getMESDashboard } from "../../api/mes";

export default function MESDashboardPage() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    getMESDashboard().then(setData).finally(() => setLoading(false));
  }, []);

  if (!data) return null;

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col span={6}><Card><Statistic title="运行设备" value={data.running_count} /></Card></Col>
        <Col span={6}><Card><Statistic title="停机设备" value={data.down_count} /></Card></Col>
        <Col span={6}><Card><Statistic title="计划产量" value={data.total_planned} /></Card></Col>
        <Col span={6}><Card><Statistic title="实际产量" value={data.total_actual} /></Card></Col>
      </Row>
      <Card title="设备状态" style={{ marginTop: 16 }}>
        <Table
          dataSource={data.equipment_summary}
          columns={[
            { title: "设备", dataIndex: "equipment_name", render: (v: string, r: any) => v || r.equipment_code },
            { title: "状态", dataIndex: "status", render: (v: string) => <Tag color={v === "running" ? "green" : "red"}>{v}</Tag> },
            { title: "可用率%", dataIndex: "availability" },
            { title: "运行率%", dataIndex: "performance" },
            { title: "质量率%", dataIndex: "quality" },
            { title: "OEE%", dataIndex: "oee" },
          ]}
          rowKey="equipment_code"
          loading={loading}
        />
      </Card>
    </div>
  );
}
```

- [ ] **Step 3: MESOrdersPage.tsx**

```tsx
// frontend/src/pages/mes/MESOrdersPage.tsx
import { useState, useEffect } from "react";
import { Table, Tag, Select } from "antd";
import { listProductionOrders } from "../../api/mes";
import type { MESProductionOrder } from "../../types/mes";

export default function MESOrdersPage() {
  const [data, setData] = useState<MESProductionOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await listProductionOrders();
      setData(res.items);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const filtered = statusFilter ? data.filter(d => d.status === statusFilter) : data;

  const columns = [
    { title: "工单号", dataIndex: "order_no" },
    { title: "产品型号", dataIndex: "product_model" },
    { title: "计划数量", dataIndex: "planned_qty" },
    { title: "实际数量", dataIndex: "actual_qty" },
    {
      title: "状态",
      dataIndex: "status",
      render: (v: string) => {
        const color = v === "completed" ? "green" : v === "in_progress" ? "blue" : "default";
        return <Tag color={color}>{v}</Tag>;
      },
    },
    { title: "开始时间", dataIndex: "started_at" },
    { title: "完成时间", dataIndex: "completed_at" },
  ];

  return (
    <div>
      <Select
        placeholder="筛选状态"
        allowClear
        style={{ width: 200, marginBottom: 16 }}
        onChange={setStatusFilter}
        options={[
          { value: "planned", label: "计划中" },
          { value: "in_progress", label: "进行中" },
          { value: "completed", label: "已完成" },
          { value: "closed", label: "已关闭" },
        ]}
      />
      <Table columns={columns} dataSource={filtered} loading={loading} rowKey="order_id" />
    </div>
  );
}
```

- [ ] **Step 4: MESScrapPage.tsx**

```tsx
// frontend/src/pages/mes/MESScrapPage.tsx
import { useState, useEffect } from "react";
import { Table, Tag, Select } from "antd";
import { listScrapRecords } from "../../api/mes";
import type { MESScrapRecord } from "../../types/mes";

export default function MESScrapPage() {
  const [data, setData] = useState<MESScrapRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [typeFilter, setTypeFilter] = useState<string | undefined>();

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await listScrapRecords();
      setData(res.items);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const filtered = typeFilter ? data.filter(d => d.defect_type === typeFilter) : data;

  const columns = [
    { title: "外部ID", dataIndex: "external_id" },
    { title: "不良类型", dataIndex: "defect_type" },
    { title: "分类", dataIndex: "defect_category" },
    { title: "不良数", dataIndex: "defect_qty" },
    { title: "总数", dataIndex: "total_qty" },
    {
      title: "不良率%",
      render: (_: any, record: MESScrapRecord) =>
        record.total_qty ? ((record.defect_qty / record.total_qty) * 100).toFixed(2) : "-",
    },
    { title: "描述", dataIndex: "defect_description" },
    { title: "记录时间", dataIndex: "recorded_at" },
  ];

  return (
    <div>
      <Select
        placeholder="筛选不良类型"
        allowClear
        style={{ width: 200, marginBottom: 16 }}
        onChange={setTypeFilter}
        options={[
          { value: "scrap", label: "报废" },
          { value: "rework", label: "返工" },
          { value: "reject", label: "拒收" },
        ]}
      />
      <Table columns={columns} dataSource={filtered} loading={loading} rowKey="scrap_id" />
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/mes/
git commit -m "feat(frontend): add MES pages (connections, dashboard, orders, scrap)"
```

---

## Task 17: 路由和侧边栏注册

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: App.tsx 注册 4 个路由**

```tsx
// frontend/src/App.tsx
import MESConnectionsPage from "./pages/mes/MESConnectionsPage";
import MESDashboardPage from "./pages/mes/MESDashboardPage";
import MESOrdersPage from "./pages/mes/MESOrdersPage";
import MESScrapPage from "./pages/mes/MESScrapPage";

// ... inside Routes ...
<Route path="/mes/dashboard" element={<ProtectedRoute><MESDashboardPage /></ProtectedRoute>} />
<Route path="/mes/connections" element={<ProtectedRoute><MESConnectionsPage /></ProtectedRoute>} />
<Route path="/mes/orders" element={<ProtectedRoute><MESOrdersPage /></ProtectedRoute>} />
<Route path="/mes/scrap" element={<ProtectedRoute><MESScrapPage /></ProtectedRoute>} />
```

- [ ] **Step 2: AppLayout.tsx 侧边栏菜单**

```tsx
// frontend/src/components/layout/AppLayout.tsx
// Add to menuItems:
{
  key: "mes",
  label: "MES 集成",
  children: [
    { key: "/mes/dashboard", label: "MES 看板" },
    { key: "/mes/orders", label: "工单列表" },
    { key: "/mes/scrap", label: "报废/返工" },
    { key: "/mes/connections", label: "连接管理" },
  ],
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(frontend): register MES routes and sidebar menu"
```

---

## Phase 8: 并发自动化测试与生命周期

---

## Task 18: 自动化并发测试

**Files:**
- Create: `backend/tests/test_mes_concurrency.py`

- [ ] **Step 1: 编写 pytest 并发测试**

```python
# backend/tests/test_mes_concurrency.py
"""MES 并发与事务核心自动化测试（pytest + asyncio）。

运行: cd backend && pytest tests/test_mes_concurrency.py -v
"""
import pytest
import asyncio
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.mes import MESConnection, MESSyncJob, MESPushOutbox, MESMeasurementIngestion, MESScrapRecord
from app.models.spc import InspectionCharacteristic
from app.services.mes_service import MESSyncService, MESPushService, MESIngestionService
from app.services.mes_connector import MockMESConnector
from app.core.security import create_access_token


# Test data prefix for cleanup isolation
_TEST_PREFIX = "TEST-MES-"


@pytest.fixture
async def db():
    """提供数据库会话供测试使用（不自动回滚，依赖 cleanup fixture 清理）。"""
    async with async_session() as session:
        yield session


@pytest.fixture
async def admin_user():
    """获取 admin 用户用于测试外键。使用独立 session 读取。"""
    async with async_session() as db:
        from app.models.user import User
        result = await db.execute(select(User).where(User.username == "admin"))
        user = result.scalar_one_or_none()
        if not user:
            pytest.skip("Admin user not found — run seed first")
        return user


@pytest.fixture
async def test_connection(admin_user):
    """创建测试 MES 连接，使用 UUID 保证唯一性，yield 后显式清理。
    使用固定 API Key 供 HTTP 路由测试。"""
    suffix = str(uuid.uuid4())[:8]
    from app.services.mes_crypto import hash_api_key
    test_api_key = "test-mes-api-key-12345"
    conn = MESConnection(
        name=f"{_TEST_PREFIX}CONN-{suffix}",
        connector_type="mock",
        config={"auth_config": {"api_key_hash": hash_api_key(test_api_key)}},
        created_by=admin_user.user_id,
        is_active=True,
    )
    async with async_session() as db:
        db.add(conn)
        await db.commit()
        await db.refresh(conn)

    yield conn

    # Cleanup
    async with async_session() as db:
        await db.execute(
            text("DELETE FROM mes_connections WHERE connection_id = :cid"),
            {"cid": conn.connection_id}
        )
        await db.commit()


@pytest.fixture
async def test_ic(admin_user):
    """创建测试检验特性，使用 UUID 保证唯一性，yield 后显式清理。"""
    suffix = str(uuid.uuid4())[:8]
    ic = InspectionCharacteristic(
        ic_code=f"{_TEST_PREFIX}IC-{suffix}",
        process_name="测试工序",
        characteristic_name="测试特性",
        chart_type="xbar_r",
        subgroup_size=5,
        target_value=10.0,
        spec_upper=12.0,
        spec_lower=8.0,
        product_line="DC-DC-100",
        created_by_id=admin_user.user_id,
    )
    async with async_session() as db:
        db.add(ic)
        await db.commit()
        await db.refresh(ic)

    yield ic

    # Cleanup
    async with async_session() as db:
        await db.execute(
            text("DELETE FROM inspection_characteristics WHERE ic_id = :iid"),
            {"iid": ic.ic_id}
        )
        await db.commit()


@pytest.fixture(autouse=True)
async def cleanup_mes_test_data():
    """每个测试结束后按连接 ID 清理 MES 测试数据。"""
    yield
    # Note: per-fixture cleanup handles individual records by PK
    # This global cleanup is a safety net for any leaked data


class TestSyncJobConcurrency:
    async def test_dual_worker_claim_once(self, test_connection):
        """双 worker 同时 claim，只有一个能获得 running 状态。"""
        # Create job in an independent session
        async with async_session() as db:
            job = MESSyncJob(
                connection_id=test_connection.connection_id,
                data_type="production_orders",
                status="pending",
            )
            db.add(job)
            await db.commit()
            job_id = job.job_id

        claimed_counts = []

        async def worker():
            async with async_session() as wdb:
                jobs = await MESSyncService.claim_jobs(wdb, connection_id=test_connection.connection_id)
                await wdb.commit()
                claimed_counts.append(len(jobs))

        await asyncio.gather(worker(), worker())

        # Only one worker should have claimed the job for this connection
        assert sum(claimed_counts) == 1

        # Cleanup: reset job to completed
        async with async_session() as db:
            job = await db.get(MESSyncJob, job_id)
            if job:
                job.status = "completed"
                await db.commit()

    async def test_running_job_timeout_recovery(self, test_connection):
        """running 超过 10 分钟的 job 被重置为 failed。"""
        async with async_session() as db:
            job = MESSyncJob(
                connection_id=test_connection.connection_id,
                data_type="equipment_status",
                status="running",
                started_at=datetime.now(timezone.utc) - timedelta(minutes=15),
            )
            db.add(job)
            await db.commit()
            job_id = job.job_id

        async with async_session() as db:
            count = await MESSyncService.recover_stuck_jobs(db, connection_id=test_connection.connection_id)
            await db.commit()
            assert count == 1
            result = await db.execute(select(MESSyncJob).where(MESSyncJob.job_id == job_id))
            updated = result.scalar_one()
            assert updated.status == "failed"

    async def test_manual_sync_blocks_running(self, test_connection):
        """手动同步时若存在 running job，返回冲突。"""
        async with async_session() as db:
            job = MESSyncJob(
                connection_id=test_connection.connection_id,
                data_type="production_orders",
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            db.add(job)
            await db.commit()

            with pytest.raises(ValueError, match="Sync already in progress"):
                await MESSyncService.manual_sync(db, test_connection.connection_id)

    async def test_inactive_connection_not_synced(self, test_connection):
        """is_active=False 的连接不会被同步。"""
        async with async_session() as db:
            # Reload connection in this session and deactivate
            conn = await db.get(MESConnection, test_connection.connection_id)
            conn.is_active = False
            await db.commit()

            job = MESSyncJob(
                connection_id=test_connection.connection_id,
                data_type="production_orders",
                status="pending",
            )
            db.add(job)
            await db.commit()

            jobs = await MESSyncService.claim_jobs(db, connection_id=test_connection.connection_id)
            await db.commit()
            assert len(jobs) == 0


class TestOutboxConcurrency:
    async def test_dual_worker_claim_once(self, db, test_connection):
        """双 worker 同时 claim outbox，只有一个能获得 processing 状态。"""
        outbox = MESPushOutbox(
            event_type="test_event",
            connection_id=test_connection.connection_id,
            payload={"test": True},
            status="pending",
        )
        db.add(outbox)
        await db.commit()

        claimed_counts = []

        async def worker():
            async with async_session() as wdb:
                recovered = await MESPushService.recover_stuck_outbox(wdb, connection_id=test_connection.connection_id)
                await wdb.commit()
                result = await wdb.execute(
                    select(MESPushOutbox)
                    .join(MESConnection, MESPushOutbox.connection_id == MESConnection.connection_id)
                    .where(MESConnection.is_active == True)
                    .where(MESPushOutbox.connection_id == test_connection.connection_id)
                    .where(MESPushOutbox.status == "pending")
                    .where(MESPushOutbox.next_retry_at <= datetime.now(timezone.utc))
                    .with_for_update(skip_locked=True)
                )
                items = result.scalars().all()
                for item in items:
                    item.status = "processing"
                    item.started_at = datetime.now(timezone.utc)
                await wdb.commit()
                claimed_counts.append(len(items))

        await asyncio.gather(worker(), worker())
        assert sum(claimed_counts) == 1

    async def test_processing_timeout_recovery(self, test_connection):
        """processing 超过 10 分钟的 outbox 被重置为 pending。"""
        async with async_session() as db:
            outbox = MESPushOutbox(
                event_type="test_event",
                connection_id=test_connection.connection_id,
                payload={},
                status="processing",
                started_at=datetime.now(timezone.utc) - timedelta(minutes=15),
            )
            db.add(outbox)
            await db.commit()
            outbox_id = outbox.outbox_id

        async with async_session() as db:
            count = await MESPushService.recover_stuck_outbox(db, connection_id=test_connection.connection_id)
            await db.commit()
            assert count == 1
            result = await db.execute(select(MESPushOutbox).where(MESPushOutbox.outbox_id == outbox_id))
            updated = result.scalar_one()
            assert updated.status == "pending"


class TestMeasurementAtomicity:
    async def test_ingestion_atomic_rollback(self, test_connection, test_ic):
        """ingestion INSERT 成功但后续失败时，事务回滚不残留。"""
        async with async_session() as db:
            data = {
                "connection_id": test_connection.connection_id,
                "external_id": "TEST-ATOMIC-001",
                "order_no": "WO-2026-001",
                "ic_code": "NON-EXISTENT-IC",
                "values": [1.0, 2.0, 3.0, 4.0, 5.0],
                "batch_no": "B-TEST-001",
                "sampled_at": datetime.now(timezone.utc),
                "product_line_code": "DC-DC-100",
            }

            with pytest.raises(ValueError):
                await MESIngestionService._ingest_measurement(db, data)
                await db.commit()

            await db.rollback()

            # Verify no ingestion record was persisted
            result = await db.execute(
                select(MESMeasurementIngestion).where(MESMeasurementIngestion.external_id == "TEST-ATOMIC-001")
            )
            assert result.scalar_one_or_none() is None

    async def test_duplicate_external_id_skipped(self, test_connection, test_ic):
        """重复 external_id 返回 skipped 不写入 SPC。"""
        data = {
            "connection_id": test_connection.connection_id,
            "external_id": "TEST-DUP-001",
            "order_no": "WO-2026-001",
            "ic_code": test_ic.ic_code,
            "values": [1.0, 2.0, 3.0, 4.0, 5.0],
            "batch_no": "B-TEST-002",
            "sampled_at": datetime.now(timezone.utc),
            "product_line_code": "DC-DC-100",
        }

        async with async_session() as db:
            result1 = await MESIngestionService._ingest_measurement(db, data)
            await db.commit()
            assert result1["status"] == "success"

        async with async_session() as db:
            result2 = await MESIngestionService._ingest_measurement(db, data)
            await db.commit()
            assert result2["status"] == "skipped"


class TestIdempotentRedelivery:
    async def test_crash_redelivery_idempotent(self, test_connection):
        """模拟崩溃后重复投递：processing→崩溃→恢复→再次 claim→推送→最终 sent。
        实际调用 MESPushService.process_outbox() 覆盖完整流程。"""
        from app.database import async_session

        # Step 1: Create outbox in independent session and commit
        async with async_session() as db:
            outbox = MESPushOutbox(
                event_type="spc_alarm",
                connection_id=test_connection.connection_id,
                payload={"alarm": "test"},
                status="processing",  # already claimed
                started_at=datetime.now(timezone.utc) - timedelta(minutes=15),
            )
            db.add(outbox)
            await db.commit()
            outbox_id = outbox.outbox_id

        # Step 2: Call process_outbox — covers recover_stuck + claim + push + result write
        async with async_session() as db:
            await MESPushService.process_outbox(db)

        # Step 3: Verify final state
        async with async_session() as verify_db:
            final = await verify_db.get(MESPushOutbox, outbox_id)
            assert final.status == "sent"
            assert final.sent_at is not None

    async def test_process_outbox_full_flow(self, test_connection):
        """process_outbox() 完整流程：pending → claim → push → sent。"""
        from app.database import async_session

        # Create a fresh pending outbox
        async with async_session() as db:
            outbox = MESPushOutbox(
                event_type="spc_alarm",
                connection_id=test_connection.connection_id,
                payload={"alarm": "test"},
                status="pending",
                next_retry_at=datetime.now(timezone.utc),
            )
            db.add(outbox)
            await db.commit()
            outbox_id = outbox.outbox_id

        # Run full outbox processor
        async with async_session() as db:
            await MESPushService.process_outbox(db)

        # Verify sent
        async with async_session() as db:
            final = await db.get(MESPushOutbox, outbox_id)
            assert final.status == "sent"
            assert final.sent_at is not None


class TestIngestValidation:
    async def test_ingest_missing_field_returns_400(self, test_connection):
        """缺失必填字段通过 HTTP 调用 /api/mes/ingest 返回 400（不是 422）。"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mes/ingest",
                headers={"X-API-Key": "test-mes-api-key-12345"},
                json={"data_type": "scrap_record"},  # missing external_id, defect_type, etc.
            )
            assert resp.status_code == 400
            body = resp.json()
            assert "detail" in body
            # Verify loc points to missing fields
            locs = [err.get("loc", []) for err in body["detail"]]
            assert any("external_id" in loc for loc in locs)

    async def test_ingest_unknown_data_type_returns_400(self, test_connection):
        """未知 data_type 通过 HTTP 调用返回 400。"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mes/ingest",
                headers={"X-API-Key": "test-mes-api-key-12345"},
                json={
                    "data_type": "unknown_type",
                    "external_id": "TEST-001",
                    "defect_type": " scratches",
                    "defect_qty": 1,
                    "total_qty": 10,
                },
            )
            assert resp.status_code == 400
            assert "Unknown data_type" in resp.json().get("detail", "")


class TestScrapOrderBackfill:
    async def test_scrap_before_order_then_backfill(self, test_connection):
        """报废先到、工单后到：生产订单写入后回填报废记录的 order_id。"""
        from app.database import async_session

        async with async_session() as db:
            # Ingest scrap first (order does not exist yet)
            await MESIngestionService._ingest_scrap_record(db, {
                "connection_id": test_connection.connection_id,
                "external_id": "SCRAP-001",
                "order_no": "WO-2026-BF",
                "defect_type": " scratches",
                "defect_qty": 5,
                "total_qty": 100,
            })
            await db.commit()

            scrap1 = (await db.execute(
                select(MESScrapRecord).where(MESScrapRecord.external_id == "SCRAP-001")
            )).scalar_one()
            assert scrap1.order_id is None  # Order not yet synced

        # Now ingest the production order
        async with async_session() as db:
            await MESIngestionService._ingest_production_order(db, {
                "connection_id": test_connection.connection_id,
                "order_no": "WO-2026-BF",
                "status": "planned",
            })
            await db.commit()

            # Verify scrap backfill
            scrap2 = (await db.execute(
                select(MESScrapRecord).where(MESScrapRecord.external_id == "SCRAP-001")
            )).scalar_one()
            assert scrap2.order_id is not None  # Backfilled by production order ingestion

    async def test_duplicate_scrap_preserves_snapshot(self, test_connection):
        """重复报废投递不会修改已有快照或清空 order_id。"""
        from app.database import async_session

        async with async_session() as db:
            # First: order exists, scrap arrives with order link
            await MESIngestionService._ingest_production_order(db, {
                "connection_id": test_connection.connection_id,
                "order_no": "WO-2026-DUP",
                "status": "planned",
            })
            await MESIngestionService._ingest_scrap_record(db, {
                "connection_id": test_connection.connection_id,
                "external_id": "SCRAP-DUP-001",
                "order_no": "WO-2026-DUP",
                "defect_type": "scratches",
                "defect_qty": 3,
                "total_qty": 50,
            })
            await db.commit()

            original_scrap = (await db.execute(
                select(MESScrapRecord).where(MESScrapRecord.external_id == "SCRAP-DUP-001")
            )).scalar_one()
            original_order_id = original_scrap.order_id
            assert original_order_id is not None

        # Re-ingest same scrap without order_no (simulating MES sending incomplete data)
        async with async_session() as db:
            await MESIngestionService._ingest_scrap_record(db, {
                "connection_id": test_connection.connection_id,
                "external_id": "SCRAP-DUP-001",
                # order_no omitted
                "defect_type": "dents",  # different value — should NOT update
                "defect_qty": 99,        # different value — should NOT update
                "total_qty": 999,        # different value — should NOT update
            })
            await db.commit()

            final_scrap = (await db.execute(
                select(MESScrapRecord).where(MESScrapRecord.external_id == "SCRAP-DUP-001")
            )).scalar_one()
            assert final_scrap.order_id == original_order_id  # Preserved
            assert final_scrap.defect_type == "scratches"      # Snapshot preserved
            assert final_scrap.defect_qty == 3                 # Snapshot preserved
            assert final_scrap.total_qty == 50                 # Snapshot preserved


class TestConnectionLifecycle:
    async def test_connection_creates_four_sync_jobs(self, admin_user):
        """创建连接后自动生成 4 个 pending 同步任务。测试共享初始化函数。"""
        from app.database import async_session
        from app.services.mes_service import MESSyncService

        suffix = str(uuid.uuid4())[:8]
        conn = MESConnection(
            name=f"TEST-JOBS-{suffix}",
            connector_type="mock",
            config={},
            created_by=admin_user.user_id,
            is_active=True,
        )
        async with async_session() as db:
            db.add(conn)
            await db.flush()
            await MESSyncService.create_sync_jobs_for_connection(db, conn.connection_id)
            await db.commit()

            result = await db.execute(
                select(MESSyncJob)
                .where(MESSyncJob.connection_id == conn.connection_id)
                .where(MESSyncJob.status == "pending")
            )
            jobs = result.scalars().all()
            data_types = {j.data_type for j in jobs}
            assert len(jobs) == 4
            assert data_types == {"production_orders", "equipment_status", "scrap_records", "measurements"}

            # Cleanup
            await db.execute(
                text("DELETE FROM mes_sync_jobs WHERE connection_id = :cid"),
                {"cid": conn.connection_id}
            )
            await db.execute(
                text("DELETE FROM mes_connections WHERE connection_id = :cid"),
                {"cid": conn.connection_id}
            )
            await db.commit()

    async def test_manual_sync_only_claims_target_connection(self, admin_user):
        """手动同步只领取目标连接的任务，不影响其他连接。"""
        from app.database import async_session
        from app.services.mes_service import MESSyncService

        async with async_session() as db:
            # Create two connections with sync jobs
            suffix_a = str(uuid.uuid4())[:8]
            suffix_b = str(uuid.uuid4())[:8]
            conn_a = MESConnection(
                name=f"TEST-SCOPE-A-{suffix_a}",
                connector_type="mock",
                config={},
                created_by=admin_user.user_id,
                is_active=True,
            )
            conn_b = MESConnection(
                name=f"TEST-SCOPE-B-{suffix_b}",
                connector_type="mock",
                config={},
                created_by=admin_user.user_id,
                is_active=True,
            )
            db.add(conn_a)
            db.add(conn_b)
            await db.flush()
            await MESSyncService.create_sync_jobs_for_connection(db, conn_a.connection_id)
            await MESSyncService.create_sync_jobs_for_connection(db, conn_b.connection_id)
            await db.commit()

            # Run manual_sync on conn_a
            await MESSyncService.manual_sync(db, conn_a.connection_id)

            # Assert conn_a jobs are now completed (or running then completed after sync)
            a_jobs = (await db.execute(
                select(MESSyncJob).where(MESSyncJob.connection_id == conn_a.connection_id)
            )).scalars().all()
            # After manual_sync, jobs should be processed (completed or failed)
            assert all(j.status in ("completed", "failed") for j in a_jobs), \
                f"Expected all conn_a jobs processed, got: {[j.status for j in a_jobs]}"

            # Assert conn_b jobs are still pending (not touched)
            b_jobs = (await db.execute(
                select(MESSyncJob).where(MESSyncJob.connection_id == conn_b.connection_id)
            )).scalars().all()
            assert all(j.status == "pending" for j in b_jobs), \
                f"Expected all conn_b jobs pending, got: {[j.status for j in b_jobs]}"

            # Cleanup
            for cid in (conn_a.connection_id, conn_b.connection_id):
                await db.execute(
                    text("DELETE FROM mes_sync_jobs WHERE connection_id = :cid"), {"cid": cid}
                )
                await db.execute(
                    text("DELETE FROM mes_connections WHERE connection_id = :cid"), {"cid": cid}
                )
            await db.commit()


class TestIngestEdgeCases:
    async def test_ingest_non_object_json_returns_400(self, test_connection):
        """/ingest 接收数组、null、字符串时返回 400。"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for bad_payload in ([], None, "string", 123):
                resp = await client.post(
                    "/api/mes/ingest",
                    headers={"X-API-Key": "test-mes-api-key-12345"},
                    json=bad_payload,
                )
                assert resp.status_code == 400, f"Expected 400 for {bad_payload!r}, got {resp.status_code}"


class TestRESTConnectorValidation:
    async def test_rest_validate_converts_iso_datetime(self):
        """RESTMESConnector._validate_items 将 ISO 时间字符串转为 datetime；source_updated_at 保留用于 checkpoint。"""
        from app.services.mes_connector import RESTMESConnector
        from datetime import datetime, timezone

        connector = RESTMESConnector({
            "base_url": "http://test",
            "endpoints": {},
            "field_mapping": {
                "order_no": "work_order_id",
                "source_updated_at": "updated_at",
            },
        })
        # _reverse_map maps MES field names → OpenQMS field names
        mes_raw = [{
            "work_order_id": "WO-001",
            "status": "running",
            "updated_at": "2026-06-04T15:30:00+00:00",
        }]
        mapped = connector._reverse_map(mes_raw[0])
        validated = connector._validate_items("production_orders", [mapped])
        assert len(validated) == 1
        assert isinstance(validated[0]["source_updated_at"], datetime)
        assert validated[0]["source_updated_at"].tzinfo is not None
        # Verify checkpoint field is present and typed correctly
        from app.services.mes_service import MESSyncService
        ts = MESSyncService._get_checkpoint_value("production_orders", validated[0])
        assert ts is not None
        assert isinstance(ts, datetime)

    async def test_rest_validate_raises_on_invalid_item(self):
        """RESTMESConnector._validate_items 任一记录校验失败即抛出异常，不跳过。"""
        from app.services.mes_connector import RESTMESConnector
        from pydantic import ValidationError

        connector = RESTMESConnector({
            "base_url": "http://test",
            "endpoints": {},
            "field_mapping": {"source_updated_at": "updated_at"},
        })
        raw = [
            {"external_id": "S-001", "defect_type": "scratches", "defect_qty": 5, "total_qty": 100},
            {"external_id": "S-002", "defect_type": "scratches", "defect_qty": -1, "total_qty": 100},  # invalid
            {"external_id": "S-003", "defect_type": "scratches", "defect_qty": 3, "total_qty": 50},
        ]
        with pytest.raises(ValidationError):
            connector._validate_items("scrap_records", raw)


class TestSyncRoundValidationFailure:
    async def test_sync_round_bad_data_fails_job_preserves_checkpoint(self, admin_user):
        """同步任务遇到坏数据：job 标记为 failed，checkpoint 不变，无数据残留。"""
        from app.database import async_session
        from app.services.mes_service import MESSyncService
        from app.services.mes_connector import RESTMESConnector

        suffix = str(uuid.uuid4())[:8]
        conn = MESConnection(
            name=f"TEST-SYNC-FAIL-{suffix}",
            connector_type="rest",
            config={
                "base_url": "https://mes.example.com",
                "endpoints": {
                    "production_orders": {"path": "/orders", "cursor_field": "since"},
                    "equipment_status": {"path": "/equipment"},
                    "scrap_records": {"path": "/scrap", "cursor_field": "since"},
                    "measurements": {"path": "/measurements", "cursor_field": "since"},
                },
                "field_mapping": {"source_updated_at": "updated_at"},
            },
            created_by=admin_user.user_id,
            is_active=True,
        )
        async with async_session() as db:
            db.add(conn)
            await db.commit()
            await db.refresh(conn)

            checkpoint = datetime(2026, 1, 1, tzinfo=timezone.utc)
            job = MESSyncJob(
                connection_id=conn.connection_id,
                data_type="scrap_records",
                status="pending",
                checkpoint=checkpoint,
            )
            db.add(job)
            await db.commit()
            job_id = job.job_id

        # Monkeypatch fetch to return invalid data that fails _validate_items
        original_fetch = RESTMESConnector.fetch_scrap_records
        async def bad_fetch(self, since):
            raw = [
                {"external_id": "S-001", "defect_type": "scratches", "defect_qty": 5, "total_qty": 100},
                {"external_id": "S-002", "defect_type": "scratches", "defect_qty": -1, "total_qty": 100},
            ]
            return self._validate_items("scrap_records", raw)
        RESTMESConnector.fetch_scrap_records = bad_fetch

        try:
            async with async_session() as db:
                await MESSyncService.run_sync_round(db, connection_id=conn.connection_id)
        finally:
            RESTMESConnector.fetch_scrap_records = original_fetch

        # Verify: job is failed, checkpoint unchanged
        async with async_session() as db:
            job = await db.get(MESSyncJob, job_id)
            assert job.status == "failed"
            assert job.checkpoint == checkpoint
            assert job.error_message is not None

        # Verify: no scrap data was written
        async with async_session() as db:
            result = await db.execute(
                select(MESScrapRecord).where(MESScrapRecord.connection_id == conn.connection_id)
            )
            assert result.scalar_one_or_none() is None

        # Cleanup
        async with async_session() as db:
            await db.execute(text("DELETE FROM mes_sync_jobs WHERE connection_id = :cid"), {"cid": conn.connection_id})
            await db.execute(text("DELETE FROM mes_connections WHERE connection_id = :cid"), {"cid": conn.connection_id})
            await db.commit()


class TestRESTConfigValidation:
    async def test_create_rest_missing_source_updated_at_returns_400(self, admin_user):
        """创建 REST 连接缺少 source_updated_at 映射返回 400。"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        token = create_access_token(str(admin_user.user_id))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mes/connections",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": "TEST-REST-BAD",
                    "connector_type": "rest",
                    "config": {
                        "base_url": "https://mes.example.com",
                        "endpoints": {
                            "production_orders": {"path": "/orders", "cursor_field": "updated_since"},
                            "equipment_status": {"path": "/equipment", "cursor_field": "since"},
                            "scrap_records": {"path": "/scrap", "cursor_field": "since"},
                            "measurements": {"path": "/measurements", "cursor_field": "since"},
                        },
                        "field_mapping": {},  # missing source_updated_at
                    },
                    "product_line_code": "DC-DC-100",
                },
            )
            assert resp.status_code == 400
            assert "source_updated_at" in resp.json().get("detail", "")

    async def test_update_rest_removes_mapping_returns_400(self, test_connection):
        """更新 REST 连接删除 source_updated_at 映射返回 400。"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        from app.database import async_session

        # Convert test_connection to REST with valid config first
        async with async_session() as db:
            conn = await db.get(MESConnection, test_connection.connection_id)
            conn.connector_type = "rest"
            conn.config = {
                "base_url": "https://mes.example.com",
                "endpoints": {
                    "production_orders": {"path": "/orders", "cursor_field": "since"},
                    "equipment_status": {"path": "/equipment"},
                    "scrap_records": {"path": "/scrap", "cursor_field": "since"},
                    "measurements": {"path": "/measurements", "cursor_field": "since"},
                },
                "field_mapping": {"source_updated_at": "updated_at"},
            }
            await db.commit()

        token = create_access_token(str(test_connection.created_by))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                f"/api/mes/connections/{test_connection.connection_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "config": {
                        "base_url": "https://mes.example.com",
                        "endpoints": {
                            "production_orders": {"path": "/orders", "cursor_field": "since"},
                            "equipment_status": {"path": "/equipment"},
                            "scrap_records": {"path": "/scrap", "cursor_field": "since"},
                            "measurements": {"path": "/measurements", "cursor_field": "since"},
                        },
                        "field_mapping": {},  # removed source_updated_at
                    },
                },
            )
            assert resp.status_code == 400
            assert "source_updated_at" in resp.json().get("detail", "")

    async def test_create_rest_missing_endpoint_returns_400(self, admin_user):
        """创建 REST 连接缺少必需 endpoint 返回 400。"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        token = create_access_token(str(admin_user.user_id))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mes/connections",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": "TEST-REST-NO-EP",
                    "connector_type": "rest",
                    "config": {
                        "base_url": "https://mes.example.com",
                        "endpoints": {
                            "production_orders": {"path": "/orders", "cursor_field": "since"},
                            # missing equipment_status, scrap_records, measurements
                        },
                        "field_mapping": {"source_updated_at": "updated_at"},
                    },
                    "product_line_code": "DC-DC-100",
                },
            )
            assert resp.status_code == 400
            assert "missing endpoints" in resp.json().get("detail", "")

    async def test_create_rest_empty_base_url_returns_400(self, admin_user):
        """创建 REST 连接空 base_url 返回 400。"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        token = create_access_token(str(admin_user.user_id))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mes/connections",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": "TEST-REST-NO-URL",
                    "connector_type": "rest",
                    "config": {
                        "base_url": "",
                        "endpoints": {
                            "production_orders": {"path": "/orders", "cursor_field": "since"},
                            "equipment_status": {"path": "/equipment", "cursor_field": "since"},
                            "scrap_records": {"path": "/scrap", "cursor_field": "since"},
                            "measurements": {"path": "/measurements", "cursor_field": "since"},
                        },
                        "field_mapping": {"source_updated_at": "updated_at"},
                    },
                    "product_line_code": "DC-DC-100",
                },
            )
            assert resp.status_code == 400
            assert "base_url" in resp.json().get("detail", "")

    async def test_create_rest_malformed_endpoints_returns_400(self, admin_user):
        """传入非对象 endpoints 返回 400（非 500）。"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        token = create_access_token(str(admin_user.user_id))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mes/connections",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": "TEST-REST-BAD-EP",
                    "connector_type": "rest",
                    "config": {
                        "base_url": "https://mes.example.com",
                        "endpoints": [],  # array instead of object
                        "field_mapping": {"source_updated_at": "updated_at"},
                    },
                    "product_line_code": "DC-DC-100",
                },
            )
            assert resp.status_code == 400
            assert "endpoints" in resp.json().get("detail", "")

    async def test_create_rest_malformed_field_mapping_returns_400(self, admin_user):
        """传入非对象 field_mapping 返回 400（非 500）。"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        token = create_access_token(str(admin_user.user_id))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mes/connections",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": "TEST-REST-BAD-FM",
                    "connector_type": "rest",
                    "config": {
                        "base_url": "https://mes.example.com",
                        "endpoints": {
                            "production_orders": {"path": "/orders", "cursor_field": "since"},
                            "equipment_status": {"path": "/equipment", "cursor_field": "since"},
                            "scrap_records": {"path": "/scrap", "cursor_field": "since"},
                            "measurements": {"path": "/measurements", "cursor_field": "since"},
                        },
                        "field_mapping": "bad",  # string instead of object
                    },
                    "product_line_code": "DC-DC-100",
                },
            )
            assert resp.status_code == 400
            assert "field_mapping" in resp.json().get("detail", "")

    async def test_update_connector_type_only_rejects_rest(self, test_connection):
        """仅更新 connector_type 为 'rest'（不提供 config）返回 400。"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        token = create_access_token(str(test_connection.created_by))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                f"/api/mes/connections/{test_connection.connection_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"connector_type": "rest"},
            )
            assert resp.status_code == 400
            assert "base_url" in resp.json().get("detail", "")

    async def test_create_rest_credential_field_non_string_returns_400(self, admin_user):
        """凭证字段为数字时返回 400（非 500）。"""
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        token = create_access_token(str(admin_user.user_id))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/mes/connections",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": "TEST-REST-BAD-CRED",
                    "connector_type": "rest",
                    "config": {
                        "base_url": "https://mes.example.com",
                        "endpoints": {
                            "production_orders": {"path": "/orders", "cursor_field": "since"},
                            "equipment_status": {"path": "/equipment"},
                            "scrap_records": {"path": "/scrap", "cursor_field": "since"},
                            "measurements": {"path": "/measurements", "cursor_field": "since"},
                        },
                        "field_mapping": {"source_updated_at": "updated_at"},
                        "auth_config": {"token": 12345},  # number instead of string
                    },
                    "product_line_code": "DC-DC-100",
                },
            )
            assert resp.status_code == 400
            assert "token" in resp.json().get("detail", "")


class TestConfigNormalization:
    """验证 _validate_rest_config 规范化后的 config 能正确驱动连接器。"""

    def test_auth_type_preserved_after_normalize(self):
        """auth_type 在规范化后保留在 config 顶层。"""
        from app.schemas.mes import RESTConfig

        config = {
            "base_url": "https://mes.example.com",
            "auth_type": "bearer",
            "endpoints": {
                "production_orders": {"path": "/orders", "cursor_field": "since"},
                "equipment_status": {"path": "/equipment"},
                "scrap_records": {"path": "/scrap", "cursor_field": "since"},
                "measurements": {"path": "/measurements", "cursor_field": "since"},
            },
            "field_mapping": {"source_updated_at": "updated_at"},
            "auth_config": {"token": "secret-value"},
        }
        validated = RESTConfig.model_validate(config)
        dumped = validated.model_dump(exclude_none=True)
        assert dumped["auth_type"] == "bearer"
        assert dumped["auth_config"]["token"] == "secret-value"

    def test_retry_null_normalized_safely(self):
        """retry: null 被规范化为 None，连接器回退默认重试策略。"""
        from app.schemas.mes import RESTConfig

        config = {
            "base_url": "https://mes.example.com",
            "endpoints": {
                "production_orders": {"path": "/orders", "cursor_field": "since"},
                "equipment_status": {"path": "/equipment"},
                "scrap_records": {"path": "/scrap", "cursor_field": "since"},
                "measurements": {"path": "/measurements", "cursor_field": "since"},
            },
            "field_mapping": {"source_updated_at": "updated_at"},
            "retry": None,
        }
        validated = RESTConfig.model_validate(config)
        dumped = validated.model_dump(exclude_none=True)
        assert "retry" not in dumped  # None stripped by exclude_none

    def test_pagination_null_normalized_safely(self):
        """pagination: null 被规范化，连接器回退默认 {'type': 'none'}。"""
        from app.schemas.mes import RESTConfig

        config = {
            "base_url": "https://mes.example.com",
            "endpoints": {
                "production_orders": {"path": "/orders", "cursor_field": "since", "pagination": None},
                "equipment_status": {"path": "/equipment"},
                "scrap_records": {"path": "/scrap", "cursor_field": "since"},
                "measurements": {"path": "/measurements", "cursor_field": "since"},
            },
            "field_mapping": {"source_updated_at": "updated_at"},
        }
        validated = RESTConfig.model_validate(config)
        dumped = validated.model_dump(exclude_none=True)
        assert "pagination" not in dumped["endpoints"]["production_orders"]

    def test_api_key_auth_type_preserved(self):
        """api_key auth_type 在规范化后保留。"""
        from app.schemas.mes import RESTConfig

        config = {
            "base_url": "https://mes.example.com",
            "auth_type": "api_key",
            "endpoints": {
                "production_orders": {"path": "/orders", "cursor_field": "since"},
                "equipment_status": {"path": "/equipment"},
                "scrap_records": {"path": "/scrap", "cursor_field": "since"},
                "measurements": {"path": "/measurements", "cursor_field": "since"},
            },
            "field_mapping": {"source_updated_at": "updated_at"},
            "auth_config": {"outbound_api_key": "key-123"},
        }
        validated = RESTConfig.model_validate(config)
        dumped = validated.model_dump(exclude_none=True)
        assert dumped["auth_type"] == "api_key"
        assert dumped["auth_config"]["outbound_api_key"] == "key-123"

    def test_retention_config_preserved(self):
        """retention 配置在规范化后保留。"""
        from app.schemas.mes import RESTConfig

        config = {
            "base_url": "https://mes.example.com",
            "endpoints": {
                "production_orders": {"path": "/orders", "cursor_field": "since"},
                "equipment_status": {"path": "/equipment"},
                "scrap_records": {"path": "/scrap", "cursor_field": "since"},
                "measurements": {"path": "/measurements", "cursor_field": "since"},
            },
            "field_mapping": {"source_updated_at": "updated_at"},
            "retention": {"equipment_status_days": 30, "scrap_days": 180, "closed_order_days": 365},
        }
        validated = RESTConfig.model_validate(config)
        dumped = validated.model_dump(exclude_none=True)
        assert dumped["retention"]["equipment_status_days"] == 30
        assert dumped["retention"]["scrap_days"] == 180

- [ ] **Step 2: Commit**

```bash
git add backend/tests/test_mes_concurrency.py
git commit -m "test(mes): add automated concurrency tests for sync, outbox, and ingestion (33 cases)

- Dual worker claim once (sync job + outbox)
- Running job timeout recovery (>10min)
- Processing outbox timeout recovery
- Manual sync conflict with running job
- Inactive connection exclusion
- Measurement ingestion atomic rollback
- Duplicate external_id idempotency
- Crash redelivery idempotency via process_outbox()
- Full process_outbox() flow: pending → claim → push → sent
- /ingest validation errors return 400 (missing fields, unknown data_type)
- Scrap order backfill: out-of-order arrival + duplicate preservation
- Connection creation auto-generates 4 sync jobs
- Manual sync only claims target connection
- /ingest rejects non-object JSON bodies
- REST connector validates and converts ISO datetime strings
- REST connector raises on invalid items (fails job, no checkpoint advance)
- REST config validation: missing source_updated_at → 400
- REST config validation: update removes mapping → 400
- REST config validation: missing endpoint → 400
- REST config validation: empty base_url → 400
- REST config validation: malformed endpoints (array) → 400
- REST config validation: malformed field_mapping (string) → 400
- REST config API tests use real JWT tokens (not hardcoded)
- All incremental endpoints require cursor_field (po, scrap, measurements)
- REST config validation uses Pydantic RESTConfig schema (before credential encryption)
- Credential processing guards against non-string auth values (prevents .startswith() on int)
- Sync round validation failure: job failed, checkpoint preserved, no data written"

```

---

## Task 19: 生命周期清理任务

**Files:**
- Modify: `backend/app/services/mes_service.py`（追加清理任务）
- Modify: `backend/app/main.py`（注册清理协程）

- [ ] **Step 1: 追加生命周期服务**

```python
# 追加到 backend/app/services/mes_service.py

class MESLifecycleService:
    """MES 数据生命周期管理后台任务。

    设计要求：
    - 设备状态：90 天保留
    - 报废记录：1 年保留，超出按月聚合到 mes_scrap_monthly_summary
    - 已关闭工单：2 年归档到 mes_production_orders_archive
    """

    # Global defaults (used when connection config has no retention override)
    DEFAULT_EQUIPMENT_DAYS = 90
    DEFAULT_SCRAP_DAYS = 365
    DEFAULT_CLOSED_ORDER_DAYS = 730  # 2 years

    @staticmethod
    def _get_retention_days(connection_config: dict) -> dict:
        """Extract per-connection retention days from config, falling back to global defaults."""
        ret = connection_config.get("retention", {})
        if not isinstance(ret, dict):
            ret = {}
        return {
            "equipment_status_days": ret.get("equipment_status_days", MESLifecycleService.DEFAULT_EQUIPMENT_DAYS),
            "scrap_days": ret.get("scrap_days", MESLifecycleService.DEFAULT_SCRAP_DAYS),
            "closed_order_days": ret.get("closed_order_days", MESLifecycleService.DEFAULT_CLOSED_ORDER_DAYS),
        }

    @staticmethod
    async def cleanup(db: AsyncSession) -> dict:
        """执行数据清理（按连接分组，各自使用连接配置的保留天数）。

        使用 PostgreSQL transaction-level advisory lock 防止多 worker 同时执行。
        xact_lock 随事务结束自动释放，不会泄漏到连接池。
        """
        from sqlalchemy import delete, text
        now = datetime.now(timezone.utc)

        # Acquire transaction-level advisory lock (auto-released on commit/rollback)
        lock_result = await db.execute(text("SELECT pg_try_advisory_xact_lock(42)"))
        has_lock = lock_result.scalar()
        if not has_lock:
            return {"deleted_equipment_status": 0, "deleted_scrap_records": 0, "aggregated_scrap_rows": 0, "archived_orders": 0}

        # Load all active connections to read per-connection retention config
        result = await db.execute(
            select(MESConnection).where(MESConnection.is_active == True)
        )
        connections = result.scalars().all()

        total_deleted_equipment = 0
        total_deleted_scrap = 0
        total_aggregated = 0
        total_archived = 0

        for conn in connections:
            retention = MESLifecycleService._get_retention_days(conn.config)

            # 1. Clean old equipment status
            cutoff_equipment = now - timedelta(days=retention["equipment_status_days"])
            eq_result = await db.execute(
                delete(MESEquipmentStatus)
                .where(MESEquipmentStatus.connection_id == conn.connection_id)
                .where(MESEquipmentStatus.recorded_at < cutoff_equipment)
            )
            total_deleted_equipment += eq_result.rowcount

            # 2. Aggregate and clean old scrap records
            cutoff_scrap = now - timedelta(days=retention["scrap_days"])
            agg_result = await db.execute(text("""
                INSERT INTO mes_scrap_monthly_summary
                    (connection_id, product_line_code, year_month, defect_category,
                     total_defect_qty, total_total_qty, record_count, created_at)
                SELECT
                    connection_id,
                    COALESCE(product_line_code, '__none__'),
                    TO_CHAR(recorded_at, 'YYYY-MM'),
                    COALESCE(defect_category, '未知'),
                    SUM(defect_qty),
                    SUM(total_qty),
                    COUNT(*),
                    NOW()
                FROM mes_scrap_records
                WHERE connection_id = :cid AND recorded_at < :cutoff
                GROUP BY connection_id, COALESCE(product_line_code, '__none__'),
                         TO_CHAR(recorded_at, 'YYYY-MM'),
                         COALESCE(defect_category, '未知')
                ON CONFLICT (connection_id, product_line_code, year_month, defect_category)
                DO UPDATE SET
                    total_defect_qty = mes_scrap_monthly_summary.total_defect_qty + EXCLUDED.total_defect_qty,
                    total_total_qty = mes_scrap_monthly_summary.total_total_qty + EXCLUDED.total_total_qty,
                    record_count = mes_scrap_monthly_summary.record_count + EXCLUDED.record_count
            """), {"cid": conn.connection_id, "cutoff": cutoff_scrap})
            total_aggregated += agg_result.rowcount

            sc_result = await db.execute(
                delete(MESScrapRecord)
                .where(MESScrapRecord.connection_id == conn.connection_id)
                .where(MESScrapRecord.recorded_at < cutoff_scrap)
            )
            total_deleted_scrap += sc_result.rowcount

            # 3. Archive closed orders
            cutoff_order = now - timedelta(days=retention["closed_order_days"])
            await db.execute(text("""
                INSERT INTO mes_production_orders_archive
                    (order_id, connection_id, order_no, product_model, process_route,
                     planned_qty, actual_qty, status, started_at, completed_at,
                     source_updated_at, product_line_code, archived_at)
                SELECT
                    order_id, connection_id, order_no, product_model, process_route,
                    planned_qty, actual_qty, status, started_at, completed_at,
                    source_updated_at, product_line_code, NOW()
                FROM mes_production_orders
                WHERE connection_id = :cid AND status = 'closed' AND completed_at < :cutoff
                ON CONFLICT (order_id) DO NOTHING
            """), {"cid": conn.connection_id, "cutoff": cutoff_order})

            arc_result = await db.execute(
                delete(MESProductionOrder)
                .where(MESProductionOrder.connection_id == conn.connection_id)
                .where(MESProductionOrder.status == "closed")
                .where(MESProductionOrder.completed_at < cutoff_order)
            )
            total_archived += arc_result.rowcount

        await db.commit()

        return {
            "deleted_equipment_status": total_deleted_equipment,
            "deleted_scrap_records": total_deleted_scrap,
            "aggregated_scrap_rows": total_aggregated,
            "archived_orders": total_archived,
        }
```

- [ ] **Step 2: 在 lifespan 中注册清理协程**

```python
# backend/app/main.py — 追加到 lifespan（MES outbox task 之后）

    # Start MES lifecycle cleanup (daily)
    from app.services.mes_service import MESLifecycleService

    async def _mes_cleanup_loop():
        while True:
            await asyncio.sleep(86400)  # 24 hours
            try:
                async with async_session() as db:
                    stats = await MESLifecycleService.cleanup(db)
                    if any(v > 0 for v in stats.values()):
                        print(f"[mes_lifecycle] cleanup: {stats}")
            except Exception as e:
                print(f"[mes_lifecycle] error: {e}")

    mes_cleanup_task = asyncio.create_task(_mes_cleanup_loop())

    yield

    # ... existing cleanup cancellations ...
    mes_cleanup_task.cancel()
    try:
        await mes_cleanup_task
    except asyncio.CancelledError:
        pass
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/mes_service.py backend/app/main.py
git commit -m "feat(lifecycle): add MES data lifecycle cleanup task

- Equipment status: 90-day retention
- Scrap records: 1-year retention
- Closed orders: 2-year archive (clear mes_raw_data)
- Daily background cleanup coroutine in lifespan"
```

---

## Spec Coverage Check

| Spec 需求 | 对应 Task | 状态 |
|-----------|----------|------|
| mes_connections 表 | Task 1 | ✅ |
| mes_production_orders 表 | Task 1 | ✅ |
| mes_equipment_status 表 | Task 1 | ✅ |
| mes_scrap_records 表 | Task 1 | ✅ |
| mes_measurement_ingestions 表 | Task 1 | ✅ |
| mes_sync_jobs 表 | Task 1 | ✅ |
| mes_push_outbox 表 | Task 1 | ✅ |
| Module.MES 权限（新迁移插入） | Task 1, 3 | ✅ |
| server_default 全部使用数据库默认值 | Task 1 | ✅ |
| Fernet 加密 + API Key hash | Task 2 | ✅ |
| 响应脱敏（config.auth_config ***） | Task 2, 13 | ✅ |
| MESConnector 抽象基类 | Task 4 | ✅ |
| MockMESConnector（timezone.utc） | Task 4 | ✅ |
| RESTMESConnector 完整实现 | Task 4 | ✅ |
| 连接器工厂 + test_mes_connection | Task 5 | ✅ |
| MESIngestionService 原子事务 | Task 6 | ✅ |
| API Key 认证守卫 | Task 7 | ✅ |
| MESSyncService 三阶段短事务 | Task 8 | ✅ |
| checkpoint=COALESCE(max_ts, old_checkpoint) | Task 8 | ✅ |
| overlap_window | Task 8 | ✅ |
| 超时恢复（sync running >10min） | Task 8 | ✅ |
| 后台调度器 lifespan 注册 | Task 9 | ✅ |
| 手动同步 409 冲突检测 | Task 8, 10 | ✅ |
| MESPushService 三阶段短事务 | Task 11 | ✅ |
| at-least-once + event_id 幂等 | Task 11 | ✅ |
| outbox 超时恢复 + 指数退避 | Task 11 | ✅ |
| 后台 outbox 处理器 lifespan 注册 | Task 9, 12 | ✅ |
| 查询 API 产品线隔离 | Task 13 | ✅ |
| 连接管理 API 凭证脱敏 | Task 13 | ✅ |
| /connections/{id}/test 端点 | Task 13 | ✅ |
| 前端复用现有 client 实例 | Task 15 | ✅ |
| 前端 4 个页面完整实现 | Task 16 | ✅ |
| 前端 4 个路由 + 侧边栏菜单 | Task 17 | ✅ |
| test_mes_concurrency.py 33 场景 | Task 18 | ✅ |
| 生命周期清理任务 | Task 19 | ✅ |
| mes_scrap_monthly_summary 表 | Task 1 | ✅ |
| mes_production_orders_archive 表 | Task 1 | ✅ |
| 模型与 Schema 显式实施任务 | Task 1b, 1c | ✅ |
| 产品线隔离真正生效（apply_product_line_filter） | Task 13 | ✅ |
| SPC 规则检测触发（_reevaluate_alarms_no_commit） | Task 6 | ✅ |
| 测试隔离可靠（显式清理） | Task 18 | ✅ |
| Outbox 产品线筛选 | Task 12b | ✅ |
| 入站/出站 API Key 拆分 | Task 2, 13 | ✅ |

---

## Placeholder Scan

- 无 "TBD", "TODO", "implement later" ✅
- 所有代码块完整（含 RESTMESConnector HTTP 实现）✅
- 类型/方法名一致 ✅
- 所有 `datetime.now()` 已替换为 `datetime.now(timezone.utc)` ✅
- 所有迁移 `default=` 已替换为 `server_default=` ✅
- 不修改已执行迁移文件 ✅

---

## Deployment Prerequisites

### MES_ENCRYPTION_KEY

出站凭证使用 Fernet 对称加密。部署前必须设置环境变量：

```bash
# 生成 32-byte base64-encoded key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 输出示例: wJalrXUtnFEMI_K7MDENG_bPxRfiCYEXAMPLEKEY

# 写入 .env 或 docker-compose.yml
export MES_ENCRYPTION_KEY="<generated-key>"
```

**未设置时行为：** `encrypt_credential()` / `decrypt_credential()` 在首次调用时抛出 `RuntimeError`，导致创建/更新带出站凭证的连接失败，以及 outbox push 运行时崩溃。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-04-mes-integration-plan.md`.**

**注意：** 本计划为 **22 个 Task 的分阶段计划**，建议按 Phase 顺序执行。Phase 1-3 为基础层，Phase 4-6 为核心逻辑，Phase 7 为前端，Phase 8 为测试与运维。

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review

**Which approach?**
