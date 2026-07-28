# 子故事 US-E2E-02.6：PFMEA Step6 优化

**状态**: 定稿 v4（2026-07-25），经三轮代码评审修订（RecommendedAction 数据模型 + FailureCause 风险处置字段归属）
**所属 epic**: US-E2E-02（README.md v3）
**关联 skill**: `verify-fmea-lifecycle-pfmea-step6-optimization`（待生成）
**前置**: 02.5（Step5 风险分析已就绪，AP 已计算）
**AIAG-VDA 引用**: `Reference/FMEA.md` §3.6（过程 FMEA 步骤六：优化）
**AI_REQUIRED**: true（RecommendedAction 含 AI 推荐措施）

## 故事

**作为** 前期策划质量工程师，**我想** 在向导 Step6 为高风险失效链创建优化行动（RecommendedAction，其中 `name` 为计划/推荐措施）或记录风险处置理由（`FailureCause.control_sufficiency_reason` / `risk_acceptance_reason` / `management_review_evidence`），
**以便** 明确降低风险的行动项与责任，或记录不采取行动的理由，闭环风险。

## 背景 / 前置条件

- Step5 风险分析已落库，AP 已计算。
- **RecommendedAction 数据模型**（对齐 `PFMEAWizardPage.tsx:581` + `schemas/fmea.py`）：
  - `name` = 计划/推荐措施（AI 推荐写入此处）
  - `action_taken` = 实际实施措施（实施后填写）
  - `completion_date` = 实际完成日期（实施后填写）
  - `status` = 状态（见下 canonical 枚举）
  - `revised_severity`/`revised_occurrence`/`revised_detection`/`revised_ap` = 改进后预期值
- **FailureCause 风险处置字段**（新增，挂 FailureCause 因行模型为 FM×FC，见 README "编辑器行模型" 节）：
  - `control_sufficiency_reason` = H 不采取行动时的控制充分理由
  - `risk_acceptance_reason` = M 不采取行动时的风险接受理由
  - `management_review_evidence` = S=9-10 且 AP=H/M 时的管理层评审证据

## 主流程

1. `planning_qe` 在 Step6 为高风险失效链选择：
   - **创建 RecommendedAction**：`name`（计划/推荐措施，AI 推荐 `optimization` trigger 或手工）+ `responsible`（责任人）+ `due_date`（计划完成日期）+ `status`；实施后填写 `action_taken`/`completion_date`/`revised_*`。
   - **不创建行动**：在 FailureCause 上记录 `control_sufficiency_reason`（H）或 `risk_acceptance_reason`（M）。
2. `OPTIMIZED_BY` 边：FC/FM → RecommendedAction（若创建）。
3. AI 推荐 `optimization` trigger → 写入 `name`。
4. 保存草稿。
5. 推进到 Step7。

## 业务规则 / 验收标准

### 结构完整性
- `RecommendedAction` 节点含现有字段：`name`/`responsible`/`due_date`/`status`/`action_taken`/`completion_date`/`revised_severity`/`revised_occurrence`/`revised_detection`/`revised_ap`。
- `FailureCause` 节点含新增字段：`control_sufficiency_reason`/`risk_acceptance_reason`/`management_review_evidence`（**需 schema 扩展**）。
- `OPTIMIZED_BY` 边：FC/FM → RecommendedAction。
- **若无 FC 的 placeholder 行**（`_null` key）允许评估，则回退到 `FailureMode.control_sufficiency_reason`/`risk_acceptance_reason`/`management_review_evidence`（同一规则，见 README "编辑器行模型" 节）。

### RecommendedAction 状态枚举（canonical，需迁移）
- **Canonical 枚举**：`{open, in_progress, completed, not_executed}`（选定，含第 4 态 `not_executed`）。
- **需迁移**：当前前端枚举为 `{undecided, planned, done, notExecuted}`；schema 注释为 `{open, closed, in_progress}`——三者不一致。
- **确定性 Legacy 映射**（需数据迁移）：
  - `undecided` → `open`
  - `planned` → `in_progress`
  - `done` → `completed`
  - `notExecuted` → `not_executed`
  - `closed` → `completed`（schema 注释的 legacy）
- **`status=not_executed` 门禁**：必须对应 `FailureCause.control_sufficiency_reason` 或 `risk_acceptance_reason` 非空（不执行须有理由）。
- **`status=completed` 门禁**：`action_taken`、`completion_date`、`revised_occurrence`/`revised_detection`/`revised_ap` 必填（`revised_severity` 可留空若 S 不变）。

### AIAG-VDA Step6 行动触发规则
- **H**：行动（RecommendedAction），或证明并记录现有控制充分（`FailureCause.control_sufficiency_reason`）。
- **M**：行动（RecommendedAction），或按公司规则记录风险接受理由（`FailureCause.risk_acceptance_reason`）。
- **L**：行动可选。
- **S=9-10 且 AP=H/M**：无论选择完成行动还是风险接受，`FailureCause.management_review_evidence` 都必须非空（纳入 Step7 门禁，见 02.7）。

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发 `optimization` 推荐时，后端必须查询 3 个 required_retrievers，通过 `source_executions[]` 可观测；`context_execution.current_product_structure` 组装产品结构；`generation_execution.llm` 生成（见 README "AI 推荐知识库查询契约" 节）。

- **缺口处理**：现状仅接图(keyword)+上下文组装+LLM，**RAG/lessons 未接入** → 验收标 `FAILED`。

### 审计与落库
- Step6 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- AI 采纳写 `ADOPT_RECOMMENDATION`。

## 验收契约（字段级）

| 项 | PFMEA 定义 |
|---|---|
| 落库实体 | `RecommendedAction` + `OPTIMIZED_BY` 边 + `FailureCause`（风险处置字段） |
| 关键字段 | RecommendedAction.{name, responsible, due_date, status ∈ {open, in_progress, completed, not_executed}, action_taken, completion_date, revised_severity/occurrence/detection/ap}；FailureCause.{control_sufficiency_reason, risk_acceptance_reason, management_review_evidence} |
| 边类型 | `OPTIMIZED_BY`（FC/FM → RecommendedAction） |
| AI 触发器 | `optimization` |
| AI 必查来源 | 3 required_retrievers（graph/semantic_search/lessons_learned）+ context_execution + generation_execution（缺任一→FAILED；#2/#3 当前未接入→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT）；RecommendedAction.status ∈ {open, in_progress, completed, not_executed}（canonical，需迁移 legacy） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`）、`action="ADOPT_RECOMMENDATION"` |
| E2E seed 前置 | 02.5 风险分析 |
| 通过条件 | RecommendedAction 现有字段完整 + status=completed 门禁（action_taken/completion_date/revised_O/D/AP 必填）+ status=not_executed 门禁（须有 control_sufficiency_reason 或 risk_acceptance_reason）+ FailureCause 风险处置字段归属（含 placeholder 行回退到 FailureMode）+ 确定性 legacy 迁移映射（undecided→open, planned→in_progress, done→completed, notExecuted→not_executed, closed→completed）+ OPTIMIZED_BY 边正确（FC/FM→RecommendedAction）+ Step6 行动触发规则（H/M/L）+ S=9-10 且 AP=H/M 时 management_review_evidence 非空 + AI 查全 3 required_retrievers（source_executions 可观测）+ 采纳留痕 + 审计 |
| 失败条件（FAILED） | AI 推荐写入 action_taken（应写入 name）；status 用 legacy 枚举未迁移；status=completed 但 action_taken/completion_date/revised_* 缺失；status=not_executed 但无理由；风险处置字段挂错节点（如挂 RecommendedAction 而非 FailureCause）；OPTIMIZED_BY 边方向反了；Step6 简单"H/M 一律创建行动"；S=9-10 且 AP=H/M 时 management_review_evidence 为空；AI 未查 #2/#3；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证（AI_REQUIRED=true） |

## 不在本子故事范围

- Step7 结果文件化（见 02.7）。
- RecommendedAction 的执行追踪深度（状态流转另立）。
- S=9-10 且 AP=H/M 的管理层评审流程深度（本子故事只验收字段存在与非空，不验收评审流程本身）。

## 后续

- RecommendedAction 与 FailureCause 风险处置字段为 Step7 结果文件化提供优化措施汇总；Step7 门禁检查所有 AP=H/M 已评估（行动完成或理由记录，S=9-10 时含 management_review_evidence）。
