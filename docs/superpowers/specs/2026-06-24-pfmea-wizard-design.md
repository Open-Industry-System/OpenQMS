# PFMEA 7 步生成向导设计

> 日期：2026-06-24
> 分支：`fix/fmea-fixes` → `worktree-pfmea-wizard-design`
> 权威数据结构来源：`docs/superpowers/specs/2026-05-20-pfmea-data-structure-design.md`（已评审通过，定义节点/边/字段口径）
> 方法论来源：`Reference/FMEA.md` §3.1–3.7（AIAG-VDA PFMEA 七步法）
> 现有 DFMEA 向导实现：`DFMEAWizardPage.tsx` + `components/dfmea/`

> [!IMPORTANT]
> 本向导**严格遵循** 2026-05-20 已批准的 PFMEA 数据结构文档。该文档已落地实现：
> `severity_plant/customer/user` 已存在于 `backend/app/schemas/fmea.py` 与 `frontend/src/types/index.ts`；
> CC/SC 通过函数节点 `classification` 字段承载（见 `backend/app/seed.py` PFMEA 种子）；
> `HAS_FAILURE_MODE` 挂在 `ProcessStepFunction`。本向导不得违背这些口径。

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
| 功能分析深度 | 完整 3 层功能树（过程项/过程步骤/工作要素功能，`FUNCTION_MAPPED_TO` 连接，区分产品特性/过程特性） | 忠实 `FMEA.md` §3.3 + 2026-05-20 文档 §2.1-B |
| 特殊特性列 | 风险分析 Step 4 包含 CC/SC 列 | PFMEA 专有（DFMEA 在 AIAG-VDA 已移除） |
| Step 1 必填字段 | `ProcessStep.process_number`（OP10/OP20）与 `ProcessWorkElement.classification`（4M：人/机/料/环）均必填 | 忠实 2026-05-20 文档 §2.1-A |
| 复用策略 | 新建 `components/pfmea/` 目录，直接复用纯通用组件（SmartSuggestionDropdown、useWizardSave、wizard utils），不改 DFMEA 现有行为 | 规避回归风险 |
| **失效链挂载层级** | **FM 挂 `ProcessStepFunction`（`HAS_FAILURE_MODE`）**，FC 经 `CAUSE_OF` 指向 FM；FC 的 4M 上下文以该步骤下的工作要素作为录入提示 + AI 上下文，**不新增 FC↔WEF 边** | 对齐 2026-05-20 文档 §2.2 + 现有 `buildRows` 行模型 + 种子数据；不擅自扩展已批准的边集合 |
| **特殊特性存储** | **复用函数节点 `classification` 字段**：CC/SC 设在 `ProcessStepFunction`（产品特性）或 `ProcessWorkElementFunction`（过程特性）上；**不新增 `FailureCause.special_characteristic`** | 对齐 2026-05-20 文档 §2.1-A NOTE + 种子（`seed.py` 行 31-32）；保持特殊特性模块/追溯口径一致 |
| **三段式严重度** | `FailureEffect` 使用 `severity_plant`/`severity_customer`/`severity_user` 三字段（已实现），`severity = max(三者)`；Step 4 提供三字段录入（弹窗或分组列），门禁要求三字段均 >0 | 对齐 2026-05-20 文档 §2.1-C IMPORTANT + 已实现字段；避免退化为单一 S |
| **pfmea_tool/pfmea_trend 触发器** | 新增需同步：后端 `RecommendRequest` 枚举、`_recommend_anchor` 分支、LLM prompt 模板、规则内容、前端 `RecommendRequest` 触发器联合类型、`ScopeTagField` 调用、缓存键、测试 | 不是仅加 prompt；对齐现有 `dfmea_tool/dfmea_trend` 全链路 |
| 路由 | 独立 `/fmea/pfmea-wizard/:id` | 与 DFMEA `/fmea/wizard/:id` 并列，互不干扰 |
| Step 1 AI | 纯手工录入（不新增 `process_step` 触发器） | YAGNI；结构与工序号由用户提供 |

## 3. 步骤映射

| 步骤 | 标题 | 收集内容 | 创建的图实体 |
|---|---|---|---|
| 0 | 5T 范围 | 团队/时间/工具/任务/趋势 | `wizardScope` 元数据 |
| 1 | 结构分析 | 过程项 → 过程步骤(OP 号) → 工作要素(4M) | `ProcessItem`、`ProcessStep`、`ProcessWorkElement` + `HAS_PROCESS_STEP`/`HAS_WORK_ELEMENT` |
| 2 | 功能分析 | 3 层功能树 + 产品/过程特性 | `ProcessItemFunction`/`ProcessStepFunction`/`ProcessWorkElementFunction` + `HAS_FUNCTION`/`FUNCTION_MAPPED_TO` |
| 3 | 失效分析 | FM（挂过程步骤功能）/FE/FC（4M 上下文）/PC/DC | `FailureMode`/`FailureEffect`/`FailureCause`/`PreventionControl`/`DetectionControl` + 失效链边（FM 挂 `ProcessStepFunction`） |
| 4 | 风险分析 | 三段式 S（本厂/客户/终端用户，取最大值）+ O/D + AP + CC/SC | 更新 `FailureEffect` 三严重度字段、`FailureCause.occurrence`、`DetectionControl.detection`；CC/SC 写入函数节点 `classification` |
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
│   ├── FunctionTreeEditor.tsx                       # 3 层功能树编辑器（Step 2），含 CC/SC 维护
│   └── RiskTable.tsx                                # 风险表（特性列只读展示，Step 4）
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

> **前端触发器类型**：`frontend/src/api/recommendation.ts` 的 `RecommendRequest.trigger_type` 联合类型需新增 `"pfmea_tool"` | `"pfmea_trend"`；`components/pfmea/ScopeTagField.tsx` 用这两个触发器调用 `getRecommendations`。`SmartSuggestionDropdown` 的 `triggerType` 联合类型不变（PFMEA 失效链复用现有 failure_* / prevention_control / detection_control）。

## 5. 各步骤图构建与 AI 集成

### Step 0 — 5T 范围
- 写 `wizardScope`（团队/时间/工具/任务/趋势）。
- PFMEA 工具预设：过程流程图、过程参数图、鱼骨图、PFMEA 模板。
- AI 触发器：`pfmea_tool`、`pfmea_trend`（后端新增 prompt 模板）。

### Step 1 — 结构分析
- 构建 `ProcessItem →[HAS_PROCESS_STEP]→ ProcessStep →[HAS_WORK_ELEMENT]→ ProcessWorkElement`。
- `ProcessStep.process_number` 必填（OP10/OP20…），`ProcessWorkElement.classification` 必填（4M：人/机/料/环，即 Man/Machine/Material/Environment）。
- 结构树用 `orderStructureNodes`（DFS 序）渲染；`wizardCascadeDelete` 处理删除。
- 纯手工录入，不新增 AI 触发器。

### Step 2 — 功能分析（3 层功能树）
- 每层功能节点带 `name` + `requirement` + 特性字段：
  - 过程项功能 / 过程步骤功能：**产品特性**（geometry/material/surface 等可测量产品属性）。
  - 工作要素功能：**过程特性**（压力/温度/速度 等过程控制参数）。
- `FUNCTION_MAPPED_TO` 自动连接 ItemFunc → StepFunc → WorkElementFunc。
- **CC/SC 维护**（见 §8）：在 `FunctionTreeEditor` 中为每个函数节点设置 `classification`（无/CC/SC）——CC 设 `ProcessStepFunction`，SC 设 `ProcessWorkElementFunction`。这是 CC/SC 的唯一维护入口。
- AI 触发器：复用现有（功能建议按 `fmea_type` 分流）。

### Step 3 — 失效分析
- **失效链挂在 `ProcessStepFunction` 上**（对齐 2026-05-20 文档 §2.2 + 种子 `seed.py:66`）：
  - `ProcessStepFunction →[HAS_FAILURE_MODE]→ FailureMode →[EFFECT_OF]→ FailureEffect`
  - `FailureCause →[CAUSE_OF]→ FailureMode`
  - `FailureCause →[PREVENTED_BY/DETECTED_BY]→ PreventionControl / DetectionControl`
- 复用 `createWizardFailureChain(processStepFunctionId)`（传入过程步骤功能 ID，而非工作要素功能 ID）与 `ensureCauseControls`。
- **FC 的 4M 上下文**：每个 `ProcessStepFunction` 下的工作要素（`ProcessWorkElement` 的 `classification` = Man/Machine/Material/Environment）作为录入提示展示；`failure_cause` AI 触发器的 context 带入该步骤的工作要素功能描述。**不新增 FC↔WEF 边**（已批准的边集合不含此边；现有 `buildRows` 行模型也不依赖它）。
- 5 个 `SmartSuggestionDropdown`（FM/FE/FC/PC/DC）。

### Step 4 — 风险分析
- **三段式严重度**（对齐 2026-05-20 文档 §2.1-C，字段已实现）：
  - `FailureEffect` 录入 `severity_plant`（本厂）/`severity_customer`（直接客户/下级工厂）/`severity_user`（终端用户），均 1–10。
  - `severity = max(severity_plant, severity_customer, severity_user)`，由前端实时计算并写入 `FailureEffect.severity`（后端/编辑器沿用此口径）。
  - UI：风险表 `FE` 单元格提供「三段评分」弹窗（三个 `InputNumber` + 实时最大值预览），表头列显示综合 `S`。
- 风险表列：`FE(S) | FM | FC | PC | O | DC | D | AP | 特性`。
  - O 存 `FailureCause.occurrence`，D 存 `DetectionControl.detection`，AP 由 `calculateAP(S,O,D)` 计算。
  - O/D 在 PC/DC 为空时禁用（镜像 DFMEA）。
- **特殊特性（CC/SC）**：Step 4 风险表「特性」列**只读**展示该行所属函数节点的 `classification`（CC 展示 `ProcessStepFunction.classification`，SC 沿 `FUNCTION_MAPPED_TO` 展示对应 `ProcessWorkElementFunction.classification`）。**CC/SC 的维护入口在 Step 2 `FunctionTreeEditor`**（见 §8），Step 4 不提供编辑入口。

### Step 5 — 优化
- AP=H 行建 `RecommendedAction`（`OPTIMIZED_BY`）。
- 字段：`responsible`、`due_date`、`status`（open/undecided/planned/done/notExecuted）、`action_taken`、`completion_date`、revised `S′/O′/D′/AP′`。

### Step 6 — 结果文档
- 汇总卡片（节点/边统计 + 高风险项清单）+ Finish。
- Finish 写 `wizardScope.wizard_completed = true` 并触发状态流转（如适用）。

## 6. 后端

### 6.1 新增 `pfmea_tool` / `pfmea_trend` 触发器（全链路，非仅 prompt）
对齐现有 `dfmea_tool`/`dfmea_trend` 的实现路径，逐处补齐：
1. **Schema 枚举**：`backend/app/schemas/recommendation.py` `RecommendRequest.trigger_type` 的 `Literal` 增加 `"pfmea_tool"`、`"pfmea_trend"`。
2. **Anchor 解析**：`backend/app/api/fmea.py` `_recommend_anchor` 将 `("dfmea_tool","dfmea_trend")` 分支扩展为也匹配 `pfmea_tool`/`pfmea_trend`（同样回退 `task`→`fmea_title`→`team`→`input_text`）。
3. **LLM prompt 模板**：`recommendation_service.py` `PROMPT_TEMPLATES` 新增 `pfmea_tool`/`pfmea_trend` 模板（PFMEA 上下文为"过程"，预设工具为过程流程图/过程参数图/鱼骨图/PFMEA 模板）；复用现有 `{fmea_type}` 参数化机制。
4. **规则引擎内容**：PFMEA 过程动词模式（焊接/装配/注塑/涂装…）与 4M 失效链映射；`failure_mode`/`failure_cause` 触发器内容按 `fmea_type` 分流（DFMEA 设计相关 vs PFMEA 过程相关）。
5. **缓存**：缓存键已含 `trigger_type`，无需改键结构；为新触发器补单元测试覆盖命中/未命中。
6. **测试**：`backend/tests` 新增 `pfmea_tool`/`pfmea_trend` 返回结构与 PFMEA 规则分流测试。

> `failure_mode`/`failure_effect`/`failure_cause`/`prevention_control`/`detection_control` 触发器已支持 PFMEA（`{fmea_type}` 已在上下文）。

### 6.2 复用
现有 FMEA CRUD / `lock_version` / recommend API 全复用，**无需新端点**。`create_fmea` 创建 PFMEA 时已自动初始化单个 `ProcessItem` 节点（2026-05-20 文档 §5.1，已实现）。

## 7. 路由与入口

- `App.tsx` 新增路由 `/fmea/pfmea-wizard/:id` → `PFMEAWizardPage`（`ProtectedRoute requiredModule="fmea"`）。
- `FMEAListPage.tsx`：
  - 创建 `fmea_type=PFMEA` 时导航到 `/fmea/pfmea-wizard/{id}`（当前是进普通编辑器 `/fmea/{id}`）。
  - 重开未完成 PFMEA 草稿（status=draft 且 `wizardScope.wizard_completed` 为假）也进向导。

## 8. 特殊特性（CC/SC）模型与归属

**核心决策**：CC/SC **在 Step 2 功能树维护、Step 4 只读展示**，避免「一个 `ProcessStepFunction` 下有多个 `ProcessWorkElementFunction` 时 SC 写入目标不可判定」的问题。

- **归属**（对齐种子 `seed.py:31-32` + 2026-05-20 文档 §2.1-A NOTE）：
  - CC（产品特性）→ `ProcessStepFunction.classification`
  - SC（过程特性）→ `ProcessWorkElementFunction.classification`
- **Step 2（`FunctionTreeEditor`）**：用户在每个函数节点上设置 `classification`（无/CC/SC）。因函数节点是 3 层树中的具体节点，写入目标唯一确定，不存在歧义。
- **Step 4（`RiskTable`）**：风险表「特性」列**只读**展示该行所属函数节点（`functionNodeId`，即 `ProcessStepFunction`）的 `classification`；若是 SC，再沿 `FUNCTION_MAPPED_TO` 展示对应 `ProcessWorkElementFunction.classification`。**Step 4 不提供 CC/SC 编辑入口**，从根源消除「行不知写哪个 WEF」的歧义。
- **不新增边、不新增字段**：复用现有 `classification` 字段与 `FUNCTION_MAPPED_TO` 边。

> 选型理由：审查提出的三种方案（Step 2 维护/Step 4 选 WEF/引入映射边）中，Step 2 维护最契合数据结构口径（CC/SC 本就是函数节点属性，非行属性），且不破坏「不新增 FC↔WEF 边」的约束。

## 9. 普通编辑器兼容性

向导完成后进入普通编辑器 `FMEAEditorPage`。当前编辑器 Class 列读写的是 `FailureMode.classification`（`FMEAEditorPage.tsx:1078/1085`），**与已批准数据结构「CC/SC 设函数节点」口径不一致**，也与向导产出数据不一致（向导把 CC/SC 写在函数节点，`FailureMode.classification` 为空）。

为消除不一致，本特性**附带必要兼容修改**（范围限于 PFMEA 的 Class 列，不动 DFMEA 的 Filter Code 列）：
- PFMEA 模式下（`!isDFMEA`），编辑器 Class 列改为**读函数节点 `classification`**（行的 `functionNodeId`）而非 `FailureMode.classification`；CC/SC 编辑入口下沉到函数节点（编辑器已有结构/功能区，可在该处编辑）或保持只读 + 提示「在向导/结构区维护」。
- 若 `FailureMode.classification` 存在历史值（旧数据），加载时迁移/展示为函数节点 classification（一次性兼容，具体策略在实现计划定）。
- DFMEA 的 Filter Code 列行为不变。

> 此修改是对既有偏离的纠正，使编辑器与向导、种子、已批准文档三者口径统一。实现计划需包含编辑器改动任务与对应回归测试。

## 10. 校验门禁（`usePfmeaWizardValidation`）

| 检查 | 条件 |
|---|---|
| Step 1 完成 | 存在结构树；所有 `ProcessStep` 有 `process_number`；所有 `ProcessWorkElement` 有 `classification`（4M） |
| Step 2 完成 | 所有工作要素有功能；3 层 `FUNCTION_MAPPED_TO` 链完整（ItemFunc→StepFunc→WorkElementFunc） |
| Step 3 完成 | 所有 `ProcessStepFunction` 有命名 FM→FE→FC 链 + PC/DC（FM 挂在过程步骤功能上） |
| Step 4 完成 | 所有行 `severity_plant`/`severity_customer`/`severity_user` 均 >0（`severity` 取最大值）、O/D>0、PC/DC 非空 |
| Step 5 完成 | 所有 AP=H 行有 RecommendedAction（负责人 + 截止） |
| Finish 门 | `warnings.length===0 && step1–5 全部完成` |

侧栏 `maxReachableStep` 由 `completedSteps` 派生（镜像 DFMEA，支持保存退出后重开续作）。

## 11. 测试（TDD）

- `PFMEAWizardPage.test.tsx`：步骤导航、保存续作、冲突弹窗、Finish 门禁。
- `usePfmeaWizardValidation` 测试：各步骤完成判定、4M/OP 必填、3 层功能链、三段式严重度门禁、CC/SC。
- `pfmeaRules` 测试：过程动词模式、4M 失效链映射、PFMEA/DFMEA 规则分流。
- `FunctionTreeEditor` / 图规范化测试：3 层功能树构建、`FUNCTION_MAPPED_TO` 连接、产品/过程特性字段、CC/SC 写入函数节点 `classification`（Step 2 维护）。
- `RiskTable` 测试：三段式严重度录入与 `severity=max`、特性列只读展示（CC/SC 来源函数节点）、O/D 禁用门、失效链挂在 `ProcessStepFunction`。
- 普通编辑器兼容测试（§9）：PFMEA Class 列读函数节点 `classification`、DFMEA Filter Code 不变、历史 `FailureMode.classification` 兼容。
- 后端测试：`pfmea_tool`/`pfmea_trend` 触发器（schema 枚举、anchor、prompt、缓存命中/未命中）、PFMEA 规则分流。

## 12. 范围边界（YAGNI）

- 不重构 DFMEA 向导为类型参数化（避免回归）。
- 不新增 `process_step` AI 触发器（Step 1 纯手工）。
- 不新增 FC↔WEF 边（已批准边集合不含；4M 上下文仅作 UI 提示 + AI context）。
- 不新增 `FailureCause.special_characteristic` 字段（CC/SC 复用函数节点 `classification`，在 Step 2 维护）。
- 不实现完整 PFMEA 报告 PDF 导出（Step 6 仅汇总卡片）。
- 不改动普通 PFMEA 编辑器的非 Class 列；Class 列按 §9 做必要兼容修改，DFMEA Filter Code 列不动。
- 特殊特性不联动控制计划（仅作为函数节点 `classification` 标记，Step 4 只读展示）。
