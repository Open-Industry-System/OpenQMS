# 全局知识库模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现跨产品线 FMEA 聚合查询 + 数据脱敏，补齐 stats/similar API 字段，构建前端全局知识库页面。

**Architecture:** 后端通过 `FMEAGraphRepository` 抽象层提供统一的 stats/similar 查询，JSONB 和 Neo4j 双实现同步补齐字段；API 层统一脱敏；前端通过独立页面展示统计卡片、风险列表和跨 FMEA 搜索。

**Tech Stack:** Python 3.11 + FastAPI | React 18 + TypeScript + Ant Design 5

---

## 文件结构

### 新增文件

| 文件 | 职责 |
|------|------|
| `backend/app/utils/ap_calculator.py` | AIAG-VDA AP 计算工具函数 |
| `frontend/src/api/graph.ts` | 图查询 API 客户端（axios） |
| `frontend/src/pages/graph/KnowledgeGraphPage.tsx` | 全局知识库页面（统计+列表+搜索） |

### 修改文件

| 文件 | 职责 |
|------|------|
| `backend/app/graph/jsonb_repository.py` | 补齐 `get_cross_fmea_stats` / `find_similar_nodes` 字段 |
| `backend/app/graph/neo4j_repository.py` | 补齐 `get_cross_fmea_stats` 字段 |
| `backend/app/api/graph.py` | 添加脱敏中间层、返回字段对齐 |
| `frontend/src/App.tsx` | 注册 `/knowledge-graph` 路由 |

---

## Task 1: 后端 AP 计算工具

**Files:**
- Create: `backend/app/utils/ap_calculator.py`
- Test: `backend/app/test_schema.py`（复用现有测试文件，追加 AP 测试）

- [ ] **Step 1: 实现 AP 计算函数**

创建 `backend/app/utils/ap_calculator.py`：

```python
"""AIAG-VDA FMEA Action Priority (AP) 计算工具.

Ref: AIAG-VDA FMEA Handbook (2019) Appendix C1.5
与前端 frontend/src/utils/fmea.ts calculateAP 逻辑严格一致.
"""


def calculate_ap(s: int, o: int, d: int) -> str:
    """Calculate Action Priority based on Severity, Occurrence, Detection.

    Returns:
        'H' (High), 'M' (Medium), 'L' (Low), or '' (if out of 1-10 range).
    """
    if s < 1 or s > 10 or o < 1 or o > 10 or d < 1 or d > 10:
        return ""

    # Severity 9-10
    if s >= 9:
        if o >= 4:
            return "H"
        if o in (3, 2):
            return "H" if d >= 7 else "M" if d >= 5 else "L"
        return "L"  # o == 1

    # Severity 7-8
    if s >= 7:
        if o >= 8:
            return "H"
        if o in (6, 7):
            return "H" if d >= 2 else "M"
        if o in (4, 5):
            return "H" if d >= 7 else "M"
        if o in (2, 3):
            return "M" if d >= 5 else "L"
        return "L"  # o == 1

    # Severity 4-6
    if s >= 4:
        if o >= 8:
            return "H" if d >= 5 else "M"
        if o in (6, 7):
            return "M" if d >= 2 else "L"
        if o in (4, 5):
            return "M" if d >= 7 else "L"
        return "L"  # o <= 3

    # Severity 1-3
    if o >= 8:
        return "M" if d >= 5 else "L"
    return "L"
```

- [ ] **Step 2: 追加测试到现有测试文件**

在 `backend/app/test_schema.py` 末尾追加：

```python
from app.utils.ap_calculator import calculate_ap


def test_calculate_ap_boundary():
    assert calculate_ap(10, 10, 10) == "H"
    assert calculate_ap(1, 1, 1) == "L"
    assert calculate_ap(0, 5, 5) == ""
    assert calculate_ap(5, 0, 5) == ""
    assert calculate_ap(5, 5, 0) == ""


def test_calculate_ap_high_severity():
    # s=9, o=4 -> H regardless of D
    assert calculate_ap(9, 4, 1) == "H"
    # s=9, o=3, d=7 -> H
    assert calculate_ap(9, 3, 7) == "H"
    # s=9, o=3, d=5 -> M
    assert calculate_ap(9, 3, 5) == "M"
    # s=9, o=3, d=4 -> L
    assert calculate_ap(9, 3, 4) == "L"
    # s=9, o=1 -> L
    assert calculate_ap(9, 1, 10) == "L"


def test_calculate_ap_medium_severity():
    # s=7, o=8 -> H
    assert calculate_ap(7, 8, 1) == "H"
    # s=7, o=6, d=2 -> H
    assert calculate_ap(7, 6, 2) == "H"
    # s=7, o=6, d=1 -> M
    assert calculate_ap(7, 6, 1) == "M"
    # s=7, o=2, d=5 -> M
    assert calculate_ap(7, 2, 5) == "M"
    # s=7, o=2, d=4 -> L
    assert calculate_ap(7, 2, 4) == "L"


def test_calculate_ap_low_severity():
    # s=4, o=8, d=5 -> H
    assert calculate_ap(4, 8, 5) == "H"
    # s=4, o=8, d=4 -> M
    assert calculate_ap(4, 8, 4) == "M"
    # s=4, o=6, d=2 -> M
    assert calculate_ap(4, 6, 2) == "M"
    # s=4, o=6, d=1 -> L
    assert calculate_ap(4, 6, 1) == "L"
    # s=3, o=8, d=5 -> M
    assert calculate_ap(3, 8, 5) == "M"
    # s=3, o=8, d=4 -> L
    assert calculate_ap(3, 8, 4) == "L"
    # s=1, o=1, d=1 -> L
    assert calculate_ap(1, 1, 1) == "L"
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python app/test_schema.py
```

Expected: All tests pass including the new AP tests.

- [ ] **Step 4: Commit**

```bash
git add backend/app/utils/ap_calculator.py backend/app/test_schema.py
git commit -m "feat: AP calculator utility with AIAG-VDA lookup table"
```

---

## Task 2: JSONBRepository 字段补齐

**Files:**
- Modify: `backend/app/graph/jsonb_repository.py`

- [ ] **Step 1: 修改 `find_similar_nodes` 返回 `document_no`**

当前代码第 43-50 行：

```python
matches.append({
    "node_id": node["id"],
    "name": node["name"],
    "type": node["type"],
    "fmea_id": str(fmea.fmea_id),
    "document_no": fmea.document_no,  # 确认已有此行
})
```

验证 `document_no` 已在返回字典中。若缺失则添加。

- [ ] **Step 2: 重写 `get_cross_fmea_stats` 补齐字段**

替换 `backend/app/graph/jsonb_repository.py` 中 `get_cross_fmea_stats` 方法（第 55-88 行）：

```python
    async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
        from app.utils.ap_calculator import calculate_ap

        query = select(FMEADocument).where(FMEADocument.product_line_code == product_line_code)
        result = await self._db.execute(query)
        fmeas = result.scalars().all()

        type_counts: dict[str, int] = {}
        high_ap_nodes: list[dict] = []
        top_failure_modes: list[dict] = []
        total_nodes = 0
        total_rpn = 0
        rpn_count = 0
        ap_counts = {"H": 0, "M": 0, "L": 0}

        for fmea in fmeas:
            if not fmea.graph_data:
                continue
            for node in fmea.graph_data.get("nodes", []):
                total_nodes += 1
                t = node.get("type", "Unknown")
                type_counts[t] = type_counts.get(t, 0) + 1

                if node.get("type") == "FailureMode":
                    s = node.get("severity", 0) or 0
                    o = node.get("occurrence", 0) or 0
                    d = node.get("detection", 0) or 0
                    rpn = s * o * d
                    ap = calculate_ap(s, o, d)

                    if rpn > 0:
                        total_rpn += rpn
                        rpn_count += 1
                        top_failure_modes.append({
                            "name": node.get("name", ""),
                            "rpn": rpn,
                            "fmea_id": str(fmea.fmea_id),
                        })

                    if ap:
                        ap_counts[ap] = ap_counts.get(ap, 0) + 1
                        if ap == "H":
                            high_ap_nodes.append({
                                "node_id": node.get("id", ""),
                                "name": node.get("name", ""),
                                "ap": ap,
                                "rpn": rpn,
                                "fmea_id": str(fmea.fmea_id),
                                "document_no": fmea.document_no,
                            })

        top_failure_modes.sort(key=lambda x: x["rpn"], reverse=True)

        return {
            "total_fmeas": len(fmeas),
            "total_nodes": total_nodes,
            "node_type_distribution": type_counts,
            "ap_distribution": ap_counts,
            "high_ap_nodes": high_ap_nodes[:20],
            "avg_rpn": round(total_rpn / rpn_count, 1) if rpn_count > 0 else 0,
            "top_failure_modes": top_failure_modes[:10],
        }
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/graph/jsonb_repository.py
git commit -m "feat: JSONBRepository stats with AP distribution and high-risk nodes"
```

---

## Task 3: Neo4jRepository stats 字段补齐

**Files:**
- Modify: `backend/app/graph/neo4j_repository.py`

- [ ] **Step 1: 重写 `get_cross_fmea_stats` 补齐字段**

替换 `backend/app/graph/neo4j_repository.py` 中 `get_cross_fmea_stats` 方法（第 55-92 行）：

```python
    async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
        from app.utils.ap_calculator import calculate_ap

        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            # 节点类型分布
            type_result = await session.run(
                "MATCH (n:GraphNode) WHERE n.product_line_code = $pl "
                "RETURN n.type AS type, count(*) AS cnt "
                "ORDER BY cnt DESC",
                pl=product_line_code,
            )
            type_records = await type_result.data()
            type_dist = {r["type"]: r["cnt"] for r in type_records}

            # FailureMode 节点全量（用于 AP 计算和统计）
            fm_result = await session.run(
                "MATCH (n:GraphNode:FailureMode) WHERE n.product_line_code = $pl "
                "RETURN n.node_id AS node_id, n.name AS name, "
                "n.severity AS severity, n.occurrence AS occurrence, n.detection AS detection, "
                "n.fmea_id AS fmea_id, n.document_no AS document_no",
                pl=product_line_code,
            )
            fm_records = await fm_result.data()

            ap_counts = {"H": 0, "M": 0, "L": 0}
            high_ap_nodes: list[dict] = []
            top_failure_modes: list[dict] = []
            total_rpn = 0
            rpn_count = 0

            for rec in fm_records:
                s = rec.get("severity", 0) or 0
                o = rec.get("occurrence", 0) or 0
                d = rec.get("detection", 0) or 0
                rpn = s * o * d
                ap = calculate_ap(s, o, d)

                if rpn > 0:
                    total_rpn += rpn
                    rpn_count += 1
                    top_failure_modes.append({
                        "name": rec.get("name", ""),
                        "rpn": rpn,
                        "fmea_id": rec.get("fmea_id", ""),
                    })

                if ap:
                    ap_counts[ap] = ap_counts.get(ap, 0) + 1
                    if ap == "H":
                        high_ap_nodes.append({
                            "node_id": rec.get("node_id", ""),
                            "name": rec.get("name", ""),
                            "ap": ap,
                            "rpn": rpn,
                            "fmea_id": rec.get("fmea_id", ""),
                            "document_no": rec.get("document_no", ""),
                        })

            top_failure_modes.sort(key=lambda x: x["rpn"], reverse=True)

            # FMEA 文档数
            doc_result = await session.run(
                "MATCH (d:FMEDocument) WHERE d.product_line_code = $pl RETURN count(*) AS cnt",
                pl=product_line_code,
            )
            doc_records = await doc_result.data()

            total_nodes = sum(type_dist.values())

            return {
                "total_fmeas": doc_records[0]["cnt"] if doc_records else 0,
                "total_nodes": total_nodes,
                "node_type_distribution": type_dist,
                "ap_distribution": ap_counts,
                "high_ap_nodes": high_ap_nodes[:20],
                "avg_rpn": round(total_rpn / rpn_count, 1) if rpn_count > 0 else 0,
                "top_failure_modes": top_failure_modes[:10],
            }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/graph/neo4j_repository.py
git commit -m "feat: Neo4jRepository stats with AP distribution and high-risk nodes"
```

---

## Task 4: API 脱敏层 + similar 字段补齐

**Files:**
- Modify: `backend/app/api/graph.py`

- [ ] **Step 1: 添加脱敏辅助函数**

在 `backend/app/api/graph.py` 的 `_repo` 函数之后、路由之前添加：

```python

# 全局查询脱敏：过滤敏感字段
_SENSITIVE_KEYS = {"created_by", "updated_by", "approved_by", "creator", "updater", "approver"}


def _sanitize_node(node: dict) -> dict:
    """对节点数据脱敏，移除人员相关敏感信息。"""
    if not isinstance(node, dict):
        return node
    return {k: v for k, v in node.items() if k not in _SENSITIVE_KEYS}


def _sanitize_similar_result(items: list[dict]) -> list[dict]:
    """similar 查询结果脱敏：仅保留必要字段。"""
    return [
        {
            "node_id": item.get("node_id"),
            "name": item.get("name"),
            "type": item.get("type"),
            "fmea_id": item.get("fmea_id"),
            "document_no": item.get("document_no"),
        }
        for item in items
    ]


def _sanitize_stats_result(data: dict) -> dict:
    """stats 查询结果脱敏：仅保留统计字段。"""
    # high_ap_nodes 中可能包含原始节点属性，需逐节点脱敏
    high_ap_nodes = data.get("high_ap_nodes", [])
    sanitized_nodes = [_sanitize_node(n) for n in high_ap_nodes]
    return {
        "total_fmeas": data.get("total_fmeas"),
        "total_nodes": data.get("total_nodes"),
        "node_type_distribution": data.get("node_type_distribution"),
        "ap_distribution": data.get("ap_distribution"),
        "high_ap_nodes": sanitized_nodes,
        "avg_rpn": data.get("avg_rpn"),
        "top_failure_modes": data.get("top_failure_modes", []),
    }
```

- [ ] **Step 2: 修改 similar_nodes 端点应用脱敏**

将 `similar_nodes` 路由修改为：

```python
@router.get("/similar")
async def similar_nodes(
    node_type: str = Query(..., description="节点类型，如 FailureMode"),
    name_keyword: str = Query(..., min_length=1, description="名称关键词"),
    product_line_code: str = Query(..., description="产品线代码（必填，租户隔离）"),
    limit: int = Query(20, ge=1, le=100),
    repo: FMEAGraphRepository = Depends(_repo),
    _user: User = Depends(get_current_user),
):
    """跨 FMEA 搜索相似节点。product_line_code 必填。返回已脱敏数据。"""
    raw = await repo.find_similar_nodes(node_type, name_keyword, product_line_code, limit)
    return _sanitize_similar_result(raw)
```

- [ ] **Step 3: 修改 cross_fmea_stats 端点应用脱敏**

将 `cross_fmea_stats` 路由修改为：

```python
@router.get("/stats")
async def cross_fmea_stats(
    product_line_code: str = Query(..., description="产品线代码（必填，租户隔离）"),
    repo: FMEAGraphRepository = Depends(_repo),
    _user: User = Depends(get_current_user),
):
    """跨 FMEA 聚合统计。product_line_code 必填。返回已脱敏数据。"""
    raw = await repo.get_cross_fmea_stats(product_line_code)
    return _sanitize_stats_result(raw)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/graph.py
git commit -m "feat: graph API sanitization for global queries"
```

---

## Task 5: 前端 API 客户端

**Files:**
- Create: `frontend/src/api/graph.ts`

- [ ] **Step 1: 创建 graph API 客户端**

```typescript
import client from "./client";

export interface ImpactChainResponse {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
}

export interface SimilarNode {
  node_id: string;
  name: string;
  type: string;
  fmea_id: string;
  document_no: string;
}

export interface CrossFmeaStats {
  total_fmeas: number;
  total_nodes: number;
  node_type_distribution: Record<string, number>;
  ap_distribution: { H: number; M: number; L: number };
  high_ap_nodes: Array<{
    node_id: string;
    name: string;
    ap: string;
    rpn: number;
    fmea_id: string;
    document_no: string;
  }>;
  avg_rpn: number;
  top_failure_modes: Array<{ name: string; rpn: number; fmea_id: string }>;
}

export async function getImpactChain(
  fmeaId: string,
  nodeId: string
): Promise<ImpactChainResponse> {
  const res = await client.get(`/graph/fmea/${fmeaId}/impact/${nodeId}`);
  return res.data;
}

export async function getCauseChain(
  fmeaId: string,
  nodeId: string
): Promise<ImpactChainResponse> {
  const res = await client.get(`/graph/fmea/${fmeaId}/cause/${nodeId}`);
  return res.data;
}

export async function searchSimilarNodes(params: {
  node_type: string;
  name_keyword: string;
  product_line_code: string;
  limit?: number;
}): Promise<SimilarNode[]> {
  const res = await client.get("/graph/similar", { params });
  return res.data;
}

export async function getCrossFmeaStats(
  productLineCode: string
): Promise<CrossFmeaStats> {
  const res = await client.get("/graph/stats", {
    params: { product_line_code: productLineCode },
  });
  return res.data;
}

export async function triggerRebuild(): Promise<{ message: string }> {
  const res = await client.post("/graph/rebuild");
  return res.data;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/graph.ts
git commit -m "feat: frontend graph API client"
```

---

## Task 6: 前端全局知识库页面

**Files:**
- Create: `frontend/src/pages/graph/KnowledgeGraphPage.tsx`

- [ ] **Step 1: 创建页面文件**

```tsx
import React, { useEffect, useState, useCallback } from "react";
import {
  Card,
  Row,
  Col,
  Statistic,
  Table,
  Input,
  Select,
  Space,
  Typography,
  Spin,
  Empty,
  Tag,
  Button,
} from "antd";
import {
  FileTextOutlined,
  NodeIndexOutlined,
  WarningOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { getCrossFmeaStats, searchSimilarNodes, type CrossFmeaStats, type SimilarNode } from "../../api/graph";
import { useProductLineStore } from "../../store/productLineStore";

const { Title } = Typography;
const { Option } = Select;

const NODE_TYPE_OPTIONS = [
  "FailureMode",
  "FailureEffect",
  "FailureCause",
  "Function",
  "Control",
  "ProcessItem",
  "ProcessStep",
  "ProcessWorkElement",
  "System",
  "Subsystem",
  "Component",
];

const AP_COLOR_MAP: Record<string, string> = {
  H: "red",
  M: "orange",
  L: "green",
};

const KnowledgeGraphPage: React.FC = () => {
  const navigate = useNavigate();
  const { currentProductLine } = useProductLineStore();

  const [stats, setStats] = useState<CrossFmeaStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const [searchKeyword, setSearchKeyword] = useState("");
  const [searchType, setSearchType] = useState("FailureMode");
  const [searchResults, setSearchResults] = useState<SimilarNode[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  const productLineCode = currentProductLine || "DC-DC-100";

  const fetchStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const data = await getCrossFmeaStats(productLineCode);
      setStats(data);
    } finally {
      setStatsLoading(false);
    }
  }, [productLineCode]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const handleSearch = async () => {
    if (!searchKeyword.trim()) return;
    setSearchLoading(true);
    try {
      const results = await searchSimilarNodes({
        node_type: searchType,
        name_keyword: searchKeyword.trim(),
        product_line_code: productLineCode,
        limit: 20,
      });
      setSearchResults(results);
    } finally {
      setSearchLoading(false);
    }
  };

  const handleViewGraph = (fmeaId: string, nodeId?: string) => {
    if (nodeId) {
      navigate(`/fmea/${fmeaId}?tab=graph&highlightNode=${nodeId}`);
    } else {
      navigate(`/fmea/${fmeaId}?tab=graph`);
    }
  };

  const apDist = stats?.ap_distribution || { H: 0, M: 0, L: 0 };

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>全局知识库</Title>
      <p style={{ color: "#888" }}>产品线: {productLineCode}</p>

      <Spin spinning={statsLoading}>
        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="FMEA 文档数"
                value={stats?.total_fmeas || 0}
                prefix={<FileTextOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="节点总数"
                value={stats?.total_nodes || 0}
                prefix={<NodeIndexOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="平均 RPN"
                value={stats?.avg_rpn || 0}
                precision={1}
                prefix={<WarningOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <div style={{ fontSize: 14, color: "#00000073", marginBottom: 8 }}>
                AP 分布
              </div>
              <Space>
                <Tag color="red">H: {apDist.H}</Tag>
                <Tag color="orange">M: {apDist.M}</Tag>
                <Tag color="green">L: {apDist.L}</Tag>
              </Space>
            </Card>
          </Col>
        </Row>
      </Spin>

      <Card title="跨 FMEA 节点搜索" style={{ marginBottom: 24 }}>
        <Space.Compact style={{ width: "100%", maxWidth: 600 }}>
          <Select
            value={searchType}
            onChange={setSearchType}
            style={{ width: 160 }}
          >
            {NODE_TYPE_OPTIONS.map((t) => (
              <Option key={t} value={t}>
                {t}
              </Option>
            ))}
          </Select>
          <Input
            placeholder="输入节点名称关键词"
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            onPressEnter={handleSearch}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
            搜索
          </Button>
        </Space.Compact>

        <div style={{ marginTop: 16 }}>
          {searchResults.length === 0 && !searchLoading && searchKeyword && (
            <Empty description="未找到匹配节点" />
          )}
          {searchResults.length > 0 && (
            <Table
              dataSource={searchResults}
              rowKey="node_id"
              loading={searchLoading}
              size="small"
              pagination={{ pageSize: 10 }}
              columns={[
                { title: "名称", dataIndex: "name", key: "name" },
                { title: "类型", dataIndex: "type", key: "type" },
                { title: "来源文档", dataIndex: "document_no", key: "document_no" },
                {
                  title: "操作",
                  key: "action",
                  render: (_, record) => (
                    <Button
                      type="link"
                      size="small"
                      onClick={() => handleViewGraph(record.fmea_id, record.node_id)}
                    >
                      查看图谱
                    </Button>
                  ),
                },
              ]}
            />
          )}
        </div>
      </Card>

      <Card title="高风险节点 (AP = H)" style={{ marginBottom: 24 }}>
        <Table
          dataSource={stats?.high_ap_nodes || []}
          rowKey="node_id"
          loading={statsLoading}
          size="small"
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "名称", dataIndex: "name", key: "name" },
            {
              title: "RPN",
              dataIndex: "rpn",
              key: "rpn",
              sorter: (a, b) => a.rpn - b.rpn,
            },
            {
              title: "AP",
              dataIndex: "ap",
              key: "ap",
              render: (ap: string) => <Tag color={AP_COLOR_MAP[ap] || "default"}>{ap}</Tag>,
            },
            { title: "来源文档", dataIndex: "document_no", key: "document_no" },
            {
              title: "操作",
              key: "action",
              render: (_, record) => (
                <Button
                  type="link"
                  size="small"
                  onClick={() => handleViewGraph(record.fmea_id, record.node_id)}
                >
                  查看图谱
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card title="TOP10 失效模式">
        <Table
          dataSource={stats?.top_failure_modes || []}
          rowKey={(record, index) => `${record.fmea_id}-${index}`}
          loading={statsLoading}
          size="small"
          pagination={false}
          columns={[
            { title: "名称", dataIndex: "name", key: "name" },
            {
              title: "RPN",
              dataIndex: "rpn",
              key: "rpn",
            },
            { title: "FMEA ID", dataIndex: "fmea_id", key: "fmea_id" },
          ]}
        />
      </Card>
    </div>
  );
};

export default KnowledgeGraphPage;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/graph/KnowledgeGraphPage.tsx
git commit -m "feat: global knowledge base page with stats, search, and risk list"
```

---

## Task 7: 前端路由注册

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 导入并注册路由**

在 `frontend/src/App.tsx` 中：

1. 找到其他页面 import 的位置，添加：

```typescript
import KnowledgeGraphPage from "./pages/graph/KnowledgeGraphPage";
```

2. 在 Route 列表中（其他受保护路由附近）添加：

```tsx
<Route path="/knowledge-graph" element={<KnowledgeGraphPage />} />
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: register /knowledge-graph route"
```

---

## Task 8: 构建验证

**Files:** 无新增/修改，仅验证

- [ ] **Step 1: 前端构建检查**

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npm run build
```

Expected: `tsc --noEmit` 通过，vite build 成功，无 TypeScript 错误。

- [ ] **Step 2: 后端启动检查**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -c "from app.utils.ap_calculator import calculate_ap; print(calculate_ap(10,10,10))"
```

Expected: 输出 `H`。

- [ ] **Step 3: Commit（如修复了任何问题）**

如有修复，单独提交。

---

## Self-Review

### 1. Spec coverage

| 设计文档需求 | 对应 Task |
|-------------|----------|
| AP 计算工具 | Task 1 |
| JSONBRepository stats 字段补齐 | Task 2 |
| Neo4jRepository stats 字段补齐 | Task 3 |
| 数据脱敏 | Task 4 |
| similar 返回 document_no | Task 2, Task 3（验证）, Task 4（脱敏保留） |
| 前端 API 客户端 | Task 5 |
| 前端全局知识库页面 | Task 6 |
| 路由注册 | Task 7 |
| 构建验证 | Task 8 |

**无遗漏。**

### 2. Placeholder scan

- 无 "TBD"/"TODO"
- 无 "add appropriate error handling" 等模糊描述
- 每个代码步骤都有完整代码
- 无 "Similar to Task N" 引用

### 3. Type consistency

- `CrossFmeaStats` 接口与后端返回字段一致
- `SimilarNode` 接口与 `_sanitize_similar_result` 返回字段一致
- `high_ap_nodes` 字段名前后端一致（`node_id`, `name`, `ap`, `rpn`, `fmea_id`, `document_no`）
- `calculate_ap` 函数名在 ap_calculator.py、jsonb_repository.py、neo4j_repository.py 中一致

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-31-global-knowledge-base-implementation.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
