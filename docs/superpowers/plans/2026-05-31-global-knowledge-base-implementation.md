# 全局知识库模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现跨产品线 FMEA 聚合查询 + 数据脱敏，补齐 stats/similar API 字段，构建前端全局知识库页面。

**Architecture:** 后端通过 `FMEAGraphRepository` 抽象层提供统一的 stats/similar 查询，JSONB 和 Neo4j 双实现同步补齐字段；API 层通过 Pydantic 白名单 ResponseModel 统一脱敏；前端通过独立页面展示统计卡片、风险列表和跨 FMEA 搜索。

**Tech Stack:** Python 3.11 + FastAPI | React 18 + TypeScript + Ant Design 5

---

## 文件结构

### 新增文件

| 文件 | 职责 |
|------|------|
| `frontend/src/api/graph.ts` | 图查询 API 客户端（axios） |
| `frontend/src/pages/graph/KnowledgeGraphPage.tsx` | 全局知识库页面（统计+列表+搜索） |

### 修改文件

| 文件 | 职责 |
|------|------|
| `backend/app/graph/jsonb_repository.py` | 补齐 `get_cross_fmea_stats` / `find_similar_nodes` 字段；复用 `compute_ap` |
| `backend/app/graph/neo4j_repository.py` | 补齐 `get_cross_fmea_stats` 字段；FMEDocument JOIN 获取 `document_no` |
| `backend/app/api/graph.py` | 添加 Pydantic 白名单 ResponseModel；产品线空值拦截 |
| `frontend/src/App.tsx` | 注册 `/knowledge-graph` 路由 |
| `frontend/src/components/layout/AppLayout.tsx` | 导航菜单添加"知识图谱"入口 |

---

## Task 1: JSONBRepository stats 字段补齐

**Files:**
- Modify: `backend/app/graph/jsonb_repository.py`

- [ ] **Step 1: 确认 `find_similar_nodes` 已返回 `document_no`**

检查当前代码第 43-50 行，确认 `document_no` 已在返回字典中：

```python
matches.append({
    "node_id": node["id"],
    "name": node["name"],
    "type": node["type"],
    "fmea_id": str(fmea.fmea_id),
    "document_no": fmea.document_no,
})
```

若缺失则添加，若已存在则跳过此步。

- [ ] **Step 2: 重写 `get_cross_fmea_stats` 补齐字段**

替换 `backend/app/graph/jsonb_repository.py` 中 `get_cross_fmea_stats` 方法（第 55-88 行）：

```python
    async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
        from app.state_machines.fmea_state import compute_ap

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
                    ap = compute_ap(s, o, d) if s > 0 and o > 0 and d > 0 else ""

                    if s > 0 and o > 0 and d > 0:
                        total_rpn += rpn
                        rpn_count += 1
                        top_failure_modes.append({
                            "name": node.get("name", ""),
                            "rpn": rpn,
                            "fmea_id": str(fmea.fmea_id),
                            "document_no": fmea.document_no,
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
        high_ap_nodes.sort(key=lambda x: x["rpn"], reverse=True)

        return {
            "total_fmeas": len(fmeas),
            "total_nodes": total_nodes,
            "node_type_distribution": type_counts,
            "ap_distribution": ap_counts,
            "high_ap_nodes": high_ap_nodes[:50],
            "avg_rpn": round(total_rpn / rpn_count, 1) if rpn_count > 0 else 0,
            "top_failure_modes": top_failure_modes[:10],
        }
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/graph/jsonb_repository.py
git commit -m "feat: JSONBRepository stats with AP distribution, high-risk nodes, and top failure modes"
```

---

## Task 2: Neo4jRepository stats 字段补齐

**Files:**
- Modify: `backend/app/graph/neo4j_repository.py`

- [ ] **Step 1: 重写 `get_cross_fmea_stats` 补齐字段**

替换 `backend/app/graph/neo4j_repository.py` 中 `get_cross_fmea_stats` 方法（第 55-92 行）：

```python
    async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
        from app.state_machines.fmea_state import compute_ap

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

            # FailureMode 节点全量（通过 FMEDocument JOIN 获取 document_no）
            fm_result = await session.run(
                "MATCH (d:FMEDocument)-[:HAS_NODE]->(n:GraphNode:FailureMode) "
                "WHERE n.product_line_code = $pl "
                "RETURN n.node_id AS node_id, n.name AS name, "
                "n.severity AS severity, n.occurrence AS occurrence, n.detection AS detection, "
                "n.fmea_id AS fmea_id, d.document_no AS document_no",
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
                ap = compute_ap(s, o, d) if s > 0 and o > 0 and d > 0 else ""

                if s > 0 and o > 0 and d > 0:
                    total_rpn += rpn
                    rpn_count += 1
                    top_failure_modes.append({
                        "name": rec.get("name", ""),
                        "rpn": rpn,
                        "fmea_id": rec.get("fmea_id", ""),
                        "document_no": rec.get("document_no", ""),
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
            high_ap_nodes.sort(key=lambda x: x["rpn"], reverse=True)

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
                "high_ap_nodes": high_ap_nodes[:50],
                "avg_rpn": round(total_rpn / rpn_count, 1) if rpn_count > 0 else 0,
                "top_failure_modes": top_failure_modes[:10],
            }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/graph/neo4j_repository.py
git commit -m "feat: Neo4jRepository stats with AP distribution, document_no via FMEDocument join"
```

---

## Task 3: API 白名单脱敏 + Pydantic DTO

**Files:**
- Modify: `backend/app/api/graph.py`

- [ ] **Step 1: 添加 Pydantic ResponseModel**

确认 `backend/app/api/graph.py` 已导入 `HTTPException`，然后添加 `BaseModel`：

```python
from pydantic import BaseModel


class SimilarNodeOut(BaseModel):
    node_id: str
    name: str
    type: str
    fmea_id: str
    document_no: str


class HighAPNodeOut(BaseModel):
    node_id: str
    name: str
    ap: str
    rpn: int
    fmea_id: str
    document_no: str


class TopFailureModeOut(BaseModel):
    name: str
    rpn: int
    fmea_id: str
    document_no: str


class CrossFmeaStatsOut(BaseModel):
    total_fmeas: int
    total_nodes: int
    node_type_distribution: dict[str, int]
    ap_distribution: dict[str, int]
    high_ap_nodes: list[HighAPNodeOut]
    avg_rpn: float
    top_failure_modes: list[TopFailureModeOut]
```

- [ ] **Step 2: 修改 `similar_nodes` 端点使用 ResponseModel**

将 `similar_nodes` 路由修改为：

```python
@router.get("/similar", response_model=list[SimilarNodeOut])
async def similar_nodes(
    node_type: str = Query(..., description="节点类型，如 FailureMode"),
    name_keyword: str = Query(..., min_length=1, description="名称关键词"),
    product_line_code: str = Query(..., min_length=1, description="产品线代码（必填，租户隔离）"),
    limit: int = Query(20, ge=1, le=100),
    repo: FMEAGraphRepository = Depends(_repo),
    _user: User = Depends(get_current_user),
):
    """跨 FMEA 搜索相似节点。product_line_code 必填且不能为空字符串。返回白名单字段。"""
    product_line_code = product_line_code.strip()
    if not product_line_code:
        raise HTTPException(status_code=422, detail="product_line_code cannot be empty")
    return await repo.find_similar_nodes(node_type, name_keyword, product_line_code, limit)
```

- [ ] **Step 3: 修改 `cross_fmea_stats` 端点使用 ResponseModel**

将 `cross_fmea_stats` 路由修改为：

```python
@router.get("/stats", response_model=CrossFmeaStatsOut)
async def cross_fmea_stats(
    product_line_code: str = Query(..., min_length=1, description="产品线代码（必填，租户隔离）"),
    repo: FMEAGraphRepository = Depends(_repo),
    _user: User = Depends(get_current_user),
):
    """跨 FMEA 聚合统计。product_line_code 必填且不能为空字符串。返回白名单字段。"""
    product_line_code = product_line_code.strip()
    if not product_line_code:
        raise HTTPException(status_code=422, detail="product_line_code cannot be empty")
    return await repo.get_cross_fmea_stats(product_line_code)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/graph.py
git commit -m "feat: graph API Pydantic whitelist response models for sanitization"
```

---

## Task 4: 前端 API 客户端

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
  top_failure_modes: Array<{
    name: string;
    rpn: number;
    fmea_id: string;
    document_no: string;
  }>;
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

## Task 5: 前端全局知识库页面

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
  Alert,
} from "antd";
import {
  FileTextOutlined,
  NodeIndexOutlined,
  WarningOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import {
  getCrossFmeaStats,
  searchSimilarNodes,
  type CrossFmeaStats,
  type SimilarNode,
} from "../../api/graph";
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

  const fetchStats = useCallback(async () => {
    if (!currentProductLine) return;
    setStatsLoading(true);
    try {
      const data = await getCrossFmeaStats(currentProductLine);
      setStats(data);
    } finally {
      setStatsLoading(false);
    }
  }, [currentProductLine]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const handleSearch = async () => {
    if (!searchKeyword.trim() || !currentProductLine) return;
    setSearchLoading(true);
    try {
      const results = await searchSimilarNodes({
        node_type: searchType,
        name_keyword: searchKeyword.trim(),
        product_line_code: currentProductLine,
        limit: 20,
      });
      setSearchResults(results);
    } finally {
      setSearchLoading(false);
    }
  };

  const handleViewGraph = (fmeaId: string, nodeId?: string) => {
    if (nodeId) {
      navigate(`/fmea/${fmeaId}?node=${nodeId}`);
    } else {
      navigate(`/fmea/${fmeaId}`);
    }
  };

  const apDist = stats?.ap_distribution || { H: 0, M: 0, L: 0 };

  if (!currentProductLine) {
    return (
      <div style={{ padding: 24 }}>
        <Title level={3}>全局知识库</Title>
        <Alert
          message="请选择产品线"
          description="请在顶部导航栏选择产品线以查看知识库数据。"
          type="info"
          showIcon
        />
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>全局知识库</Title>
      <p style={{ color: "#888" }}>产品线: {currentProductLine}</p>

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
            { title: "来源文档", dataIndex: "document_no", key: "document_no" },
            {
              title: "操作",
              key: "action",
              render: (_, record) => (
                <Button
                  type="link"
                  size="small"
                  onClick={() => handleViewGraph(record.fmea_id)}
                >
                  查看图谱
                </Button>
              ),
            },
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

## Task 6: 前端路由注册 + 导航菜单

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: App.tsx 导入并注册路由**

在 `frontend/src/App.tsx` 中：

1. 找到其他页面 import 的位置，添加：

```typescript
import KnowledgeGraphPage from "./pages/graph/KnowledgeGraphPage";
```

2. 在 Route 列表中（其他受保护路由附近）添加：

```tsx
<Route path="/knowledge-graph" element={<KnowledgeGraphPage />} />
```

- [ ] **Step 2: AppLayout.tsx 添加导航菜单项**

在 `frontend/src/components/layout/AppLayout.tsx` 的 `menuItems` 中，找到 "前期质量策划" 分组（`grp:planning`），在其 children 末尾添加：

```tsx
{ key: "/knowledge-graph", icon: <NodeIndexOutlined />, label: "知识图谱" },
```

确保 `NodeIndexOutlined` 已在文件顶部的 import 中（检查现有 imports，若缺失则添加）。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat: register /knowledge-graph route and sidebar menu entry"
```

---

## Task 7: 构建验证

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
python -c "from app.state_machines.fmea_state import compute_ap; print(compute_ap(10,10,10))"
```

Expected: 输出 `H`。

- [ ] **Step 3: 运行现有测试**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m pytest tests/test_fmea_state.py -v 2>/dev/null || python tests/test_fmea_state.py
```

Expected: 现有 AP 计算测试通过。

- [ ] **Step 4: Commit（如修复了任何问题）**

如有修复，单独提交。

---

## Self-Review

### 1. Spec coverage

| 设计文档需求 | 对应 Task |
|-------------|----------|
| AP 计算复用 `compute_ap` | Task 1, Task 2（import from fmea_state） |
| JSONBRepository stats 字段补齐 | Task 1 |
| Neo4jRepository stats 字段补齐 | Task 2 |
| 数据脱敏（Pydantic 白名单） | Task 3 |
| similar 返回 document_no | Task 1, Task 2, Task 3（验证） |
| 产品线空值拦截 | Task 3（API 422）+ Task 5（前端提示） |
| 跳转参数 `?node=` | Task 5 |
| Neo4j document_no JOIN | Task 2 |
| top_failure_modes 含 document_no | Task 1, Task 2 |
| stats 语义（排序/limit/空值） | Task 1, Task 2 |
| AppLayout 导航菜单 | Task 6 |
| 前端 API 客户端 | Task 4 |
| 前端全局知识库页面 | Task 5 |
| 路由注册 | Task 6 |
| 构建验证 | Task 7 |

**无遗漏。**

### 2. Placeholder scan

- 无 "TBD"/"TODO"
- 无 "add appropriate error handling" 等模糊描述
- 每个代码步骤都有完整代码
- 无 "Similar to Task N" 引用

### 3. Type consistency

- `CrossFmeaStats` / `SimilarNode` 接口与后端 ResponseModel 字段一致
- `high_ap_nodes` 字段名前后端一致
- `top_failure_modes` 含 `document_no` 前后端一致
- 跳转参数 `node=` 与 FMEAEditorPage `searchParams.get("node")` 一致
- `compute_ap` 函数名在 Task 1 和 Task 2 中一致

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-31-global-knowledge-base-implementation.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
