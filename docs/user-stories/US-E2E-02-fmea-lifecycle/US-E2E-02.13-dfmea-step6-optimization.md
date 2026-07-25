# 子故事 US-E2E-02.13：DFMEA Step6 优化

**状态**: 定稿 v3（2026-07-25），经代码评审修订（RecommendedAction 数据模型收口）
**所属 epic**: US-E2E-02（README.md v2）
**关联 skill**: `verify-fmea-lifecycle-dfmea-step6-optimization`（待生成）
**前置**: 02.12（Step5 风险分析已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §2.6（设计 FMEA 步骤六：优化）
**AI_REQUIRED**: true（RecommendedAction 含 AI 推荐措施）

## 故事

**作为** 设计质量工程师，**我想** 在向导 Step6 为高风险失效链创建优化行动（RecommendedAction），其中 `name` 为计划/推荐措施（AI 推荐或手工），`action_taken` 为实施后实际采取的措施，`completion_date` 为实际完成日期，`revised_*` 为改进后预期值，
**以便** 明确降低设计风险的行动项与责任，可追踪执行状态。

## 背景 / 前置条件

- Step5 风险分析已落库，AP 已计算。
- **数据模型**（对齐 `schemas/fmea.py`）：`name` = 计划/推荐措施；`action_taken` = 实际实施措施；`completion_date` = 实际完成日期；`status` = 状态；`revised_*` = 改进后预期值。

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
- **Canonical 枚举**：`{open, in_progress, completed}`（选定）。
- **需迁移**：当前前端枚举为 `{undecided, planned, done, notExecuted}`；schema 注释为 `{open, closed, in_progress}`——三者不一致。
- **Legacy 映射**：`undecided`→`open`；`planned`→`open`/`in_progress`；`done`→`completed`；`notExecuted`→`open`。
- **status=completed 门禁**：`action_taken`、`completion_date`、`revised_occurrence`/`revised_detection`/`revised_ap` 必填。

### AIAG-VDA Step6 行动触发规则（同 02.6）
- H：行动，或证明并记录现有控制充分（`control_sufficiency_reason`）。
- M：行动，或按公司规则记录风险接受理由（`risk_acceptance_reason`）。
- L：行动可选。
- S=9-10 且 AP=H/M：增加管理层评审证据（`management_review_evidence`）。

### 落库字段（新增，需 schema 扩展，同 02.6）
- `control_sufficiency_reason`、`risk_acceptance_reason`、`management_review_evidence`。

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发 `optimization` 推荐时，后端必须查询 4 来源，通过 `source_executions[]` 可观测（同 02.4）。

- **缺口处理**：现状仅接图(keyword)+结构+LLM，**RAG/lessons 未接入** → 验收标 `FAILED`。

### 审计与落库
- Step6 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- AI 采纳写 `ADOPT_RECOMMENDATION`。

## 验收契约（字段级）

| 项 | DFMEA 定义 |
|---|---|
| 落库实体 | `RecommendedAction` + `OPTIMIZED_BY` 边 |
| 关键字段 | name、responsible、due_date、status ∈ {open, in_progress, completed}（canonical，需迁移）、action_taken、completion_date、revised_severity/occurrence/detection/ap、control_sufficiency_reason、risk_acceptance_reason、management_review_evidence |
| 边类型 | `OPTIMIZED_BY`（FC/FM → RecommendedAction） |
| AI 触发器 | `optimization` |
| AI 必查来源 | #1+#2+#3+#4（缺任一→FAILED；#2/#3 当前未接入→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT）；RecommendedAction.status ∈ {open, in_progress, completed}（canonical，需迁移 legacy） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`）、`action="ADOPT_RECOMMENDATION"` |
| E2E seed 前置 | 02.12 风险分析 |
| 通过条件 | 现有字段完整 + status=completed 门禁 + legacy 迁移映射 + OPTIMIZED_BY 边正确 + Step6 行动触发规则 + 新增落库字段 + AI 查全 4 来源（source_executions 可观测）+ 采纳留痕 + 审计 |
| 失败条件（FAILED） | AI 推荐写入 action_taken（应写入 name）；status 用 legacy 枚举未迁移；status=completed 但字段缺失；OPTIMIZED_BY 边方向反了；Step6 简单"H/M 一律创建行动"；新增落库字段缺失；AI 未查 #2/#3；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证 |

## 不在本子故事范围

- Step7 结果文件化（见 02.14）。
- RecommendedAction 的执行追踪深度（另立）。

## 后续

- RecommendedAction 为 Step7 提供优化措施汇总。
