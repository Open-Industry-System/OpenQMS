# 子故事 US-E2E-02.6：PFMEA Step6 优化

**状态**: 定稿 v2（2026-07-25），经代码评审修订
**所属 epic**: US-E2E-02（README.md v2）
**关联 skill**: `verify-fmea-lifecycle-pfmea-step6-optimization`（待生成）
**前置**: 02.5（Step5 风险分析已就绪，AP 已计算）
**AIAG-VDA 引用**: `Reference/FMEA.md` §3.6（过程 FMEA 步骤六：优化）
**AI_REQUIRED**: true（RecommendedAction 含 AI 推荐措施）

## 故事

**作为** 前期策划质量工程师，**我想** 在向导 Step6 为高风险失效链创建优化行动（RecommendedAction），含责任人/截止日期/状态/实际措施/完成日期/改进后 S′O′D′AP′，其中措施由 AI 推荐（查询全部知识库后生成），
**以便** 明确降低风险的行动项与责任，可追踪执行状态，闭环风险。

## 背景 / 前置条件

- Step5 风险分析已落库，AP 已计算。

## 主流程

1. `planning_qe` 在 Step6 为高 AP 行创建 `RecommendedAction`：
   - `responsible`（责任人）、`due_date`（计划完成日期）、`status`（open/in_progress/completed）
   - `action_taken`（实际采取的措施描述，AI 推荐 `optimization` trigger 或手工）
   - `completion_date`（实际完成日期）
   - `revised_severity`/`revised_occurrence`/`revised_detection`/`revised_ap`（改进后预期值）
2. `OPTIMIZED_BY` 边连接 RecommendedAction 与失效链节点（FC/FM）。
3. AI 推荐 `optimization` trigger。
4. 保存草稿。
5. 推进到 Step7。

## 业务规则 / 验收标准

### 结构完整性
- `RecommendedAction` 节点含现有字段（对齐 `schemas/fmea.py`）：`responsible`/`due_date`/`status`/`action_taken`/`completion_date`/`revised_severity`/`revised_occurrence`/`revised_detection`/`revised_ap`。
- `OPTIMIZED_BY` 边指向失效链节点（FC/FM，见 README "图结构契约" 节）。

### AIAG-VDA Step6 行动触发规则（非简单"H/M 一律创建行动"）
- **H**：行动，或证明并记录现有控制充分（文档化理由）。
- **M**：行动，或按公司规则记录风险接受理由。
- **L**：行动可选。
- **S=9-10 且 AP=H/M**：增加管理层评审证据（可留空，另立深度）。

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
| 关键字段 | responsible、due_date、status ∈ {open, in_progress, completed}、action_taken、completion_date、revised_severity/occurrence/detection/ap |
| 边类型 | `OPTIMIZED_BY`（FC/FM → RecommendedAction） |
| AI 触发器 | `optimization` |
| AI 必查来源 | #1+#2+#3+#4（缺任一→FAILED；#2/#3 当前未接入→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT）；RecommendedAction.status ∈ {open, in_progress, completed}（canonical，对齐 schemas/fmea.py） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`）、`action="ADOPT_RECOMMENDATION"` |
| E2E seed 前置 | 02.5 风险分析 |
| 通过条件 | RecommendedAction 现有字段完整 + OPTIMIZED_BY 边正确 + Step6 行动触发规则（H/M/L）正确 + AI 查全 4 来源（source_executions 可观测）+ 采纳留痕 + 审计 |
| 失败条件（FAILED） | 用了不存在的字段（owner/action_text/target_*）；边缺失；Step6 简单"H/M 一律创建行动"（未区分 H=行动或控制充分/M=行动或风险接受/L=可选）；AI 未查 #2/#3；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证（AI_REQUIRED=true） |

## 不在本子故事范围

- Step7 结果文件化（见 02.7）。
- RecommendedAction 的执行追踪深度（状态流转另立）。
- S=9-10 且 AP=H/M 的管理层评审证据深度（另立）。

## 后续

- RecommendedAction 为 Step7 结果文件化提供优化措施汇总。
