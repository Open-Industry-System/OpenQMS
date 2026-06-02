# FMEA 智能推荐 — 知识图谱相似度匹配 + 来源文档标注 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将知识图谱从历史 FMEA 文档中挖掘的相似节点接入现有推荐管道，实现跨产品线经验复用，每条推荐标注来源文档、产品线、相似度分数和匹配原因。

**Architecture:** 在现有 `RecommendationService`（规则引擎 + LLM）中注入 `FMEAGraphRepository`，新增图谱相似度查询层。管道变为：缓存检查 → 规则引擎 → 图谱相似度 → 合并去重 → 不足时 LLM 补充。Repository 层在 JSONB 和 Neo4j 双实现上各增加 `find_similar_nodes_advanced()`。

**Tech Stack:** Python 3.11 + FastAPI + Pydantic v2 + SQLAlchemy 2.0 (async) + PostgreSQL JSONB / Neo4j | React 18 + TypeScript + Ant Design

---

## 文件结构映射

| 文件 | 责任 |
|------|------|
| `backend/app/utils/similarity.py` | 共享相似度计算函数（子串 boost + bigram Jaccard） |
| `backend/app/graph/repository.py` | 抽象接口新增 `find_similar_nodes_advanced` |
| `backend/app/graph/jsonb_repository.py` | JSONB 实现 + 批量产品线名称加载 |
| `backend/app/graph/neo4j_repository.py` | Neo4j 实现（Cypher 过滤 + Python 评分） |
| `backend/app/schemas/recommendation.py` | 扩展 `SuggestionItem`、`RecommendRequest`、`RecommendResponse`；新增 `SimilarNodesRequest`/`Response` |
| `backend/app/services/recommendation_service.py` | 核心改造：注入 graph_repo、scope 降级、新管道、邻接提取、合并去重 |
| `backend/app/api/fmea.py` | 更新 `recommend` 端点：传入 scope、权限检查、注入 graph_repo |
| `backend/app/api/graph.py` | 新增 `POST /similar-nodes` 独立端点 |
| `backend/app/core/permissions.py` | `Module` 枚举新增 `KNOWLEDGE_GRAPH` |
| `backend/alembic/versions/029_knowledge_graph_permissions.py` | 新增迁移：为 admin/manager 角色插入 `knowledge_graph` 权限 |
| `frontend/src/hooks/usePermission.ts` | `ModuleKey` 类型新增 `"knowledge_graph"` |
| `frontend/src/api/recommendation.ts` | 扩展 TS 类型，请求中增加 scope |
| `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx` | 增加 SourceTag 组件、范围切换控件、来源信息展示 |
| `backend/tests/test_similarity.py` | 相似度函数单元测试 |
| `backend/tests/test_recommendation_service.py` | RecommendationService 新逻辑测试（stub graph_repo） |
| `backend/tests/test_graph_api.py` | `/similar-nodes` 端点测试 |

---

## Task 1: 共享相似度计算模块

**Files:**
- Create: `backend/app/utils/similarity.py`
- Test: `backend/tests/test_similarity.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from app.utils.similarity import compute_similarity


def test_substring_match():
    score, reason = compute_similarity("焊接不良", "焊接虚焊")
    assert score == 0.75
    assert reason == "substring_match"


def test_bigram_jaccard():
    score, reason = compute_similarity("密封失效", "密封不良")
    assert score > 0.3
    assert score < 1.0
    assert reason == "text_similarity"


def test_no_match():
    score, reason = compute_similarity("abc", "xyz")
    assert score == 0.0
    assert reason == "text_similarity"


def test_empty_query():
    score, reason = compute_similarity("", "anything")
    assert score == 0.0
    assert reason == "text_similarity"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_similarity.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.utils.similarity'"

- [ ] **Step 3: Write minimal implementation**

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
        return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else set()

    a, b = _bigrams(query), _bigrams(candidate)
    if not a or not b:
        return 0.0, "text_similarity"
    score = len(a & b) / len(a | b)
    return score, "text_similarity"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_similarity.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/similarity.py backend/tests/test_similarity.py
git commit -m "feat(recommendation): shared similarity utility (substring + Jaccard)"
```

---

## Task 2: Repository 抽象接口扩展

**Files:**
- Modify: `backend/app/graph/repository.py`

- [ ] **Step 1: Add abstract method to FMEAGraphRepository**

在 `backend/app/graph/repository.py` 中，在 `get_global_stats` 方法之后、`analyze_change_impact` 之前插入：

```python
    @abstractmethod
    async def find_similar_nodes_advanced(
        self,
        node_type: str,
        query_text: str,
        scope: str,
        product_line_code: str | None,
        limit: int = 10,
        min_similarity: float = 0.3,
    ) -> list[dict]:
        """跨 FMEA 相似节点搜索（增强版）。

        返回项包含：
        - node_id, name, type, fmea_id, document_no
        - product_line_code, product_line_name
        - similarity_score (0.0 ~ 1.0)
        - match_reason
        """
```

- [ ] **Step 2: Verify abstract method enforcement**

Run: `cd backend && python -c "from app.graph.jsonb_repository import JSONBRepository; JSONBRepository(None)"`
Expected: `TypeError: Can't instantiate abstract class JSONBRepository with abstract method find_similar_nodes_advanced`
（这是预期行为，证明抽象方法生效）

- [ ] **Step 3: Commit**

```bash
git add backend/app/graph/repository.py
git commit -m "feat(graph): add find_similar_nodes_advanced abstract method"
```

---

## Task 3: JSONBRepository 实现

**Files:**
- Modify: `backend/app/graph/jsonb_repository.py`

- [ ] **Step 1: Write failing test for find_similar_nodes_advanced (TDD)**

创建 `backend/tests/test_graph_repository_advanced.py`：

```python
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from app.graph.jsonb_repository import JSONBRepository


class StubDB:
    """Minimal async stub for testing abstract method instantiation."""
    pass


def test_jsonb_repo_has_find_similar_nodes_advanced():
    """验证 JSONBRepository 已实现 find_similar_nodes_advanced。"""
    repo = JSONBRepository(StubDB())
    assert hasattr(repo, "find_similar_nodes_advanced")
    import inspect
    assert "compute_similarity" in inspect.getsource(repo.find_similar_nodes_advanced)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_graph_repository_advanced.py -v`
Expected: FAIL — `JSONBRepository` has no attribute `find_similar_nodes_advanced` (or import error if method not yet added)

- [ ] **Step 3: 在文件顶部导入 similarity 函数**

```python
from app.utils.similarity import compute_similarity
```

- [ ] **Step 4: 添加 `_load_product_line_names` 辅助方法**

在 `JSONBRepository` 类末尾（`analyze_change_impact` 之后）添加：

```python
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

- [ ] **Step 5: 添加 `find_similar_nodes_advanced` 实现**

在 `_load_product_line_names` 之后添加：

```python
    async def find_similar_nodes_advanced(
        self,
        node_type: str,
        query_text: str,
        scope: str,
        product_line_code: str | None,
        limit: int = 10,
        min_similarity: float = 0.3,
    ) -> list[dict]:
        from sqlalchemy import select as sa_select

        query = sa_select(FMEADocument).where(
            FMEADocument.status == "approved",  # approved = 已审批并发布；后续可扩展为 in_(["approved", "published"])
            FMEADocument.graph_data.isnot(None),
        )
        if scope == "current_product_line" and product_line_code:
            query = query.where(FMEADocument.product_line_code == product_line_code)
        result = await self._db.execute(query)
        fmeas = result.scalars().all()

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
```

- [ ] **Step 6: Run new + existing repository tests**

Run: `cd backend && python -m pytest tests/test_graph_repository_advanced.py tests/test_graph_repository.py -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/graph/jsonb_repository.py backend/tests/test_graph_repository_advanced.py
git commit -m "feat(graph): JSONBRepository.find_similar_nodes_advanced + TDD tests"
```

---

## Task 4: Neo4jRepository 实现

**Files:**
- Modify: `backend/app/graph/neo4j_repository.py`

- [ ] **Step 1: Write failing test for Neo4j find_similar_nodes_advanced (TDD)**

在 `backend/tests/test_graph_repository_advanced.py` 末尾追加：

```python
def test_neo4j_repo_has_find_similar_nodes_advanced():
    """验证 Neo4jRepository 已实现 find_similar_nodes_advanced。"""
    from app.graph.neo4j_repository import Neo4jRepository
    assert hasattr(Neo4jRepository, "find_similar_nodes_advanced")
    import inspect
    assert "compute_similarity" in inspect.getsource(Neo4jRepository.find_similar_nodes_advanced)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_graph_repository_advanced.py::test_neo4j_repo_has_find_similar_nodes_advanced -v`
Expected: FAIL — `Neo4jRepository` has no attribute `find_similar_nodes_advanced`

- [ ] **Step 3: 在文件顶部导入 similarity 函数**

```python
from app.utils.similarity import compute_similarity
```

- [ ] **Step 4: 添加 `find_similar_nodes_advanced` 实现**

在 `get_global_stats` 方法之后添加：

```python
    async def find_similar_nodes_advanced(
        self,
        node_type: str,
        query_text: str,
        scope: str,
        product_line_code: str | None,
        limit: int = 10,
        min_similarity: float = 0.3,
    ) -> list[dict]:
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            cypher = """
            MATCH (d:FMEDocument)-[:HAS_NODE]->(n:GraphNode {type: $node_type})
            WHERE d.status = 'approved'  /* approved = 已审批并发布；后续可扩展为 IN ['approved', 'published'] */
            """
            params: dict[str, Any] = {"node_type": node_type}
            if scope == "current_product_line" and product_line_code:
                cypher += " AND n.product_line_code = $pl"
                params["pl"] = product_line_code
            cypher += """
            RETURN n.node_id AS node_id, n.name AS name, n.type AS type,
                   n.fmea_id AS fmea_id, n.product_line_code AS product_line_code,
                   d.document_no AS document_no,
                   d.product_line_name AS product_line_name
            """
            result = await session.run(cypher, **params)
            records = await result.data()

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
                        "product_line_name": r.get("product_line_name", r.get("product_line_code")),
                        "similarity_score": round(score, 3),
                        "match_reason": reason,
                    })
            matches.sort(key=lambda x: x["similarity_score"], reverse=True)
            return matches[:limit]
```

- [ ] **Step 5: Run TDD tests**

Run: `cd backend && python -m pytest tests/test_graph_repository_advanced.py -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/neo4j_repository.py backend/tests/test_graph_repository_advanced.py
git commit -m "feat(graph): Neo4jRepository.find_similar_nodes_advanced + TDD tests"
```

---

## Task 5: GraphProjectionService 投影契约更新

**Files:**
- Modify: `backend/app/services/graph_projection_service.py`

设计 §6.3 要求 Neo4j 投影在 `FMEDocument` 节点写入 `product_line_name`。当前 projection 只写 `product_line_code`。

- [ ] **Step 0: Write failing test for product_line_name projection (TDD)**

创建 `backend/tests/test_graph_projection.py`：

```python
from app.services.graph_projection_service import build_cypher_sync


def test_build_cypher_sync_includes_product_line_name():
    """FMEDocument CREATE 语句 params 必须包含 product_line_name。"""
    statements = build_cypher_sync(
        fmea_id="f1", document_no="PFMEA-001", title="测试",
        fmea_type="PFMEA", product_line_code="DC-DC-100",
        product_line_name="DC-DC 电源模块",  # 新增参数
        status="approved", version=1,
        graph_data={"nodes": [{"id": "n1", "type": "FailureMode", "name": "测试"}], "edges": []},
    )
    # 找到 CREATE FMEDocument 语句
    doc_statements = [s for s in statements if "CREATE (d:FMEDocument" in s[0]]
    assert len(doc_statements) == 1
    _, params = doc_statements[0]
    assert params["product_line_name"] == "DC-DC 电源模块"
    assert "product_line_name" in params
```

- [ ] **Step 1: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_graph_projection.py::test_build_cypher_sync_includes_product_line_name -v`
Expected: FAIL — `TypeError: build_cypher_sync() got an unexpected keyword argument 'product_line_name'`

- [ ] **Step 2: 更新 `build_cypher_sync` 签名和 Cypher**

在 `build_cypher_sync` 参数列表增加 `product_line_name: str`，并在 `CREATE FMEDocument` 语句中加入该字段：

```python
def build_cypher_sync(
    fmea_id: str,
    document_no: str,
    title: str,
    fmea_type: str,
    product_line_code: str,
    product_line_name: str,  # 新增
    status: str,
    version: int,
    graph_data: dict,
) -> list[tuple[str, dict]]:
    """为单个 FMEA 文档生成完整的 Neo4j 投影 Cypher 语句序列。"""
    statements: list[tuple[str, dict]] = []

    # Step 1: DELETE existing projection for this fmea_id
    statements.append((
        "MATCH (n) WHERE n.fmea_id = $fmea_id DETACH DELETE n",
        {"fmea_id": fmea_id},
    ))

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    if not nodes:
        return statements

    # Step 2: CREATE FMEDocument node（新增 product_line_name）
    statements.append((
        "CREATE (d:FMEDocument {fmea_id: $fmea_id, document_no: $document_no, "
        "title: $title, fmea_type: $fmea_type, product_line_code: $product_line_code, "
        "product_line_name: $product_line_name, "
        "status: $status, version: $version})",
        {
            "fmea_id": fmea_id,
            "document_no": document_no,
            "title": title,
            "fmea_type": fmea_type,
            "product_line_code": product_line_code,
            "product_line_name": product_line_name,
            "status": status,
            "version": version,
        },
    ))

    # Step 3: CREATE each GraphNode
    for node in nodes:
        raw_type = node.get("type", "")
        if raw_type not in ALLOWED_NODE_TYPES:
            logger.warning(f"Skipping unknown node type: {raw_type}")
            continue
        label = NODE_TYPE_LABEL_MAP.get(raw_type, raw_type)
        props = _node_properties(node)
        props["fmea_id"] = fmea_id
        props["product_line_code"] = product_line_code

        statements.append((
            f"CREATE (n:GraphNode:{label}) SET n += $props",
            {"props": props},
        ))

        statements.append((
            "MATCH (d:FMEDocument {fmea_id: $fmea_id}), "
            f"(n:GraphNode {{fmea_id: $fmea_id, node_id: $node_id}}) "
            "CREATE (d)-[:HAS_NODE]->(n)",
            {"fmea_id": fmea_id, "node_id": node["id"]},
        ))

    # Step 4: CREATE edges
    node_ids = {n["id"] for n in nodes if n.get("type") in ALLOWED_NODE_TYPES}
    for edge_idx, edge in enumerate(edges):
        edge_type = edge.get("type", "")
        source = edge.get("source", "")
        target = edge.get("target", "")
        if edge_type not in ALLOWED_EDGE_TYPES:
            logger.warning(f"Skipping unknown edge type: {edge_type}")
            continue
        if source not in node_ids or target not in node_ids:
            continue
        statements.append((
            f"MATCH (s:GraphNode {{fmea_id: $fmea_id, node_id: $source}}), "
            f"(t:GraphNode {{fmea_id: $fmea_id, node_id: $target}}) "
            f"CREATE (s)-[:{edge_type} {{edge_index: $edge_index}}]->(t)",
            {"fmea_id": fmea_id, "source": source, "target": target, "edge_index": edge_idx},
        ))

    return statements
```

- [ ] **Step 3: 更新 `GraphProjectionService.sync_fmea_to_neo4j` 以获取并传入 product_line_name**

```python
    async def sync_fmea_to_neo4j(self, fmea_id: uuid.UUID) -> None:
        from app.models.fmea import FMEADocument
        from app.models.product_line import ProductLine
        from sqlalchemy import select

        async with self._session_factory() as db:
            result = await db.execute(
                select(FMEADocument).where(FMEADocument.fmea_id == fmea_id)
            )
            fmea = result.scalar_one_or_none()
            if fmea is None:
                return

            # 获取产品线名称
            pl_result = await db.execute(
                select(ProductLine.name).where(ProductLine.code == fmea.product_line_code)
            )
            product_line_name = pl_result.scalar_one_or_none() or fmea.product_line_code

        statements = build_cypher_sync(
            fmea_id=str(fmea.fmea_id),
            document_no=fmea.document_no,
            title=fmea.title,
            fmea_type=fmea.fmea_type,
            product_line_code=fmea.product_line_code,
            product_line_name=product_line_name,
            status=fmea.status,
            version=fmea.version,
            graph_data=fmea.graph_data or {"nodes": [], "edges": []},
        )

        async def _tx(tx):
            for cypher, params in statements:
                result = await tx.run(cypher, params)
                await result.consume()

        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            await session.execute_write(_tx)
```

- [ ] **Step 4: Run projection test to verify it passes**

Run: `cd backend && python -m pytest tests/test_graph_projection.py::test_build_cypher_sync_includes_product_line_name -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/graph_projection_service.py backend/tests/test_graph_projection.py
git commit -m "feat(projection): write product_line_name to Neo4j FMEDocument nodes + TDD test"
```

---

## Task 6: Schema 扩展

**Files:**
- Modify: `backend/app/schemas/recommendation.py`

- [ ] **Step 1: 扩展现有 schema**

将 `backend/app/schemas/recommendation.py` 完整替换为：

```python
from typing import Literal
from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    trigger_type: Literal[
        "failure_mode", "failure_effect", "failure_cause", "measure", "optimization"
    ]
    context: dict = Field(default_factory=dict)
    scope: Literal["global", "current_product_line"] = "global"
    include_graph: bool = True


class SuggestionItem(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["rule", "graph", "llm"] = "rule"
    explanation: str = ""
    # 来源文档标注（仅 source == "graph" 时填充）
    source_fmea_id: str | None = None
    source_document_no: str | None = None
    source_product_line_code: str | None = None
    source_product_line_name: str | None = None
    source_node_type: str | None = None
    source_node_id: str | None = None
    similarity_score: float | None = None
    match_reason: str | None = None


class RecommendResponse(BaseModel):
    suggestions: list[SuggestionItem]
    source: Literal["rule", "graph", "hybrid", "rule_fallback", "graph_enriched"]
    cached: bool = False
    llm_available: bool = False
    graph_match_count: int = 0
    effective_scope: Literal["global", "current_product_line"] = "global"


class SuggestionList(BaseModel):
    """LLM 输出校验模型。"""
    suggestions: list[SuggestionItem]


# --- 独立调试端点 schema ---

class SimilarNodesRequest(BaseModel):
    node_type: str
    query_text: str
    scope: Literal["global", "current_product_line"] = "global"
    product_line_code: str
    limit: int = Field(10, ge=1, le=100)
    min_similarity: float = Field(0.3, ge=0.0, le=1.0)


class SimilarNodeMatch(BaseModel):
    node_id: str
    name: str
    node_type: str
    fmea_id: str
    document_no: str
    product_line_code: str | None = None
    product_line_name: str | None = None
    similarity_score: float
    match_reason: str


class SimilarNodesResponse(BaseModel):
    matches: list[SimilarNodeMatch]
    total: int
    effective_scope: Literal["global", "current_product_line"] = "global"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/recommendation.py
git commit -m "feat(schema): extend recommendation schemas with graph source fields"
```

---

## Task 7: RecommendationService 核心改造

**Files:**
- Modify: `backend/app/services/recommendation_service.py`

- [ ] **Step 1: Write failing tests for new RecommendationService methods (TDD)**

创建 `backend/tests/test_recommendation_service.py`（先写会失败的测试）：

```python
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from app.services.recommendation_service import RecommendationService
from app.schemas.recommendation import SuggestionItem


class StubGraphRepo:
    async def find_similar_nodes_advanced(self, **kwargs):
        return []


def test_merge_and_deduplicate_prefers_higher_confidence():
    """同名 suggestion 保留 confidence 更高的版本。"""
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    a = [SuggestionItem(name="焊接不良", confidence=0.7, source="rule")]
    b = [SuggestionItem(name="焊接不良", confidence=0.85, source="graph")]
    result = svc._merge_and_deduplicate(a, b)
    assert len(result) == 1
    assert result[0].source == "graph"
    assert result[0].confidence == 0.85


def test_graph_matches_to_suggestions_maps_confidence():
    """similarity_score 正确映射到 confidence 范围。"""
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    matches = [{
        "node_id": "n1", "name": "焊接不良", "type": "FailureMode",
        "fmea_id": "f1", "document_no": "PFMEA-001",
        "product_line_code": "DC-DC-100", "product_line_name": "DC-DC",
        "similarity_score": 0.75, "match_reason": "substring_match",
    }]
    items = svc._graph_matches_to_suggestions(matches, "DC-DC-100")
    assert len(items) == 1
    assert items[0].confidence == 0.875  # 0.5 + 0.75 * 0.5
    assert items[0].source == "graph"
    assert items[0].source_document_no == "PFMEA-001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_recommendation_service.py -v`
Expected: FAIL — `AttributeError: 'RecommendationService' object has no attribute '_merge_and_deduplicate'` (methods not yet implemented)

- [ ] **Step 3: 更新导入和构造函数**

在文件顶部添加导入：

```python
from app.graph.repository import FMEAGraphRepository
```

修改 `RecommendationService.__init__`：

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
```

- [ ] **Step 4: 重写 `recommend()` 方法**

替换现有的 `recommend()` 方法为：

```python
    async def recommend(
        self, fmea_id: _uuid.UUID, request: RecommendRequest, user: User
    ) -> RecommendResponse:
        from app.core.permissions import get_user_permission, Module, PermissionLevel

        fmea = await self._get_fmea_or_404(fmea_id)

        # 权限检查 + scope 强制降级
        requested_scope = getattr(request, "scope", "global")
        has_kg_permission = await get_user_permission(user, Module.KNOWLEDGE_GRAPH, self.db) >= PermissionLevel.VIEW
        effective_scope = "current_product_line" if (not has_kg_permission and requested_scope == "global") else requested_scope
        include_graph = getattr(request, "include_graph", True)

        # 1. Check cache（cache key 包含 scope 和 include_graph）
        context_hash = self._compute_context_hash({
            **request.context,
            "scope": effective_scope,
            "include_graph": include_graph,
        })
        cache_result = await self._get_cached(
            fmea_id, request.trigger_type, context_hash, effective_scope
        )
        if cache_result:
            cached_response, cached_with_llm = cache_result
            if self.llm is not None and not cached_with_llm:
                pass  # fall through to re-evaluate with LLM
            else:
                return cached_response

        # 2. Rule engine（sync, ~1ms）
        rule_result = self.rules.evaluate(request.trigger_type, request.context)
        rule_suggestions = [
            SuggestionItem(name=s.name, confidence=s.confidence, source="rule", explanation=s.explanation)
            for s in rule_result.suggestions
        ]

        # 3. Graph similarity query
        graph_suggestions: list[SuggestionItem] = []
        if include_graph:
            try:
                graph_matches = await self._query_graph_similarity(
                    fmea, request.trigger_type, request.context, effective_scope
                )
                graph_suggestions = self._graph_matches_to_suggestions(
                    graph_matches, fmea.product_line_code
                )
            except Exception as e:
                logger.warning("Graph similarity query failed: %s", e)

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
                import asyncio
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

- [ ] **Step 5: 添加 `_query_graph_similarity` 方法**

```python
    async def _query_graph_similarity(
        self, fmea: FMEADocument, trigger_type: str, context: dict, scope: str
    ) -> list[dict]:
        query_text = ""
        if trigger_type == "failure_mode":
            query_text = context.get("function_description") or context.get("input_text") or ""
        else:
            query_text = context.get("failure_mode") or ""

        if not query_text or len(query_text) < 2:
            return []

        fm_matches = await self.graph_repo.find_similar_nodes_advanced(
            node_type="FailureMode",
            query_text=query_text,
            scope=scope,
            product_line_code=fmea.product_line_code,
            limit=20,
            min_similarity=0.3,
        )

        if trigger_type == "failure_mode":
            return fm_matches

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
                    "similarity_score": match["similarity_score"],
                    "match_reason": f"{match['match_reason']}_neighbor",
                    "parent_node_name": match["name"],
                })
        return recommendations
```

- [ ] **Step 6: 添加 `_extract_neighbors_from_match` 方法**

```python
    async def _extract_neighbors_from_match(self, match: dict, trigger_type: str) -> list[dict]:
        fmea_id = _uuid.UUID(match["fmea_id"])
        graph_data = await self._get_graph_data_by_fmea_id(fmea_id)
        if not graph_data:
            return []

        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        node_map = {n["id"]: n for n in nodes}
        fm_id = match["node_id"]

        if trigger_type == "failure_effect":
            return [
                node_map[e["target"]] for e in edges
                if e.get("type") == "EFFECT_OF" and e.get("source") == fm_id
                and e.get("target") in node_map
            ]

        elif trigger_type == "failure_cause":
            return [
                node_map[e["source"]] for e in edges
                if e.get("type") == "CAUSE_OF" and e.get("target") == fm_id
                and e.get("source") in node_map
            ]

        elif trigger_type == "measure":
            ctrl_ids = set()
            for e in edges:
                if e.get("type") in ("PREVENTED_BY", "DETECTED_BY") and e.get("source") == fm_id:
                    ctrl_ids.add(e.get("target"))
            cause_ids = {
                e.get("source") for e in edges
                if e.get("type") == "CAUSE_OF" and e.get("target") == fm_id
            }
            for e in edges:
                if e.get("type") in ("PREVENTED_BY", "DETECTED_BY") and e.get("source") in cause_ids:
                    ctrl_ids.add(e.get("target"))
            return [node_map[cid] for cid in ctrl_ids if cid in node_map]

        elif trigger_type == "optimization":
            opt_ids = set()
            for e in edges:
                if e.get("type") == "OPTIMIZED_BY" and e.get("source") == fm_id:
                    opt_ids.add(e.get("target"))
            cause_ids = {
                e.get("source") for e in edges
                if e.get("type") == "CAUSE_OF" and e.get("target") == fm_id
            }
            for e in edges:
                if e.get("type") == "OPTIMIZED_BY" and e.get("source") in cause_ids:
                    opt_ids.add(e.get("target"))
            return [node_map[oid] for oid in opt_ids if oid in node_map]

        return []

    async def _get_graph_data_by_fmea_id(self, fmea_id: _uuid.UUID) -> dict | None:
        from sqlalchemy import select as sa_select
        result = await self.db.execute(
            sa_select(FMEADocument.graph_data).where(FMEADocument.fmea_id == fmea_id)
        )
        row = result.scalar_one_or_none()
        return row if row else None
```

- [ ] **Step 7: 添加 `_graph_matches_to_suggestions` 方法**

```python
    def _graph_matches_to_suggestions(
        self, matches: list[dict], current_product_line_code: str
    ) -> list[SuggestionItem]:
        suggestions = []
        for m in matches:
            confidence = 0.5 + (m.get("similarity_score", 0) * 0.5)
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

- [ ] **Step 8: 添加 `_merge_and_deduplicate` 方法**

```python
    def _merge_and_deduplicate(
        self,
        items_a: list[SuggestionItem],
        items_b: list[SuggestionItem],
    ) -> list[SuggestionItem]:
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
                seen[key] = item
        return sorted(seen.values(), key=lambda x: x.confidence, reverse=True)
```

- [ ] **Step 9: 更新 `_get_cached` 以动态计算 `graph_match_count` 和 `effective_scope`**

```python
    async def _get_cached(
        self, fmea_id: _uuid.UUID, trigger_type: str, context_hash: str, effective_scope: str
    ) -> tuple[RecommendResponse, bool] | None:
        stmt = (
            select(RecommendationCache)
            .where(RecommendationCache.fmea_id == fmea_id)
            .where(RecommendationCache.trigger_type == trigger_type)
            .where(RecommendationCache.context_hash == context_hash)
            .where(RecommendationCache.expires_at > func.now())
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            suggestions = row.suggestions
            graph_count = sum(1 for s in suggestions if s.get("source") == "graph")
            response = RecommendResponse(
                suggestions=suggestions,
                source=row.source,
                cached=True,
                llm_available=self.llm is not None,
                graph_match_count=graph_count,
                effective_scope=effective_scope,
            )
            return (response, row.llm_available)
        return None
```

- [ ] **Step 10: 更新 `_cache_result` 以保存新字段**

```python
    async def _cache_result(
        self, fmea_id: _uuid.UUID, trigger_type: str, context_hash: str,
        fmea: FMEADocument, response: RecommendResponse,
    ) -> None:
        stmt = (
            pg_insert(RecommendationCache)
            .values(
                fmea_id=fmea_id,
                trigger_type=trigger_type,
                context_hash=context_hash,
                product_line_code=fmea.product_line_code,
                fmea_type=fmea.fmea_type,
                suggestions=[s.model_dump() for s in response.suggestions],
                source=response.source,
                llm_available=self.llm is not None,
            )
            .on_conflict_do_update(
                index_elements=["fmea_id", "trigger_type", "context_hash"],
                set_={
                    "suggestions": [s.model_dump() for s in response.suggestions],
                    "source": response.source,
                    "llm_available": self.llm is not None,
                    "product_line_code": fmea.product_line_code,
                    "fmea_type": fmea.fmea_type,
                    "created_at": func.now(),
                    "expires_at": func.now() + text("INTERVAL '24 hours'"),
                },
            )
        )
        await self.db.execute(stmt)
```

- [ ] **Step 11: 删除旧的 `_merge_suggestions` 方法（被 `_merge_and_deduplicate` 替代）**

在文件中删除 `_merge_suggestions` 方法。

- [ ] **Step 12: Commit**

```bash
git add backend/app/services/recommendation_service.py backend/tests/test_recommendation_service.py
git commit -m "feat(recommendation): integrate graph similarity into RecommendationService + TDD tests"
```

---

## Task 8: 权限系统更新

**Files:**
- Modify: `backend/app/core/permissions.py`
- Create: `backend/alembic/versions/029_knowledge_graph_permissions.py`

- [ ] **Step 1: 在 Module 枚举中新增 KNOWLEDGE_GRAPH**

```python
class Module(StrEnum):
    FMEA = "fmea"
    CAPA = "capa"
    DASHBOARD = "dashboard"
    AUDIT = "audit"
    CUSTOMER_QUALITY = "customer_quality"
    CUSTOMER_AUDIT = "customer_audit"
    SUPPLIER = "supplier"
    IQC = "iqc"
    PPAP = "ppap"
    SPC = "spc"
    MSA = "msa"
    PLANNING = "planning"
    MANAGEMENT_REVIEW = "management_review"
    USER_MGMT = "user_mgmt"
    PERMISSION_MGMT = "permission_mgmt"
    SPECIAL_CHARACTERISTIC = "special_characteristic"
    QUALITY_GOAL = "quality_goal"
    SCAR = "scar"
    KNOWLEDGE_GRAPH = "knowledge_graph"  # 新增
```

- [ ] **Step 2: 保存当前 head revision（在创建任何新文件之前）**

```bash
cd backend
# 先记录当前 head（创建新文件之前）
CURRENT_HEAD=$(alembic heads | head -1 | awk '{print $1}')
echo "Current head: $CURRENT_HEAD"
```

- [ ] **Step 3: 检查 alembic heads，多 head 时自动 merge**

Run: `cd backend && alembic heads`

如果输出多于一行：

```bash
cd backend
# 收集所有 head revision
HEADS=$(alembic heads | awk '{print $1}')
# 自动创建 merge revision
alembic merge -m "merge branches before knowledge_graph permissions" $HEADS
# 验证已合并为单 head
alembic heads
```

Expected: 现在 alembic heads 只输出一行

**注意**：merge 后重新获取 CURRENT_HEAD：

```bash
cd backend
CURRENT_HEAD=$(alembic heads | head -1 | awk '{print $1}')
```

- [ ] **Step 4: 创建迁移文件（直接用 CURRENT_HEAD 填入 down_revision）**

用 Write 工具创建 `backend/alembic/versions/029_knowledge_graph_permissions.py`：

```python
"""add knowledge_graph permissions

Revision ID: 029
Create Date: 2026-06-02
"""
from typing import Sequence, Union
from alembic import op

revision: str = '029_knowledge_graph_permissions'
down_revision: Union[str, None] = 'CURRENT_HEAD_PLACEHOLDER'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO role_permissions (role_id, module, permission_level) "
        "SELECT id, 'knowledge_graph', 1 FROM role_definitions WHERE role_key = 'admin'"
    )
    op.execute(
        "INSERT INTO role_permissions (role_id, module, permission_level) "
        "SELECT id, 'knowledge_graph', 1 FROM role_definitions WHERE role_key = 'manager'"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE module = 'knowledge_graph'"
    )
```

然后立即用 Edit 工具替换 `CURRENT_HEAD_PLACEHOLDER` 为 Step 2 保存的实际值：

```python
down_revision: Union[str, None] = 'CURRENT_HEAD_PLACEHOLDER'
```

替换为：

```python
down_revision: Union[str, None] = '20260602_collab_sessions'
```

（使用 Step 2 中 `$CURRENT_HEAD` 的实际值）

- [ ] **Step 5: 验证迁移文件**

Run: `cd backend && python -m py_compile alembic/versions/029_knowledge_graph_permissions.py`
Expected: No output (success)

Run: `cd backend && alembic check`
Expected: No error, revision chain is valid

- [ ] **Step 6: Commit**

```bash
# 包含可能自动生成的 merge migration 和权限迁移
git add backend/app/core/permissions.py backend/alembic/versions/*.py
git commit -m "feat(permissions): add KNOWLEDGE_GRAPH module for admin/manager"
```

---

## Task 9: API 路由更新

**Files:**
- Modify: `backend/app/api/fmea.py`
- Modify: `backend/app/api/graph.py`

- [ ] **Step 1: 更新 `recommend` 端点以传入 user 和 graph_repo**

修改 `backend/app/api/fmea.py` 中的 `recommend` 函数：

```python
from app.graph.deps import get_graph_repository
from app.graph.repository import FMEAGraphRepository
from app.core.permissions import get_user_permission

@router.post("/{fmea_id}/recommend", response_model=RecommendResponse)
async def recommend(
    fmea_id: uuid.UUID,
    request: RecommendRequest,
    fastapi_request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.EDIT)),
    graph_repo: FMEAGraphRepository = Depends(get_graph_repository),
):
    # Rate limiting (unchanged)
    user_key = f"rec_user:{user.user_id}"
    fmea_key = f"rec_fmea:{fmea_id}"
    if not _check_rate_limit(user_key, _RATE_LIMITS["per_user"]):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")
    if not _check_rate_limit(fmea_key, _RATE_LIMITS["per_fmea"]):
        raise HTTPException(status_code=429, detail="该文档请求过于频繁，请稍后重试")

    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)

    # 提前计算 effective_scope（短输入 early return 也需要正确值）
    requested_scope = getattr(request, "scope", "global")
    has_kg = await get_user_permission(user, Module.KNOWLEDGE_GRAPH, db) >= PermissionLevel.VIEW
    effective_scope = "current_product_line" if (not has_kg and requested_scope == "global") else requested_scope

    if len(request.context.get("function_description", request.context.get("failure_mode", ""))) < 2:
        return RecommendResponse(
            suggestions=[], source="rule", cached=False,
            llm_available=False, graph_match_count=0,
            effective_scope=effective_scope,
        )

    llm = getattr(fastapi_request.app.state, "llm_provider", None)
    service = RecommendationService(db=db, llm_provider=llm, graph_repo=graph_repo)
    result = await service.recommend(fmea_id, request, user)
    await db.commit()
    return result
```

- [ ] **Step 2: 在 graph.py 中添加 `POST /similar-nodes` 端点**

在 `backend/app/api/graph.py` 底部、`@router.post("/rebuild")` 之前添加：

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.recommendation import SimilarNodesRequest, SimilarNodesResponse, SimilarNodeMatch
from app.core.permissions import get_user_permission, Module, PermissionLevel
from app.core.product_line_filter import enforce_product_line_access


@router.post("/similar-nodes", response_model=SimilarNodesResponse)
async def similar_nodes_advanced(
    req: SimilarNodesRequest,
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """跨 FMEA 相似节点搜索（增强版，用于调试和预览）。
    无 KNOWLEDGE_GRAPH 权限时，global scope 强制降级为 current_product_line。
    """

    # 产品线访问校验
    await enforce_product_line_access(user, req.product_line_code, db)

    # scope 强制降级
    has_kg = await get_user_permission(user, Module.KNOWLEDGE_GRAPH, db) >= PermissionLevel.VIEW
    effective_scope = "current_product_line" if (not has_kg and req.scope == "global") else req.scope

    matches = await repo.find_similar_nodes_advanced(
        node_type=req.node_type,
        query_text=req.query_text,
        scope=effective_scope,
        product_line_code=req.product_line_code,
        limit=req.limit,
        min_similarity=req.min_similarity,
    )

    # 防御性脱敏：无全局权限用户的跨产品线节点
    current_pl = req.product_line_code
    result_matches = []
    for m in matches:
        name = m["name"]
        if not has_kg and m.get("product_line_code") != current_pl:
            name = mask_name(name)
        result_matches.append(SimilarNodeMatch(
            node_id=m["node_id"],
            name=name,
            node_type=m["type"],
            fmea_id=m["fmea_id"],
            document_no=m["document_no"],
            product_line_code=m.get("product_line_code"),
            product_line_name=m.get("product_line_name"),
            similarity_score=m["similarity_score"],
            match_reason=m["match_reason"],
        ))

    return SimilarNodesResponse(
        matches=result_matches,
        total=len(result_matches),
        effective_scope=effective_scope,
    )
```

注意：`get_db` 已经在文件顶部被导入（通过 `app.graph.deps.get_graph_repository` 的依赖链间接使用），但这里需要显式使用。检查 `backend/app/api/graph.py` 顶部没有 `get_db` 导入，需要添加：

```python
from app.database import get_db
```

- [ ] **Step 3: 更新 `fmea_service.py` 中的 cache invalidation 调用**

`backend/app/services/fmea_service.py:235` 中 `RecommendationService` 的实例化需要传入 `graph_repo`。由于此处只调用 `invalidate_cache_for_fmea`（不依赖 graph repo），传入内部 `_NullGraphRepo` stub：

在 `backend/app/services/recommendation_service.py` 顶部添加（`RuleEngine` 类之前）：

```python
class _NullGraphRepo(FMEAGraphRepository):
    """仅用于 cache invalidation 等不依赖 graph 查询的场景。"""
    async def get_impact_chain(self, *a, **kw): return {"nodes": [], "edges": []}
    async def get_cause_chain(self, *a, **kw): return {"nodes": [], "edges": []}
    async def find_similar_nodes(self, *a, **kw): return []
    async def get_cross_fmea_stats(self, *a, **kw): return {}
    async def get_global_stats(self): return {}
    async def analyze_change_impact(self, *a, **kw):
        from app.schemas.change_impact import ChangeImpactResult, ImpactSummary
        return ChangeImpactResult(affected_nodes=[], summary=ImpactSummary(
            total_affected=0, failure_modes_affected=0, controls_affected=0,
            ap_upgraded_count=0, max_hop_distance=0,
        ))
    async def find_similar_nodes_advanced(self, *a, **kw): return []
```

在 `backend/app/services/fmea_service.py:235` 修改：

```python
from app.services.recommendation_service import RecommendationService, _NullGraphRepo
rec_service = RecommendationService(db=db, llm_provider=None, graph_repo=_NullGraphRepo())
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/fmea.py backend/app/api/graph.py backend/app/services/fmea_service.py backend/app/services/recommendation_service.py
git commit -m "feat(api): update recommend endpoint + add /similar-nodes + fix fmea_service cache invalidation"
```

---

## Task 10: 前端类型与 API 更新

**Files:**
- Modify: `frontend/src/hooks/usePermission.ts`
- Modify: `frontend/src/api/recommendation.ts`

- [ ] **Step 1: 在 ModuleKey 中新增 knowledge_graph**

```typescript
export type ModuleKey =
  | "fmea" | "capa" | "dashboard" | "audit" | "customer_quality"
  | "customer_audit" | "supplier" | "iqc" | "ppap" | "spc"
  | "msa" | "planning" | "management_review" | "user_mgmt"
  | "permission_mgmt" | "special_characteristic" | "quality_goal" | "scar"
  | "knowledge_graph";  // 新增
```

- [ ] **Step 2: 扩展 recommendation.ts 类型**

```typescript
import client from "./client";

export interface Suggestion {
  name: string;
  confidence: number;
  source: "rule" | "graph" | "llm";
  explanation: string;
  source_fmea_id?: string;
  source_document_no?: string;
  source_product_line_code?: string;
  source_product_line_name?: string;
  source_node_type?: string;
  source_node_id?: string;
  similarity_score?: number;
  match_reason?: string;
}

export interface RecommendRequest {
  trigger_type: string;
  context: Record<string, unknown>;
  scope?: "global" | "current_product_line";
  include_graph?: boolean;
}

export interface RecommendResponse {
  suggestions: Suggestion[];
  source: "rule" | "graph" | "hybrid" | "rule_fallback" | "graph_enriched";
  cached: boolean;
  llm_available: boolean;
  graph_match_count: number;
  effective_scope: "global" | "current_product_line";
}

export async function getRecommendations(
  fmeaId: string,
  request: RecommendRequest,
  signal?: AbortSignal
): Promise<RecommendResponse> {
  const { data } = await client.post(`/fmea/${fmeaId}/recommend`, request, { signal });
  return data;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/usePermission.ts frontend/src/api/recommendation.ts
git commit -m "feat(frontend): extend types for graph-powered recommendations"
```

---

## Task 11: 前端 SmartSuggestionDropdown 增强

**Files:**
- Modify: `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx`

- [ ] **Step 1: 在文件顶部添加 Radio 导入和 usePermission hook**

```typescript
import { useState, useEffect, useRef, useCallback } from "react";
import { Input, Dropdown, Tag, Spin, Alert, Typography, Radio } from "antd";
import { BulbOutlined, StarOutlined, SettingOutlined, GlobalOutlined } from "@ant-design/icons";
import { getRecommendations, type Suggestion, type RecommendResponse } from "../../api/recommendation";
import { usePermission } from "../../hooks/usePermission";
import type { ModuleKey } from "../../hooks/usePermission";

const { Text } = Typography;
```

- [ ] **Step 2: 扩展 props 以接受 scope**

```typescript
interface SmartSuggestionDropdownProps {
  triggerType: "failure_mode" | "failure_effect" | "failure_cause" | "measure" | "optimization";
  context: Record<string, unknown>;
  fmeaId: string;
  onSelect: (suggestion: Suggestion) => void;
  disabled?: boolean;
  value?: string;
  onChange?: (value: string) => void;
  scope?: "global" | "current_product_line";
}
```

- [ ] **Step 3: 在组件内部添加 scope 状态、权限检查和 SourceTag**

```typescript
export default function SmartSuggestionDropdown({
  triggerType,
  context,
  fmeaId,
  onSelect,
  disabled = false,
  value,
  onChange,
  scope: externalScope,
}: SmartSuggestionDropdownProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [llmAvailable, setLlmAvailable] = useState(true);
  const [fallback, setFallback] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [scope, setScope] = useState<"global" | "current_product_line">(externalScope || "global");
  const [effectiveScope, setEffectiveScope] = useState<"global" | "current_product_line">("global");

  const { canView } = usePermission();
  const hasKgPermission = canView("knowledge_graph" as ModuleKey);

  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const abortRef = useRef<AbortController>();

  // SourceTag 子组件
  const SourceTag = ({ item }: { item: Suggestion }) => {
    if (item.source === "graph" && item.source_document_no) {
      const href = `/fmea/${item.source_fmea_id}?tab=graph&highlightNode=${item.source_node_id}`;
      return (
        <span style={{ fontSize: 11, color: "#52c41a" }}>
          来自 <a href={href} target="_blank" rel="noopener" style={{ color: "#52c41a", textDecoration: "underline" }}>{item.source_document_no}</a>
          {item.source_product_line_code && ` · ${item.source_product_line_code}`}
          {item.source_product_line_name && `（${item.source_product_line_name}）`}
          {item.similarity_score !== undefined && ` · 相似度 ${(item.similarity_score * 100).toFixed(0)}%`}
        </span>
      );
    }
    if (item.source === "rule") {
      return <span style={{ fontSize: 11, color: "#1890ff" }}>规则引擎</span>;
    }
    if (item.source === "llm") {
      return <span style={{ fontSize: 11, color: "#722ed1" }}>AI 生成</span>;
    }
    return null;
  };
```

- [ ] **Step 4: 更新 fetchSuggestions 以传入 scope**

```typescript
  const fetchSuggestions = useCallback(
    async (inputValue: string) => {
      if (!inputValue || inputValue.length < 2 || !fmeaId) {
        setSuggestions([]);
        setOpen(false);
        return;
      }

      abortRef.current?.abort();
      abortRef.current = new AbortController();

      setLoading(true);
      setError(null);
      try {
        const res: RecommendResponse = await getRecommendations(
          fmeaId,
          {
            trigger_type: triggerType,
            context: { ...context, input_text: inputValue },
            scope,
            include_graph: true,
          },
          abortRef.current.signal
        );
        setSuggestions(res.suggestions.slice(0, 5));
        setLlmAvailable(res.llm_available);
        setFallback(res.source === "rule_fallback");
        setEffectiveScope(res.effective_scope);
        setOpen(res.suggestions.length > 0);
        setSelectedIndex(-1);
      } catch (e: unknown) {
        if (e instanceof Error && e.name === "AbortError") return;
        const err = e as { response?: { status?: number }; message?: string };
        if (err?.response?.status === 429) {
          setError("请求过于频繁，请稍后重试");
        } else if (err?.response?.status === 403) {
          setError("无权限使用推荐功能");
        } else {
          setError("推荐服务暂不可用");
        }
        setSuggestions([]);
        setOpen(true);
      } finally {
        setLoading(false);
      }
    },
    [fmeaId, triggerType, context, scope]
  );
```

- [ ] **Step 5: 更新 dropdownContent 以展示 SourceTag 和 scope 控件**

```typescript
  const dropdownContent = (
    <div style={{ width: 360, background: "#fff", borderRadius: 4, boxShadow: "0 2px 8px rgba(0,0,0,0.15)" }}>
      {error && (
        <Alert type="error" message={error} banner style={{ fontSize: 12 }} />
      )}
      {fallback && (
        <Alert type="warning" message="AI 建议暂不可用，已使用规则引擎" banner style={{ fontSize: 12 }} />
      )}
      {!llmAvailable && (
        <Text type="secondary" style={{ display: "block", padding: "4px 12px", fontSize: 12 }}>
          仅规则引擎模式
        </Text>
      )}
      <div style={{ padding: "4px 12px", borderBottom: "1px solid #f0f0f0" }}>
        <Radio.Group
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          disabled={!hasKgPermission}
          size="small"
        >
          <Radio.Button value="global"><GlobalOutlined /> 全局经验</Radio.Button>
          <Radio.Button value="current_product_line">仅当前产品线</Radio.Button>
        </Radio.Group>
        {!hasKgPermission && (
          <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
            （无全局权限，仅当前产品线）
          </Text>
        )}
        {effectiveScope !== scope && (
          <Text type="warning" style={{ fontSize: 11, marginLeft: 8 }}>
            实际范围：{effectiveScope === "global" ? "全局" : "仅当前产品线"}
          </Text>
        )}
      </div>
      {suggestions.map((s, i) => (
        <div
          key={i}
          onClick={() => handleSelect(s)}
          style={{
            padding: "8px 12px",
            cursor: "pointer",
            background: i === selectedIndex ? "#f0f0f0" : "transparent",
            borderBottom: i < suggestions.length - 1 ? "1px solid #f0f0f0" : "none",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {sourceIcon(s.source)}
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13 }}>{s.name}</div>
              {s.explanation && (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {s.explanation}
                </Text>
              )}
              <div><SourceTag item={s} /></div>
            </div>
            {confidenceLabel(s.confidence)}
          </div>
        </div>
      ))}
    </div>
  );
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/dfmea/SmartSuggestionDropdown.tsx
git commit -m "feat(frontend): SmartSuggestionDropdown with source tags and scope toggle"
```

---

## Task 12: 后端测试

**Files:**
- Create: `backend/tests/test_recommendation_service.py`
- Modify: `backend/tests/test_graph_api.py`

- [ ] **Step 1: 写 RecommendationService 测试**

```python
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
import uuid

from app.services.recommendation_service import RecommendationService, RuleEngine
from app.schemas.recommendation import RecommendRequest, SuggestionItem


class StubGraphRepo:
    async def find_similar_nodes_advanced(self, **kwargs):
        return [
            {
                "node_id": "fm_001",
                "name": "焊接虚焊",
                "type": "FailureMode",
                "fmea_id": str(uuid.uuid4()),
                "document_no": "PFMEA-2026-001",
                "product_line_code": "DC-DC-100",
                "product_line_name": "DC-DC 电源模块",
                "similarity_score": 0.75,
                "match_reason": "substring_match",
            }
        ]

    async def get_impact_chain(self, *a, **kw):
        return {"nodes": [], "edges": []}

    async def get_cause_chain(self, *a, **kw):
        return {"nodes": [], "edges": []}

    async def get_cross_fmea_stats(self, *a, **kw):
        return {}

    async def get_global_stats(self):
        return {}

    async def analyze_change_impact(self, *a, **kw):
        from app.schemas.change_impact import ChangeImpactResult, ImpactSummary
        return ChangeImpactResult(affected_nodes=[], summary=ImpactSummary(
            total_affected=0, failure_modes_affected=0, controls_affected=0,
            ap_upgraded_count=0, max_hop_distance=0,
        ))


def test_merge_and_deduplicate_prefers_higher_confidence():
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    a = [SuggestionItem(name="焊接不良", confidence=0.7, source="rule")]
    b = [SuggestionItem(name="焊接不良", confidence=0.85, source="graph")]
    result = svc._merge_and_deduplicate(a, b)
    assert len(result) == 1
    assert result[0].source == "graph"
    assert result[0].confidence == 0.85


def test_merge_and_deduplicate_graph_wins_on_tie():
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    a = [SuggestionItem(name="A", confidence=0.7, source="rule")]
    b = [SuggestionItem(name="A", confidence=0.7, source="graph")]
    result = svc._merge_and_deduplicate(a, b)
    assert result[0].source == "graph"


def test_graph_matches_to_suggestions():
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    matches = [
        {
            "node_id": "n1",
            "name": "焊接不良",
            "type": "FailureMode",
            "fmea_id": "f1",
            "document_no": "PFMEA-001",
            "product_line_code": "DC-DC-100",
            "product_line_name": "DC-DC",
            "similarity_score": 0.75,
            "match_reason": "substring_match",
        }
    ]
    items = svc._graph_matches_to_suggestions(matches, "DC-DC-100")
    assert len(items) == 1
    assert items[0].name == "焊接不良"
    assert items[0].source == "graph"
    assert items[0].confidence == 0.875  # 0.5 + 0.75 * 0.5
    assert items[0].source_document_no == "PFMEA-001"


def test_rule_engine_failure_mode():
    engine = RuleEngine()
    result = engine.evaluate("failure_mode", {"function_description": "采集数据"})
    assert len(result.suggestions) > 0
    assert result.quality == "specific"


def test_rule_engine_generic_fallback():
    engine = RuleEngine()
    result = engine.evaluate("failure_mode", {"function_description": "未知操作"})
    assert len(result.suggestions) == 4
    assert result.quality == "generic"


def test_graph_matches_to_suggestions_with_parent_node():
    """neighbor_match 结果 explanation 应包含父节点名称。"""
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    matches = [{
        "node_id": "n1", "name": "密封件老化", "type": "FailureCause",
        "fmea_id": "f1", "document_no": "PFMEA-001",
        "product_line_code": "DC-DC-100", "product_line_name": "DC-DC",
        "similarity_score": 0.75, "match_reason": "substring_match_neighbor",
        "parent_node_name": "密封失效",
    }]
    items = svc._graph_matches_to_suggestions(matches, "DC-DC-100")
    assert "密封失效" in items[0].explanation
    assert items[0].source_node_type == "FailureCause"
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && python -m pytest tests/test_recommendation_service.py -v`
Expected: 6 passed

- [ ] **Step 3: 在 test_graph_api.py 中添加 /similar-nodes 测试**

以下测试依赖 `test_graph_api.py` 中已有的 imports 和 fixtures（`app`, `get_current_user`, `_make_user`, `_override_get_current_user`, `client`）。

先在 `StubGraphRepo` 类（已存在于 `test_graph_api.py`）末尾添加：

```python
    async def find_similar_nodes_advanced(self, **kwargs):
        scope = kwargs.get("scope", "global")
        pl = kwargs.get("product_line_code", "DC-DC-100")
        return [
            {
                "node_id": "fm_001",
                "name": "焊接虚焊",
                "type": "FailureMode",
                "fmea_id": "fmea-1",
                "document_no": "PFMEA-2026-001",
                "product_line_code": pl,
                "product_line_name": "DC-DC 电源模块",
                "similarity_score": 0.75,
                "match_reason": "substring_match",
            }
        ]
```

然后在 `test_graph_api.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_similar_nodes_advanced_success(client: AsyncClient):
    resp = await client.post("/api/graph/similar-nodes", json={
        "node_type": "FailureMode",
        "query_text": "焊接",
        "scope": "global",
        "product_line_code": "DC-DC-100",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "matches" in data
    assert data["effective_scope"] == "global"
    assert len(data["matches"]) > 0
    first = data["matches"][0]
    assert "node_id" in first
    assert "similarity_score" in first


@pytest.mark.asyncio
async def test_similar_nodes_advanced_scope_downgrade(client: AsyncClient):
    """viewer 无 KNOWLEDGE_GRAPH 权限，global 被降级为 current_product_line。
    降级后仍应返回当前产品线结果。"""
    app.dependency_overrides[get_current_user] = lambda: _make_user("viewer")
    try:
        resp = await client.post("/api/graph/similar-nodes", json={
            "node_type": "FailureMode",
            "query_text": "焊接",
            "scope": "global",
            "product_line_code": "DC-DC-100",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["effective_scope"] == "current_product_line"
        # 降级后仍应返回当前产品线结果
        assert len(data["matches"]) > 0
        assert data["matches"][0]["product_line_code"] == "DC-DC-100"
    finally:
        app.dependency_overrides[get_current_user] = _override_get_current_user


@pytest.mark.asyncio
async def test_similar_nodes_advanced_rejects_unauthorized_product_line(client: AsyncClient):
    """无权产品线返回 403。"""
    # viewer 无 bypass_row_level_security，默认只允许 DC-DC-100
    resp = await client.post("/api/graph/similar-nodes", json={
        "node_type": "FailureMode",
        "query_text": "焊接",
        "scope": "current_product_line",
        "product_line_code": "UNAUTHORIZED-PL",
    })
    assert resp.status_code == 403
```

- [ ] **Step 4: 运行 graph API 测试**

Run: `cd backend && python -m pytest tests/test_graph_api.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_recommendation_service.py backend/tests/test_graph_api.py
git commit -m "test: add recommendation service and similar-nodes endpoint tests"
```

---

## Task 13: 构建验证

**Files:** 全项目

- [ ] **Step 1: 后端 lint / import 检查**

Run: `cd backend && python -c "from app.main import app; print('imports OK')"`
Expected: `imports OK`

- [ ] **Step 2: 前端类型检查**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 3: Commit（如有修复）**

```bash
git commit -m "chore: build verification fixes" || echo "no fixes needed"
```

---

## Spec 覆盖自检

| 设计文档 § | 实施任务 |
|-----------|---------|
| §3 相似度算法 | Task 1 |
| §4.1 权限模型（Module.KNOWLEDGE_GRAPH） | Task 8 |
| §4.2 scope 强制降级 | Task 7 (recommend)、Task 9 (similar-nodes) |
| §4.3 跨产品线防御性脱敏 | Task 9 (similar-nodes API 层) |
| §4.4 FMEA 状态过滤 | Task 3 (JSONB where status==approved)、Task 4 (Neo4j where d.status='approved') |
| §5.1 扩展推荐端点 | Task 9 |
| §5.2 响应 Schema 扩展 | Task 6 |
| §5.3 独立 similar-nodes 端点 | Task 9 |
| §6 Repository 扩展 | Task 2, 3, 4 |
| §6.3 Neo4j 投影契约 | Task 5 |
| §7 Trigger Type 映射 | Task 7 (_query_graph_similarity, _extract_neighbors_from_match) |
| §8 推荐服务层改造 | Task 7 |
| §9 前端改造 | Task 11 |
| §10 缓存策略 | Task 7 (context_hash 包含 scope) |
| §12 错误处理 | Task 7 (try/except around graph query) |

**无遗漏。**

## Placeholder 扫描

- [x] 无 "TBD" / "TODO" / "... existing code ..." 占位
- [x] 无 "Add appropriate error handling" 等模糊描述
- [x] 每个步骤含完整代码（迁移文件的 down_revision 通过 Edit 工具填入实际值，非占位）
- [x] 无 "Similar to Task N" 引用

## 类型一致性检查

- `compute_similarity` → 返回 `tuple[float, str]` ✓
- `find_similar_nodes_advanced` 签名：Task 2 抽象定义与 Task 3/4 实现一致 ✓
- `SuggestionItem.source`：schema 中为 `"rule" | "graph" | "llm"`，与前后端一致 ✓
- `RecommendResponse.source`：schema 中为 `"rule" | "graph" | "hybrid" | "rule_fallback" | "graph_enriched"`，与服务层一致 ✓
- `effective_scope`：前后端均为 `"global" | "current_product_line"` ✓
- `ModuleKey` 前端与 `Module` 后端值均为 `"knowledge_graph"` ✓

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-02-fmea-smart-recommendation.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?