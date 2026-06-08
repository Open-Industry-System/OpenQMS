# PLM 集成连接器设计文档

> **日期**: 2026-06-08
> **版本**: v1.0
> **方案**: 方案 C — 独立但相似（复用 MES 已验证模式，保持数据独立）
> **前置模块**: MES 集成连接器（已完成，2026-06-05）

---

## 1. 目标与范围

### 1.1 目标
实现 PLM（产品生命周期管理）系统与 OpenQMS 的双向集成，打通设计数据与质量管理数据，让 BOM、零部件版本、工程变更单等设计信息直接驱动质量分析。

### 1.2 范围
- **Inbound（拉取）**: 从 PLM 同步 Parts、BOMs、Change Orders 到 OpenQMS
- **Outbound（推送）**: 将变更影响分析结果、SC 状态回写 PLM（可选）
- **联动**: BOM → FMEA 结构树导入、ECN → 变更影响分析、Part → Special Characteristic 关联
- **不在这个版本**: PLM 厂商专用适配器（西门子 TC、达索 ENOVIA、PTC Windchill）仅预留接口，先实现 mock + REST 通用适配器

### 1.3 验收标准
- [ ] 6 张数据表 + Alembic 迁移
- [ ] PLMConnector ABC + Mock + REST 实现
- [ ] 三阶段短事务同步（parts → boms → change_orders 顺序）
- [ ] 4 页前端（Connections + Dashboard + Parts + Change Orders）
- [ ] BOM 一键导入 DFMEA 结构树
- [ ] ECN approved 自动触发变更影响分析
- [ ] 产品线隔离 + 权限控制

---

## 2. 架构概述

### 2.1 设计原则
1. **复用已验证模式** — 直接复用 MES 的连接器 ABC、三阶段短事务同步、Outbox 推送、凭证加密
2. **数据独立** — PLM 拥有独立的连接/数据/同步表，不与 MES 混合
3. **渐进式同步** — Parts 先同步，BOMs 依赖 Parts，Change Orders 依赖 Parts/BOMs
4. **双向联动** — PLM 数据驱动质量分析，质量结果反哺设计决策

### 2.2 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                       PLM 集成连接器                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────────┐  │
│  │PLMConnector │   │PLMIngestion  │   │ PLMSyncService  │  │
│  │  (ABC)      │◄──►│   Service    │◄──►│ (3-phase tx)  │  │
│  └──────┬──────┘   └──────┬───────┘   └────────┬────────┘  │
│         │                 │                    │           │
│    ┌────┴────┐       ┌────┴────┐         ┌────┴────┐      │
│    │  Mock   │       │ BOM/Part│         │sync_jobs│      │
│    │  REST   │       │   ECN   │         │ outbox  │      │
│    └─────────┘       └─────────┘         └─────────┘      │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              与 OpenQMS 现有模块联动                    │  │
│  │  BOM ──► FMEA 结构树自动填充                           │  │
│  │  ECN ──► 触发变更影响分析（知识图谱 BFS）              │  │
│  │  Part ──► Special Characteristic 关联                 │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 数据模型（6 张表）

### 3.1 `plm_connections`

与 `mes_connections` 结构一致。

| 字段 | 类型 | 说明 |
|------|------|------|
| connection_id | UUID PK | 主键 |
| name | String(100) | 连接名称 |
| connector_type | String(50) | mock / rest / siemens_tc / dassault_enovia / ptc_windchill |
| config | JSONB | 连接配置（含端点、字段映射、认证） |
| is_active | Boolean | 是否启用 |
| product_line_code | String(50) FK | 产品线隔离 |
| created_by | UUID FK | 创建人 |
| created_at / updated_at | DateTime | 时间戳 |

### 3.2 `plm_parts` — 零部件主数据

| 字段 | 类型 | 说明 |
|------|------|------|
| part_id | UUID PK | 主键 |
| connection_id | UUID FK | 所属连接 |
| external_id | String(100) | PLM 系统内部 ID |
| part_number | String(100) | 零部件编码（如 DC-DC-100-PCB-001） |
| name | String(200) | 名称 |
| revision | String(20) | 版本号，默认 "A" |
| material | String(100) | 材料 |
| specification | Text | 规格 |
| status | String(20) | active / obsolete / pending |
| is_safety_related | Boolean | 安全特性标识 |
| is_key_characteristic | Boolean | 关键特性标识 |
| source_updated_at | DateTime | PLM 更新时间戳 |
| product_line_code | String(50) FK | 产品线 |
| plm_raw_data | JSONB | 原始数据 |

**唯一约束**: `(connection_id, part_number)`

### 3.3 `plm_boms` — BOM 结构（邻接表）

| 字段 | 类型 | 说明 |
|------|------|------|
| bom_id | UUID PK | 主键 |
| connection_id | UUID FK | 所属连接 |
| external_id | String(100) | PLM 内部 ID |
| parent_part_number | String(100) | 父零部件编码 |
| child_part_number | String(100) | 子零部件编码 |
| quantity | Numeric(10,4) | 数量 |
| revision | String(20) | BOM 版本 |
| level | Integer | BOM 层级（1=顶层） |
| source_updated_at | DateTime | PLM 更新时间戳 |
| product_line_code | String(50) FK | 产品线 |
| plm_raw_data | JSONB | 原始数据 |

**唯一约束**: `(connection_id, parent_part_number, child_part_number, revision)`

### 3.4 `plm_change_orders` — 工程变更单（ECN）

| 字段 | 类型 | 说明 |
|------|------|------|
| change_id | UUID PK | 主键 |
| connection_id | UUID FK | 所属连接 |
| external_id | String(100) | PLM 内部 ID |
| change_number | String(50) | 变更单号（如 ECN-2026-001） |
| title | String(200) | 标题 |
| description | Text | 描述 |
| change_type | String(50) | design / process / material / supplier |
| status | String(20) | draft → pending_approval → approved → implemented → closed |
| priority | String(20) | urgent / high / normal / low |
| affected_part_numbers | JSONB | 受影响的零部件编码数组 |
| proposed_changes | JSONB | 变更前后对比 `{field: {old, new}}` |
| requested_by | String(100) | 申请人 |
| approved_by | String(100) | 批准人 |
| planned_implementation_date | DateTime | 计划实施日期 |
| actual_implementation_date | DateTime | 实际实施日期 |
| source_updated_at | DateTime | PLM 更新时间戳 |
| product_line_code | String(50) FK | 产品线 |
| plm_raw_data | JSONB | 原始数据 |

**唯一约束**: `(connection_id, change_number)`

### 3.5 `plm_sync_jobs`

与 `mes_sync_jobs` 结构一致。同步数据类型：`parts` | `boms` | `change_orders`。

### 3.6 `plm_push_outbox`

与 `mes_push_outbox` 结构一致。

---

## 4. 连接器层

### 4.1 PLMConnector ABC

```python
class PLMConnector(ABC):
    @abstractmethod
    async def fetch_parts(self, since: datetime) -> list[dict]: ...
    @abstractmethod
    async def fetch_boms(self, since: datetime) -> list[dict]: ...
    @abstractmethod
    async def fetch_change_orders(self, since: datetime) -> list[dict]: ...
    @abstractmethod
    async def push_change_status(self, change_number: str, status: str, data: dict) -> dict: ...
```

### 4.2 MockPLMConnector
生成符合 DC-DC-100 产品线的模拟数据：
- **Parts**: PCB、MOSFET、电感、电容、外壳、散热器等 12 个零部件
- **BOMs**: 3 级 BOM 结构（DC-DC-100 → 子系统 → 组件 → 零件）
- **Change Orders**: 5 张模拟 ECN（设计变更、材料替代、工艺调整等）

### 4.3 RESTPLMConnector
复用 MES 的 HTTP 核心逻辑（`_request`、分页、重试、认证），但保持独立类：
- 端点配置：`parts`、`boms`、`change_orders`
- 字段映射：PLM 厂商字段 → OpenQMS 标准字段
- 校验 Schema：`PLMIngestPart`、`PLMIngestBOM`、`PLMIngestChangeOrder`

---

## 5. 同步与摄入服务

### 5.1 PLMIngestionService
- 接收 `AsyncSession`，由调用方控制事务（与 MES 同模式）
- `_ingest_part`: `pg_insert PLMPart ON CONFLICT (connection_id, part_number) DO UPDATE`
- `_ingest_bom`: `pg_insert PLMBOM ON CONFLICT (...) DO UPDATE`
- `_ingest_change_order`: `pg_insert PLMChangeOrder ON CONFLICT (...) DO UPDATE`
  - 若状态从非 approved 变为 approved，触发变更影响分析

### 5.2 PLMSyncService
完全复用 MESSyncService 的三阶段短事务模式。

**同步顺序控制**（PLM 特有）：
| 数据类型 | next_run_at | 说明 |
|---------|-------------|------|
| parts | now() | 第一轮同步 |
| boms | now() + 2min | 等 parts 同步完成 |
| change_orders | now() + 4min | 等 parts + boms 同步完成 |

### 5.3 ECN 自动触发变更影响分析

当 ECN 状态变为 `approved` 时：

```python
for part_number in change_order.affected_part_numbers:
    fmea_nodes = await find_fmea_nodes_by_part_number(db, part_number)
    for node in fmea_nodes:
        await change_impact_service.analyze(
            fmea_id=node.fmea_id,
            node_id=node.id,
            change_type="plm_ecn",
            change_ref=change_order.change_number,
        )
```

---

## 6. API 路由

```
POST   /api/plm/connections                    # 创建连接
GET    /api/plm/connections                    # 列表（分页+产品线过滤）
GET    /api/plm/connections/{id}               # 详情
PUT    /api/plm/connections/{id}               # 更新
DELETE /api/plm/connections/{id}               # 删除
POST   /api/plm/connections/{id}/test          # 连通性测试
POST   /api/plm/connections/{id}/sync          # 手动触发同步

GET    /api/plm/parts                          # 零部件列表
GET    /api/plm/parts/{part_id}                # 零部件详情（含 BOM 父子）
GET    /api/plm/boms                           # BOM 列表
GET    /api/plm/boms/tree/{part_number}        # BOM 树形展开
GET    /api/plm/change-orders                  # ECN 列表
GET    /api/plm/change-orders/{id}             # ECN 详情（含影响分析结果）
GET    /api/plm/dashboard                      # 概览统计

POST   /api/plm/parts/{part_id}/link-fmea                  # Part 关联 FMEA 节点
POST   /api/plm/change-orders/{id}/impact-analysis          # 手动触发影响分析
POST   /api/plm/boms/{part_number}/import-to-fmea           # BOM 导入 DFMEA
```

---

## 7. 前端页面

| 页面 | 路由 | 核心功能 |
|------|------|---------|
| PLM 连接管理 | `/plm/connections` | CRUD + 测试 + 手动同步 |
| PLM 数据看板 | `/plm/dashboard` | KPI 卡片 + 快速入口 |
| 零部件管理 | `/plm/parts` | 列表 + 搜索 + 详情 Drawer（BOM 树 + SC 标识） |
| 工程变更单 | `/plm/change-orders` | ECN 列表 + 状态标签 + 详情（变更内容 + 影响分析面板） |

---

## 8. 与现有模块联动

### 8.1 BOM → FMEA 结构树导入
- Part 详情页或 BOM 页提供 **"导入到 DFMEA"** 按钮
- 后端遍历 BOM 邻接表 → 按 `level` 构建树 → 写入 `fmea_documents.graph_data.nodes`
- 节点类型映射：level 1=system, level 2=subsystem, level 3+=component

### 8.2 ECN → 变更影响分析
- **自动触发**: ECN 状态变为 `approved`
- **手动触发**: ECN 详情页 **"运行影响分析"** 按钮
- 结果展示：受影响 FMEA 列表 + 高风险节点红色高亮 + 建议优化措施

### 8.3 Part → Special Characteristic 关联
- `is_safety_related=True` 或 `is_key_characteristic=True` 的 Part 同步时，自动在 SC 模块创建待确认条目
- Part 详情页显示关联 SC 记录
- SC 审批完成后通过 `plm_push_outbox` 回写 PLM

---

## 9. 技术决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 方案 | C（独立但相似） | 零重构风险，数据隔离好，核心模式复用 |
| BOM 存储 | 邻接表 | 支持多级树，查询简单，易于导入 FMEA |
| affected_part_numbers | JSONB 数组 | 简单够用，若未来需复杂查询再拆关联表 |
| ECN 触发时机 | approved | 在正式实施前给质量团队预留分析时间 |
| 同步顺序 | 延迟 next_run_at | 无需复杂依赖图，利用现有调度机制 |
| 厂商适配器 | 预留接口 | 先验证通用 REST 模式，再扩展专用适配器 |

---

## 10. 文件清单

### 后端新增
- `backend/alembic/versions/031_add_plm_tables.py`
- `backend/app/models/plm.py`
- `backend/app/schemas/plm.py`
- `backend/app/services/plm_connector.py`
- `backend/app/services/plm_service.py`
- `backend/app/api/plm.py`

### 后端修改
- `backend/app/core/permissions.py` — 新增 `Module.PLM`
- `backend/app/core/product_line_filter.py` — 添加 `"plm": "product_line_code"`
- `backend/app/models/__init__.py` — 导出 PLM 模型
- `backend/app/main.py` — 注册 plm_router + 后台协程

### 前端新增
- `frontend/src/pages/plm/PLMConnectionsPage.tsx`
- `frontend/src/pages/plm/PLMDashboardPage.tsx`
- `frontend/src/pages/plm/PLMPartsPage.tsx`
- `frontend/src/pages/plm/PLMChangeOrdersPage.tsx`
- `frontend/src/api/plm.ts`
- `frontend/src/types/plm.ts`

### 前端修改
- `frontend/src/App.tsx` — 新增 PLM 路由
- `frontend/src/components/layout/AppLayout.tsx` — 新增 PLM 侧边栏菜单
