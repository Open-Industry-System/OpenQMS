# 全局知识库模块设计文档

**日期**: 2026-05-31
**模块**: 全局知识库 (Global Knowledge Base)
**阶段**: Phase 3 — AI + 知识图谱增强
**状态**: Approved (rev.2)

---

## 1. 目标

实现 OpenQMS 全局知识库：跨产品线 FMEA 聚合查询 + 数据脱敏，为前端知识图谱可视化提供数据支撑。

**范围：**
1. 补齐图查询 API 的 stats/similar 字段（AP 分布、高风险节点列表、平均 RPN）
2. 数据脱敏机制（白名单模式）
3. 前端全局知识库页面（统计卡片 + 风险列表 + 搜索）

**依赖：** Neo4j 基础设施（已完成）

**排除范围：** Neo4j 数据迁移、GraphSyncWorker、全量重建 CLI（已在 2026-05-30 完成）

---

## 2. 架构

```
PostgreSQL (FMEA graph_data JSONB)
  │
  ├── JSONBRepository ──┐
  │                      ├──→ FMEAGraphRepository 接口 ──→ api/graph.py ──→ 前端
  ├── Neo4jRepository ──┘        ↑ (白名单脱敏 + Pydantic DTO)
  │                              │
  └── Neo4j (Graph Projection) ──┘
```

**核心原则：**
- 全局查询走 `FMEAGraphRepository` 抽象层，前端不感知底层存储
- **默认使用 JSONBRepository**（零配置即工作）；Neo4jRepository 通过 `GRAPH_REPOSITORY=neo4j` 显式启用
- 脱敏在 API 层通过 **Pydantic ResponseModel 白名单** 实现，彻底阻断敏感字段外泄
- AP 计算复用已有 `app.state_machines.fmea_state.compute_ap`，不新建第二套规则

---

## 3. 后端增强

### 3.1 AP 计算复用

**不新增 AP 计算文件。** 已有 `backend/app/state_machines/fmea_state.py:34` 的 `compute_ap(s, o, d)` 与前端 `calculateAP` 逻辑完全一致（已通过 `backend/tests/test_fmea_state.py` 验证）。

Repository 中通过 `from app.state_machines.fmea_state import compute_ap` 复用。

### 3.2 Repository 字段补齐与统计语义

#### 3.2.1 JSONBRepository

文件：`backend/app/graph/jsonb_repository.py`

**`get_cross_fmea_stats` 统计语义（严格定义，确保与 Neo4j 实现一致）：**

| 字段 | 统计范围 | 计算规则 | 排序 | Limit |
|------|---------|---------|------|-------|
| `total_fmeas` | 全部 | 产品线过滤后的文档总数 | — | — |
| `total_nodes` | 全部 | 所有 FMEA 的 graph_data.nodes 长度之和 | — | — |
| `node_type_distribution` | 全部 | 按 node.type 分组计数 | 计数降序 | — |
| `ap_distribution` | **仅 FailureMode** | 对 S/O/D 有效的节点调用 `compute_ap` 分组 | — | — |
| `high_ap_nodes` | **仅 AP=H 的 FailureMode** | 优先按 AP（固定 H），**次要按 RPN 降序** | RPN 降序 | **Top 50** |
| `avg_rpn` | **仅 FailureMode** | 有效 RPN（S/O/D 均 > 0）的平均值，保留 1 位小数 | — | — |
| `top_failure_modes` | **仅 FailureMode** | 按 RPN 降序 | RPN 降序 | **Top 10** |

**空 S/O/D 处理：** 任一值为 0 或缺失时，RPN 计为 0，AP 计为 `""`，不纳入 `ap_distribution` 和 `avg_rpn` 计算。

**`find_similar_nodes`：** 返回字段补充 `document_no`（已在当前代码中）。

#### 3.2.2 Neo4jRepository

文件：`backend/app/graph/neo4j_repository.py`

**`get_cross_fmea_stats`：** 与 JSONBRepository 返回**完全一致的字段结构和语义**。

**关键实现注意：** GraphNode 节点上没有 `document_no` 属性（该属性只在 `FMEDocument` 节点上）。获取 `document_no` 必须通过 JOIN：

```cypher
MATCH (d:FMEDocument)-[:HAS_NODE]->(n:GraphNode)
WHERE n.product_line_code = $pl AND n.type = 'FailureMode'
RETURN n.node_id AS node_id, n.name AS name, n.severity AS severity, ...,
       d.document_no AS document_no
```

### 3.3 数据脱敏（白名单模式）

文件：`backend/app/api/graph.py`

**废弃黑名单思路，改用 Pydantic ResponseModel 白名单。**

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

**ap_distribution 缺键保护：** 无论实际分布如何，`ap_distribution` 必须始终返回 `{H: 0, M: 0, L: 0}` 全键（Repository 中显式初始化）。前端直接解构 `{H, M, L}` 而不会遇到 `undefined`。

端点返回类型注解为 `CrossFmeaStatsOut` / `list[SimilarNodeOut]`，FastAPI 自动过滤多余字段。

**明确：** `fmea_id`（UUID）和 `node_id`（字符串）是前端跳转必需的标识符，**不属于敏感字段**，允许返回。`document_no` 是业务编号，也允许返回。

### 3.4 产品线过滤策略

**强制要求 `product_line_code`：**
- 后端 API：`product_line_code` 为 Query 必填参数（`Query(..., min_length=1)`）。**实现方式：** 端点内先执行 `product_line_code = product_line_code.strip()`，再判断 `if not product_line_code: raise HTTPException(status_code=422, detail="product_line_code cannot be empty")`。`min_length=1` 拦截空字符串，但无法拦截纯空白（如 `"   "`），必须配合显式 `strip()` 校验。
- 前端页面：读取 `useProductLineStore` 当前选择值。若用户清空为"全部产品线"（`null` 或空字符串），页面显示提示"请选择产品线以查看知识库"，**禁用查询按钮和自动加载**

**理由：** 全局知识库涉及跨 FMEA 聚合，"全部产品线"会暴露所有产品数据，与当前 RBAC 设计冲突。后续如需支持全局汇总，需单独设计权限控制。

---

## 4. 前端页面

### 4.1 数据契约

```typescript
// api/graph.ts
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

export interface SimilarNode {
  node_id: string;
  name: string;
  type: string;
  fmea_id: string;
  document_no: string;
}
```

### 4.2 页面结构

路由：`/knowledge-graph`

页面组件：`frontend/src/pages/graph/KnowledgeGraphPage.tsx`

布局：
```
┌─────────────────────────────────────────────────────────────┐
│  产品线选择器 (ProductLineSelector)                          │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ FMEA总数  │ │ 节点总数  │ │ 平均RPN  │ │ AP分布   │       │
│  │ 12       │ │ 384      │ │ 145.2    │ │ 饼图     │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
├─────────────────────────────────────────────────────────────┤
│  [🔍 搜索节点] [节点类型下拉 ▼]                               │
├─────────────────────────────────────────────────────────────┤
│  高风险节点列表 (AP = H，按 RPN 降序)                         │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 名称          │ RPN  │ AP │ 来源文档      │ 操作      │  │
│  │ 焊接不良      │ 720  │ H  │ PFMEA-2026-001│ 查看图谱  │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  TOP10 失效模式（按 RPN 降序）                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 名称          │ RPN  │ 来源文档                        │  │
│  │ ...                                                    │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 交互流程

1. **页面加载**：读取 `useProductLineStore` → 若 `currentProductLine` 为空，显示提示并要求选择 → 否则调用 `getCrossFmeaStats(productLineCode)`
2. **产品线切换**：重新拉取 stats 数据；若清空则清空页面数据并显示提示
3. **搜索节点**：输入关键词 + 选择节点类型 → 防抖 300ms → 调用 `searchSimilarNodes` → 结果列表展示
4. **查看图谱**：点击"查看图谱" → 跳转 `/fmea/:id?node=:nodeId`。FMEAEditorPage 已支持通过 `searchParams.get("node")` 高亮对应节点。图谱 Tab 切换由知识图谱可视化模块负责实现，全局知识库模块不依赖也不修改 FMEAEditorPage 的 Tab 逻辑。

### 4.4 排序优先级说明（AIAG-VDA 合规）

**高风险节点列表 (`high_ap_nodes`)：**
- 所有节点 AP 均为 "H"（已过滤）
- **次要排序：RPN 降序**
- Limit：50

**TOP10 失效模式 (`top_failure_modes`)：**
- **主排序：RPN 降序**
- Limit：10

> 注：根据 AIAG-VDA (2019)，AP 已取代 RPN 作为首要决策依据。`high_ap_nodes` 通过 AP="H" 过滤已体现优先级，列表内再按 RPN 细化排序；`top_failure_modes` 侧重 RPN 绝对值排名，用于快速识别高数值失效模式。

---

## 5. 文件清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `frontend/src/api/graph.ts` | 图查询 API 客户端 |
| `frontend/src/pages/graph/KnowledgeGraphPage.tsx` | 全局知识库页面 |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `backend/app/graph/jsonb_repository.py` | 补齐 stats/similar 字段；复用 `compute_ap`；明确 limit/排序/空值规则 |
| `backend/app/graph/neo4j_repository.py` | 补齐 stats 字段；通过 FMEDocument JOIN 获取 `document_no` |
| `backend/app/api/graph.py` | 添加 Pydantic 白名单 ResponseModel；产品线空值拦截 |
| `frontend/src/App.tsx` | 注册 `/knowledge-graph` 路由 |
| `frontend/src/components/layout/AppLayout.tsx` | 导航菜单添加"知识图谱"入口 |

---

## 6. 降级与容错

### 6.1 Repository 降级

当前 `_repo()` 默认返回 `JSONBRepository`；当 `GRAPH_REPOSITORY=neo4j` 时尝试 Neo4jRepository，若 Neo4j 连接失败会抛出异常。

**现状保持：** 全局知识库查询默认走 JSONBRepository，无需额外降级逻辑。若后续启用 Neo4j，连接失败时异常由 FastAPI 全局异常处理返回 503。

### 6.2 G6 画布降级

全局知识库页面**不直接渲染 G6 画布**，仅展示统计卡片和表格列表。点击"查看图谱"跳转至 FMEA 编辑器，图谱 Tab/画布能力由知识图谱可视化模块负责实现和降级。

---

## 7. 验收标准

### 功能验收

- [ ] `GET /api/graph/stats` 返回完整的 `ap_distribution`、`high_ap_nodes`（Top 50，按 RPN 降序）、`avg_rpn`、`top_failure_modes`（Top 10，含 `document_no`）
- [ ] `GET /api/graph/similar` 返回结果包含 `document_no`
- [ ] 后端 `compute_ap`（`fmea_state.py`）与前端 `calculateAP` 结果一致
- [ ] 全局查询返回的数据**仅包含白名单字段**（无 created_by/updated_by/approved_by/responsible 等）
- [ ] `product_line_code` 为空字符串或纯空白时 API 返回 422；前端页面提示选择产品线
- [ ] 前端全局知识库页面可正常展示统计卡片、风险列表、搜索结果
- [ ] 点击"查看图谱"正确跳转 `/fmea/:id?node=:nodeId`，FMEA 编辑器能识别 node 参数高亮对应节点
- [ ] 支持按产品线过滤
- [ ] 中文 UI

### 一致性验收

- [ ] JSONBRepository 与 Neo4jRepository 的 `get_cross_fmea_stats` 对同一数据集返回相同数值
- [ ] `high_ap_nodes` 和 `top_failure_modes` 排序规则一致（RPN 降序）
- [ ] 空 S/O/D 处理一致（跳过 AP 计算，RPN=0）

### 性能验收

- [ ] 单产品线 stats 查询 < 3s（当前数据量）
- [ ] similar 搜索响应 < 1s（带关键词过滤）

### 构建验收

- [ ] `npm run build` 通过，无 TypeScript 错误
- [ ] 后端 `pytest tests/test_fmea_state.py -v` 通过（验证 AP 计算），`python app/test_schema.py` 通过（基础 schema 测试）
