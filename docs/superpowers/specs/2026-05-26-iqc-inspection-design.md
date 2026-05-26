# IQC 来料检验模块 — 设计规格

**日期**: 2026-05-26
**阶段**: Phase 2 (供应商/客户质量)
**优先级**: P0
**范围**: 后端 API + 服务层 + 数据库迁移 + 前端页面

---

## 1. 概述

IQC (Incoming Quality Control) 来料检验模块，负责管理供应商来料的抽样检验流程。支持两种检验模式：

- **快速模式**: 直接录入抽样数、缺陷数、判定结果，适合简单物料
- **详细模式**: 基于检验模板逐项检验（外观/尺寸/性能等），适合关键物料

核心能力：AQL 抽样方案自动计算（ISO 2859-1 / GB/T 2828.1）、检验批全生命周期管理、拒收触发 SCAR、供应商绩效自动更新。

---

## 2. 数据模型

### 2.1 已有模型扩展

**`iqc_inspections` 表** — 扩展已有模型，新增字段：

| 新增字段 | 类型 | 说明 |
|----------|------|------|
| `inspection_mode` | String(10) | `"quick"` / `"detailed"` |
| `material_id` | UUID? → iqc_materials | 关联物料 |
| `template_id` | UUID? → iqc_inspection_templates | 关联检验模板 |
| `code_letter` | String(2)? | AQL 抽样代码字 |
| `accept_number` | Integer? | AQL 合格判定数 Ac |
| `reject_number` | Integer? | AQL 不合格判定数 Re |
| `status` | String(20) | `pending`/`inspecting`/`judged`/`closed` |
| `re_inspection` | Boolean | 是否复检（默认 false） |
| `parent_inspection_id` | UUID? → iqc_inspections | 复检时指向原检验单 |
| `product_line_code` | String(20)? | 产品线隔离 |
| `linked_scar_id` | UUID? → supplier_scars | 关联 SCAR 单 |
| `judged_by` | UUID? → users | 判定人 |
| `judged_at` | DateTime? | 判定时间 |

现有字段保留：`inspection_id`, `inspection_no`, `supplier_id`, `part_no`, `part_name`, `lot_no`, `lot_qty`, `sample_qty`, `aql_level`, `inspection_level`, `sampling_standard`, `inspection_result`, `defect_qty`, `defect_description`, `linked_capa_id`, `inspection_date`, `inspected_by`, `created_at`, `updated_at`。

### 2.2 新建表

**`iqc_materials` — 物料主数据**

| 字段 | 类型 | 说明 |
|------|------|------|
| `material_id` | UUID PK | 主键 |
| `part_no` | String(100) UNIQUE | 物料号（内部统一编号） |
| `part_name` | String(200) | 物料名称 |
| `part_spec` | String(200)? | 规格型号 |
| `material_type` | String(20) | 物料类型（raw/component/package/other） |
| `default_aql` | Float? | 默认 AQL 等级（如 1.0, 2.5） |
| `default_inspection_level` | String(10)? | 默认检验水平（如 "II"） |
| `unit` | String(20)? | 单位 |
| `product_line_code` | String(20) | 产品线 |
| `status` | String(20) | active/inactive |
| `created_by` | UUID → users | 创建人 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

> **设计决策：不在此表存储 `supplier_id`。** 物料主数据只维护内部物料属性。
> 制造业中同一物料通常有多个合格供应商（AML/AVL，一物多供），供应商信息通过 `iqc_inspections.supplier_id` 记录每批来料的实际供应商。
> v1 不建 AML 关联表，后续如需按供应商配置免检逻辑再新增 `iqc_material_suppliers` 多对多表。

**`iqc_inspection_templates` — 检验模板**

| 字段 | 类型 | 说明 |
|------|------|------|
| `template_id` | UUID PK | 主键 |
| `template_name` | String(200) | 模板名称 |
| `material_id` | UUID → iqc_materials | 关联物料 |
| `version` | Integer | 版本号（默认 1） |
| `is_active` | Boolean | 是否启用 |
| `created_by` | UUID → users | 创建人 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

**`iqc_template_items` — 模板检验项**

| 字段 | 类型 | 说明 |
|------|------|------|
| `item_id` | UUID PK | 主键 |
| `template_id` | UUID → templates | 关联模板 |
| `sort_order` | Integer | 排序序号 |
| `category` | String(50) | 检验类别（外观/尺寸/性能） |
| `item_name` | String(200) | 检验项名称 |
| `inspection_method` | String(100)? | 检验方法 |
| `inspect_type` | String(20) | `"attribute"` / `"variable"` |
| `spec_upper` | Float? | 规格上限 |
| `spec_lower` | Float? | 规格下限 |
| `target_value` | Float? | 目标值 |
| `unit` | String(20)? | 单位 |
| `sample_size` | Integer? | 抽样数（覆盖 AQL 计算） |
| `aql_level` | Float? | 独立 AQL 等级 |

**`iqc_inspection_items` — 检验项（检验批实例化）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `item_id` | UUID PK | 主键 |
| `inspection_id` | UUID → inspections | 关联检验批 |
| `template_item_id` | UUID? → template_items | 来源模板项 |
| `sort_order` | Integer | 排序序号 |
| `category` | String(50) | 检验类别 |
| `item_name` | String(200) | 检验项名称 |
| `inspect_type` | String(20) | `"attribute"` / `"variable"` |
| `spec_upper` | Float? | 规格上限 |
| `spec_lower` | Float? | 规格下限 |
| `target_value` | Float? | 目标值 |
| `sample_size` | Integer? | 抽样数 |
| `accept_no` | Integer? | 合格判定数 |
| `reject_no` | Integer? | 不合格判定数 |
| `defect_qty` | Integer | 缺陷数（默认 0） |
| `result` | String(10) | `"pending"` / `"ok"` / `"ng"` |
| `remark` | Text? | 备注 |

**`iqc_item_measurements` — 测量值明细**

| 字段 | 类型 | 说明 |
|------|------|------|
| `measurement_id` | UUID PK | 主键 |
| `item_id` | UUID → inspection_items | 关联检验项 |
| `sequence_no` | Integer | 序号 |
| `measured_value` | Float? | 测量值（variable 类型） |
| `attribute_result` | String(10)? | OK/NG（attribute 类型） |
| `remark` | Text? | 备注 |

### 2.3 关系图

```
iqc_materials (1)──(N) iqc_inspection_templates (1)──(N) iqc_template_items
       │
       └──(N) iqc_inspections (1)──(N) iqc_inspection_items (1)──(N) iqc_item_measurements
                      │                parent_inspection_id ──→ iqc_inspections (复检链)
                      ├──(N) suppliers
                      ├──(?) iqc_materials
                      ├──(?) iqc_inspection_templates
                      └──(?) supplier_scars
```

quick 模式：`iqc_inspection_items` 和 `iqc_item_measurements` 为空，结果直接写在 inspection 主表。
detailed 模式：从模板实例化检验项，逐项录入结果。

---

## 3. 状态机

### 3.1 主流程

```
pending → inspecting → judged → closed
```

| 状态 | 中文 | 说明 | 可执行操作 |
|------|------|------|-----------|
| `pending` | 待检验 | 刚创建，等待分配 | 编辑、删除、开始检验 |
| `inspecting` | 检验中 | 检验员录入结果 | 录入结果、提交判定 |
| `judged` | 已判定 | 判定完成 | 让步审批、触发SCAR、申请复检、关闭 |
| `closed` | 已关闭 | 归档 | 仅查看 |

### 3.2 判定结果

`inspection_result` 字段值：

- `accepted` — 接收（defect_qty ≤ accept_number）
- `rejected` — 拒收（defect_qty ≥ reject_number）
- `concession` — 让步接收（拒收后经 manager/admin 特批）
- `pending` — 待判定

### 3.3 可选复检（克隆-关联模式）

judged(rejected) 状态下可申请复检。采用**"克隆并关联"**模式，不回退状态、不覆盖数据：

```
原检验单 IQC-260526-001 (judged/rejected) → 保持不变
    └── 克隆新单 IQC-260526-001-R1 (pending → inspecting → judged → closed)
        parent_inspection_id = IQC-260526-001
```

复检流程：
1. 原检验单状态保持 `judged(rejected)` 不变，所有检验项数据完整保留
2. 系统自动创建新检验单，`inspection_no` 后缀 `-R1`（多次复检递增 `-R2`、`-R3`）
3. `parent_inspection_id` 指向原检验单，`re_inspection=True`
4. 携带原检验批基础信息（供应商、物料、批号、批量、模板）进入新的检验流程
5. 新检验单走完整的 pending → inspecting → judged → closed 流程

优势：
- 完整保留首次检验的结构化数据，支持直通率 (First Pass Yield) 和最终合格率 (Final Yield) 统计
- 溯源链清晰：通过 `parent_inspection_id` 可追溯完整的复检历史
- 不破坏状态机的单向流转

### 3.4 权限矩阵

| 操作 | viewer | engineer | manager | admin |
|------|--------|----------|---------|-------|
| 查看检验单 | ✓ | ✓ | ✓ | ✓ |
| 创建检验单 | — | ✓ | ✓ | ✓ |
| 录入检验结果 | — | ✓ | ✓ | ✓ |
| 判定（提交） | — | ✓ | ✓ | ✓ |
| 让步接收审批 | — | — | ✓ | ✓ |
| 触发 SCAR | — | ✓ | ✓ | ✓ |
| 关闭检验单 | — | — | ✓ | ✓ |
| 删除检验单 | — | — | — | ✓ |

---

## 4. API 端点

### 4.1 物料主数据

基础路径: `/api/iqc/materials`

| Method | Path | 说明 | 权限 |
|--------|------|------|------|
| GET | `/` | 物料列表（分页+搜索） | all |
| POST | `/` | 创建物料 | engineer+ |
| GET | `/{id}` | 物料详情（含模板信息） | all |
| PUT | `/{id}` | 更新物料 | engineer+ |
| DELETE | `/{id}` | 删除物料 | admin |

### 4.2 检验模板

基础路径: `/api/iqc/templates`

| Method | Path | 说明 | 权限 |
|--------|------|------|------|
| GET | `/` | 模板列表（可按物料筛选） | all |
| POST | `/` | 创建模板 + 检验项 | engineer+ |
| GET | `/{id}` | 模板详情（含检验项列表） | all |
| PUT | `/{id}` | 更新模板（新建版本） | engineer+ |
| DELETE | `/{id}` | 删除模板 | admin |

> **约束**: 同一 `material_id` 同一时间只能有一个 `is_active = True` 的模板。创建新版本时自动将旧版本设为 `is_active = False`。

### 4.3 检验单

基础路径: `/api/iqc/inspections`

| Method | Path | 说明 | 权限 |
|--------|------|------|------|
| GET | `/` | 检验单列表（分页+筛选） | all |
| POST | `/` | 创建检验单（AQL 自动计算） | engineer+ |
| GET | `/{id}` | 检验单详情（含检验项/测量值） | all |
| PUT | `/{id}` | 更新基础信息（仅 pending 状态） | engineer+ |
| DELETE | `/{id}` | 删除检验单（仅 pending 状态） | admin |
| POST | `/{id}/start` | 开始检验 pending→inspecting | engineer+ |
| POST | `/{id}/submit-items` | 提交检验项结果（detailed 模式） | engineer+ |
| PUT | `/{id}/items` | 批量更新检验项和测量值 | engineer+ |
| POST | `/{id}/judge` | 判定 inspecting→judged | engineer+ |
| POST | `/{id}/request-reinspect` | 申请复检 judged→re_inspecting | engineer+ |
| POST | `/{id}/rejudge` | 复检判定 | engineer+ |
| POST | `/{id}/concession` | 让步接收审批 | manager+ |
| POST | `/{id}/close` | 关闭 judged→closed | manager+ |
| POST | `/{id}/trigger-scar` | 触发 SCAR | engineer+ |
| POST | `/{id}/import-excel` | Excel 批量导入检验结果 | engineer+ |

### 4.4 辅助端点

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/iqc/calculate-aql` | AQL 抽样方案计算（前端实时预览） |
| GET | `/api/iqc/stats` | IQC 统计概览（看板用） |

### 4.5 AQL 计算集成

**批次级 AQL**：创建检验单时自动调用 `aql_engine.calculate_aql_plan(lot_qty, aql_level, inspection_level)`，将结果写入 `code_letter`、`sample_qty`、`accept_number`、`reject_number`。

**检验项级 AQL**（详细模式）：创建详细模式检验单时，AQL Engine 还需遍历模板中的每一个检验项，根据该项独立的 `aql_level`（若为空则使用批次级默认值）分别计算并写入 `iqc_inspection_items` 的 `sample_size`、`accept_no`、`reject_no`。同一检验批中，关键项可能使用 AQL 0.65（严格），一般项使用 AQL 2.5（宽松），各自的抽样数和判定数不同。

前端创建前可调用 `/calculate-aql` 预览方案。

### 4.6 详细模式判定逻辑

详细模式下批次级判定规则：**任一检验项 NG → 整批拒收**。不是简单累加各检验项的 `defect_qty`，而是按项独立判定后取最严结果。

`iqc_inspections.defect_qty` 记录的是不良品总数（Defective Units），不是缺陷总数（Total Defects）。一个不良品上可能存在多个缺陷，但只计为一个不良品。

### 4.6 列表查询参数

检验单列表支持的筛选参数：
- `status` — 状态筛选
- `inspection_result` — 结果筛选
- `supplier_id` — 供应商筛选
- `material_id` — 物料筛选
- `keyword` — 关键词搜索（检验单号/物料号/批号）
- `date_from` / `date_to` — 日期范围
- `product_line_code` — 产品线筛选
- `page` / `page_size` — 分页

---

## 5. 前端页面

### 5.1 路由

```
/iqc              → IqcInspectionListPage    检验单列表
/iqc/:id          → IqcInspectionDetailPage   检验单详情
/iqc/materials    → IqcMaterialListPage       物料管理
```

### 5.2 检验单列表页 (`IqcInspectionListPage`)

- 顶部：搜索框 + 状态/结果/供应商/日期范围筛选器 + "新建检验单"按钮
- 新建 Modal：选择模式（快速/详细）→ 选择供应商 → 选择物料（自动带入AQL参数和模板）→ 输入批号/批量 → 确认创建
- 表格列：检验单号、供应商、物料号、批号、批量、抽样数、模式、状态、结果、检验日期、操作
- 操作列根据状态动态显示：查看、录入、SCAR、复检、关闭
- Viewer 角色隐藏所有操作按钮

### 5.3 检验详情页 (`IqcInspectionDetailPage`)

**快速模式**：
- 上方：基础信息卡片（检验单号、供应商、物料、批号、状态等）
- 下方：录入区域（抽样数、AQL 计算结果、缺陷数、缺陷描述、判定按钮）

**详细模式**：
- 上方：基础信息卡片
- 中部：检验项表格（每行一个检验项，含类别/名称/类型/规格/抽样数/Ac/Re/测量值录入/缺陷数/结果）
- 计量类型项：点击展开输入测量值明细
- 计数类型项：直接录入缺陷数，自动判定 OK/NG
- 下方：汇总判定区域（根据各项结果自动汇总，高亮显示拒收原因）
- 拒收时显示"触发 SCAR"和"申请复检"按钮

### 5.4 物料管理页 (`IqcMaterialListPage`)

- 表格：物料号、名称、规格、默认 AQL、检验水平、供应商、检验模板数、操作
- 新建/编辑 Modal：物料信息 + AQL 参数配置
- "模板"按钮打开右侧 Drawer：管理检验项（添加/删除/排序），每项配置类别、类型、规格限、抽样数

### 5.5 侧边栏更新

在 AppLayout 侧边栏添加 "来料检验 (IQC)" 菜单组：
- 检验单管理 (`/iqc`)
- 物料管理 (`/iqc/materials`)

---

## 6. 下游联动

### 6.1 拒收 → 触发 SCAR

检验单判定为 rejected 时，工程师可点击"触发 SCAR"：
- 自动创建 `SupplierSCAR` 记录
- `source_type = "iqc"`, `source_id = inspection_id`
- 自动带入：供应商、物料号、批号、缺陷描述
- SCAR 状态默认 `open`
- 更新 inspection 的 `linked_scar_id`

### 6.2 结果 → 供应商绩效

每次检验单关闭时：
- 汇总该供应商本周期内的检验批次数、接收数、拒收数
- 自动计算 PPM 和批次合格率
- 更新 `SupplierEvaluation` 的 `quality_score` 权重
- 数据可供供货质量看板（Phase 2 另一模块）直接查询

### 6.3 结果 → 供货质量看板

IQC 检验结果通过 `/api/iqc/stats` API 输出：
- 总检验批次数、接收率、拒收率
- 按供应商分组的 PPM
- 按物料分组的缺陷分布
- 趋势数据（按月/周）

### 6.4 通知质量工程师

关键事件触发系统通知（预留接口，v1 记录 AuditLog）：
- 检验单创建时通知对应供应商的质量工程师
- 拒收判定时紧急通知
- 让步审批请求通知 manager

---

## 7. Excel 导入

### 7.1 导入格式

支持 Excel (.xlsx) 批量导入检验结果：
- 详细模式：每行一个检验项的测量数据
- 快速模式：每行一个检验批的汇总数据

### 7.2 导入流程

1. 用户上传 Excel 文件
2. 后端解析并校验格式
3. 逐行创建/更新 inspection items 和 measurements
4. 返回导入结果（成功数/失败数/失败原因）

---

## 8. 数据库迁移

需要 1 个新的 Alembic 迁移文件：
- 创建 `iqc_materials` 表
- 创建 `iqc_inspection_templates` 表
- 创建 `iqc_template_items` 表
- 创建 `iqc_inspection_items` 表
- 创建 `iqc_item_measurements` 表
- 为 `iqc_inspections` 表新增字段（inspection_mode, material_id, template_id, code_letter, accept_number, reject_number, status, re_inspection, parent_inspection_id, product_line_code, linked_scar_id, judged_by, judged_at）

新增字段的 `server_default` 要求（兼容存量数据）：
- `status`: `server_default=text("'closed'")` — 历史数据视为已完成
- `inspection_mode`: `server_default=text("'quick'")` — 历史数据无明细项
- `re_inspection`: `server_default=text('false')`
- `inspection_result`: 历史数据保持原值，新增 `server_default=text("'pending'")` 仅对新记录生效

---

## 9. 已有资产（不需要重建）

- `models/iqc_inspection.py` — IqcInspection 模型（需扩展）
- `services/aql_engine.py` — AQL 抽样方案计算引擎（完整，直接使用）
- `schemas/supplier.py` — IqcInspectionCreate/Update/Response schemas（需扩展）
- `frontend/src/types/index.ts` — IqcInspection TypeScript interface（需扩展）

---

## 10. 不在本次范围

- 设备自动采集（留 API 接口，Phase 3+）
- 高级统计报表（供货质量看板独立模块）
- 来料不合格品处理流程（退货/挑选/返工，Phase 2 RMA 模块）
- SCAR → 8D 关联闭环（SCAR 模块已有 8D 关联字段，本模块只负责触发）
