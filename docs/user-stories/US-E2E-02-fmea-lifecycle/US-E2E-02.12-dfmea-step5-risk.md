# 子故事 US-E2E-02.12：DFMEA Step5 风险分析

**状态**: 定稿 v3（2026-07-25），经三轮代码评审修订（AI 契约同步为 3 required_retrievers）
**所属 epic**: US-E2E-02（README.md v3）
**关联 skill**: `verify-fmea-lifecycle-dfmea-step5-risk`（待生成）
**前置**: 02.11（Step4 失效链已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §2.5（设计 FMEA 步骤五：风险分析）
**AI_REQUIRED**: true（PC/DC 措施推荐）

## 故事

**作为** 设计质量工程师，**我想** 在向导 Step5 评分：单一严重度 S（DFMEA 无三段式，对齐 AIAG-VDA DFMEA）+ 频度 O（FailureCause.occurrence）+ 探测度 D（DetectionControl.detection），系统自动查 AIAG-VDA AP 表得出 AP（H/M/L），
**以便** 量化每个设计失效链的风险等级，为优化（Step6）提供排序依据。

## 背景 / 前置条件

- Step4 失效链已落库。

## 主流程

1. `planning_qe` 在 Step5 为每行评分：
   - FE 严重度 S：`severity`（1-10，单一值；DFMEA 无三段式）
   - FC 频度 O：`occurrence`（1-10）
   - DC 探测度 D：`detection`（1-10）
2. 系统自动查 AIAG-VDA AP 表得出 AP（**查表结果，非 S×O×D 乘积**；`utils/fmea.ts calculateAP`）。
3. DFMEA 无 CC/SC 列（PFMEA 专有）。
4. PC/DC 措施可触发 AI 推荐（`prevention_control`/`detection_control` trigger）。
5. 保存草稿。
6. 推进到 Step6。

## 业务规则 / 验收标准

### 结构完整性
- S 字段 >0（单一 severity，无三段式）。
- AP 为 S/O/D 组合的**查表结果**（非乘积映射；`utils/fmea.ts` 的 `calculateAP`）。

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发 `prevention_control`/`detection_control` 推荐时，后端必须查询 3 个 required_retrievers（graph/semantic_search/lessons_learned），通过 `source_executions[]` 可观测；`context_execution.current_product_structure` 组装产品结构；`generation_execution.llm` 生成（同 02.4）。

- **E2E 健康环境断言**：健康环境（有 embedding + LLM 凭证）中，3 required_retrievers 必须为 `success | empty`；`unavailable | error` → FAILED。
- **缺口处理**：现状仅接图(keyword)+context+LLM，**RAG/lessons 未接入** → 验收标 `FAILED`。

### 审计与落库
- Step5 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- AI 采纳写 `ADOPT_RECOMMENDATION`。

## 验收契约（字段级）

| 项 | DFMEA 定义 |
|---|---|
| 落库实体 | `FailureEffect`（更新 severity）、`FailureCause`（更新 occurrence）、`DetectionControl`（更新 detection） |
| 关键字段 | FE.severity（单一）；FC.occurrence；DC.detection；AP（查表，非乘积） |
| 边类型 | 无新增 |
| AI 触发器 | `prevention_control`、`detection_control` |
| AI 必查来源 | 3 required_retrievers（graph/semantic_search/lessons_learned）+ context_execution + generation_execution（缺任一→FAILED；#2/#3 当前未接入→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`）、`action="ADOPT_RECOMMENDATION"` |
| E2E seed 前置 | 02.11 失效链 |
| 通过条件 | S>0 + AP 查表正确 + AI 查全 3 required_retrievers（source_executions 可观测）+ 采纳留痕 + 审计 |
| 失败条件（FAILED） | S=0；AP 写成乘积或计算错误；AI 未查 #2/#3（或健康环境下为 unavailable/error）；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证 |

## 不在本子故事范围

- Step6 优化（见 02.13）。

## 后续

- 高 AP 行驱动 Step6 优化行动。
