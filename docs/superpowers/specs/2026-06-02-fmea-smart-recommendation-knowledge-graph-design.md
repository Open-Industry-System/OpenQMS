# FMEA 智能推荐 — 知识图谱相似度匹配 + 来源文档标注 设计文档

**日期:** 2026-06-02
**范围:** 在现有推荐系统（规则引擎 + LLM）基础上接入知识图谱作为独立推荐源
**基础版本:** 规则引擎 + LLM 版已完成（`RecommendationService` + `SmartSuggestionDropdown`）

---

## 1. 设计目标

- 将知识图谱从历史 FMEA 文档中挖掘的相似节点作为独立推荐源接入现有推荐管道
- 推荐结果可跨产品线检索，支持全局经验复用
- 每条推荐项明确标注来源文档、产品线、节点类型、相似度分数和匹配原因
- LLM 降级为补充层：规则 + 图谱结果充足时不调用 LLM；不足时 LLM 使用图谱结果作为上下文增强生成

---

## 2. 核心决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 相似度匹配范围 | 默认跨产品线，可选仅当前产品线 | 全局经验复用是核心价值；保留隔离开关满足合规场景 |
| 匹配算法（第一版）| 关键词子串 + 归一化文本相似度 + 节点类型过滤 | 最小可行，不引入 embedding 依赖 |
| 推荐管道 | 缓存 → 并行[规则引擎, 图谱相似度] → 合并去重排序 → 不足时 LLM → 缓存 | 图谱是可审计的独立来源，不与规则引擎耦合 |
| 来源标注 | 每项推荐显示来源文档编号（可点击跳转） | 质量管理场景可追溯性优先于界面极简 |
| LLM 角色 | 补充层：结果不足/过于 generic 时调用；可使用图谱结果作为上下文 | 避免 LLM 幻觉替代可审计的图谱匹配 |

---

## 3. 算法演进路线

```
第一版（本期）: 关键词子串匹配 + 归一化文本相似度（Jaccard/编辑距离）+ 节点类型过滤
第二版（后续）: 接入 pgvector embedding 语义相似度
第三版（远期）: 图结构相似度（同失效模式下的原因/控制措施路径相似）
```

**第一版相似度计算：**

```python
def compute_similarity(query: str, candidate: str) -> float:
    """归一化文本相似度：Jaccard 系数（基于字符二元组）。"""
    def _bigrams(s: str) -> set[str]:
        s = s.lower().strip()
        return {s[i:i+2] for i in range(len(s) - 1)} if len(s) >= 2 else set()
    
    a, b = _bigrams(query), _bigrams(candidate)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
```

**匹配原因标注：**
- `keyword_match` — 关键词子串命中
- `text_similarity` — 归一化文本相似度超过阈值
- `neighbor_match` — （预留）图谱邻域相似

---

## 4. API 设计

### 4.1 扩展现有推荐端点

`POST /api/fmea/{fmea_id}/recommend` 行为不变，内部管道增强。新增请求字段：

```python
class RecommendRequest(BaseModel):
    trigger_type: Literal["failure_mode", "failure_effect", "failure_cause", "measure", "optimization"]
    context: dict = Field(default_factory=dict)
    scope: Literal["global", "current_product_line"] = "global"  # 新增：匹配范围
    include_graph: bool = True  # 新增：是否包含图谱推荐
```

### 4.2 响应 Schema 扩展

```python
class SuggestionItem(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["rule", "graph", "llm"] = "rule"
    explanation: str = ""
    # 新增：来源文档标注（仅 source == "graph" 时填充）
    source_document_no: str | None = None      # 如 "PFMEA-2026-001"
    source_product_line: str | None = None     # 如 "DC-DC-100"
    source_node_type: str | None = None        # 如 "FailureMode"
    source_node_id: str | None = None          # 节点 ID
    similarity_score: float | None = None      # 0.0 ~ 1.0
    match_reason: str | None = None            # 如 "text_similarity"


class RecommendResponse(BaseModel):
    suggestions: list[SuggestionItem]
    source: Literal["rule", "graph", "hybrid", "rule_fallback", "graph_enriched"]
    cached: bool = False
    llm_available: bool = False
    graph_match_count: int = 0  # 新增：图谱匹配命中数
```

### 4.3 新增独立端点（用于调试和预览）

```http
POST /api/graph/similar-nodes
Authorization: Bearer <token>
Content-Type: application/json

{
  "node_type": "FailureMode",
  "query_text": "焊接不良",
  "scope": "global",
  "limit": 10,
  "min_similarity": 0.3
}
```

**响应：**

```json
{
  "matches": [
    {
      "node_id": "fm_001",
      "name": "焊接虚焊",
      "node_type": "FailureMode",
      "document_no": "PFMEA-2026-001",
      "product_line_code": "DC-DC-100",
      "similarity_score": 0.72,
      "match_reason": "text_similarity",
      "fmea_id": "uuid"
    }
  ],
  "total": 1
}
```

---

## 5. Repository 层扩展

### 5.1 抽象接口新增

在 `FMEAGraphRepository` 中添加：

```python
@abstractmethod
async def find_similar_nodes_advanced(
    self,
    node_type: str,
    query_text: str,
    scope: Literal["global", "current_product_line"],
    product_line_code: str | None,
    limit: int = 10,
    min_similarity: float = 0.3,
) -> list[dict]:
    """跨 FMEA 相似节点搜索（增强版）。

    返回项包含：
    - node_id, name, type, fmea_id, document_no
    - product_line_code
    - similarity_score (0.0 ~ 1.0)
    - match_reason
    """
```

### 5.2 JSONB 实现

```python
async def find_similar_nodes_advanced(
    self, node_type, query_text, scope, product_line_code, limit=10, min_similarity=0.3
):
    query = select(FMEADocument)
    if scope == "current_product_line" and product_line_code:
        query = query.where(FMEADocument.product_line_code == product_line_code)
    result = await self._db.execute(query)
    fmeas = result.scalars().all()

    matches = []
    for fmea in fmeas:
        if not fmea.graph_data:
            continue
        for node in fmea.graph_data.get("nodes", []):
            if node.get("type") != node_type:
                continue
            node_name = node.get("name") or ""
            score = self._compute_similarity(query_text, node_name)
            if score >= min_similarity:
                matches.append({
                    "node_id": node.get("id", ""),
                    "name": node_name,
                    "type": node_type,
                    "fmea_id": str(fmea.fmea_id),
                    "document_no": fmea.document_no,
                    "product_line_code": fmea.product_line_code,
                    "similarity_score": round(score, 3),
                    "match_reason": "text_similarity",
                })

    matches.sort(key=lambda x: x["similarity_score"], reverse=True)
    return matches[:limit]

@staticmethod
def _compute_similarity(a: str, b: str) -> float:
    def _bigrams(s: str) -> set[str]:
        s = s.lower().strip()
        return {s[i:i+2] for i in range(len(s) - 1)} if len(s) >= 2 else set()
    set_a, set_b = _bigrams(a), _bigrams(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)
```

### 5.3 Neo4j 实现

与 JSONB 实现逻辑一致，使用 Cypher 查询所有匹配节点后在 Python 中计算相似度：

```python
async def find_similar_nodes_advanced(...):
    async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
        if scope == "current_product_line" and product_line_code:
            result = await session.run(
                "MATCH (n:GraphNode {type: $node_type}) WHERE n.product_line_code = $pl "
                "MATCH (d:FMEDocument) WHERE d.fmea_id = n.fmea_id "
                "RETURN n.node_id AS node_id, n.name AS name, n.type AS type, "
                "n.fmea_id AS fmea_id, n.product_line_code AS product_line_code, "
                "d.document_no AS document_no",
                node_type=node_type, pl=product_line_code,
            )
        else:
            result = await session.run(
                "MATCH (n:GraphNode {type: $node_type}) "
                "MATCH (d:FMEDocument) WHERE d.fmea_id = n.fmea_id "
                "RETURN n.node_id AS node_id, n.name AS name, n.type AS type, "
                "n.fmea_id AS fmea_id, n.product_line_code AS product_line_code, "
                "d.document_no AS document_no",
                node_type=node_type,
            )
        records = await result.data()
        # Python 中计算相似度并过滤
        ...
```

---

## 6. 推荐服务层改造

### 6.1 新管道流程

```
┌─────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Cache  │────▶│ Parallel Query   │────▶│ Merge & Deduplicate│
│  Check  │     │ [RuleEngine]     │     │ Sort by confidence │
└─────────┘     │ [GraphRepo]      │     └────────┬────────┘
                └──────────────────┘              │
                                                  ▼
                              ┌─────────────────────────────────┐
                              │ Result count >= threshold?      │
                              │ OR quality is specific?         │
                              └────────┬─────────────┬──────────┘
                                       │ YES         │ NO
                                       ▼             ▼
                              ┌────────────┐  ┌──────────────┐
                              │ Return     │  │ LLM with     │
                              │ result     │  │ graph context│
                              └────────────┘  └──────┬───────┘
                                                     │
                                                     ▼
                                              ┌────────────┐
                                              │ Cache &    │
                                              │ Return     │
                                              └────────────┘
```

### 6.2 `RecommendationService.recommend()` 改造

```python
async def recommend(self, fmea_id: uuid.UUID, request: RecommendRequest) -> RecommendResponse:
    fmea = await self._get_fmea_or_404(fmea_id)
    scope = getattr(request, "scope", "global")
    include_graph = getattr(request, "include_graph", True)

    # 1. Check cache (key now includes scope and include_graph)
    context_hash = self._compute_context_hash({
        **request.context,
        "scope": scope,
        "include_graph": include_graph,
    })
    cache_result = await self._get_cached(fmea_id, request.trigger_type, context_hash)
    if cache_result:
        cached_response, cached_with_llm = cache_result
        if self.llm is not None and not cached_with_llm:
            pass  # fall through to re-evaluate with LLM
        else:
            return cached_response

    # 2. Parallel: Rule engine + Graph similarity
    rule_result = self.rules.evaluate(request.trigger_type, request.context)
    
    graph_suggestions: list[SuggestionItem] = []
    if include_graph:
        graph_matches = await self._query_graph_similarity(
            fmea, request.trigger_type, request.context, scope
        )
        graph_suggestions = self._graph_matches_to_suggestions(graph_matches)

    # 3. Merge & deduplicate
    all_suggestions = self._merge_and_deduplicate(
        rule_result.suggestions, graph_suggestions
    )

    # 4. Determine if LLM is needed
    has_specific = any(s.confidence >= 0.6 for s in all_suggestions)
    need_llm = (
        self.llm is not None
        and not has_specific
        and len(all_suggestions) < 3
    )

    if need_llm:
        try:
            llm_context = await self._assemble_context(fmea, request)
            # 将图谱匹配结果作为上下文注入 LLM
            if graph_suggestions:
                llm_context["similar_history"] = [
                    {"name": s.name, "from": s.source_document_no}
                    for s in graph_suggestions[:5]
                ]
            prompt = self._build_prompt(request.trigger_type, llm_context)
            llm_result = await asyncio.wait_for(
                self.llm.complete(prompt, {}),
                timeout=settings.LLM_TIMEOUT,
            )
            validated = SuggestionList.model_validate(llm_result)
            llm_items = [
                SuggestionItem(
                    name=s.name,
                    confidence=s.confidence,
                    source="llm",
                    explanation=s.explanation,
                )
                for s in validated.suggestions
            ]
            all_suggestions = self._merge_and_deduplicate(all_suggestions, llm_items)
            source = "graph_enriched" if graph_suggestions else "hybrid"
        except Exception as e:
            source = "rule_fallback" if not graph_suggestions else "graph"
            logger.warning("LLM failed, using rule+graph results: %s", e)
    else:
        source = "graph" if graph_suggestions else "rule"

    response = RecommendResponse(
        suggestions=all_suggestions[:10],
        source=source,
        cached=False,
        llm_available=self.llm is not None,
        graph_match_count=len(graph_suggestions),
    )

    if source != "rule_fallback":
        await self._cache_result(fmea_id, request.trigger_type, context_hash, fmea, response)
    return response
```

### 6.3 去重逻辑

```python
def _merge_and_deduplicate(
    rule_items: list[RuleSuggestion],
    graph_items: list[SuggestionItem],
) -> list[SuggestionItem]:
    """合并规则引擎和图谱结果，按名称去重，保留最高置信度。
    
    去重策略：
    - 同名建议保留 confidence 更高的版本
    - graph 来源优先于 rule（因为 graph 有真实历史依据）
    - 保留 source_document_no 等来源信息
    """
    seen: dict[str, SuggestionItem] = {}
    
    for item in rule_items:
        key = item.name.strip()
        seen[key] = SuggestionItem(
            name=item.name,
            confidence=item.confidence,
            source="rule",
            explanation=item.explanation,
        )
    
    for item in graph_items:
        key = item.name.strip()
        existing = seen.get(key)
        if existing is None or item.confidence > existing.confidence:
            seen[key] = item
        # 如果 rule 已存在同名但 graph 有更高 confidence，用 graph 覆盖
        # 如果 confidence 相同，优先保留 graph（有来源可追溯）
    
    return sorted(seen.values(), key=lambda x: x.confidence, reverse=True)
```

---

## 7. 前端改造

### 7.1 `SmartSuggestionDropdown` 展示增强

每个建议项增加来源标注：

```tsx
// 来源标注组件
function SourceTag({ item }: { item: SuggestionItem }) {
  if (item.source === "graph" && item.source_document_no) {
    return (
      <span className="source-tag">
        来自 {item.source_document_no}
        {item.source_product_line && ` · ${item.source_product_line}`}
        {item.similarity_score !== undefined && ` · 相似度 ${(item.similarity_score * 100).toFixed(0)}%`}
      </span>
    );
  }
  if (item.source === "rule") {
    return <span className="source-tag rule">规则引擎</span>;
  }
  if (item.source === "llm") {
    return <span className="source-tag llm">AI 生成</span>;
  }
  return null;
}
```

### 7.2 点击跳转

来源文档编号可点击，跳转至对应 FMEA 编辑器：

```tsx
<a href={`/fmea/${item.fmea_id}`} target="_blank" rel="noopener">
  {item.source_document_no}
</a>
```

> 远期可扩展为：跳转后高亮对应节点（通过 URL query param `?highlight_node_id=xxx`）。

### 7.3 范围切换控件

在 FMEA 编辑器中添加切换开关（默认全局）：

```tsx
<Radio.Group value={scope} onChange={setScope}>
  <Radio.Button value="global">全局经验</Radio.Button>
  <Radio.Button value="current_product_line">仅当前产品线</Radio.Button>
</Radio.Group>
```

该 `scope` 值随推荐请求一同发送。

---

## 8. 缓存策略调整

缓存 key 需要包含 `scope` 和 `include_graph`，否则全局/隔离切换会导致缓存污染：

```python
def _compute_context_hash(self, context: dict) -> str:
    raw = json.dumps(context, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()
```

缓存表 `recommendation_cache` 已有 `context_hash` 字段，无需迁移。新请求会将 `scope` 和 `include_graph` 混入 `context` 中计算 hash。

---

## 9. 性能考量

| 场景 | 估算 | 对策 |
|------|------|------|
| 图谱匹配遍历全量 FMEA | 假设 100 文档 × 平均 50 节点 = 5000 节点 | Python 内存遍历，首版可接受；后续可引入 SQL JSONB 过滤或 Neo4j 索引 |
| 并行查询 | 规则引擎(~1ms) + 图谱查询(~50ms) 并行 | 使用 `asyncio.gather` 并行执行 |
| LLM 调用 | 仅结果不足时触发 | 减少 LLM 调用次数，降低成本和延迟 |
| 缓存命中率 | 相同输入 + scope 组合 | context_hash 包含 scope，避免污染 |

---

## 10. 错误处理

| 场景 | 行为 |
|------|------|
| 图谱查询失败 | 降级为仅规则引擎结果，记录 warning |
| Neo4j 未配置 | JSONBRepository fallback 自动生效 |
| 无匹配结果 | 返回空列表，触发 LLM（如果可用） |
| LLM 失败 | 返回规则 + 图谱结果（如有），source 标记为对应值 |
| 用户无跨产品线权限 | 后端强制 scope = "current_product_line" |

---

## 11. 验收标准

- [ ] 知识图谱相似度匹配作为独立推荐源接入推荐管道
- [ ] 默认跨产品线匹配，支持切换仅当前产品线
- [ ] 推荐项显示来源文档编号、产品线、节点类型、相似度分数
- [ ] 来源文档编号可点击跳转至对应 FMEA
- [ ] 规则引擎 + 图谱结果充足时不调用 LLM
- [ ] LLM 可将图谱匹配结果作为上下文增强生成
- [ ] 去重逻辑正确：同名建议保留最高置信度版本
- [ ] 缓存 key 包含 scope，避免全局/隔离切换污染
- [ ] Neo4j 和 JSONB 双实现均支持相似度匹配
- [ ] 构建和测试无错误
