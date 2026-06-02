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
| 匹配算法（第一版）| 关键词子串命中 boost + Jaccard 二元组相似度 + 节点类型过滤 | 最小可行，不引入 embedding 依赖 |
| 推荐管道 | 缓存 → 顺序查询[规则引擎, 图谱相似度] → 合并去重排序 → 不足时 LLM → 缓存 | 规则引擎是同步 CPU 运算（~1ms），与 I/O 并行收益极低，顺序执行避免调度开销 |
| 来源标注 | 每项推荐显示来源文档编号（可点击跳转） | 质量管理场景可追溯性优先于界面极简 |
| LLM 角色 | 补充层：结果不足/过于 generic 时调用；可使用图谱结果作为上下文 | 避免 LLM 幻觉替代可审计的图谱匹配 |

---

## 3. 算法演进路线

```
第一版（本期）: 子串命中 boost + Jaccard 二元组相似度 + 节点类型过滤
第二版（后续）: 接入 pgvector embedding 语义相似度
第三版（远期）: 图结构相似度（同失效模式下的原因/控制措施路径相似）
```

**第一版相似度计算：**

```python
def compute_similarity(query: str, candidate: str) -> float:
    """混合相似度：子串命中给基础分，否则走 bigram Jaccard。
    短查询（如中文 2 字词）在 Jaccard 中容易因分母过大被低估，子串 boost 可保真。
    """
    def _bigrams(s: str) -> set[str]:
        s = s.lower().strip()
        return {s[i:i+2] for i in range(len(s) - 1)} if len(s) >= 2 else set()
    
    q, c = query.lower().strip(), candidate.lower().strip()
    # 子串命中直接给基础分
    if q in c or c in q:
        return 0.75
    
    a, b = _bigrams(query), _bigrams(candidate)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
```

**匹配原因标注：**
- `substring_match` — 关键词子串命中（相似度固定 0.75）
- `text_similarity` — bigram Jaccard 相似度超过阈值
- `neighbor_match` — （预留）图谱邻域相似

---

## 4. 权限与数据隔离

### 4.1 权限模型

新增权限枚举值：`KNOWLEDGE_GRAPH_GLOBAL_READ`（全局知识库读取）。

绑定至角色：
- **admin / manager** — 拥有 `KNOWLEDGE_GRAPH_GLOBAL_READ`
- **quality_engineer / viewer** — 不拥有该权限

权限检查由后端统一执行，前端通过用户角色预渲染切换控件状态。

### 4.2 scope 强制降级规则

| 用户权限 | 请求 scope | 实际生效 scope | 返回数据 |
|---------|-----------|---------------|---------|
| 有 `KNOWLEDGE_GRAPH_GLOBAL_READ` | `global` | `global` | 完整来源信息 |
| 有 `KNOWLEDGE_GRAPH_GLOBAL_READ` | `current_product_line` | `current_product_line` | 完整来源信息 |
| 无 `KNOWLEDGE_GRAPH_GLOBAL_READ` | `global` | **强制降级为 `current_product_line`** | 完整来源信息 |
| 无 `KNOWLEDGE_GRAPH_GLOBAL_READ` | `current_product_line` | `current_product_line` | 完整来源信息 |

**实现：**后端在 `recommend()` 入口处检查权限，无权限则覆盖 `request.scope = "current_product_line"`。

### 4.3 跨产品线数据隔离

**数据访问原则：**
- 有 `KNOWLEDGE_GRAPH_GLOBAL_READ` 权限的用户：可查看完整跨产品线推荐内容（名称不脱敏），因为权限本身已授权跨产品线数据访问
- 无全局权限的用户：scope 被强制降级为 `current_product_line`，不会看到跨产品线节点

**防御性脱敏：**
如果无权限用户通过异常路径获取到跨产品线节点（如 API 直接调用），在 API 响应层对跨产品线节点名称脱敏：

```python
from app.api.graph import mask_name

# 仅在 API 层做防御性脱敏，不污染 service 层的 suggestion.name
if not has_global_permission and match_product_line_code != current_fmea_product_line:
    display_name = mask_name(match_name)
else:
    display_name = match_name
```

**关键决策：** 不在 `_graph_matches_to_suggestions()` 中对 `SuggestionItem.name` 脱敏。脱敏只作为 API 层的防御性措施，不影响有权限用户的完整推荐体验。

### 4.4 FMEA 状态过滤

图谱相似度匹配只从**已批准**的 FMEA 文档中检索：

```python
query = select(FMEADocument).where(FMEADocument.status == "approved")
```

> 注：若后续增加 `published` 状态，扩展为 `status.in_(("approved", "published"))`。草稿、评审中、返工、归档文档不进入推荐源。

---

## 5. API 设计

### 5.1 扩展现有推荐端点

`POST /api/fmea/{fmea_id}/recommend` 行为不变，内部管道增强。新增请求字段：

```python
class RecommendRequest(BaseModel):
    trigger_type: Literal["failure_mode", "failure_effect", "failure_cause", "measure", "optimization"]
    context: dict = Field(default_factory=dict)
    scope: Literal["global", "current_product_line"] = "global"
    include_graph: bool = True
```

### 5.2 响应 Schema 扩展

```python
class SuggestionItem(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["rule", "graph", "llm"] = "rule"
    explanation: str = ""
    # 来源文档标注（仅 source == "graph" 时填充）
    source_fmea_id: str | None = None          # 来源 FMEA UUID
    source_document_no: str | None = None      # 如 "PFMEA-2026-001"
    source_product_line_code: str | None = None  # 如 "DC-DC-100"
    source_product_line_name: str | None = None  # 如 "DC-DC 电源模块"
    source_node_type: str | None = None        # 如 "FailureMode"
    source_node_id: str | None = None          # 节点 ID
    similarity_score: float | None = None      # 0.0 ~ 1.0
    match_reason: str | None = None            # 如 "substring_match" / "text_similarity"


class RecommendResponse(BaseModel):
    suggestions: list[SuggestionItem]
    source: Literal["rule", "graph", "hybrid", "rule_fallback", "graph_enriched"]
    cached: bool = False
    llm_available: bool = False
    graph_match_count: int = 0
    effective_scope: Literal["global", "current_product_line"] = "global"  # 新增：实际生效范围
```

### 5.3 新增独立端点（用于调试和预览）

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

**权限降级：**与推荐端点同一语义。无 `KNOWLEDGE_GRAPH_GLOBAL_READ` 权限时，`scope="global"` 强制降级为 `"current_product_line"`，响应返回 `effective_scope` 告知前端实际生效范围。

**响应：**

```json
{
  "matches": [
    {
      "node_id": "fm_001",
      "name": "焊接虚焊",
      "node_type": "FailureMode",
      "fmea_id": "uuid",
      "document_no": "PFMEA-2026-001",
      "product_line_code": "DC-DC-100",
      "product_line_name": "DC-DC 电源模块",
      "similarity_score": 0.75,
      "match_reason": "substring_match"
    }
  ],
  "total": 1,
  "effective_scope": "global"
}
```

---

## 6. Repository 层扩展

### 6.1 抽象接口新增

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

### 6.2 JSONB 实现

```python
async def find_similar_nodes_advanced(
    self, node_type, query_text, scope, product_line_code, limit=10, min_similarity=0.3
):
    # 基础过滤：已批准 + graph_data 非空 + 产品线（如指定）
    query = select(FMEADocument).where(
        FMEADocument.status == "approved",
        FMEADocument.graph_data.isnot(None),
    )
    if scope == "current_product_line" and product_line_code:
        query = query.where(FMEADocument.product_line_code == product_line_code)
    result = await self._db.execute(query)
    fmeas = result.scalars().all()

    # 加载产品线名称映射（防御性，避免 N+1）
    pl_codes = {fmea.product_line_code for fmea in fmeas if fmea.product_line_code}
    pl_name_map = await self._load_product_line_names(pl_codes)

    matches = []
    for fmea in fmeas:
        for node in fmea.graph_data.get("nodes", []):
            if node.get("type") != node_type:
                continue
            node_name = node.get("name") or ""
            score, reason = compute_similarity(query_text, node_name)
            if score >= min_similarity:
                pl_code = fmea.product_line_code
                matches.append({
                    "node_id": node.get("id", ""),
                    "name": node_name,
                    "type": node_type,
                    "fmea_id": str(fmea.fmea_id),
                    "document_no": fmea.document_no,
                    "product_line_code": pl_code,
                    "product_line_name": pl_name_map.get(pl_code, pl_code),
                    "similarity_score": round(score, 3),
                    "match_reason": reason,
                })

    matches.sort(key=lambda x: x["similarity_score"], reverse=True)
    return matches[:limit]

async def _load_product_line_names(self, codes: set[str]) -> dict[str, str]:
    """批量加载产品线名称，避免 N+1。"""
    if not codes:
        return {}
    from app.models.product_line import ProductLine
    from sqlalchemy import select as sa_select
    result = await self._db.execute(
        sa_select(ProductLine.code, ProductLine.name).where(ProductLine.code.in_(codes))
    )
    return {row.code: row.name for row in result.all()}
```

**共享相似度函数（提取至独立模块）：**

```python
# backend/app/utils/similarity.py

def compute_similarity(query: str, candidate: str) -> tuple[float, str]:
    """混合相似度：子串命中给基础分，否则走 bigram Jaccard。
    返回 (score, match_reason)。
    """
    q, c = query.lower().strip(), candidate.lower().strip()
    if not q or not c:
        return 0.0, "text_similarity"
    if q in c or c in q:
        return 0.75, "substring_match"

    def _bigrams(s: str) -> set[str]:
        s = s.lower().strip()
        return {s[i:i+2] for i in range(len(s) - 1)} if len(s) >= 2 else set()
    
    a, b = _bigrams(query), _bigrams(candidate)
    if not a or not b:
        return 0.0, "text_similarity"
    score = len(a & b) / len(a | b)
    return score, "text_similarity"
```

### 6.3 Neo4j 实现

```python
async def find_similar_nodes_advanced(...):
    from app.utils.similarity import compute_similarity

    async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
        # 基础过滤：状态 + 节点类型 + 产品线（如指定）
        cypher = """
        MATCH (d:FMEDocument)-[:HAS_NODE]->(n:GraphNode {type: $node_type})
        WHERE d.status = 'approved'
        """
        params = {"node_type": node_type}
        if scope == "current_product_line" and product_line_code:
            cypher += " AND n.product_line_code = $pl"
            params["pl"] = product_line_code
        cypher += """
        RETURN n.node_id AS node_id, n.name AS name, n.type AS type,
               n.fmea_id AS fmea_id, n.product_line_code AS product_line_code,
               d.document_no AS document_no
        """
        result = await session.run(cypher, **params)
        records = await result.data()

        # Python 中计算相似度并过滤（不预过滤 query_text，保证 Jaccard 不遗漏）
        matches = []
        for r in records:
            score, reason = compute_similarity(query_text, r.get("name", ""))
            if score >= min_similarity:
                matches.append({
                    "node_id": r.get("node_id", ""),
                    "name": r.get("name", ""),
                    "type": node_type,
                    "fmea_id": r.get("fmea_id", ""),
                    "document_no": r.get("document_no"),
                    "product_line_code": r.get("product_line_code"),
                    "product_line_name": r.get("product_line_code"),  # Neo4j 中可扩展为 JOIN product_lines
                    "similarity_score": round(score, 3),
                    "match_reason": reason,
                })
        matches.sort(key=lambda x: x["similarity_score"], reverse=True)
        return matches[:limit]
```

---

## 7. Trigger Type → 查询策略映射

推荐触发类型与图谱查询的对应关系：

| trigger_type | query_text 来源字段 | 查询 node_type | 提取推荐项策略 |
|-------------|-------------------|---------------|--------------|
| `failure_mode` | `context["function_description"]` 或 `context["input_text"]` | `FailureMode` | 直接返回匹配节点的 name |
| `failure_effect` | `context["failure_mode"]` | `FailureMode` | 匹配失效模式 → 取其 EFFECT_OF 邻接的 `FailureEffect` 节点 |
| `failure_cause` | `context["failure_mode"]` | `FailureMode` | 匹配失效模式 → 取其 CAUSE_OF 邻接的 `FailureCause` 节点 |
| `measure` | `context["failure_mode"]` | `FailureMode` | 匹配失效模式 → 分别取 `PreventionControl` 和 `DetectionControl`（两次查询） |
| `optimization` | `context["failure_mode"]` | `FailureMode` | 匹配失效模式 → 取 `OPTIMIZED_BY` 邻接的优化措施节点 |

> **关键洞察：** 用户输入的触发类型不总是直接查询同类型节点。例如用户想填写 `failure_cause` 时，先用当前 `failure_mode` 匹配历史相似失效模式，再**从其邻接关系中提取原因**推荐给用户。这样推荐的因果链更有语义价值。

**邻接提取逻辑（以 failure_cause 为例）：**

```python
def _extract_neighbors(graph_data: dict, fm_node_id: str, edge_type: str) -> list[dict]:
    """从匹配到的失效模式节点中提取指定边类型的邻接节点。"""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    node_map = {n["id"]: n for n in nodes}
    
    results = []
    for e in edges:
        if e.get("type") == edge_type and e.get("target") == fm_node_id:
            neighbor = node_map.get(e.get("source"))
            if neighbor:
                results.append(neighbor)
    return results
```

---

## 8. 推荐服务层改造

### 8.1 新管道流程

```
┌─────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Cache  │────▶│ Sequential Query │────▶│ Merge & Deduplicate│
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

> 规则引擎是同步 CPU 运算（~1ms），图谱查询是 I/O（~50ms）。将 ~1ms 的 CPU 任务与 I/O 并行收益极低且增加调度开销，因此采用**顺序执行**。

### 8.2 `RecommendationService` 构造函数与 `recommend()` 改造

```python
class RecommendationService:
    def __init__(
        self,
        db: AsyncSession,
        llm_provider: LLMProvider | None,
        graph_repo: FMEAGraphRepository,
    ):
        self.db = db
        self.llm = llm_provider
        self.graph_repo = graph_repo
        self.rules = RuleEngine()

    async def recommend(self, fmea_id: uuid.UUID, request: RecommendRequest) -> RecommendResponse:
        fmea = await self._get_fmea_or_404(fmea_id)
        scope = getattr(request, "scope", "global")
        include_graph = getattr(request, "include_graph", True)

        # 权限检查：无全局权限强制降级
        effective_scope = self._resolve_scope(scope, fmea.product_line_code)

        # 1. Check cache
        context_hash = self._compute_context_hash({
            **request.context,
            "scope": effective_scope,
            "include_graph": include_graph,
        })
        cache_result = await self._get_cached(fmea_id, request.trigger_type, context_hash)
        if cache_result:
            cached_response, cached_with_llm = cache_result
            if self.llm is not None and not cached_with_llm:
                pass  # fall through to re-evaluate with LLM
            else:
                return cached_response

        # 2. Rule engine (sync, ~1ms)
        rule_result = self.rules.evaluate(request.trigger_type, request.context)
        rule_suggestions = [
            SuggestionItem(name=s.name, confidence=s.confidence, source="rule", explanation=s.explanation)
            for s in rule_result.suggestions
        ]

        # 3. Graph similarity query (~50ms)
        graph_suggestions: list[SuggestionItem] = []
        if include_graph:
            graph_matches = await self._query_graph_similarity(
                fmea, request.trigger_type, request.context, effective_scope
            )
            graph_suggestions = self._graph_matches_to_suggestions(
                graph_matches, fmea.product_line_code
            )

        # 4. Merge & deduplicate
        all_suggestions = self._merge_and_deduplicate(rule_suggestions, graph_suggestions)

        # 5. Determine if LLM is needed
        has_specific = any(s.confidence >= 0.6 for s in all_suggestions)
        need_llm = (
            self.llm is not None
            and not has_specific
            and len(all_suggestions) < 3
        )

        if need_llm:
            try:
                llm_context = await self._assemble_context(fmea, request)
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
                        name=s.name, confidence=s.confidence, source="llm", explanation=s.explanation
                    )
                    for s in validated.suggestions
                ]
                all_suggestions = self._merge_and_deduplicate(all_suggestions, llm_items)
                source = "graph_enriched" if graph_suggestions else "hybrid"
            except Exception as e:
                source = "graph" if graph_suggestions else "rule_fallback"
                logger.warning("LLM failed, using rule+graph results: %s", e)
        else:
            source = "graph" if graph_suggestions else "rule"

        response = RecommendResponse(
            suggestions=all_suggestions[:10],
            source=source,
            cached=False,
            llm_available=self.llm is not None,
            graph_match_count=len(graph_suggestions),
            effective_scope=effective_scope,
        )

        if source != "rule_fallback":
            await self._cache_result(fmea_id, request.trigger_type, context_hash, fmea, response)
        return response
```

### 8.3 `_query_graph_similarity()` 实现

```python
async def _query_graph_similarity(
    self, fmea: FMEADocument, trigger_type: str, context: dict, scope: str
) -> list[dict]:
    """根据 trigger_type 提取 query_text，调用 Repository 查询相似节点并提取邻接推荐项。"""

    # trigger_type → query_text 来源映射
    query_text = ""
    if trigger_type == "failure_mode":
        query_text = context.get("function_description") or context.get("input_text") or ""
    else:
        query_text = context.get("failure_mode") or ""

    if not query_text or len(query_text) < 2:
        return []

    # 查询相似 FailureMode 节点（所有 trigger_type 都以 FailureMode 为锚点）
    fm_matches = await self.graph_repo.find_similar_nodes_advanced(
        node_type="FailureMode",
        query_text=query_text,
        scope=scope,
        product_line_code=fmea.product_line_code,
        limit=20,
        min_similarity=0.3,
    )

    # failure_mode：直接返回匹配的 FailureMode
    if trigger_type == "failure_mode":
        return fm_matches

    # 其他 trigger_type：从匹配的 FailureMode 提取邻接节点作为推荐项
    recommendations = []
    for match in fm_matches:
        neighbors = await self._extract_neighbors_from_match(match, trigger_type)
        for n in neighbors:
            recommendations.append({
                "node_id": n.get("id", ""),
                "name": n.get("name", ""),
                "type": n.get("type", ""),
                "fmea_id": match["fmea_id"],
                "document_no": match["document_no"],
                "product_line_code": match["product_line_code"],
                "product_line_name": match.get("product_line_name", match["product_line_code"]),
                "similarity_score": match["similarity_score"],  # 继承父节点的相似度
                "match_reason": f"{match['match_reason']}_neighbor",
                "parent_node_name": match["name"],  # 用于 explanation
            })

    return recommendations

async def _extract_neighbors_from_match(self, match: dict, trigger_type: str) -> list[dict]:
    """从历史匹配节点的 graph_data 中提取指定类型的邻接节点。"""
    # 获取匹配节点所在 FMEA 的 graph_data
    fmea_id = uuid.UUID(match["fmea_id"])
    graph_data = await self._get_graph_data_by_fmea_id(fmea_id)
    if not graph_data:
        return []

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    node_map = {n["id"]: n for n in nodes}
    fm_id = match["node_id"]

    if trigger_type == "failure_effect":
        # EFFECT_OF: fm --EFFECT_OF--> effect
        return [
            node_map[e["target"]] for e in edges
            if e.get("type") == "EFFECT_OF" and e.get("source") == fm_id
            and e.get("target") in node_map
        ]

    elif trigger_type == "failure_cause":
        # CAUSE_OF: cause --CAUSE_OF--> fm
        return [
            node_map[e["source"]] for e in edges
            if e.get("type") == "CAUSE_OF" and e.get("target") == fm_id
            and e.get("source") in node_map
        ]

    elif trigger_type == "measure":
        # 控制措施：fm 和其原因节点的 PREVENTED_BY / DETECTED_BY
        ctrl_ids = set()
        for e in edges:
            if e.get("type") in ("PREVENTED_BY", "DETECTED_BY") and e.get("source") == fm_id:
                ctrl_ids.add(e.get("target"))
        # 也收集原因节点的控制措施
        cause_ids = {
            e.get("source") for e in edges
            if e.get("type") == "CAUSE_OF" and e.get("target") == fm_id
        }
        for e in edges:
            if e.get("type") in ("PREVENTED_BY", "DETECTED_BY") and e.get("source") in cause_ids:
                ctrl_ids.add(e.get("target"))
        return [node_map[cid] for cid in ctrl_ids if cid in node_map]

    elif trigger_type == "optimization":
        # OPTIMIZED_BY: fm --OPTIMIZED_BY--> action
        return [
            node_map[e["target"]] for e in edges
            if e.get("type") == "OPTIMIZED_BY" and e.get("source") == fm_id
            and e.get("target") in node_map
        ]

    return []

async def _get_graph_data_by_fmea_id(self, fmea_id: uuid.UUID) -> dict | None:
    """通过 FMEA ID 获取 graph_data（优先 JSONB，因为推荐场景通常不走 Neo4j）。"""
    from app.models.fmea import FMEADocument
    from sqlalchemy import select as sa_select
    result = await self.db.execute(
        sa_select(FMEADocument.graph_data).where(FMEADocument.fmea_id == fmea_id)
    )
    row = result.scalar_one_or_none()
    return row if row else None
```

### 8.4 `_graph_matches_to_suggestions()` 实现

```python
def _graph_matches_to_suggestions(
    self, matches: list[dict], current_product_line_code: str
) -> list[SuggestionItem]:
    """将图谱匹配结果转为 SuggestionItem。"""
    suggestions = []
    for m in matches:
        confidence = 0.5 + (m.get("similarity_score", 0) * 0.5)  # 映射到 0.5~1.0
        # explanation：failure_mode 直接说明匹配原因；其他 trigger_type 说明来自哪个父节点
        if m.get("parent_node_name"):
            explanation = f"来自相似失效模式「{m['parent_node_name']}」的{m.get('type', '节点')}"
        else:
            explanation = f"历史相似节点（{m.get('match_reason', '')}）"

        suggestions.append(SuggestionItem(
            name=m["name"],
            confidence=round(confidence, 2),
            source="graph",
            explanation=explanation,
            source_fmea_id=m.get("fmea_id"),
            source_document_no=m.get("document_no"),
            source_product_line_code=m.get("product_line_code"),
            source_product_line_name=m.get("product_line_name", m.get("product_line_code")),
            source_node_type=m.get("type"),
            source_node_id=m.get("node_id"),
            similarity_score=m.get("similarity_score"),
            match_reason=m.get("match_reason"),
        ))
    return suggestions
```

### 8.5 `_merge_and_deduplicate()` 实现

```python
def _merge_and_deduplicate(
    items_a: list[SuggestionItem],
    items_b: list[SuggestionItem],
) -> list[SuggestionItem]:
    """合并两组建议，按名称去重。
    
    去重策略：
    - 同名保留 confidence 更高的版本
    - confidence 相同时，graph 优先于 rule（有真实历史依据可追溯）
    - confidence 相同时，llm 优先于 rule（语义更丰富）
    """
    seen: dict[str, SuggestionItem] = {}

    for item in items_a:
        key = item.name.strip()
        seen[key] = item

    for item in items_b:
        key = item.name.strip()
        existing = seen.get(key)
        if existing is None:
            seen[key] = item
        elif item.confidence > existing.confidence:
            seen[key] = item
        elif item.confidence == existing.confidence and item.source == "graph" and existing.source != "graph":
            # confidence 相等时，graph 优先
            seen[key] = item

    return sorted(seen.values(), key=lambda x: x.confidence, reverse=True)
```

### 8.6 缓存读取时动态计算 graph_match_count

```python
async def _get_cached(self, fmea_id, trigger_type, context_hash):
    """缓存命中时动态计算 graph_match_count，避免 schema 迁移。"""
    row = await self._fetch_cache_row(fmea_id, trigger_type, context_hash)
    if not row:
        return None
    
    suggestions = row.suggestions
    graph_count = sum(1 for s in suggestions if s.get("source") == "graph")
    
    response = RecommendResponse(
        suggestions=suggestions,
        source=row.source,
        cached=True,
        llm_available=self.llm is not None,
        graph_match_count=graph_count,
        effective_scope=row.context.get("scope", "global") if isinstance(row.context, dict) else "global",
    )
    return response, row.llm_available
```

---

## 9. 前端改造

### 9.1 `SmartSuggestionDropdown` 展示增强

```tsx
function SourceTag({ item }: { item: SuggestionItem }) {
  if (item.source === "graph" && item.source_document_no) {
    const href = `/fmea/${item.source_fmea_id}?tab=graph&highlightNode=${item.source_node_id}`;
    return (
      <span className="source-tag">
        来自 <a href={href} target="_blank" rel="noopener">{item.source_document_no}</a>
        {item.source_product_line_code && ` · ${item.source_product_line_code}`}
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

### 9.2 范围切换控件

```tsx
<Radio.Group 
  value={scope} 
  onChange={setScope}
  disabled={!userHasPermission("KNOWLEDGE_GRAPH_GLOBAL_READ")}
>
  <Radio.Button value="global">全局经验</Radio.Button>
  <Radio.Button value="current_product_line">仅当前产品线</Radio.Button>
</Radio.Group>
{!userHasPermission("KNOWLEDGE_GRAPH_GLOBAL_READ") && (
  <span className="scope-hint">仅当前产品线（无全局权限）</span>
)}
```

---

## 10. 缓存策略

缓存 key 包含 `scope` 和 `include_graph`：

```python
def _compute_context_hash(self, context: dict) -> str:
    raw = json.dumps(context, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()
```

缓存表 `recommendation_cache` 无需迁移。`graph_match_count` 在缓存读取时从 suggestions 动态计算。

---

## 11. 性能考量

| 场景 | 估算 | 对策 |
|------|------|------|
| JSONB 遍历 | 假设 100 文档 × 50 节点 = 5000 节点 | 状态 + 产品线过滤后在 Python 内存中评分；首版数据规模下可接受 |
| Neo4j 遍历 | 所有 GraphNode 遍历 | 状态 + 产品线过滤后 Cypher 返回；Python 中计算相似度 |
| 顺序查询延迟 | 规则(~1ms) + 图谱(~50ms) = ~51ms | 规则引擎是同步 CPU，与 I/O 并行收益极低，顺序执行避免调度开销 |
| LLM 调用 | 仅结果不足时触发 | 减少 LLM 调用次数，降低成本和延迟 |
| 缓存命中率 | 相同输入 + scope 组合 | context_hash 包含 scope，避免污染 |

---

## 12. 错误处理

| 场景 | 行为 |
|------|------|
| 图谱查询失败 | 降级为仅规则引擎结果，记录 warning |
| Neo4j 未配置 | JSONBRepository fallback 自动生效 |
| 无匹配结果 | 返回空列表，触发 LLM（如果可用） |
| LLM 失败 | 返回规则 + 图谱结果（如有），source 标记为对应值 |
| 用户无跨产品线权限 | 后端强制 scope = "current_product_line"，返回 `effective_scope` 告知前端 |
| 跨产品线节点（防御性）| API 层对无全局权限用户的跨产品线节点名称脱敏（mask_name），有权限用户不受影响 |

---

## 13. 验收标准

- [ ] 知识图谱相似度匹配作为独立推荐源接入推荐管道
- [ ] 默认跨产品线匹配，支持切换仅当前产品线
- [ ] 权限控制：`KNOWLEDGE_GRAPH_GLOBAL_READ` 控制全局访问，无权限强制降级
- [ ] 跨产品线节点 API 层防御性脱敏（仅无全局权限用户）
- [ ] FMEA 状态过滤：仅查询 `approved` 文档
- [ ] 推荐项显示来源文档编号、产品线 code/name、节点类型、相似度分数
- [ ] 来源文档编号可点击跳转至对应 FMEA（带 highlightNode 参数）
- [ ] 规则引擎 + 图谱结果充足时不调用 LLM
- [ ] LLM 可将图谱匹配结果作为上下文增强生成
- [ ] 去重逻辑正确：同名保留最高置信度，相等时 graph 优先
- [ ] 缓存 key 包含 scope，避免全局/隔离切换污染
- [ ] `effective_scope` 返回实际生效范围
- [ ] Neo4j 和 JSONB 双实现均支持相似度匹配（含预过滤优化）
- [ ] 构建和测试无错误
