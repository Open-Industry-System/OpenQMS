# 前期策划模块 — 用户手册

> 最后更新: 2026-06-25 | 适用版本: OpenQMS v1.0

---

## 1. 功能概述

前期策划模块覆盖 IATF 16949 产品质量先期策划（APQP）全流程，从风险识别（FMEA）到控制计划、PPAP 提交，再到特殊特性管理，形成完整的产品质量策划闭环：

| 子模块 | 路由 | ModuleKey | 功能范围 |
|--------|------|-----------|----------|
| FMEA | `/fmea`, `/fmea/:id`, `/fmea/pfmea-wizard/:id` | fmea | DFMEA/PFMEA 新建、编辑、审批、归档；PFMEA 七步法生成向导 |
| 控制计划 | `/control-plans`, `/control-plans/:id` | planning | 从 PFMEA 导入、编辑、审批、版本管理 |
| APQP | `/apqp`, `/apqp/:id` | planning | 5 阶段门径管理、交付物关联 |
| PPAP | `/ppap`, `/ppap/:id` | ppap | 18 要素提交、审批、驳回、重新提交 |
| 特殊特性 | `/special-characteristics`, `/special-characteristics/matrix`, `/special-characteristics/traceability`, `/special-characteristics/:id` | special_characteristic | CC/SC 识别、覆盖率矩阵、追溯性视图、FMEA→CP 联动 |

五个子模块通过数据关联实现端到端追溯：FMEA 失效模式识别出特殊特性（CC/SC），控制计划从 PFMEA 导入过程步骤和特性，APQP 项目关联 FMEA、控制计划、PPAP 作为交付物，特殊特性矩阵展示 FMEA→控制计划→MSA 的完整覆盖。

---

## 2. 适用角色与权限

权限模型采用 **ModuleKey × PermissionLevel × 角色** 三级结构。PermissionLevel 含义：0 = NONE（不可见）、1 = VIEW（只读）、2 = CREATE（可新建）、3 = EDIT（可编辑）、4 = APPROVE（可审批/关闭）、5 = ADMIN（完全控制）。

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| fmea | 5 | 4 | 3 | 3 | 1 | 1 | 1 |
| planning | 5 | 4 | 1 | 3 | 1 | 0 | 1 |
| ppap | 5 | 4 | 0 | 3 | 3 | 0 | 1 |
| special_characteristic | 5 | 4 | 0 | 3 | 0 | 0 | 1 |

**关键操作与最低权限对照：**

| 操作 | 模块 | 所需 PermissionLevel |
|------|------|----------------------|
| 查看 FMEA/CP/APQP 列表与详情 | fmea / planning | VIEW (1) |
| 新建 FMEA | fmea | CREATE (2) |
| 编辑 FMEA 图谱 | fmea | EDIT (3) |
| 审批/归档 FMEA | fmea | APPROVE (4) |
| 新建/编辑控制计划 | planning | CREATE (2) / EDIT (3) |
| 审批控制计划 | planning | APPROVE (4) |
| 创建 APQP 项目、提交阶段门径 | planning | CREATE (2) |
| 审批/驳回 APQP 门径 | planning | APPROVE (4) |
| 取消 APQP 项目 | planning | ADMIN (5) |
| 查看 PPAP 提交 | ppap | VIEW (1) |
| 创建/编辑 PPAP 提交 | ppap | CREATE (2) / EDIT (3) |
| 审批/驳回 PPAP | ppap | APPROVE (4) |
| 查看特殊特性 | special_characteristic | VIEW (1) |
| 创建/编辑特殊特性 | special_characteristic | EDIT (3) |
| 安全特性审批 | special_characteristic | APPROVE (4) |

---

## 3. FMEA

### 3.1 核心概念

OpenQMS 采用 AIAG-VDA FMEA 第一版（2019 版）方法论，支持 **DFMEA** 和 **PFMEA** 两种类型，使用图模型（Graph Model）存储失效分析数据。

#### 3.1.1 AIAG-VDA 七步法

| 步骤 | 名称 | 说明 |
|:----:|------|------|
| 1 | 范围定义 (Scope) | 定义分析范围、边界和职责 |
| 2 | 结构分析 (Structure Analysis) | 建立系统结构树 / 过程流程 |
| 3 | 功能分析 (Function Analysis) | 为每个结构元素定义功能 |
| 4 | 失效分析 (Failure Analysis) | 识别失效模式、失效影响和失效原因 |
| 5 | 风险分析 (Risk Analysis) | 评估严重度 S、频度 O、探测度 D |
| 6 | 优化 (Optimization) | 制定预防措施和探测措施 |
| 7 | 结果文档化 (Results Documentation) | 记录结论和改进措施 |

#### 3.1.2 图模型 (Graph Model)

FMEA 数据以 JSONB 图结构存储在 `graph_data` 字段中，格式为 `{ nodes: [...], edges: [...] }`。

**DFMEA 节点链：**
```
System → Subsystem → Component → Function → FailureMode → FailureEffect / FailureCause → Controls
```

**PFMEA 节点链：**
```
ProcessItem → ProcessStep → ProcessWorkElement → ProcessStepFunction / ProcessWorkElementFunction → FailureMode → FailureEffect / FailureCause → Controls
```

**边类型：**

| 边类型 | 含义 |
|--------|------|
| `HAS_PROCESS_STEP` | 过程步骤归属 |
| `FUNCTION_MAPPED_TO` | 功能映射 |
| `HAS_FAILURE_MODE` | 失效模式关联 |
| `EFFECT_OF` | 失效影响 |
| `CAUSE_OF` | 失效原因 |
| `PREVENTED_BY` | 预防措施 |
| `DETECTED_BY` | 探测措施 |
| `OPTIMIZED_BY` | 优化措施 |

前端 `fmeaTable.ts` 负责将图数据与 20+ 列电子表格视图之间的双向转换。

#### 3.1.3 风险评估：RPN 与 AP

系统同时支持两种风险评估指标：

- **RPN（风险顺序数）**：`RPN = S × O × D`，值域 1–1000
- **AP（Action Priority）**：依据 AIAG-VDA 附录 C 的 S×O×D 矩阵，结果为 H（高）、M（中）、L（低）

AP 优先级由后端 `compute_ap()` 函数计算，逻辑严格遵循 AIAG-VDA 手册附录 C1.5。

#### 3.1.4 特殊特性标记

FMEA 节点通过 `classification` 字段标记特殊特性：

- **CC（Critical Characteristic）**：关键特性
- **SC（Special Characteristic）**：重要特性
- 当节点的严重度 (severity) ≥ 9 时，系统自动将该 CC 节点标记为安全相关（`is_safety_suggested = true`）

### 3.2 操作流程

#### 3.2.1 创建 FMEA

1. 进入 FMEA 列表页 `/fmea`，点击「新建」
2. 填写基本信息：
   - **标题**：必填
   - **FMEA 类型**：DFMEA 或 PFMEA
   - **产品线**：默认 `DC-DC-100`
   - **关联 DFMEA**（仅 PFMEA 可选）
3. 系统自动生成文档编号（`PFMEA-2026-XXX` 或 `DFMEA-2026-XXX`）
4. 初始状态为 `draft`

> 也可在创建后通过列表页「进入向导」入口使用七步法生成向导（见 3.2.4）完成建模。

#### 3.2.2 编辑 FMEA 图谱

1. 在 FMEA 列表点击文档编号进入编辑页 `/fmea/:id`
2. 编辑器呈现为 20+ 列的电子表格视图，每行对应一条失效模式链
3. 所有节点操作（增/删/改）保存时提交整个 `graph_data`
4. 系统自动计算 RPN 和 AP

#### 3.2.3 审批与状态流转

FMEA 状态机定义如下：

```
draft ──→ in_review ──→ approved ──→ archived
  │           │             │
  │           ↓             ↓
  │        rework ←────────┘
  │           │
  ↓           ↓
archived    in_review
```

| 当前状态 | 允许的目标状态 | 所需权限 |
|----------|---------------|----------|
| draft | in_review, archived | EDIT (3) |
| in_review | approved, rework | APPROVE (4) 可审批到 approved；EDIT (3) 可打回 rework |
| approved | rework, archived | APPROVE (4) |
| rework | in_review | EDIT (3) |

> **审批限制**：仅 `admin` 和 `manager` 角色可将 FMEA 推进到 `approved` 状态。

#### 3.2.4 七步法生成向导

PFMEA 与 DFMEA 均提供引导式生成向导，将 AIAG-VDA 七步法分解为可逐步完成的交互流程，降低手工建模成本。

**PFMEA 向导**（`/fmea/pfmea-wizard/:id`）：

| 步骤 | 名称 | 内容 |
|:----:|------|------|
| 0 | 范围定义 | 5T 工具/趋势标签 + 时间区间 + 范围边界 |
| 1 | 结构分析 | `PFMEAWizardSidebar` 过程项 / 工序 / 作业元素树；结构树拖拽排序（`@dnd-kit`） |
| 2 | 功能分析 | `FunctionTreeEditor` 三级功能树 + `FUNCTION_MAPPED_TO` 边 + CC/SC 标记 |
| 3 | 失效分析 | 在 ProcessStepFunction 上构建 FE-FM-FC 失效链，4M 语境（人/机/料/法） |
| 4 | 风险分析 | `RiskTable`：severity 取层级 max、CC/SC 只读聚合、O/D 门禁；Step 4 上下文前置 |
| 5 | 优化 | AP=H 的失效模式自动生成推荐措施；PC/DC 创建前置 |
| 6 | 结果文档化 | 确认完成门禁（`usePfmeaWizardValidation`：4M/OP 门禁、3 级严重度、CC/SC 感知） |

向导内置级联删除（`wizardCascadeDelete`），删除共享控制/措施节点时会校验是否被其他行引用。

**DFMEA 向导** 增强：时间区间改用 `DatePicker.RangePicker`；5T 工具/趋势由 AI 推荐（`pfmea_tool` / `pfmea_trend` 触发器 + 4M 规则内容）；Step 3 AI 推荐（`SmartSuggestionDropdown` 接后端触发器）；Step 5 风险分析承载 Step 4 上下文与 PC/DC 创建前置；PC/DC AI 推荐；`ToolStructureGuide` 工具结构引导卡。

> **权限**：向导写入受 `fmea` 模块 `EDIT (3)` 权限约束；列表页仅对 `draft` 状态文档开放「进入向导」入口。

#### 3.2.5 删除 FMEA

仅 `draft` 与 `rework` 状态的 FMEA 文档可删除：

- 列表页（`FMEAListPage`）对上述状态显示删除按钮；其他状态不开放入口
- 后端状态守卫：非 `draft` / `rework` 返回 400「只能删除草稿或返工状态的FMEA」
- 删除前执行 `_null_out_fmea_references`：将 `control_plan`、`capa_eightd` 等关联记录的 FMEA 外键置空，避免外键约束导致的 `IntegrityError` → 500
- 删除操作写入审计日志

> **权限**：删除受 `fmea` 模块 `EDIT (3)` 权限约束；已审批 / 归档文档不可删除，需先退回 `rework`。

### 3.3 版本管理

FMEA 支持版本快照：每次审批通过时自动创建版本记录（`fmea_versions` 表），包含：

- **主版本号 + 次版本号**（如 1.0、1.1）
- **完整图谱快照**（`snapshot` JSONB）
- **SHA-256 哈希**（`sha256_hash`），用于完整性校验
- **变更摘要和类型**（`change_summary`, `change_type`）

**版本快照只读查看器**：编辑器顶部版本历史中可切换查看任一历史版本，进入只读模式（`viewingVersion` 状态，`FMEAVersionSnapshot` 组件），完整还原该版本图谱而不影响当前可编辑态。控制计划编辑器提供对等的 `CPVersionSnapshot` 只读查看器。

### 3.4 FMEA 与控制计划的关联

- 控制计划创建时可选择关联 FMEA（`fmea_ref_id`）
- 通过「从 PFMEA 导入」功能，系统遍历 PFMEA 图谱的 ProcessStep 节点，自动生成控制计划行项
- 导入映射关系：

| PFMEA 图谱节点 | 控制计划字段 |
|---------------|-------------|
| ProcessStep | step_no, process_name |
| ProcessWorkElement | equipment |
| ProcessStepFunction | product_characteristic, specification_tolerance, special_class |
| ProcessWorkElementFunction | process_characteristic |

---

## 4. 控制计划

### 4.1 概述

控制计划（Control Plan）是 APQP Phase 3 的核心交付物，定义产品/过程的控制方法、规格、抽样和反应计划。

### 4.2 数据模型

控制计划由表头（`ControlPlan`）和行项（`ControlPlanItem`）组成：

**表头字段：**

| 字段 | 说明 |
|------|------|
| document_no | 文档编号，格式 `CP-2026-XXX` |
| title | 标题 |
| fmea_ref_id | 关联的 FMEA 文档 |
| source_fmea_version_id | 关联的 FMEA 版本快照 |
| phase | 阶段：`prototype`（样件）、`pre_launch`（试生产）、`production`（量产，默认） |
| part_no / part_name | 零件号/名称 |
| drawing_rev | 图纸版本 |
| org_factory | 责任工厂/组织 |
| core_group | 核心小组 |
| contact_info | 联系方式 |
| customer_requirements | 客户要求（JSONB） |
| status | 状态：`draft` / `approved` |
| version | 版本号 |
| lock_version | 乐观锁版本 |

**行项字段：**

| 字段 | 说明 |
|------|------|
| step_no | 过程编号 |
| process_name | 过程名称 |
| equipment | 设备 |
| product_characteristic | 产品特性 |
| process_characteristic | 过程特性 |
| special_class | 特殊特性分类（CC/SC） |
| specification_tolerance | 规格/公差 |
| evaluation_method | 评价方法 |
| sample_size / sample_frequency | 样本量/频次 |
| control_method | 控制方法 |
| reaction_plan | 反应计划 |
| source_fmea_node_id | 来源 FMEA 节点 ID |
| item_source | 来源标记（`fmea` 或 `manual`） |
| sop_ref | 作业指导书编号 |
| spc_chart_id | 关联 SPC 控制图 |
| gauge_id | 关联量具 |

### 4.3 从 PFMEA 导入

1. 在控制计划详情页，点击「从 PFMEA 导入」
2. 选择 PFMEA 文档和需要导入的过程步骤（`step_nos`）
3. 系统遍历 PFMEA 图谱：
   - ProcessStep → 生成行项的 step_no 和 process_name
   - ProcessWorkElement → 填入 equipment
   - ProcessStepFunction → 填入 product_characteristic、specification_tolerance、special_class
   - ProcessWorkElementFunction → 填入 process_characteristic
4. 导入后自动关联 `fmea_ref_id`，行项标记 `item_source = "fmea"`

> **限制**：仅 PFMEA 类型文档可导入到控制计划；已审批的控制计划不可导入。

### 4.4 审批

控制计划的审批流程：

1. 状态从 `draft` → `approved`
2. 审批时系统自动执行**量具验证**：检查所有关联量具是否激活且在有效校准期内
3. 审批通过后自动创建版本快照（`control_plan_versions` 表）
4. 版本快照包含：
   - 表头快照（`header_snapshot`）
   - 行项快照（`items_snapshot`）
   - SHA-256 哈希（`sha256_hash`）
   - 关联的 FMEA 版本 ID（`source_fmea_version_id`）

> **审批权限**：仅 `admin` 和 `manager` 角色可审批控制计划。

### 4.5 CP 验证引擎

系统内置控制计划验证引擎（`CPValidationEngine`），支持自动和手动触发验证：

- **触发方式**：`manual`（手动）、`auto_on_save`（保存时自动）、`fmea_change`（FMEA 变更触发）
- **验证结果**：每条规则返回 error / warning / info 级别
- **验证记录**：存储在 `cp_validation_runs` 和 `cp_validation_findings` 表

验证运行状态：

| 状态 | 说明 |
|------|------|
| running | 验证进行中 |
| completed | 验证完成 |
| failed | 验证异常 |

---

## 5. APQP

### 5.1 概述

APQP（Advanced Product Quality Planning，产品质量先期策划）是 IATF 16949 标准要求的项目管理框架，用于确保新产品开发过程满足客户要求。

### 5.2 五阶段门径模型

| 阶段 | 名称 | 关键交付物 | 交付物检查 |
|:----:|------|-----------|-----------|
| 1 | 计划与确定项目 (Plan & Define) | 项目计划、目标设定 | 无强制检查 |
| 2 | 产品设计与开发 (Product Design & Development) | DFMEA | 需关联 DFMEA |
| 3 | 过程设计与开发 (Process Design & Development) | PFMEA、控制计划 | 需关联 PFMEA 和控制计划 |
| 4 | 产品与过程确认 (Product & Process Validation) | PPAP | 需关联 PPAP 提交 |
| 5 | 反馈评估与纠正措施 (Feedback & Corrective Action) | 项目总结 | 阶段 5 完成后项目标记为 completed |

> **交付物检查**：门径审批时，系统验证当前阶段是否已关联必要交付物。未满足条件时，审批将被拒绝。

### 5.3 数据模型

**APQPProject 主要字段：**

| 字段 | 说明 |
|------|------|
| project_code | 项目编号，格式 `APQP-2026-XXX` |
| project_name | 项目名称 |
| product_name | 产品名称 |
| product_line_code | 产品线编码 |
| customer_name | 客户名称 |
| target_sop_date | 目标 SOP 日期 |
| team_members | 团队成员（JSONB） |
| current_phase | 当前阶段（1-5） |
| phase_status | 阶段状态：`in_progress` / `pending_approval` / `completed` |
| project_status | 项目状态：`active` / `completed` / `cancelled` |
| dfmea_id / pfmea_id / control_plan_id / ppap_submission_id | 关联交付物 |

### 5.4 门径状态流转

```
in_progress ──submit_gate──→ pending_approval ──approve_gate──→ next phase (in_progress)
                                │
                                ├──reject_gate──→ in_progress
                                │
                                └──(phase 5 approve)──→ completed

任何阶段均可 cancel ──→ cancelled
```

| 动作 | 当前状态要求 | 目标状态 | 所需权限 |
|------|-------------|---------|----------|
| submit_gate | in_progress | pending_approval | CREATE (2) |
| approve_gate | pending_approval | 下一阶段 in_progress 或 completed | APPROVE (4) |
| reject_gate | pending_approval | in_progress | APPROVE (4) |
| cancel | 任意 | cancelled | ADMIN (5) |

### 5.5 门径历史

每个门径动作记录在 `gate_history` JSONB 字段中：

```json
{
  "phase": 2,
  "action": "approve",
  "user_id": "...",
  "user_name": "...",
  "comments": "DFMEA 已完成审批",
  "timestamp": "2026-06-13T08:30:00Z"
}
```

### 5.6 项目生命周期

```
创建项目 (active, phase 1) 
  → 完成阶段 1 → 提交门径 → 审批通过 → 进入阶段 2
    → 关联 DFMEA → 完成阶段 2 → 提交门径 → 审批通过 → 进入阶段 3
      → 关联 PFMEA + 控制计划 → 完成阶段 3 → 提交门径 → 审批通过 → 进入阶段 4
        → 关联 PPAP → 完成阶段 4 → 提交门径 → 审批通过 → 进入阶段 5
          → 完成阶段 5 → 提交门径 → 审批通过 → 项目 completed
```

---

## 6. PPAP

### 6.1 概述

PPAP（Production Part Approval Process，生产件批准程序）是汽车行业供应商向客户证明生产过程能力的标准流程。OpenQMS 实现 PPAP Level 1–5 提交管理，覆盖 AIAG 规定的 18 项提交要素。

### 6.2 PPAP 提交等级

| 等级 | 说明 | 适用场景 |
|:----:|------|---------|
| 1 | 仅提交保证书 (PSW) | 客户指定 |
| 2 | 提交保证书 + 样品 | 客户指定 |
| 3 | 提交保证书 + 样品 + 完整数据 | 新零件首次提交（默认） |
| 4 | 提交保证书 + 完整数据（不送样） | 设计变更 |
| 5 | 不提交，仅保留在制造现场 | 客户书面授权 |

### 6.3 18 项提交要素

| 序号 | 要素名称 | 英文名称 |
|:----:|---------|---------|
| 1 | 设计记录 | Design Records |
| 2 | 工程变更文件 | Authorized Engineering Change Documents |
| 3 | 客户工程批准 | Customer Engineering Approval |
| 4 | 设计 FMEA | Design FMEA |
| 5 | 过程流程图 | Process Flow Diagrams |
| 6 | 过程 FMEA | Process FMEA |
| 7 | 控制计划 | Control Plan |
| 8 | 测量系统分析 | Measurement System Analysis |
| 9 | 尺寸结果 | Dimensional Results |
| 10 | 材料/性能试验结果 | Material / Performance Test Results |
| 11 | 初始过程研究 | Initial Process Studies |
| 12 | 合格实验室文件 | Qualified Laboratory Documentation |
| 13 | 外观批准报告 | Appearance Approval Report |
| 14 | 样件 | Sample Production Parts |
| 15 | 检具 | Checking Aids |
| 16 | 客户特殊要求 | Customer-Specific Requirements |
| 17 | 零件提交保证书 | Part Submission Warrant — PSW |
| 18 | 散装材料要求检查表 | Bulk Material Requirements Checklist |

每项要素包含：`required`（是否必填）、`status`（pending / approved / rejected）、`file_url`（附件）、`notes`（备注）。

### 6.4 PPAP 状态生命周期

```
draft ──submit──→ under_review ──approve──→ approved
                      │
                      └──reject──→ rejected ──resubmit──→ under_review
```

| 动作 | 当前状态 | 目标状态 | 所需权限 | 附加条件 |
|------|---------|---------|----------|---------|
| submit | draft | under_review | CREATE (2) | 自动设置 submission_date |
| approve | under_review | approved | APPROVE (4) | 所有必填要素必须已 approved |
| reject | under_review | rejected | APPROVE (4) | 必须填写驳回原因 |
| resubmit | rejected | under_review | CREATE (2) | revision 自增 +1 |

### 6.5 数据模型

**SupplierPPAPSubmission 主要字段：**

| 字段 | 说明 |
|------|------|
| ppap_no | PPAP 编号，格式 `PPAP-2026-XXX` |
| supplier_id | 供应商 ID |
| part_no / part_name | 零件号/名称 |
| submission_level | 提交等级（1-5） |
| submission_date | 提交日期 |
| status | 状态：draft / under_review / approved / rejected |
| revision | 修订版本号 |
| rejection_reason | 驳回原因 |
| customer_name | 客户名称 |
| product_line_code | 产品线编码 |

> **审批规则**：审批时系统自动检查所有 `required=True` 的要素是否全部 `approved`，未满足时拒绝审批。

---

## 7. 特殊特性

### 7.1 概述

特殊特性管理模块负责识别、分类和追溯 CC（Critical Characteristic，关键特性）和 SC（Special Characteristic，重要特性），确保从 FMEA 到控制计划到 MSA 的完整覆盖。

### 7.2 特殊特性类型

| 类型 | 缩写 | 说明 |
|------|:----:|------|
| 关键特性 | CC | 影响产品安全/法规符合性的特性 |
| 重要特性 | SC | 影响产品功能/质量但非安全相关的特性 |

### 7.3 特殊特性识别方式

1. **从 FMEA 同步**（推荐）：通过「从 FMEA 同步」功能，系统自动扫描 FMEA 图谱中 `classification` 为 CC/SC 的节点，或 `severity ≥ 9` 的节点，生成特殊特性记录
2. **手动创建**：在特殊特性列表页直接创建

#### 7.3.1 FMEA 同步逻辑

系统 `sync_from_fmea` 函数执行以下操作：

1. **扫描 FMEA 图谱**：识别所有 `classification` 为 CC/SC 或 `severity ≥ 9` 的节点
2. **新增**：对图谱中新的 CC/SC 节点，创建 `SpecialCharacteristic` 记录
3. **更新**：对已存在的特性，更新名称和分类
4. **安全建议**：对 `severity ≥ 9` 的 CC 节点，标记 `is_safety_suggested = true`
5. **PFMEA→DFMEA 关联**：PFMEA 来源的特性自动查找同名 DFMEA 特性作为父级（`parent_sc_id`）
6. **降级检测**：如果已标记安全特性的节点严重度从 ≥9 降至 <9：
   - 审批通过的：记录审计日志警告，需人工评估
   - 审批中/已驳回的：记录审计日志，需人工评估
7. **删除保护**：FMEA 中移除的 CC/SC 节点：
   - 普通特性：自动删除
   - 安全相关特性：**拦截自动删除**，记录审计日志，需人工处理

### 7.4 安全特性审批流程

当 `is_safety_suggested = true` 或 `is_safety_related = true` 时，需经过安全审批：

```
pending ──submitted──→ submitted ──approved──→ approved ──(重新评估)──→ pending
                          │
                          └──rejected──→ rejected ──(重新提交)──→ submitted
```

| 状态 | 说明 | 可执行操作 |
|------|------|-----------|
| pending | 待提交 | 提交审批 (submit) |
| submitted | 已提交 | 审批通过 (approve) 或驳回 (reject) |
| approved | 已批准 | 变更后回到 pending 重新评估 |
| rejected | 已驳回 | 重新提交 (submit) |

> **安全特性审批权限**：仅 `admin` 和 `manager` 角色可审批安全特性。

安全特性附加字段：

| 字段 | 说明 |
|------|------|
| is_safety_related | 是否安全特性 |
| is_safety_suggested | 系统是否建议标记为安全特性（severity ≥ 9 的 CC） |
| safety_approval_status | 安全审批状态 |
| safety_regulation_ref | 法规依据 |
| safety_verification_method | 验证方法 |
| safety_approval_comment | 审批意见 |

### 7.5 覆盖率矩阵

覆盖率矩阵页面（`/special-characteristics/matrix`）展示特殊特性在 FMEA、控制计划、MSA 各环节的覆盖情况：

- **行**：每条特殊特性
- **列**：FMEA 节点、控制计划行项、MSA 研究
- **标记**：已覆盖 ✓ / 未覆盖 ✗

覆盖率检查逻辑：
- 特性是否关联了 FMEA 节点（`source_fmea_id` + `source_node_id`）
- 特性是否关联了控制计划行项（`cp_item_id`）
- 特性是否关联了 MSA 研究（`msa_study_id`）及其状态

### 7.6 追溯性视图

追溯性页面（`/special-characteristics/traceability`）提供从 FMEA → 特殊特性 → 控制计划 → MSA 的端到端追溯链：

```
DFMEA 失效模式节点
  └→ 特殊特性 (SC/CC)
      └→ 控制计划行项 (ControlPlanItem)
          └→ MSA 研究 (GRG/Linearity/Stability)
```

追溯性视图支持：
- 按产品线筛选
- 按特性类型（CC/SC）筛选
- 仅查看安全相关特性
- 仅查看待审批的安全特性

### 7.7 特殊特性编码规则

系统自动生成编码，格式：`SC-{年份}-{序号}`，例如 `SC-2026-001`。

### 7.8 FMEA→控制计划联动

特殊特性在 FMEA 和控制计划之间的联动通过以下机制实现：

1. **FMEA 标记**：在 FMEA 编辑器中为节点设置 `classification` 为 CC/SC
2. **同步到特殊特性**：通过「从 FMEA 同步」功能自动创建/更新 `SpecialCharacteristic` 记录
3. **控制计划导入**：通过「从 PFMEA 导入」功能，控制计划行项的 `special_class` 字段自动携带 FMEA 节点的分类标记
4. **手动关联**：可在特殊特性详情页手动关联控制计划行项（`cp_item_id`）

---

## 8. 常见问题

### 8.1 FMEA

**Q: FMEA 审批后被退回修改，版本号会变吗？**

A: 审批通过时自动创建版本快照（如 1.0）。退回到 rework 状态后再提交审批，审批通过时会创建新的版本快照（主版本号不变，次版本号递增）。版本历史可在详情页查看。

**Q: 已审批的 FMEA 可以编辑吗？**

A: 已审批（approved）的 FMEA 不能直接编辑，需要先将状态退回到 rework，编辑完成后再走审批流程。

**Q: DFMEA 和 PFMEA 可以关联吗？**

A: PFMEA 创建时可以选择关联的 DFMEA 文档。此外，特殊特性模块在 PFMEA 同步时会自动查找同名 DFMEA 特性建立父子关系。

**Q: AP 值如何计算？**

A: 系统严格按照 AIAG-VDA FMEA 手册附录 C1.5 的 S×O×D 矩阵计算 Action Priority。S=9-10 时优先级更高，S=1-3 时即使 O 和 D 较高，AP 也不超过 M。具体对照表见 FMEA 编辑器中的 AP 查询功能。

### 8.2 控制计划

**Q: 控制计划只有 draft 和 approved 两个状态吗？**

A: 是的。控制计划当前仅支持 `draft` 和 `approved` 两个状态。审批通过后不可再编辑，如需修改需要创建新版本。

**Q: 从 PFMEA 导入后能手动修改行项吗？**

A: 可以。导入生成的行项标记 `item_source = "fmea"`，但仍然可以手动修改。也可手动添加新行项（`item_source = "manual"`）。

**Q: 审批控制计划时量具验证失败怎么办？**

A: 审批前系统自动检查所有关联量具的状态。如果量具未激活或不在有效校准期内，审批将被拒绝。需要先更新量具校准信息或移除无效量具关联。

**Q: 控制计划版本和 FMEA 版本如何关联？**

A: 控制计划版本快照中包含 `source_fmea_version_id`，指向审批时关联的 FMEA 版本。这确保了控制计划与特定版本的 FMEA 之间的可追溯性。

### 8.3 APQP

**Q: 门径审批时提示"需要关联 DFMEA"怎么办？**

A: 阶段 2 的门径审批要求 `dfmea_id` 不为空。请在项目编辑页面关联一个状态为 approved 的 DFMEA 文档后再提交审批。

**Q: 可以跳过某个阶段吗？**

A: 不可以。APQP 门径模型要求严格按顺序推进：1 → 2 → 3 → 4 → 5。只有当前阶段审批通过后才能进入下一阶段。

**Q: 已取消的 APQP 项目可以恢复吗？**

A: 目前不支持恢复。取消操作（cancel）是最终状态，仅管理员可执行。建议在取消前确认。

**Q: APQP 项目编号格式是什么？**

A: 系统自动生成，格式为 `APQP-2026-XXX`，其中年份取当前年份，序号自增。

### 8.4 PPAP

**Q: PPAP 审批时提示"存在未批准的必填元素"怎么办？**

A: PPAP 审批要求所有 `required=True` 的要素状态为 `approved`。请逐项审查并审批各要素后再提交 PPAP 整体审批。

**Q: 被驳回的 PPAP 可以重新提交吗？**

A: 可以。驳回状态（rejected）的 PPAP 执行 resubmit 操作后回到 under_review 状态，同时 revision（修订版本号）自动 +1。

**Q: 提交等级如何选择？**

A: 提交等级由客户要求决定。Level 3 是最常见的默认等级（新零件首次提交），Level 1 适用于客户仅要求 PSW 的场景，Level 5 适用于客户书面授权不提交的场景。

**Q: PPAP 编号格式是什么？**

A: 系统自动生成，格式为 `PPAP-2026-XXX`。

### 8.5 特殊特性

**Q: severity ≥ 9 的节点标记为安全特性后可以取消吗？**

A: 安全特性（`is_safety_related = true`）不能通过 FMEA 同步自动取消。如果 FMEA 中节点严重度降级（从 ≥9 降至 <9），系统会记录审计日志警告，但不会自动移除安全标记，需人工评估。

**Q: 特殊特性的覆盖率矩阵中"未覆盖"意味着什么？**

A: 表示该特殊特性尚未关联到控制计划行项或 MSA 研究。IATF 16949 要求所有特殊特性必须有对应的控制方法和验证手段，覆盖率矩阵帮助识别缺失环节。

**Q: 从 FMEA 同步会覆盖手动创建的特殊特性吗？**

A: 不会。同步功能只更新从同一 FMEA 节点来源的已有记录，不会覆盖手动创建的记录。如果 FMEA 中某节点被移除，普通特性会被自动删除，但安全相关特性会被保留并记录警告。

**Q: PFMEA 同步的特殊特性为什么会自动关联 DFMEA 特性？**

A: PFMEA 的失效模式往往继承自 DFMEA。同步时系统在 DFMEA 来源的特殊特性中查找同名记录作为父级（`parent_sc_id`），建立 PFMEA→DFMEA 的追溯链，符合 AIAG-VDA 要求的层级追溯性。

---

> **文档路径**：`/docs/modules/planning.md`