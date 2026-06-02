# 8D D4/D5 全混合管道升级设计文档

**日期**: 2026-06-02  
**状态**: 待实现  
**关联 Roadmap**: Phase 3 — 8D D4/D5 全混合管道升级 (历史 CAPA 匹配 + LLM 增强 + RAG 语义搜索替代关键词子串匹配)

---

## 1. 背景与目标

### 1.1 现有实现

当前 D4/D5 推荐系统（2026-06-02 已完成）包含：

- **D4 根因推荐**：3 策略匹配
  - Strategy A: 关联 FMEA 图遍历（`fmea_node_id` → FailureMode → FailureCause）
  - Strategy B: 跨 FMEA 关键词子串匹配（`kw in name or kw in desc`）
  - Strategy C: 规则引擎回退
- **D5 措施推荐**：
  - 现有控制措施遍历（FailureCause → PreventionControl/DetectionControl，3 路径）
  - 规则引擎通用建议

### 1.2 问题

1. **关键词子串匹配太粗糙**："焊接虚焊"和"焊点不牢"无法匹配，只能匹配字面包含的关键词
2. **无历史经验复用**：已关闭的 CAPA 的 D4/D5 经验无法被新 CAPA 利用
3. **LLM 未接入 CAPA 推荐**：现有 LLM 只用于 FMEA 编辑时的智能推荐

### 1.3 目标

构建**全混合推荐管道**，在保持现有 API 契约**向后兼容**的前提下：

1. **历史 CAPA 匹配**：用语义搜索匹配已关闭 CAPA 的 D2/D4，推荐其 D4/D5 经验
2. **RAG 语义搜索**：用向量语义搜索替代所有关键词子串匹配
3. **LLM 增强**：作为融合层（去重/排序/生成解释）+ 回退生成器（候选不足时补充）

---

## 2. 架构设计

### 2.1 核心抽象

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    HybridRecommendationPipeline                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────┐ │
│  │   Source    │ → │  Retrieve   │ → │    Fuse     │ → │   LLM    │ │
│  │  (多种来源)  │    │  (召回候选)  │    │ (去重/排序)  │    │ (增强)   │ │
│  └─────────────┘    └─────────────┘    └─────────────┘    └──────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心类

```python
class HybridRecommendationPipeline:
    def __init__(self, db, llm_provider, embedding_provider):
        self.d4_sources = [
            FMEAGraphSource(),
            SemanticSearchSource(embedding_provider),      # 替代跨 FMEA 关键词匹配
            HistoricalCAPASource(db, embedding_provider),  # 历史 CAPA D2→D2
            RuleEngineSource(),
        ]
        self.d5_sources = [
            SemanticSearchSource(embedding_provider),      # Stage 1: 找 FailureCause
            HistoricalCAPAMeasureSource(db, embedding_provider),  # 历史 CAPA D4→D4
            RuleEngineMeasureSource(),
        ]
        # D5 Stage 2: 基于 Stage 1 召回的 Cause IDs 扩展 Controls
        # 不是独立 Source，在 pipeline 中顺序执行
        self.d5_control_expander = FMEAControlExpander()
        self.fusion = FusionEngine()
        self.llm_layer = LLMFusionLayer(llm_provider)

    async def recommend(self, context: RecommendationContext) -> RecommendationResult:
        # 1. 召回阶段：
        #    - DB 依赖的 Source（SemanticSearchSource, HistoricalCAPASource）串行执行，
        #      避免共享 AsyncSession 的并发使用问题
        #    - 纯计算 Source（FMEAGraphSource, RuleEngineSource）可与 DB Source 并行
        #    - D5 的 FMEAControlExpander 在 SemanticSearchSource 之后执行（两阶段依赖）
        # 2. FusionEngine 去重排序
        # 3. LLMFusionLayer 增强（只改写 match_reason，保留原 candidate id 和 metadata）
        #    - 阶段 1（融合理由）：FusionEngine 输出 > 0 条候选时触发
        #    - 阶段 2（回退生成）：阶段 1 后有效候选仍 < 3 条时触发
        #    - 两阶段串行执行，但总 LLM 调用受单次/总超时控制
        ...
```

### 2.3 Source 协议

每个 Source 独立实现，只负责**召回候选**：

```python
class RecommendationSource(Protocol):
    name: str
    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        ...
```

### 2.4 数据类型

```python
@dataclass
class RecommendationContext:
    capa_data: dict[str, Any]           # 当前 CAPA 数据 (d2_description, d4_root_cause, ...)
    user_product_lines: list[str] | None # None = admin 全权限
    stage: Literal["d4", "d5"]
    fmea_docs: list[dict] | None = None  # 预加载的同产品线 FMEA 列表
    linked_fmea: dict | None = None      # 关联的 FMEA（如有）

@dataclass
class RecommendationCandidate:
    source: str           # "fmea_graph" | "semantic_search" | "historical_capa" | "rule_engine" | "llm"
    content: str          # 根因文本 / 措施文本
    category: str | None  # D5 用: "预防措施" | "探测措施" | "纠正措施"
    confidence: float     # 0.0 ~ 1.0
    match_reason: str     # 人类可读的理由
    metadata: dict        # {fmea_id, node_id, capa_id, document_no, product_line_code, severity, ...}
```

---

## 3. Source 层详细设计

### 3.1 D4 Sources

| Source | 职责 | 查询文本 | 返回内容 | Confidence 范围 |
|--------|------|----------|----------|----------------|
| `FMEAGraphSource` | 关联 FMEA 结构性图匹配 | `fmea_node_id` | FailureCause 节点 | 0.6（结构性） |
| `SemanticSearchSource` | FMEA 节点语义搜索 | `d2_description` | FailureCause / FailureMode | 0.3~0.8 |
| `HistoricalCAPASource` | 历史 CAPA D2→D2 匹配 | `d2_description` | 历史 CAPA 的 `d4_root_cause` | 0.4~0.8 |
| `RuleEngineSource` | 规则引擎兜底 | `d2_description` | 通用根因建议 | 0.3~0.5 |

**FMEAGraphSource 边界**：只做纯结构解析（`fmea_node_id` → FailureMode → FailureCause），不做任何文本匹配。文本匹配全部交给 SemanticSearchSource。

**HistoricalCAPASource 过滤**：
- `entity_type = "capa"`, `entity_field = "d2_description"`
- JOIN `capa_eightd` 过滤 `status = 'D8_CLOSURE'`
- 产品线优先同产品线，无结果时放宽
- 返回的 `metadata` 包含 `historical_capa_id`, `document_no`, `d5_correction`（给 D5 备用）, `source_updated_at`

### 3.2 D5 Sources

| Source | 职责 | 查询文本 | 返回内容 | Confidence 范围 |
|--------|------|----------|----------|----------------|
| `SemanticSearchSource` | FMEA FailureCause 语义搜索 | `d4_root_cause` | FailureCause 节点 | 0.3~0.8 |
| `FMEAControlExpander` | 基于召回的 Cause 做图遍历扩展 | Stage 1 的 Cause IDs | PreventionControl / DetectionControl | 0.5~0.7 |
| `HistoricalCAPAMeasureSource` | 历史 CAPA D4→D4 匹配 | `d4_root_cause` | 历史 CAPA 的 `d5_correction` | 0.5~0.85 |
| `RuleEngineMeasureSource` | 规则引擎通用建议 | `d2_description` + AP | 通用措施建议 | 0.3~0.5 |

**D5 两阶段召回**：
- **Stage 1**: `SemanticSearchSource` 语义召回匹配的 FailureCause 节点
- **Stage 2**: `FMEAControlExpander` 接收 Stage 1 的 Cause ID 列表，执行 3 路径图遍历找 PreventionControl / DetectionControl
- 两阶段在同个 pipeline 调用内顺序执行，不是独立并行 Source

**HistoricalCAPAMeasureSource 过滤**：
- `entity_type = "capa"`, `entity_field = "d4_root_cause"`
- JOIN `capa_eightd` 过滤 `status = 'D8_CLOSURE'`
- 返回的 `match_reason` 示例："历史 CAPA [8D-2026-001] 相似根因已验证有效"

---

## 4. Fusion 层设计

### 4.1 FusionEngine

```python
class FusionEngine:
    SOURCE_PRIORITY = {
        "fmea_graph": 1.0,       # 结构性关联最可信
        "historical_capa": 0.9,  # 已验证的历史经验
        "semantic_search": 0.7,  # 语义相似度
        "llm": 0.6,              # LLM 生成
        "rule_engine": 0.5,      # 通用规则兜底
    }

    def merge(self, candidates, context):
        # 1. 元数据加权与来源优先级归一化
        for c in candidates:
            priority = self.SOURCE_PRIORITY.get(c.source, 0.5)
            product_bonus = 0.05 if c.metadata.get("product_line_code") == context.capa_data.get("product_line_code") else 0.0
            severity_bonus = 0.03 if c.metadata.get("severity") == context.capa_data.get("severity") else 0.0
            # 公式: 原始 confidence * 来源优先级 + 元数据 bonus
            # bonus 线性累加，避免被优先级乘法削弱
            c.confidence = min(c.confidence * priority + product_bonus + severity_bonus, 0.95)

        # 2. 去重（归一化文本匹配）
        seen = set()
        deduped = []
        for c in sorted(candidates, key=lambda x: x.confidence, reverse=True):
            normalized = "".join(c.content.lower().split())
            if normalized not in seen:
                seen.add(normalized)
                deduped.append(c)

        # 3. 截断
        return deduped[:10]
```

### 4.2 去重策略

- **第一阶段**：文本归一化去重（去除空格标点，小写匹配）
- **未来升级**：可用向量相似度做更精细的语义去重（"焊接虚焊" vs "焊点不牢"）

### 4.3 排序策略

综合排序分 = `confidence * source_priority + metadata_bonus`

- 同产品线 bonus: +0.05
- 同严重度 bonus: +0.03
- 上限: 0.95（保留 0.95~1.0 给人工确认标记）

---

## 5. LLM 层设计

### 5.1 角色：融合层 + 回退生成器

```python
class LLMFusionLayer:
    async def enrich(self, candidates, context):
        if not self.llm:
            return candidates

        # 阶段 1：为候选生成推荐理由
        if candidates:
            try:
                prompt = self._build_fusion_prompt(candidates, context)
                result = await asyncio.wait_for(self.llm.complete(prompt, {}), timeout=settings.LLM_TIMEOUT)
                enriched = self._merge_explanations(candidates, result)
            except Exception as e:
                logger.warning(f"LLM fusion failed: {e}")
                enriched = candidates
        else:
            enriched = []

        # 阶段 2：候选不足时独立生成
        if len(enriched) < 3:
            generated = await self._generate_fallback(context)
            enriched.extend(generated)

        return enriched
```

### 5.2 LLM Prompt 设计

**System Prompt**：
> 你是一名资深质量工程师，擅长 AIAG-VDA 8D 问题解决方法。请根据提供的候选根因/措施列表，识别重复项并合并，按相关性和组织经验价值重新排序，为每条推荐写一句中文推荐理由。
> 
> 规则：
> 1. 你只能改写 `match_reason` 字段，**不允许**生成新的 `content`、`failure_cause_node_id`、`control_node_id` 等主键字段
> 2. 输出必须保留每条候选的原始 `candidate_id`，以便后端合并回原始 metadata
> 3. 不增减候选数量，只优化理由和微调排序
> 4. 输出 JSON 数组

**Input**：当前 CAPA 的 D2/D4 描述 + 候选列表（含 candidate_id、source、content、confidence、metadata）

**Output**：JSON 数组，每条包含 `candidate_id`, `match_reason`

### 5.3 回退生成

当所有 Source 召回的候选不足 3 条时，LLM 直接基于 D2/D4 描述生成新的根因/措施建议。

---

## 6. Embedding 数据流

### 6.1 现有基础设施

CAPA 已经是**字段级 embedding**：

```python
# embedding_sync_worker.py fetch_chunks 中
"capa": ("capa_eightd", "report_id", "product_line_code", "document_no", [
    ("d2_description", "d2_description"),
    ("d4_root_cause", "d4_root_cause"),
    ("d5_correction", "d5_correction"),
    ("d7_prevention", "d7_prevention"),
])
```

每个字段是独立的 `document_embeddings` 记录，`entity_field` 分别为 `"d2_description"`, `"d4_root_cause"`, `"d5_correction"`。

FMEA 也是**节点级 embedding**：`entity_type = "fmea_node"`，每个节点独立 chunk。

### 6.1.1 FMEA Embedding 范围扩展

现有 FMEA 节点 embedding 只拼接 `name + requirement + specification`，**不包含 `description`**。而当前关键词子串匹配会搜索 `description` 字段。

**本次实现内**：扩展 `embedding_sync_worker.py` 的 `fetch_chunks` 中 FMEA 节点的 chunk 内容，加入 `description`：

```python
# 现有
text_parts = [row["name"]]
if row["requirement"]:
    text_parts.append(row["requirement"])
if row["specification"]:
    text_parts.append(row["specification"])

# 扩展后
text_parts = [row["name"]]
if row.get("description"):
    text_parts.append(row["description"])
if row["requirement"]:
    text_parts.append(row["requirement"])
if row["specification"]:
    text_parts.append(row["specification"])
```

> 注意：所有 FMEA 节点的 `entity_field` 保持为 `"name"`（节点级 chunk，不按字段拆分）。语义搜索召回的是节点整体向量，返回后通过 `metadata.node_type` 区分节点类型。

### 6.2 CAPA Embedding 更新触发

**问题**：`d4_root_cause` 和 `d5_correction` 是后续步骤填写的，create 时为空。

**解决方案**：在 `capa_service.update_capa()` 中，当更新的字段**实际内容发生变化**时，重新触发同步：

```python
EMBEDDING_FIELDS = {"d2_description", "d4_root_cause", "d5_correction", "d7_prevention"}

async def update_capa(db, capa, update_data, user_id):
    # ... 现有更新逻辑 ...
    changed = {
        k for k, v in update_data.items()
        if k in EMBEDDING_FIELDS and getattr(capa, k) != v
    }
    if changed:
        from app.services.embedding_outbox import enqueue_embedding
        await enqueue_embedding(db, "capa", capa.report_id, capa.product_line_code)
```

### 6.3 历史 CAPA 语义搜索查询

```sql
SELECT de.id, de.entity_id, de.chunk_text, de.entity_field,
       1 - (de.embedding <=> :query_vector) AS similarity,
       capa.document_no, capa.severity, capa.updated_at AS source_updated_at
FROM document_embeddings de
JOIN capa_eightd capa ON de.entity_id = capa.report_id
WHERE de.entity_type = 'capa'
  AND de.entity_field = :target_field   -- 'd2_description' 或 'd4_root_cause'
  AND capa.status = 'D8_CLOSURE'
  AND (:product_line_codes IS NULL OR de.product_line_code = ANY(:product_line_codes))
ORDER BY de.embedding <=> :query_vector
LIMIT :limit
```

> **注意**：CAPA 模型没有 `closed_at` 字段，返回 `updated_at AS source_updated_at`（进入 D8_CLOSURE 后若不再编辑，updated_at 即关闭时间）。`product_line_codes` 为数组类型，使用 `= ANY()` 支持多产品线权限过滤。

---

## 7. API 与前端变更

### 7.1 API 变更

**零新端点，向后兼容的 Schema 扩展**：

```
GET /api/capa/{report_id}/d4-fmea-recommendations  → D4RecommendationResponse
GET /api/capa/{report_id}/d5-fmea-recommendations  → D5RecommendationResponse
```

内部实现从直接调用 `get_d4_recommendations()` / `get_d5_recommendations()` 改为调用 `HybridRecommendationPipeline.recommend()`。

**Schema 扩展（向后兼容，新增可选字段）**：
- `D4Recommendation` 新增：`source_capa_id`, `source_capa_document_no`, `source_product_line_code`（历史 CAPA 来源标识）
- `D5GeneralSuggestion` 新增：`match_source`, `source_capa_id`, `source_capa_document_no`（历史 CAPA 措施来源标识）
- 现有字段全部保留，前端不读取新字段时不影响功能

### 7.2 前端变更

**最小变更**：

- `match_reason` 字段内容会更丰富（LLM 生成的推荐理由），前端可直接展示
- 历史 CAPA 候选可展示 `document_no` 链接（从新增的 `source_capa_document_no` 读取）
- 无新增组件需求，现有推荐面板直接复用

---

## 8. 错误处理策略

| 场景 | 行为 |
|------|------|
| SemanticSearchSource 失败（pgvector 不可用） | 记录 warning，继续执行其他 Source |
| HistoricalCAPASource 失败 | 记录 warning，降级为无历史 CAPA 推荐 |
| LLMFusionLayer 失败 | 记录 warning，返回未 LLM 增强的候选 |
| 所有非规则 Source 都失败 | 单独调用 RuleEngine fallback |
| 无 embedding provider | 语义搜索 Source 返回空，依赖 FMEAGraphSource + RuleEngine |
| 单 Source 超时 | 超时 Source 返回空，不影响其他 Source |

---

## 9. 测试策略

### 9.1 单元测试

每个 Source 独立测试（Mock DB + Mock embedding provider）：
- `FMEAGraphSource`：关联 FMEA 有/无 `fmea_node_id`、跨 FMEA 场景
- `SemanticSearchSource`：Mock embedding 返回、空结果、异常降级
- `HistoricalCAPASource` / `HistoricalCAPAMeasureSource`：D8_CLOSURE 过滤、`source_updated_at` 返回、跨产品线放宽
- `FusionEngine`：去重逻辑（相同文本不同来源）、排序公式验证、空输入、单 Source
- `LLMFusionLayer`：LLM 可用/不可用、候选不足回退、超时降级

### 9.2 集成测试

- **Pipeline 完整链路**：D4（D2 → 多 Source 召回 → Fusion → LLM）和 D5（D4 → Stage1/Stage2 → Fusion → LLM）
- **Schema 扩展验证**：
  - `D4Recommendation` 新增字段 `source_capa_id`、`source_capa_document_no` 正确填充
  - `D5GeneralSuggestion` 新增字段 `match_source`、`source_capa_id` 正确填充
- **历史 CAPA D5 映射**：验证 `d5_correction` 映射到 `D5GeneralSuggestion`（不是 `D5ExistingControl`），`category = "纠正措施"`

### 9.3 端到端测试

- 完整 pipeline 输入输出，验证 API 响应格式向后兼容
- 现有前端不读取新字段时功能不受影响

### 9.4 回归测试

- 验证 `D4RecommendationResponse` / `D5RecommendationResponse` 现有字段不变
- **更新现有测试断言**：`D5GeneralSuggestion.category` 允许 `"纠正措施"`（此前仅允许 `"预防措施"`、`"探测措施"`）
- 验证 `match_source` 保留旧值 `"linked"`、`"keyword"`、`"rule"`，新值 `"historical_capa"`、`"semantic_search"`、`"fmea_graph"`、`"llm"` 正确返回
- 验证无 embedding provider 时系统不崩溃（降级为 FMEAGraphSource + RuleEngine）

---

## 10. 实现范围与边界

### 10.1 在本次实现内

- [ ] `HybridRecommendationPipeline` 核心管道类
- [ ] 7 个 Source/组件 实现（FMEAGraphSource, SemanticSearchSource, HistoricalCAPASource, HistoricalCAPAMeasureSource, RuleEngineSource, RuleEngineMeasureSource, FMEAControlExpander）
- [ ] `FusionEngine` 去重排序
- [ ] `LLMFusionLayer` 融合解释 + 回退生成
- [ ] `RecommendationContext` / `RecommendationCandidate` 数据模型
- [ ] CAPA update 时触发 embedding 重新同步
- [ ] API 路由内部实现替换
- [ ] 单元测试

### 10.2 明确不在本次实现内

- 向量相似度去重（第一阶段用文本归一化去重，后续迭代）
- 前端展示优化（历史 CAPA 链接等，可后续迭代）
- 新 API 端点
- 异步推荐 Worker（保持同步 API）
- 推荐结果缓存（可后续添加）

---

## 11. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| pgvector 查询性能差（历史 CAPA 数据量大） | 先过滤 `status = 'D8_CLOSURE'` 减少数据量；加 `LIMIT`；后续可加 HNSW 索引 |
| CAPA embedding 未及时更新 | update_capa 中检测字段变化并重新触发 enqueue_embedding |
| LLM 调用慢/失败 | 超时控制（`asyncio.wait_for`）；失败时降级为未增强候选 |
| 历史 CAPA 推荐传播错误经验 | 只复用 `D8_CLOSURE`；confidence 上限 0.8/0.85；LLM 融合层过滤低质量候选 |
| LLM 同步调用延迟高 | 单次 LLM timeout ≤ 2.0s；限制输出 token（≤ 200）；总 LLM 调用时间受控（阶段 1 成功 + 候选不足时进入阶段 2，但总时间不超过 4.0s）；后续可加基于 `report_id + stage + content_hash` 的短期缓存 |
| 重复触发 embedding 同步 | update_capa 中增加值比对，仅字段内容实际变化时才 enqueue |

---

## 12. 附录：Schema 兼容性

### 向后兼容的 Schema 扩展

```python
# D4Recommendation (扩展后)
class D4Recommendation(BaseModel):
    # --- 现有字段 ---
    failure_cause_node_id: str | None = None
    failure_cause_name: str
    failure_cause_desc: str | None = None
    failure_mode_node_id: str | None = None
    failure_mode_name: str | None = None
    fmea_document_no: str | None = None
    fmea_id: str | None = None
    match_source: str      # "linked" | "keyword" | "fmea_graph" | "semantic_search" | "historical_capa" | "rule" | "llm"
    match_reason: str
    related_d2_keywords: list[str] = []
    confidence: float = 0.5
    # --- 新增字段（可选，历史 CAPA 来源标识） ---
    source_capa_id: str | None = None           # 历史 CAPA 的 report_id
    source_capa_document_no: str | None = None  # 历史 CAPA 的 document_no
    source_product_line_code: str | None = None # 历史 CAPA 的产品线

# D5ExistingControl (现有，不变)
class D5ExistingControl(BaseModel):
    failure_mode_node_id: str | None = None
    failure_mode_name: str | None = None
    failure_cause_node_id: str | None = None
    failure_cause_name: str | None = None
    control_node_id: str
    control_name: str
    control_type: str      # "prevention" | "detection"
    match_source: str
    match_reason: str
    fmea_id: str | None = None
    fmea_document_no: str | None = None

# D5GeneralSuggestion (扩展后)
class D5GeneralSuggestion(BaseModel):
    # --- 现有字段 ---
    content: str
    category: str          # "预防措施" | "探测措施" | "纠正措施"
    basis: str
    confidence: float
    # --- 新增字段（可选，历史 CAPA 来源标识） ---
    match_source: str | None = None             # 来源标识
    source_capa_id: str | None = None           # 历史 CAPA 的 report_id
    source_capa_document_no: str | None = None  # 历史 CAPA 的 document_no
```

### 历史 CAPA D5 措施的映射

历史 CAPA 的 `d5_correction` **不**映射到 `D5ExistingControl`（没有 control_node_id），而是映射到 `D5GeneralSuggestion`：
- `content` = 历史 CAPA 的 `d5_correction`
- `category` = `"纠正措施"`（历史 CAPA 已验证的纠正措施）
- `match_source` = `"historical_capa"`
- `match_reason` = "历史 CAPA [document_no] 相似根因已验证有效"

### match_source 枚举值扩展

| 来源 | match_source 值 |
|------|----------------|
| 关联 FMEA 图遍历 | `fmea_graph` |
| FMEA 语义搜索 | `semantic_search` |
| 历史 CAPA | `historical_capa` |
| 规则引擎 | `rule` |
| LLM 生成 | `llm` |
