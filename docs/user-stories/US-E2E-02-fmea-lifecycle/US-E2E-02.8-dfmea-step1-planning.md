# 子故事 US-E2E-02.8：DFMEA Step1 策划与准备（5T 范围）

**状态**: 定稿 v3（2026-07-25），经三轮代码评审修订（AI 契约同步为 3 required_retrievers）
**所属 epic**: US-E2E-02（README.md v3）
**关联 skill**: `verify-fmea-lifecycle-dfmea-step1-planning`（待生成）
**前置**: 无（向导第一步）
**AIAG-VDA 引用**: `Reference/FMEA.md` §2.1（设计 FMEA 步骤一：策划与准备）
**AI_REQUIRED**: true（5T 范围含 AI 工具/趋势推荐）

## 故事

**作为** 设计质量工程师，**我想** 在创建 DFMEA 时通过向导 Step1 定义 5T 范围（团队 / 时间 / 工具 / 任务 / 趋势），其中工具与趋势字段由 AI 推荐（查询知识库后生成），
**以便** 明确本次 DFMEA 的分析边界、团队职责、输入数据来源，为后续结构/功能/失效分析奠定基础。

## 背景 / 前置条件

- 用户已创建 DFMEA draft 文档（`fmea_type="DFMEA"`，后端注入初始 System 节点）。
- 进入向导 `/fmea/wizard/:id`。

## 主流程

1. `planning_qe` 在 Step1 录入 5T。
2. 工具/趋势字段触发 AI 推荐（`dfmea_tool`/`dfmea_trend` trigger）。
3. 采纳推荐或手工录入。
4. 保存草稿。
5. 推进到 Step2。

## 业务规则 / 验收标准

### 结构完整性
- `wizardScope` 元数据含 5T 字段：`team` / `timeframe` / `tool` / `task` / `trend`（**timeframe，非 timing**，对齐 `WizardScopeSchema`）。

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发 `dfmea_tool`/`dfmea_trend` 推荐时，后端必须查询 3 个 required_retrievers（graph/semantic_search/lessons_learned），通过 `source_executions[]` 可观测；`context_execution.current_product_structure` 组装产品结构；`generation_execution.llm` 生成（见 README "AI 推荐知识库查询契约" 节，查询 DFMEA 节点）。

- **E2E 健康环境断言**：健康环境（有 embedding + LLM 凭证）中，3 required_retrievers 必须为 `success | empty`；`unavailable | error` → FAILED。
- **缺口处理**：现状仅接图(keyword)+context+LLM，**RAG/lessons 未接入** → 验收标 `FAILED`。

### 审计与落库
- Step1 保存写 AuditLog（`action="UPDATE"`，Outbox `fmea.updated`）。
- AI 采纳写 `ADOPT_RECOMMENDATION`。

## 验收契约（字段级）

| 项 | DFMEA 定义 |
|---|---|
| 落库实体 | `FMEADocument.graph_data.wizardScope` |
| 关键字段 | wizardScope.{team, timeframe, tool, task, trend} |
| AI 触发器 | `dfmea_tool`、`dfmea_trend` |
| AI 必查来源 | 3 required_retrievers（graph/semantic_search/lessons_learned）+ context_execution + generation_execution（缺任一→FAILED；#2/#3 当前未接入→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`）、`action="ADOPT_RECOMMENDATION"` |
| E2E seed 前置 | DFMEA draft 文档 + 产品线 |
| 通过条件 | wizardScope 5T 完整 + AI 查全 3 required_retrievers（source_executions 可观测）+ 推荐带 source + 采纳留痕 + 审计 |
| 失败条件（FAILED） | 字段缺失或字段名错误（如 timing）；AI 未查 #2/#3（或健康环境下为 unavailable/error）；推荐无 source；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证 |

## 不在本子故事范围

- Step2 结构分析（见 02.9）。

## 后续

- Step1 为 Step2 结构分析提供上下文。
