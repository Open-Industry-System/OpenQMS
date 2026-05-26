# 客户质量核心闭环设计文档

**日期**: 2026-05-26  
**状态**: 已批准，待实施  
**对应 ROADMAP**: Phase 2 — 客诉管理 + RMA 退货 + 客户质量看板  
**范围原则**: 只开发与已完成模块可联动的客户质量能力；对未开发模块预留接口和数据字段。

---

## 目标

实现客户质量核心闭环：客户档案、客诉接单、RMA 退货、不良分析、8D/CAPA 关联、FMEA 关联、超期预警和客户质量看板。该闭环依赖现有产品线、CAPA、FMEA、审计日志、权限体系，不依赖未开发的 IQC、SCAR、客户审核、CSR 或 0 公里 PPM 模块。

本期做成可独立使用的客户质量模块，同时为后续 Phase 2 剩余项保留扩展点：

- SCAR 联动：RMA 或客诉判定为供应商责任时，预留 `scar_ref_id` 和 `supplier_responsibility` 字段。
- 客户审核：预留客户详情页 Tab 与 API 路由命名空间，不创建审核业务表。
- CSR/VOC：客户档案保留 `csr_list` JSONB 字段，不实现控制计划同步。
- 0 公里 PPM：看板保留独立数据源接口，当前只基于客诉和 RMA 计算。

---

## 范围

### 本期实现

1. **客户档案**  
   共享客户主数据，不按产品线隔离。包含客户编号、名称、行业分类、联系人、PPM 目标、默认年发运量、CSR 列表。

2. **客诉管理**  
   客诉按产品线归属，支持分类、严重等级、影响数量、状态、期限、超期预警、FMEA 关联、CAPA/8D 关联。

3. **RMA 退货管理**  
   支持从客诉创建 RMA，也支持独立 RMA。记录退货数量、不良类型、责任判定、分析结论、纠正措施、FMEA/CAPA 关联。

4. **客户质量看板**  
   按客户和产品线统计投诉数、开放投诉数、超期数、RMA 数、退货数量、估算客户 PPM、风险灯号。

5. **ROADMAP 更新**  
   标记本期客户质量核心闭环范围，并列出后续 SCAR、客户审核、CSR、0 公里 PPM、高级看板开发顺序。

### 本期不实现

- SCAR 创建与状态流转。
- IQC 数据拉取。
- 客户审核日程和发现项。
- CSR 自动同步到控制计划。
- 文件上传服务；本期只保存附件元数据和 `file_url`。
- 满意度、保修、NTF、质量会议纪要。
- Excel 批量导入导出。

---

## 数据模型

### `customers`

客户主数据为共享档案。同一客户可以在多条产品线下产生客诉和 RMA。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| customer_id | UUID | PK, default=uuid4 | |
| customer_code | VARCHAR(20) | UNIQUE, NOT NULL | 客户编号，如 `CUS-001` |
| name | VARCHAR(200) | NOT NULL | 客户名称 |
| segment | VARCHAR(50) | nullable | 汽车/消费电子/工业/医疗等 |
| contact_name | VARCHAR(100) | nullable | 联系人 |
| contact_email | VARCHAR(200) | nullable | |
| contact_phone | VARCHAR(50) | nullable | |
| csr_list | JSONB | default `[]` | 客户特殊要求，预留 CSR/VOC 模块 |
| ppm_target | FLOAT | nullable | 客户要求 PPM 目标 |
| annual_shipment_qty | INTEGER | nullable | 默认年发运量，用于列表和看板 PPM 估算 |
| notes | TEXT | nullable | |
| created_by | UUID | FK users.user_id | |
| created_at | DateTime | server_default=now() | |
| updated_at | DateTime | onupdate=now() | |

**索引**: `customer_code`, `name`

### `customer_complaints`

客诉是客户质量闭环的入口，按产品线隔离。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| complaint_id | UUID | PK, default=uuid4 | |
| complaint_no | VARCHAR(50) | UNIQUE, NOT NULL | 编号，如 `CC-2026-001` |
| product_line_code | VARCHAR(20) | FK product_lines.code, NOT NULL | 产品线归属 |
| customer_id | UUID | FK customers.customer_id, NOT NULL | |
| product_id | VARCHAR(50) | nullable | 客户物料号或产品号 |
| batch_no | VARCHAR(50) | nullable | 生产批次或追溯批号 |
| serial_number | VARCHAR(100) | nullable | 单件序列号，适用于可序列化产品 |
| category | VARCHAR(20) | NOT NULL | `safety` / `function` / `appearance` / `delivery` |
| severity | VARCHAR(20) | NOT NULL | `致命` / `严重` / `一般` / `轻微` |
| defect_desc | TEXT | NOT NULL | 投诉描述 |
| impact_qty | INTEGER | default 0 | 影响数量 |
| occurred_date | DATE | nullable | 客户端失效或问题发生日期 |
| received_date | DATE | NOT NULL | 接收日期 |
| due_date | DATE | nullable | 回复或关闭期限 |
| status | VARCHAR(20) | default `open` | `open` / `investigating` / `responded` / `closed` / `cancelled` |
| fmea_ref_id | UUID | FK fmea_documents.fmea_id, nullable | |
| capa_ref_id | UUID | FK capa_eightd.report_id, nullable | |
| has_rma | BOOLEAN | default false | 是否已产生 RMA |
| preliminary_response | TEXT | nullable | 初步回复 |
| root_cause | TEXT | nullable | 根因 |
| corrective_action | TEXT | nullable | 纠正措施摘要 |
| attachments | JSONB | default `[]` | `[{file_name, file_url, uploaded_at, uploaded_by, category}]` |
| assignee_id | UUID | FK users.user_id, nullable | 负责跟进的 CQE/质量工程师 |
| supplier_responsibility | BOOLEAN | default false | 预留 SCAR 触发条件 |
| scar_ref_id | UUID | nullable | 预留，未来 FK supplier_scars |
| created_by | UUID | FK users.user_id | |
| created_at | DateTime | server_default=now() | |
| updated_at | DateTime | onupdate=now() | |
| closed_at | DateTime | nullable | |

**索引**: `(product_line_code, status)`, `(customer_id, received_date)`, `(due_date)`, `(assignee_id)`, `(batch_no)`, `(capa_ref_id)`, `(fmea_ref_id)`

### `rma_records`

RMA 可从客诉创建，也可独立创建。独立 RMA 后续可补关联客诉。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| rma_id | UUID | PK, default=uuid4 | |
| rma_no | VARCHAR(50) | UNIQUE, NOT NULL | 编号，如 `RMA-2026-001` |
| product_line_code | VARCHAR(20) | FK product_lines.code, NOT NULL | 产品线归属 |
| customer_id | UUID | FK customers.customer_id, NOT NULL | |
| complaint_id | UUID | FK customer_complaints.complaint_id, nullable | |
| product_id | VARCHAR(50) | nullable | |
| batch_no | VARCHAR(50) | nullable | 生产批次或追溯批号 |
| serial_number | VARCHAR(100) | nullable | 单件序列号，适用于可序列化产品 |
| return_qty | INTEGER | NOT NULL | 退货数量 |
| defect_type | VARCHAR(50) | NOT NULL | 功能不良/外观缺陷/包装损坏/数量短缺等 |
| responsibility | VARCHAR(50) | nullable | `supplier` / `internal` / `transport` / `customer_misuse` / `unknown` |
| analysis_result | TEXT | nullable | 不良分析 |
| corrective_action | TEXT | nullable | 纠正措施 |
| status | VARCHAR(20) | default `open` | `open` / `analysis` / `action_pending` / `closed` / `cancelled` |
| fmea_ref_id | UUID | FK fmea_documents.fmea_id, nullable | |
| capa_ref_id | UUID | FK capa_eightd.report_id, nullable | |
| scar_ref_id | UUID | nullable | 预留，未来 FK supplier_scars |
| attachments | JSONB | default `[]` | `[{file_name, file_url, uploaded_at, uploaded_by, category}]` |
| assignee_id | UUID | FK users.user_id, nullable | 负责分析和闭环的 CQE/质量工程师 |
| tracking_number | VARCHAR(100) | nullable | 退货物流单号 |
| received_date | DATE | nullable | 退货接收日期 |
| closed_at | DateTime | nullable | |
| created_by | UUID | FK users.user_id | |
| created_at | DateTime | server_default=now() | |
| updated_at | DateTime | onupdate=now() | |

**索引**: `(product_line_code, status)`, `(customer_id, received_date)`, `(complaint_id)`, `(responsibility)`, `(assignee_id)`, `(batch_no)`

---

## 状态和规则

### 客诉状态

```
open -> investigating -> responded -> closed
open -> cancelled
investigating -> cancelled
responded -> investigating
```

- `open`: 已接收，尚未启动分析。
- `investigating`: 已开始分析或已创建 8D/CAPA。
- `responded`: 已向客户给出阶段性或正式回复。
- `closed`: 根因、措施、验证和客户回复完成。
- `cancelled`: 误建或客户撤回。

### RMA 状态

```
open -> analysis -> action_pending -> closed
open -> cancelled
analysis -> cancelled
```

- `open`: 已登记退货。
- `analysis`: 正在不良分析。
- `action_pending`: 已判责，等待纠正措施或 CAPA 闭环。
- `closed`: 分析和处理完成。
- `cancelled`: 误建或退货取消。

### 超期规则

- 客诉 `status` 不在 `closed/cancelled` 且 `due_date < today` 时为超期。
- `severity = 致命` 且未填写 `preliminary_response` 时，列表和看板显示 24 小时响应风险。
- RMA 超期本期不单独配置 SLA；看板只统计打开 RMA 和关闭率。

### 风险灯号

按客户和产品线计算：

- 红色：存在致命开放客诉，或超期客诉数 > 0，或估算 PPM 超过目标 2 倍。
- 黄色：开放客诉数 > 0，或估算 PPM 超过目标。
- 绿色：无开放客诉，且估算 PPM 未超过目标。

估算 PPM 本期公式：

`customer_ppm = (complaint impact_qty + independent_rma return_qty) / shipment_qty * 1,000,000`

其中 `independent_rma` 只包含未关联客诉的 RMA，避免同一质量事件在客诉和退货中重复计数。`shipment_qty` 的取值顺序：

1. API 查询参数 `shipment_qty`，用于看板临时覆盖。
2. `customers.annual_shipment_qty`，用于客户列表、客户摘要和默认看板。
3. 两者都为空时，不计算 PPM，也不因 PPM 触发红黄灯。

客户列表和 `/api/customers/{customer_id}/summary` 必须能在没有查询参数时返回稳定风险灯号；此时只使用开放致命客诉、超期客诉和 `annual_shipment_qty` 可计算的 PPM。

---

## API 设计

### 客户档案

前缀：`/api/customers`

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/customers` | viewer+ | 列表，支持 `q`、`segment`、分页，返回基于开放/超期客诉和默认发运量的风险灯号 |
| POST | `/api/customers` | engineer/admin | 创建客户 |
| GET | `/api/customers/{customer_id}` | viewer+ | 详情 |
| PUT | `/api/customers/{customer_id}` | engineer/admin | 更新客户 |
| GET | `/api/customers/{customer_id}/summary` | viewer+ | 客诉/RMA/风险摘要 |

### 客诉

前缀：`/api/customer-complaints`

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/customer-complaints` | viewer+ | 列表，支持 `product_line`、`customer_id`、`status`、`severity`、`overdue`、`assignee_id` |
| POST | `/api/customer-complaints` | engineer/admin | 创建客诉 |
| GET | `/api/customer-complaints/{complaint_id}` | viewer+ | 详情 |
| PUT | `/api/customer-complaints/{complaint_id}` | engineer/admin | 更新客诉 |
| POST | `/api/customer-complaints/{complaint_id}/start-investigation` | engineer/admin | 进入调查中 |
| POST | `/api/customer-complaints/{complaint_id}/mark-responded` | engineer/admin | 标记已回复客户 |
| POST | `/api/customer-complaints/{complaint_id}/cancel` | engineer/admin | 取消误建或撤回客诉 |
| POST | `/api/customer-complaints/{complaint_id}/link-capa` | engineer/admin | 关联已有 8D/CAPA |
| POST | `/api/customer-complaints/{complaint_id}/create-capa` | engineer/admin | 从客诉创建 8D/CAPA |
| POST | `/api/customer-complaints/{complaint_id}/link-fmea` | engineer/admin | 关联 FMEA |
| POST | `/api/customer-complaints/{complaint_id}/close` | manager/admin | 关闭客诉 |

### RMA

前缀：`/api/rma-records`

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/rma-records` | viewer+ | 列表，支持 `product_line`、`customer_id`、`complaint_id`、`status`、`responsibility`、`assignee_id` |
| POST | `/api/rma-records` | engineer/admin | 创建 RMA |
| GET | `/api/rma-records/{rma_id}` | viewer+ | 详情 |
| PUT | `/api/rma-records/{rma_id}` | engineer/admin | 更新 RMA |
| POST | `/api/rma-records/{rma_id}/start-analysis` | engineer/admin | 进入分析中 |
| POST | `/api/rma-records/{rma_id}/mark-action-pending` | engineer/admin | 标记等待措施 |
| POST | `/api/rma-records/{rma_id}/cancel` | engineer/admin | 取消误建或撤回 RMA |
| POST | `/api/rma-records/{rma_id}/link-complaint` | engineer/admin | 补关联客诉 |
| POST | `/api/rma-records/{rma_id}/link-capa` | engineer/admin | 关联 8D/CAPA |
| POST | `/api/rma-records/{rma_id}/link-fmea` | engineer/admin | 关联 FMEA |
| POST | `/api/rma-records/{rma_id}/close` | manager/admin | 关闭 RMA |

### 客户质量看板

前缀：`/api/customer-quality`

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/customer-quality/dashboard` | viewer+ | 汇总 KPI、风险灯号、趋势 |
| GET | `/api/customer-quality/customers/{customer_id}/trend` | viewer+ | 单客户投诉/RMA 趋势 |

看板参数：

- `product_line`: 可选，遵循全局产品线筛选。
- `customer_id`: 可选。
- `date_from` / `date_to`: 可选，默认最近 90 天。
- `shipment_qty`: 可选，本期用于估算 PPM。

---

## 服务层设计

新增 `customer_quality_service.py`，保持现有项目风格，API 层薄，业务逻辑放 service。

核心职责：

- 校验产品线存在。
- 校验客户存在。
- 防止编号重复。
- 执行状态转换、状态动作 API 和关闭权限前置条件。
- 对 `PUT` 中传入的 `status` 做旧状态到新状态校验；禁止绕过状态机直接跳转到非法状态。
- 创建和写入 `AuditLog`。
- 从客诉创建 CAPA 时调用现有 `capa_service.create_capa`，并把 `capa_ref_id` 回写客诉。
- 计算超期、风险灯号、客户摘要和看板指标。

错误策略：

- service 抛 `ValueError`，API 转为 `HTTPException(400)`。
- 查无记录由 API 返回 404。
- 未授权继续使用现有依赖函数处理。

审计日志：

- 新增、更新、关闭、关联 CAPA、关联 FMEA、创建 CAPA、RMA 关联客诉均写入 `audit_logs`。
- `table_name` 分别使用 `customers`、`customer_complaints`、`rma_records`。

---

## 前端设计

### 路由和菜单

- 新增菜单：`客户质量`
- 路由：
  - `/customer-quality`
  - `/customer-quality/customers/:id`
  - `/customer-quality/complaints/:id`
  - `/customer-quality/rma/:id`

### 页面结构

`CustomerQualityPage` 使用工作台布局：

- 顶部 KPI：客户数、开放客诉、超期客诉、RMA 数、影响数量。
- 左侧客户列表：客户编号、名称、风险灯号、开放客诉数。
- 右侧 Tab：
  - `概览`: 客户摘要、趋势、风险说明。
  - `客诉`: 客诉列表、新建客诉、超期排序、严重等级标签。
  - `RMA`: RMA 列表、新建 RMA、责任判定标签。
  - `档案`: 客户基本资料和 CSR 列表只读/编辑。

详情页用于较复杂的编辑和关联操作：

- 客诉详情：基础信息、批次/序列号、发生日期、处理人、附件证据、分析字段、CAPA/FMEA 关联、创建 8D、关闭。
- RMA 详情：退货信息、批次/序列号、物流单号、处理人、附件证据、分析结果、责任判定、CAPA/FMEA 关联、关闭。

### UI 规则

- 严重等级颜色沿用 CAPA：致命红、严重橙、一般蓝、轻微默认。
- 超期客诉置顶并使用红色 Tag。
- 客诉和 RMA 列表支持“我的待办”，即 `assignee_id = 当前用户`。
- 附件字段只维护元数据和 URL；上传、预览、存储权限由后续文件服务或外部系统提供。
- viewer 隐藏创建、编辑、关闭、关联按钮；后端仍执行权限校验。
- 全局产品线选择器变化时刷新客诉、RMA 和看板；客户档案列表不因产品线过滤而消失，但摘要按产品线过滤。

---

## 与现有模块联动

### 产品线

- 客诉和 RMA 必须写入 `product_line_code`。
- 列表和看板支持 `product_line` 参数。
- 客户档案共享，不带产品线字段。

### CAPA/8D

- 客诉和 RMA 可关联已有 CAPA。
- 客诉可一键创建 CAPA，CAPA 标题默认使用客诉编号和缺陷描述摘要。
- CAPA 关闭不会自动关闭客诉；客户质量工程师或 manager 需要确认客户回复和效果验证后关闭客诉。

### FMEA

- 客诉和 RMA 可关联 FMEA 文档。
- 本期不把客诉失效模式自动写回 FMEA 图谱，只保留关联和后续知识库扩展点。

### SCAR 预留

- 当 RMA `responsibility = supplier` 或客诉 `supplier_responsibility = true` 时，界面显示“待创建 SCAR”提示。
- 本期不创建 SCAR，只保留 `scar_ref_id` 字段和后续 API 入口。

---

## 迁移和种子数据

新增 Alembic 迁移：

- 创建 `customers`
- 创建 `customer_complaints`
- 创建 `rma_records`
- 添加必要索引和外键

种子数据：

- 2 个客户。
- 3 条客诉，其中 1 条致命、1 条超期、1 条已关闭。
- 2 条 RMA，其中 1 条关联客诉，1 条独立登记。
- 种子客诉和 RMA 包含批次号、处理人和附件元数据示例。

---

## 测试策略

### 后端

新增轻量测试文件 `backend/tests/test_customer_quality.py`，沿用现有手写测试风格或 pytest 兼容写法，覆盖纯函数和服务规则：

- 超期判断。
- 风险灯号计算。
- 客户 PPM 估算在无发运数时返回空。
- 客户风险灯号在无发运数时只基于致命开放客诉和超期客诉。
- 客户风险灯号在有 `annual_shipment_qty` 或查询参数 `shipment_qty` 时纳入 PPM。
- 客诉状态转换合法/非法路径。
- RMA 状态转换合法/非法路径。

API 和数据库集成验证通过后端启动、迁移、手工 smoke 请求覆盖。

### 前端

项目当前无 Vitest 配置，本期执行：

- `npm run build`
- 页面手动 smoke：客户质量菜单、客户列表、客诉创建、RMA 创建、附件元数据录入、我的待办、看板加载、产品线过滤。

---

## ROADMAP 更新计划

本期实施完成后更新 `docs/ROADMAP.md`：

- `客诉管理`: 标记为完成，说明包含分类、严重等级、超期预警、CAPA/FMEA 联动。
- `RMA 退货管理`: 标记为完成，说明包含退货登记、不良分析、责任判定、CAPA/FMEA 联动。
- `客户质量看板`: 标记为完成，说明当前基于客诉和 RMA 数据，0 公里 PPM 与发运数据为后续增强。
- 新增 Phase2 后续说明：
  1. `SCAR 管理 + 8D 关联`: 接入 `scar_ref_id`，支持供应商责任客诉/RMA 创建 SCAR。
  2. `客户审核管理`: 复用客户档案和 CAPA 联动。
  3. `客户特殊要求 CSR/VOC`: 使用 `customers.csr_list`，后续同步控制计划。
  4. `0公里 PPM`: 增加发运/客户端接收质量数据源后替换临时 `shipment_qty` 参数。
  5. `高级客户质量看板`: 融合 SPC CPK、0公里 PPM、保修和满意度数据。

---

## 验收标准

- 客户质量菜单可访问。
- 可创建、查看、编辑客户档案。
- 客户档案可配置默认年发运量，用于列表和看板 PPM 估算。
- 可创建、查看、编辑客诉，并按产品线、客户、状态、严重等级和超期过滤。
- 客诉支持批次号、序列号、发生日期、处理人和附件元数据。
- 可从客诉创建或关联 8D/CAPA。
- 可关联 FMEA。
- 可创建、查看、编辑 RMA，并关联客诉、CAPA、FMEA。
- RMA 支持批次号、序列号、物流单号、处理人和附件元数据。
- 客诉和 RMA 支持“我的待办”过滤。
- 客诉和 RMA 关闭需要 manager/admin。
- 客户质量看板显示客户维度 KPI、风险灯号和趋势。
- 所有写操作生成审计日志。
- 未开发模块仅显示预留提示，不出现不可用的强依赖流程。
- `docs/ROADMAP.md` 明确本期完成范围和后续开发计划。
