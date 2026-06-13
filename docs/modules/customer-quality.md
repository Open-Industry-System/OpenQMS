# 客户质量管理模块 — 用户手册

> 最后更新: 2026-06-13 | 适用版本: OpenQMS v1.0

---

## 1. 功能概述

客户质量管理模块覆盖从客户投诉受理到供应商纠正措施 (SCAR) 的全流程闭环管理，包含以下四个子模块：

| 子模块 | 路由 | 功能范围 |
|--------|------|----------|
| 客诉管理 | `/customer-quality`, `/customer-quality/complaints/:id` | 客户投诉登记、调查、回复、关闭 |
| RMA 退货管理 | `/customer-quality`, `/customer-quality/rma/:id` | 退货接收、缺陷分析、责任判定、关闭 |
| 客户审核 | `/customer-audits`, `/customer-audits/:id` | 客户审核计划、发现项跟踪、客户确认 |
| SCAR 供应商纠正措施 | `/scars`, `/scars/:id` | 从客诉/RMA/IQC 不良发起 SCAR，跟踪供应商整改 |

这四个子模块通过数据关联实现端到端追溯：客诉可关联 RMA、FMEA、CAPA；RMA 可关联客诉、FMEA、CAPA；SCAR 可从客诉或 RMA 一键发起；客户审核发现项可关联 CAPA。

---

## 2. 适用角色与权限

权限模型采用 **ModuleKey × PermissionLevel × 角色** 三级结构。PermissionLevel 含义：0 = NONE（不可见）、1 = VIEW（只读）、2 = CREATE（可新建）、3 = EDIT（可编辑）、4 = APPROVE（可审批/关闭）、5 = ADMIN（完全控制）。

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| customer_quality | 5 | 4 | 1 | 1 | 0 | 3 | 1 |
| customer_audit | 5 | 4 | 1 | 1 | 0 | 3 | 1 |
| scar | 5 | 4 | 1 | 1 | 3 | 1 | 1 |

**操作与最低权限对照：**

| 操作 | 所需 PermissionLevel |
|------|----------------------|
| 查看列表/详情 | VIEW (1) |
| 新建/编辑/状态流转 | CREATE (2) |
| 关闭客诉/关闭 RMA | APPROVE (4) |
| SCAR 验证 (verify) / 关闭 (close) | APPROVE (4) |
| SCAR 开始 (start) / 回复 (respond) | CREATE (2) |

> 注意：`supplier_qe` 角色对 `customer_quality` 和 `customer_audit` 模块权限为 NONE (0)，即看不到这两个模块的菜单和数据；`customer_qe` 对 `scar` 仅有 VIEW 权限，无法直接操作 SCAR。

---

## 3. 客诉管理

### 3.1 客诉列表

**路由：** `/customer-quality`（Tab: 客诉）

列表页支持以下筛选条件：

- 产品线 (`product_line`)
- 客户 (`customer_id`)
- 状态 (`status`)
- 严重度 (`severity`)
- 是否逾期 (`overdue`)
- 负责人 (`assignee_id`)

列表返回字段：`complaint_no`、客户名称、产品线、严重度、类别、状态、逾期标记、创建时间。

### 3.2 新建客诉

**API：** `POST /api/customer-complaints`

必填字段：

| 字段 | 说明 | 取值 |
|------|------|------|
| `complaint_no` | 客诉编号（全局唯一） | 自定义编号，如 `CP-2026-001` |
| `product_line_code` | 产品线 | 系统已有产品线编码 |
| `customer_id` | 客户 | 关联 `customers` 表 |
| `category` | 缺陷类别 | `safety`（安全）、`function`（功能）、`appearance`（外观）、`delivery`（交付） |
| `severity` | 严重度 | `致命`、`严重`、`一般`、`轻微` |
| `defect_desc` | 缺陷描述 | 自由文本 |
| `received_date` | 接收日期 | 日期 |

选填字段：

| 字段 | 说明 |
|------|------|
| `product_id` | 产品编号 |
| `batch_no` | 批次号 |
| `serial_number` | 序列号 |
| `impact_qty` | 影响数量，默认 0 |
| `occurred_date` | 发生日期 |
| `due_date` | 截止日期 |
| `fmea_ref_id` | 关联 FMEA 文档 |
| `capa_ref_id` | 关联 8D/CAPA |
| `assignee_id` | 负责人 |
| `preliminary_response` | 初步回复 |
| `root_cause` | 根本原因 |
| `corrective_action` | 纠正措施 |
| `attachments` | 附件列表 (JSONB) |
| `supplier_responsibility` | 是否判定供应商责任，默认 false |
| `supplier_id` | 责任供应商 |
| `scar_ref_id` | 关联 SCAR |

> `status` 默认为 `open`。创建时不能指定 `closed` 或 `cancelled`。

### 3.3 客诉状态流转

客诉遵循以下状态机：

```
open ──start_investigation──▶ investigating
investigating ──mark_responded──▶ responded
responded ──close──▶ closed
open / investigating ──cancel──▶ cancelled
responded ──start_investigation──▶ investigating
```

| 当前状态 | 操作 | 目标状态 | 最低权限 | API |
|----------|------|----------|----------|-----|
| open | start_investigation | investigating | CREATE | `POST /api/customer-complaints/{id}/start-investigation` |
| investigating | mark_responded | responded | CREATE | `POST /api/customer-complaints/{id}/mark-responded` |
| responded | close | closed | APPROVE | `POST /api/customer-complaints/{id}/close` |
| open / investigating | cancel | cancelled | CREATE | `POST /api/customer-complaints/{id}/cancel` |
| responded | start_investigation | investigating | CREATE | `POST /api/customer-complaints/{id}/start-investigation` |

关闭客诉时，系统自动记录 `closed_at` 时间戳。

### 3.4 关联操作

| 操作 | API | 说明 |
|------|-----|------|
| 关联 CAPA | `POST /api/customer-complaints/{id}/link-capa?capa_ref_id=…` | 将已有 8D/CAPA 报告关联到客诉 |
| 从客诉创建 CAPA | `POST /api/customer-complaints/{id}/create-capa?document_no=…` | 自动创建 8D 报告，并关联到客诉；客诉状态变为 `investigating` |
| 关联 FMEA | `POST /api/customer-complaints/{id}/link-fmea?fmea_ref_id=…` | 将 FMEA 文档关联到客诉 |
| 从客诉创建 SCAR | `POST /api/customer-complaints/{id}/create-scar` | 前提：`supplier_responsibility=true` 且尚未关联 SCAR |

### 3.5 客诉编辑限制

- 当客诉已关联 RMA 记录时，不可更改客户 (`customer_id`) 和产品线 (`product_line_code`)。
- 编辑 `status` 字段时，仅允许合法的状态转移路径；`closed` 和 `cancelled` 必须通过 transition 端点操作。
- 严重度 (`severity`) 和类别 (`category`) 的取值必须符合预定义枚举。

### 3.6 逾期判定

客诉的逾期状态由 `due_date` 和 `status` 决定：

- `due_date < 今天` 且状态不是 `closed` 或 `cancelled` → 逾期
- `due_date` 为空或状态为终态 → 不逾期

---

## 4. RMA 退货管理

### 4.1 RMA 列表

**路由：** `/customer-quality`（Tab: RMA）

筛选条件：产品线、客户、关联客诉、状态、责任方、负责人。

### 4.2 新建 RMA

**API：** `POST /api/rma-records`

必填字段：

| 字段 | 说明 | 取值 |
|------|------|------|
| `rma_no` | RMA 编号（全局唯一） | 自定义编号 |
| `product_line_code` | 产品线 | 系统已有产品线编码 |
| `customer_id` | 客户 | 关联 `customers` 表 |
| `return_qty` | 退货数量 | 正整数 |
| `defect_type` | 缺陷类型 | 自由文本 |

选填字段：

| 字段 | 说明 |
|------|------|
| `complaint_id` | 关联客诉（如有关联） |
| `product_id` | 产品编号 |
| `batch_no` | 批次号 |
| `serial_number` | 序列号 |
| `responsibility` | 责任判定：`supplier`、`internal`、`transport`、`customer_misuse`、`unknown` |
| `analysis_result` | 分析结果 |
| `corrective_action` | 纠正措施 |
| `fmea_ref_id` | 关联 FMEA |
| `capa_ref_id` | 关联 8D/CAPA |
| `scar_ref_id` | 关联 SCAR |
| `attachments` | 附件列表 (JSONB) |
| `assignee_id` | 负责人 |
| `tracking_number` | 物流追踪号 |
| `received_date` | 收货日期 |

> 若 `complaint_id` 非空，系统校验 RMA 的 `customer_id` 和 `product_line_code` 必须与关联客诉一致，否则返回错误。新建 RMA 时，若关联了客诉，系统自动将客诉的 `has_rma` 标记为 `true`。

### 4.3 RMA 状态流转

```
open ──start_analysis──▶ analysis
analysis ──mark_action_pending──▶ action_pending
action_pending ──close──▶ closed
open / analysis ──cancel──▶ cancelled
```

| 当前状态 | 操作 | 目标状态 | 最低权限 | API |
|----------|------|----------|----------|-----|
| open | start_analysis | analysis | CREATE | `POST /api/rma-records/{id}/start-analysis` |
| analysis | mark_action_pending | action_pending | CREATE | `POST /api/rma-records/{id}/mark-action-pending` |
| action_pending | close | closed | APPROVE | `POST /api/rma-records/{id}/close` |
| open / analysis | cancel | cancelled | CREATE | `POST /api/rma-records/{id}/cancel` |

关闭 RMA 时，系统自动记录 `closed_at` 时间戳。

### 4.4 责任判定

RMA 的 `responsibility` 字段用于记录退货责任归属：

| 值 | 中文含义 | 后续影响 |
|----|----------|----------|
| `supplier` | 供应商 | 可从该 RMA 直接创建 SCAR |
| `internal` | 内部 | 内部整改 |
| `transport` | 运输 | 物流索赔 |
| `customer_misuse` | 客户误用 | 拒赔/说明 |
| `unknown` | 待定 | 继续调查 |

### 4.5 关联操作

| 操作 | API | 说明 |
|------|-----|------|
| 关联客诉 | `POST /api/rma-records/{id}/link-complaint?complaint_id=…` | 校验客户和产品线一致性 |
| 关联 CAPA | `POST /api/rma-records/{id}/link-capa?capa_ref_id=…` | 关联 8D/CAPA |
| 关联 FMEA | `POST /api/rma-records/{id}/link-fmea?fmea_ref_id=…` | 关联 FMEA |
| 从 RMA 创建 SCAR | `POST /api/rma-records/{id}/create-scar` | 前提：`responsibility=supplier` 且尚未关联 SCAR |

### 4.6 客诉与 RMA 联动

- 关联客诉后，客诉的 `has_rma` 自动变为 `true`。
- 取消关联（改为其他客诉）时，旧客诉如无其他 RMA 关联，`has_rma` 自动回退为 `false`。
- 不可在有 RMA 关联时更改客诉的客户或产品线。

---

## 5. 客户审核

### 5.1 审核列表

**路由：** `/customer-audits`

筛选条件：客户类型、审核方式、客户名称、状态、产品线。

### 5.2 新建审核

**API：** `POST /api/audit-plans`

必填字段：

| 字段 | 说明 | 取值 |
|------|------|------|
| `audit_scope` | 审核范围 | 自由文本 |
| `audit_criteria` | 审核准则 | 自由文本 |
| `planned_date` | 计划日期 | 日期 |
| `customer_name` | 客户名称 | 自由文本 |
| `customer_type` | 客户类型 | `OEM`、`Tier 1`、`Tier 2`、`其他` |

选填字段：

| 字段 | 说明 |
|------|------|
| `audit_mode` | 审核方式：`on_site`（现场）、`remote`（远程） |
| `lead_auditor` | 主审核员 |
| `team_members` | 审核组成员 (JSONB) |
| `checklist` | 审核检查表 (JSONB) |
| `product_line_code` | 产品线 |

> 系统自动生成审核编号 (`plan_no`)，格式为 `CA-{年份}-{序号}`，如 `CA-2026-001`。系统同时自动创建或关联对应年度的客户审核方案 (`AuditProgram`)。

### 5.3 审核状态

客户审核使用 `AuditPlan` 模型，`audit_category` 固定为 `"customer"`，状态沿用审核模块状态机：

| 状态 | 说明 |
|------|------|
| `planned` | 已计划 |
| `in_progress` | 进行中 |
| `completed` | 已完成 |

**完成审核条件：** 所有发现项必须已关闭 (`status=closed`) 且已获得客户确认 (`customer_confirmed=true`)。

### 5.4 发现项管理

客户审核的发现项使用 `AuditFinding` 模型，额外包含客户确认字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `customer_confirmed` | boolean | 客户是否确认，默认 false |
| `customer_confirmation_date` | date | 客户确认日期 |
| `customer_confirmation_attachments` | JSONB | 客户确认附件 |

发现项状态流转：

```
open ──start_progress──▶ in_progress ──close──▶ closed
```

**关闭条件：**
- 必须填写 `root_cause` 和 `corrective_action`
- 如关联了 CAPA，CAPA 状态必须为 `D8_CLOSURE`
- 客户审核发现项关闭时，`customer_confirmed` 必须为 `true`

### 5.5 客户确认

**API：** `POST /api/audit-findings/{finding_id}/customer-confirm`

客户端可独立确认发现项（不改变工作流状态），传入：
- `confirmation_date`：确认日期
- `attachments`：确认附件

确认后 `customer_confirmed` 变为 `true`，记录确认日期和附件。

### 5.6 审核统计

**API：** `GET /api/customer-audits/stats`

返回统计信息：

| 字段 | 说明 |
|------|------|
| `total_customer_audits` | 审核总数 |
| `planned` | 计划中 |
| `in_progress` | 进行中 |
| `completed` | 已完成 |
| `open_findings` | 未关闭发现项数 |
| `major_nc_count` | 重大不符合项数 |
| `customer_confirmed_count` | 已获客户确认数 |
| `pending_confirmation_count` | 待客户确认数 |

---

## 6. SCAR 供应商纠正措施

### 6.1 SCAR 列表

**路由：** `/scars`

筛选条件：状态（支持多选逗号分隔）、供应商、来源类型 (`source_type`)。

### 6.2 新建 SCAR

**API：** `POST /api/scars`

必填字段：

| 字段 | 说明 | 取值 |
|------|------|------|
| `supplier_id` | 供应商 | 关联 `suppliers` 表 |
| `source_type` | 来源类型 | `iqc`、`complaint`、`rma`、`manual` |
| `description` | 问题描述 | 自由文本 |

选填字段：

| 字段 | 说明 |
|------|------|
| `source_id` | 来源 ID（IQC 检验 ID / 客诉 ID / RMA ID） |
| `product_line_code` | 产品线 |
| `requested_action` | 要求供应商采取的措施 |
| `due_date` | 截止日期 |

> 系统自动生成 SCAR 编号，格式为 `SCAR-{YYMMDD}-{序号}`，如 `SCAR-260613-001`。状态默认为 `open`。

### 6.3 SCAR 状态流转

SCAR 采用 5 状态生命周期：

```
open ──start──▶ in_progress ──respond──▶ responded
responded ──verify──▶ verified ──close──▶ closed
responded ──reject──▶ open
verified ──reopen──▶ in_progress
```

| 动作 | 当前状态 | 目标状态 | 最低权限 | 必填字段 |
|------|----------|----------|----------|----------|
| start | open | in_progress | CREATE (2) | — |
| respond | in_progress | responded | CREATE (2) | `supplier_response` |
| verify | responded | verified | APPROVE (4) | — |
| reject | responded | open | APPROVE (4) | — |
| close | verified | closed | APPROVE (4) | `resolution_summary` |
| reopen | verified | in_progress | APPROVE (4) | — |

**API：** `POST /api/scars/{id}/transition`

请求体：
```json
{
  "action": "start",
  "supplier_response": "...",
  "resolution_summary": "..."
}
```

### 6.4 从客诉/RMA 创建 SCAR

除了直接创建 SCAR，还可从客诉或 RMA 一键发起：

| 来源 | API | 前提条件 |
|------|-----|-----------|
| 客诉 | `POST /api/customer-complaints/{id}/create-scar` | `supplier_responsibility=true` 且 `scar_ref_id` 为空 |
| RMA | `POST /api/rma-records/{id}/create-scar` | `responsibility=supplier` 且 `scar_ref_id` 为空 |

从客诉发起时，系统自动将客诉的 `scar_ref_id` 回填为创建的 SCAR ID。从 RMA 发起时同理。

创建请求体 (SCARRelatedCreate)：

```json
{
  "supplier_id": "uuid",           // 必填（RMA 发起时无默认值，必须手动指定）
  "description": "...",            // 可选，默认取客诉的 defect_desc 或 RMA 的 defect_type + analysis_result
  "requested_action": "...",       // 可选
  "due_date": "2026-07-31"         // 可选
}
```

### 6.5 关联 CAPA

**API：** `POST /api/scars/{id}/link-capa`

请求体：`{ "capa_ref_id": "uuid" }`

将 8D/CAPA 报告关联到 SCAR，用于跟踪供应商整改效果。

### 6.6 SCAR 关闭与风险预警联动

当 SCAR 状态变为 `closed` 时，系统自动将所有关联的未关闭供应商风险预警 (`SupplierRiskAlert`) 标记为已关闭。

---

## 7. 客户质量看板

**API：** `GET /api/customer-quality/dashboard`

看板提供以下维度的数据：

| 指标 | 说明 |
|------|------|
| 客诉总数 / 开放客诉数 / 逾期数 | 按时间窗口统计 |
| RMA 总数 / 退货总量 / 独立退货量 | 独立退货量 = 不关联客诉的 RMA 退货数 |
| 影响数量 (impact_qty) | 所有客诉的影响数量之和 |
| PPM | (影响数量 + 独立退货量) / 出货量 × 1,000,000 |
| 风险灯号 | red/yellow/green，基于逾期数、致命客诉、PPM 与目标值比较 |
| SPC Cpk/Ppk | 按产品线的制程能力指数 |
| 保修金额 | 时间窗口内保修总额 |
| 客户满意度 | 平均满意度评分 |
| 客户审核摘要 | 已完成审核数、发现项数、最近审核日期 |

**客户摘要 (Customer Summary)：**

每个客户提供：客诉数、开放客诉数、逾期数、致命客诉数、RMA 数、PPM、风险灯号。

**趋势图数据：** 按月汇总客诉数、RMA 数、退货量。

---

## 8. 常见问题

### Q1：为什么无法创建 SCAR？

**A：** 检查以下几点：
1. 确认你有 `scar` 模块的 CREATE 权限（supplier_qe 或更高角色）。
2. 从客诉发起 SCAR 时，客诉的 `supplier_responsibility` 必须为 `true`，且 `scar_ref_id` 必须为空。
3. 从 RMA 发起 SCAR 时，RMA 的 `responsibility` 必须为 `supplier`。
4. 供应商 ID 必须存在于系统中。

### Q2：客诉关闭按钮为什么灰显？

**A：** 关闭客诉需要 APPROVE 权限（PermissionLevel >= 4）。只有 admin 和 manager 角色可以关闭客诉。

### Q3：RMA 关联客诉时提示"不属于同一客户或产品线"？

**A：** RMA 的 `customer_id` 和 `product_line_code` 必须与关联客诉完全一致。请检查 RMA 和客诉的客户及产品线选择。

### Q4：客户审核发现项无法关闭？

**A：** 关闭客户审核发现项需要同时满足：
1. 已填写 `root_cause`（根本原因）和 `corrective_action`（纠正措施）。
2. 如关联了 CAPA，CAPA 状态必须为 `D8_CLOSURE`。
3. `customer_confirmed` 必须为 `true`。可通过 `POST /api/customer-audits/findings/{id}/confirm` 单独完成客户确认。

### Q5：SCAR 编号冲突怎么办？

**A：** SCAR 编号使用日期+序号格式自动生成。如果极短时间内并发创建，可能出现编号冲突，系统会自动重试最多 3 次。如果持续失败，请稍后重试。

### Q6：如何从客诉直接创建 CAPA？

**A：** 使用 `POST /api/customer-complaints/{id}/create-capa?document_no=XXX`。系统会自动创建 8D 报告（状态为 `D1_TEAM`），并将客诉的 `capa_ref_id` 关联，同时将客诉状态推进为 `investigating`。

### Q7：customer_qe 角色能看到 SCAR 列表吗？

**A：** 可以。customer_qe 对 `scar` 模块有 VIEW 权限，可以查看 SCAR 列表和详情，但不能创建、流转或关闭 SCAR。如需操作 SCAR，请使用 supplier_qe 或更高级角色。

### Q8：逾期客诉如何计算？

**A：** 逾期 = `due_date` 早于今天 且 状态不是 `closed` 或 `cancelled`。如果 `due_date` 为空，则不判定为逾期。

### Q9：PPM 如何计算？

**A：** PPM = (客诉影响数量 + 独立 RMA 退货数量) / 出货量 × 1,000,000。出货量优先使用：
1. 显式传入的 `shipment_qty` 参数
2. `shipment_records` 表中时间窗口内的出货总量
3. 客户的 `annual_shipment_qty` 按时间窗口天数折算

如果三者均不可用，PPM 返回 `null`。

### Q10：风险灯号如何判定？

| 条件 | 灯号 |
|------|------|
| 存在开放致命客诉 或 存在逾期客诉 | 🔴 red |
| PPM > 2×目标值 | 🔴 red |
| PPM > 目标值（且非 red） | 🟡 yellow |
| 有开放客诉（且非 red/yellow） | 🟡 yellow |
| 以上均不满足 | 🟢 green |

---

## 附录：API 端点汇总

### 客户管理

| 方法 | 端点 | 最低权限 |
|------|------|----------|
| GET | `/api/customers` | VIEW |
| POST | `/api/customers` | CREATE |
| GET | `/api/customers/{id}` | VIEW |
| PUT | `/api/customers/{id}` | CREATE |
| GET | `/api/customers/{id}/summary` | VIEW |

### 客诉管理

| 方法 | 端点 | 最低权限 |
|------|------|----------|
| GET | `/api/customer-complaints` | VIEW |
| POST | `/api/customer-complaints` | CREATE |
| GET | `/api/customer-complaints/{id}` | VIEW |
| PUT | `/api/customer-complaints/{id}` | CREATE |
| POST | `/api/customer-complaints/{id}/start-investigation` | CREATE |
| POST | `/api/customer-complaints/{id}/mark-responded` | CREATE |
| POST | `/api/customer-complaints/{id}/close` | APPROVE |
| POST | `/api/customer-complaints/{id}/cancel` | CREATE |
| POST | `/api/customer-complaints/{id}/link-capa` | CREATE |
| POST | `/api/customer-complaints/{id}/create-capa` | CREATE |
| POST | `/api/customer-complaints/{id}/link-fmea` | CREATE |
| POST | `/api/customer-complaints/{id}/create-scar` | CREATE |

### RMA 管理

| 方法 | 端点 | 最低权限 |
|------|------|----------|
| GET | `/api/rma-records` | VIEW |
| POST | `/api/rma-records` | CREATE |
| GET | `/api/rma-records/{id}` | VIEW |
| PUT | `/api/rma-records/{id}` | CREATE |
| POST | `/api/rma-records/{id}/start-analysis` | CREATE |
| POST | `/api/rma-records/{id}/mark-action-pending` | CREATE |
| POST | `/api/rma-records/{id}/close` | APPROVE |
| POST | `/api/rma-records/{id}/cancel` | CREATE |
| POST | `/api/rma-records/{id}/link-complaint` | CREATE |
| POST | `/api/rma-records/{id}/link-capa` | CREATE |
| POST | `/api/rma-records/{id}/link-fmea` | CREATE |
| POST | `/api/rma-records/{id}/create-scar` | CREATE |

### SCAR 管理

| 方法 | 端点 | 最低权限 |
|------|------|----------|
| GET | `/api/scars` | VIEW |
| POST | `/api/scars` | CREATE |
| GET | `/api/scars/{id}` | VIEW |
| PUT | `/api/scars/{id}` | CREATE |
| POST | `/api/scars/{id}/transition` | 见动作权限表 |
| POST | `/api/scars/{id}/link-capa` | CREATE |

### 客户审核

| 方法 | 端点 | 最低权限 |
|------|------|----------|
| GET | `/api/audit-plans` | VIEW |
| POST | `/api/audit-plans` | CREATE |
| GET | `/api/audit-plans/{id}` | VIEW |
| PUT | `/api/audit-plans/{id}` | CREATE |
| POST | `/api/audit-plans/{id}/complete` | APPROVE |
| GET | `/api/audit-plans/customer-stats` | VIEW |
| POST | `/api/audit-findings/{finding_id}/customer-confirm` | CREATE |

### 看板与统计

| 方法 | 端点 | 最低权限 |
|------|------|----------|
| GET | `/api/customer-quality/dashboard` | VIEW |
| GET | `/api/customer-quality/customers/{id}/trend` | VIEW |
| GET | `/api/customer-complaints/by-supplier/{supplier_id}` | VIEW |