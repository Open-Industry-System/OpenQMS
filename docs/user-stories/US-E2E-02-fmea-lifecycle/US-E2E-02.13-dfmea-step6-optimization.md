# 子故事 US-E2E-02.13：DFMEA Step6 优化

**状态**: 定稿 v4（2026-07-25），经三轮代码评审修订（RecommendedAction 数据模型 + FailureCause 风险处置字段归属）
**所属 epic**: US-E2E-02（README.md v3）
**关联 skill**: `verify-fmea-lifecycle-dfmea-step6-optimization`（待生成）
**前置**: 02.12（Step5 风险分析已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §2.6（设计 FMEA 步骤六：优化）
**AI_REQUIRED**: true（RecommendedAction 含 AI 推荐措施）

## 故事

**作为** 设计质量工程师，**我想** 在向导 Step6 为高风险失效链创建优化行动（RecommendedAction，其中 `name` 为计划/推荐措施）或记录风险处置理由（`FailureCause.control_sufficiency_reason` / `risk_acceptance_reason` / `management_review_evidence`），
**以便** 明确降低设计风险的行动项与责任，或记录不采取行动的理由。

## 背景 / 前置条件

- Step5 风险分析已落库，AP 已计算。
- **RecommendedAction 数据模型**（对齐 `schemas/fmea.py`）：`name` = 计划/推荐措施；`action_taken` = 实际实施措施；`completion_date` = 实际完成日期；`status` = 状态；`revised_*` = 改进后预期值。
- **FailureCause 风险处置字段**（新增，挂 FailureCause 因行模型为 FM×FC）：`control_sufficiency_reason`/`risk_acceptance_reason`/`management_review_evidence`。

## 主流程

1. `planning_qe` 在 Step6 为高风险失效链选择：
   - **创建 RecommendedAction**：`name`（AI 推荐或手工）+ `responsible` + `due_date` + `status`；实施后填写 `action_taken`/`completion_date`/`revised_*`。
   - **不创建行动**：在 FailureCause 上记录 `control_sufficiency_reason`（H）或 `risk_acceptance_reason`（M）。
2. `OPTIMIZED_BY` 边：FC/FM → RecommendedAction（若创建）。
3. AI 推荐 `optimization` trigger → 写入 `name`。
4. 保存草稿。
5. 推进到 Step7。

## 业务规则 / 验收标准

### 结构完整性
- `RecommendedAction` 节点含现有字段（同 02.6）。
- `FailureCause` 节点含新增字段：`control_sufficiency_reason`/`risk_acceptance_reason`/`management_review_evidence`（**需 schema 扩展**）。
- `OPTIMIZED_BY` 边：FC/FM → RecommendedAction。
- **若无 FC 的 placeholder 行**（`_null` key）允许评估，则回退到 `FailureMode.*_reason`/`management_review_evidence`（同 02.6）。

### RecommendedAction 状态枚举（canonical，需迁移，同 02.6）
- **Canonical 枚举**：`{open, in_progress, completed, not_executed}`。
- **确定性 Legacy 映射**：`undecided`→`open`；`planned`→`in_progress`；`done`→`completed`；`notExecuted`→`not_executed`；`closed`→`completed`。
- **`status=not_executed` 门禁**：必须对应 `FailureCause.control_sufficiency_reason` 或 `risk_acceptance_reason` 非空。
- **`status=completed` 门禁**：`action_taken`/`completion_date`/`revised_occurrence`/`revised_detection`/`revised_ap` 必填。

### AIAG-VDA Step6 行动触发规则（同 02.6）
- H：行动（RecommendedAction），或记录控制充分理由（`FailureCause.control_sufficiency_reason`）。
- M：行动（RecommendedAction），或记录风险接受理由（`FailureCause.risk_acceptance_reason`）。
- L：行动可选。
- S=9-10 且 AP=H/M：无论完成行动还是风险接受，`FailureCause.management_review_evidence` 都必须非空（纳入 Step7 门禁，见 02.14）。

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发 `optimization` 推荐时，后端必须查询 3 个 required_retrievers，通过 `source_executions[]` 可观测；`context_execution.current_product_structure` 组装产品结构；`generation_execution.llm` 生成（同 02.6）。

- **缺口处理**：现状仅接图(keyword)+上下文组装+LLM，**RAG/lessons 未接入** → 验收标 `FAILED`。

### 审计与落库
- Step6 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- AI 采纳写 `ADOPT_RECOMMENDATION`。

## 验收契约（字段级）

| 项 | DFMEA 定义 |
|---|---|
| 落库实体 | `RecommendedAction` + `OPTIMIZED_BY` 边 + `FailureCause`（风险处置字段） |
| 关键字段 | RecommendedAction.{name, responsible, due_date, status ∈ {open, in_progress, completed, not_executed}, action_taken, completion_date, revised_severity/occurrence/detection/ap}；FailureCause.{control_sufficiency_reason, risk_acceptance_reason, management_review_evidence} |
| 边类型 | `OPTIMIZED_BY`（FC/FM → RecommendedAction） |
| AI 触发器 | `optimization` |
| AI 必查来源 | 3 required_retrievers + context_execution + generation_execution（缺任一→FAILED；#2/#3 当前未接入→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT）；RecommendedAction.status ∈ {open, in_progress, completed, not_executed}（canonical，需迁移 legacy） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`）、`action="ADOPT_RECOMMENDATION"` |
| E2E seed 前置 | 02.12 风险分析 |
| 通过条件 | 同 02.6（RecommendedAction 字段完整 + status 门禁 + FailureCause 风险处置字段归属 + 确定性迁移 + OPTIMIZED_BY 边正确 + Step6 行动触发规则 + S=9-10 时 management_review_evidence 非空 + AI 查全 3 required_retrievers + 采纳留痕 + 审计） |
| 失败条件（FAILED） | 同 02.6 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证 |

## 不在本子故事范围

- Step7 结果文件化（见 02.14）。
- RecommendedAction 的执行追踪深度（另立）。

## 后续

- RecommendedAction 与 FailureCause 风险处置字段为 Step7 提供优化措施汇总。
