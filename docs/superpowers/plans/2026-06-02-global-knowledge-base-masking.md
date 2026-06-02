# 全局知识库脱敏 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现跨产品线全局知识库统计 API（`/api/graph/global-stats`，Admin Only），返回数据动态脱敏，不暴露可追溯标识。

**Architecture:** 在现有双 Repository（Neo4j + JSONB）架构上新增 `get_global_stats()` 方法（移除产品线过滤），API 层用白名单重建响应 + `mask_name()` 脱敏函数处理敏感字段。顺带修复 JSONB `get_cross_fmea_stats` 中 `top_failure_modes` 缺失 `document_no` 的历史缺陷。

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy 2.0 (async) + Neo4j (async) | pytest

---

## 文件结构

### 后端修改

```
backend/app/
  graph/
    repository.py              # 新增 get_global_stats 抽象方法
    neo4j_repository.py        # 实现 get_global_stats（移除所有 $pl 过滤）
    jsonb_repository.py        # 实现 get_global_stats（不限制 product_line_code）
                                # + 修复 get_cross_fmea_stats top_failure_modes 缺失 document_no
  api/graph.py                 # 新增 GlobalStatsOut, MaskedNodeOut, mask_name, _sanitize_global_stats
                                # + /global-stats 路由（require_admin）
  tests/test_graph_api.py      # 新增 global-stats 测试用例（含 dependency override 修复）
  tests/test_graph_repository.py  # 新增 JSONBRepository 测试
```

---

## Task 1: Repository 层 — 抽象方法 + Neo4j/JSONB 双实现 + document_no 修复

**Files:**
- Modify: `backend/app/graph/repository.py`
- Modify: `backend/app/graph/neo4j_repository.py`
- Modify: `backend/app/graph/jsonb_repository.py`

**注意:** 抽象方法和两个具体实现必须在**同一个 commit** 中完成，避免中间状态导致 `get_graph_repository()` 实例化失败。

- [ ] **Step 1: 在 `FMEAGraphRepository` 中添加抽象方法**

在 `backend/app/graph/repository.py` 中，`get_cross_fmea_stats` 之后、`analyze_change_impact` 之前插入：

```python
    @abstractmethod
    async def get_global_stats(self) -> dict:
        """跨产品线全局统计。返回结构与 get_cross_fmea_stats 相同。"""
```

- [ ] **Step 2: Neo4jRepository 实现 `get_global_stats`**

在 `backend/app/graph/neo4j_repository.py` 中，`get_cross_fmea_stats` 之后插入：

```python
    async def get_global_stats(self) -> dict:
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            # 节点类型分布（移除 product_line_code 过滤）
            type_result = await session.run(
                "MATCH (n:GraphNode) RETURN n.type AS type, count(*) AS cnt ORDER BY cnt DESC"
            )
            type_records = await type_result.data()
            type_dist = {r["type"]: r["cnt"] for r in type_records}

            # FailureMode RPN 计算（同 get_cross_fmea_stats，移除 WHERE fm.product_line_code = $pl）
            fm_result = await session.run(
                """
                MATCH (fm:GraphNode {type: 'FailureMode'})
                MATCH (d:FMEDocument) WHERE d.fmea_id = fm.fmea_id
                OPTIONAL MATCH (fm)-[re:EFFECT_OF]->(effect:GraphNode)
                WITH fm, d, effect, re
                   ORDER BY re.edge_index ASC
                WITH fm, d, coalesce(head(collect(effect.severity)), 0) as s
                OPTIONAL MATCH (cause:GraphNode)-[rc:CAUSE_OF]->(fm)
                WITH fm, d, s, cause, rc
                   ORDER BY rc.edge_index ASC
                WITH fm, d, s, collect(cause) as causes
                UNWIND CASE WHEN size(causes) = 0 THEN [null] ELSE causes END as cause
                WITH fm, d, s,
                     coalesce(cause.occurrence, 0) as o
                OPTIONAL MATCH (cause)-[rdc:DETECTED_BY]->(det_c:GraphNode)
                WITH fm, d, s, o, det_c, rdc
                   ORDER BY rdc.edge_index ASC
                WITH fm, d, s, o,
                     coalesce(head(collect(det_c.detection)), 0) as first_d_cause,
                     count(det_c) > 0 as has_cause_det
                OPTIONAL MATCH (fm)-[rdf:DETECTED_BY]->(det_f:GraphNode)
                WITH fm, d, s, o, first_d_cause, has_cause_det, det_f, rdf
                   ORDER BY rdf.edge_index ASC
                WITH fm, d, s, o, first_d_cause, has_cause_det,
                     coalesce(head(collect(det_f.detection)), 0) as first_d_fm
                WITH fm, d, s, o,
                     CASE WHEN has_cause_det THEN first_d_cause ELSE first_d_fm END as d_val,
                     s * o * CASE WHEN has_cause_det THEN first_d_cause ELSE first_d_fm END as rpn
                ORDER BY rpn DESC
                WITH fm, d, s,
                     head(collect(o)) as o_best,
                     head(collect(d_val)) as d_best,
                     head(collect(rpn)) as max_rpn
                RETURN fm.node_id AS node_id, fm.name AS name,
                       s AS severity, o_best AS occurrence, d_best AS detection, max_rpn AS rpn,
                       fm.fmea_id AS fmea_id, d.document_no AS document_no
                """
            )
            fm_records = await fm_result.data()

            ap_counts = {"H": 0, "M": 0, "L": 0}
            high_ap_nodes: list[dict] = []
            total_rpn = 0
            rpn_count = 0
            top_modes: list[dict] = []

            for r in fm_records:
                s = r.get("severity", 0) or 0
                o = r.get("occurrence", 0) or 0
                d = r.get("detection", 0) or 0
                rpn = s * o * d
                ap = compute_ap(s, o, d) if s > 0 and o > 0 and d > 0 else ""

                if rpn > 0:
                    total_rpn += rpn
                    rpn_count += 1
                    top_modes.append({
                        "name": r.get("name", ""),
                        "rpn": rpn,
                        "fmea_id": r.get("fmea_id", ""),
                        "document_no": r.get("document_no"),
                    })

                if ap:
                    ap_counts[ap] = ap_counts.get(ap, 0) + 1
                    if ap == "H":
                        high_ap_nodes.append({
                            "node_id": r.get("node_id", ""),
                            "name": r.get("name", ""),
                            "ap": ap,
                            "rpn": rpn,
                            "fmea_id": r.get("fmea_id", ""),
                            "document_no": r.get("document_no"),
                        })

            avg_rpn = round(total_rpn / rpn_count, 1) if rpn_count > 0 else 0

            doc_result = await session.run(
                "MATCH (d:FMEDocument) RETURN count(*) AS cnt"
            )
            doc_records = await doc_result.data()

            return {
                "total_fmeas": doc_records[0]["cnt"] if doc_records else 0,
                "total_nodes": sum(type_dist.values()),
                "node_type_distribution": type_dist,
                "ap_distribution": ap_counts,
                "high_ap_nodes": sorted(high_ap_nodes, key=lambda x: x["rpn"], reverse=True)[:20],
                "avg_rpn": avg_rpn,
                "top_failure_modes": sorted(top_modes, key=lambda x: x["rpn"], reverse=True)[:10],
            }
```

- [ ] **Step 3: JSONBRepository 修复 document_no + 实现 get_global_stats**

在 `backend/app/graph/jsonb_repository.py` 中：

**3a. 修复 `get_cross_fmea_stats` 中 `top_failure_modes` 缺失 `document_no`**

找到这段代码（约 line 175-179）：

```python
                    top_modes.append({
                        "name": fm["name"],
                        "rpn": rpn,
                        "fmea_id": str(fmea.fmea_id),
                    })
```

替换为：

```python
                    top_modes.append({
                        "name": fm["name"],
                        "rpn": rpn,
                        "fmea_id": str(fmea.fmea_id),
                        "document_no": fmea.document_no,
                    })
```

**3b. 添加 `get_global_stats` 方法**

在 `get_cross_fmea_stats` 之后插入：

```python
    async def get_global_stats(self) -> dict:
        query = select(FMEADocument)
        result = await self._db.execute(query)
        fmeas = result.scalars().all()

        type_counts: dict[str, int] = {}
        total_nodes = 0
        ap_counts = {"H": 0, "M": 0, "L": 0}
        high_ap_nodes: list[dict] = []
        total_rpn = 0
        rpn_count = 0
        top_modes: list[dict] = []

        for fmea in fmeas:
            if not fmea.graph_data:
                continue

            for node in fmea.graph_data.get("nodes", []):
                total_nodes += 1
                t = node.get("type", "Unknown")
                type_counts[t] = type_counts.get(t, 0) + 1

            for fm in self._collect_failure_mode_rpn(fmea.graph_data):
                rpn = fm["rpn"]
                ap = fm["ap"]

                if rpn > 0:
                    total_rpn += rpn
                    rpn_count += 1
                    top_modes.append({
                        "name": fm["name"],
                        "rpn": rpn,
                        "fmea_id": str(fmea.fmea_id),
                        "document_no": fmea.document_no,
                    })

                if ap:
                    ap_counts[ap] = ap_counts.get(ap, 0) + 1
                    if ap == "H":
                        high_ap_nodes.append({
                            "node_id": fm["node_id"],
                            "name": fm["name"],
                            "ap": ap,
                            "rpn": rpn,
                            "fmea_id": str(fmea.fmea_id),
                            "document_no": fmea.document_no,
                        })

        return {
            "total_fmeas": len(fmeas),
            "total_nodes": total_nodes,
            "node_type_distribution": type_counts,
            "ap_distribution": ap_counts,
            "high_ap_nodes": sorted(high_ap_nodes, key=lambda x: x["rpn"], reverse=True)[:20],
            "avg_rpn": round(total_rpn / rpn_count, 1) if rpn_count > 0 else 0,
            "top_failure_modes": sorted(top_modes, key=lambda x: x["rpn"], reverse=True)[:10],
        }
```

- [ ] **Step 4: Commit（Repository 层一次性提交）**

```bash
git add backend/app/graph/repository.py backend/app/graph/neo4j_repository.py backend/app/graph/jsonb_repository.py
git commit -m "feat(graph): add get_global_stats across all repositories + fix document_no in JSONB top_failure_modes"
```

---

## Task 2: API Schema + 脱敏函数 + 路由

**Files:**
- Modify: `backend/app/api/graph.py`

- [ ] **Step 1: 在文件顶部导入区添加 `typing.Any`**

```python
from typing import Any
```

- [ ] **Step 2: 添加 Pydantic Schema 和脱敏函数**

在现有 Schema 类之后、`router = APIRouter(...)` 之前插入：

```python
class MaskedNodeOut(BaseModel):
    name: str
    ap: str | None = None
    rpn: int


class GlobalStatsOut(BaseModel):
    total_fmeas: int
    total_nodes: int
    node_type_distribution: dict[str, int]
    ap_distribution: dict[str, int]
    avg_rpn: float
    high_ap_nodes: list[MaskedNodeOut]
    top_failure_modes: list[MaskedNodeOut]


def mask_name(name: Any) -> str:
    """安全脱敏：保留前 2 个字符（去除首尾空格后），其余替换为 ***；
    短名称（≤2 字符）仅保留首字符 + ***，防止完整暴露原值。
    非字符串类型直接返回 ***，避免异常类型被意外展示。
    """
    if name is None:
        return "***"
    if not isinstance(name, str):
        return "***"
    name_str = name.strip()
    if not name_str:
        return "***"
    if len(name_str) <= 2:
        return name_str[:1] + "***"
    return name_str[:2] + "***"


def _sanitize_global_stats(raw: dict) -> dict:
    """白名单重建：只保留统计字段，对 name 脱敏，丢弃所有可追溯标识。"""

    def _mask_node(node: dict) -> dict:
        return {
            "name": mask_name(node.get("name", "")),
            "ap": node.get("ap"),
            "rpn": node.get("rpn", 0),
        }

    return {
        "total_fmeas": raw.get("total_fmeas", 0),
        "total_nodes": raw.get("total_nodes", 0),
        "node_type_distribution": raw.get("node_type_distribution", {}),
        "ap_distribution": raw.get("ap_distribution", {}),
        "avg_rpn": raw.get("avg_rpn", 0.0),
        "high_ap_nodes": [_mask_node(n) for n in raw.get("high_ap_nodes", [])],
        "top_failure_modes": [_mask_node(n) for n in raw.get("top_failure_modes", [])],
    }
```

- [ ] **Step 3: 添加 `/global-stats` 路由**

在 `/stats` 路由之后、`/rebuild` 路由之前插入：

```python
@router.get("/global-stats", response_model=GlobalStatsOut, response_model_exclude_none=True)
async def global_stats(
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    _user: User = Depends(require_admin),
):
    """跨产品线全局知识库统计（Admin Only）。返回数据已脱敏。
    不接受 product_line_code 参数（传入则忽略，不做校验）。
    """
    raw = await repo.get_global_stats()
    return _sanitize_global_stats(raw)
```

**注意:** `response_model_exclude_none=True` 确保 `top_failure_modes` 中 `ap: null` 不会被序列化，与设计示例一致。

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/graph.py
git commit -m "feat(graph): add GlobalStatsOut, mask_name, _sanitize_global_stats and /global-stats endpoint"
```

---

## Task 3: API 测试 + mask_name 边界测试

**Files:**
- Modify: `backend/tests/test_graph_api.py`

**注意:** 当前 `test_graph_api.py` 的 dependency override 使用 `app.api.graph._repo`，但 `api/graph.py` 已改用 `get_graph_repository`。必须同步修复 override 目标。

- [ ] **Step 1: 修复测试文件的 dependency override**

将文件顶部的：

```python
from app.api.graph import _repo
```

替换为：

```python
from app.graph.deps import get_graph_repository
```

将 fixture 中的：

```python
    app.dependency_overrides[_repo] = _override_repo
```

替换为：

```python
    app.dependency_overrides[get_graph_repository] = _override_repo
```

- [ ] **Step 2: 在 `StubGraphRepo` 中添加 `get_global_stats`**

在 `StubGraphRepo` 的 `get_cause_chain` 之后插入：

```python
    async def get_global_stats(self):
        # 模拟跨产品线数据，故意加入敏感字段验证白名单过滤
        return {
            "total_fmeas": 5,
            "total_nodes": 50,
            "node_type_distribution": {"FailureMode": 5, "Function": 10},
            "ap_distribution": {"H": 2, "M": 2, "L": 1},
            "high_ap_nodes": [
                {
                    "node_id": "n1",
                    "name": "焊接不良",
                    "ap": "H",
                    "rpn": 360,
                    "fmea_id": "fmea-1",
                    "document_no": "PFMEA-2026-001",
                    "product_line_code": "DC-DC-100",
                    "leaked_field": "secret",
                }
            ],
            "avg_rpn": 180.0,
            "top_failure_modes": [
                {
                    "name": "密封失效",
                    "rpn": 280,
                    "fmea_id": "fmea-2",
                    "document_no": "PFMEA-2026-002",
                    "product_line_code": "DC-DC-200",
                }
            ],
        }
```

- [ ] **Step 3: 添加测试用例**

在文件末尾添加：

```python
from app.api.graph import mask_name


@pytest.mark.asyncio
async def test_global_stats_admin_only(client: AsyncClient):
    """验证 /global-stats 仅 admin 可访问。"""
    # 默认 client 使用 admin 角色，先验证 200
    resp = await client.get("/api/graph/global-stats")
    assert resp.status_code == status.HTTP_200_OK

    # 切换为 non-admin 角色
    # require_admin 检查 user.role_definition.role_key，不是 user.role
    async def _non_admin_user():
        from app.models.user import User
        from app.models.role import RoleDefinition
        user = User(
            user_id="00000000-0000-0000-0000-000000000002",
            username="viewer",
            display_name="Viewer",
            email="viewer@openqms.local",
            password_hash="hashed",
            is_active=True,
            role="viewer",
        )
        user.role_definition = RoleDefinition(role_key="viewer", role_name="Viewer")
        return user

    app.dependency_overrides[get_current_user] = _non_admin_user
    try:
        resp = await client.get("/api/graph/global-stats")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
    finally:
        app.dependency_overrides[get_current_user] = _override_get_current_user


@pytest.mark.asyncio
async def test_global_stats_response_sanitized(client: AsyncClient):
    """验证 /global-stats 响应已脱敏，无敏感字段。"""
    resp = await client.get("/api/graph/global-stats")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    # 基本统计字段存在
    assert "total_fmeas" in data
    assert "ap_distribution" in data
    assert "high_ap_nodes" in data
    assert "top_failure_modes" in data

    # 敏感字段不存在
    assert "fmea_id" not in data
    assert "document_no" not in data
    assert "product_line_code" not in data
    assert "node_id" not in data
    assert "leaked_field" not in data

    # high_ap_nodes 脱敏检查
    first = data["high_ap_nodes"][0]
    assert "name" in first
    assert first["name"].endswith("***")
    assert "fmea_id" not in first
    assert "document_no" not in first
    assert "node_id" not in first
    assert "ap" in first  # high_ap_nodes 有 ap

    # top_failure_modes 脱敏检查（ap 不应出现，因为原始数据无 ap）
    top = data["top_failure_modes"][0]
    assert "name" in top
    assert top["name"].endswith("***")
    assert "fmea_id" not in top
    assert "document_no" not in top
    assert "ap" not in top  # response_model_exclude_none=True 过滤了 null


# mask_name 边界测试（纯函数，不依赖 HTTP）
def test_mask_name_normal():
    assert mask_name("焊接不良") == "焊接***"


def test_mask_name_short_two_chars():
    assert mask_name("短路") == "短***"


def test_mask_name_short_one_char():
    assert mask_name("A") == "A***"


def test_mask_name_empty():
    assert mask_name("") == "***"


def test_mask_name_none():
    assert mask_name(None) == "***"


def test_mask_name_non_string():
    assert mask_name(123) == "***"
    assert mask_name([1, 2, 3]) == "***"


def test_mask_name_whitespace():
    assert mask_name("   ") == "***"


def test_mask_name_two_char_alphanumeric():
    assert mask_name("A1") == "A***"
```

- [ ] **Step 4: 运行测试**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m pytest tests/test_graph_api.py -v
```

Expected: 所有测试通过。

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_graph_api.py
git commit -m "test(graph): fix dependency override, add global-stats tests and mask_name boundary tests"
```

---

## Task 4: JSONBRepository 测试

**Files:**
- Create: `backend/tests/test_graph_repository.py`

**注意:** 测试 JSONBRepository 的 `get_global_stats` 和 `get_cross_fmea_stats`（验证 document_no 修复）。Neo4jRepository 无测试数据库环境，本期不测。

- [ ] **Step 1: 创建测试文件**

```python
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-graph-repo-tests")

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.graph.jsonb_repository import JSONBRepository


def _create_mock_db():
    """创建 mock AsyncSession。"""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _mock_fmea(document_no, product_line_code, graph_data):
    """构造 mock FMEADocument。"""
    fmea = MagicMock()
    fmea.fmea_id = "123e4567-e89b-12d3-a456-426614174000"
    fmea.document_no = document_no
    fmea.product_line_code = product_line_code
    fmea.graph_data = graph_data
    return fmea


@pytest.mark.asyncio
async def test_jsonb_get_cross_fmea_stats_top_failure_modes_has_document_no():
    """验证 JSONB get_cross_fmea_stats 的 top_failure_modes 包含 document_no。"""
    db = _create_mock_db()

    # Mock 一个包含 FailureMode 的 FMEA
    fmea = _mock_fmea(
        document_no="PFMEA-2026-001",
        product_line_code="DC-DC-100",
        graph_data={
            "nodes": [
                {"id": "fm1", "type": "FailureMode", "name": "焊接不良"},
                {"id": "e1", "type": "FailureEffect", "name": "开裂", "severity": 8},
                {"id": "c1", "type": "FailureCause", "name": "温度高", "occurrence": 5},
            ],
            "edges": [
                {"source": "fm1", "target": "e1", "type": "EFFECT_OF"},
                {"source": "c1", "target": "fm1", "type": "CAUSE_OF"},
            ],
        },
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fmea]
    db.execute.return_value = mock_result

    repo = JSONBRepository(db)
    stats = await repo.get_cross_fmea_stats("DC-DC-100")

    assert "top_failure_modes" in stats
    assert len(stats["top_failure_modes"]) == 1
    assert stats["top_failure_modes"][0]["document_no"] == "PFMEA-2026-001"


@pytest.mark.asyncio
async def test_jsonb_get_global_stats_aggregates_all_product_lines():
    """验证 JSONB get_global_stats 聚合所有产品线，不限制 product_line_code。"""
    db = _create_mock_db()

    fmea_a = _mock_fmea(
        document_no="PFMEA-2026-001",
        product_line_code="DC-DC-100",
        graph_data={
            "nodes": [
                {"id": "fm1", "type": "FailureMode", "name": "焊接不良"},
                {"id": "e1", "type": "FailureEffect", "name": "开裂", "severity": 8},
                {"id": "c1", "type": "FailureCause", "name": "温度高", "occurrence": 5},
            ],
            "edges": [
                {"source": "fm1", "target": "e1", "type": "EFFECT_OF"},
                {"source": "c1", "target": "fm1", "type": "CAUSE_OF"},
            ],
        },
    )
    fmea_b = _mock_fmea(
        document_no="PFMEA-2026-002",
        product_line_code="DC-DC-200",
        graph_data={
            "nodes": [
                {"id": "fm2", "type": "FailureMode", "name": "密封失效"},
                {"id": "e2", "type": "FailureEffect", "name": "漏水", "severity": 7},
                {"id": "c2", "type": "FailureCause", "name": "老化", "occurrence": 4},
            ],
            "edges": [
                {"source": "fm2", "target": "e2", "type": "EFFECT_OF"},
                {"source": "c2", "target": "fm2", "type": "CAUSE_OF"},
            ],
        },
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fmea_a, fmea_b]
    db.execute.return_value = mock_result

    repo = JSONBRepository(db)
    stats = await repo.get_global_stats()

    # 应包含两个产品线的所有文档
    assert stats["total_fmeas"] == 2
    assert stats["total_nodes"] == 6  # 3 nodes * 2 fmeas
    assert len(stats["top_failure_modes"]) == 2
    # top_failure_modes 应包含 document_no（来自 Task 3 的修复）
    for tm in stats["top_failure_modes"]:
        assert "document_no" in tm
```

- [ ] **Step 2: 运行测试**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m pytest tests/test_graph_repository.py -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_graph_repository.py
git commit -m "test(graph): add JSONBRepository tests for get_global_stats and document_no fix"
```

---

## Task 5: 构建验证

- [ ] **Step 1: 后端语法检查**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m py_compile app/graph/repository.py app/graph/neo4j_repository.py app/graph/jsonb_repository.py app/api/graph.py
```

Expected: No syntax errors.

- [ ] **Step 2: 运行全部相关测试**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m pytest tests/test_graph_api.py tests/test_graph_repository.py -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "feat(graph): global knowledge base masking complete — build and test verified"
```

---

## Self-Review

### 1. Spec Coverage

| Spec Section | 实现任务 |
|-------------|---------|
| `get_global_stats` 抽象方法 + 双实现 | Task 1 ✅ |
| Neo4j 实现（移除所有 $pl 过滤） | Task 1 Step 2 ✅ |
| JSONB 实现（不限制 product_line_code） | Task 1 Step 3 ✅ |
| `document_no` 缺陷修复 | Task 1 Step 3a ✅ |
| `mask_name()` 脱敏函数 | Task 2 ✅ |
| `_sanitize_global_stats()` 白名单重建 | Task 2 ✅ |
| `GlobalStatsOut` / `MaskedNodeOut` Schema | Task 2 ✅ |
| `/global-stats` 路由（require_admin, response_model_exclude_none） | Task 2 Step 3 ✅ |
| 权限测试（含 role_definition） | Task 3 ✅ |
| 脱敏字段测试 | Task 3 ✅ |
| `mask_name` 边界测试 | Task 3 ✅ |
| dependency override 修复（get_graph_repository） | Task 3 Step 1 ✅ |
| JSONBRepository 测试 | Task 4 ✅ |

### 2. Placeholder Scan

- 无 "TBD", "TODO", "implement later" ✅
- 无 "Add appropriate error handling" 等模糊描述 ✅
- 无 "Similar to Task N" 引用 ✅
- 所有代码块包含完整实现 ✅

### 3. Type Consistency

- `mask_name(name: Any)` — Task 2 和 Task 3 测试一致 ✅
- `_sanitize_global_stats(raw: dict) -> dict` — Task 2 定义，Task 2 Step 3 调用 ✅
- `GlobalStatsOut` / `MaskedNodeOut` — Task 2 定义，Task 2 Step 3 路由使用 ✅
- `get_global_stats()` — Task 1 定义和实现 ✅
- `response_model_exclude_none=True` — Task 2 Step 3 路由声明，Task 3 测试断言 `ap not in top` ✅
