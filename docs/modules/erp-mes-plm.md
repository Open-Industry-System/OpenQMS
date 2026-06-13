# ERP / MES / PLM 集成模块 — 用户手册

> 最后更新: 2026-06-13 | 适用版本: OpenQMS v1.0

---

## 1. 功能概述

OpenQMS 提供 ERP、MES、PLM 三大外部系统集成模块，以 **连接器 (Connector)** 架构对接企业现有系统，将质量数据与供应链、制造执行、产品生命周期打通，实现全链路质量追溯。

三大模块均为 **集成看板 (Integration Dashboard)** 形态：通过配置连接器从外部系统拉取数据，在 OpenQMS 内展示、关联并驱动质量业务。

| 模块 | 核心能力 | 典型场景 |
|------|---------|---------|
| ERP | 供应商/客户主数据同步、采购与销售订单追踪、库存查询、质量成本分析、批次正反向追溯 | 追溯某批次原材料从哪个供应商采购、发往哪个客户；核算质量成本 |
| MES | 生产订单进度监控、设备 OEE 查看、不良品/报废追踪、SPC 测量数据自动回传 | 实时查看产线状态；MES 推送测量数据至 OpenQMS 触发 SPC 报警 |
| PLM | 零件/BOM 同步、ECN 变更管理、FMEA 关联与 BOM 导入、特殊特性确认 | 零件变更后自动分析受影响的 FMEA 节点；将 BOM 结构导入 FMEA |

**数据流向：**

- **拉取 (Pull)：** 连接器定时从外部系统同步数据，写入 OpenQMS 对应数据表
- **推送 (Push)：** 外部系统通过 Ingest API 主动推送数据到 OpenQMS
- **回写 (Outbox Push)：** MES 模块支持将 SPC 报警事件推送到 MES 系统（需连接器启用 `push_enabled`）

**前端路由：**

| 模块 | 页面 | 路由 | 路由守卫 |
|------|------|------|---------|
| ERP | 仪表盘 | `/erp` | `requiredModule="erp"` |
| | 连接管理 | `/erp/connections` | `requiredModule="erp"` |
| | 主数据 | `/erp/master-data` | `requiredModule="erp"` |
| | 供应链 | `/erp/supply-chain` | `requiredModule="erp"` |
| | 商务/成本 | `/erp/commercial` | `requiredModule="erp"` |
| | 追溯 | `/erp/traceability` | `requiredModule="erp"` |
| MES | 仪表盘 | `/mes/dashboard` | 仅认证（无 `requiredModule`） |
| | 连接管理 | `/mes/connections` | 仅认证 |
| | 生产订单 | `/mes/orders` | 仅认证 |
| | 报废追踪 | `/mes/scrap` | 仅认证 |
| PLM | 仪表盘 | `/plm/dashboard` | `requiredModule="plm"` |
| | 连接管理 | `/plm/connections` | `requiredModule="plm"` |
| | 零件/BOM | `/plm/parts` | `requiredModule="plm"` |
| | 变更单 | `/plm/change-orders` | `requiredModule="plm"` |

> **注意：** MES 前端路由未设置 `requiredModule` 守卫，仅检查登录状态；但后端 API 仍通过 `get_user_permission(user, Module.MES, db)` 校验权限。

---

## 2. 适用角色与权限

系统采用 6 级权限模型：NONE(0) / VIEW(1) / CREATE(2) / EDIT(3) / APPROVE(4) / ADMIN(5)。

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| `erp` | 5 | 4 | 2 | 1 | 1 | 1 | 1 |
| `mes` | 5 | 4 | 2 | 1 | 1 | 1 | 1 |
| `plm` | 5 | 4 | 2 | 1 | 1 | 1 | 1 |

**权限解读：**

- **admin (5 — ADMIN)：** 完全控制，包括删除连接、配置加密密钥等
- **manager (4 — APPROVE)：** 可创建/编辑连接、触发同步、查看全部数据
- **field_qe (2 — CREATE)：** ERP/MES 仅查看数据，PLM 可创建连接和关联 FMEA/确认特殊特性
- **planning_qe / supplier_qe / customer_qe (1 — VIEW)：** 仅可查看数据看板和报表
- **viewer (1 — VIEW)：** 仅可查看数据看板和报表

### 操作与最低权限对照

#### ERP 操作权限

| 操作 | 最低 PermissionLevel | 说明 |
|------|---------------------|------|
| 查看仪表盘/数据 | VIEW (1) | 所有角色可查看 |
| 查看供应商/客户（脱敏） | VIEW (1) | VIEW 级别显示掩码数据 |
| 查看供应商/客户（完整） | APPROVE (4) | APPROVE 及以上显示完整信息 |
| 关联/取消关联供应商 | EDIT (3) | field_qe 无此权限，仅 manager/admin |
| 关联/取消关联客户 | EDIT (3) | 同上 |
| 创建连接 | APPROVE (4) | 仅 manager、admin |
| 修改连接配置 | APPROVE (4) | 仅 manager、admin |
| 测试连接 | APPROVE (4) | 仅 manager、admin |
| 触发手动同步 | APPROVE (4) | 仅 manager、admin |
| 删除连接 | ADMIN (5) | 仅 admin |
| Ingest API 推送 | API Key 认证 | 不走角色权限，使用 X-API-Key 头 |

#### MES 操作权限

| 操作 | 最低 PermissionLevel | 说明 |
|------|---------------------|------|
| 查看仪表盘/生产订单/设备/报废 | VIEW (1) | 所有角色可查看 |
| 创建连接 | APPROVE (4) | 仅 manager、admin |
| 修改/删除连接 | APPROVE (4) | 仅 manager、admin |
| 测试连接 | APPROVE (4) | 仅 manager、admin |
| 触发手动同步 | APPROVE (4) | 仅 manager、admin |
| Ingest API 推送 | API Key 认证 | 不走角色权限，使用 X-API-Key + X-Connection-Id 头 |

#### PLM 操作权限

| 操作 | 最低 PermissionLevel | 说明 |
|------|---------------------|------|
| 查看仪表盘/零件/BOM/变更单 | VIEW (1) | 所有角色可查看 |
| 创建连接 | CREATE (2) | field_qe 及以上 |
| 修改连接配置 | EDIT (3) | field_qe 无此权限，仅 manager/admin |
| 测试连接 | EDIT (3) | 仅 manager/admin |
| 触发手动同步 | EDIT (3) | 仅 manager/admin |
| 零件关联 FMEA | EDIT (3) | 仅 manager/admin |
| 确认特殊特性 | EDIT (3) + SC CREATE (2) | 需同时拥有 PLM EDIT 和 SPECIAL_CHARACTERISTIC CREATE |
| 触发变更影响分析 | EDIT (3) | 仅 manager/admin |
| 导入 BOM 到 FMEA | EDIT (3) | 仅 manager/admin |
| 删除连接 | ADMIN (5) | 仅 admin |

> **PLM 特殊权限：** `confirm_part_sc` 接口需同时校验 PLM 模块 EDIT (3) 权限和 SPECIAL_CHARACTERISTIC 模块 CREATE (2) 权限。

---

## 3. ERP 集成

### 3.1 仪表盘

ERP 仪表盘（`/erp`）提供以下概览信息：

| 区域 | 内容 | 数据源 |
|------|------|--------|
| 同步健康状态 | 各数据类型的最近同步时间、状态、失败次数 | `erp_sync_jobs` |
| 质量成本摘要 | 按类别的质量成本汇总 | `erp_cost_records` |
| 待处理事项 | 需要关注的异常项（如库存预警、发运风险） | 系统聚合 |
| 库存预警 | 低库存或过期预警 | `erp_inventory_balances` |
| 发运风险 | 延期或异常发运 | `erp_shipments` |
| KPI 指标 | 关键绩效指标 | 系统计算 |

### 3.2 连接管理

**路由：** `/erp/connections`

#### 3.2.1 连接器类型

| 类型 | 说明 |
|------|------|
| `mock` | 内置模拟连接器，生成 DC-DC-100 产品线的示例数据，用于演示和测试 |
| `rest` | 通用 REST API 连接器，支持分页、认证、重试、字段映射等完整配置 |

#### 3.2.2 REST 连接器配置

创建 REST 连接器时需配置以下参数：

**基础配置：**

| 参数 | 说明 | 示例 |
|------|------|------|
| `name` | 连接名称 | "SAP S/4HANA 生产" |
| `connector_type` | 固定为 `rest` | — |
| `product_line_code` | 产品线编码 | "DC-DC-100" |
| `config.base_url` | ERP 系统 API 基地址 | `https://erp.example.com/api/v1` |
| `config.timeout` | 请求超时（秒） | 30 |
| `config.retry` | 重试配置 | `{"max_retries": 3, "backoff_factor": 1.0}` |

**认证配置 (`config.auth_type`)：**

| 类型 | 说明 | 额外参数 |
|------|------|---------|
| `none` | 无认证 | — |
| `basic` | HTTP Basic Auth | `auth_config.username`, `auth_config.password` |
| `bearer` | Bearer Token | `auth_config.token` |
| `api_key` | API Key 头 | `auth_config.header_name`, `auth_config.api_key` |

> 认证信息存储时使用 Fernet 对称加密（`ERP_ENCRYPTION_KEY` 环境变量），API 响应中自动脱敏（移除 `auth_config`、`*_encrypted`、`*_hash` 字段）。

**端点配置 (`config.endpoints`)：**

需配置 9 个数据类型的拉取端点：

| 端点键 | 对应数据 | 说明 |
|--------|---------|------|
| `suppliers` | 供应商 | 供应商主数据 |
| `customers` | 客户 | 客户主数据 |
| `materials` | 物料 | 物料主数据 |
| `locations` | 库位 | 仓库/库位信息 |
| `purchase_orders` | 采购订单 | PO 明细 |
| `sales_orders` | 销售订单 | SO 明细 |
| `inventory_balances` | 库存余额 | 实时库存快照 |
| `shipments` | 发运记录 | 出货记录 |
| `cost_records` | 成本记录 | 质量成本数据 |

每个端点需配置 `url_path`、`method`（默认 GET）、分页方式（`offset` / `cursor` / `none`）、字段映射等。

**字段映射 (`config.field_mapping`)：**

用于将外部系统字段名映射到 OpenQMS 内部字段名，格式示例：

```json
{
  "suppliers": {"外部字段_供应商编码": "supplier_code", "外部字段_名称": "name"},
  "materials": {"MaterialNo": "material_code"}
}
```

#### 3.2.3 连接生命周期

| 操作 | 权限 | 说明 |
|------|------|------|
| 创建连接 | APPROVE (4) | 填写名称、类型、配置 |
| 测试连接 | APPROVE (4) | 向外部系统发起一次测试请求，验证连通性和认证 |
| 修改配置 | APPROVE (4) | 更新连接参数 |
| 触发手动同步 | APPROVE (4) | 立即拉取所有数据类型 |
| 删除连接 | ADMIN (5) | 软删除（标记 `is_active = false`） |

**同步机制：**

ERP 同步采用 **4 阶段 DAG 调度**：

- **Phase 1：** suppliers、customers、materials、locations（主数据）
- **Phase 2：** purchase_orders、sales_orders（单据，依赖 Phase 1）
- **Phase 3：** inventory_balances、shipments（实时数据）
- **Phase 4：** cost_records（汇总数据）

每个数据类型对应一条 `ERPSyncJob`，使用 `SELECT ... FOR UPDATE SKIP LOCKED` 避免并发冲突。连续失败 3 次后自动停用连接。

### 3.3 主数据

**路由：** `/erp/master-data`

展示从 ERP 同步的四大主数据：

| 数据 | 字段要点 | 说明 |
|------|---------|------|
| **供应商 (Suppliers)** | supplier_code, name, status, payment_terms, currency, tax_id, bank_info, link_status | VIEW 权限显示脱敏数据（银行信息掩码），APPROVE 权限显示完整数据 |
| **客户 (Customers)** | customer_code, name, status, region, customer_level, tax_id, link_status | 同供应商，按权限脱敏 |
| **物料 (Materials)** | material_code, name, specification, unit, material_type, is_purchased, is_manufactured, default_supplier_code, status | 物料类型区分采购件和自制件 |
| **库位 (Locations)** | location_code, warehouse_code, zone_code, location_type, is_enabled | 仓库-区域-库位三级结构 |

**供应商/客户关联：**

每条供应商/客户记录有 `link_status` 字段，取值为：

| 状态 | 说明 |
|------|------|
| `pending` | 已同步但未关联 OpenQMS 内部供应商/客户 |
| `linked` | 已关联 OpenQMS 供应商/客户记录 |
| `unlinked` | 已取消关联 |

关联操作通过 `/api/erp/suppliers/{id}/link` 和 `/api/erp/customers/{id}/link` 接口完成（需 EDIT 权限），将外部 ERP 供应商与 OpenQMS `suppliers` 表建立双向引用。

### 3.4 供应链

**路由：** `/erp/supply-chain`

展示采购、销售、库存、发运四个维度的供应链数据：

| 数据 | 关键字段 | 说明 |
|------|---------|------|
| **采购订单 (Purchase Orders)** | po_number, line_number, supplier_code, material_code, quantity, unit_price, delivery_date, received_quantity, status, lot_no | 含批次号，可追溯到供应商 |
| **销售订单 (Sales Orders)** | so_number, line_number, customer_code, material_code, quantity, unit_price, delivery_date, status | 按客户维度查看 |
| **库存余额 (Inventory Balances)** | material_code, location_code, lot_no, supplier_lot_no, quantity, unit, inventory_status, manufacture_date, expiry_date | 含批次和供应商批次，支持效期管理 |
| **发运记录 (Shipments)** | shipment_number, so_number, customer_code, material_code, lot_no, quantity, shipment_date, link_status | 可关联 OpenQMS 发运检验记录 |

**发运关联：** 同步时系统自动按 `customer_id + lot_no + shipment_date` 匹配 OpenQMS `ShipmentRecord`，将 `openqms_shipment_id` 写入 ERP 发运记录。

### 3.5 商务与成本

**路由：** `/erp/commercial`

展示质量成本数据：

| 数据 | 关键字段 | 说明 |
|------|---------|------|
| **成本记录 (Cost Records)** | record_type, cost_category, cost_type, amount, currency, period_month, source_document_no, material_code, supplier_code, cost_center, cost_date, description | 多维度成本归集 |

成本分类维度：

- **record_type：** 记录类型（如预防成本、鉴定成本、内部故障成本、外部故障成本）
- **cost_category：** 成本类别
- **cost_type：** 具体成本项目
- **cost_center：** 成本中心

### 3.6 追溯

**路由：** `/erp/traceability`

提供基于批次的 **双向追溯 (Traceability)** 功能：

- **正向追溯：** 从原材料批次出发 → 采购订单 → 供应商 → 成品发运 → 客户
- **反向追溯：** 从客户投诉出发 → 发运记录 → 生产批次 → 原材料批次 → 供应商

**追溯结果：**

```json
{
  "nodes": [/* 追溯节点列表 */],
  "edges": [/* 节间关系 */],
  "gaps": [/* 数据缺口提示 */]
}
```

`gaps` 字段标识追溯链中的断点，提醒用户关注数据不完整的环节。

---

## 4. MES 集成

### 4.1 仪表盘

MES 仪表盘（`/mes/dashboard`）提供以下概览信息：

| 区域 | 内容 | 数据源 |
|------|------|--------|
| 设备汇总 | 各设备 OEE（可用率 × 性能 × 质量率）、运行/停机台数 | `mes_equipment_status` |
| 生产统计 | 计划总产量 vs 实际总产量 | `mes_production_orders` |
| 不良分布 | 按缺陷类别统计报废量 | `mes_scrap_records` |
| 报废趋势 | 近 7 天报废趋势 | `mes_scrap_records` |

### 4.2 连接管理

**路由：** `/mes/connections`

#### 4.2.1 连接器类型

| 类型 | 说明 |
|------|------|
| `mock` | 内置模拟连接器，生成 DC-DC-100 产品线的示例数据 |
| `rest` | 通用 REST API 连接器，完整支持分页、认证、重试、字段映射、数据校验 |

#### 4.2.2 REST 连接器配置

与 ERP 连接器类似，但端点配置仅需 4 个数据类型：

| 端点键 | 对应数据 | 说明 |
|--------|---------|------|
| `production_orders` | 生产订单 | 工单号、产品型号、工艺路线、计划/实际产量 |
| `equipment_status` | 设备状态 | 设备编码、名称、OEE、停机原因 |
| `scrap_records` | 报废记录 | 工单号、缺陷类型、缺陷数量 |
| `measurements` | 测量数据 | SPC 检验特性数据，推送到 OpenQMS SPC 模块 |

**认证配置**与 ERP 相同（none / basic / bearer / api_key），加密密钥为 `MES_ENCRYPTION_KEY` 环境变量。

**推送配置：**

当 MES 连接器启用 `push_enabled = true` 时，需配置 `push_event` 端点，OpenQMS 会将 SPC 报警事件通过 Outbox 模式推送到 MES 系统。

#### 4.2.3 连接生命周期

与 ERP 类似，MES 同样使用 `SELECT ... FOR UPDATE SKIP LOCKED` 的 claim_token 并发控制模式，连续失败 3 次自动停用连接。

**同步机制：** MES 同步按数据类型独立运行，4 个同步任务并行：

| 数据类型 | 同步策略 |
|---------|---------|
| `production_orders` | UPSERT，按 `connection_id + order_no` 去重 |
| `equipment_status` | INSERT ON CONFLICT DO NOTHING |
| `scrap_records` | UPSERT，回填 `order_id` |
| `measurements` | 去重入库，关联 IC + 创建 SampleBatch + 重新评估 SPC 报警 |

**同步参数：**

| 参数 | 值 | 说明 |
|------|---|------|
| 同步间隔 | 5 分钟 | `SYNC_INTERVAL_MINUTES` |
| 重叠窗口 | 300 秒 | `OVERLAP_WINDOW_SECONDS` |
| 超时 | 10 分钟 | `TIMEOUT_MINUTES` |
| 最大失败次数 | 3 次 | `MAX_FAILURES` |
| 批次大小 | 100 条 | `BATCH_SIZE` |

#### 4.2.4 数据生命周期管理

MES 模块内置数据生命周期清理机制：

| 数据类型 | 保留期 | 处理方式 |
|---------|--------|---------|
| 设备状态 | 90 天 | 直接删除 |
| 报废记录 | 365 天 | 先聚合到 `mes_scrap_monthly_summary`，再删除明细 |
| 已关闭生产订单 | 730 天 | 归档到 `mes_production_orders_archive` |

清理任务使用 `pg_try_advisory_xact_lock(42)` 防止并发执行。

### 4.3 生产订单

**路由：** `/mes/orders`

展示从 MES 同步的生产订单数据：

| 字段 | 说明 |
|------|------|
| `order_no` | 工单号（唯一标识，同连接内去重） |
| `product_model` | 产品型号 |
| `process_route` | 工艺路线 |
| `planned_qty` | 计划产量 |
| `actual_qty` | 实际产量 |
| `status` | 订单状态：`planned` / `in_progress` / `completed` / `closed` |
| `started_at` | 开始时间 |
| `completed_at` | 完成时间 |

支持按状态、时间范围等条件筛选和分页查询。

### 4.4 报废追踪

**路由：** `/mes/scrap`

展示从 MES 同步的报废/不良品记录：

| 字段 | 说明 |
|------|------|
| `order_no` | 关联工单号 |
| `order_id` | 关联工单 ID（外键） |
| `equipment_code` | 发生设备编码 |
| `defect_type` | 缺陷类型 |
| `defect_category` | 缺陷分类 |
| `defect_qty` | 缺陷数量 |
| `total_qty` | 总检验数量 |
| `defect_description` | 缺陷描述 |

报废记录与生产订单通过 `order_id` 关联，支持按工单、设备、缺陷类型等维度分析。

### 4.5 SPC 联动

MES 模块最核心的跨模块联动是 **测量数据 → SPC**：

1. MES 系统通过 Ingest API 或同步拉取推送测量数据
2. 数据写入 `mes_measurement_ingestions`，按 `(connection_id, external_id)` 去重
3. 系统查找对应的 InspectionCharacteristic（检验特性），创建 SampleBatch
4. 触发 SPC 报警规则重新评估
5. 若产生报警且连接器启用 `push_enabled`，将报警事件写入 `MESPushOutbox`
6. Push Worker 将报警推送回 MES 系统

**推送事件格式：** SPC 报警事件包含检验特性 ID、报警规则、触发时间、样本数据等，MES 系统可据此触发停线或加检。

---

## 5. PLM 集成

### 5.1 仪表盘

PLM 仪表盘（`/plm/dashboard`）提供以下概览信息：

| 区域 | 内容 | 数据源 |
|------|------|--------|
| 零件统计 | 零件总数 | `plm_parts` |
| BOM 统计 | BOM 条目总数 | `plm_boms` |
| 待处理 ECN | 待审批变更单数量 | `plm_change_orders` |
| 待确认特殊特性 | 安全/关键特性待确认数 | `plm_part_sc_links` (status=pending) |
| 最近变更 | 最近的变更单列表 | `plm_change_orders` |

### 5.2 连接管理

**路由：** `/plm/connections`

#### 5.2.1 连接器类型

| 类型 | 说明 | 实现状态 |
|------|------|---------|
| `mock` | 内置模拟连接器，生成 DC-DC-100 产品线示例数据 | 已实现 |
| `rest` | 通用 REST API 连接器 | 框架已实现，数据拉取方法为 TODO |
| `siemens_tc` | Siemens Teamcenter 连接器 | 框架已实现（映射到 RESTPLMConnector） |
| `dassault_enovia` | Dassault ENOVIA 连接器 | 框架已实现（映射到 RESTPLMConnector） |
| `ptc_windchill` | PTC Windchill 连接器 | 框架已实现（映射到 RESTPLMConnector） |

> **重要：** 当前仅 `mock` 类型可通过 API 创建连接。后端校验 `IMPLEMENTED_CONNECTOR_TYPES = {"mock"}`，创建其他类型会返回 400 错误。`rest`、`siemens_tc`、`dassault_enovia`、`ptc_windchill` 的连接器骨架已搭建，但数据拉取方法均抛出 `NotImplementedError`。

#### 5.2.2 Mock 连接器示例数据

Mock 连接器生成的 DC-DC-100 示例数据：

**零件 (5 个)：**

| 零件号 | 名称 | 特殊标记 |
|--------|------|---------|
| DC-DC-100-ASM | DC-DC-100 总成 | safety + key_characteristic |
| PCBA-MAIN-01 | 主控板组件 | key_characteristic |
| HOUSING-TOP-01 | 上壳体 | — |
| HEATSINK-01 | 散热器 | — |
| CAP-CER-100UF | 陶瓷电容 100μF | — |

**BOM (5 条，3 层结构)：**

```
DC-DC-100-ASM (L0)
├── PCBA-MAIN-01 (L1, qty=1)
├── HOUSING-TOP-01 (L1, qty=1)
└── HEATSINK-01 (L1, qty=1)
    └── CAP-CER-100UF (L2, qty=2)
```

**变更单 (2 条)：**

| 变更号 | 标题 | 状态 | 优先级 |
|--------|------|------|--------|
| ECN-2026-001 | 散热器材料升级 | approved | high |
| ECN-2026-002 | 陶瓷电容规格调整 | draft | normal |

#### 5.2.3 同步机制

PLM 同步采用 3 阶段调度：

| 阶段 | 数据类型 | 说明 |
|------|---------|------|
| Phase 1 | `part` | 零件主数据（含安全/关键特性自动创建 SC Link） |
| Phase 2 | `bom` | BOM 结构（6 列唯一约束去重） |
| Phase 3 | `change_order` | 变更单（状态变为 `approved` 时自动创建变更影响分析任务） |

同步同样使用 claim_token 并发控制模式，连续失败 3 次自动停用连接。

### 5.3 零件与 BOM

**路由：** `/plm/parts`

#### 5.3.1 零件列表

展示从 PLM 同步的零件数据：

| 字段 | 说明 |
|------|------|
| `part_number` | 零件号（同连接+版本号唯一） |
| `name` | 零件名称 |
| `revision` | 版本号（默认 "A"） |
| `material` | 材料 |
| `specification` | 规格描述 |
| `status` | 状态 |
| `is_safety_related` | 是否安全相关 |
| `is_key_characteristic` | 是否关键特性 |
| `sc_links` | 关联的特殊特性列表 |

**特殊特性联动：**

当零件的 `is_safety_related = true` 时，同步自动创建 `PLMPartSCLink`（`characteristic_type = "safety"`, `status = "pending"`）；当 `is_key_characteristic = true` 时，自动创建 `characteristic_type = "key_characteristic"` 的 SC Link。

#### 5.3.2 BOM 树

通过 `/api/plm/connections/{id}/boms/tree/{part_number}` 接口可获取指定零件的完整 BOM 展开树：

```json
{
  "part_number": "DC-DC-100-ASM",
  "revision": "A",
  "children": [
    {
      "part_number": "PCBA-MAIN-01",
      "revision": "A",
      "quantity": 1,
      "children": []
    }
  ]
}
```

#### 5.3.3 零件关联 FMEA

通过 `/api/plm/parts/{part_id}/link-fmea` 可将零件关联到 FMEA 文档的特定节点：

```json
{
  "fmea_id": "uuid-of-fmea-document",
  "node_id": "uuid-of-fmea-node",
  "link_type": "manual"
}
```

`link_type` 取值：`auto_import`（BOM 导入自动创建）或 `manual`（手动关联）。

#### 5.3.4 确认特殊特性

通过 `/api/plm/parts/{part_id}/confirm-sc` 确认零件的特殊特性标记，需同时满足：
- PLM 模块 EDIT (3) 权限
- SPECIAL_CHARACTERISTIC 模块 CREATE (2) 权限

```json
{
  "fmea_id": "uuid-of-fmea-document",
  "node_id": "uuid-of-fmea-node",
  "characteristic_type": "safety"
}
```

#### 5.3.5 导入 BOM 到 FMEA

通过 `/api/plm/connections/{id}/boms/{part_number}/import-to-fmea` 可将 BOM 结构导入到指定 FMEA 文档：

```json
{
  "fmea_id": "uuid-of-fmea-document",
  "overwrite": false
}
```

系统将 BOM 树结构转换为 FMEA 图谱节点和边，创建 `PLMPartFMEALink`（`link_type = "auto_import"`）。

### 5.4 变更单

**路由：** `/plm/change-orders`

展示从 PLM 同步的工程变更单 (ECN)：

| 字段 | 说明 |
|------|------|
| `change_number` | 变更单号（同连接唯一） |
| `title` | 变更标题 |
| `description` | 变更描述 |
| `change_type` | 变更类型 |
| `status` | 状态（draft / approved / implemented / closed） |
| `priority` | 优先级 |
| `affected_part_numbers` | 受影响零件列表 (JSONB) |
| `proposed_changes` | 建议变更内容 (JSONB) |
| `requested_by` | 申请人 |
| `approved_by` | 审批人 |
| `planned_implementation_date` | 计划实施日期 |
| `actual_implementation_date` | 实际实施日期 |

#### 5.4.1 变更影响分析

当变更单状态变为 `approved` 时，系统自动创建 `PLMChangeImpactTask`。也可通过 API `/api/plm/change-orders/{change_id}/impact-analysis` 手动触发。

影响分析流程：

1. 获取变更单的 `affected_part_numbers`
2. 通过 `PLMPartFMEALink` 查找受影响的 FMEA 文档和节点
3. 调用 `ChangeImpactService.analyze()` 对每个受影响节点执行影响分析
4. 返回分析结果

---

## 6. 连接配置说明

### 6.1 创建连接

1. 进入对应模块的「连接管理」页面
2. 点击「新建连接」按钮
3. 填写基本信息：
   - **名称：** 连接的显示名称
   - **连接器类型：** 选择 `mock`（测试）或 `rest`（生产）
   - **产品线：** 选择对应的产品线编码
4. 如果选择 `rest` 类型，需继续配置：
   - **API 基地址：** 外部系统的 URL
   - **认证方式：** 选择 none / basic / bearer / api_key
   - **各数据类型端点：** 逐一配置每个数据类型的 API 路径
   - **字段映射：** 外部字段到 OpenQMS 字段的映射关系
5. 点击「创建」

### 6.2 测试连接

创建连接后，在连接列表中点击「测试」按钮。系统会尝试：

- **ERP：** 从外部系统拉取 1 条供应商数据，返回 `{success, message}`
- **MES：** 从外部系统拉取 1 条生产订单数据，返回 `{ok, error}`
- **PLM：** 尝试拉取零件数据，返回 `{status, parts_count}` 或 `{status, error, error_class}`

测试成功仅表示连接可用，不代表全部数据类型端点都正确。

### 6.3 数据同步

#### 手动同步

在连接列表中点击「同步」按钮，系统立即触发一次全量同步：

- **ERP：** 按 4 阶段 DAG 顺序拉取所有 9 种数据类型
- **MES：** 并行拉取 4 种数据类型
- **PLM：** 按 3 阶段拉取零件 → BOM → 变更单

#### 自动同步

系统后台按配置的同步间隔自动执行同步任务，使用 `SELECT ... FOR UPDATE SKIP LOCKED` 确保不会重复执行。

#### 推送 (Ingest) 模式

外部系统也可主动推送数据到 OpenQMS：

**请求头：**

| 模块 | 必需头 |
|------|--------|
| ERP | `X-API-Key: <api_key>` |
| MES | `X-API-Key: <api_key>` + `X-Connection-Id: <connection_id>` |

**ERP Ingest 请求体：**

```json
{
  "data_type": "suppliers",
  "connection_id": "uuid",
  "items": [{...}, {...}]
}
```

`data_type` 允许值：`suppliers`, `customers`, `materials`, `locations`, `purchase_orders`, `sales_orders`, `inventory_balances`, `shipments`, `cost_records`

**MES Ingest 请求体：** 使用区分联合类型 (Discriminated Union)，需指定 `data_type` 字段：

- `production_orders`
- `equipment_status`
- `scrap_records`
- `measurements`

### 6.4 连接加密

所有连接的认证信息（密码、Token、API Key）均使用 Fernet 对称加密存储：

| 模块 | 环境变量 | 用途 |
|------|---------|------|
| ERP | `ERP_ENCRYPTION_KEY` | 加密出站认证凭据、哈希入站 API Key |
| MES | `MES_ENCRYPTION_KEY` | 同上 |

**安全措施：**

- 出站认证凭据（密码、Token）使用 Fernet 加密存储
- 入站 API Key 使用 SHA-256 哈希存储，验证时使用计时安全比较 (`hmac.compare_digest`)
- API 响应中自动脱敏：移除 `auth_config`、`*_encrypted`、`*_hash` 字段

---

## 7. 常见问题

### Q1：创建 REST 连接器时提示 "不支持的连接器类型"

**原因：** PLM 模块当前仅允许创建 `mock` 类型连接（`IMPLEMENTED_CONNECTOR_TYPES = {"mock"}`），`rest`、`siemens_tc` 等类型的连接器数据拉取方法尚未实现。

**解决方案：** 使用 `mock` 连接器进行功能演示和测试；生产环境需等待后续版本支持 REST 连接器。

### Q2：同步一直失败，连接被自动停用

**原因：** 连续 3 次同步失败后，系统自动将连接标记为 `is_active = false` 并写入审计日志。

**解决方案：**
1. 检查外部系统是否可达（使用「测试连接」功能）
2. 检查认证配置是否正确（API Key、用户名密码等）
3. 检查端点 URL 是否正确（特别是字段映射是否匹配外部系统的响应格式）
4. 修正后重新激活连接并触发手动同步

### Q3：MES 前端页面可见但 API 返回 403

**原因：** MES 前端路由未设置 `requiredModule` 守卫，仅检查登录状态。但后端 API 仍通过 `get_user_permission(user, Module.MES, db)` 校验权限。如果当前用户对 MES 模块没有 VIEW 权限，API 将返回 403。

**解决方案：** 在权限配置中为该用户角色赋予 MES 模块 VIEW (1) 或以上权限。

### Q4：ERP 供应商/客户信息显示为掩码

**原因：** VIEW 权限级别下，供应商银行信息、客户税务信息等敏感字段会自动脱敏。需要 APPROVE (4) 或以上权限才能查看完整信息。

**解决方案：** 使用 manager 或 admin 角色登录，或在权限配置中提升当前角色的 ERP 权限等级。

### Q5：PLM 变更影响分析没有结果

**可能原因：**

1. 变更单的 `affected_part_numbers` 为空
2. 受影响的零件尚未关联到 FMEA 文档（没有 `PLMPartFMEALink` 记录）
3. 变更单状态不是 `approved`（自动触发仅在状态变为 approved 时）

**解决方案：** 先通过「零件关联 FMEA」功能将受影响零件关联到对应 FMEA 文档节点，再触发影响分析。

### Q6：MES 推送报警事件失败

**原因：** 推送使用 Outbox 模式，采用指数退避重试（间隔 = 2^retry_count 分钟，最大 32 分钟）。

**排查步骤：**
1. 检查 MES 连接器是否启用 `push_enabled`
2. 检查 `push_event` 端点配置是否正确
3. 查看 `mes_push_outbox` 表中失败记录的 `retry_count` 和错误信息
4. 确认外部 MES 系统的推送接收接口可用

### Q7：ERP 追溯结果显示 "gaps"（数据缺口）

**原因：** 追溯链路中存在数据不完整的环节，例如：

- 采购订单缺少批次号
- 发运记录未关联到 OpenQMS 发运检验记录（`openqms_shipment_id` 为空）
- 库存余额缺少供应商批次号

**解决方案：** 补全外部系统中的关键字段（批次号、供应商批次号等），或通过 Ingest API 补充数据后重新同步。

### Q8：如何查看同步任务状态？

**解决方案：** 各模块的 `*_sync_jobs` 表记录了每个数据类型的同步状态、检查点（checkpoint）和连续失败次数。可通过 ERP/MES/PLM 仪表盘查看同步健康状态，或直接查询数据库：

```sql
-- 查看 ERP 同步任务状态
SELECT job_id, data_type, status, checkpoint, consecutive_failures
FROM erp_sync_jobs WHERE connection_id = '...';

-- 查看 MES 同步任务状态
SELECT job_id, data_type, status, checkpoint, consecutive_failures
FROM mes_sync_jobs WHERE connection_id = '...';

-- 查看PLM 同步任务状态
SELECT job_id, data_type, status, checkpoint, consecutive_failures
FROM plm_sync_jobs WHERE connection_id = '...';
```

### Q9：PLM 确认特殊特性提示权限不足

**原因：** `confirm_part_sc` 接口需要同时满足两个权限条件：

1. PLM 模块 EDIT (3) 权限
2. SPECIAL_CHARACTERISTIC 模块 CREATE (2) 权限

**解决方案：** 确认当前用户角色在这两个模块上分别达到所需权限等级。例如 `field_qe` 角色 PLM 权限为 2 (CREATE)，不满足 EDIT (3) 要求，因此无法确认特殊特性。

### Q10：Mock 连接器的数据可以修改吗？

Mock 连接器每次同步都会重新生成固定的示例数据（DC-DC-100 产品线），不支持自定义。如需使用真实数据，请配置 REST 连接器对接实际 ERP/MES/PLM 系统。Mock 数据仅用于功能演示和测试。