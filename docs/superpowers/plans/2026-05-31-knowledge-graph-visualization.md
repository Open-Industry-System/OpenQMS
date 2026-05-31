# 知识图谱可视化前端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 OpenQMS 添加交互式 FMEA 知识图谱可视化能力，包含 FMEA 编辑器内嵌图谱 Tab 和独立全局知识图谱页。

**Architecture:** 基于 AntV G6 v5 构建共享 `GraphCanvas` 组件，两个入口（编辑器内嵌 + 独立页面）复用同一套组件。全局页首版以统计卡片 + 数据列表 + 搜索为核心，单 FMEA 详细图谱通过链接跳转展示。

**Tech Stack:** React 18 + TypeScript + Vite + Ant Design 5.x + AntV G6 v5

---

## 文件结构

```
frontend/src/
├── api/graph.ts                    # 图查询 API 客户端（新增）
├── components/graph/
│   ├── GraphCanvas.tsx             # 共享 G6 画布（核心，新增）
│   ├── GraphToolbar.tsx            # 工具栏（新增）
│   ├── NodeDetailDrawer.tsx        # 节点详情侧边栏（新增）
│   ├── GraphLegend.tsx             # 图例（新增）
│   └── index.ts                    # 组件统一导出（新增）
├── pages/graph/
│   └── KnowledgeGraphPage.tsx      # 独立全局知识图谱页（新增）
├── pages/planning/fmea/
│   └── FMEAEditorPage.tsx          # 添加"图谱"Tab（修改）
├── App.tsx                         # 添加 /knowledge-graph 路由（修改）
└── components/layout/AppLayout.tsx # 添加侧边栏菜单项（修改）
```

---

## Task 1: 安装 AntV G6 依赖

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: 安装依赖**

```bash
cd frontend
npm install @antv/g6
```

- [ ] **Step 2: 验证安装**

```bash
npm ls @antv/g6
```
Expected: `@antv/g6@5.x.x` 已安装

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "deps: add @antv/g6 for knowledge graph visualization"
```

---

## Task 2: 创建图查询 API 客户端

**Files:**
- Create: `frontend/src/api/graph.ts`

**上下文:** 参照 `frontend/src/api/fmea.ts` 的 axios client 调用模式。

- [ ] **Step 1: 创建 API 文件**

Create `frontend/src/api/graph.ts`:

```typescript
import client from "./client";

// ========== 原始数据类型（后端返回的多种格式）==========
export interface RawGraphNode {
  id?: string;
  node_id?: string;
  type?: string;
  label?: string;
  name?: string;
  severity?: number;
  occurrence?: number;
  detection?: number;
  ap?: string;
  [key: string]: unknown;
}

export interface RawGraphEdge {
  source: string;
  target: string;
  type?: string;
  label?: string;
}

// ========== 渲染数据类型（GraphCanvas 统一消费）==========
export interface RenderGraphNode {
  id: string;
  label: string;           // 对应 type/label，用于映射颜色和形状
  properties: {
    name: string;
    severity?: number;
    occurrence?: number;
    detection?: number;
    ap?: string;
    [key: string]: unknown;
  };
  style?: unknown;
}

export interface RenderGraphEdge {
  source: string;
  target: string;
  label: string;
  properties?: Record<string, unknown>;
}

// ========== 转换层（抹平 JSONB 扁平结构 vs Neo4j 嵌套结构）==========
export function normalizeGraphData(
  rawNodes: Array<Record<string, unknown>>,
  rawEdges: Array<Record<string, unknown>>
): { nodes: RenderGraphNode[]; edges: RenderGraphEdge[] } {
  return {
    nodes: rawNodes.map((n) => {
      const id = (n.id as string) ?? (n.node_id as string) ?? "";
      const label = (n.type as string) ?? (n.label as string) ?? "";
      const props = (n.properties as Record<string, unknown>) ?? n;
      return {
        id,
        label,
        properties: {
          name: (props.name as string) ?? (n.name as string) ?? "",
          severity: (props.severity as number) ?? (n.severity as number),
          occurrence: (props.occurrence as number) ?? (n.occurrence as number),
          detection: (props.detection as number) ?? (n.detection as number),
          ap: (props.ap as string) ?? (n.ap as string),
          ...props,
        },
        style: undefined,
      };
    }),
    edges: rawEdges.map((e) => ({
      source: (e.source as string) ?? "",
      target: (e.target as string) ?? "",
      label: (e.type as string) ?? (e.label as string) ?? "",
      properties: undefined,
    })),
  };
}

// ========== 兼容别名（后续组件统一使用 GraphNode / GraphEdge）==========
export type GraphNode = RenderGraphNode;
export type GraphEdge = RenderGraphEdge;

// ========== API 返回类型（原始数据，需 normalize 后使用）==========
export interface GraphChainResponse {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
}

export interface SimilarNode {
  node_id: string;
  name: string;
  type: string;
  fmea_id: string;
  document_no?: string;
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
    document_no?: string;
  }>;
  avg_rpn: number;
  top_failure_modes: Array<{ name: string; rpn: number; fmea_id: string }>;
}

export async function getImpactChain(
  fmeaId: string,
  nodeId: string
): Promise<GraphChainResponse> {
  const resp = await client.get(`/graph/fmea/${fmeaId}/impact/${nodeId}`);
  return resp.data; // 返回原始数据，调用方需用 normalizeGraphData() 转换
}

export async function getCauseChain(
  fmeaId: string,
  nodeId: string
): Promise<GraphChainResponse> {
  const resp = await client.get(`/graph/fmea/${fmeaId}/cause/${nodeId}`);
  return resp.data; // 返回原始数据，调用方需用 normalizeGraphData() 转换
}

export async function searchSimilarNodes(params: {
  node_type: string;
  name_keyword: string;
  product_line_code: string;
  limit?: number;
}): Promise<SimilarNode[]> {
  const resp = await client.get("/graph/similar", { params });
  return resp.data;
}

export async function getCrossFmeaStats(
  productLineCode: string
): Promise<CrossFmeaStats> {
  const resp = await client.get("/graph/stats", {
    params: { product_line_code: productLineCode },
  });
  return resp.data;
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 无错误（可能需等待 GraphNode/GraphEdge 类型与现有 types/index.ts 兼容，如有冲突以 api/graph.ts 为准）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/graph.ts
git commit -m "feat(graph): add graph query API client with normalize adapter"
```

---

## Task 2a: 后端 stats DTO 更新（AP 优先口径）

**Files:**
- Modify: `backend/app/graph/jsonb_repository.py`
- Modify: `backend/app/graph/neo4j_repository.py`

**上下文:** 当前后端 `get_cross_fmea_stats` 返回 `high_risk_failure_modes`（RPN ≥ 100），与设计要求的 AP 优先口径不一致。需统一返回 `CrossFmeaStatsDTO`。

- [ ] **Step 1: 修改 JSONBRepository**

修改 `backend/app/graph/jsonb_repository.py` 的 `get_cross_fmea_stats` 方法：

```python
from app.state_machines.fmea_state import compute_ap

async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
    query = select(FMEADocument).where(FMEADocument.product_line_code == product_line_code)
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

            if t == "FailureMode":
                s = node.get("severity", 0) or 0
                o = node.get("occurrence", 0) or 0
                d = node.get("detection", 0) or 0
                rpn = s * o * d
                ap = compute_ap(s, o, d) if s > 0 and o > 0 and d > 0 else ""

                if rpn > 0:
                    total_rpn += rpn
                    rpn_count += 1
                    top_modes.append({"name": node.get("name", ""), "rpn": rpn, "fmea_id": str(fmea.fmea_id)})

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

- [ ] **Step 2: 修改 Neo4jRepository**

修改 `backend/app/graph/neo4j_repository.py` 的 `get_cross_fmea_stats` 方法，Cypher 查询增加 `n.ap` 和 `n.node_id` 字段：

```python
async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
    async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
        # 节点类型分布
        type_result = await session.run(
            "MATCH (n:GraphNode) WHERE n.product_line_code = $pl "
            "RETURN n.type AS type, count(*) AS cnt ORDER BY cnt DESC",
            pl=product_line_code,
        )
        type_records = await type_result.data()
        type_dist = {r["type"]: r["cnt"] for r in type_records}

        # AP 分布
        ap_result = await session.run(
            "MATCH (n:GraphNode:FailureMode) WHERE n.product_line_code = $pl "
            "RETURN n.ap AS ap, count(*) AS cnt",
            pl=product_line_code,
        )
        ap_records = await ap_result.data()
        ap_counts = {"H": 0, "M": 0, "L": 0}
        for r in ap_records:
            if r.get("ap") in ap_counts:
                ap_counts[r["ap"]] = r["cnt"]

        # 高风险节点（AP=H）
        risk_result = await session.run(
            "MATCH (n:GraphNode:FailureMode) WHERE n.product_line_code = $pl AND n.ap = 'H' "
            "RETURN n.node_id AS node_id, n.name AS name, n.ap AS ap, "
            "n.severity * n.occurrence * n.detection AS rpn, "
            "n.fmea_id AS fmea_id "
            "ORDER BY rpn DESC LIMIT 20",
            pl=product_line_code,
        )
        risk_records = await risk_result.data()

        # 平均 RPN
        avg_result = await session.run(
            "MATCH (n:GraphNode:FailureMode) WHERE n.product_line_code = $pl "
            "AND n.severity > 0 AND n.occurrence > 0 AND n.detection > 0 "
            "RETURN avg(n.severity * n.occurrence * n.detection) AS avg_rpn, count(*) AS cnt",
            pl=product_line_code,
        )
        avg_records = await avg_result.data()

        # Top 失效模式
        top_result = await session.run(
            "MATCH (n:GraphNode:FailureMode) WHERE n.product_line_code = $pl "
            "RETURN n.name AS name, n.severity * n.occurrence * n.detection AS rpn, n.fmea_id AS fmea_id "
            "ORDER BY rpn DESC LIMIT 10",
            pl=product_line_code,
        )
        top_records = await top_result.data()

        # FMEA 文档数
        doc_result = await session.run(
            "MATCH (d:FMEDocument) WHERE d.product_line_code = $pl RETURN count(*) AS cnt",
            pl=product_line_code,
        )
        doc_records = await doc_result.data()

        return {
            "total_fmeas": doc_records[0]["cnt"] if doc_records else 0,
            "total_nodes": sum(type_dist.values()),
            "node_type_distribution": type_dist,
            "ap_distribution": ap_counts,
            "high_ap_nodes": risk_records,
            "avg_rpn": round(avg_records[0]["avg_rpn"], 1) if avg_records and avg_records[0]["avg_rpn"] else 0,
            "top_failure_modes": top_records,
        }
```

- [ ] **Step 3: 修改 JSONBRepository.find_similar_nodes 补 document_no**

在 `backend/app/graph/jsonb_repository.py` 的 `find_similar_nodes` 中，确保返回包含 `document_no`：

```python
matches.append({
    "node_id": node["id"],
    "name": node["name"],
    "type": node["type"],
    "fmea_id": str(fmea.fmea_id),
    "document_no": fmea.document_no,  # 确保存在
})
```

- [ ] **Step 4: 验证后端编译**

```bash
cd backend && python -m py_compile app/graph/jsonb_repository.py app/graph/neo4j_repository.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/jsonb_repository.py backend/app/graph/neo4j_repository.py
git commit -m "feat(graph): update stats DTO with AP-first metrics, align similar_nodes fields"
```

---

## Task 3: 创建 GraphLegend 组件

**Files:**
- Create: `frontend/src/components/graph/GraphLegend.tsx`

**上下文:** 展示图例，说明各节点类型对应的颜色和形状。

- [ ] **Step 1: 创建组件**

Create `frontend/src/components/graph/GraphLegend.tsx`:

```typescript
import { Card, Space, Tag } from "antd";

const NODE_STYLES: Array<{ type: string; label: string; color: string }> = [
  { type: "System", label: "系统", color: "#1890ff" },
  { type: "ProcessItem", label: "过程项", color: "#1890ff" },
  { type: "Subsystem", label: "子系统", color: "#69c0ff" },
  { type: "ProcessStep", label: "工序", color: "#69c0ff" },
  { type: "Component", label: "零部件", color: "#36cfc9" },
  { type: "ProcessWorkElement", label: "工作要素", color: "#36cfc9" },
  { type: "Function", label: "功能", color: "#52c41a" },
  { type: "FailureMode", label: "失效模式", color: "#ff4d4f" },
  { type: "FailureEffect", label: "失效影响", color: "#fa8c16" },
  { type: "FailureCause", label: "失效原因", color: "#faad14" },
  { type: "PreventionControl", label: "预防控制", color: "#73d13d" },
  { type: "DetectionControl", label: "探测控制", color: "#722ed1" },
  { type: "RecommendedAction", label: "建议措施", color: "#8c8c8c" },
];

export default function GraphLegend() {
  return (
    <Card size="small" title="图例" style={{ width: 200 }}>
      <Space direction="vertical" size="small">
        {NODE_STYLES.map((s) => (
          <Tag key={s.type} color={s.color}>
            {s.label}
          </Tag>
        ))}
      </Space>
    </Card>
  );
}
```

- [ ] **Step 2: 验证编译**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/graph/GraphLegend.tsx
git commit -m "feat(graph): add GraphLegend component"
```

---

## Task 4: 创建 GraphToolbar 组件

**Files:**
- Create: `frontend/src/components/graph/GraphToolbar.tsx`

- [ ] **Step 1: 创建组件**

Create `frontend/src/components/graph/GraphToolbar.tsx`:

```typescript
import { Button, Space, Tooltip } from "antd";
import {
  ZoomInOutlined,
  ZoomOutOutlined,
  FullscreenOutlined,
  DownloadOutlined,
  ColumnWidthOutlined,
  BranchesOutlined,
  ApartmentOutlined,
} from "@ant-design/icons";

export type GraphLayout = "dagre" | "force" | "compact-box";

interface GraphToolbarProps {
  layout: GraphLayout;
  onLayoutChange: (layout: GraphLayout) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitView: () => void;
  onDownload: () => void;
}

export default function GraphToolbar({
  layout,
  onLayoutChange,
  onZoomIn,
  onZoomOut,
  onFitView,
  onDownload,
}: GraphToolbarProps) {
  return (
    <Space wrap>
      <Tooltip title="层次布局">
        <Button
          icon={<ApartmentOutlined />}
          type={layout === "dagre" ? "primary" : "default"}
          onClick={() => onLayoutChange("dagre")}
        >
          层次
        </Button>
      </Tooltip>
      <Tooltip title="力导向布局">
        <Button
          icon={<BranchesOutlined />}
          type={layout === "force" ? "primary" : "default"}
          onClick={() => onLayoutChange("force")}
        >
          力导向
        </Button>
      </Tooltip>
      <Tooltip title="紧凑树">
        <Button
          icon={<ColumnWidthOutlined />}
          type={layout === "compact-box" ? "primary" : "default"}
          onClick={() => onLayoutChange("compact-box")}
        >
          紧凑树
        </Button>
      </Tooltip>
      <Tooltip title="放大">
        <Button icon={<ZoomInOutlined />} onClick={onZoomIn} />
      </Tooltip>
      <Tooltip title="缩小">
        <Button icon={<ZoomOutOutlined />} onClick={onZoomOut} />
      </Tooltip>
      <Tooltip title="适应画布">
        <Button icon={<FullscreenOutlined />} onClick={onFitView} />
      </Tooltip>
      <Tooltip title="下载快照">
        <Button icon={<DownloadOutlined />} onClick={onDownload} />
      </Tooltip>
    </Space>
  );
}
```

- [ ] **Step 2: 验证编译**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/graph/GraphToolbar.tsx
git commit -m "feat(graph): add GraphToolbar component"
```

---

## Task 5: 创建 NodeDetailDrawer 组件

**Files:**
- Create: `frontend/src/components/graph/NodeDetailDrawer.tsx`

- [ ] **Step 1: 创建组件**

Create `frontend/src/components/graph/NodeDetailDrawer.tsx`:

```typescript
import { Drawer, Descriptions, Tag, Space } from "antd";
import type { GraphNode } from "../../api/graph";
import { calculateAP } from "../../utils/fmea";

interface NodeDetailDrawerProps {
  node: GraphNode | null;
  visible: boolean;
  onClose: () => void;
}

function apTag(ap: string | undefined) {
  if (ap === "H") return <Tag color="red">高 (H)</Tag>;
  if (ap === "M") return <Tag color="orange">中 (M)</Tag>;
  if (ap === "L") return <Tag color="green">低 (L)</Tag>;
  return <Tag>未评级</Tag>;
}

export default function NodeDetailDrawer({
  node,
  visible,
  onClose,
}: NodeDetailDrawerProps) {
  if (!node) return null;

  const p = node.properties;
  const s = p.severity ?? 0;
  const o = p.occurrence ?? 0;
  const d = p.detection ?? 0;
  const rpn = s * o * d;
  const computedAP = s > 0 && o > 0 && d > 0 ? calculateAP(s, o, d) : "";

  return (
    <Drawer title={p.name || "节点详情"} open={visible} onClose={onClose} width={400}>
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="节点 ID">{node.id}</Descriptions.Item>
        <Descriptions.Item label="节点类型">
          <Tag>{node.label}</Tag>
        </Descriptions.Item>
        {p.severity !== undefined && (
          <Descriptions.Item label="严重度 (S)">{p.severity}</Descriptions.Item>
        )}
        {p.occurrence !== undefined && (
          <Descriptions.Item label="发生度 (O)">{p.occurrence}</Descriptions.Item>
        )}
        {p.detection !== undefined && (
          <Descriptions.Item label="探测度 (D)">{p.detection}</Descriptions.Item>
        )}
        {rpn > 0 && (
          <Descriptions.Item label="RPN">
            {s} × {o} × {d} = <strong>{rpn}</strong>
          </Descriptions.Item>
        )}
        {(p.ap || computedAP) && (
          <Descriptions.Item label="行动优先级 (AP)">
            <Space>
              {apTag(p.ap)}
              {computedAP && p.ap !== computedAP && (
                <span style={{ fontSize: 12, color: "#888" }}>
                  (计算值: {computedAP})
                </span>
              )}
            </Space>
          </Descriptions.Item>
        )}
        {p.revised_severity !== undefined && (
          <Descriptions.Item label="修订严重度">{p.revised_severity}</Descriptions.Item>
        )}
        {p.revised_occurrence !== undefined && (
          <Descriptions.Item label="修订发生度">{p.revised_occurrence}</Descriptions.Item>
        )}
        {p.revised_detection !== undefined && (
          <Descriptions.Item label="修订探测度">{p.revised_detection}</Descriptions.Item>
        )}
        {p.status && (
          <Descriptions.Item label="状态">{p.status}</Descriptions.Item>
        )}
        {p.responsible && (
          <Descriptions.Item label="责任人">{p.responsible}</Descriptions.Item>
        )}
        {p.due_date && (
          <Descriptions.Item label="截止日期">{p.due_date}</Descriptions.Item>
        )}
      </Descriptions>
    </Drawer>
  );
}
```

**注意:** `calculateAP` 函数已在 `frontend/src/utils/fmea.ts` 中定义，直接使用。

- [ ] **Step 2: 验证编译**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/graph/NodeDetailDrawer.tsx
git commit -m "feat(graph): add NodeDetailDrawer component"
```

---

## Task 6: 创建 GraphCanvas 核心组件

**Files:**
- Create: `frontend/src/components/graph/GraphCanvas.tsx`

**上下文:** 这是整个模块的核心。使用 AntV G6 v5 创建图实例，配置节点/边样式、布局、交互。组件卸载时必须调用 `graph.destroy()` 防止内存泄漏。

- [ ] **Step 1: 创建组件**

Create `frontend/src/components/graph/GraphCanvas.tsx`:

```typescript
import { forwardRef, useEffect, useRef, useCallback, useImperativeHandle } from "react";
import { Graph } from "@antv/g6";
import type { GraphNode, GraphEdge } from "../../api/graph";
import type { GraphLayout } from "./GraphToolbar";

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  mode: "single-fmea" | "global";
  layout?: GraphLayout;
  highlightNodes?: string[];
  dimOthers?: boolean;
  onNodeClick?: (node: GraphNode) => void;
  onNodeDoubleClick?: (node: GraphNode) => void;
  onNodeContextMenu?: (node: GraphNode, event: MouseEvent) => void;
}

const NODE_TYPE_COLORS: Record<string, string> = {
  System: "#1890ff",
  ProcessItem: "#1890ff",
  Subsystem: "#69c0ff",
  ProcessStep: "#69c0ff",
  Component: "#36cfc9",
  ProcessWorkElement: "#36cfc9",
  Function: "#52c41a",
  FailureMode: "#ff4d4f",
  FailureEffect: "#fa8c16",
  FailureCause: "#faad14",
  PreventionControl: "#73d13d",
  DetectionControl: "#722ed1",
  RecommendedAction: "#8c8c8c",
};

const NODE_TYPE_SHAPES: Record<string, string> = {
  System: "rect",
  ProcessItem: "rect",
  Subsystem: "rect",
  ProcessStep: "rect",
  Component: "rect",
  ProcessWorkElement: "rect",
  Function: "rect",
  FailureMode: "diamond",
  FailureEffect: "ellipse",
  FailureCause: "ellipse",
  PreventionControl: "circle",
  DetectionControl: "circle",
  RecommendedAction: "rect",
};

function toG6Data(nodes: GraphNode[], edges: GraphEdge[]) {
  const g6Nodes = nodes.map((n) => ({
    id: n.id,
    data: {
      label: n.properties.name || n.label,
      type: n.label,
    },
    style: {
      fill: NODE_TYPE_COLORS[n.label] || "#e8e8e8",
      stroke: NODE_TYPE_COLORS[n.label] || "#8c8c8c",
      lineWidth: 1,
      size: n.label === "FailureMode" ? [80, 50] : n.label?.includes("Control") ? 30 : [100, 40],
    },
  }));

  const g6Edges = edges.map((e, i) => ({
    id: `e${i}`,
    source: e.source,
    target: e.target,
    data: { label: e.label },
    style: {
      stroke: "#8c8c8c",
      lineWidth: 1,
      endArrow: true,
    },
  }));

  return { nodes: g6Nodes, edges: g6Edges };
}

export interface GraphCanvasRef {
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
  download: () => void;
}

const GraphCanvas = forwardRef<GraphCanvasRef, GraphCanvasProps>(function GraphCanvas(
  {
    nodes,
    edges,
    mode,
    layout = mode === "single-fmea" ? "dagre" : "force",
    highlightNodes = [],
    dimOthers = false,
    onNodeClick,
    onNodeDoubleClick,
    onNodeContextMenu,
  }: GraphCanvasProps,
  ref
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);

  const initGraph = useCallback(() => {
    if (!containerRef.current) return;

    const graph = new Graph({
      container: containerRef.current,
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight || 600,
      autoFit: "view",
      data: toG6Data(nodes, edges),
      node: {
        type: (d: { data: { type: string } }) =>
          NODE_TYPE_SHAPES[d.data.type] || "rect",
        style: {
          labelText: (d: { data: { label: string } }) => d.data.label,
          labelFontSize: 10,
          labelPlacement: "center",
          labelFill: "#333",
        },
      },
      edge: {
        type: "line",
        style: {
          endArrow: true,
          labelText: (d: { data: { label: string } }) => d.data.label,
          labelFontSize: 9,
          labelFill: "#666",
        },
      },
      layout: {
        type: layout,
        rankdir: layout === "dagre" ? "LR" : undefined,
        animation: true,
      } as unknown,
      behaviors: [
        "drag-canvas",
        "zoom-canvas",
        "drag-node",
        {
          type: "collapse-expand",
          trigger: "dblclick",
        },
      ],
      plugins: [
        {
          type: "minimap",
          size: [150, 100],
        },
      ],
    });

    graphRef.current = graph;

    if (onNodeClick) {
      graph.on("node:click", (evt: { target: { id: string } }) => {
        const nodeId = evt.target.id;
        const node = nodes.find((n) => n.id === nodeId);
        if (node) onNodeClick(node);
      });
    }

    if (onNodeDoubleClick) {
      graph.on("node:dblclick", (evt: { target: { id: string } }) => {
        const nodeId = evt.target.id;
        const node = nodes.find((n) => n.id === nodeId);
        if (node) onNodeDoubleClick(node);
      });
    }

    if (onNodeContextMenu) {
      graph.on("node:contextmenu", (evt: { target: { id: string }; originalEvent: MouseEvent }) => {
        evt.originalEvent.preventDefault();
        const nodeId = evt.target.id;
        const node = nodes.find((n) => n.id === nodeId);
        if (node) onNodeContextMenu(node, evt.originalEvent);
      });
    }
  }, [nodes, edges, layout, mode, onNodeClick, onNodeDoubleClick, onNodeContextMenu]);

  // Apply highlight/dim
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;

    if (highlightNodes.length > 0 && dimOthers) {
      graph.getNodeData().forEach((node: { id: string; style?: Record<string, unknown> }) => {
        const isHighlighted = highlightNodes.includes(node.id);
        graph.updateNodeData([
          {
            id: node.id,
            style: {
              ...node.style,
              opacity: isHighlighted ? 1 : 0.2,
            },
          },
        ]);
      });
      graph.getEdgeData().forEach((edge: { id: string; source: string; target: string; style?: Record<string, unknown> }) => {
        const isHighlighted =
          highlightNodes.includes(edge.source) && highlightNodes.includes(edge.target);
        graph.updateEdgeData([
          {
            id: edge.id,
            style: {
              ...edge.style,
              opacity: isHighlighted ? 1 : 0.1,
              stroke: isHighlighted ? "#ff4d4f" : "#8c8c8c",
              lineWidth: isHighlighted ? 2 : 1,
            },
          },
        ]);
      });
    } else {
      // Reset
      graph.getNodeData().forEach((node: { id: string; style?: Record<string, unknown> }) => {
        graph.updateNodeData([
          {
            id: node.id,
            style: {
              ...node.style,
              opacity: 1,
            },
          },
        ]);
      });
      graph.getEdgeData().forEach((edge: { id: string; style?: Record<string, unknown> }) => {
        graph.updateEdgeData([
          {
            id: edge.id,
            style: {
              ...edge.style,
              opacity: 1,
              stroke: "#8c8c8c",
              lineWidth: 1,
            },
          },
        ]);
      });
    }
  }, [highlightNodes, dimOthers]);

  useEffect(() => {
    initGraph();
    return () => {
      graphRef.current?.destroy();
      graphRef.current = null;
    };
  }, [initGraph]);

  // Resize handler
  useEffect(() => {
    const handleResize = () => {
      if (containerRef.current && graphRef.current) {
        graphRef.current.setSize([
          containerRef.current.clientWidth,
          containerRef.current.clientHeight || 600,
        ]);
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Expose imperative methods for GraphToolbar
  useImperativeHandle(ref, () => ({
    zoomIn: () => graphRef.current?.zoomBy?.(1.2),
    zoomOut: () => graphRef.current?.zoomBy?.(0.8),
    fitView: () => graphRef.current?.fitCenter?.() || graphRef.current?.fitView?.(),
    download: () => {
      const canvas = containerRef.current?.querySelector("canvas");
      if (canvas) {
        const link = document.createElement("a");
        link.download = "graph.png";
        link.href = (canvas as HTMLCanvasElement).toDataURL();
        link.click();
      }
    },
  }));

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: "100%",
        minHeight: 500,
        border: "1px solid #f0f0f0",
        borderRadius: 4,
        background: "#fafafa",
      }}
    />
  );
});

export default GraphCanvas;
```

**注意:** G6 v5 API 可能与示例代码有差异，实际实现时需参考 `@antv/g6` 官方文档调整。如果 G6 初始化失败，需在父组件中捕获错误并降级为列表视图。

- [ ] **Step 2: 验证编译**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 可能因 G6 v5 类型定义差异出现类型错误，根据实际报错调整

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/graph/GraphCanvas.tsx
git commit -m "feat(graph): add GraphCanvas core component"
```

---

## Task 7: 创建组件统一导出文件

**Files:**
- Create: `frontend/src/components/graph/index.ts`

- [ ] **Step 1: 创建导出文件**

Create `frontend/src/components/graph/index.ts`:

```typescript
export { default as GraphCanvas } from "./GraphCanvas";
export type { GraphCanvasRef } from "./GraphCanvas";
export { default as GraphToolbar } from "./GraphToolbar";
export { default as NodeDetailDrawer } from "./NodeDetailDrawer";
export { default as GraphLegend } from "./GraphLegend";
export type { GraphLayout } from "./GraphToolbar";
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/graph/index.ts
git commit -m "feat(graph): add graph components barrel export"
```

---

## Task 8: 修改 FMEAEditorPage 添加图谱 Tab

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`

**上下文:** 现有页面使用 `outerTab` state 管理外层 Tabs（editor、related-capa、history）。在 editor 旁边添加 "图谱" Tab。

- [ ] **Step 1: 导入图组件和 API**

在 `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` 顶部添加导入：

```typescript
// 修改现有 React import，追加 useRef：
// import { useState, useEffect, useCallback, useMemo } from "react";
// →
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Dropdown } from "antd";
import type { MenuProps } from "antd";
import { GraphCanvas, GraphToolbar, NodeDetailDrawer, GraphLegend } from "../../../components/graph";
import type { GraphLayout, GraphCanvasRef } from "../../../components/graph";
import type { GraphNode as APIGraphNode } from "../../../api/graph";
import { getImpactChain, getCauseChain, normalizeGraphData } from "../../../api/graph";
```

- [ ] **Step 2: 添加图谱相关 state**

在组件内部（约第 90 行附近，其他 state 定义之后）添加：

```typescript
const [graphTabActive, setGraphTabActive] = useState(false);
const graphDataRef = useRef<{ nodes: APIGraphNode[]; edges: import("../../../api/graph").GraphEdge[] } | null>(null);
const [selectedGraphNode, setSelectedGraphNode] = useState<APIGraphNode | null>(null);
const [drawerVisible, setDrawerVisible] = useState(false);
const [graphLayout, setGraphLayout] = useState<GraphLayout>("dagre");
const [highlightNodes, setHighlightNodes] = useState<string[]>([]);
const [dimOthers, setDimOthers] = useState(false);
const [graphLoading, setGraphLoading] = useState(false);
const canvasRef = useRef<import("../../../components/graph").GraphCanvasRef>(null);

// 右键菜单状态
const [contextMenuOpen, setContextMenuOpen] = useState(false);
const [contextMenuPos, setContextMenuPos] = useState({ x: 0, y: 0 });
const [contextMenuNode, setContextMenuNode] = useState<APIGraphNode | null>(null);
const [pendingHighlightNode, setPendingHighlightNode] = useState<string | null>(null);
```

- [ ] **Step 3: 添加图谱数据加载函数**

在组件内部添加：

```typescript
const loadGraphData = useCallback(async () => {
  if (!id || graphDataRef.current) return;
  setGraphLoading(true);
  try {
    const doc = await getFMEA(id);
    const rawNodes = doc.graph_data?.nodes || [];
    const rawEdges = doc.graph_data?.edges || [];
    graphDataRef.current = normalizeGraphData(rawNodes, rawEdges);
    // 如果有待高亮节点（来自 URL 参数），在数据加载完成后应用
    if (pendingHighlightNode) {
      setHighlightNodes([pendingHighlightNode]);
      setDimOthers(true);
      setPendingHighlightNode(null);
    }
  } catch {
    message.error("图谱数据加载失败");
  } finally {
    setGraphLoading(false);
  }
}, [id, message, pendingHighlightNode]);

const handleTraceImpact = async (nodeId: string) => {
  if (!id) return;
  try {
    const chain = await getImpactChain(id, nodeId);
    const { nodes } = normalizeGraphData(chain.nodes, chain.edges);
    setHighlightNodes(nodes.map((n) => n.id));
    setDimOthers(true);
  } catch {
    message.error("影响链查询失败");
  }
};

const handleTraceCause = async (nodeId: string) => {
  if (!id) return;
  try {
    const chain = await getCauseChain(id, nodeId);
    const { nodes } = normalizeGraphData(chain.nodes, chain.edges);
    setHighlightNodes(nodes.map((n) => n.id));
    setDimOthers(true);
  } catch {
    message.error("原因链查询失败");
  }
};
```

- [ ] **Step 4: 监听 outerTab 切换加载图谱**

在 `useEffect` 区域添加（可在现有 useEffect 之后）：

```typescript
useEffect(() => {
  if (outerTab === "graph") {
    loadGraphData();
  }
}, [outerTab, loadGraphData]);

// 响应 URL ?tab=graph&highlightNode=... 参数
useEffect(() => {
  const tabParam = searchParams.get("tab");
  const highlightParam = searchParams.get("highlightNode");
  if (tabParam === "graph") {
    setOuterTab("graph");
    if (highlightParam) {
      setPendingHighlightNode(highlightParam);
    }
  }
}, [searchParams]);
```

- [ ] **Step 5: 在 save 成功后清空图谱缓存**

在 `save` useCallback 中，在 `setFmea(updated)` 之后添加：

```typescript
graphDataRef.current = null; // 保存后清空缓存，下次切回 graph 时重新加载
```

- [ ] **Step 6: 修改外层 Tabs 添加"图谱"TabPane**

找到现有代码（约 783 行）：

```tsx
<Tabs activeKey={outerTab} onChange={setOuterTab} style={{ marginBottom: 16 }}>
```

在其 `Tabs.TabPane` children 中，在 "editor" 和 "related-capa" 之间插入：

```tsx
<Tabs.TabPane tab="🕸️ 图谱" key="graph">
  <div style={{ display: "flex", gap: 16, height: "calc(100vh - 240px)" }}>
    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
      <GraphToolbar
        layout={graphLayout}
        onLayoutChange={setGraphLayout}
        onZoomIn={() => canvasRef.current?.zoomIn()}
        onZoomOut={() => canvasRef.current?.zoomOut()}
        onFitView={() => canvasRef.current?.fitView()}
        onDownload={() => canvasRef.current?.download()}
      />
      {graphLoading ? (
        <Spin size="large" style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }} />
      ) : graphDataRef.current ? (
        <>
          <GraphCanvas
            ref={canvasRef}
            nodes={graphDataRef.current.nodes}
            edges={graphDataRef.current.edges}
            mode="single-fmea"
            layout={graphLayout}
            highlightNodes={highlightNodes}
            dimOthers={dimOthers}
            onNodeClick={(node) => {
              setSelectedGraphNode(node);
              setDrawerVisible(true);
            }}
            onNodeContextMenu={(node, evt) => {
              evt.preventDefault();
              setContextMenuNode(node);
              setContextMenuPos({ x: evt.clientX, y: evt.clientY });
              setContextMenuOpen(true);
            }}
          />
          <Dropdown
            open={contextMenuOpen}
            onOpenChange={setContextMenuOpen}
            menu={{
              items: [
                { key: "impact", label: "追溯影响" },
                { key: "cause", label: "追溯原因" },
              ],
              onClick: ({ key }) => {
                setContextMenuOpen(false);
                if (key === "impact" && contextMenuNode) handleTraceImpact(contextMenuNode.id);
                if (key === "cause" && contextMenuNode) handleTraceCause(contextMenuNode.id);
              },
            }}
          >
            <span style={{
              position: "fixed",
              left: contextMenuPos.x,
              top: contextMenuPos.y,
              zIndex: 1050,
            }} />
          </Dropdown>
        </>
      ) : (
        <Empty description="暂无图谱数据" style={{ flex: 1 }} />
      )}
    </div>
    <div style={{ width: 220, display: "flex", flexDirection: "column", gap: 16 }}>
      <GraphLegend />
      {highlightNodes.length > 0 && (
        <Button onClick={() => { setHighlightNodes([]); setDimOthers(false); }}>
          清除高亮
        </Button>
      )}
    </div>
  </div>
  <NodeDetailDrawer
    node={selectedGraphNode}
    visible={drawerVisible}
    onClose={() => setDrawerVisible(false)}
  />
</Tabs.TabPane>
```

**注意:** 右键菜单使用 Ant Design Dropdown 受控组件实现，`menu={{ items, onClick }}` API（AntD 5 推荐）。`contextMenuOpen`/`contextMenuPos`/`contextMenuNode` 三个 state 在 Step 2 中定义于组件顶层。G6 的 `node:contextmenu` 事件提供坐标，一个固定定位的 `<span>` 作为 Dropdown 的锚点元素。

- [ ] **Step 7: 验证编译**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx
git commit -m "feat(fmea): add graph visualization tab to editor"
```

---

## Task 9: 创建 KnowledgeGraphPage（全局知识图谱页）

**Files:**
- Create: `frontend/src/pages/graph/KnowledgeGraphPage.tsx`

**上下文:** 全局页以统计聚合、关键词搜索、风险列表为核心。引用 `frontend/src/store/productLineStore.ts` 中的全局产品线选择器。

- [ ] **Step 1: 创建页面**

Create `frontend/src/pages/graph/KnowledgeGraphPage.tsx`:

```typescript
import { useState, useEffect } from "react";
import { Card, Tabs, Input, Select, Table, Tag, Spin, Empty, Space, Statistic, Row, Col, Button } from "antd";
import { SearchOutlined, BarChartOutlined, FireOutlined, LinkOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useProductLineStore } from "../../store/productLineStore";
import { searchSimilarNodes, getCrossFmeaStats } from "../../api/graph";
import type { SimilarNode, CrossFmeaStats } from "../../api/graph";

const { TabPane } = Tabs;

export default function KnowledgeGraphPage() {
  const navigate = useNavigate();
  const { selected: productLineCode } = useProductLineStore();
  const [activeTab, setActiveTab] = useState("overview");
  const [stats, setStats] = useState<CrossFmeaStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [searchType, setSearchType] = useState("FailureMode");
  const [searchResults, setSearchResults] = useState<SimilarNode[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  useEffect(() => {
    if (!productLineCode) return;
    setStatsLoading(true);
    getCrossFmeaStats(productLineCode)
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));
  }, [productLineCode]);

  const handleSearch = () => {
    if (!productLineCode || !searchKeyword.trim()) return;
    setSearchLoading(true);
    searchSimilarNodes({
      node_type: searchType,
      name_keyword: searchKeyword.trim(),
      product_line_code: productLineCode,
      limit: 20,
    })
      .then(setSearchResults)
      .catch(() => setSearchResults([]))
      .finally(() => setSearchLoading(false));
  };

  const riskColumns = [
    { title: "失效模式", dataIndex: "name", key: "name" },
    { title: "RPN", dataIndex: "rpn", key: "rpn", width: 80 },
    {
      title: "来源 FMEA",
      dataIndex: "document_no",
      key: "document_no",
      render: (v: string, record: { node_id: string; fmea_id: string }) => (
        <Button
          type="link"
          icon={<LinkOutlined />}
          onClick={() => navigate(`/fmea/${record.fmea_id}?tab=graph&highlightNode=${record.node_id}`)}
        >
          {v || record.fmea_id}
        </Button>
      ),
    },
    {
      title: "操作",
      key: "action",
      render: (_: unknown, record: { node_id: string; fmea_id: string }) => (
        <Button
          size="small"
          onClick={() => navigate(`/fmea/${record.fmea_id}?tab=graph&highlightNode=${record.node_id}`)}
        >
          查看图谱
        </Button>
      ),
    },
  ];

  const searchColumns = [
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "类型", dataIndex: "type", key: "type", width: 120 },
    {
      title: "来源 FMEA",
      dataIndex: "document_no",
      key: "document_no",
      render: (v: string, record: { node_id: string; fmea_id: string }) => (
        <Button
          type="link"
          onClick={() => navigate(`/fmea/${record.fmea_id}?tab=graph&highlightNode=${record.node_id}`)}
        >
          {v || record.fmea_id}
        </Button>
      ),
    },
    {
      title: "操作",
      key: "action",
      render: (_: unknown, record: { node_id: string; fmea_id: string }) => (
        <Button
          size="small"
          onClick={() => navigate(`/fmea/${record.fmea_id}?tab=graph&highlightNode=${record.node_id}`)}
        >
          查看
        </Button>
      ),
    },
  ];

  if (!productLineCode) {
    return (
      <Card>
        <Empty description="请先选择产品线" />
      </Card>
    );
  }

  return (
    <div>
      <h2>知识图谱</h2>
      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={<span><BarChartOutlined /> 总览 / 风险地图</span>} key="overview">
          {statsLoading ? (
            <Spin size="large" style={{ display: "block", margin: "60px auto" }} />
          ) : stats ? (
            <Space direction="vertical" size="large" style={{ width: "100%" }}>
              <Row gutter={16}>
                <Col span={6}>
                  <Card><Statistic title="FMEA 总数" value={stats.total_fmeas} /></Card>
                </Col>
                <Col span={6}>
                  <Card><Statistic title="节点总数" value={stats.total_nodes} /></Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="高优先级失效模式 (AP=H)"
                      value={stats.high_ap_nodes?.length || 0}
                      prefix={<FireOutlined style={{ color: "#ff4d4f" }} />}
                    />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card><Statistic title="平均 RPN" value={stats.avg_rpn || 0} precision={1} /></Card>
                </Col>
              </Row>
              <Card title="AP 分布">
                <Space size="large">
                  <Tag color="red">高 (H): {stats.ap_distribution?.H || 0}</Tag>
                  <Tag color="orange">中 (M): {stats.ap_distribution?.M || 0}</Tag>
                  <Tag color="green">低 (L): {stats.ap_distribution?.L || 0}</Tag>
                </Space>
              </Card>
              <Card title="高优先级失效模式 Top 10" extra={<Tag color="red">AP = H (高优先级)</Tag>}>
                <Table
                  dataSource={stats.high_ap_nodes || []}
                  columns={riskColumns}
                  rowKey={(r) => `${r.fmea_id}-${r.name}`}
                  pagination={false}
                  size="small"
                />
              </Card>
              <Card title="节点类型分布">
                <Space wrap>
                  {Object.entries(stats.node_type_distribution || {}).map(([type, count]) => (
                    <Tag key={type}>{type}: {count}</Tag>
                  ))}
                </Space>
              </Card>
            </Space>
          ) : (
            <Empty description="暂无统计数据" />
          )}
        </TabPane>

        <TabPane tab={<span><SearchOutlined /> 历史关键词搜索</span>} key="search">
          <Space style={{ marginBottom: 16 }}>
            <Select value={searchType} onChange={setSearchType} style={{ width: 140 }}>
              <Select.Option value="FailureMode">失效模式</Select.Option>
              <Select.Option value="FailureCause">失效原因</Select.Option>
              <Select.Option value="FailureEffect">失效影响</Select.Option>
              <Select.Option value="Function">功能</Select.Option>
            </Select>
            <Input.Search
              placeholder="输入关键词搜索..."
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              onSearch={handleSearch}
              loading={searchLoading}
              style={{ width: 300 }}
            />
          </Space>
          {searchResults.length > 0 && (
            <Table
              dataSource={searchResults}
              columns={searchColumns}
              rowKey={(r) => `${r.fmea_id}-${r.node_id}`}
              size="small"
            />
          )}
        </TabPane>
      </Tabs>
    </div>
  );
}
```

- [ ] **Step 2: 验证编译**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/graph/KnowledgeGraphPage.tsx
git commit -m "feat(graph): add KnowledgeGraphPage with stats and search"
```

---

## Task 10: 添加路由和侧边栏导航

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: App.tsx 添加路由**

在 `frontend/src/App.tsx` 中：

1. 添加导入（在现有页面导入之后）：

```typescript
import KnowledgeGraphPage from "./pages/graph/KnowledgeGraphPage";
```

2. 在 Routes 的 ProtectedRoute 内添加：

```tsx
<Route path="/knowledge-graph" element={<KnowledgeGraphPage />} />
```

- [ ] **Step 2: AppLayout.tsx 添加侧边栏菜单**

1. 导入图标（在现有导入之后）：

```typescript
import { ShareAltOutlined } from "@ant-design/icons";
```

2. 在 `MENU_KEYS` 数组中添加：

```typescript
"/knowledge-graph",
```

3. 在 `MENU_KEY_TO_OPEN_KEYS` 中添加：

```typescript
"/knowledge-graph": ["grp:planning"],
```

4. 在 `menuItems` 的 "grp:planning" children 中，在 "特殊特性" 之后添加：

```typescript
{ key: "/knowledge-graph", icon: <ShareAltOutlined />, label: "知识图谱" },
```

- [ ] **Step 3: 验证编译**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(graph): add /knowledge-graph route and sidebar nav"
```

---

## Task 11: Build 验证

**Files:**
- All modified files

- [ ] **Step 1: TypeScript 编译检查**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

- [ ] **Step 2: Vite 构建**

```bash
cd frontend && npm run build
```
Expected: Build complete, no errors

- [ ] **Step 3: 最终 Commit**

```bash
git add -A
git commit -m "feat(graph): complete knowledge graph visualization frontend"
```

---

## Self-Review

### 1. Spec Coverage

| Spec 章节 | 对应 Task |
|:---|:---|
| 4.1 数据契约 | Task 2 (`api/graph.ts`) |
| 4.2 GraphCanvas | Task 6 |
| 4.3 GraphToolbar | Task 4 |
| 4.4 NodeDetailDrawer | Task 5 |
| 4.3 GraphLegend | Task 3 |
| 5.1 节点映射 | Task 6 (NODE_TYPE_COLORS/SHAPES) |
| 5.2 边映射 | Task 6 (edge style) |
| 5.3 高亮与置灰 | Task 6 (highlightNodes/dimOthers effect) |
| 6.1 失效链全貌 | Task 8 (FMEAEditorPage graph tab) |
| 6.2 追溯影响 | Task 8 (handleTraceImpact) |
| 6.3 历史关键词搜索 | Task 9 (search tab) |
| 6.4 全局风险地图 | Task 9 (overview tab with stats) |
| 6.5 追溯原因链 | Task 8 (handleTraceCause) |
| 7.1 单 FMEA 缓存 | Task 8 (graphDataRef) |
| 7.2 全局数据流 | Task 9 |
| 8.1 路由 | Task 10 |
| 8.2 导航 | Task 10 |
| 9. 错误处理 | Task 6 (try-catch), Task 8 (Empty fallback) |
| 10. 性能 | Task 6 (destroy on unmount), Task 8 (useRef cache) |

### 2. Placeholder Scan

- 无 TBD/TODO/implement later
- 所有代码步骤含完整代码块
- 无 "add appropriate error handling" 等模糊描述
- 验证命令和期望输出均已给出

### 3. Type Consistency

- `RenderGraphNode` / `RenderGraphEdge` 类型在 `api/graph.ts` 中定义，通过别名 `GraphNode` / `GraphEdge` 向后兼容
- `GraphLayout` 类型在 `GraphToolbar.tsx` 中导出，被 `GraphCanvas.tsx` 和 `FMEAEditorPage.tsx` 使用
- `SimilarNode` / `CrossFmeaStats` 类型在 `api/graph.ts` 中定义，被 `KnowledgeGraphPage.tsx` 使用
- 所有类型命名一致，无冲突；Neo4j 返回的 `node_id` 在 `normalizeGraphData()` 中统一映射为 `id`

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-31-knowledge-graph-visualization.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
