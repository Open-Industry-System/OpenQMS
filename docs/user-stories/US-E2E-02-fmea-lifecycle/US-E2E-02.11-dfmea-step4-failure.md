# 子故事 US-E2E-02.11：DFMEA Step4 失效分析

**状态**: 定稿 v3（2026-07-25），经三轮代码评审修订（AI 契约同步为 3 required_retrievers）
**所属 epic**: US-E2E-02（README.md v3）
**关联 skill**: `verify-fmea-lifecycle-dfmea-step4-failure`（待生成）
**前置**: 02.10（Step3 功能树已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §2.4（设计 FMEA 步骤四：失效分析）
**AI_REQUIRED**: true（FM/FE/FC + PC/DC 含 AI 推荐）

## 故事

**作为** 设计质量工程师，**我想** 在向导 Step4 定义失效链：失效模式(FM) → 失效效应(FE) / 失效原因(FC) + 预防控制(PC) + 探测控制(DC)，其中 FM/FE/FC 由 AI 推荐（查询全部知识库后生成），
**以便** 完整描述设计失效链，为风险分析（Step5）提供评分对象。

## 背景 / 前置条件

- Step3 功能树已落库。

## 主流程

1. `planning_qe` 在 Step4 为每个功能节点录入失效链：
   - `FailureMode`（挂 `ProcessStepFunction`/`ProcessItemFunction`，`HAS_FAILURE_MODE` 边）
   - `FailureEffect`（`EFFECT_OF` 边：FM → FE）
   - `FailureCause`（`CAUSE_OF` 边：FC → FM）
   - `PreventionControl`（`PREVENTED_BY` 边：FC → PC）
   - `DetectionControl`（`DETECTED_BY` 边：FC/FM → DC）
2. FM/FE/FC 字段触发 AI 推荐（`failure_mode`/`failure_effect`/`failure_cause` trigger）。
3. 采纳或手工录入。
4. 保存草稿。
5. 推进到 Step5。

## 业务规则 / 验收标准

### 结构完整性
- 失效链边方向正确（同 02.4，见 README "图结构契约" 节）。
- FM 挂 DFMEA 功能节点（Process*Function）。
- DFMEA 无 4M 上下文（PFMEA 专有）。

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发 `failure_mode`/`failure_effect`/`failure_cause`/`prevention_control`/`detection_control` 推荐时，后端必须查询 3 个 required_retrievers（graph/semantic_search/lessons_learned），通过 `source_executions[]` 可观测；`context_execution.current_product_structure` 组装产品结构；`generation_execution.llm` 生成（同 02.4）。

- **E2E 健康环境断言**：健康环境（有 embedding + LLM 凭证）中，3 required_retrievers 必须为 `success | empty`；`unavailable | error` → FAILED。
- **缺口处理**：现状仅接图(keyword)+context+LLM，**RAG/lessons 未接入** → 验收标 `FAILED`。

### 审计与落库
- Step4 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- AI 采纳写 `ADOPT_RECOMMENDATION`。

## 验收契约（字段级）

| 项 | DFMEA 定义 |
|---|---|
| 落库实体 | `FailureMode`、`FailureEffect`、`FailureCause`、`PreventionControl`、`DetectionControl` |
| 关键字段 | FM.name；FE.name；FC.name；PC.name；DC.name |
| 边类型 | `HAS_FAILURE_MODE`（功能→FM）、`EFFECT_OF`（FM→FE）、`CAUSE_OF`（FC→FM）、`PREVENTED_BY`（FC→PC）、`DETECTED_BY`（FC/FM→DC） |
| AI 触发器 | `failure_mode`、`failure_effect`、`failure_cause`、`prevention_control`、`detection_control` |
| AI 必查来源 | 3 required_retrievers（graph/semantic_search/lessons_learned）+ context_execution + generation_execution（缺任一→FAILED；#2/#3 当前未接入→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`）、`action="ADOPT_RECOMMENDATION"` |
| E2E seed 前置 | 02.10 功能树 |
| 通过条件 | 失效链边方向正确 + FM 挂 DFMEA 功能节点 + AI 查全 3 required_retrievers（source_executions 可观测）+ 采纳留痕 + 审计 |
| 失败条件（FAILED） | 失效链边方向反了；FM 挂错层级；AI 未查 #2/#3（source_executions 缺，或健康环境下为 unavailable/error）；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证 |

## 不在本子故事范围

- Step5 风险分析（见 02.12）。

## 后续

- 失效链节点为 Step5 提供 S/O/D 评分对象。
