# 8D D4/D5 全混合管道升级实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 HybridRecommendationPipeline，将现有 CAPA D4/D5 推荐升级为全混合管道（历史 CAPA 语义匹配 + RAG 替代关键词 + LLM 融合增强）。

**Architecture:** 引入管道化架构：独立 Source 召回 → FusionEngine 去重排序 → LLMFusionLayer 增强解释。保持现有 API 契约向后兼容，Schema 扩展为可选字段。

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (async), pgvector, pytest, pytest-asyncio

---

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `backend/app/services/recommendation_types.py` | 数据模型：RecommendationContext, RecommendationCandidate, RecommendationResult | 新建 |
| `backend/app/services/fusion_engine.py` | FusionEngine（去重排序） | 新建 |
| `backend/app/services/llm_fusion_layer.py` | LLMFusionLayer（LLM 融合） | 新建 |
| `backend/app/services/recommendation_sources.py` | 7 个 Source/Expander 实现 | 新建 |
| `backend/app/services/hybrid_recommendation_pipeline.py` | HybridRecommendationPipeline 管道编排 | 新建 |
| `backend/app/schemas/capa.py` | 扩展 D4Recommendation / D5GeneralSuggestion | 修改 |
| `backend/app/services/capa_service.py` | update_capa 时触发 embedding 重新同步 | 修改 |
| `backend/app/services/embedding_sync_worker.py` | FMEA 节点 embedding 加入 description | 修改 |
| `backend/app/api/capa.py` | 替换 d4/d5 推荐内部实现 | 修改 |
| `backend/tests/test_fusion_engine.py` | FusionEngine 单元测试 | 新建 |
| `backend/tests/test_recommendation_sources.py` | Source/Expander 单元测试 | 新建 |
| `backend/tests/test_hybrid_pipeline.py` | 管道集成测试 | 新建 |

---

### Task 1: 数据模型 (recommendation_types.py)

**Files:**
- Create: `backend/app/services/recommendation_types.py`
- Test: `backend/tests/test_recommendation_types.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_recommendation_types.py
from app.services.recommendation_types import RecommendationContext, RecommendationCandidate


def test_recommendation_context_creation():
    ctx = RecommendationContext(
        capa_data={"d2_description": "焊接虚焊"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
    )
    assert ctx.stage == "d4"
    assert ctx.fmea_docs is None


def test_recommendation_candidate_creation():
    c = RecommendationCandidate(
        source="fmea_graph",
        content="焊接参数偏移",
        category=None,
        confidence=0.6,
        match_reason="关联 FMEA 失效原因",
        metadata={"fmea_id": "abc"},
    )
    assert c.source == "fmea_graph"
    assert c.metadata["fmea_id"] == "abc"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_recommendation_types.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.recommendation_types'`

- [ ] **Step 3: 实现数据模型**

```python
# backend/app/services/recommendation_types.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class RecommendationContext:
    """上下文：当前 CAPA 数据 + 用户权限 + 预加载数据。"""
    capa_data: dict[str, Any]
    user_product_lines: list[str] | None  # None = admin 全权限
    stage: Literal["d4", "d5"]
    # 预加载的共享数据（避免每个 Source 重复查库）
    fmea_docs: list[dict[str, Any]] | None = None
    linked_fmea: dict[str, Any] | None = None


@dataclass
class RecommendationCandidate:
    """单个推荐候选。"""
    source: str  # 内部 Source 标识
    content: str  # 根因文本 / 措施文本
    category: str | None  # D5 用: "预防措施" | "探测措施" | "纠正措施"
    confidence: float
    match_reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_d4_schema(self) -> dict[str, Any]:
        """转换为 D4Recommendation 响应字典。"""
        result = {
            "failure_cause_node_id": self.metadata.get("failure_cause_node_id"),
            "failure_cause_name": self.content,
            "failure_cause_desc": self.metadata.get("failure_cause_desc"),
            "failure_mode_node_id": self.metadata.get("failure_mode_node_id"),
            "failure_mode_name": self.metadata.get("failure_mode_name"),
            "fmea_document_no": self.metadata.get("fmea_document_no"),
            "fmea_id": self.metadata.get("fmea_id"),
            # 内部 source "rule_engine" 映射为旧值 "rule"
            "match_source": "rule" if self.source == "rule_engine" else self.source,
            "match_reason": self.match_reason,
            "related_d2_keywords": self.metadata.get("related_d2_keywords", []),
            "confidence": round(self.confidence, 2),
        }
        # 历史 CAPA 来源字段（可选）
        if self.source == "historical_capa":
            result["source_capa_id"] = self.metadata.get("historical_capa_id")
            result["source_capa_document_no"] = self.metadata.get("document_no")
            result["source_product_line_code"] = self.metadata.get("product_line_code")
        return result

    def to_d5_control_schema(self) -> dict[str, Any] | None:
        """转换为 D5ExistingControl 响应字典。仅 control 类型候选可用。"""
        if self.metadata.get("control_node_id"):
            return {
                "failure_mode_node_id": self.metadata.get("failure_mode_node_id"),
                "failure_mode_name": self.metadata.get("failure_mode_name"),
                "failure_cause_node_id": self.metadata.get("failure_cause_node_id"),
                "failure_cause_name": self.metadata.get("failure_cause_name"),
                "control_node_id": self.metadata["control_node_id"],
                "control_name": self.content,
                "control_type": self.metadata.get("control_type", "prevention"),
                "match_source": "rule" if self.source == "rule_engine" else self.source,
                "match_reason": self.match_reason,
                "fmea_id": self.metadata.get("fmea_id"),
                "fmea_document_no": self.metadata.get("fmea_document_no"),
            }
        return None

    def to_d5_suggestion_schema(self) -> dict[str, Any]:
        """转换为 D5GeneralSuggestion 响应字典。"""
        result = {
            "content": self.content,
            "category": self.category or "预防措施",
            "basis": self.metadata.get("basis", ""),
            "confidence": round(self.confidence, 2),
        }
        # 历史 CAPA 来源字段（可选）
        if self.source == "historical_capa":
            result["match_source"] = "historical_capa"
            result["source_capa_id"] = self.metadata.get("historical_capa_id")
            result["source_capa_document_no"] = self.metadata.get("document_no")
        return result


@dataclass
class RecommendationResult:
    """管道输出。"""
    items: list[RecommendationCandidate]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_recommendation_types.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendation_types.py backend/tests/test_recommendation_types.py
git commit -m "feat(recommendation): add RecommendationContext/Candidate/Result data models"
```

---

### Task 2: FusionEngine (fusion_engine.py)

**Files:**
- Create: `backend/app/services/fusion_engine.py`
- Test: `backend/tests/test_fusion_engine.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_fusion_engine.py
import pytest
from app.services.fusion_engine import FusionEngine
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext


class TestFusionEngine:
    def test_deduplicate_by_normalized_text(self):
        engine = FusionEngine()
        candidates = [
            RecommendationCandidate("semantic_search", "焊接虚焊", None, 0.7, "", {}),
            RecommendationCandidate("historical_capa", "焊接虚焊", None, 0.8, "", {}),
        ]
        ctx = RecommendationContext({"d2_description": ""}, None, "d4")
        result = engine.merge(candidates, ctx)
        assert len(result) == 1
        assert result[0].source == "historical_capa"  # higher confidence first

    def test_source_priority_applied(self):
        engine = FusionEngine()
        candidates = [
            RecommendationCandidate("rule_engine", "规则建议", None, 0.9, "", {}),
            RecommendationCandidate("fmea_graph", "图匹配", None, 0.6, "", {}),
        ]
        ctx = RecommendationContext({"d2_description": ""}, None, "d4")
        result = engine.merge(candidates, ctx)
        # fmea_graph priority 1.0 > rule_engine 0.5
        # 0.6 * 1.0 = 0.6 vs 0.9 * 0.5 = 0.45
        assert result[0].source == "fmea_graph"

    def test_product_line_bonus(self):
        engine = FusionEngine()
        candidates = [
            RecommendationCandidate("semantic_search", "A", None, 0.7, "", {"product_line_code": "DC-DC-100"}),
            RecommendationCandidate("semantic_search", "B", None, 0.7, "", {"product_line_code": "OTHER"}),
        ]
        ctx = RecommendationContext({"product_line_code": "DC-DC-100"}, None, "d4")
        result = engine.merge(candidates, ctx)
        # A: 0.7 * 0.7 + 0.05 = 0.54; B: 0.7 * 0.7 + 0 = 0.49
        assert result[0].content == "A"

    def test_cap_at_10(self):
        engine = FusionEngine()
        candidates = [
            RecommendationCandidate("rule_engine", f"item_{i}", None, 0.5, "", {})
            for i in range(15)
        ]
        ctx = RecommendationContext({}, None, "d4")
        result = engine.merge(candidates, ctx)
        assert len(result) == 10
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_fusion_engine.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.fusion_engine'`

- [ ] **Step 3: 实现 FusionEngine**

```python
# backend/app/services/fusion_engine.py
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext


class FusionEngine:
    """Merge candidates from multiple sources, deduplicate and rank."""

    SOURCE_PRIORITY = {
        "fmea_graph": 1.0,
        "historical_capa": 0.9,
        "semantic_search": 0.7,
        "llm": 0.6,
        "rule_engine": 0.5,
    }

    def merge(
        self,
        candidates: list[RecommendationCandidate],
        context: RecommendationContext,
    ) -> list[RecommendationCandidate]:
        # 1. 来源优先级归一化 + 元数据 bonus
        for c in candidates:
            priority = self.SOURCE_PRIORITY.get(c.source, 0.5)
            product_bonus = (
                0.05
                if c.metadata.get("product_line_code")
                == context.capa_data.get("product_line_code")
                else 0.0
            )
            severity_bonus = (
                0.03
                if c.metadata.get("severity")
                == context.capa_data.get("severity")
                else 0.0
            )
            c.confidence = min(
                c.confidence * priority + product_bonus + severity_bonus,
                0.95,
            )

        # 2. 去重（归一化文本匹配）
        seen: set[str] = set()
        deduped: list[RecommendationCandidate] = []
        for c in sorted(candidates, key=lambda x: x.confidence, reverse=True):
            normalized = "".join(c.content.lower().split())
            if normalized not in seen:
                seen.add(normalized)
                deduped.append(c)

        # 3. 截断 Top 10
        return deduped[:10]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_fusion_engine.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/fusion_engine.py backend/tests/test_fusion_engine.py
git commit -m "feat(recommendation): add FusionEngine with dedup, ranking, metadata bonus"
```

---

### Task 3: 推荐 Source 层 (recommendation_sources.py) — Part 1: FMEAGraphSource

**Files:**
- Create: `backend/app/services/recommendation_sources.py`
- Test: `backend/tests/test_recommendation_sources.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_recommendation_sources.py
import uuid
import pytest
from app.services.recommendation_sources import FMEAGraphSource
from app.services.recommendation_types import RecommendationContext


@pytest.fixture
def sample_graph():
    fm_id = str(uuid.uuid4())
    cause_id = str(uuid.uuid4())
    func_id = str(uuid.uuid4())
    return {
        "nodes": [
            {"id": func_id, "type": "ProcessStepFunction", "name": "焊接功能"},
            {"id": fm_id, "type": "FailureMode", "name": "焊接虚焊"},
            {"id": cause_id, "type": "FailureCause", "name": "焊接参数偏移"},
        ],
        "edges": [
            {"source": func_id, "target": fm_id, "type": "HAS_FAILURE_MODE"},
            {"source": cause_id, "target": fm_id, "type": "CAUSE_OF"},
        ],
    }


class TestFMEAGraphSource:
    @pytest.mark.asyncio
    async def test_linked_fmea_with_failuremode_node(self, sample_graph):
        source = FMEAGraphSource()
        fmea_id = uuid.uuid4()
        fm_id = sample_graph["nodes"][1]["id"]
        ctx = RecommendationContext(
            capa_data={
                "fmea_ref_id": fmea_id,
                "fmea_node_id": fm_id,
                "d2_description": "",
            },
            user_product_lines=None,
            stage="d4",
            linked_fmea={"fmea_id": fmea_id, "document_no": "PFMEA-001", "graph_data": sample_graph},
        )
        results = await source.retrieve(ctx)
        assert len(results) == 1
        assert results[0].content == "焊接参数偏移"
        assert results[0].source == "fmea_graph"
        assert results[0].metadata["failure_mode_node_id"] == fm_id

    @pytest.mark.asyncio
    async def test_no_linked_fmea_returns_empty(self):
        source = FMEAGraphSource()
        ctx = RecommendationContext(
            capa_data={"fmea_ref_id": None, "fmea_node_id": None},
            user_product_lines=None,
            stage="d4",
        )
        results = await source.retrieve(ctx)
        assert results == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_recommendation_sources.py::TestFMEAGraphSource -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.recommendation_sources'`

- [ ] **Step 3: 实现 FMEAGraphSource**

```python
# backend/app/services/recommendation_sources.py
from __future__ import annotations

from typing import Any

from app.services.recommendation_types import RecommendationCandidate, RecommendationContext


class FMEAGraphSource:
    """关联 FMEA 结构性图匹配。纯结构解析，不做文本匹配。"""

    name = "fmea_graph"

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        linked_fmea = context.linked_fmea
        if not linked_fmea or not linked_fmea.get("graph_data"):
            return []

        capa_data = context.capa_data
        target_node_id = capa_data.get("fmea_node_id")
        if not target_node_id:
            return []

        graph = linked_fmea["graph_data"]
        node_map = {n["id"]: n for n in graph.get("nodes", [])}
        edges = graph.get("edges", [])

        forward_edges: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            forward_edges.setdefault(e["source"], []).append((e["target"], e["type"]))

        reverse_edges: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            reverse_edges.setdefault(e["target"], []).append((e["source"], e["type"]))

        target_node = node_map.get(target_node_id)
        if not target_node:
            return []

        # Resolve to FailureMode IDs
        failure_mode_ids: list[str] = []
        ntype = target_node["type"]
        if ntype == "FailureCause":
            for tgt, etype in forward_edges.get(target_node_id, []):
                if etype == "CAUSE_OF" and node_map.get(tgt, {}).get("type") == "FailureMode":
                    failure_mode_ids.append(tgt)
        elif ntype == "FailureMode":
            failure_mode_ids.append(target_node_id)
        elif ntype in ("Function", "ProcessStepFunction", "ProcessItemFunction", "ProcessWorkElementFunction"):
            for tgt, etype in forward_edges.get(target_node_id, []):
                if etype == "HAS_FAILURE_MODE" and node_map.get(tgt, {}).get("type") == "FailureMode":
                    failure_mode_ids.append(tgt)

        # For each FailureMode, find FailureCauses
        results: list[RecommendationCandidate] = []
        for fm_id in failure_mode_ids:
            fm_node = node_map.get(fm_id, {})
            cause_ids = [
                src
                for src, etype in reverse_edges.get(fm_id, [])
                if etype == "CAUSE_OF" and node_map.get(src, {}).get("type") == "FailureCause"
            ]
            for cause_id in cause_ids:
                cause_node = node_map.get(cause_id, {})
                results.append(RecommendationCandidate(
                    source="fmea_graph",
                    content=cause_node.get("name", ""),
                    category=None,
                    confidence=0.6,
                    match_reason="关联 FMEA 失效原因",
                    metadata={
                        "failure_cause_node_id": cause_id,
                        "failure_cause_desc": cause_node.get("description"),
                        "failure_mode_node_id": fm_id,
                        "failure_mode_name": fm_node.get("name"),
                        "fmea_document_no": linked_fmea.get("document_no"),
                        "fmea_id": str(linked_fmea["fmea_id"]),
                        "product_line_code": linked_fmea.get("product_line_code"),
                    },
                ))

            # If no FailureCause matched but FM was found, return FM-level match
            if not cause_ids:
                results.append(RecommendationCandidate(
                    source="fmea_graph",
                    content=fm_node.get("name", ""),
                    category=None,
                    confidence=0.4,
                    match_reason="关联 FMEA 失效模式",
                    metadata={
                        "failure_mode_node_id": fm_id,
                        "failure_mode_name": fm_node.get("name"),
                        "fmea_document_no": linked_fmea.get("document_no"),
                        "fmea_id": str(linked_fmea["fmea_id"]),
                        "product_line_code": linked_fmea.get("product_line_code"),
                    },
                ))

        return results
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_recommendation_sources.py::TestFMEAGraphSource -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendation_sources.py backend/tests/test_recommendation_sources.py
git commit -m "feat(recommendation): add FMEAGraphSource for linked FMEA structural matching"
```

---

### Task 4: 推荐 Source 层 — Part 2: SemanticSearchSource + HistoricalCAPASource

**Files:**
- Modify: `backend/app/services/recommendation_sources.py`
- Test: `backend/tests/test_recommendation_sources.py`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 backend/tests/test_recommendation_sources.py
import pytest
from unittest.mock import AsyncMock

from app.services.recommendation_sources import SemanticSearchSource
from app.services.recommendation_types import RecommendationContext


class TestSemanticSearchSource:
    @pytest.mark.asyncio
    async def test_d4_uses_d2_description(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.execute.return_value.fetchall.return_value = []

        mock_embedding = AsyncMock()
        mock_embedding.embed = AsyncMock(return_value=[[0.1] * 768])

        source = SemanticSearchSource(mock_db, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接虚焊问题", "d4_root_cause": ""},
            user_product_lines=None,
            stage="d4",
            fmea_docs=[],
        )
        results = await source.retrieve(ctx)
        assert results == []
        mock_embedding.embed.assert_called_once_with(["焊接虚焊问题"])
```

由于 SemanticSearchSource 和 HistoricalCAPASource 需要 DB 和 embedding provider，纯单元测试需要大量 Mock。在计划中我们标记这些测试为集成测试（Task 10），此处先实现 Source 代码。

- [ ] **Step 2: 实现 SemanticSearchSource + HistoricalCAPASource**

追加到 `backend/app/services/recommendation_sources.py`：

```python
from sqlalchemy import text

from app.services.embedding_provider import EmbeddingProvider


class SemanticSearchSource:
    """FMEA 节点语义搜索。通过 pgvector 检索 + 图结构回溯。"""

    name = "semantic_search"

    def __init__(self, db, embedding_provider: EmbeddingProvider | None):
        self.db = db
        self.embedding = embedding_provider

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        if not self.embedding:
            return []

        capa_data = context.capa_data
        if context.stage == "d4":
            query_text = capa_data.get("d2_description", "")
        else:
            query_text = capa_data.get("d4_root_cause", "")
            if not query_text:
                query_text = capa_data.get("d2_description", "")

        if not query_text or not query_text.strip():
            return []

        query_vector = await self.embedding.embed([query_text])
        if not query_vector:
            return []

        vec_str = "[" + ",".join(str(v) for v in query_vector[0]) + "]"
        user_pls = context.user_product_lines

        params: dict[str, Any] = {
            "query_vector": vec_str,
            "limit": 10,
        }
        pl_filter = ""
        if user_pls is not None:
            pl_filter = "AND de.product_line_code = ANY(:product_line_codes)"
            params["product_line_codes"] = user_pls

        stmt = text(f"""
            SELECT de.entity_id AS fmea_id, de.node_id,
                   1 - (de.embedding <=> CAST(:query_vector AS vector)) AS similarity,
                   de.product_line_code
            FROM document_embeddings de
            WHERE de.entity_type = 'fmea_node'
              {pl_filter}
            ORDER BY de.embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        """)

        rows = await self.db.execute(stmt, params)
        raw_matches = rows.fetchall()

        # 将预加载的 fmea_docs 转为映射，方便 O(1) 回溯
        doc_map = {str(d["fmea_id"]): d for d in (context.fmea_docs or []) if d.get("graph_data")}

        candidates: list[RecommendationCandidate] = []
        for row in raw_matches:
            fmea_id = str(row.fmea_id)
            node_id = row.node_id
            similarity = float(row.similarity)

            doc = doc_map.get(fmea_id)
            if not doc or not node_id:
                continue

            graph = doc["graph_data"]
            node_map = {n["id"]: n for n in graph.get("nodes", [])}
            node = node_map.get(node_id)
            if not node:
                continue

            node_type = node.get("type")
            edges = graph.get("edges", [])

            # D4: 召回 FailureCause 或 FailureMode
            if context.stage == "d4":
                if node_type == "FailureCause":
                    fm_id = None
                    fm_name = None
                    for e in edges:
                        if e["source"] == node_id and e["type"] == "CAUSE_OF":
                            parent = node_map.get(e["target"])
                            if parent and parent.get("type") == "FailureMode":
                                fm_id = parent["id"]
                                fm_name = parent.get("name")
                                break
                    candidates.append(RecommendationCandidate(
                        source="semantic_search",
                        content=node.get("name", ""),
                        category=None,
                        confidence=similarity * 0.7,
                        match_reason="语义相关失效原因",
                        metadata={
                            "failure_cause_node_id": node_id,
                            "failure_cause_desc": node.get("description"),
                            "failure_mode_node_id": fm_id,
                            "failure_mode_name": fm_name,
                            "fmea_id": fmea_id,
                            "fmea_document_no": doc.get("document_no"),
                            "product_line_code": doc.get("product_line_code"),
                        },
                    ))
                elif node_type == "FailureMode":
                    candidates.append(RecommendationCandidate(
                        source="semantic_search",
                        content=node.get("name", ""),
                        category=None,
                        confidence=similarity * 0.5,
                        match_reason="语义相关失效模式",
                        metadata={
                            "failure_mode_node_id": node_id,
                            "failure_mode_name": node.get("name"),
                            "fmea_id": fmea_id,
                            "fmea_document_no": doc.get("document_no"),
                            "product_line_code": doc.get("product_line_code"),
                        },
                    ))

            # D5: 只召回 FailureCause（后续交给 FMEAControlExpander）
            elif context.stage == "d5" and node_type == "FailureCause":
                fm_id = None
                fm_name = None
                for e in edges:
                    if e["source"] == node_id and e["type"] == "CAUSE_OF":
                        parent = node_map.get(e["target"])
                        if parent and parent.get("type") == "FailureMode":
                            fm_id = parent["id"]
                            fm_name = parent.get("name")
                            break
                candidates.append(RecommendationCandidate(
                    source="semantic_search",
                    content=node.get("name", ""),
                    category=None,
                    confidence=similarity * 0.8,
                    match_reason="语义相关失效原因",
                    metadata={
                        "failure_cause_node_id": node_id,
                        "failure_cause_desc": node.get("description"),
                        "failure_mode_node_id": fm_id,
                        "failure_mode_name": fm_name,
                        "fmea_id": fmea_id,
                        "fmea_document_no": doc.get("document_no"),
                        "product_line_code": doc.get("product_line_code"),
                    },
                ))

        return candidates


class HistoricalCAPASource:
    """历史 CAPA D2→D2 语义匹配。只搜索 D8_CLOSURE。"""

    name = "historical_capa"

    def __init__(self, db, embedding_provider: EmbeddingProvider | None):
        self.db = db
        self.embedding = embedding_provider

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        if not self.embedding:
            return []

        d2 = context.capa_data.get("d2_description", "")
        if not d2 or not d2.strip():
            return []

        query_vector = await self.embedding.embed([d2])
        if not query_vector:
            return []

        vec_str = "[" + ",".join(str(v) for v in query_vector[0]) + "]"
        user_pls = context.user_product_lines

        # 先尝试同产品线（或用户允许的产品线）
        # 注意：user_pls 为 None 时表示 admin（无限制），不应放宽
        # user_pls 为 [] 时表示无权限，应返回空
        # user_pls 为 ["xxx"] 时优先搜索这些产品线的 CAPA
        capa_pl = context.capa_data.get("product_line_code")
        search_pls = user_pls
        if user_pls is not None and capa_pl and capa_pl in user_pls:
            # 优先搜索当前 CAPA 的产品线
            search_pls = [capa_pl]

        results = await self._search(vec_str, search_pls, "d2_description", limit=5)
        if not results and user_pls is not None and len(user_pls) > 1 and capa_pl in user_pls:
            # 当前产品线无结果，放宽到用户允许的所有产品线
            results = await self._search(vec_str, user_pls, "d2_description", limit=5)

        return results

    async def _search(
        self,
        vec_str: str,
        product_line_codes: list[str] | None,
        target_field: str,
        limit: int,
    ) -> list[RecommendationCandidate]:
        params: dict[str, Any] = {
            "query_vector": vec_str,
            "target_field": target_field,
            "limit": limit,
        }
        pl_filter = ""
        if product_line_codes is not None:
            pl_filter = "AND de.product_line_code = ANY(:product_line_codes)"
            params["product_line_codes"] = product_line_codes

        stmt = text(f"""
            SELECT de.entity_id, de.chunk_text,
                   1 - (de.embedding <=> CAST(:query_vector AS vector)) AS similarity,
                   capa.document_no, capa.severity, capa.updated_at AS source_updated_at,
                   capa.d4_root_cause, capa.d5_correction, de.product_line_code
            FROM document_embeddings de
            JOIN capa_eightd capa ON de.entity_id = capa.report_id
            WHERE de.entity_type = 'capa'
              AND de.entity_field = :target_field
              AND capa.status = 'D8_CLOSURE'
              {pl_filter}
            ORDER BY de.embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        """)

        rows = await self.db.execute(stmt, params)
        candidates: list[RecommendationCandidate] = []
        for row in rows.mappings():
            sim = row["similarity"]
            capa_id = str(row["entity_id"])
            candidates.append(RecommendationCandidate(
                source="historical_capa",
                content=row["d4_root_cause"] or row["chunk_text"],
                category=None,
                confidence=min(float(sim) * 0.8, 0.8),
                match_reason=f"历史 CAPA [{row['document_no']}] 相似问题",
                metadata={
                    "historical_capa_id": capa_id,
                    "document_no": row["document_no"],
                    "d5_correction": row["d5_correction"],
                    "product_line_code": row["product_line_code"],
                    "severity": row["severity"],
                    "source_updated_at": row["source_updated_at"],
                },
            ))
        return candidates


class HistoricalCAPAMeasureSource:
    """历史 CAPA D4→D4 匹配 → 推荐 D5 措施。"""

    name = "historical_capa"

    def __init__(self, db, embedding_provider: EmbeddingProvider | None):
        self.db = db
        self.embedding = embedding_provider

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        if not self.embedding:
            return []

        d4 = context.capa_data.get("d4_root_cause", "")
        if not d4 or not d4.strip():
            return []

        query_vector = await self.embedding.embed([d4])
        if not query_vector:
            return []

        vec_str = "[" + ",".join(str(v) for v in query_vector[0]) + "]"
        user_pls = context.user_product_lines

        capa_pl = context.capa_data.get("product_line_code")
        search_pls = user_pls
        if user_pls is not None and capa_pl and capa_pl in user_pls:
            search_pls = [capa_pl]

        results = await self._search(vec_str, search_pls, "d4_root_cause", limit=5)
        if not results and user_pls is not None and len(user_pls) > 1 and capa_pl in user_pls:
            results = await self._search(vec_str, user_pls, "d4_root_cause", limit=5)

        return results

    async def _search(
        self,
        vec_str: str,
        product_line_codes: list[str] | None,
        target_field: str,
        limit: int,
    ) -> list[RecommendationCandidate]:
        params: dict[str, Any] = {
            "query_vector": vec_str,
            "target_field": target_field,
            "limit": limit,
        }
        pl_filter = ""
        if product_line_codes is not None:
            pl_filter = "AND de.product_line_code = ANY(:product_line_codes)"
            params["product_line_codes"] = product_line_codes

        stmt = text(f"""
            SELECT de.entity_id, de.chunk_text,
                   1 - (de.embedding <=> :query_vector) AS similarity,
                   capa.document_no, capa.severity, capa.updated_at AS source_updated_at,
                   capa.d5_correction, de.product_line_code
            FROM document_embeddings de
            JOIN capa_eightd capa ON de.entity_id = capa.report_id
            WHERE de.entity_type = 'capa'
              AND de.entity_field = :target_field
              AND capa.status = 'D8_CLOSURE'
              {pl_filter}
            ORDER BY de.embedding <=> :query_vector
            LIMIT :limit
        """)

        rows = await self.db.execute(stmt, params)
        candidates: list[RecommendationCandidate] = []
        for row in rows.mappings():
            sim = row["similarity"]
            capa_id = str(row["entity_id"])
            d5 = row["d5_correction"]
            if not d5:
                continue
            candidates.append(RecommendationCandidate(
                source="historical_capa",
                content=d5,
                category="纠正措施",
                confidence=min(float(sim) * 0.85, 0.85),
                match_reason=f"历史 CAPA [{row['document_no']}] 相似根因已验证有效",
                metadata={
                    "historical_capa_id": capa_id,
                    "document_no": row["document_no"],
                    "product_line_code": row["product_line_code"],
                    "severity": row["severity"],
                    "source_updated_at": row["source_updated_at"],
                },
            ))
        return candidates
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/recommendation_sources.py
git commit -m "feat(recommendation): add SemanticSearchSource + HistoricalCAPA sources"
```

---

### Task 5: 推荐 Source 层 — Part 3: RuleEngineSource + RuleEngineMeasureSource + FMEAControlExpander

**Files:**
- Modify: `backend/app/services/recommendation_sources.py`

- [ ] **Step 1: 实现 RuleEngineSource**

追加到 `backend/app/services/recommendation_sources.py`：

```python
class RuleEngineSource:
    """规则引擎兜底 — D4 根因建议。"""

    name = "rule_engine"

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        from app.services.recommendation_service import RuleEngine

        engine = RuleEngine()
        d2 = context.capa_data.get("d2_description", "")
        result = engine.evaluate("failure_cause", {"input_text": d2, "failure_mode": d2})

        candidates: list[RecommendationCandidate] = []
        for s in result.suggestions:
            candidates.append(RecommendationCandidate(
                source="rule_engine",
                content=s.name,
                category=None,
                confidence=s.confidence * 0.5,
                match_reason="规则引擎推断",
                metadata={"explanation": s.explanation},
            ))
        return candidates


class RuleEngineMeasureSource:
    """规则引擎兜底 — D5 通用措施建议。"""

    name = "rule_engine"

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        from app.services.recommendation_service import RuleEngine

        engine = RuleEngine()

        # Try to get AP level from linked FMEA
        ap_level = None
        linked_fmea = context.linked_fmea
        target_node_id = context.capa_data.get("fmea_node_id")
        if linked_fmea and linked_fmea.get("graph_data"):
            graph = linked_fmea["graph_data"]
            node_map = {n["id"]: n for n in graph.get("nodes", [])}
            edges = graph.get("edges", [])

            target_fm_id = None
            if target_node_id:
                target_node = node_map.get(target_node_id)
                if target_node:
                    if target_node["type"] == "FailureMode":
                        target_fm_id = target_node_id
                    elif target_node["type"] == "FailureCause":
                        for e in edges:
                            if e["source"] == target_node_id and e["type"] == "CAUSE_OF":
                                parent = node_map.get(e["target"])
                                if parent and parent.get("type") == "FailureMode":
                                    target_fm_id = e["target"]
                                    break

            if target_fm_id and node_map.get(target_fm_id, {}).get("ap"):
                ap_level = node_map[target_fm_id]["ap"]
            else:
                for node in graph.get("nodes", []):
                    if node.get("type") == "FailureMode" and node.get("ap"):
                        ap_level = node["ap"]
                        break

        failure_mode_text = context.capa_data.get("d2_description", "")
        ctx = {"failure_mode": failure_mode_text, "ap": ap_level or "M"}
        result = engine.evaluate("measure", ctx)

        candidates: list[RecommendationCandidate] = []
        for s in result.suggestions:
            cat = s.explanation or "预防措施"
            if cat == "检测措施":
                cat = "探测措施"
            candidates.append(RecommendationCandidate(
                source="rule_engine",
                content=s.name,
                category=cat,
                confidence=s.confidence,
                match_reason=f"AP={ap_level or 'M'} 规则建议",
                metadata={"basis": f"AP={ap_level or 'M'}"},
            ))
        return candidates
```

- [ ] **Step 2: 实现 FMEAControlExpander**

追加到 `backend/app/services/recommendation_sources.py`：

```python
class FMEAControlExpander:
    """D5 Stage 2: 基于召回的 FailureCause 做图遍历扩展 Controls。"""

    name = "fmea_graph"

    async def expand(
        self,
        cause_candidates: list[RecommendationCandidate],
        fmea_docs: list[dict[str, Any]],
    ) -> list[RecommendationCandidate]:
        """接收 Stage 1 召回的 FailureCause 候选，扩展出 Control 候选。"""
        controls: list[RecommendationCandidate] = []
        seen: set[tuple[str, str]] = set()

        # Build fmea_id -> doc map
        doc_map = {str(doc["fmea_id"]): doc for doc in fmea_docs if doc.get("graph_data")}

        for cause_candidate in cause_candidates:
            cause_id = cause_candidate.metadata.get("failure_cause_node_id")
            fmea_id = cause_candidate.metadata.get("fmea_id")
            if not cause_id or not fmea_id:
                continue

            doc = doc_map.get(fmea_id)
            if not doc:
                continue

            graph = doc["graph_data"]
            node_map = {n["id"]: n for n in graph.get("nodes", [])}
            edges = graph.get("edges", [])

            forward_edges: dict[str, list[tuple[str, str]]] = {}
            for e in edges:
                forward_edges.setdefault(e["source"], []).append((e["target"], e["type"]))

            fm_id = cause_candidate.metadata.get("failure_mode_node_id")
            fm_name = cause_candidate.metadata.get("failure_mode_name")
            cause_name = cause_candidate.content

            # Path 1: Cause -> PREVENTED_BY -> PreventionControl
            for tgt, etype in forward_edges.get(cause_id, []):
                if etype == "PREVENTED_BY":
                    ctrl = node_map.get(tgt)
                    if ctrl and ctrl.get("type") == "PreventionControl":
                        key = (tgt, "prevention")
                        if key not in seen:
                            seen.add(key)
                            controls.append(RecommendationCandidate(
                                source="fmea_graph",
                                content=ctrl.get("name", ""),
                                category="prevention",
                                confidence=0.6,
                                match_reason="FMEA 预防措施",
                                metadata={
                                    "failure_mode_node_id": fm_id,
                                    "failure_mode_name": fm_name,
                                    "failure_cause_node_id": cause_id,
                                    "failure_cause_name": cause_name,
                                    "control_node_id": tgt,
                                    "control_type": "prevention",
                                    "fmea_id": fmea_id,
                                    "fmea_document_no": doc.get("document_no"),
                                },
                            ))

            # Path 2: Cause -> DETECTED_BY -> DetectionControl
            for tgt, etype in forward_edges.get(cause_id, []):
                if etype == "DETECTED_BY":
                    ctrl = node_map.get(tgt)
                    if ctrl and ctrl.get("type") == "DetectionControl":
                        key = (tgt, "detection")
                        if key not in seen:
                            seen.add(key)
                            controls.append(RecommendationCandidate(
                                source="fmea_graph",
                                content=ctrl.get("name", ""),
                                category="detection",
                                confidence=0.55,
                                match_reason="FMEA 探测措施（原因级）",
                                metadata={
                                    "failure_mode_node_id": fm_id,
                                    "failure_mode_name": fm_name,
                                    "failure_cause_node_id": cause_id,
                                    "failure_cause_name": cause_name,
                                    "control_node_id": tgt,
                                    "control_type": "detection",
                                    "fmea_id": fmea_id,
                                    "fmea_document_no": doc.get("document_no"),
                                },
                            ))

            # Path 3: FailureMode -> DETECTED_BY -> DetectionControl
            if fm_id:
                for tgt, etype in forward_edges.get(fm_id, []):
                    if etype == "DETECTED_BY":
                        ctrl = node_map.get(tgt)
                        if ctrl and ctrl.get("type") == "DetectionControl":
                            key = (tgt, "detection")
                            if key not in seen:
                                seen.add(key)
                                controls.append(RecommendationCandidate(
                                    source="fmea_graph",
                                    content=ctrl.get("name", ""),
                                    category="detection",
                                    confidence=0.5,
                                    match_reason="FMEA 探测措施（失效模式级）",
                                    metadata={
                                        "failure_mode_node_id": fm_id,
                                        "failure_mode_name": fm_name,
                                        "failure_cause_node_id": cause_id,
                                        "failure_cause_name": cause_name,
                                        "control_node_id": tgt,
                                        "control_type": "detection",
                                        "fmea_id": fmea_id,
                                        "fmea_document_no": doc.get("document_no"),
                                    },
                                ))

        return controls
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/recommendation_sources.py
git commit -m "feat(recommendation): add RuleEngine sources + FMEAControlExpander"
```

---

### Task 6: LLM 融合层 (llm_fusion_layer.py)

**Files:**
- Create: `backend/app/services/llm_fusion_layer.py`
- Test: `backend/tests/test_llm_fusion_layer.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_llm_fusion_layer.py
import pytest
from unittest.mock import AsyncMock

from app.services.llm_fusion_layer import LLMFusionLayer
from app.services.recommendation_types import RecommendationCandidate


class TestLLMFusionLayer:
    @pytest.mark.asyncio
    async def test_no_llm_returns_candidates_unchanged(self):
        layer = LLMFusionLayer(None)
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "reason", {})]
        result = await layer.enrich(candidates, None)
        assert len(result) == 1
        assert result[0].match_reason == "reason"

    @pytest.mark.asyncio
    async def test_llm_fusion_updates_match_reason(self):
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=[
            {"candidate_id": 0, "match_reason": "LLM improved reason"}
        ])

        layer = LLMFusionLayer(mock_llm)
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "original", {})]
        result = await layer.enrich(candidates, None)
        assert result[0].match_reason == "LLM improved reason"

    @pytest.mark.asyncio
    async def test_llm_failure_fallback_to_original(self):
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=Exception("timeout"))

        layer = LLMFusionLayer(mock_llm)
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "original", {})]
        result = await layer.enrich(candidates, None)
        assert result[0].match_reason == "original"

    @pytest.mark.asyncio
    async def test_fallback_generation_when_no_candidates(self):
        mock_llm = AsyncMock()
        # candidates empty -> stage 1 skipped -> _generate_fallback called directly
        mock_llm.complete = AsyncMock(return_value=[
            {"content": "generated", "confidence": 0.4, "match_reason": "LLM fallback"}
        ])

        layer = LLMFusionLayer(mock_llm)
        candidates = []
        result = await layer.enrich(candidates, None)
        assert len(result) == 1
        assert result[0].content == "generated"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_llm_fusion_layer.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现 LLMFusionLayer**

```python
# backend/app/services/llm_fusion_layer.py
import asyncio
import logging
from typing import Any

from app.services.recommendation_types import RecommendationCandidate, RecommendationContext

logger = logging.getLogger(__name__)


class LLMFusionLayer:
    """LLM 融合层：为候选生成推荐理由 + 候选不足时回退生成。"""

    def __init__(self, llm_provider):
        self.llm = llm_provider

    async def enrich(
        self,
        candidates: list[RecommendationCandidate],
        context: RecommendationContext | None,
    ) -> list[RecommendationCandidate]:
        if not self.llm:
            return candidates

        # 阶段 1：为候选生成推荐理由
        enriched: list[RecommendationCandidate] = []
        if candidates:
            try:
                prompt = self._build_fusion_prompt(candidates, context)
                result = await asyncio.wait_for(
                    self.llm.complete(prompt, {}),
                    timeout=2.0,
                )
                enriched = self._merge_explanations(candidates, result)
            except Exception as e:
                logger.warning(f"LLM fusion failed: {e}")
                enriched = candidates
        else:
            enriched = []

        # 阶段 2：候选不足时独立生成
        if len(enriched) < 3:
            try:
                generated = await self._generate_fallback(context)
                enriched.extend(generated)
            except Exception as e:
                logger.warning(f"LLM fallback generation failed: {e}")

        return enriched

    def _build_fusion_prompt(
        self,
        candidates: list[RecommendationCandidate],
        context: RecommendationContext | None,
    ) -> str:
        d2 = context.capa_data.get("d2_description", "") if context else ""
        d4 = context.capa_data.get("d4_root_cause", "") if context else ""
        stage = context.stage if context else "d4"

        items = []
        for i, c in enumerate(candidates):
            items.append({
                "candidate_id": i,
                "source": c.source,
                "content": c.content,
                "confidence": c.confidence,
                "match_reason": c.match_reason,
            })

        system = (
            "你是一名资深质量工程师，擅长 AIAG-VDA 8D 问题解决方法。"
            "请根据提供的候选列表，为每条推荐写一句中文推荐理由。\n\n"
            "规则：\n"
            "1. 你只能改写 match_reason 字段，不允许生成新的 content、node_id 等主键字段\n"
            "2. 输出必须保留每条候选的 candidate_id\n"
            "3. 不增减候选数量，只优化理由\n"
            "4. 输出 JSON 数组"
        )

        user = f"""
当前 8D 阶段: {stage}
D2 问题描述: {d2}
D4 根因: {d4}

候选列表:
{items}

请输出 JSON 数组: [{{"candidate_id": 0, "match_reason": "..."}}, ...]
"""
        return f"{system}\n\n{user}"

    def _merge_explanations(
        self,
        candidates: list[RecommendationCandidate],
        result: Any,
    ) -> list[RecommendationCandidate]:
        if not isinstance(result, list):
            return candidates

        reason_map = {}
        for item in result:
            if isinstance(item, dict) and "candidate_id" in item:
                reason_map[item["candidate_id"]] = item.get("match_reason", "")

        for i, c in enumerate(candidates):
            if i in reason_map and reason_map[i]:
                c.match_reason = reason_map[i]

        return candidates

    async def _generate_fallback(
        self,
        context: RecommendationContext | None,
    ) -> list[RecommendationCandidate]:
        if not context:
            return []

        d2 = context.capa_data.get("d2_description", "")
        d4 = context.capa_data.get("d4_root_cause", "")
        stage = context.stage

        prompt = f"""
你是一名质量工程师。请基于以下信息生成 8D {stage.upper()} 阶段的建议：

D2 问题描述: {d2}
D4 根因: {d4}

请输出 JSON 数组，每条包含 content、confidence(0.0-1.0)、match_reason：
[{{"content": "...", "confidence": 0.5, "match_reason": "..."}}]
"""

        result = await asyncio.wait_for(
            self.llm.complete(prompt, {}),
            timeout=2.0,
        )

        candidates: list[RecommendationCandidate] = []
        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict) and item.get("content"):
                    candidates.append(RecommendationCandidate(
                        source="llm",
                        content=item["content"],
                        category=item.get("category") if stage == "d5" else None,
                        confidence=float(item.get("confidence", 0.5)),
                        match_reason=item.get("match_reason", "LLM 生成建议"),
                        metadata={},
                    ))
        return candidates
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_llm_fusion_layer.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm_fusion_layer.py backend/tests/test_llm_fusion_layer.py
git commit -m "feat(recommendation): add LLMFusionLayer with fusion + fallback generation"
```

---

### Task 7: 混合管道 (hybrid_recommendation_pipeline.py)

**Files:**
- Create: `backend/app/services/hybrid_recommendation_pipeline.py`
- Test: `backend/tests/test_hybrid_pipeline.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_hybrid_pipeline.py
import uuid
import pytest
from unittest.mock import AsyncMock

from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
from app.services.recommendation_types import RecommendationContext


class TestHybridRecommendationPipeline:
    @pytest.mark.asyncio
    async def test_d4_pipeline_with_mock_sources(self):
        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        mock_embedding = AsyncMock()

        pipeline = HybridRecommendationPipeline(mock_db, mock_llm, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接问题", "d4_root_cause": ""},
            user_product_lines=["DC-DC-100"],
            stage="d4",
            linked_fmea=None,
            fmea_docs=[],
        )

        result = await pipeline.recommend(ctx)
        assert isinstance(result.items, list)

    @pytest.mark.asyncio
    async def test_d5_pipeline_with_mock_sources(self):
        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        mock_embedding = AsyncMock()

        pipeline = HybridRecommendationPipeline(mock_db, mock_llm, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接问题", "d4_root_cause": "参数偏移"},
            user_product_lines=["DC-DC-100"],
            stage="d5",
            linked_fmea=None,
            fmea_docs=[],
        )

        result = await pipeline.recommend(ctx)
        assert isinstance(result.items, list)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_hybrid_pipeline.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.hybrid_recommendation_pipeline'`

- [ ] **Step 3: 实现 HybridRecommendationPipeline**

```python
# backend/app/services/hybrid_recommendation_pipeline.py
import logging

from app.services.fusion_engine import FusionEngine
from app.services.llm_fusion_layer import LLMFusionLayer
from app.services.recommendation_sources import (
    FMEAGraphSource,
    SemanticSearchSource,
    HistoricalCAPASource,
    HistoricalCAPAMeasureSource,
    RuleEngineSource,
    RuleEngineMeasureSource,
    FMEAControlExpander,
)
from app.services.recommendation_types import (
    RecommendationContext,
    RecommendationResult,
)

logger = logging.getLogger(__name__)


class HybridRecommendationPipeline:
    """8D D4/D5 全混合推荐管道。"""

    def __init__(self, db, llm_provider, embedding_provider):
        self.db = db
        self.llm = llm_provider
        self.embedding = embedding_provider

        # D4 Sources
        self.d4_sources = [
            FMEAGraphSource(),
            SemanticSearchSource(db, embedding_provider),
            HistoricalCAPASource(db, embedding_provider),
            RuleEngineSource(),
        ]

        # D5 Sources (Stage 1: text/semantic recall)
        self.d5_sources = [
            SemanticSearchSource(db, embedding_provider),
            HistoricalCAPAMeasureSource(db, embedding_provider),
            RuleEngineMeasureSource(),
        ]

        # D5 Stage 2: control expander (not an independent Source)
        self.d5_control_expander = FMEAControlExpander()

        self.fusion = FusionEngine()
        self.llm_layer = LLMFusionLayer(llm_provider)

    async def recommend(self, context: RecommendationContext) -> RecommendationResult:
        """执行完整推荐管道。"""
        stage = context.stage
        all_candidates = []

        # --- Stage 1: 召回 ---
        sources = self.d4_sources if stage == "d4" else self.d5_sources

        for source in sources:
            try:
                candidates = await source.retrieve(context)
                all_candidates.extend(candidates)
                logger.debug(f"Source {source.name} returned {len(candidates)} candidates")
            except Exception as e:
                logger.warning(f"Source {source.name} failed: {e}")

        # --- D5 Stage 2: Control expansion ---
        if stage == "d5":
            # Collect FailureCause candidates from Stage 1 for expander
            cause_candidates = [
                c for c in all_candidates
                if c.metadata.get("failure_cause_node_id")
            ]
            if cause_candidates and context.fmea_docs:
                try:
                    control_candidates = await self.d5_control_expander.expand(
                        cause_candidates, context.fmea_docs
                    )
                    all_candidates.extend(control_candidates)
                except Exception as e:
                    logger.warning(f"FMEAControlExpander failed: {e}")

        # --- Stage 3: 融合去重排序 ---
        fused = self.fusion.merge(all_candidates, context)

        # --- Stage 4: LLM 增强 ---
        enriched = await self.llm_layer.enrich(fused, context)

        return RecommendationResult(items=enriched)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_hybrid_pipeline.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/hybrid_recommendation_pipeline.py backend/tests/test_hybrid_pipeline.py
git commit -m "feat(recommendation): add HybridRecommendationPipeline orchestration"
```

---

### Task 8: Schema 扩展 (schemas/capa.py)

**Files:**
- Modify: `backend/app/schemas/capa.py`

- [ ] **Step 1: 修改 D4Recommendation**

在 `backend/app/schemas/capa.py` 的 `D4Recommendation` 类中，在 `confidence` 字段后追加：

```python
class D4Recommendation(BaseModel):
    # ... existing fields ...
    confidence: float = 0.5
    # --- 新增字段（可选，历史 CAPA 来源标识） ---
    source_capa_id: str | None = None
    source_capa_document_no: str | None = None
    source_product_line_code: str | None = None
```

- [ ] **Step 2: 修改 D5GeneralSuggestion**

在 `D5GeneralSuggestion` 类中，在 `confidence` 字段后追加：

```python
class D5GeneralSuggestion(BaseModel):
    # ... existing fields ...
    confidence: float
    # --- 新增字段（可选，历史 CAPA 来源标识） ---
    match_source: str | None = None
    source_capa_id: str | None = None
    source_capa_document_no: str | None = None
```

- [ ] **Step 3: 运行 schema 验证**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m app.test_schema
```

Expected: `All schema validations passed perfectly!`

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/capa.py
git commit -m "feat(schema): extend D4Recommendation and D5GeneralSuggestion with historical CAPA fields"
```

---

### Task 9: CAPA 服务 embedding 触发 (capa_service.py)

**Files:**
- Modify: `backend/app/services/capa_service.py`

- [ ] **Step 1: 在 update_capa 末尾添加 embedding 触发逻辑**

```python
# 在 capa_service.py 的 update_capa 函数末尾，在 return capa 之前添加：

EMBEDDING_FIELDS = {"d2_description", "d4_root_cause", "d5_correction", "d7_prevention"}

async def update_capa(db, capa, update_data, user_id):
    # ... existing logic (before mutation) ...

    # Detect embedding field changes BEFORE mutating capa
    embedding_changed = {
        k for k, v in update_data.items()
        if k in EMBEDDING_FIELDS and getattr(capa, k) != v
    }

    # ... existing mutation logic ...

    if embedding_changed:
        from app.services.embedding_outbox import enqueue_embedding
        await enqueue_embedding(db, "capa", capa.report_id, capa.product_line_code)

    return capa
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/capa_service.py
git commit -m "feat(capa): trigger re-embedding on d2/d4/d5/d7 field changes"
```

---

### Task 10: FMEA embedding 扩展 (embedding_sync_worker.py)

**Files:**
- Modify: `backend/app/services/embedding_sync_worker.py`

- [ ] **Step 1: 扩展 FMEA 节点 chunk 加入 description**

在 `fetch_chunks` 函数中修改 `entity_type == "fmea_node"` 分支：

```python
# Step 1: 扩展 SQL SELECT 加入 description
# 在 embedding_sync_worker.py fetch_chunks 的 fmea_node 分支中：
# 修改前：
#     SELECT node->>'id' as node_id,
#            node->>'type' as node_type,
#            node->>'name' as name,
#            COALESCE(node->>'requirement', '') as requirement,
#            COALESCE(node->>'specification', '') as specification,
#            ...
# 修改后：
#     SELECT node->>'id' as node_id,
#            node->>'type' as node_type,
#            node->>'name' as name,
#            COALESCE(node->>'description', '') as description,
#            COALESCE(node->>'requirement', '') as requirement,
#            COALESCE(node->>'specification', '') as specification,
#            ...

# Step 2: 扩展 chunk 内容加入 description
# 修改前
text_parts = [row["name"]]
if row["requirement"]:
    text_parts.append(row["requirement"])
if row["specification"]:
    text_parts.append(row["specification"])

# 修改后
text_parts = [row["name"]]
if row.get("description"):
    text_parts.append(row["description"])
if row["requirement"]:
    text_parts.append(row["requirement"])
if row["specification"]:
    text_parts.append(row["specification"])
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/embedding_sync_worker.py
git commit -m "feat(embedding): include description in FMEA node chunks"
```

---

### Task 11: API 路由替换 (api/capa.py)

**Files:**
- Modify: `backend/app/api/capa.py`

- [ ] **Step 1: 添加 imports**

在 `backend/app/api/capa.py` 顶部添加：

```python
from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline, RecommendationContext
from app.services.llm_provider import create_llm_provider
from app.services.embedding_provider import create_embedding_provider
from fastapi import Request
```

- [ ] **Step 2: 替换 d4-fmea-recommendations 路由**

将 `get_d4_fmea_recommendations` 函数体替换为：

```python
@router.get("/{report_id}/d4-fmea-recommendations", response_model=D4RecommendationResponse)
async def get_d4_fmea_recommendations(
    report_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    from app.models.fmea import FMEADocument
    from app.services.capa_service import get_capa

    fmea_level = await get_user_permission(user, Module.FMEA, db)
    if fmea_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    capa = await get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    await enforce_product_line_access(user, capa.product_line_code, db)

    if user.role_definition.bypass_row_level_security:
        allowed_pls = None
    else:
        allowed_pls = await get_user_product_line_codes(user, db)
        if not allowed_pls:
            return {"items": []}

    # Preload FMEA docs for all allowed product lines (not just current CAPA's PL)
    # SemanticSearchSource may retrieve cross-PL matches
    fmea_query = select(FMEADocument)
    if allowed_pls is not None:
        fmea_query = fmea_query.where(FMEADocument.product_line_code.in_(allowed_pls))
    else:
        fmea_query = fmea_query.where(FMEADocument.product_line_code == capa.product_line_code)
    fmea_result = await db.execute(fmea_query)
    fmea_docs = [
        {"fmea_id": f.fmea_id, "document_no": f.document_no, "graph_data": f.graph_data, "product_line_code": f.product_line_code}
        for f in fmea_result.scalars().all()
    ]

    linked_fmea = None
    if capa.fmea_ref_id:
        for doc in fmea_docs:
            if doc["fmea_id"] == capa.fmea_ref_id:
                linked_fmea = doc
                break

    llm_provider = request.app.state.llm_provider
    embedding_provider = request.app.state.embedding_provider
    pipeline = HybridRecommendationPipeline(db, llm_provider, embedding_provider)

    context = RecommendationContext(
        capa_data={
            "d2_description": capa.d2_description or "",
            "d3_interim": capa.d3_interim or "",
            "fmea_ref_id": capa.fmea_ref_id,
            "fmea_node_id": capa.fmea_node_id,
            "product_line_code": capa.product_line_code,
        },
        user_product_lines=allowed_pls,
        stage="d4",
        fmea_docs=fmea_docs,
        linked_fmea=linked_fmea,
    )

    result = await pipeline.recommend(context)
    return {"items": [c.to_d4_schema() for c in result.items]}
```

- [ ] **Step 3: 替换 d5-fmea-recommendations 路由**

类似替换 `get_d5_fmea_recommendations`，使用 `stage="d5"`：

```python
@router.get("/{report_id}/d5-fmea-recommendations", response_model=D5RecommendationResponse)
async def get_d5_fmea_recommendations(
    report_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    from app.models.fmea import FMEADocument
    from app.services.capa_service import get_capa

    fmea_level = await get_user_permission(user, Module.FMEA, db)
    if fmea_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    capa = await get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    await enforce_product_line_access(user, capa.product_line_code, db)

    if user.role_definition.bypass_row_level_security:
        allowed_pls = None
    else:
        allowed_pls = await get_user_product_line_codes(user, db)
        if not allowed_pls:
            return {"existing_controls": [], "general_suggestions": []}

    # Preload FMEA docs for all allowed product lines (not just current CAPA's PL)
    # SemanticSearchSource may retrieve cross-PL matches
    fmea_query = select(FMEADocument)
    if allowed_pls is not None:
        fmea_query = fmea_query.where(FMEADocument.product_line_code.in_(allowed_pls))
    else:
        fmea_query = fmea_query.where(FMEADocument.product_line_code == capa.product_line_code)
    fmea_result = await db.execute(fmea_query)
    fmea_docs = [
        {"fmea_id": f.fmea_id, "document_no": f.document_no, "graph_data": f.graph_data, "product_line_code": f.product_line_code}
        for f in fmea_result.scalars().all()
    ]

    linked_fmea = None
    if capa.fmea_ref_id:
        for doc in fmea_docs:
            if doc["fmea_id"] == capa.fmea_ref_id:
                linked_fmea = doc
                break

    llm_provider = request.app.state.llm_provider
    embedding_provider = request.app.state.embedding_provider
    pipeline = HybridRecommendationPipeline(db, llm_provider, embedding_provider)

    context = RecommendationContext(
        capa_data={
            "d4_root_cause": capa.d4_root_cause or "",
            "d2_description": capa.d2_description or "",
            "fmea_ref_id": capa.fmea_ref_id,
            "fmea_node_id": capa.fmea_node_id,
            "product_line_code": capa.product_line_code,
        },
        user_product_lines=allowed_pls,
        stage="d5",
        fmea_docs=fmea_docs,
        linked_fmea=linked_fmea,
    )

    result = await pipeline.recommend(context)

    existing_controls = []
    general_suggestions = []
    for c in result.items:
        control = c.to_d5_control_schema()
        if control:
            existing_controls.append(control)
        else:
            general_suggestions.append(c.to_d5_suggestion_schema())

    return {
        "existing_controls": existing_controls,
        "general_suggestions": general_suggestions,
    }
```

- [ ] **Step 4: 验证编译**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -c "from app.api.capa import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/capa.py
git commit -m "feat(api): integrate HybridRecommendationPipeline into D4/D5 endpoints"
```

---

### Task 12: 集成与端到端测试

**Files:**
- Modify: `backend/tests/test_hybrid_pipeline.py`

- [ ] **Step 1: 追加端到端测试**

```python
# 追加到 backend/tests/test_hybrid_pipeline.py
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
from app.services.recommendation_types import RecommendationContext, RecommendationCandidate


class TestHybridPipelineEndToEnd:
    @pytest.mark.asyncio
    async def test_d4_historical_capa_schema_mapping(self):
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_row = {
            "entity_id": uuid.uuid4(),
            "chunk_text": "温度不稳定",
            "similarity": 0.75,
            "document_no": "8D-2026-001",
            "severity": "严重",
            "source_updated_at": "2026-05-01",
            "d4_root_cause": "温度不稳定",
            "d5_correction": "增加温控",
            "product_line_code": "DC-DC-100",
        }
        mock_db.execute.return_value.mappings.return_value = [mock_row]

        mock_embedding = AsyncMock()
        mock_embedding.embed = AsyncMock(return_value=[[0.1] * 768])

        pipeline = HybridRecommendationPipeline(mock_db, None, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接温度问题", "product_line_code": "DC-DC-100"},
            user_product_lines=["DC-DC-100"],
            stage="d4",
        )

        result = await pipeline.recommend(ctx)
        historical = [c for c in result.items if c.source == "historical_capa"]
        assert len(historical) >= 1
        schema = historical[0].to_d4_schema()
        assert schema["source_capa_document_no"] == "8D-2026-001"
        assert schema["match_source"] == "historical_capa"

    @pytest.mark.asyncio
    async def test_d5_category_纠正措施(self):
        candidate = RecommendationCandidate(
            source="historical_capa",
            content="增加温控闭环",
            category="纠正措施",
            confidence=0.8,
            match_reason="历史 CAPA 相似根因",
            metadata={"historical_capa_id": "abc", "document_no": "8D-001"},
        )
        schema = candidate.to_d5_suggestion_schema()
        assert schema["category"] == "纠正措施"
        assert schema["match_source"] == "historical_capa"
        assert schema["source_capa_document_no"] == "8D-001"

    @pytest.mark.asyncio
    async def test_match_source_rule_backward_compat(self):
        candidate = RecommendationCandidate(
            source="rule_engine",
            content="规则建议",
            category=None,
            confidence=0.5,
            match_reason="规则",
            metadata={},
        )
        schema = candidate.to_d4_schema()
        assert schema["match_source"] == "rule"
```

- [ ] **Step 2: 运行测试**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_hybrid_pipeline.py -v
```

Expected: `5 passed`

- [ ] **Step 3: 运行现有测试确保不破坏**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
pytest tests/test_capa_recommendation.py -v
```

Expected: All existing tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_hybrid_pipeline.py
git commit -m "test(recommendation): add hybrid pipeline end-to-end tests"
```

---

## Self-Review

### 1. Spec Coverage

| Spec 要求 | 实现任务 |
|-----------|---------|
| HybridRecommendationPipeline 核心管道 | Task 7 |
| 7 个 Source/Expander | Task 3, 4, 5 |
| FusionEngine 去重排序 | Task 2 |
| LLMFusionLayer 融合 + 回退 | Task 6 |
| RecommendationContext/Candidate/Result | Task 1 |
| CAPA update 触发 embedding | Task 9 |
| FMEA embedding 扩展 description | Task 10 |
| API 路由内部替换 | Task 11 |
| Schema 扩展 | Task 8 |
| 单元测试 | Task 2, 6, 12 |
| 集成/端到端测试 | Task 12 |

**无遗漏。**

### 2. Placeholder Scan

- 无 "TBD", "TODO", "implement later"
- 无 "Add appropriate error handling"
- 无 "Similar to Task N"
- **已修复**: Task 4 SemanticSearchSource 原为空实现 (`return []`)，已替换为完整的 pgvector + 图回溯实现
- **已修复**: Task 4 测试原为 `pass` placeholder，已替换为真实 Mock 测试

### 3. Type Consistency

- `RecommendationCandidate.source` 在 Task 1 定义为 `str`，Task 3-7 使用一致
- `to_d4_schema()` / `to_d5_control_schema()` / `to_d5_suggestion_schema()` 在 Task 1 定义，Task 11 调用一致
- `match_source` 内部值 `"rule_engine"`，响应映射为 `"rule"`，Task 1 和 Task 12 测试一致

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-02-8d-d4d5-hybrid-pipeline.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
