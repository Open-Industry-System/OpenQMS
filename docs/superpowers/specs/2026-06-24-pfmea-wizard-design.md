# PFMEA 7 步生成向导设计

> 日期：2026-06-24
> 分支：`fix/fmea-fixes` → `worktree-pfmea-wizard-design`
> 参考：`Reference/FMEA.md` §3.1–3.7（AIAG-VDA PFMEA）、现有 DFMEA 向导实现

## 1. 背景与目标

DFMEA 已有 7 步生成向导（`DFMEAWizardPage.tsx` + `components/dfmea/`）。PFMEA 目前创建后直接进入普通编辑器，缺乏结构化引导。

目标：为 PFMEA 构建镜像 DFMEA 的 7 步生成向导，按 AIAG-VDA 参考文档替换为 PFMEA 实体与术语，复用代码库已有的 PFMEA 实体类型与边类型，以及 DFMEA 向导中已验证的通用组件。

### 已就绪的基础设施

- `FMEADocument` 模型 `fmea_type` 默认 `"PFMEA"`，`graph_data` JSONB 统一存 `{nodes, edges, wizardScope}`。
- PFMEA 节点类型已在 `graphPresentation.ts` / `fmeaTable.ts` 注册：`ProcessItem`、`ProcessStep`、`ProcessWorkElement`、`ProcessItemFunction`、`ProcessStepFunction`、`ProcessWorkElementFunction`、`FailureMode`、`FailureEffect`、`FailureCause`、`PreventionControl`、`DetectionControl`、`RecommendedAction`。
- PFMEA 边类型已注册：`HAS_PROCESS_STEP`、`HAS_WORK_ELEMENT`、`HAS_FUNCTION`、`FUNCTION_MAPPED_TO`、`HAS_FAILURE_MODE`、`EFFECT_OF`、`CAUSE_OF`、`PREVENTED_BY`、`DETECTED_BY`、`OPTIMIZED_BY`。
- 后端 `recommendation_service.py` 的 LLM prompt 已用 `{fmea_type}` 参数化（DFMEA=设计 / PFMEA=过程）。
- `utils/fmea.ts` 的 `calculateAP` 对 DFMEA/PFMEA 通用（AIAG-VDA AP 表共享）。

## 2. 决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| 功能分析深度 | 完整 3 层功能树（过程项/过程步骤/工作要素功能，`FUNCTION_MAPPED_TO` 连接，区分产品特性/过程特性） | 忠实 `FMEA.md` §3.3 |
| 特殊特性列 | 风险分析 Step 4 包含 CC/SC 列 | PFMEA 专有（DFMEA 在 AIAG-VDA 已移除） |
| Step 1 必填字段 | `ProcessStep.process_number`（OP10/OP20）与 `ProcessWorkElement.classification`（4M：人/机/料/法/环）均必填 | 忠实参考，失效原因按 4M 组织 |
| 复用策略 | 新建 `components/pfmea/` 目录，直接复用纯通用组件（SmartSuggestionDropdown、useWizardSave、wizard utils），不改 DFMEA 现有行为 | 规避回归风险 |
| 特殊特性存储 | 新增 `FailureCause.special_characteristic` 字段（无/CC/SC） | 原因节点承载控制与优化，特性标志自然归属 |
| 路由 | 独立 `/fmea/pfmea-wizard/:id` | 与 DFMEA `/fmea/wizard/:id` 并列，互不干扰 |
| Step 1 AI | 纯手工录入（不新增 `process_step` 触发器） | YAGNI；结构与工序号由用户提供 |

## 3. 步骤映射

| 步骤 | 标题 | 收集内容 | 创建的图实体 |
|---|---|---|---|
| 0 | 5T 范围 | 团队/时间/工具/任务/趋势 | `wizardScope` 元数据 |
| 1 | 结构分析 | 过程项 → 过程步骤(OP 号) → 工作要素(4M) | `ProcessItem`、`ProcessStep`、`ProcessWorkElement` + `HAS_PROCESS_STEP`/`HAS_WORK_ELEMENT` |
| 2 | 功能分析 | 3 层功能树 + 产品/过程特性 | `ProcessItemFunction`/`ProcessStepFunction`/`ProcessWorkElementFunction` + `HAS_FUNCTION`/`FUNCTION_MAPPED_TO` |
| 3 | 失效分析 | FM/FE/FC/PC/DC（原因按 4M） | `FailureMode`/`FailureEffect`/`FailureCause`/`PreventionControl`/`DetectionControl` + 失效链边 |
| 4 | 风险分析 | S/O/D + AP + CC/SC | 更新节点评分 + `FailureCause.special_characteristic` |
| 5 | 优化 | RecommendedAction（负责人/截止/状态/措施/S′O′D′AP′） | `RecommendedAction` + `OPTIMIZED_BY` |
| 6 | 结果文档 | 汇总评审 + 完成 | 无（写 `wizard_completed=true`） |

## 4. 架构与文件结构

### 新建文件

```
frontend/src/
├── pages/planning/fmea/PFMEAWizardPage.tsx          # 主页面（镜像 DFMEAWizardPage）
├── components/pfmea/
│   ├── PFMEAWizardSidebar.tsx                       # 侧栏：PFMEA 结构树 + 步骤导航
│   ├── PFMEAGuidanceCard.tsx                        # 引导卡（i18n pfmea.wizard.guidance.step{0-6}）
│   ├── ScopeTagField.tsx                            # PFMEA 版（pfmea_tool/pfmea_trend + 过程工具预设）
│   ├── FunctionTreeEditor.tsx                       # 3 层功能树编辑器（Step 2）
│   └── RiskTable.tsx                                # 风险表（含 CC/SC 列，Step 4）
├── utils/pfmeaRules.ts                              # PFMEA 规则建议（过程动词/4M 失效链）
├── hooks/usePfmeaWizardValidation.ts                # PFMEA 校验
└── locales/{zh-CN,en-US}/pfmea.json                 # i18n
```

### 直接复用（不改、直接 import）

- `components/dfmea/SmartSuggestionDropdown.tsx`（触发器驱动，已支持 prevention/detection_control）
- `hooks/useWizardSave.ts`（完全通用）
- `utils/wizardCascadeDelete.ts`、`wizardStructureOrder.ts`、`wizardTimeframe.ts`、`wizardScopeTokens.ts`、`wizardGraphNormalize.ts`（`createWizardFailureChain`/`ensureCauseControls` 通用）
- `utils/fmea.ts`（`calculateAP` 通用）

**不改动 DFMEA 现有行为。**

## 5. 各步骤图构建与 AI 集成

### Step 0 — 5T 范围
- 写 `wizardScope`（团队/时间/工具/任务/趋势）。
- PFMEA 工具预设：过程流程图、过程参数图、鱼骨图、PFMEA 模板。
- AI 触发器：`pfmea_tool`、`pfmea_trend`（后端新增 prompt 模板）。

### Step 1 — 结构分析
- 构建 `ProcessItem →[HAS_PROCESS_STEP]→ ProcessStep →[HAS_WORK_ELEMENT]→ ProcessWorkElement`。
- `ProcessStep.process_number` 必填（OP10/OP20…），`ProcessWorkElement.classification` 必填（4M：人/机/料/法/环）。
- 结构树用 `orderStructureNodes`（DFS 序）渲染；`wizardCascadeDelete` 处理删除。
- 纯手工录入，不新增 AI 触发器。

### Step 2 — 功能分析（3 层功能树）
- 每层功能节点带 `name` + `requirement` + 特性字段：
  - 过程项功能 / 过程步骤功能：**产品特性**（geometry/material/surface 等可测量产品属性）。
  - 工作要素功能：**过程特性**（压力/温度/速度 等过程控制参数）。
- `FUNCTION_MAPPED_TO` 自动连接 ItemFunc → StepFunc → WorkElementFunc。
- AI 触发器：复用现有（功能建议按 `fmea_type` 分流）。

### Step 3 — 失效分析
- 每个工作要素功能建失效链：`FailureMode →[EFFECT_OF]→ FailureEffect`、`FailureCause →[CAUSE_OF]→ FailureMode`、`FailureCause →[PREVENTED_BY/DETECTED_BY]→ PC/DC`。
- 5 个 `SmartSuggestionDropdown`（FM/FE/FC/PC/DC），原因建议带入工作要素的 4M 分类上下文。
- `createWizardFailureChain` / `ensureCauseControls` 复用。

### Step 4 — 风险分析
- 风险表列：`FE | S | FM | FC | PC | O | DC | D | AP | 特性(CC/SC)`。
- S/O/D 用 `InputNumber`（1–10），AP 自动算（`calculateAP`）。
- O/D 在 PC/DC 为空时禁用（镜像 DFMEA）。
- CC/SC：`Select`（无/CC/SC），存储于 `FailureCause.special_characteristic`。
- 严重度引导按 3 级评估（本厂/下游厂/终端用户）。

### Step 5 — 优化
- AP=H 行建 `RecommendedAction`（`OPTIMIZED_BY`）。
- 字段：`responsible`、`due_date`、`status`（open/undecided/planned/done/notExecuted）、`action_taken`、`completion_date`、revised `S′/O′/D′/AP′`。

### Step 6 — 结果文档
- 汇总卡片（节点/边统计 + 高风险项清单）+ Finish。
- Finish 写 `wizardScope.wizard_completed = true` 并触发状态流转（如适用）。

## 6. 后端

- `recommendation_service.py`：新增 `pfmea_tool`、`pfmea_trend` 触发器的 LLM prompt 模板（PFMEA 上下文为"过程"，预设工具为过程类）。
- 规则引擎：新增 PFMEA 过程动词模式（焊接/装配/注塑/涂装…）与 4M 失效链映射；`failure_mode`/`failure_cause` 触发器内容按 `fmea_type` 分流（DFMEA 设计相关 vs PFMEA 过程相关）。
- `failure_mode`/`failure_effect`/`failure_cause`/`prevention_control`/`detection_control` 触发器已支持 PFMEA（`{fmea_type}` 已在上下文）。
- 现有 FMEA CRUD/lock_version/recommend API 全复用，**无需新端点**。

## 7. 路由与入口

- `App.tsx` 新增路由 `/fmea/pfmea-wizard/:id` → `PFMEAWizardPage`（`ProtectedRoute requiredModule="fmea"`）。
- `FMEAListPage.tsx`：
  - 创建 `fmea_type=PFMEA` 时导航到 `/fmea/pfmea-wizard/{id}`（当前是进普通编辑器 `/fmea/{id}`）。
  - 重开未完成 PFMEA 草稿（status=draft 且 `wizardScope.wizard_completed` 为假）也进向导。

## 8. 校验门禁（`usePfmeaWizardValidation`）

| 检查 | 条件 |
|---|---|
| Step 1 完成 | 存在结构树；所有 `ProcessStep` 有 `process_number`；所有 `ProcessWorkElement` 有 `classification` |
| Step 2 完成 | 所有工作要素有功能；3 层 `FUNCTION_MAPPED_TO` 链完整（ItemFunc→StepFunc→WorkElementFunc） |
| Step 3 完成 | 所有功能有 FM→FE→FC 命名链 + PC/DC |
| Step 4 完成 | 所有行 S/O/D>0、PC/DC 非空 |
| Step 5 完成 | 所有 AP=H 行有 RecommendedAction（负责人 + 截止） |
| Finish 门 | `warnings.length===0 && step1–5 全部完成` |

侧栏 `maxReachableStep` 由 `completedSteps` 派生（镜像 DFMEA，支持保存退出后重开续作）。

## 9. 测试（TDD）

- `PFMEAWizardPage.test.tsx`：步骤导航、保存续作、冲突弹窗、Finish 门禁。
- `usePfmeaWizardValidation` 测试：各步骤完成判定、4M/OP 必填、3 层功能链、CC/SC。
- `pfmeaRules` 测试：过程动词模式、4M 失效链映射。
- `FunctionTreeEditor` / 图规范化测试：3 层功能树构建、`FUNCTION_MAPPED_TO` 连接、产品/过程特性字段。
- `RiskTable` 测试：CC/SC 存取、O/D 禁用门。
- 后端测试：`pfmea_tool`/`pfmea_trend` 触发器返回、PFMEA 规则分流。

## 10. 范围边界（YAGNI）

- 不重构 DFMEA 向导为类型参数化（避免回归）。
- 不新增 `process_step` AI 触发器（Step 1 纯手工）。
- 不实现完整 PFMEA 报告 PDF 导出（Step 6 仅汇总卡片）。
- 不改动普通 PFMEA 编辑器（`FMEAEditorPage`）——向导完成后的编辑沿用现有编辑器。
- 特殊特性不联动控制计划（仅作为风险表标记）。
