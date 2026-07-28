# 子故事 US-E2E-02.16：编辑器内 AI 推荐（全知识库查询）

**状态**: 定稿 v3（2026-07-25），经三轮代码评审修订（AI 契约同步为 3 required_retrievers）
**所属 epic**: US-E2E-02（README.md v3）
**关联 skill**: `verify-fmea-lifecycle-editor-ai-recommend`（待生成）
**前置**: 02.15（编辑器行已就绪）
**AI_REQUIRED**: true（SmartSuggestionDropdown 全触发器）

## 故事

**作为** 前期策划质量工程师 / 设计质量工程师，**我想** 在 FMEA 编辑器内的失效链单元格触发 AI 推荐下拉（SmartSuggestionDropdown），覆盖 failure_mode/failure_effect/failure_cause/prevention_control/detection_control 五种触发器，每次推荐查询全部知识库后生成，来源可观测（source_executions），采纳可审计（ADOPT_RECOMMENDATION），
**以便** 在编辑器内继续编辑时复用跨 FMEA 知识，AI 推荐有据可依、来源可追溯、采纳可审计。

## 背景 / 前置条件

- 编辑器已集成 `SmartSuggestionDropdown`（`frontend/src/components/dfmea/SmartSuggestionDropdown.tsx`）。
- 后端 `POST /api/fmea/{id}/recommend` 支持 5 触发器。
- 现状：`RecommendationService.recommend` 仅接图(keyword)+产品结构+LLM，**RAG 语义搜索(#2)与经验教训库(#3)未接入**（缺口）；`RecommendResponse` 无 `source_executions` 字段（缺口）；保存 payload 无采纳元数据（缺口）。

## 主流程

1. `planning_qe` 在编辑器单元格聚焦/输入，500ms 防抖后触发 AI 推荐。
2. 后端 `RecommendationService.recommend` 执行：
   - 规则引擎 → 图相似度 → RAG 语义 → 经验教训 → 上下文组装 → LLM 融合
3. 响应含 `source_executions[]`（3 required_retrievers 的 status/hit_count/latency_ms）+ `context_execution.current_product_structure` + `generation_execution.llm`。
4. 前端下拉展示推荐项（含 source 标签 + source_document_no 来源标注）。
5. 采纳或跳过；采纳在保存 payload 中携带采纳元数据，后端写 `ADOPT_RECOMMENDATION` 审计。

## 业务规则 / 验收标准

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发任一 5 触发器推荐时，后端必须查询 3 个 required_retrievers（外部检索），通过 `source_executions[]` 可观测；`context_execution.current_product_structure` 组装产品结构（不计入 source_executions）；`generation_execution.llm` 生成（见 README "AI 推荐知识库查询契约" 节）：

| # | 来源 | 查询内容 | `source_executions` 期望 |
|---|---|---|---|
| 1 | 其他 FMEA 图节点 | `find_similar_nodes_advanced`（FailureMode/Cause/Control） | `source=graph, status∈{success,empty}` |
| 2 | RAG 语义搜索 | `document_embeddings` pgvector（`SemanticSearchSource`，现状未接入 FMEA 推荐） | `source=semantic_search, status∈{success,empty}` |
| 3 | 经验教训库 | `LessonsLearnedService`（现状未接入 FMEA 推荐） | `source=lessons_learned, status∈{success,empty}` |
| — | 当前产品结构 | `_assemble_context`（process_step / function_description） | （`context_execution.current_product_structure`，不计入 source_executions） |

- **来源可追溯**：每条推荐带 `source` ∈ {rule, graph, semantic_search, lessons_learned, llm}（需扩展 `schemas/recommendation.py`）；`source_document_no` 仅对 graph/semantic_search/lessons_learned（有来源文档时）必填。
- **零命中 vs 未调用**：`source_executions` 的 `status=empty`（调用了但无结果）≠ `status=unavailable`（未调用/无凭证）—— E2E 依据 `source_executions` 区分。
- **E2E 健康环境断言**：健康环境（有 embedding + LLM 凭证）中，3 required_retrievers 必须为 `success | empty`；`unavailable | error` → FAILED。
- **缺口处理**：现状 #2/#3 未接入 `RecommendationService`（仅接 CAPA `HybridRecommendationPipeline`）；`RecommendResponse` 无 `source_executions`/`context_execution`/`generation_execution` 字段 → 本子故事验收标 `FAILED`（驱动补齐）。

### AI 采纳审计契约（当前无 API，验收为 FAILED 驱动补齐）
- 保存 payload 携带采纳元数据 `{field_id, recommendation_id, source, stage_index, adopted_text}`（见 README "AI 采纳审计契约" 节）。
- 后端写 `ADOPT_RECOMMENDATION`（`action="ADOPT_RECOMMENDATION"`，changed_fields 含采纳元数据）。
- 区分采纳（有元数据）vs 手工输入（无元数据 → 普通 UPDATE）。

### 限流与缓存
- 限流：per_user + per_fmea（`_check_rate_limit`）。
- 缓存：24h（`RecommendationCache`，cache key 含 scope + include_graph）。

### 可编辑状态
- 仅 DRAFT、REWORK 可触发 AI 推荐（编辑器内编辑行为，IN_REVIEW/APPROVED 不可编辑）。

## 验收契约（字段级）

| 项 | 定义（跨 PFMEA/DFMEA） |
|---|---|
| 落库实体 | `RecommendationCache`（缓存）、`AuditLog`（采纳）、`RecommendResponse.source_executions`/`context_execution`/`generation_execution`（三个新增响应字段） |
| 关键字段 | RecommendResponse.{suggestions, source_executions, context_execution, generation_execution, graph_match_count, effective_scope}；SuggestionItem.{name, confidence, source, source_document_no}；source_executions[].{source, status, hit_count, latency_ms}；context_execution.{current_product_structure}；generation_execution.{llm} |
| 边类型 | 无新增 |
| AI 触发器 | `failure_mode`、`failure_effect`、`failure_cause`、`prevention_control`、`detection_control` |
| AI 必查来源 | 3 required_retrievers（graph/semantic_search/lessons_learned）+ context_execution + generation_execution（缺任一→FAILED；#2/#3 当前未接入→FAILED） |
| 状态枚举 | FMEAState ∈ {DRAFT, REWORK}（仅二者可编辑） |
| 审计事件 | AuditLog `action="ADOPT_RECOMMENDATION"`（采纳）、`action="UPDATE"`（手工） |
| E2E seed 前置 | 02.15 编辑器行 + LLM 凭证 |
| 通过条件 | 5 触发器均可用 + AI 查全 3 required_retrievers（source_executions 可观测）+ 推荐带 source + 来源可追溯 + 采纳元数据 + ADOPT_RECOMMENDATION 审计 + 限流/缓存生效 + 仅 DRAFT/REWORK 可触发 |
| 失败条件（FAILED） | AI 未查 #2 RAG 或 #3 lessons（source_executions 缺，或健康环境下为 unavailable/error）；RecommendResponse 无 source_executions/context_execution/generation_execution；推荐无 source；来源不可追溯；采纳无元数据/审计；IN_REVIEW/APPROVED 可触发 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证（AI_REQUIRED=true） |

## 不在本子故事范围

- 编辑器行级 CRUD（见 02.15）。
- 协同编辑 + 冲突（见 02.17）。
- AI 推荐准确率评测（另立）。

## 后续

- 补齐 #2/#3 接入 + `source_executions`/`context_execution`/`generation_execution` 三个响应字段 + 采纳元数据 API 后，本子故事转 PASS；与 02.4/02.5/02.6/02.11/02.12/02.13 向导内 AI 共享同一推荐管道。
