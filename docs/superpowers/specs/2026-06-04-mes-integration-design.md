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
- `field_mapping`：MES 字段名 → OpenQMS 字段名的映射

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
| consecutive_failures | INTEGER | 连续同步失败次数，达到 3 次自动置 inactive（默认 0） |
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

### mes_scrap_records — 报废/返工

| 字段 | 类型 | 说明 |
|------|------|------|
| scrap_id | UUID PK | |
| connection_id | UUID FK→mes_connections ON DELETE CASCADE | |
| order_id | UUID FK→mes_production_orders ON DELETE SET NULL | 关联工单（外键，替代原 order_no VARCHAR） |
| equipment_code | VARCHAR(50) | 关联设备 |
| defect_type | VARCHAR(50) | `scrap`/`rework`/`reject` |
| defect_category | VARCHAR(100) | 不良分类 |
| defect_qty | INTEGER | 不良数量 |
| total_qty | INTEGER | 检验总数 |
| defect_description | TEXT | 不良描述 |
| recorded_at | TIMESTAMPTZ | |
| product_line | VARCHAR(50) | |
| mes_raw_data | JSONB | |

**设计决策**：
- 每条记录带 `connection_id`，支持多 MES 源
- `mes_raw_data` JSONB 保留 MES 原始数据，避免信息丢失
- 过程测量数据不建新表，直接写入现有 SPC `SampleBatch`/`SampleValue`，但需为 `SampleBatch` 增加 `connection_id`（FK→mes_connections, SET NULL）和 `order_no`（VARCHAR(50)）两个可选字段，确保 MES 来源可追溯
- 所有表带 `product_line`，与现有产品线隔离一致
- 所有时间字段使用 `TIMESTAMPTZ`（带时区），与现有模型一致
- `mes_production_orders` 建联合唯一索引 `UniqueConstraint(connection_id, order_no)`
- `mes_scrap_records` 通过 `order_id` 外键关联工单（而非 VARCHAR `order_no`），避免多 MES 源工单号碰撞
- `mes_connections` 增加 `consecutive_failures` 字段，持久化失败计数，重启不丢失

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
| checkpoint | TIMESTAMPTZ | 增量同步起点（上次成功时间） |
| started_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | |
| error_message | TEXT | |
| created_at | TIMESTAMPTZ | |

**联合唯一索引**：`UniqueConstraint(connection_id, data_type)` — 每个 connection 的每种数据类型一个 job。

**同步流程**：
```
定时调度 (asyncio background task, 5min 间隔)
  → MESSyncService.schedule_and_run()
    → SELECT mes_sync_jobs WHERE status IN ('pending', 'failed')
      FOR UPDATE SKIP LOCKED  -- 防多 worker 重复
    → 加载对应 MESConnector
    → fetch_{data_type}(since=job.checkpoint) → 增量写入
    → 更新 job: status=completed, checkpoint=now(), completed_at=now()
    → 审计日志
```

**手动同步**：`POST /api/mes/connections/{id}/sync` 将该 connection 的所有 job 置为 `pending`，立即触发一轮调度。

**优势**：
- 每个 connection + data_type 独立 checkpoint，工单/设备/报废/测量可分别追踪进度
- `FOR UPDATE SKIP LOCKED` 确保多 worker/多实例安全
- 失败 job 保留 `error_message`，下次调度自动重试
- 重启后 job 状态持久化，不丢失

### 反向推送（OpenQMS → MES）

```
SPC 异常触发 / CAPA 状态变更
  → MESPushService.push_event()
    → 遍历关联 connection 的 MESConnector
    → push_quality_event()
    → 审计日志
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
- 权限等级：

| 操作 | Module.MES 最低等级 |
|------|:-----:|
| 连接管理（CRUD + 测试 + 手动同步） | L3 (manager) |
| 数据查询（工单/设备/报废/看板） | L2 (quality_engineer) |
| 数据推送接入（`/api/mes/ingest`） | API Key（无 JWT，MES 系统调用） |

- 通过 `require_permission(Module.MES, PermissionLevel.MANAGE)` 等现有权限守卫实现，不再用角色名硬判断
- 迁移文件需在 `permission_matrix` 表中插入 MES 模块各角色的默认等级

---

## 错误处理

### 拉取同步
- 单个 job 失败不影响其他（独立 try/catch）
- 失败时 job.status=failed, error_message 记录详情
- 失败不更新 checkpoint，下次调度自动重试增量数据
- 失败时 `mes_connections.consecutive_failures += 1`，达到 3 次自动标记 `is_active = False`
- 同步成功时重置 `consecutive_failures = 0`
- 多 Worker 安全：`SELECT ... FOR UPDATE SKIP LOCKED`

### 推送接收
- 数据校验失败返回 400 + 具体错误字段
- 重复数据（相同 `order_no` + `recorded_at`）跳过，返回 200 + 提示
- 未知 `data_type` 返回 400

### 反向推送
- MES 返回非 2xx → 审计日志 + 不阻塞主流程
- 连接超时 30s

---

## 测试策略

- **后端**：延续 `test_schema.py` 手动测试模式，新增 `test_mes_connector.py` 验证 Mock 适配器 + API 端点
- **前端**：无 Vitest，手动验证
- **集成测试**：Mock 模拟器 + 手动同步 API 触发完整数据流验证

---

## 数据生命周期管理

- `mes_equipment_status`：设备状态历史仅保留 **90 天**，到期自动清理（后台任务每日检查）
- `mes_scrap_records`：报废/返工明细保留 **1 年**，超出部分按月聚合成统计摘要
- `mes_production_orders`：已关闭（`closed`）超 **2 年** 的工单归档到历史表
- `mes_raw_data` JSONB：归档时可清除原始数据，仅保留结构化字段
- 数据清理策略在 `mes_connections.config` 中可配置保留天数
