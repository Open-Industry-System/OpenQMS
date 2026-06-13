# IQC 与供应商管理模块用户手册

## 1. 功能概述

本手册涵盖 OpenQMS 中四个紧密关联的模块：

| 模块 | 核心功能 | 前端路由前缀 |
|------|---------|-------------|
| IQC 来料检验 | 检验批创建、AQL 抽样方案自动计算、判定与复检、AQL 动态优化 | `/iqc` |
| 供应商管理 | 供应商主数据、评级评价（A/B/C/D）、质量绩效仪表板 | `/suppliers` |
| 供应商风险 | 风险规则配置、供应商风险评分与告警、告警处理 | `/supplier-risk` |
| 供应链风险地图 | 多维度热力图、供应商快照对比、时间趋势 | `/supply-chain-risk-map` |

这四个模块的数据流关系：

```
IQC 检验 ──→ 供应商绩效数据（PPM、批次合格率）
                              │
                              ▼
供应商评价（A/B/C/D 评级）──→ 供应商风险评分 ──→ 供应链风险地图
                                                        │
SCAR / CAPA ◄────────────── 告警处理 ◄───────────────┘
```

---

## 2. 适用角色与权限

OpenQMS 采用五级权限模型：NONE(0)、VIEW(1)、CREATE(2)、EDIT(3)、APPROVE(4)、ADMIN(5)。

| 模块 (ModuleKey) | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `iqc` | 5 | 4 | 1 | 1 | 3 | 0 | 1 |
| `supplier` | 5 | 4 | 1 | 1 | 3 | 1 | 1 |
| `supplier_risk` | 5 | 4 | 3 | 1 | 3 | 1 | 1 |
| `supply_chain_risk_map` | 5 | 5 | 3 | 3 | 3 | 3 | 1 |

**权限级别说明：**

| 级别 | 值 | 能力 |
|------|:-:|------|
| NONE | 0 | 无法访问该模块 |
| VIEW | 1 | 只读：查看列表、详情、仪表板 |
| CREATE | 2 | VIEW + 新建记录 |
| EDIT | 3 | CREATE + 修改/编辑已有记录 |
| APPROVE | 4 | EDIT + 审批、判定、关闭等高级操作 |
| ADMIN | 5 | 全部操作，含配置管理、批量评估 |

**典型操作与所需权限：**

| 操作 | 所需权限级别 |
|------|:---:|
| 查看检验记录列表 | VIEW (1) |
| 创建检验批 | CREATE (2) |
| 编辑检验项结果 | EDIT (3) |
| 判定检验（接收/拒收） | APPROVE (4) |
| 配置 AQL 参数 | ADMIN (5) |
| 查看供应商列表 | VIEW (1) |
| 创建供应商 | CREATE (2) |
| 编辑供应商信息 | EDIT (3) |
| 供应商评价打分 | APPROVE (4) |
| 触发全部供应商风险评估 | APPROVE (4) |
| 修改风险规则配置 | ADMIN (5) |

---

## 3. IQC 来料检验

### 3.1 模块总览

IQC（Incoming Quality Control，来料质量控制）模块用于管理从供应商进货物料的质量检验全过程，支持两种检验模式：

- **快速检验 (quick)**：逐批录入检验信息，适用于常规来料检验
- **详细检验 (detailed)**：基于检验模板创建多检验项，适用于关键物料或需要逐项记录测量数据的场景

**前端路由：**

| 路由 | 功能 |
|------|------|
| `/iqc/inspections` | 检验批列表 |
| `/iqc/inspections/:id` | 检验批详情（含检验项与测量记录） |
| `/iqc/materials` | 物料主数据管理 |
| `/iqc/aql-optimization` | AQL 动态优化主页面 |
| `/iqc/aql-optimization/profiles` | AQL Profile 列表 |
| `/iqc/aql-optimization/profiles/:supplierId/:materialId` | 单个 Profile 详情 |
| `/iqc/aql-optimization/config` | AQL 全局配置 |

### 3.2 物料主数据

**路由：** `/iqc/materials`

物料主数据是 IQC 检验的基础。每个物料记录包含以下信息：

| 字段 | 说明 |
|------|------|
| `part_no` | 物料编号（唯一） |
| `part_name` | 物料名称 |
| `part_spec` | 规格描述 |
| `material_type` | 物料类型，默认 `raw`（原材料） |
| `default_aql` | 默认 AQL 值（如 1.0、2.5 等） |
| `default_inspection_level` | 默认检验水平（如 `II`） |
| `unit` | 计量单位 |
| `product_line_code` | 产品线代码，默认 `DC-DC-100` |
| `status` | 状态：`active` / `inactive` |

物料主数据可为后续创建检验批提供默认 AQL 和检验水平，避免每次手动输入。

### 3.3 检验批管理

**路由：** `/iqc/inspections`

#### 3.3.1 创建检验批

创建检验批时需填写以下信息：

| 字段 | 说明 | 必填 |
|------|------|:---:|
| `supplier_id` | 供应商 | 是 |
| `inspection_mode` | 检验模式：`quick`（快速）或 `detailed`（详细） | 是 |
| `material_id` | 物料（关联物料主数据） | 否 |
| `template_id` | 检验模板（详细模式必填） | 否 |
| `part_no` | 零件编号 | 否 |
| `part_name` | 零件名称 | 否 |
| `lot_no` | 批次号 | 否 |
| `lot_qty` | 批量大小 | 否 |
| `aql_level` | AQL 水平 | 否（自动推断） |
| `inspection_level` | 检验水平，默认 `II` | 否 |
| `inspection_date` | 检验日期 | 否 |

**AQL 自动推断逻辑：**

1. 若用户未指定 `aql_level`，系统首先查找该供应商+物料的 AQL Profile 中的 `current_aql`
2. 若 Profile 不存在或为 `frozen` 状态，回退到物料主数据的 `default_aql`
3. 最终若批量大小 `lot_qty` 和 `aql_level` 均有值，自动调用 `calculate_aql_plan()` 计算抽样方案

#### 3.3.2 AQL 抽样方案自动计算

系统依据 **ISO 2859-1 / GB/T 2828.1** 标准实现 AQL 抽样方案自动计算。输入批量大小 `lot_qty`、AQL 水平 `aql_level` 和检验水平 `inspection_level` 后，系统自动输出：

| 输出 | 说明 |
|------|------|
| `code_letter` | 样本量字码 |
| `sample_qty` | 应抽检数量 |
| `accept_number` | 合格判定数 (Ac) |
| `reject_number` | 不合格判定数 (Re) |

**检验水平对应的字码调整：**

| 检验水平 | 字码偏移 |
|----------|---------|
| S-1 | -4 |
| S-2 | -3 |
| S-3 | -2 |
| S-4 | -1 |
| I | -1 |
| II | 0（基准） |
| III | +1 |

**判定规则：**
- 缺陷数 ≤ Ac → 接收（`accepted`）
- 缺陷数 ≥ Re → 拒收（`rejected`）

#### 3.3.3 检验项与测量记录

当使用**详细检验模式 (detailed)** 并关联检验模板时，系统自动从模板实例化检验项 (IqcInspectionItem)：

| 字段 | 说明 |
|------|------|
| `category` | 检验类别（如外观、尺寸、性能） |
| `item_name` | 检验项名称 |
| `inspect_type` | 检验类型：`attribute`（计件）或 `variable`（计量） |
| `spec_upper` / `spec_lower` | 规格上限 / 下限 |
| `target_value` | 目标值 |
| `sample_size` | 该项抽检数量 |
| `aql_level` | 该项 AQL 水平 |

每个检验项下可录入多次测量记录 (IqcItemMeasurement)，含 `measured_value`（计量值）或 `attribute_result`（计件判定结果）。

#### 3.3.4 检验判定

检验批状态机：

```
pending → in_progress → judged
                          ├── accepted（接收）
                          ├── rejected（拒收）
                          └── conditionally_accepted（有条件接收）
```

判定操作 (`judge_inspection`) 需要 APPROVE 权限。判定时可标记：
- `has_safety_defect`：是否存在安全相关缺陷
- `defect_description`：缺陷描述
- `linked_capa_id`：关联 CAPA 记录
- `linked_scar_id`：关联 SCAR 记录

#### 3.3.5 复检

对已判定的检验批可发起复检 (`request_reinspect`)。系统将：
- 创建新的检验批，标记 `re_inspection = True`
- 记录 `parent_inspection_id` 指向原检验批
- 原 AQL 状态若为 `normal`，自动触发加严检验评估

### 3.4 检验模板

检验模板 (IqcInspectionTemplate) 关联物料，用于详细检验模式的自动实例化：

- 一个模板包含多个检验项 (IqcTemplateItem)
- 每项定义类别、名称、检验方法、规格上下限、目标值、样本量、AQL 水平
- 模板有版本号 `version`，支持通过 `is_active` 字段启用/停用

### 3.5 AQL 动态优化

**路由：** `/iqc/aql-optimization`

AQL 动态优化功能基于供应商+物料的历史检验表现，自动调整 AQL 检验水平，减少优质供应商的检验成本，同时加强对问题供应商的管控。

#### 3.5.1 AQL Profile

**路由：** `/iqc/aql-optimization/profiles`

每个「供应商 + 物料」组合对应一个 AQL Profile (IqcAqlProfile)：

| 字段 | 说明 |
|------|------|
| `base_aql` | 基准 AQL 值 |
| `current_aql` | 当前生效的 AQL 值 |
| `min_aql` / `max_aql` | AQL 变动范围限制 |
| `inspection_level` | 当前检验水平 |
| `state` | 状态：`normal` / `tightened` / `reduced` / `frozen` |
| `frozen_until` | 冻结截止日期（`frozen` 状态时有效） |
| `frozen_reason` | 冻结原因 |
| `baseline_inspection_id` | 基线检验批（用于后续对比） |

**状态转换规则：**

| 条件 | 新状态 | AQL 变化 |
|------|--------|---------|
| 连续 N 批合格 | `reduced` | AQL 可放宽（如 1.0 → 1.5） |
| 连续 M 批中有拒收 | `tightened` | AQL 收紧（如 1.0 → 0.65） |
| 出现安全缺陷 | `frozen` | 锁定当前 AQL，直到冻结期结束 |

#### 3.5.2 AQL 配置

**路由：** `/iqc/aql-optimization/config`

AQL 配置 (IqcAqlConfig) 为系统级参数，支持产品线级别的覆盖：

- 配置项通过 `config_key` 标识，如 `switch_normal_to_reduced_batches`（转放宽所需连续合格批数）
- 每个配置项可有全局默认值和产品线特定覆盖值
- `is_editable` 标识是否允许用户修改
- 仅 ADMIN 权限可修改配置

配置层级优先级：**产品线覆盖值 > 全局默认值 > 硬编码默认值**

#### 3.5.3 质量快照

系统在每次 AQL 评估时记录质量快照 (IqcAqlQualitySnapshot)，用于后续趋势分析：

| 字段 | 说明 |
|------|------|
| `total_inspections` | 统计窗口内检验批数 |
| `accepted_count` | 合格批数 |
| `rejected_count` | 不合格批数 |
| `ppm` | 百万分数 PPM |
| `calculated_state` | 计算得出的建议状态 |

---

## 4. 供应商管理

### 4.1 模块总览

**前端路由：**

| 路由 | 功能 |
|------|------|
| `/suppliers` | 供应商列表 |
| `/suppliers/:id` | 供应商详情 |
| `/suppliers/quality` | 供应商质量仪表板 |
| `/suppliers/quality/:supplierId` | 单个供应商质量详情 |

### 4.2 供应商主数据

#### 4.2.1 创建供应商

创建供应商时需填写：

| 字段 | 说明 | 必填 |
|------|------|:---:|
| `name` | 供应商全称 | 是 |
| `short_name` | 供应商简称 | 是 |
| `contact_name` | 联系人姓名 | 否 |
| `contact_phone` | 联系电话 | 否 |
| `contact_email` | 联系邮箱 | 否 |
| `address` | 地址 | 否 |
| `product_scope` | 供货范围 | 否 |

创建后供应商自动生成 `supplier_no`（格式 `SUP-{YYYY}-{序号}`），状态初始为 `pending_review`。

#### 4.2.2 供应商状态流转

```
pending_review → audit_required → approved
                    ↓                  ↓
                 rejected          suspended
```

| 状态 | 说明 |
|------|------|
| `pending_review` | 待审核，新建后的初始状态 |
| `audit_required` | 需现场审核 |
| `approved` | 已批准，可正常交易 |
| `rejected` | 审核不通过 |
| `suspended` | 已暂停合作 |

#### 4.2.3 供应商认证

每个供应商可关联多条认证记录 (SupplierCertification)：

| 字段 | 说明 |
|------|------|
| `cert_type` | 认证类型（如 ISO 9001、IATF 16949） |
| `cert_no` | 证书编号 |
| `issued_by` | 发证机构 |
| `issue_date` | 发证日期 |
| `expiry_date` | 到期日期 |
| `file_url` | 证书文件路径 |

#### 4.2.4 批量导入

支持通过 Excel 批量导入供应商数据。导入时系统自动校验：
- 名称 (`name`) 和简称 (`short_name`) 为必填
- 不允许重复名称或简称（含数据库已有记录）
- 单次导入上限受 `MAX_IMPORT_ROWS` 限制

### 4.3 供应商评价

#### 4.3.1 评价打分

供应商评价 (SupplierEvaluation) 采用加权评分法，按评价周期（`eval_period`，如 `2026-Q1`）录入：

**评分维度与权重：**

| 维度 | 权重 | 评分范围 |
|------|:---:|---------|
| 质量评分 `quality_score` | 35% | 0–100 |
| 交付评分 `delivery_score` | 30% | 0–100 |
| 服务评分 `service_score` | 15% | 0–100 |

**扣分项（上限各 10 分）：**

| 扣分项 | 单位扣分 | 说明 |
|--------|:---:|------|
| `capa_count` | 2 分/次 | CAPA 数量 |
| `finding_count` | 3 分/次 | 审核发现数 |
| `premium_freight_count` | 5 分/次 | 加急运费次数 |
| `customer_disruption_count` | 5 分/次 | 客户中断次数 |

**计算公式：**

```
base = quality_score × 0.35 + delivery_score × 0.30 + service_score × 0.15
total_score = max(0, base - capa_penalty - finding_penalty - premium_freight_penalty - customer_disruption_penalty)
```

#### 4.3.2 评级标准

| 总分 | 评级 |
|:---:|:---:|
| ≥ 72 | A |
| ≥ 60 | B |
| ≥ 48 | C |
| < 48 | D |

#### 4.3.3 评价类型

评价类型 `eval_type` 包括：
- `periodic`：定期评价（如季度、年度）
- `event`：事件驱动评价（如重大质量问题后）

### 4.4 供应商质量仪表板

**路由：** `/suppliers/quality`

仪表板展示以下 KPI：

| 指标 | 计算方式 |
|------|---------|
| 总供应商数 | `COUNT(suppliers)` |
| 综合 PPM | `SUM(defect_qty) / SUM(lot_qty) × 1,000,000` |
| 批次合格率 | `COUNT(accepted) / COUNT(total)` |
| 开放 SCAR 数 | `COUNT(scars WHERE status != 'closed')` |

还包含：
- **评级分布**：A/B/C/D 各级供应商数量
- **PPM 趋势图**：按月统计 PPM 变化
- **供应商排名**：按总分降序，取前 20 名，展示 PPM、批次合格率、交付率、开放 SCAR

**单个供应商详情** (`/suppliers/quality/:supplierId`) 额外展示：
- 最近一次评价的各维度分数与总分
- 该供应商的 PPM 趋势和批次合格率趋势
- SCAR 统计（总数与开放数）

### 4.5 供应商 SCAR

SCAR (Supplier Corrective Action Request) 用于向供应商发起纠正措施要求：

| 字段 | 说明 |
|------|------|
| `scar_no` | SCAR 编号（自动生成） |
| `source_type` | 来源类型（如 `iqc`、`risk_alert`） |
| `source_id` | 来源记录 ID |
| `description` | 问题描述 |
| `requested_action` | 要求采取的措施 |
| `supplier_response` | 供应商回复 |
| `status` | 状态：`open` → `in_progress` → `closed` |
| `due_date` | 截止日期 |

SCAR 可从 IQC 检验拒收或供应商风险告警自动触发。

---

## 5. 供应商风险

### 5.1 模块总览

**前端路由：**

| 路由 | 功能 |
|------|------|
| `/supplier-risk` | 风险仪表板 |
| `/supplier-risk/config` | 风险规则配置 |

供应商风险模块基于可配置的风险规则，对供应商进行多维度风险评分，自动生成风险告警，并与 SCAR / CAPA 联动。

### 5.2 风险规则配置

**路由：** `/supplier-risk/config`

风险规则通过 SupplierRiskConfig 管理，支持四级优先级覆盖：

| 优先级 | 层级 | 说明 |
|:---:|------|------|
| 1（最高） | 供应商 + 产品线 | `supplier_id` + `product_line_code` 均指定 |
| 2 | 供应商全局 | 指定 `supplier_id`，`product_line_code` 为空 |
| 3 | 产品线默认 | `supplier_id` 为空，指定 `product_line_code` |
| 4（最低） | 全局默认 | `supplier_id` 和 `product_line_code` 均为空 |

每条规则配置包含：

| 字段 | 说明 |
|------|------|
| `rule_id` | 规则标识（如 `R01`） |
| `enabled` | 是否启用 |
| `thresholds` | 阈值参数（JSONB，如 `{"ppm_limit": 1000, "window_days": 90}`） |
| `weight` | 权重，用于加权计算总分 |
| `category` | 风险类别：`quality`（质量）、`delivery`（交付）、`compliance`（合规） |
| `product_line_code` | 产品线代码（为空表示全局） |
| `supplier_id` | 供应商 ID（为空表示全局） |

### 5.3 风险评估流程

风险评估分两种模式：

1. **单供应商评估** (`POST /supplier-risk/evaluate/{supplier_id}`)：需要 EDIT 权限
2. **全部供应商评估** (`POST /supplier-risk/evaluate`)：需要 APPROVE 权限

评估步骤：

```
1. 获取有效的规则配置（按优先级）
2. 采集数据：
   ├── IQC 检验记录（PPM、批次合格率）
   ├── SCAR 记录
   ├── 供应商评价记录
   └── 认证记录
3. 运行所有规则 → 生成 RuleResult 列表
4. 加权计算风险评分 → RiskScore
5. 生成/更新风险告警 → SupplierRiskAlert
6. 若为新增或升级的高风险告警，发送通知
```

### 5.4 风险评分与等级

**评分维度：**

| 维度 | 数据来源 |
|------|---------|
| `quality_score` | IQC 检验 PPM、批次合格率 |
| `delivery_score` | 交付准时率（ERP 或评价数据） |
| `compliance_score` | 认证到期、SCAR 开放数量 |

**风险等级：**

| 风险评分 | 等级 | 说明 |
|:---:|:---:|------|
| — | `low` | 低风险，不生成告警 |
| — | `medium` | 中等风险 |
| — | `high` | 高风险，发送通知 |
| — | `critical` | 严重风险，发送通知 |

### 5.5 风险告警

风险告警 (SupplierRiskAlert) 记录：

| 字段 | 说明 |
|------|------|
| `risk_level` | 风险等级 |
| `risk_score` | 综合风险分 |
| `quality_score` / `delivery_score` / `compliance_score` | 各维度分数 |
| `rule_results` | 触发的规则结果（JSONB） |
| `alert_type` | 告警类型：`initial`（首次）/ `escalated`（升级） |
| `status` | 状态：`open` / `acknowledged` / `resolved` |
| `handled_by` | 处理人 |
| `handle_note` | 处理备注 |
| `linked_scar_id` | 关联 SCAR |
| `linked_capa_id` | 关联 CAPA |

**告警事件类型：**

| 事件 | 说明 |
|------|------|
| `new` | 新生成的告警 |
| `escalated` | 风险等级升级的告警 |
| `unchanged` | 同等级或降级的更新 |

告警按 `(supplier_id, product_line_code, snapshot_date)` 去重，同一天同供应商同产品线只保留最新一条。

### 5.6 通知渠道

告警通知通过 SupplierRiskNotificationChannel 配置：

| 字段 | 说明 |
|------|------|
| `channel_type` | 通知类型（如 `email`、`webhook`） |
| `config` | 通知配置（JSONB，如邮箱地址、webhook URL） |
| `min_risk_level` | 最低通知风险等级，默认 `high` |
| `enabled` | 是否启用 |

---

## 6. 供应链风险地图

### 6.1 模块总览

**路由：** `/supply-chain-risk-map`

供应链风险地图以热力图形式展示多供应商、多维度风险全景，支持时间轴回溯与供应商对比。

### 6.2 数据快照

系统通过定时任务将各供应商的风险评分聚合成快照 (SupplyChainRiskSnapshot)，每个快照记录一个月份的风险数据：

| 字段 | 说明 |
|------|------|
| `supplier_id` | 供应商 |
| `product_line_code` | 产品线 |
| `snapshot_period` | 快照月份（如 `2026-01`） |
| `risk_score` | 综合风险分 |
| `risk_level` | 风险等级 |
| `quality_score` | 质量维度分 |
| `delivery_score` | 交付维度分 |
| `compliance_score` | 合规维度分 |
| `erp_on_time_rate` | ERP 交付准时率 |
| `erp_on_time_rate_source` | 数据来源（`evaluation` / `erp`） |
| `purchase_amount_pct` | 采购金额占比 |
| `delivery_delay_days` | 平均延期天数 |
| `open_scar_count` | 开放 SCAR 数量 |
| `ppm_value` | PPM 值 |
| `dimensions` | 各维度明细（JSONB） |

快照通过唯一约束 `(supplier_id, product_line_code, snapshot_period)` 防止重复（PostgreSQL `NULLS NOT DISTINCT`）。

### 6.3 热力图

热力图是风险地图的核心可视化组件，展示以下列（维度）：

| 列标识 | 类型 | 极性 | 说明 |
|--------|------|------|------|
| `quality_score` | score | `higher_is_risk` | 质量风险分 |
| `delivery_score` | score | `higher_is_risk` | 交付风险分 |
| `compliance_score` | score | `higher_is_risk` | 合规风险分 |
| `risk_score` | risk | `higher_is_risk` | 综合风险分 |
| `ppm_value` | number | `higher_is_risk` | PPM 值 |
| `erp_on_time_rate` | percent | `lower_is_risk` | 交付准时率 |
| `purchase_amount_pct` | percent | `neutral_exposure` | 采购占比 |
| `open_scar_count` | count | `higher_is_risk` | 开放 SCAR 数 |

每个单元格包含：
- `value`：原始值
- `risk_index`：归一化风险指数（0–100）
- `level`：风险等级标签（low/medium/high/critical）
- `diff`：与上一期差值（红色/绿色标识恶化/改善）
- `source`：数据来源标识

### 6.4 时间轴

用户可通过时间轴滑块切换月份查看历史快照。系统自动提供可用月份列表和当前月份标识。

### 6.5 供应商对比

选择多个供应商后可进行横向对比 (Comparison)，展示各供应商在质量、交付、合规等维度的风险指数。

### 6.6 供应商详情

点击热力图中的供应商行，弹出详情面板，展示：

- 当前月各维度的原始值与风险指数
- 近期趋势图（`risk_score`、`quality_score`、`delivery_score`、`compliance_score` 按月变化）
- 数据来源标识（评价数据 vs ERP 实际数据）

### 6.7 快照生成

快照通过 `POST /supply-chain-risk-map/generate` 手动触发，也可通过后台定时任务自动执行。生成时：
1. 遍历所有 `approved` 状态供应商
2. 汇总各数据源（IQC、评价、ERP、SCAR 等）
3. 计算各维度风险分并存储为快照
4. 对比上期数据计算差值 (`diff`)

### 6.8 数据源标识

各指标的数据来源通过 `source` 字段标识：

| 值 | 说明 |
|----|------|
| `evaluation` | 来源于供应商评价数据 |
| `erp` | 来源于 ERP 系统数据 |
| `iqc` | 来源于 IQC 检验数据 |
| `scar` | 来源于 SCAR 记录 |
| `calculated` | 由其他指标计算得出 |

当 ERP 数据不可用时，系统自动回退到供应商评价数据（`erp_on_time_rate_source` 标记为 `evaluation`）。

---

## 7. 常见问题

### 7.1 IQC 相关

**Q: 创建检验批时 AQL 值如何确定？**

A: 系统按以下优先级确定 AQL 值：
1. 用户手动指定 `aql_level` → 直接使用
2. 该供应商+物料的 AQL Profile 的 `current_aql` → 使用 Profile 值（`frozen` 状态也使用 `current_aql`）
3. 物料主数据的 `default_aql` → 使用物料默认值
4. 以上均无 → AQL 相关字段留空

**Q: 详细检验模式和快速检验模式有什么区别？**

A: 快速模式 (`quick`) 直接在检验批上记录总缺陷数和判定结果，适用于简单来料检验。详细模式 (`detailed`) 需要关联检验模板，自动实例化多个检验项，每个检验项可独立录入测量数据，适用于需要逐项记录的关键物料检验。

**Q: 如何发起复检？**

A: 对已判定的检验批（`accepted` 或 `rejected` 状态）可发起复检。系统创建新检验批并标记 `re_inspection = True`、`parent_inspection_id` 指向原检验批。若当前 AQL Profile 为 `normal` 状态，会自动触发加严检验评估。

### 7.2 供应商管理相关

**Q: 供应商评级 A/B/C/D 的标准是什么？**

A: 评级基于加权总分：质量(35%) + 交付(30%) + 服务(15%) = 基础分，再减去各扣分项（CAPA、审核发现、加急运费、客户中断，各项上限10分）。≥72 为 A，≥60 为 B，≥48 为 C，<48 为 D。

**Q: 供应商认证记录如何管理？**

A: 每个供应商可添加多条认证记录，包含认证类型、编号、发证机构、有效期等。认证到期信息会被供应商风险模块的合规维度采集使用。

**Q: 批量导入供应商时有哪些校验规则？**

A: 系统校验：名称和简称为必填；不允许与数据库已有记录重名或简称重复；不允许与同批导入内重复；单次导入上限受 `MAX_IMPORT_ROWS` 限制。导入失败的行会返回错误明细。

### 7.3 供应商风险相关

**Q: 风险规则的优先级如何工作？**

A: 四级覆盖：供应商+产品线 > 供应商全局 > 产品线默认 > 全局默认。系统取最高优先级的配置作为有效规则。例如，为某供应商单独配置的 `ppm_limit = 400` 会覆盖全局默认的 `1000`。

**Q: 什么时候会发送风险通知？**

A: 仅在以下条件下发送通知：
- 告警事件类型为 `new`（新生成）或 `escalated`（风险等级升级）
- 风险等级为 `high` 或 `critical`

`unchanged`（等级不变）或 `low`（低风险）不发送通知。

**Q: 风险告警如何处理？**

A: 告警处理流程：`open`（开放）→ `acknowledged`（已确认）→ `resolved`（已解决）。处理时可记录处理备注 (`handle_note`)，并可关联 SCAR 或 CAPA 记录以便追溯。

### 7.4 供应链风险地图相关

**Q: 热力图中数据来源标识的含义？**

A: 每个单元格的 `source` 字段标明数据来源：
- `evaluation`：来自供应商评价（人工录入评分）
- `erp`：来自 ERP 系统实际数据（如交付准时率）
- `iqc`：来自 IQC 检验数据（如 PPM）
- `scar`：来自 SCAR 记录
- `calculated`：由其他指标计算得出

当 ERP 数据不可用时，交付准时率会回退到供应商评价中的 `delivery_score`，此时 `erp_on_time_rate_source` 标记为 `evaluation`。

**Q: 供应链风险快照如何避免重复？**

A: 数据库对 `(supplier_id, product_line_code, snapshot_period)` 建立了 `UNIQUE NULLS NOT DISTINCT` 约束。当 `product_line_code` 为 NULL 时，NULL 值也被视为相同，确保同一供应商同一月份只有一个全局快照。重新生成同一月份的快照时会覆盖旧数据。

**Q: 采购金额占比 (`purchase_amount_pct`) 如何计算？**

A: 系统从 ERP 数据中获取各供应商在指定时间窗口内的采购金额，计算其占总采购金额的百分比。该指标极性为 `neutral_exposure`（中性暴露），即金额占比本身不代表高风险或低风险，但占比过高意味着对该供应商的依赖度大，需要关注。

**Q: 热力图中颜色编码规则是什么？**

A: 单元格颜色基于 `risk_index`（0-100 的归一化值）和极性：
- `higher_is_risk`：值越高越危险，红色渐变（0=绿，100=红）
- `lower_is_risk`：值越低越危险，反向红色渐变（如交付准时率低=高风险）
- `neutral_exposure`：中性色标识，表示需关注但不直接判为风险

差值 (`diff`) 用红色/绿色三角标识与上期对比的恶化/改善趋势。