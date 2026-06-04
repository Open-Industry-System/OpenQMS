# MES 集成连接器设计

**日期**: 2026-06-04
**状态**: 已批准
**阶段**: Phase 4

---

## 概述

构建 MES（制造执行系统）集成连接器，实现 OpenQMS 与 MES 的双向数据交换。采用适配器模式，内置 Mock 模拟器用于开发测试和演示。

**数据范围**：
1. 过程测量数据 → 自动写入 SPC 控制图
2. 生产工单/批次信息 → 关联质量记录
3. 设备状态数据 → OEE 分析
4. 报废/返工数据 → 不良分析

---

## 架构：适配器模式

```
MESConnector (抽象基类)
├── MockMESConnector    — 模拟器，生成随机生产数据
├── RESTMESConnector    — 通用 REST API 适配器（配置驱动）
└── (未来) SiemensConnector, RockwellConnector...
```

### MESConnector 抽象基类

```python
class MESConnector(ABC):
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
    async def push_quality_event(self, event_type: str, data: dict) -> dict:
        """推送质量事件到 MES。"""
```

### MockMESConnector

模拟器生成真实感数据：
- **生产工单**：随机工单号 `WO-2026-{NNN}`、产品型号 `DC-DC-100-{A/B/C}`、工艺路线、数量 100-500
- **测量数据**：按 SPC `ic_code` 查库获取规格上下限，正态分布 μ=target ± σ=(USL-LSL)/6，99% 规格内，1% 越界
- **设备状态**：3 台设备（EQ-001 注塑、EQ-002 焊接、EQ-003 组装），随机 running/idle/down/changeover，availability 85-95%, performance 80-95%, quality 95-99%, OEE 自动计算
- **报废/返工**：不良分类（尺寸超差 40%、外观不良 30%、功能异常 20%、其他 10%），不良率 0.5-2%
- **每次同步**：2-5 个工单、1-3 个设备状态变化、0-2 条报废记录、每工单 1 个测量批次

### RESTMESConnector

通过 `config` JSONB 配置：
```json
{
  "base_url": "http://mes-server:8080/api",
  "timeout": 30,
  "retry": { "max_retries": 3, "backoff_seconds": [1, 2, 4] },
  "auth_type": "bearer",
  "auth_config": { "token_encrypted": "..." },
  "endpoints": {
    "production_orders": {
      "path": "/orders",
      "method": "GET",
      "cursor_field": "updated_since",
      "pagination": { "type": "offset", "page_param": "page", "size_param": "page_size", "size": 100 },
      "response_path": "data.orders"
    },
    "equipment_status": {
      "path": "/equipment/status",
      "method": "GET",
      "pagination": { "type": "none" },
      "response_path": "data.equipment"
    },
    "scrap_records": {
      "path": "/scrap",
      "method": "GET",
      "cursor_field": "recorded_since",
      "pagination": { "type": "cursor", "cursor_param": "after", "cursor_response_field": "next_cursor" },
      "response_path": "data.records"
    },
    "measurements": {
      "path": "/measurements",
      "method": "GET",
      "cursor_field": "sampled_since",
      "pagination": { "type": "offset", "page_param": "page", "size_param": "per_page", "size": 50 },
      "response_path": "data.measurements"
    },
    "push_event": {
      "path": "/quality/events",
      "method": "POST"
    }
  },
  "field_mapping": {
    "order_no": "work_order_id",
    "product_model": "product_name",
    "equipment_code": "equip_id",
    "external_id": "measurement_id"
  }
}
```

**配置字段说明**：
- `timeout`：请求超时秒数（默认 30）
- `retry`：重试策略（次数 + 指数退避间隔）
- `endpoints.{name}.cursor_field`：增量同步时传入的查询参数名（如 `?updated_since=2026-06-04T00:00:00Z`）
- `endpoints.{name}.pagination.type`：分页方式 — `none`（无分页）/ `offset`（页码分页）/ `cursor`（游标分页）
- `endpoints.{name}.response_path`：响应 JSON 中数据数组的嵌套路径（如 `data.orders`）
- `field_mapping`：OpenQMS 字段名 → MES 字段名的映射（key 是 OpenQMS 侧，value 是 MES 侧）

---

## 数据模型

### mes_connections — MES 连接配置

| 字段 | 类型 | 说明 |
|------|------|------|
| connection_id | UUID PK | |
| name | VARCHAR(100) | 连接名称 |
| connector_type | VARCHAR(50) | `mock` / `rest` |
| config | JSONB | 适配器配置（API Key/Token 等敏感字段在输出 Schema 中脱敏） |
| is_active | BOOLEAN | 是否启用 |
| product_line_code | VARCHAR(50) FK→product_lines.code | 关联产品线 |
| created_by | UUID FK→users | |
| created_at / updated_at | TIMESTAMPTZ | |

### mes_production_orders — 生产工单

| 字段 | 类型 | 说明 |
|------|------|------|
| order_id | UUID PK | |
| connection_id | UUID FK→mes_connections ON DELETE CASCADE | 来源 MES |
| order_no | VARCHAR(50) | 工单号（联合唯一索引：connection_id + order_no） |
| product_model | VARCHAR(100) | 产品型号 |
| process_route | VARCHAR(200) | 工艺路线 |
| planned_qty | INTEGER | 计划数量 |
| actual_qty | INTEGER | 实际数量 |
| status | VARCHAR(20) | `planned`/`in_progress`/`completed`/`closed` |
| started_at / completed_at | TIMESTAMPTZ | |
| product_line_code | VARCHAR(50) FK→product_lines.code | 关联产品线 |
| mes_raw_data | JSONB | MES 原始数据 |
| created_at | TIMESTAMPTZ | |

### mes_equipment_status — 设备状态

| 字段 | 类型 | 说明 |
|------|------|------|
| record_id | UUID PK | |
| connection_id | UUID FK→mes_connections ON DELETE CASCADE | |
| external_id | VARCHAR(100) | MES 外部幂等键 |
| equipment_code | VARCHAR(50) | 设备编号 |
| equipment_name | VARCHAR(100) | 设备名称 |
| status | VARCHAR(20) | `running`/`idle`/`down`/`changeover` |
| availability | NUMERIC(5,2) | 可用率百分比 |
| performance | NUMERIC(5,2) | 运行率百分比 |
| quality | NUMERIC(5,2) | 质量率百分比 |
| oee | NUMERIC(5,2) | OEE 百分比（= availability × performance × quality / 10000） |
| downtime_reason | VARCHAR(200) | 停机原因（仅 status=down 时有值） |
| recorded_at | TIMESTAMPTZ | |
| product_line_code | VARCHAR(50) FK→product_lines.code | 关联产品线 |
| mes_raw_data | JSONB | |

**联合唯一索引**：`UniqueConstraint(connection_id, external_id)`

### mes_scrap_records — 报废/返工

| 字段 | 类型 | 说明 |
|------|------|------|
| scrap_id | UUID PK | |
| connection_id | UUID FK→mes_connections ON DELETE CASCADE | |
| external_id | VARCHAR(100) | MES 外部幂等键 |
| order_id | UUID FK→mes_production_orders ON DELETE SET NULL | 关联工单 |
| equipment_code | VARCHAR(50) | 关联设备 |
| defect_type | VARCHAR(50) | `scrap`/`rework`/`reject` |
| defect_category | VARCHAR(100) | 不良分类 |
| defect_qty | INTEGER | 不良数量 |
| total_qty | INTEGER | 检验总数 |
| defect_description | TEXT | 不良描述 |
| recorded_at | TIMESTAMPTZ | |
| product_line_code | VARCHAR(50) FK→product_lines.code | 关联产品线 |
| mes_raw_data | JSONB | |

**联合唯一索引**：`UniqueConstraint(connection_id, external_id)`

### mes_measurement_ingestions — MES 测量来源追踪

过程测量数据**不复用 SampleBatch/SampleValue 原表**存储来源元数据，而是新增本表作为 MES→SPC 的桥接层。SPC 仍复用 `SampleBatch/SampleValue` 做控制图计算，本表保存 MES 来源信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| ingestion_id | UUID PK | |
| connection_id | UUID FK→mes_connections ON DELETE CASCADE | 来源 MES |
| external_id | VARCHAR(100) | MES 外部幂等键（防止重复写入） |
| order_no | VARCHAR(50) | 关联工单号 |
| ic_code | VARCHAR(100) | 对应 SPC 检验特性代码 |
| batch_id | UUID FK→sample_batches ON DELETE SET NULL | 写入的 SPC 批次（写入后回填） |
| source_sampled_at | TIMESTAMPTZ | MES 原始采样时间 |
| ingested_at | TIMESTAMPTZ | 写入 OpenQMS 的时间 |
| product_line_code | VARCHAR(50) FK→product_lines.code | 关联产品线 |
| mes_raw_data | JSONB | MES 原始测量数据完整保留 |

**联合唯一索引**：`UniqueConstraint(connection_id, external_id)` — 幂等保障，相同 external_id 不重复写入。

**设计决策**：
- 每条记录带 `connection_id`，支持多 MES 源
- `mes_raw_data` JSONB 保留 MES 原始数据，避免信息丢失
- 过程测量数据通过 `mes_measurement_ingestions` 桥接层追踪来源，SPC 仍复用 `SampleBatch/SampleValue` 做控制图计算，不重复 SPC 逻辑
- `mes_measurement_ingestions.batch_id` 在 SPC 写入成功后回填，前端通过此字段关联 SPC 批次与 MES 来源
- `mes_measurement_ingestions.external_id` 提供幂等保障，重复推送跳过不写入
- 所有时间字段使用 `TIMESTAMPTZ`（带时区）
- 产品线字段统一使用 `product_line_code` 并 FK 到 `product_lines.code`（与多数模块一致；SPC `InspectionCharacteristic.product_line` 作为历史特例保留不改）
- `mes_production_orders` 建联合唯一索引 `UniqueConstraint(connection_id, order_no)`
- `mes_scrap_records` 通过 `order_id` 外键关联工单，避免多 MES 源工单号碰撞
- `mes_sync_jobs` 包含 `consecutive_failures` 字段，按数据类型追踪失败次数，任一 job 达 3 次则连接停用

---

## 数据流

### 推送路径（MES → OpenQMS）

```
MES 推送 POST /api/mes/ingest
  → MESIngestionService.ingest()
    → 根据 data_type 分发：
      - "measurement" → spc_service.ingest_external_data() + 触发规则检测
      - "production_order" → 写入 mes_production_orders
      - "equipment_status" → 写入 mes_equipment_status
      - "scrap_record" → 写入 mes_scrap_records
    → 审计日志
```

### 拉取路径（OpenQMS → MES）

采用数据库同步任务表替代 asyncio background task，解决多 worker 重复同步和 checkpoint 粒度问题。

**mes_sync_jobs — 同步任务表**

| 字段 | 类型 | 说明 |
|------|------|------|
| job_id | UUID PK | |
| connection_id | UUID FK→mes_connections | |
| data_type | VARCHAR(20) | `production_orders`/`equipment_status`/`scrap_records`/`measurements` |
| status | VARCHAR(20) | `pending`/`running`/`completed`/`failed` |
| checkpoint | TIMESTAMPTZ | 增量同步起点（上次成功处理的最大 MES 源时间戳） |
| next_run_at | TIMESTAMPTZ | 下次调度时间（completed 后 = now() + interval） |
| started_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | |
| error_message | TEXT | |
| consecutive_failures | INTEGER | 连续失败次数，达到 3 次触发连接告警（默认 0） |
| created_at | TIMESTAMPTZ | |

**联合唯一索引**：`UniqueConstraint(connection_id, data_type)` — 每个 connection 的每种数据类型一个 job。

**同步流程**（两阶段短事务，避免长事务持锁）：
```
定时调度 (asyncio background task, 1min 间隔检查)

阶段 1 — 领取 job（短事务）：
  BEGIN
    SELECT j FROM mes_sync_jobs j
      JOIN mes_connections c ON j.connection_id = c.connection_id
      WHERE c.is_active = TRUE
        AND (j.status IN ('pending', 'failed')
             OR (j.status = 'completed' AND j.next_run_at <= now()))
      FOR UPDATE SKIP LOCKED
    → UPDATE j SET status='running', started_at=now()
  COMMIT  -- 释放行锁

阶段 2 — 执行外部请求（无事务）：
  加载对应 MESConnector
  fetch_{data_type}(since=job.checkpoint - overlap_window) → 数据在内存中

阶段 3 — 写入结果（短事务）：
  BEGIN
    增量写入数据库（UPSERT 工单/设备/报废/测量）
    UPDATE job SET status='completed',
      checkpoint=COALESCE(max_source_timestamp, job.checkpoint),
      next_run_at=now()+interval, completed_at=now()
    （空结果时保持原 checkpoint，仅更新 next_run_at/completed_at/status）
  COMMIT
  审计日志
```

**超时恢复**：调度器每轮检查 `status='running' AND started_at < now() - 10min` 的 job，视为崩溃残留，重置为 `status='failed'`，下次调度自动重试。

**手动同步**：`POST /api/mes/connections/{id}/sync` 仅将该 connection 中 `status IN ('completed', 'failed')` 的 job 置为 `pending`；若存在 `status = 'running'` 的 job，返回 409 Conflict 及其运行状态。立即触发一轮调度。

**优势**：
- 每个 connection + data_type 独立 checkpoint，工单/设备/报废/测量可分别追踪进度
- `FOR UPDATE SKIP LOCKED` 确保多 worker/多实例安全
- 失败 job 保留 `error_message`，下次调度自动重试
- 重启后 job 状态持久化，不丢失
- `next_run_at` 确保已完成的 job 到期后自动重新调度
- checkpoint 使用"本次成功处理的最大 MES 源时间戳"而非 now()，避免跳数据
- 拉取时回看 overlap_window（默认 5 分钟，可在 connection config 中配置），配合幂等键去重

### 反向推送（OpenQMS → MES）

采用 outbox 模式确保可靠投递，业务事务只写 outbox 表，后台任务异步推送。

**mes_push_outbox — 推送事件发件箱**

| 字段 | 类型 | 说明 |
|------|------|------|
| outbox_id | UUID PK | |
| event_type | VARCHAR(50) | `spc_alarm`/`capa_status_change`/`fmea_recommendation` 等 |
| connection_id | UUID FK→mes_connections ON DELETE CASCADE | 目标 MES 连接 |
| payload | JSONB | 事件数据 |
| status | VARCHAR(20) | `pending`/`processing`/`sent`/`failed` |
| retry_count | INTEGER | 已重试次数（默认 0） |
| max_retries | INTEGER | 最大重试次数（默认 3） |
| next_retry_at | TIMESTAMPTZ NOT NULL DEFAULT now() | 下次重试时间（新记录默认立即领取；失败后指数退避） |
| started_at | TIMESTAMPTZ | 开始处理时间 |
| last_error | TEXT | 最近一次失败原因 |
| created_at | TIMESTAMPTZ | 事件创建时间 |
| sent_at | TIMESTAMPTZ | 成功发送时间 |

```
业务事件（SPC 异常 / CAPA 状态变更）
  → 同一事务内写入 mes_push_outbox (status=pending)

后台推送任务（短事务领取 + 异步发送 + 短事务写结果）：

  阶段 1 — 领取（短事务）：
    BEGIN
      SELECT o FROM mes_push_outbox o
        JOIN mes_connections c ON o.connection_id = c.connection_id
        WHERE c.is_active = TRUE
          AND o.status = 'pending'
          AND o.next_retry_at <= now()
        FOR UPDATE SKIP LOCKED
      → UPDATE o SET status='processing', started_at=now()
    COMMIT

  阶段 2 — 发送（无事务）：
    加载 MESConnector
    push_quality_event(payload, event_id=outbox_id)
    投递语义：at-least-once。每次推送携带稳定的 event_id=outbox_id，
    MES 接收方按 event_id 幂等处理（重复 event_id 时忽略）。
    若 OpenQMS 在更新 status=sent 前崩溃，超时恢复后会再次推送相同
    event_id，MES 需保证幂等。允许重复，不允许静默丢失。

  阶段 3 — 写结果（短事务）：
    成功 → UPDATE status='sent', sent_at=now()
    失败 → UPDATE retry_count += 1, next_retry_at=now()+backoff,
            last_error=..., status='pending'
      → retry_count >= max_retries → status='failed'（永久失败，人工介入）

  超时恢复：processing 超过 10 分钟 → 重置为 pending
```

### 与现有系统衔接

- 测量数据 → 通过 `mes_measurement_ingestions` 桥接层写入 `spc_service.ingest_external_data()`，回填 `batch_id` 实现追溯
- SPC 异常 → 已有 `SPCAlarm` + FMEA 关联推荐，反向推送增加事件通知
- 生产批次 → `mes_production_orders` 为 CAPA/客诉提供批次追溯补充数据
- 报废数据 → 与 IQC 拒收、供应商 PPM 计算联动

---

## API 端点

### MES 连接管理（admin/manager）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/mes/connections` | GET | 列表（分页） |
| `/api/mes/connections` | POST | 创建连接配置 |
| `/api/mes/connections/{id}` | GET | 详情 |
| `/api/mes/connections/{id}` | PUT | 更新配置 |
| `/api/mes/connections/{id}` | DELETE | 删除连接 |
| `/api/mes/connections/{id}/test` | POST | 测试连接 |
| `/api/mes/connections/{id}/sync` | POST | 手动触发同步 |

### MES 数据推送（API Key 认证）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/mes/ingest` | POST | MES 推送数据 |

### MES 数据查询（engineer+）

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/mes/production-orders` | GET | 工单列表 |
| `/api/mes/production-orders/{id}` | GET | 工单详情 |
| `/api/mes/equipment-status` | GET | 设备状态列表 |
| `/api/mes/scrap-records` | GET | 报废/返工列表 |
| `/api/mes/dashboard` | GET | MES 数据看板 |

### MES 看板数据

`/api/mes/dashboard` 返回：
- OEE 概览（各设备当前 availability/performance/quality/OEE 四值）
- 在线设备数 / 停机设备数
- 今日产量 vs 计划产量
- 不良率（按类型分布）
- 近 7 天不良趋势

---

## 前端页面

### 1. MES 连接管理页 (`/mes/connections`)
- 连接列表（卡片式：名称 + 类型 + 状态灯 + 最近同步时间）
- 创建/编辑 Modal（选择 connector_type → 动态表单）
- 测试连接按钮 + 手动同步按钮
- 仅 admin/manager 可见

### 2. MES 数据看板页 (`/mes/dashboard`)
- OEE 卡片（设备可用率 availability、运行率 performance、质量率 quality、总 OEE）
- 产量进度条（计划 vs 实际）
- 不良率饼图（按分类）
- 设备状态矩阵（设备名 + 状态灯 + A/P/Q + OEE）
- 近 7 天不良趋势折线图

### 3. 工单列表页 (`/mes/orders`)
- 标准列表页（工单号 + 产品型号 + 数量 + 状态 + 时间）
- 状态筛选 + 产品线筛选

### 4. 报废/返工列表页 (`/mes/scrap`)
- 标准列表页（工单号 + 不良类型 + 分类 + 数量 + 描述）
- 不良类型筛选

### 侧边栏
新增"MES 集成"菜单分组，含以上 4 个页面入口

### 与现有页面联动
- SPC 控制图详情页：通过 `mes_measurement_ingestions` 查询批次来源，MES 来源的批次显示 `order_no` 和 connection 名称
- CAPA 详情页：D2 描述区域增加"关联工单"链接，可跳转到 MES 工单详情

---

## 认证与安全

### MES 推送认证（入站）
- `POST /api/mes/ingest` 使用 `X-API-Key` 认证
- 入站 API Key **只存 SHA-256 hash**（`mes_connections.config.auth_config.api_key_hash`），验证时对比 hash，永不明文读取
- 每个 connection 有独立 API Key
- 后续将 SPC ingest 端点认证也改为 hash 验证

### 出站 MES 凭证保护
- 向 MES 推送时使用的 token/password 等出站凭证，使用 `cryptography.fernet` 对称加密存储
- 加密密钥从环境变量 `MES_ENCRYPTION_KEY` 读取（首次部署时生成）
- 解密仅在 `push_quality_event()` 运行时进行，不暴露给 API 层

### 凭证脱敏
- Pydantic 输出 Schema（如 `ConnectionOut`）中，`config.auth_config` 的所有敏感字段（api_key_hash/token/password）必须脱敏为 `"***"`，不允许通过 GET 接口明文读回前端
- 创建/更新时允许写入完整凭证（入站 api_key 明文写入后立即 hash 替换；出站凭证加密后存储）

### 反向推送认证
- `push_quality_event()` 使用 connection 的 `config.auth_config` 向 MES 认证
- 支持 4 种：`none` / `basic` / `bearer` / `api_key`

### 权限控制
- 新增 `Module.MES` 到权限矩阵（`core/permissions.py`）
- 权限等级（现有枚举：VIEW/CREATE/EDIT/APPROVE/ADMIN）：

| 操作 | Module.MES 最低等级 | 对应角色 |
|------|:-----:|------|
| 连接管理（CRUD + 测试 + 手动同步） | APPROVE | admin/manager |
| 数据查询（工单/设备/报废/看板） | VIEW | 所有认证用户 |
| 数据推送接入（`/api/mes/ingest`） | API Key（无 JWT，MES 系统调用） | N/A |

- 通过 `require_permission(Module.MES, PermissionLevel.APPROVE)` 等现有权限守卫实现，不再用角色名硬判断
- 迁移文件需在 `permission_matrix` 表中插入 MES 模块各角色的默认等级

---

## 错误处理

### 拉取同步
- 单个 job 失败不影响其他（独立 try/catch）
- 失败时 job.status=failed, error_message 记录详情
- 失败不更新 checkpoint，下次调度自动重试增量数据
- 失败时 `mes_sync_jobs.consecutive_failures += 1`，任一 job 达到 3 次自动标记 `mes_connections.is_active = False`
- 同步成功时重置该 job 的 `consecutive_failures = 0`
- 多 Worker 安全：`SELECT ... FOR UPDATE SKIP LOCKED`

### 拉取幂等性保障

增量拉取重叠时（失败重试导致 since 时间窗口重叠），需防止重复写入：

1. **工单数据**：`mes_production_orders` 使用 `ON CONFLICT (connection_id, order_no) DO UPDATE` 更新 `actual_qty`/`status`/`completed_at` 等可变字段（工单在 MES 中会持续更新）
2. **报废与设备数据**：`mes_scrap_records` 和 `mes_equipment_status` 使用 `ON CONFLICT (connection_id, external_id) DO NOTHING`（历史快照，不更新）
3. **测量数据**：`mes_measurement_ingestions` 使用 `INSERT ... ON CONFLICT (connection_id, external_id) DO NOTHING RETURNING ingestion_id`，只有成功取得 `ingestion_id` 的请求才继续写入 SPC。ingestion 创建、SPC batch 写入、batch_id 回填必须在同一事务内完成，防止并发重复写入
4. **细粒度事务提交**：sync_all() 内将工单、设备状态、报废记录、测量数据四个拉取动作拆分为**四个独立事务提交块**。任一动作失败只回滚当前块，已成功持久化的数据保留，审计日志记录每块结果

### 推送接收
- 幂等规则：工单以 `(connection_id, order_no)` 判定并更新；设备状态/报废/测量以 `(connection_id, external_id)` 判定，已有则跳过
- 工单推送必须包含 `order_no`；设备状态/报废/测量推送必须包含 `external_id`
- 重复数据跳过，返回 200 + 提示
- 数据校验失败返回 400 + 具体错误字段
- 未知 `data_type` 返回 400

### 反向推送
- 采用 outbox 模式：业务事务只写 `mes_push_outbox`，后台任务异步推送
- 短事务领取（`FOR UPDATE SKIP LOCKED`）+ 异步发送 + 短事务写结果，防多 worker 重复投递
- `processing` 状态超时（>10min）自动恢复为 `pending`
- inactive 连接的 outbox 记录暂停投递（不领取），连接恢复后自动继续
- MES 返回非 2xx → retry_count += 1，指数退避重试，达到 max_retries (默认 3) 则 status=failed（人工介入）
- 连接超时 30s

---

## 测试策略

### 自动化测试（并发与事务核心风险）

在 `backend/tests/test_mes_concurrency.py` 中覆盖以下场景（使用 pytest + asyncio + 测试数据库）：

- **双 worker 只能领取一次 job**：两个协程同时 claim 同一 sync job，仅一个成功获取 running 状态
- **双 worker 只能领取一次 outbox**：两个协程同时 claim 同一 outbox 记录，仅一个成功获取 processing 状态
- **running job 超时恢复**：started_at 超过 10 分钟的 running job 被重置为 failed
- **processing outbox 超时恢复**：started_at 超过 10 分钟的 processing outbox 被重置为 pending
- **手动同步不抢占 running job**：对含 running job 的连接调用手动同步，返回 409，running job 不变
- **inactive 连接不被同步或推送**：is_active=False 的连接的 job 和 outbox 不被领取
- **测量 ingestion 与 SPC 写入原子回滚**：ingestion INSERT ON CONFLICT 成功但 SPC 写入失败时，整个事务回滚
- **崩溃后重复投递幂等**：模拟 MES 已接收但 OpenQMS 写 sent 前崩溃，恢复后再次推送时携带相同 event_id，MES 幂等返回成功，OpenQMS 最终标记 sent

### 手动测试

- **后端**：延续 `test_schema.py` 模式，新增 `test_mes_connector.py` 验证 Mock 适配器 + API 端点
- **前端**：无 Vitest，手动验证
- **集成测试**：Mock 模拟器 + 手动同步 API 触发完整数据流验证

---

## 数据生命周期管理

- `mes_equipment_status`：设备状态历史仅保留 **90 天**，到期自动清理（后台任务每日检查）
- `mes_scrap_records`：报废/返工明细保留 **1 年**，超出部分按月聚合成统计摘要
- `mes_production_orders`：已关闭（`closed`）超 **2 年** 的工单归档到历史表
- `mes_raw_data` JSONB：归档时可清除原始数据，仅保留结构化字段
- 数据清理策略在 `mes_connections.config` 中可配置保留天数
