# 子故事 US-E2E-02.1：PFMEA Step1 策划与准备（5T 范围）

**状态**: 定稿 v2（2026-07-25），经代码评审修订
**所属 epic**: US-E2E-02（README.md v2）
**关联 skill**: `verify-fmea-lifecycle-pfmea-step1-planning`（待生成）
**前置**: 无（向导第一步）
**AIAG-VDA 引用**: `Reference/FMEA.md` §3.1（过程 FMEA 步骤一：策划与准备）
**AI_REQUIRED**: true（5T 范围含 AI 工具/趋势推荐）

## 故事

**作为** 前期策划质量工程师，**我想** 在创建 PFMEA 时通过向导 Step1 定义 5T 范围（团队 Team / 时间 Timeframe / 工具 Tool / 任务 Task / 趋势 Trend），其中工具与趋势字段由 AI 推荐（查询知识库后生成），
**以便** 明确本次 PFMEA 的分析边界、团队职责、输入数据来源，为后续结构/功能/失效分析奠定基础。

## 背景 / 前置条件

- 系统已部署；用户已创建 PFMEA draft 文档（`POST /api/fmea/`，`fmea_type="PFMEA"`，后端注入初始 ProcessItem 节点）。
- 进入向导页面 `/fmea/pfmea-wizard/:id`。

## 主流程

1. `planning_qe` 在 Step1 录入 5T：团队（成员 + 角色）、时间安排（timeframe）、任务（task）、工具（tool）、趋势（trend）。
2. 工具/趋势字段触发 AI 推荐（`pfmea_tool`/`pfmea_trend` trigger），下拉展示 AI 建议。
3. 采纳推荐或手工录入。
4. 保存草稿（`PUT /api/fmea/{id}` graph_data + `wizardScope` 元数据）。
5. 推进到 Step2。

## 业务规则 / 验收标准

### 结构完整性
- `wizardScope` 元数据含 5T 字段：`team` / `timeframe` / `tool` / `task` / `trend`（**字段名对齐 `WizardScopeSchema`**，非 timing）。
- 工具字段非空（AI 采纳或手工）；趋势字段非空。

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发 `pfmea_tool`/`pfmea_trend` 推荐时，后端必须**先查询以下全部来源**，通过 `source_executions[]` 可观测（见 README "AI 推荐知识库查询契约" 节）：

| # | 来源 | 查询内容 | `source_executions` 期望 |
|---|---|---|---|
| 1 | 其他 FMEA 图节点 | 同产品线/全局的 PFMEA `wizardScope.tool`/`trend` 历史 | `source=graph, status∈{success,empty}` |
| 2 | RAG 语义搜索 | 跨 FMEA wizardScope 向量相似（pgvector） | `source=semantic_search, status∈{success,empty,unavailable}` |
| 3 | 经验教训库 | 历史 PFMEA 经验教训 | `source=lessons_learned, status∈{success,empty,unavailable}` |
| 4 | 当前产品结构 | product_line_code / fmea_title / task / team | （context assembly，不计入 source_executions） |

- **来源可追溯**：每条推荐带 `source` ∈ {rule, graph, semantic_search, lessons_learned, llm}（需扩展 `schemas/recommendation.py`）；`source_document_no` 仅对 graph/semantic_search 必填。
- **缺口处理**：现状 `RecommendationService` 仅接 #1(keyword)+#4+LLM，**#2/#3 未接入** → 本子故事验收标 `FAILED`（驱动补齐）。

### 审计与落库
- Step1 保存写 AuditLog（`action="UPDATE"`，Outbox `event_type="fmea.updated"`）。
- AI 采纳写 `ADOPT_RECOMMENDATION`（`action="ADOPT_RECOMMENDATION"`，changed_fields 含 field_id/source/stage_index/adopted_text；当前无采纳元数据 API，见 README "AI 采纳审计契约" 节）。
- `wizardScope` 持久化到 `graph_data.wizardScope` JSONB。

## 验收契约（字段级）

| 项 | PFMEA 定义 |
|---|---|
| 落库实体 | `FMEADocument.graph_data.wizardScope`（元数据，无新图节点） |
| 关键字段 | wizardScope.{team, timeframe, tool, task, trend}（**timeframe，非 timing**） |
| AI 触发器 | `pfmea_tool`、`pfmea_trend` |
| AI 必查来源 | #1+#2+#3+#4（缺任一→FAILED；#2/#3 当前未接入→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | AuditLog `action="UPDATE"`（Outbox `fmea.updated`）、`action="ADOPT_RECOMMENDATION"` |
| E2E seed 前置 | PFMEA draft 文档 + 产品线 DC-DC-100 |
| 通过条件 | wizardScope 5T 完整 + AI 查全 4 来源（source_executions 可观测）+ 推荐带 source + 采纳留痕 + 审计 |
| 失败条件（FAILED） | wizardScope 字段缺失或字段名错误（如 timing）；AI 未查 #2 RAG 或 #3 lessons（source_executions 缺 semantic_search/lessons_learned）；推荐无 source；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证（AI_REQUIRED=true） |

## 不在本子故事范围

- Step2 结构分析（见 02.2）。
- 5T 字段的逐项 UI 表单校验深度（另立）。
- AI 推荐准确率评测（另立）。

## 后续

- Step1 的 `wizardScope` 与产品线信息为 Step2 结构分析提供上下文。
