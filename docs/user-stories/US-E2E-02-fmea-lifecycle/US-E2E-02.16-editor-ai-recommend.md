# 子故事 US-E2E-02.16：编辑器内 AI 推荐（全知识库查询）

**状态**: 定稿 v1（2026-07-25）
**所属 epic**: US-E2E-02（README.md v1）
**关联 skill**: `verify-fmea-lifecycle-editor-ai-recommend`
**前置**: 02.15（编辑器行已就绪）
**AI_REQUIRED**: true（SmartSuggestionDropdown 全触发器）

## 故事

**作为** 前期策划质量工程师 / 设计质量工程师，**我想** 在 FMEA 编辑器内的失效链单元格触发 AI 推荐下拉（SmartSuggestionDropdown），覆盖 failure_mode/failure_effect/failure_cause/prevention_control/detection_control 五种触发器，每次推荐查询全部知识库后生成，
**以便** 在编辑器内继续编辑时复用跨 FMEA 知识，AI 推荐有据可依、来源可追溯。

## 背景 / 前置条件

- 编辑器已集成 `SmartSuggestionDropdown`（`frontend/src/components/dfmea/SmartSuggestionDropdown.tsx`）。
- 后端 `POST /api/fmea/{id}/recommend` 支持 5 触发器。
- 现状：`RecommendationService.recommend` 仅接图(keyword)+产品结构+LLM，**RAG 语义搜索(#2)与经验教训库(#3)未接入**（缺口）。

## 主流程

1. `planning_qe` 在编辑器单元格聚焦/输入，500ms 防抖后触发 AI 推荐。
2. 后端 `RecommendationService.recommend` 执行：
   - 规则引擎 → 图相似度 → RAG 语义 → 经验教训 → LLM 融合
3. 前端下拉展示推荐项（含 source 标签 + source_document_no 来源标注）。
4. 采纳或跳过；采纳写 `ADOPT_RECOMMENDATION` 审计。

## 业务规则 / 验收标准

### AI 推荐知识库查询契约（AI_REQUIRED=true）
触发任一 5 触发器推荐时，后端必须查询 4 来源：

| # | 来源 | 查询内容 |
|---|---|---|
| 1 | 其他 FMEA 图节点 | `find_similar_nodes_advanced`（FailureMode/Cause/Control） |
| 2 | RAG 语义搜索 | `document_embeddings` pgvector（`SemanticSearchSource`，现状未接入 FMEA 推荐） |
| 3 | 经验教训库 | `LessonsLearnedService`（现状未接入 FMEA 推荐） |
| 4 | 当前产品结构 | `_assemble_context`（process_step / function_description） |

- **来源可追溯**：每条推荐带 `source` ∈ {rule, graph, semantic_search, lessons_learned, llm}；`source_document_no` 标注来源 FMEA。
- **缺口处理**：现状 #2/#3 未接入 `RecommendationService`（仅接 CAPA `HybridRecommendationPipeline`） → 本子故事验收标 `FAILED`（驱动补齐 FMEA 推荐管道的 RAG/lessons 接入）。

### 限流与缓存
- 限流：per_user + per_fmea（`_check_rate_limit`）。
- 缓存：24h（`RecommendationCache`，cache key 含 scope + include_graph）。

### 审计与落库
- AI 采纳写 `ADOPT_RECOMMENDATION`（含 trigger / source / adopted_text / stage_index）。

## 验收契约（字段级）

| 项 | 定义（跨 PFMEA/DFMEA） |
|---|---|
| 落库实体 | `RecommendationCache`（缓存）、`AuditLog`（采纳） |
| 关键字段 | RecommendResponse.{suggestions, source, graph_match_count, effective_scope}；SuggestionItem.{name, confidence, source, source_document_no} |
| 边类型 | 无新增 |
| AI 触发器 | `failure_mode`、`failure_effect`、`failure_cause`、`prevention_control`、`detection_control` |
| AI 必查来源 | #1+#2+#3+#4（缺任一→FAILED） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | `ADOPT_RECOMMENDATION` |
| E2E seed 前置 | 02.15 编辑器行 + LLM 凭证 |
| 通过条件 | 5 触发器均可用 + AI 查全 4 来源 + 推荐带 source + 来源可追溯 + 采纳留痕 + 限流/缓存生效 |
| 失败条件（FAILED） | AI 未查 #2 RAG 或 #3 lessons；推荐无 source；来源不可追溯；未采纳留痕 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证（AI_REQUIRED=true） |

## 不在本子故事范围

- 编辑器行级 CRUD（见 02.15）。
- 协同编辑 + 冲突（见 02.17）。
- AI 推荐准确率评测（另立）。

## 后续

- 补齐 #2/#3 接入后，本子故事转 PASS；与 02.4/02.5/02.6/02.11/02.12/02.13 向导内 AI 共享同一推荐管道。
