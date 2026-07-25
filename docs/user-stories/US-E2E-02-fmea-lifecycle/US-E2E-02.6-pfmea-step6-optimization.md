# 子故事 US-E2E-02.6：PFMEA Step6 优化

**状态**: 定稿 v3（2026-07-25），经代码评审修订（RecommendedAction 数据模型收口）
**所属 epic**: US-E2E-02（README.md v2）
**关联 skill**: `verify-fmea-lifecycle-pfmea-step6-optimization`（待生成）
**前置**: 02.5（Step5 风险分析已就绪，AP 已计算）
**AIAG-VDA 引用**: `Reference/FMEA.md` §3.6（过程 FMEA 步骤六：优化）
**AI_REQUIRED**: true（RecommendedAction 含 AI 推荐措施）

## 故事

**作为** 前期策划质量工程师，**我想** 在向导 Step6 为高风险失效链创建优化行动（RecommendedAction），其中 `name` 为计划/推荐措施（AI 推荐或手工），`action_taken` 为实施后实际采取的措施，`completion_date` 为实际完成日期，`revised_*` 为改进后预期值，
**以便** 明确降低风险的行动项与责任，可追踪执行状态，闭环风险。

## 背景 / 前置条件

- Step5 风险分析已落库，AP 已计算。
- **数据模型**（对齐 `PFMEAWizardPage.tsx:581` + `schemas/fmea.py`）：
  - `name` = 计划/推荐措施（AI 推荐写入此处）
  - `action_taken` = 实际实施措施（实施后填写）
  - `completion_date` = 实际完成日期（实施后填写）
  - `status` = 状态（见下 canonical 枚举）
  - `revised_severity`/`revised_occurrence`/`revised_detection`/`revised_ap` = 改进后预期值

## 主流程

1. `planning_qe` 在 Step6 为高 AP 行创建 `RecommendedAction`：
   - `name`（计划/推荐措施，AI 推荐 `optimization` trigger 或手工）
   - `responsible`（责任人）、`due_date`（计划完成日期）、`status`
   - 实施后填写：`action_taken`（实际措施）、`completion_date`（实际完成日期）
   - `revised_severity`/`revised_occurrence`/`revised_detection`/`revised_ap`（改进后预期值）
2. `OPTIMIZED_BY` 边：FC/FM → RecommendedAction。
3. AI 推荐 `optimization` trigger → 写入 `name`。
4. 保存草稿。
5. 推进到 Step7。

## 业务规则 / 验收标准

### 结构完整性
- `RecommendedAction` 节点含现有字段：`name`/`responsible`/`due_date`/`status`/`action_taken`/`completion_date`/`revised_severity`/`revised_occurrence`/`revised_detection`/`revised_ap`。
- `OPTIMIZED_BY` 边：FC/FM → RecommendedAction。

### RecommendedAction 状态枚举（canonical，需迁移）
- **Canonical 枚举**：`{open, in_progress, completed}`（选定，对齐 `schemas/fmea.py:36` 注释）。
- **需迁移**：当前前端枚举为 `{undecided, planned, done, notExecuted}`（`PFMEAWizardPage.tsx:567-570`）；schema 注释为 `{open, closed, in_progress}`——三者不一致。
- **Legacy 映射**（需数据迁移）：
  - `undecided` → `open`
  - `planned` → `open` 或 `in_progress`（按实际进度）
  - `done` → `completed`
  - `notExecuted` → `open`
- **status=completed 门禁**：`action_taken`、`completion_date`、`revised_occurrence`/`revised_detection`/`revised_ap` 必填（`revised_severity` 可留空若 S 不变）。

### AIAG-VDA Step6 行动触发规则
- **H**：行动，或证明并记录现有控制充分（`control_sufficiency_reason` 字段，见下）。
- **M**：行动，或按公司规则记录风险接受理由（`risk_acceptance_reason` 字段，见下）。
- **L**：行动可选。
- **S=9-10 且 AP=H/M**：增加管理层评审证据（`management_review_evidence` 字段，见下）。

### 落库字段（新增，需 schema 扩展）
- `control_sufficiency_reason: str | None`（H 不采取行动时的理由）
- `risk_acceptance_reason: str | None`（M 不采取行动时的理由）
- `management_review_evidence: str | None`（S=9-10 且 AP=H/M 时的管理层评审证据）
- **Step7 门禁依赖**：Step7 完成前检查——所有 AP=H/M 的行，要么有 RecommendedAction（status=completed），要么有 control_sufficiency_reason/risk_acceptance_reason 非空。

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发 `optimization` 推荐时，后端必须查询 4 来源，通过 `source_executions[]` 可观测（同 02.4）。

- **缺口处理**：现状仅接图(keyword)+结构+LLM，**RAG/lessons 未接入** → 验收标 `FAILED`。

### 审计与落库
- Step6 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- AI 采纳写 `ADOPT_RECOMMENDATION`。

## 验收契约（字段级）

| 项 | PFMEA 定义 |
|---|---|
| 落库实体 | `RecommendedAction` + `OPTIMIZED_BY` 边 |
| 关键字段 | name（计划/推荐措施）、responsible、due_date、status ∈ {open, in_progress, completed}（canonical，需迁移）、action_taken（实施后）、completion_date（实施后）、revised_severity/occurrence/detection/ap、control_sufficiency_reason（H 不行动时）、risk_acceptance_reason（M 不行动时）、management_review_evidence（S=9-10+AP=H/M 时） |
| 边类型 | `OPTIMIZED_BY`（FC/FM → RecommendedAction） |
| AI 触发器 | `optimization` |
| AI 必查来源 | #1+#2+#3+#4（缺任一→FAILED；#2/#3 当前未接入→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT）；RecommendedAction.status ∈ {open, in_progress, completed}（canonical，需迁移 legacy） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`）、`action="ADOPT_RECOMMENDATION"` |
| E2E seed 前置 | 02.5 风险分析 |
| 通过条件 | RecommendedAction 现有字段完整（name/action_taken/completion_date/revised_*）+ status=completed 门禁（action_taken/completion_date/revised_O/D/AP 必填）+ legacy 迁移映射 + OPTIMIZED_BY 边正确（FC/FM→RecommendedAction）+ Step6 行动触发规则（H/M/L）+ 新增落库字段（control_sufficiency_reason/risk_acceptance_reason/management_review_evidence）+ AI 查全 4 来源（source_executions 可观测）+ 采纳留痕 + 审计 |
| 失败条件（FAILED） | AI 推荐写入 action_taken（应写入 name）；status 用 legacy 枚举未迁移；status=completed 但 action_taken/completion_date/revised_* 缺失；OPTIMIZED_BY 边方向反了；Step6 简单"H/M 一律创建行动"（未区分 H=行动或控制充分/M=行动或风险接受/L=可选）；新增落库字段缺失；AI 未查 #2/#3；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证（AI_REQUIRED=true） |

## 不在本子故事范围

- Step7 结果文件化（见 02.7）。
- RecommendedAction 的执行追踪深度（状态流转另立）。
- S=9-10 且 AP=H/M 的管理层评审流程深度（本子故事只验收字段存在与非空，不验收评审流程本身）。

## 后续

- RecommendedAction 为 Step7 结果文件化提供优化措施汇总；Step7 门禁检查所有 AP=H/M 已评估（行动完成或理由记录）。
