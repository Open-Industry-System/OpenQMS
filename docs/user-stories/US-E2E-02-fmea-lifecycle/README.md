# Epic US-E2E-02：FMEA 生命周期（AIAG-VDA 七步法创建 + 编辑器编辑 + 审核闭环）

**状态**: 定稿 v3（2026-07-25），经三轮代码评审修订（数据契约/图结构/审批权限/AI 可观测性 + RecommendedAction 数据模型 + AI 契约同步 + 审批门禁 + 审计实体）
**前序版本**: v2（2026-07-25，见 git 历史）、v1（2026-07-25，见 git 历史）
**方法论来源**: `Reference/FMEA.md`（AIAG-VDA *FMEA手册* 第五版）§2(DFMEA)/§3(PFMEA) 七步法
**关联**: 现有向导 `frontend/src/pages/planning/fmea/{DFMEA,PFMEA}WizardPage.tsx`；编辑器 `FMEAEditorPage.tsx`；审批 `POST /api/fmea/{id}/transition`
**前序 epic**: US-E2E-01-capa-8d-closed-loop（8D 侧已建 FMEA 关联；本 epic 从 FMEA 侧验收创建→编辑→审批全生命周期）
**派生 verify skill**: `.claude/skills/verify-fmea-lifecycle/`（总 skill，**待生成**）+ 19 子 skill（每子故事一个，**待生成**）

## 故事

**作为** 前期策划质量工程师(PFMEA) / 设计质量工程师(DFMEA)，**我想** 按 AIAG-VDA 七步法创建 FMEA——
Step1 策划准备(5T 范围 + AI 工具/趋势推荐)、
Step2 结构分析(结构树)、
Step3 功能分析(功能树 + 产品/过程特性)、
Step4 失效分析(FM/FE/FC + PC/DC + AI 全知识库推荐)、
Step5 风险分析(三段式 S(PFMEA)/单 S(DFMEA) + O/D + AP + CC/SC)、
Step6 优化(RecommendedAction + AI 推荐措施)、
Step7 结果文件化(汇总评审 + 完成 + 跳转编辑器)——
在编辑器内继续编辑（增删行/多效应/多原因/失效链、行级 AI 推荐、多人协同 + 冲突检测、版本快照 + CP 联动），
最后提交评审、由 manager 审批通过（或驳回返工），
且每步 AI 推荐前**查询全部知识库**（其他 FMEA 图 + RAG 语义 + 经验教训 + 产品结构）再生成回答，
**以便** FMEA 严格遵循 AIAG-VDA 方法论、失效链可追溯、AI 推荐有据可依、跨 FMEA 知识可复用、协同编辑不冲突、审批闭环可审计、FMEA→控制计划变更可联动。

> **角色说明**：PFMEA 由 `planning_qe`（前期策划质量工程师）主导；DFMEA 由 `planning_qe`/设计质量工程师主导（沿用现有 RBAC，不新增角色）。审批（IN_REVIEW→APPROVED）需 `canApprove('fmea')` 权限（当前由 `manager` 账号代表；若需拆"设计负责人"为独立 RBAC 角色，另立改造）。

## 状态机（FMEAState，5 态）

| 状态 | 含义 | 推进动作 | 责任子故事 |
|---|---|---|---|
| DRAFT | 向导进行中 / 草稿 / 编辑器编辑中 | 创建 → 进入向导；Step7 完成 → 编辑器 | 02.1–02.14（向导）+ 02.15–02.18（编辑器） |
| IN_REVIEW | 已提交评审 | DRAFT/REWORK → 提交 | 02.19 |
| APPROVED | 已批准 | manager 审批 | 02.19 |
| REWORK | 驳回返工 | IN_REVIEW → REWORK（驳回）/ APPROVED → REWORK | 02.19 |
| ARCHIVED | 归档 | — | 不在本 epic |

- **向导内流转**：Step1→Step2→…→Step7 全在 DRAFT，不触发状态机；Step7 完成 → 可进入编辑器（仍 DRAFT）继续编辑。
- **可编辑状态**：仅 DRAFT、REWORK 可修改图（编辑器 PUT）；IN_REVIEW、APPROVED、ARCHIVED 的 PUT 必须拒绝（见 02.19 权限矩阵）。
- **提交评审**：编辑器内"提交评审"按钮 → DRAFT/REWORK → IN_REVIEW（02.19），生成版本快照。
- **审批通过**：manager 审批 → IN_REVIEW → APPROVED（02.19），生成版本快照 + 触发 CP 同步（02.18）。
- **驳回返工**：manager 驳回 → IN_REVIEW → REWORK（02.19，必须携带非空 reason）；REWORK → IN_REVIEW 可重提。
- **草稿恢复**：列表中 DRAFT 的 FMEA 显示"草稿"标签，点击重新进入向导（DFMEA）或编辑器（PFMEA/有内容的 DFMEA）；非 DRAFT 跳编辑器或详情。

## 审批权限矩阵（后端契约）

| 流转 | 权限 | 说明 |
|---|---|---|
| DRAFT/REWORK → IN_REVIEW | EDIT | 提交评审；**后端强制校验** `wizardScope.wizard_completed=true`（前端仅用于提前提示，可绕过 API 调用） |
| IN_REVIEW → APPROVED | APPROVE | 审批通过；置 approved_by/at + 生成 approve 快照 + 触发 CP sync（仅 PFMEA 关联时） |
| IN_REVIEW → REWORK | APPROVE | 驳回；必须携带非空 reason |
| REWORK → IN_REVIEW | EDIT | 重提；后端同样强制校验 wizard_completed |
| APPROVED → REWORK | APPROVE | 已批准后返工 |
| 不可跳步 | — | DRAFT 不可直接 APPROVED（**状态机已阻止**，`fmea_state.py:18`） |
| 可编辑图 | EDIT | 仅 DRAFT、REWORK；IN_REVIEW/APPROVED/ARCHIVED 的 PUT 必须拒绝 |

- **状态机支持情况**：APPROVED→REWORK **已支持**（`fmea_state.py:20` `APPROVED: [REWORK, ARCHIVED]`）；DRAFT→APPROVED **已阻止**（`fmea_state.py:18` `DRAFT: [IN_REVIEW, ARCHIVED]`）。
- **真正缺的实现缺口**：① 权限校验（`require_approve_permission` 仅对 `target_status=="approved"` 检查 APPROVE，见 `api/fmea.py:192`；IN_REVIEW→REWORK / APPROVED→REWORK / REWORK→IN_REVIEW 未检查权限）；② 非空 reason 校验（驳回时）；③ 可编辑状态门禁（IN_REVIEW/APPROVED 拒绝 PUT）；④ wizard_completed 后端强制校验（提交/重提时）。
- **wizard_completed 门禁契约**：后端在 `DRAFT/REWORK→IN_REVIEW` 时强制校验 `wizardScope.wizard_completed=true`；缺失或 false 返回 **422 Unprocessable Entity**（带明确 detail，如 "向导未完成，不能提交评审"）；E2E 直接调用 `POST /api/fmea/{id}/transition` 验证无法绕过前端。
- **APPROVED→REWORK 后**：approved_by/approved_at **保留历史**（不清空），便于追溯。

## 图结构契约（共享边词汇，跨 PFMEA/DFMEA）

PFMEA 与 DFMEA 共享同一边词汇与 Process*Function 类型（`frontend/src/utils/structureTree.ts` / `fmeaTable.ts`）；DFMEA 的 System/Subsystem/Component 仅为**语义/UI 名称**（`graphPresentation.ts:239-240` 将 HAS_PROCESS_STEP 映射为 hasSubsystem，HAS_WORK_ELEMENT 映射为 hasComponent），**不新增 HAS_SUBSYSTEM/HAS_COMPONENT 边**。

**结构层边**：
```
ProcessItem/System ─HAS_PROCESS_STEP→ ProcessStep/Subsystem ─HAS_WORK_ELEMENT→ ProcessWorkElement/Component
<any structure node> ─HAS_FUNCTION→ <layer-mapped function node>
```

**失效链边**（方向，以现有 `buildRows` 为准）：
```
<Function node> ─HAS_FAILURE_MODE→ FailureMode
FailureMode      ─EFFECT_OF→ FailureEffect
FailureCause     ─CAUSE_OF→ FailureMode
FailureCause     ─PREVENTED_BY→ PreventionControl
FailureCause/FailureMode ─DETECTED_BY→ DetectionControl
FailureCause/FailureMode ─OPTIMIZED_BY→ RecommendedAction
```

**功能层边**：
```
<structure node> ─HAS_FUNCTION→ <function node>          # 结构节点 → 功能节点
<function node> ─FUNCTION_MAPPED_TO→ <function node>      # 不同层级功能之间的功能关系（非功能→结构）
```

**节点类型**：
- PFMEA 结构：`ProcessItem` / `ProcessStep`(process_number=OP10/OP20 必填) / `ProcessWorkElement`(classification=4M: Man/Machine/Material/Environment，中文仅为 UI 标签)。
- DFMEA 结构：`System` / `Subsystem` / `Component`（语义/UI 名称；System/Subsystem/Component 本身可作为功能行头）。
- 功能：`ProcessItemFunction`/`ProcessStepFunction`/`ProcessWorkElementFunction`（PFMEA + DFMEA 共用；DFMEA 无独立 SystemFunction 类型，注释见 `schemas/fmea.py:6-9`）。
- 失效链：`FailureMode` / `FailureEffect` / `FailureCause` / `PreventionControl` / `DetectionControl` / `RecommendedAction`。

## 编辑器行模型（`fmeaTable.buildRows`，稳定契约）

- **一行对应一个 FM×FC**（FailureMode × FailureCause）；无 cause 时单行 placeholder（key 后缀 `_null`）。
- **多效应是 FM 级共享列表**（`failureEffectNodeIds: string[]`，`EFFECT_OF` from the mode），跨该 FM 的所有 cause 行共享。
- **多效应在同一单元格内编辑，不增加行数**（非 cause × effect 笛卡尔积）。
- **合并列**：`computeRowSpans` 按 function/mode 分组合并单元格；效应/严重度/CC 列按 failureModeNodeId 分组。

## AI 推荐知识库查询契约（AI_REQUIRED=true 的子故事）

**响应契约**（需在 `RecommendResponse` 增加 `source_executions[]` + `context_execution` + `generation_execution`）：
```json
{
  "suggestions": [...],
  "source_executions": [
    {"source": "graph", "status": "success", "hit_count": 3, "latency_ms": 12},
    {"source": "semantic_search", "status": "empty", "hit_count": 0, "latency_ms": 45},
    {"source": "lessons_learned", "status": "success", "hit_count": 2, "latency_ms": 23}
  ],
  "context_execution": {"current_product_structure": "assembled"},
  "generation_execution": {"llm": "success"}
}
```

- **`required_retrievers`**（外部检索，必须出现在 `source_executions`）：`graph` / `semantic_search` / `lessons_learned`。
- **`context_execution`**（内部组装，不计入 `source_executions`）：`current_product_structure`（assembled | unavailable）——`process_step`/`function_description` 是 `_assemble_context` 的产物，作为 LLM prompt 输入，非外部检索命中。
- **`generation_execution`**：`llm`（success | unavailable | error）。
- **`rule` 不计入 required_retrievers**：`rule` 是本地规则表（同步，~1ms），非外部检索；`rule` 可出现在 `source_executions` 作为附加诊断，但不作为"必查"验收项。
- **`status` 枚举**：`success | empty | unavailable | error`。
- **"必查"定义**：`required_retrievers` 的 3 个适配器必须被调用，允许合法零命中（`status=empty`）；`unavailable`（无 embedding 凭证）与 `error`（调用失败）需明确运行时行为——**本 spec 定为带诊断降级**（返回 200 + `source_executions` 标注 unavailable/error，不整体失败）。
- **E2E 健康环境断言**：在健康 E2E 环境（有 embedding 凭证 + LLM 凭证）中，`graph`/`semantic_search`/`lessons_learned` 必须为 `success | empty`；`unavailable | error` 虽可在生产运行时降级返回 200，但 **E2E 应判 FAILED**（防止"适配器永远 unavailable"也通过验收）。
- **零命中 vs 未调用可区分**：`empty`（调用了但无结果）≠ `unavailable`（未调用）—— `source_executions` 是 E2E 区分二者的依据。
- **source_document_no**：仅对具有来源文档的候选必填——`graph` / `semantic_search` / `lessons_learned`（若 lessons 候选有来源 CAPA/审核文档）；`rule`/`llm` 不强制。

**3 来源 + 上下文组装 + 生成**（后端查询顺序）：

| # | 来源 | 实现 | `source_executions` |
|---|---|---|---|
| 1 | 其他 FMEA 图节点 | `find_similar_nodes_advanced` | `graph` |
| 2 | RAG 语义搜索 | `document_embeddings` pgvector（`SemanticSearchSource`） | `semantic_search` |
| 3 | 经验教训库 | `LessonsLearnedService` | `lessons_learned` |
| — | 当前产品结构 | `_assemble_context` | （`context_execution.current_product_structure`，不计入） |

- **缺口处理**：现状 `RecommendationService` 仅接 #1(keyword)+上下文组装+LLM，**#2/#3 未接入** → 相关子故事验收标 `FAILED`（驱动补齐）。

## AI 采纳审计契约（ADOPT_RECOMMENDATION）

当前无"下拉采纳 vs 手工输入"的区分 API。本子故事（02.4/02.16 等 AI_REQUIRED=true）验收以下契约：

- **采纳 payload 位置**：`FMEAUpdate.adoptions: list[RecommendationAdoption]`（**独立于 graph_data**，不混入节点字段）。
- **`RecommendationAdoption` schema**：
  ```json
  {
    "field_id": "fm_node_123",
    "recommendation_id": "rec_abc456",
    "source": "graph",
    "stage_index": 2,
    "adopted_text": "焊接电流不足"
  }
  ```
- **幂等性**：`recommendation_id` 幂等——重复保存相同 `recommendation_id` 不得重复写审计（后端按 `recommendation_id` 去重）。
- **后端审计**：保存时解析 `adoptions`，写 `ADOPT_RECOMMENDATION` AuditLog（`action="ADOPT_RECOMMENDATION"`，changed_fields 含 field_id/recommendation_id/source/stage_index/adopted_text）。
- **区分采纳 vs 手工**：有 `adoptions` 条目 → `ADOPT_RECOMMENDATION`；无 → 普通 `UPDATE`。
- **当前实现缺口**：`RecommendationService` 返回的 `SuggestionItem` 无 `recommendation_id`；`FMEAUpdate` 无 `adoptions` 字段。本子故事验收此契约为 `FAILED`（驱动补齐）。

## AuditLog 与 Outbox 事件分离

- **AuditLog `action`**（枚举）：`CREATE` / `UPDATE` / `DELETE` / `TRANSITION` / `FORCE_SAVE_OVERRIDE` / `ADOPT_RECOMMENDATION`（新增）。
- **Outbox `event_type`**（字符串）：`fmea.created` / `fmea.updated` / `fmea.deleted` / `fmea.approved` / `fmea.submitted` / `fmea.rejected` / `fmea.version_created` / `cp.sync_pending_set`。
- 本子故事（02.15/02.18/02.19）验收 AuditLog `action` 与 Outbox `event_type` 分离，不混用。

## 子故事索引

### A. 创建向导（按类型 × 七步，14 子故事）

| 编号 | 子故事 | AIAG-VDA | AI_REQUIRED | 文件 |
|---|---|---|---|---|
| 02.1 | PFMEA Step1 策划准备(5T) | §3.1 | true | `US-E2E-02.1-pfmea-step1-planning.md` |
| 02.2 | PFMEA Step2 结构分析 | §3.2 | false | `US-E2E-02.2-pfmea-step2-structure.md` |
| 02.3 | PFMEA Step3 功能分析 | §3.3 | false | `US-E2E-02.3-pfmea-step3-function.md` |
| 02.4 | PFMEA Step4 失效分析 | §3.4 | true | `US-E2E-02.4-pfmea-step4-failure.md` |
| 02.5 | PFMEA Step5 风险分析 | §3.5 | true | `US-E2E-02.5-pfmea-step5-risk.md` |
| 02.6 | PFMEA Step6 优化 | §3.6 | true | `US-E2E-02.6-pfmea-step6-optimization.md` |
| 02.7 | PFMEA Step7 结果文件化 | §3.7 | false | `US-E2E-02.7-pfmea-step7-documentation.md` |
| 02.8 | DFMEA Step1 策划准备(5T) | §2.1 | true | `US-E2E-02.8-dfmea-step1-planning.md` |
| 02.9 | DFMEA Step2 结构分析 | §2.2 | false | `US-E2E-02.9-dfmea-step2-structure.md` |
| 02.10 | DFMEA Step3 功能分析 | §2.3 | false | `US-E2E-02.10-dfmea-step3-function.md` |
| 02.11 | DFMEA Step4 失效分析 | §2.4 | true | `US-E2E-02.11-dfmea-step4-failure.md` |
| 02.12 | DFMEA Step5 风险分析 | §2.5 | true | `US-E2E-02.12-dfmea-step5-risk.md` |
| 02.13 | DFMEA Step6 优化 | §2.6 | true | `US-E2E-02.13-dfmea-step6-optimization.md` |
| 02.14 | DFMEA Step7 结果文件化 | §2.7 | false | `US-E2E-02.14-dfmea-step7-documentation.md` |

### B. 编辑器与审核闭环（跨类型能力，5 子故事）

| 编号 | 子故事 | AI_REQUIRED | 文件 |
|---|---|---|---|
| 02.15 | 编辑器行级 CRUD + 图同步 | false | `US-E2E-02.15-editor-row-crud.md` |
| 02.16 | 编辑器内 AI 推荐（全知识库查询） | true | `US-E2E-02.16-editor-ai-recommend.md` |
| 02.17 | 协同编辑 + 冲突检测 | false | `US-E2E-02.17-collaborative-editing.md` |
| 02.18 | 版本快照 + CP 联动 | false | `US-E2E-02.18-version-snapshot-cp-sync.md` |
| 02.19 | 审核闭环（提交+审批+驳回） | false | `US-E2E-02.19-approval-cycle.md` |

> **AI_REQUIRED**：true = 该子故事有 AI 步骤，无 LLM 凭证时验收为 `BLOCKED`（环境缺失，不可降级）；false = 该子故事无 AI 步骤，但功能错误时为 `FAILED`。

## 交付顺序与依赖

**交付顺序**（建议的实施顺序，遵循 FMEA 生命周期业务流程）：

```
向导创建（02.1→02.7 / 02.8→02.14）→ 编辑器编辑（02.15→02.18）→ 审核闭环（02.19）
PFMEA 与 DFMEA 向导可并行；编辑器/审批跨类型共用
```

**前置依赖**（硬约束）：

```
02.{N} → 02.{N-1}（同类型向导内，Step N 依赖 Step N-1 结构/功能/失效链数据）
02.7/02.14 → 02.1-02.6 / 02.8-02.13（结果文件化需前 6 步数据就绪）
02.15 → 02.7 或 02.14（编辑器需向导已完成或已有 draft FMEA）
02.16 → 02.15（AI 推荐依附编辑器行）
02.17 → 02.15（协同编辑依附编辑器）
02.18 → 02.15（版本快照依附编辑器保存）
02.19 → 02.7 或 02.14（提交评审需向导完成）
PFMEA 向导与 DFMEA 向导互不前置（可并行）
```

> 交付顺序 ≠ 前置依赖。交付顺序按生命周期编排（便于走查与增量交付）；前置依赖是硬约束。

## FMEA 生命周期执行顺序

```
创建 draft → 向导 Step1-7（02.1-02.14）→ 编辑器编辑（02.15-02.18）→ 提交评审 IN_REVIEW（02.19）→ manager 审批 → APPROVED（02.19，触发 02.18 CP 同步）/ 驳回 REWORK（02.19，返工回编辑器）
```

## 验收骨架（epic 级）

epic 级验收 = 各子故事验收的**合取**（全部子故事通过，epic 方为通过）。

- **状态机**：FMEA 按 DRAFT(向导/编辑器)→IN_REVIEW→APPROVED/REWORK 顺序流转，向导内 Step1-7 不可跳步；仅 DRAFT/REWORK 可编辑图。
- **权限矩阵**：见"审批权限矩阵"节；IN_REVIEW/APPROVED/ARCHIVED 的 PUT 必须拒绝。
- **AIAG-VDA 忠实度**：每步创建的节点/边类型与 `Reference/FMEA.md` §X.Y 定义一致（PFMEA=§3.x，DFMEA=§2.x），但**边词汇统一为共享 Process* 边**（DFMEA 语义名称由 `graphPresentation.ts` 映射）。
- **AI 流程可视化与执行验证**（强制 LLM 凭证，AI_REQUIRED=true 的子故事：02.1/02.4/02.5/02.6/02.8/02.11/02.12/02.13/02.16）：响应含 `source_executions[]`（3 required_retrievers: graph/semantic_search/lessons_learned）+ `context_execution.current_product_structure` + `generation_execution.llm`；3 required_retrievers 必须查询（允许 empty），缺任一或健康环境下为 unavailable/error → `FAILED`；无 LLM 凭证 → `BLOCKED`。
- **审计轨迹**：AuditLog `action` 与 Outbox `event_type` 分离（见"AuditLog 与 Outbox 事件分离"节）；AI 采纳写 `ADOPT_RECOMMENDATION`（含采纳元数据）。
- **数据落库**：节点/边/wizardScope/wizard_completed（在 wizardScope 内）/lock_version/version snapshot（`FMEAVersion.snapshot`）持久化正确；编辑器保存保留向导元数据（不覆盖 wizardScope）；CP 同步状态 `sync_pending` 在 FMEA approved（仅 PFMEA 关联时）置 true。

## 不在本 epic 范围

- FMEA-MSR（§4，监视及系统响应补充 FMEA，未实现，另立 epic）。
- FMEA 归档（ARCHIVED）与重审（APPROVED→REWORK 后的二次审批深度，另立）。
- AI 推荐的准确率/排序质量评测（另立，需标注数据集）。
- 「设计负责人」作为独立 RBAC 角色的系统改造（另立；当前用 `manager` 账号代表审批方）。
- FMEA ↔ 8D/SCAR/供应商 双向追溯（已由 01.4-01.6 验收，本 epic 只验 FMEA 侧生命周期）。
- FMEA 列表筛选/导出（现有功能，不在本 epic 验收）。
- 全图 schema migration（若需将 DFMEA 边改为 HAS_SUBSYSTEM/HAS_COMPONENT，另立改造；本 epic 保持共享 Process* 边）。

## 维护

- 任一子故事版本/日期变更，对应 `verify-fmea-lifecycle-{name}` 子 skill 须重新核对同步（更新顶部版本声明）。
- README 版本变更，总 skill `verify-fmea-lifecycle` 须重新核对同步。
- 子故事可独立迭代，无需 bumping epic 版本；仅当 epic 验收骨架、状态机、依赖关系或生命周期顺序变更时才 bumping README 版本。

## 评审决议（v3，已定）

- **范围**：本 epic 覆盖 PFMEA + DFMEA（不含 FMEA-MSR）；生命周期 = 创建向导 + 编辑器编辑 + 审核闭环。
- **子故事粒度**：向导按"类型 × 七步"拆 14 子故事（每文件单一业务结果 = AIAG-VDA 一步一类）；编辑器/审批跨类型通用，拆 5 子故事（不按类型重复，避免冗余）。
- **AI 知识库查询契约**：AI_REQUIRED=true 的子故事，验收要求推荐前查询 3 个 required_retrievers（其他 FMEA 图 graph + RAG 语义 semantic_search + 经验教训 lessons_learned），通过 `source_executions[]` 可观测（empty 允许，unavailable/error 带诊断降级）；`context_execution.current_product_structure` 组装产品结构（不计入 source_executions），`generation_execution.llm` 生成。现状 `RecommendationService` 仅接图(keyword)+context+LLM，**RAG 语义搜索(#2)与经验教训库(#3)未接入**——本 epic 验收将此标为 `FAILED`，驱动补齐接入。
- **AI 采纳审计**：保存 payload 携带采纳元数据，后端写 `ADOPT_RECOMMENDATION`（当前无此 API，验收为 `FAILED` 驱动补齐）。
- **AI_REQUIRED 分布**：向导 Step1/4/5/6 + 编辑器 AI 推荐 = true（9 个）；向导 Step2/3/7 + 编辑器 CRUD/协同/版本/审批 = false（10 个）。
- **审批角色**：当前用 `manager` 账号代表审批方；「设计负责人」独立角色改造另立。
- **图结构**：共享 Process* 边词汇；DFMEA System/Subsystem/Component 为语义/UI 名称（`graphPresentation.ts` 映射）；不新增 HAS_SUBSYSTEM/HAS_COMPONENT 边（除非另立 schema migration）。
- **编辑器行模型**：一行 = FM×FC；多效应为 FM 级共享列表（非笛卡尔积）。
- **字段契约**：wizardScope.{team,timeframe,tool,task,trend}；wizard_completed 在 wizardScope 内；FMEAVersion.{major_no,minor_no,snapshot,sha256_hash,change_type}；RecommendedAction 现有字段（name/responsible/due_date/status/action_taken/completion_date/revised_*）+ 新增落库字段（FailureCause.control_sufficiency_reason / FailureCause.risk_acceptance_reason / FailureCause.management_review_evidence）；4M = Man/Machine/Material/Environment（存储枚举，中文仅 UI）。
- **CP 联动**：仅 PFMEA 关联时触发 CP sync_pending；DFMEA 审批只生成版本快照，不要求 CP。
- **CP sync 交付语义**：**Durable outbox**（对齐现有两阶段实现，`fmea_service.py:378` 先 commit + `control_plan_service.py:665` 再 commit）——同事务只提交 APPROVED、版本快照、三条 AuditLog、outbox 记录；CP sync_pending 最终一致（outbox worker 重试、幂等、最终置位）。不采用"同事务"（需重构现有两阶段代码）。
- **AIAG-VDA Step5/6**：AP 是 S/O/D 组合的**查表结果**（`calculateAP` 查 `utils/fmea.ts` AP 表），非 S×O×D 乘积（乘积是 RPN）；Step6 行动触发：H=行动或记录现有控制充分；M=行动或记录风险接受理由；L=行动可选；S=9-10 且 AP=H/M 需管理层评审证据；Step7 门禁 = 所有 AP 已评估（行动已关闭或风险接受已记录）。
- **RecommendedAction 状态**：选定 canonical 枚举 `{open, in_progress, completed}`（对齐现有 `schemas/fmea.py:36` 注释与前端）；AIAG-VDA 手册的 {planned, decided, not_implemented} 不在本 spec 采用。
- **Step3 功能树门禁**：每个纳入分析范围的结构节点都有功能节点（HAS_FUNCTION 边），而非仅"至少一个功能"。
- **编辑器保存保留向导元数据**：编辑器保存 graph_data 时保留 wizardScope（含 wizard_completed），不覆盖非表格 metadata。
- **verify skill**：README 声明的 19 子 skill + 1 总 skill **待生成**（本 epic 仅交付 user stories；skill 由后续走查时派生）。
