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
  tests/test_graph_api.py      # 新增 global-stats 测试用例
```

---

## Task 1: Repository 抽象接口 — 新增 `get_global_stats`

**Files:**
- Modify: `backend/app/graph/repository.py`

- [ ] **Step 1: 在 `FMEAGraphRepository` 中添加抽象方法**

在 `get_cross_fmea_stats` 之后、`analyze_change_impact` 之前插入：

```python
    @abstractmethod
    async def get_global_stats(self) -> dict:
        """跨产品线全局统计。返回结构与 get_cross_fmea_stats 相同。"""
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/graph/repository.py
git commit -m "feat(graph): add get_global_stats abstract method to FMEAGraphRepository"
```

---

## Task 2: Neo4jRepository 实现 `get_global_stats`

**Files:**
- Modify: `backend/app/graph/neo4j_repository.py`

**注意:** 与 `get_cross_fmea_stats` 基本一致，区别是**移除所有产品线过滤条件和 `$pl` 参数**。

- [ ] **Step 1: 添加 `get_global_stats` 方法**

在 `get_cross_fmea_stats` 之后插入：

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

- [ ] **Step 2: Commit**

```bash
git add backend/app/graph/neo4j_repository.py
git commit -m "feat(graph): implement get_global_stats in Neo4jRepository"
```

---

## Task 3: JSONBRepository 实现 `get_global_stats` + 修复 `document_no` 缺陷

**Files:**
- Modify: `backend/app/graph/jsonb_repository.py`

**注意:** 
1. `get_global_stats` 与 `get_cross_fmea_stats` 基本一致，只是查询时不限制 `product_line_code`
2. 顺带修复 `get_cross_fmea_stats` 中 `top_failure_modes` 缺失 `document_no`（line 175-179 只包含 `name`, `rpn`, `fmea_id`，需要加上 `document_no: fmea.document_no`）

- [ ] **Step 1: 修复 `get_cross_fmea_stats` 中 `top_failure_modes` 缺失 `document_no`**

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

- [ ] **Step 2: 添加 `get_global_stats` 方法**

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

- [ ] **Step 3: Commit**

```bash
git add backend/app/graph/jsonb_repository.py
git commit -m "feat(graph): implement get_global_stats in JSONBRepository + fix missing document_no in top_failure_modes"
```

---

## Task 4: API Schema + 脱敏函数

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

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/graph.py
git commit -m "feat(graph): add GlobalStatsOut, MaskedNodeOut, mask_name and _sanitize_global_stats"
```

---

## Task 5: API 路由 `/global-stats`

**Files:**
- Modify: `backend/app/api/graph.py`

- [ ] **Step 1: 添加路由**

在 `/stats` 路由之后、`/rebuild` 路由之前插入：

```python
@router.get("/global-stats", response_model=GlobalStatsOut)
async def global_stats(
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    _user: User = Depends(require_admin),
):
    """跨产品线全局知识库统计（Admin Only）。返回数据已脱敏。"""
    raw = await repo.get_global_stats()
    return _sanitize_global_stats(raw)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/graph.py
git commit -m "feat(graph): add /global-stats endpoint (admin only, sanitized)"
```

---

## Task 6: 测试

**Files:**
- Modify: `backend/tests/test_graph_api.py`

- [ ] **Step 1: 在 `StubGraphRepo` 中添加 `get_global_stats`**

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

- [ ] **Step 2: 添加测试用例**

在文件末尾添加：

```python
@pytest.mark.asyncio
async def test_global_stats_admin_only(client: AsyncClient):
    """验证 /global-stats 仅 admin 可访问。"""
    # 默认 client 使用 admin 角色，先验证 200
    resp = await client.get("/api/graph/global-stats")
    assert resp.status_code == status.HTTP_200_OK

    # 切换为 non-admin 角色
    async def _non_admin_user():
        from app.models.user import User
        return User(
            user_id="00000000-0000-0000-0000-000000000002",
            username="viewer",
            display_name="Viewer",
            email="viewer@openqms.local",
            password_hash="hashed",
            is_active=True,
            role="viewer",
        )

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

    # top_failure_modes 脱敏检查
    top = data["top_failure_modes"][0]
    assert "name" in top
    assert top["name"].endswith("***")
    assert "fmea_id" not in top
    assert "document_no" not in top


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

- [ ] **Step 3: 运行测试**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m pytest tests/test_graph_api.py -v
```

Expected: 所有测试通过。

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_graph_api.py
git commit -m "test(graph): add global-stats admin/sanitization tests and mask_name boundary tests"
```

---

## Task 7: 构建验证

- [ ] **Step 1: 后端语法检查**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m py_compile app/graph/repository.py app/graph/neo4j_repository.py app/graph/jsonb_repository.py app/api/graph.py
```

Expected: No syntax errors.

- [ ] **Step 2: 运行测试**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m pytest tests/test_graph_api.py -v
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
| `get_global_stats` 抽象方法 | Task 1 ✅ |
| Neo4j 实现（移除所有 $pl 过滤） | Task 2 ✅ |
| JSONB 实现（不限制 product_line_code） | Task 3 ✅ |
| `document_no` 缺陷修复 | Task 3 Step 1 ✅ |
| `mask_name()` 脱敏函数 | Task 4 ✅ |
| `_sanitize_global_stats()` 白名单重建 | Task 4 ✅ |
| `GlobalStatsOut` / `MaskedNodeOut` Schema | Task 4 ✅ |
| `/global-stats` 路由（require_admin） | Task 5 ✅ |
| 权限测试 | Task 6 ✅ |
| 脱敏字段测试 | Task 6 ✅ |
| `mask_name` 边界测试 | Task 6 ✅ |

### 2. Placeholder Scan

- 无 "TBD", "TODO", "implement later" ✅
- 无 "Add appropriate error handling" 等模糊描述 ✅
- 无 "Similar to Task N" 引用 ✅
- 所有代码块包含完整实现 ✅

### 3. Type Consistency

- `mask_name(name: Any)` — Task 4 和 Task 6 测试一致 ✅
- `_sanitize_global_stats(raw: dict) -> dict` — Task 4 定义，Task 5 调用 ✅
- `GlobalStatsOut` / `MaskedNodeOut` — Task 4 定义，Task 5 路由使用 ✅
- `get_global_stats()` — Task 1 定义，Task 2/3 实现 ✅
