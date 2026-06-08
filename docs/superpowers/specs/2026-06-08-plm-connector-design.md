# PLM 集成连接器设计文档

> **日期**: 2026-06-08
> **版本**: v2.0
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
- [ ] 9 张数据表 + Alembic 迁移
- [ ] PLMConnector ABC + Mock + REST 实现
- [ ] 三阶段短事务同步（parts → boms → change_orders 顺序）
- [ ] 4 页前端（Connections + Dashboard + Parts + Change Orders）
- [ ] BOM 一键导入 DFMEA 结构树（含 nodes + edges）
- [ ] ECN approved 自动排队变更影响分析任务（后台 worker 执行）
- [ ] 产品线隔离 + 完整权限控制（路由守卫 + 前端菜单 + 种子数据）
- [ ] 后端测试：幂等同步测试、多 revision 测试、权限测试

---

## 2. 架构概述

### 2.1 设计原则
1. **复用已验证模式** — 直接复用 MES 的连接器 ABC、三阶段短事务同步、Outbox 推送、凭证加密
2. **数据独立** — PLM 拥有独立的连接/数据/同步表，不与 MES 混合
3. **渐进式同步** — Parts 先同步，BOMs 依赖 Parts，Change Orders 依赖 Parts/BOMs
4. **不破坏已有事务边界** — ECN 触发分析不直接在摄入事务内调用会 commit() 的外部服务
5. **版本完整性** — Part 和 BOM 均支持 revision，不丢失历史版本
6. **可追溯关联** — PLM Part ↔ FMEA 节点通过独立关联表映射，不假设 FMEA 节点 schema 包含 PLM 字段

### 2.2 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                       PLM 集成连接器                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────────┐      │
│  │PLMConnector  │   │PLMIngestion  │   │ PLMSyncService  │      │
│  │  (ABC)       │◄──►│   Service    │◄──►│ (3-phase tx)  │      │
│  └──────┬───────┘   └──────┬───────┘   └────────┬────────┘      │
│         │                  │                    │                │
│    ┌────┴────┐        ┌────┴────┐         ┌────┴────┐           │
│    │  Mock   │        │ BOM/Part│         │sync_jobs│           │
│    │  REST   │        │   ECN   │         │ outbox  │           │
│    └─────────┘        └─────────┘         └─────────┘           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              关联表（打通 PLM ↔ OpenQMS）                │    │
│  │  plm_part_fmea_links    — Part ↔ FMEA 节点              │    │
│  │  plm_part_sc_links      — Part ↔ SC（含 pending 状态）   │    │
│  │  plm_change_impact_tasks — ECN 分析任务队列              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              与 OpenQMS 现有模块联动                      │    │
│  │  BOM ──► FMEA 结构树（nodes + edges）                   │    │
│  │  ECN ──► 变更影响分析任务（后台 worker）                 │    │
│  │  Part ──► SC 待确认条目（工程师确认后写入 SC 表）        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 数据模型（9 张表）

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

### 3.2 `plm_parts` — 零部件主数据（支持多版本）

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
| product_line_code | String(50) FK, nullable | 产品线（Ingestion 层从 connection 强制拷贝） |
| plm_raw_data | JSONB | 原始数据 |

**唯一约束**: `(connection_id, part_number, revision)` — 同一零部件的不同版本共存，不覆盖。

### 3.3 `plm_boms` — BOM 结构（邻接表，含父子版本）

| 字段 | 类型 | 说明 |
|------|------|------|
| bom_id | UUID PK | 主键 |
| connection_id | UUID FK | 所属连接 |
| external_id | String(100) | PLM 内部 ID |
| parent_part_number | String(100) | 父零部件编码 |
| parent_revision | String(20) | 父零部件版本，默认 "A" |
| child_part_number | String(100) | 子零部件编码 |
| child_revision | String(20) | 子零部件版本，默认 "A" |
| quantity | Numeric(10,4) | 数量 |
| bom_revision | String(20) | BOM 版本 |
| level | Integer | BOM 层级（1=顶层） |
| source_updated_at | DateTime | PLM 更新时间戳 |
| product_line_code | String(50) FK, nullable | 产品线（Ingestion 层从 connection 强制拷贝） |
| plm_raw_data | JSONB | 原始数据 |

**唯一约束**: `(connection_id, parent_part_number, parent_revision, child_part_number, child_revision, bom_revision)` — 精确到版本，避免 A 版 BOM 覆盖 B 版 BOM。

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
| affected_part_numbers | JSONB | 受影响的零部件编码数组（含 revision，如 `["DC-DC-100-PCB-001|A", ...]`） |
| proposed_changes | JSONB | 变更前后对比 `{field: {old, new}}` |
| requested_by | String(100) | 申请人 |
| approved_by | String(100) | 批准人 |
| planned_implementation_date | DateTime | 计划实施日期 |
| actual_implementation_date | DateTime | 实际实施日期 |
| source_updated_at | DateTime | PLM 更新时间戳 |
| product_line_code | String(50) FK, nullable | 产品线（Ingestion 层从 connection 强制拷贝） |
| plm_raw_data | JSONB | 原始数据 |

**唯一约束**: `(connection_id, change_number)`

### 3.5 `plm_sync_jobs`

与 `mes_sync_jobs` 结构一致。同步数据类型：`parts` | `boms` | `change_orders`。

### 3.6 `plm_push_outbox`

与 `mes_push_outbox` 结构一致。

### 3.7 `plm_change_impact_tasks` — 变更影响分析任务队列

**设计理由**：`change_impact_service.analyze()` 内部会调用 `db.commit()`（见 `backend/app/services/change_impact_service.py:130`），如果在 PLM 摄入事务中直接调用，会破坏"三阶段短事务同步"的事务边界。因此 ECN approved 时只写入任务记录，由后台 worker 在独立事务中执行分析。

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | UUID PK | 主键 |
| change_id | UUID FK | 关联 `plm_change_orders.change_id` |
| status | String(20) | `pending` → `running` → `completed` / `failed` |
| created_at | DateTime | 创建时间 |
| started_at | DateTime, nullable | 开始时间 |
| completed_at | DateTime, nullable | 完成时间 |
| error_message | Text, nullable | 错误信息 |
| result | JSONB, nullable | 分析结果（影响节点列表、评分等） |

**处理流程**：
1. PLMIngestionService 摄入 ECN 时，若状态变为 `approved`，创建 `pending` 任务记录（同一事务内）
2. 后台 worker 轮询 `plm_change_impact_tasks`，领取 `pending` 任务
3. Worker 在**独立事务**中调用 `change_impact_service.analyze()`
4. 更新任务状态为 `completed` 或 `failed`

### 3.8 `plm_part_fmea_links` — Part 与 FMEA 节点关联表

**设计理由**：当前 FMEA 节点 schema（`backend/app/schemas/fmea.py:11` 和 `frontend/src/types/index.ts:32`）没有 `part_number` / `external_part_id` / `revision` 字段。如果 BOM 导入时把 `part_number` 塞进节点属性，Pydantic 更新路径会丢弃未知字段。因此通过独立关联表建立 Part ↔ FMEA 节点的可追溯映射。

| 字段 | 类型 | 说明 |
|------|------|------|
| link_id | UUID PK | 主键 |
| part_id | UUID FK | 关联 `plm_parts.part_id` |
| fmea_id | UUID FK | 关联 `fmea_documents.fmea_id` |
| node_id | String(36) | FMEA 节点 ID（`graph_data.nodes[].id`） |
| link_type | String(20) | `auto_import`（BOM 导入自动创建）/ `manual_link`（工程师手动关联） |
| created_at | DateTime | 创建时间 |

**使用场景**：
- BOM 导入 DFMEA 时，为每个创建的 FMEA 节点同时写入关联记录
- ECN 触发影响分析时，通过 `part_id` → `plm_part_fmea_links` → `node_id` 查找受影响节点
- Part 详情页显示关联的 FMEA 文档和节点

### 3.9 `plm_part_sc_links` — Part 与 Special Characteristic 关联表

**设计理由**：`special_characteristics` 表的 `source_type` CHECK 约束仅允许 `DFMEA`/`PFMEA`，且 `source_node_id` 为 `nullable=False`。PLM Part 不是 FMEA 来源，直接写入会触发约束错误。因此通过独立关联表管理 Part 与 SC 的关系，不修改已有 SC 表结构。

| 字段 | 类型 | 说明 |
|------|------|------|
| link_id | UUID PK | 主键 |
| part_id | UUID FK | 关联 `plm_parts.part_id` |
| sc_id | UUID FK, nullable | 关联 `special_characteristics.id`（确认后回填） |
| characteristic_type | String(20) | `safety` / `key_characteristic` |
| status | String(20) | `pending` → `confirmed` → `rejected` |
| confirmed_by | UUID FK, nullable | 确认人 |
| confirmed_at | DateTime, nullable | 确认时间 |
| product_line_code | String(50) FK | 产品线 |
| created_at | DateTime | 创建时间 |

**处理流程**：
1. PLM Part 同步时，若 `is_safety_related=True` 或 `is_key_characteristic=True`，自动创建 `pending` 记录
2. 前端 Part 详情页显示待处理 SC 申请，工程师选择关联 FMEA 节点后确认
3. 确认后：写入 `special_characteristics` 表（`source_type="DFMEA"`，`source_node_id` 来自工程师选择的 FMEA 节点）
4. 回填 `plm_part_sc_links.sc_id`，更新 `status = "confirmed"`
5. SC 审批完成后通过 `plm_push_outbox` 回写 PLM

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
- **Parts**: PCB、MOSFET、电感、电容、外壳、散热器等 12 个零部件（含 A/B revision）
- **BOMs**: 3 级 BOM 结构（DC-DC-100 → 子系统 → 组件 → 零件），含版本
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
- `_ingest_part`: `pg_insert PLMPart ON CONFLICT (connection_id, part_number, revision) DO UPDATE`
- `_ingest_bom`: `pg_insert PLMBOM ON CONFLICT (...) DO UPDATE`
- `_ingest_change_order`: `pg_insert PLMChangeOrder ON CONFLICT (...) DO UPDATE`
  - 若状态从非 approved 变为 approved，创建 `plm_change_impact_tasks` 记录（同一事务内，不直接调用 analyze）

### 5.2 PLMSyncService
完全复用 MESSyncService 的三阶段短事务模式。

**同步顺序控制**（PLM 特有）：
| 数据类型 | next_run_at | 说明 |
|---------|-------------|------|
| parts | now() | 第一轮同步 |
| boms | now() + 2min | 等 parts 同步完成 |
| change_orders | now() + 4min | 等 parts + boms 同步完成 |

### 5.3 ECN → 变更影响分析任务队列

当 ECN 状态变为 `approved` 时，**只写任务记录，不直接调用分析服务**：

```python
# PLMIngestionService._ingest_change_order 中（同一事务内）：
if old_status != "approved" and new_status == "approved":
    db.add(PLMChangeImpactTask(
        change_id=change_order.change_id,
        status="pending",
    ))
```

后台 worker（独立事务）消费任务：

```python
SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

async def process_plm_change_impact_task(db, task: PLMChangeImpactTask):
    change_order = await db.get(PLMChangeOrder, task.change_id)
    for part_ref in change_order.affected_part_numbers:
        # part_ref 格式: "part_number|revision" 或仅 "part_number"
        part_number = part_ref.split("|")[0] if "|" in part_ref else part_ref
        
        # 通过关联表查找 FMEA 节点（不假设 FMEA 节点含 part_number 字段）
        links = await find_part_fmea_links(db, part_number=part_number)
        for link in links:
            node = await get_fmea_node(db, link.fmea_id, link.node_id)
            if not node:
                continue
            await change_impact_service.analyze(
                fmea_id=link.fmea_id,
                node_id=link.node_id,
                node_type=node.get("type", "Component"),
                node_name=node.get("name", ""),
                change_type="plm_ecn",
                field_name="part_number",
                new_value=change_order.change_number,
                old_value=None,
                user_id=SYSTEM_USER_ID,
            )
    task.status = "completed"
```

**关键约束**：`change_impact_service.analyze()` 内部会 `commit()`，因此必须在**独立事务**中调用，不能在 PLM 摄入事务内调用。

---

## 6. API 路由

所有路由挂载 `@require_permission(Module.PLM, ...)` 装饰器：

```python
router = APIRouter(prefix="/api/plm", tags=["plm"])

# --- Connection CRUD ---
POST   /api/plm/connections                    # 创建连接 [EDIT]
GET    /api/plm/connections                    # 列表（分页+产品线过滤）[VIEW]
GET    /api/plm/connections/{id}               # 详情 [VIEW]
PUT    /api/plm/connections/{id}               # 更新 [EDIT]
DELETE /api/plm/connections/{id}               # 删除 [ADMIN]
POST   /api/plm/connections/{id}/test          # 连通性测试 [EDIT]
POST   /api/plm/connections/{id}/sync          # 手动触发同步 [EDIT]

# --- Data Query ---
GET    /api/plm/parts                          # 零部件列表 [VIEW]
GET    /api/plm/parts/{part_id}                # 零部件详情（含 BOM 父子 + FMEA links + SC links）[VIEW]
GET    /api/plm/boms                           # BOM 列表 [VIEW]
GET    /api/plm/connections/{connection_id}/boms/tree/{part_number}  # BOM 树形展开 [VIEW]
GET    /api/plm/change-orders                  # ECN 列表 [VIEW]
GET    /api/plm/change-orders/{id}             # ECN 详情（含影响分析任务结果）[VIEW]
GET    /api/plm/dashboard                      # 概览统计 [VIEW]

# --- Integration Actions ---
POST   /api/plm/parts/{part_id}/link-fmea                           # Part 关联 FMEA 节点 [EDIT]
POST   /api/plm/change-orders/{id}/impact-analysis                   # 手动触发/刷新影响分析任务 [EDIT]
POST   /api/plm/connections/{connection_id}/boms/{part_number}/import-to-fmea  # BOM 导入 DFMEA [EDIT]
```

**权限映射**：
| 角色 | PLM 权限级别 | 能力 |
|------|-------------|------|
| admin | 5 | 全部操作 |
| manager | 4 | 全部操作 |
| field_qe | 2 | VIEW + EDIT（连接管理、导入、关联） |
| viewer | 1 | 仅 VIEW |
| 其他角色 | 1 | 仅 VIEW |

---

## 7. 前端页面

| 页面 | 路由 | 核心功能 | requiredModule |
|------|------|---------|----------------|
| PLM 连接管理 | `/plm/connections` | CRUD + 测试 + 手动同步 | `plm` |
| PLM 数据看板 | `/plm/dashboard` | KPI 卡片 + 快速入口 | `plm` |
| 零部件管理 | `/plm/parts` | 列表 + 搜索 + 详情 Drawer（BOM 树 + SC 待确认 + FMEA links） | `plm` |
| 工程变更单 | `/plm/change-orders` | ECN 列表 + 状态标签 + 详情（变更内容 + 影响分析任务结果面板） | `plm` |

**路由守卫**：`frontend/src/App.tsx` 中 PLM 路由需配置 `requiredModule="plm"`，viewer 角色只能查看，编辑按钮隐藏。

**菜单显隐**：`frontend/src/components/layout/AppLayout.tsx` 中 PLM 菜单项根据 `userPermissions.plm >= PermissionLevel.VIEW` 控制显隐。

---

## 8. 与现有模块联动

### 8.1 BOM → FMEA 结构树导入

**前置条件**：
- 目标 FMEA 文档状态必须为 `draft`
- 首次导入：`graph_data.nodes` 为空
- 重复导入：需前端二次确认弹窗，后端清空原有节点和边后全量覆写

**导入逻辑（同时创建 nodes 和 edges）**：

```python
# 1. 遍历 BOM 邻接表，按 level 构建树
# 2. 为每个 BOM 节点创建 FMEA node
for bom_node in bom_tree:
    fmea_node = {
        "id": f"plm-{connection_id}-{bom_node.part_number}-{bom_node.revision}",
        "type": node_type_map[bom_node.level],  # 1=System, 2=Subsystem, 3+=Component
        "name": bom_node.name,
        "part_number": bom_node.part_number,     # 写入节点属性（前端显示用）
        "revision": bom_node.revision,
        # 功能/失效模式占位符，工程师后续补充
        "function": "",
        "failure_mode": "",
    }
    fmea_nodes.append(fmea_node)

# 3. 为父子关系创建 edges
for bom in boms:
    fmea_edges.append({
        "id": f"edge-{parent_id}-{child_id}",
        "source": parent_node_id,
        "target": child_node_id,
        "type": "HAS_CHILD",  # BOM 层级边
    })

# 4. 写入 FMEA 文档
fmea.graph_data = {"nodes": fmea_nodes, "edges": fmea_edges}

# 5. 创建 plm_part_fmea_links 关联记录
for node in fmea_nodes:
    await create_part_fmea_link(part_number=node["part_number"], fmea_id=fmea.fmea_id, node_id=node["id"])
```

**节点 ID 稳定规则**：`plm-{connection_id}-{part_number}-{revision}` — 确保同一 Part 多次导入时 ID 一致，避免重复节点。

**边类型定义**：
| 边类型 | 来源 | 目标 | 语义 |
|--------|------|------|------|
| `HAS_CHILD` | 父零部件节点 | 子零部件节点 | BOM 父子结构 |
| `HAS_FUNCTION` | 零部件节点 | 功能节点 | 功能映射（占位） |
| `HAS_FAILURE_MODE` | 功能节点 | 失效模式节点 | 失效分析（占位） |

**注意**：初始导入仅创建 `HAS_CHILD` 边（BOM 结构）。`HAS_FUNCTION` 和 `HAS_FAILURE_MODE` 需要工程师在 FMEA 编辑器中补充。

### 8.2 ECN → 变更影响分析

- **自动触发**: ECN 状态变为 `approved` → 创建 `plm_change_impact_tasks` pending 记录 → 后台 worker 执行
- **手动触发**: ECN 详情页 **"运行影响分析"** 按钮 → 创建/重置任务记录
- 结果展示：受影响 FMEA 列表（通过 `plm_part_fmea_links` 查询）+ 高风险节点红色高亮 + 建议优化措施

### 8.3 Part → Special Characteristic 关联

- `is_safety_related=True` 或 `is_key_characteristic=True` 的 Part 同步时，自动创建 `plm_part_sc_links` 记录（`status=pending`）
- Part 详情页显示待处理 SC 申请列表，工程师选择关联 FMEA 节点后确认
- 确认后写入 `special_characteristics` 表（`source_type="DFMEA"`，`source_node_id` 来自工程师选择的 FMEA 节点）
- 回填 `plm_part_sc_links.sc_id`，更新 `status = "confirmed"`
- SC 审批完成后通过 `plm_push_outbox` 回写 PLM

**为什么不直接写入 `special_characteristics`？**
- `source_type` CHECK 约束仅允许 `DFMEA`/`PFMEA`，PLM 来源不合法
- `source_node_id` 为 `nullable=False`，PLM Part 刚同步时无关联 FMEA 节点
- 独立关联表实现解耦，不修改已稳定的 SC 表结构

---

## 9. 技术决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 方案 | C（独立但相似） | 零重构风险，数据隔离好，核心模式复用 |
| BOM 存储 | 邻接表 | 支持多级树，查询简单，易于导入 FMEA |
| affected_part_numbers | JSONB 数组（含 revision） | 精确标识受影响版本，格式 `"PN\|REV"` |
| ECN 触发时机 | approved | 在正式实施前给质量团队预留分析时间 |
| 同步顺序 | 延迟 next_run_at | 无需复杂依赖图，利用现有调度机制 |
| 厂商适配器 | 预留接口 | 先验证通用 REST 模式，再扩展专用适配器 |
| SC 关联方式 | 独立关联表 `plm_part_sc_links` | 不修改 `special_characteristics` 的 CHECK 约束和 `nullable=False` |
| product_line_code | nullable=True | 外部 PLM 通常无 OpenQMS 产品线码，由 Ingestion 层强制拷贝 |
| BOM 导入限制 | 仅 draft + 空 graph_data | 防止误覆盖已编辑的 FMEA 结构 |
| API 路由 | 含 connection_id | 消除多 PLM 连接下 part_number 重复的歧义 |
| SYSTEM_USER_ID | config 统一定义 | 后台自动触发变更分析时的审计归属 |
| Part/BOM 版本 | 唯一键含 revision | 同一零部件的多版本共存，不覆盖 |
| FMEA 节点关联 | `plm_part_fmea_links` 关联表 | FMEA 节点 schema 无 part_number 字段，不假设 schema 扩展 |
| 变更分析调用 | 任务队列 `plm_change_impact_tasks` | `change_impact_service.analyze()` 内部 commit()，不能在摄入事务内调用 |
| BOM 导入边创建 | 同时创建 nodes + edges | 影响分析 BFS 依赖边类型（`backend/app/graph/jsonb_repository.py:356`） |
| 节点 ID 规则 | `plm-{connection_id}-{part_number}-{revision}` | 稳定唯一，重复导入幂等 |
| 权限控制 | 完整守卫（路由+前端+菜单+种子） | 避免复制 MES 路由未传 requiredModule 的漏洞 |

---

## 10. 文件清单

### 后端新增
- `backend/alembic/versions/031_add_plm_tables.py` — 9 张表 + PLM 权限数据
- `backend/app/models/plm.py` — 9 个模型
- `backend/app/schemas/plm.py` — Pydantic schemas
- `backend/app/services/plm_connector.py` — PLMConnector ABC + Mock + REST
- `backend/app/services/plm_service.py` — PLMIngestionService + PLMSyncService + 后台 worker
- `backend/app/api/plm.py` — FastAPI 路由（含权限装饰器）

### 后端修改
- `backend/app/core/permissions.py` — 新增 `Module.PLM`
- `backend/app/core/product_line_filter.py` — 添加 `"plm": "product_line_code"`
- `backend/app/core/config.py` — 定义 `SYSTEM_USER_ID` 常量
- `backend/app/models/__init__.py` — 导出 PLM 模型
- `backend/app/services/graph_projection_service.py` — `_node_properties` 白名单增加 `"part_number"`
- `backend/app/main.py` — 注册 plm_router + 后台协程（sync + outbox + impact task worker）
- `backend/app/seed.py` — 插入 PLM 模块权限种子数据
- `backend/alembic/versions/031_add_plm_tables.py` 末尾 — 插入 PLM 角色权限（参考 MES 在 030 中的做法）

### 前端新增
- `frontend/src/pages/plm/PLMConnectionsPage.tsx`
- `frontend/src/pages/plm/PLMDashboardPage.tsx`
- `frontend/src/pages/plm/PLMPartsPage.tsx`
- `frontend/src/pages/plm/PLMChangeOrdersPage.tsx`
- `frontend/src/api/plm.ts`
- `frontend/src/types/plm.ts`

### 前端修改
- `frontend/src/App.tsx` — 新增 PLM 路由（带 `requiredModule="plm"`）
- `frontend/src/components/layout/AppLayout.tsx` — 新增 PLM 侧边栏菜单（权限控制显隐）

---

## 11. 已知限制与后续版本

| 限制 | 说明 | 后续版本规划 |
|------|------|-------------|
| 厂商专用适配器 | 仅预留接口，未实现西门子 TC / 达索 ENOVIA / PTC Windchill 专用适配器 | Phase 4 后期 |
| BOM 导入边类型 | 初始仅创建 `HAS_CHILD` 边，功能/失效模式边需手动补充 | 考虑从 PLM 同步功能定义 |
| 生效区间（Effectivity） | BOM 和 Part 未建模生效时间区间 | 需要时扩展 |
| 图纸/文档同步 | 未纳入范围 | 需要时扩展 |
| ECN 双向同步 | 目前仅 Inbound，Outbound 推送为可选 | Phase 4 后期 |

---

## 12. 验收测试项

### 后端测试
- [ ] **幂等同步测试**：同一 Part/BOM/ECN 多次同步，数据不重复、版本不覆盖
- [ ] **多 revision 测试**：同一 part_number 的 A/B/C 版本共存，查询返回正确版本
- [ ] **事务边界测试**：ECN approved 摄入事务不直接调用 analyze()，任务表正确记录
- [ ] **权限测试**：viewer 角色无法调用 EDIT/ADMIN 路由，返回 403
- [ ] **产品线隔离测试**：用户只能查询其有权限的产品线数据
- [ ] **BOM 导入测试**：draft + 空 graph_data 的 FMEA 才能导入，导入后 nodes + edges 完整

### 前端测试
- [ ] **菜单显隐测试**：viewer 角色看不到编辑按钮，admin 角色看到全部
- [ ] **路由守卫测试**：未登录/无权限用户访问 PLM 路由被拦截
