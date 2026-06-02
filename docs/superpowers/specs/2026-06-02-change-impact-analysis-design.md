# OpenQMS 变更影响分析模块设计文档

**日期**: 2026-06-02  
**模块**: 变更影响分析（Change Impact Analysis）  
**对应路线图**: Phase 3 — 变更影响分析（图遍历）  
**状态**: 设计完成，待实施

---

## 1. 背景与目标

### 1.1 问题背景

在 FMEA 质量管理系统中，设计参数的变更（如 Component 尺寸、材料、公差）可能产生连锁影响，波及下游的功能、失效模式、控制措施等节点。现有系统仅支持手动查看 FMEA 图，无法自动追溯变更的传播路径和影响范围。

### 1.2 设计目标

- **自动追溯**: 输入变更节点和变更内容，自动分析影响范围
- **可视化呈现**: 以报告+图谱联动的形式展示影响路径
- **历史追溯**: 持久化分析结果，形成变更审计线索
- **架构预留**: 单 FMEA 文档为核心，数据模型和 API 预留跨文档扩展

### 1.3 支持场景

| 场景 | 变更类型 | 示例 |
|------|----------|------|
| 属性变更 | `attribute` | Component 的 `design_parameter` 从 "0.5mm" 改为 "0.6mm" |
| 结构变更 | `structural` | 新增/删除一个 FailureMode 节点 |

---

## 2. 数据模型设计

### 2.1 新增表：`change_impact_analysis`

```sql
CREATE TABLE change_impact_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fmea_id UUID NOT NULL REFERENCES fmea_documents(fmea_id) ON DELETE CASCADE,
    product_line_code VARCHAR NOT NULL,

    -- 变更定义
    node_id VARCHAR NOT NULL,           -- 变更的节点 ID
    node_type VARCHAR NOT NULL,         -- 节点类型（Component/Function/FailureMode 等）
    node_name VARCHAR NOT NULL,         -- 节点名称（快照，防后续修改）
    change_type VARCHAR NOT NULL,       -- 'attribute' | 'structural'
    field_name VARCHAR,                 -- 属性变更时：字段名；结构变更时：null
    old_value TEXT,                     -- 变更前值
    new_value TEXT,                     -- 变更后值

    -- 分析结果
    scope VARCHAR NOT NULL DEFAULT 'single_fmea',  -- 'single_fmea' | 'cross_fmea'
    status VARCHAR NOT NULL DEFAULT 'completed',   -- 'pending' | 'completed' | 'failed'
    impact_score INTEGER,               -- 1-10 影响严重程度评分（Service 单点计算）
    impact_result JSONB NOT NULL DEFAULT '{}',     -- 详细结果（仅 affected_nodes + summary）

    created_by UUID REFERENCES users(user_id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_change_impact_fmea ON change_impact_analysis(fmea_id);
CREATE INDEX idx_change_impact_node ON change_impact_analysis(node_id);
CREATE INDEX idx_change_impact_product_line ON change_impact_analysis(product_line_code);
```

### 2.2 `impact_result` JSONB 结构

```json
{
  "affected_nodes": [
    {
      "node_id": "n123",
      "node_type": "FailureMode",
      "name": "引脚虚焊",
      "path": ["SystemA", "SubsystemB", "ComponentC", "FunctionD", "FailureMode-n123"],
      "impact_type": "downstream",
      "hop_distance": 3,
      "risk_change": {
        "severity": {"old": 7, "new": 8, "reason": "design_parameter_change"},
        "ap": {"old": "M", "new": "H"}
      }
    }
  ],
  "summary": {
    "total_affected": 5,
    "failure_modes_affected": 2,
    "controls_affected": 1,
    "ap_upgraded_count": 1,
    "max_hop_distance": 3
  }
}
```

### 2.3 设计要点

- `impact_result` 使用 JSONB 存储完整分析结果，避免频繁变更表结构
- `impact_score` 后续可用于仪表盘排序和预警
- `scope` 字段预留跨文档扩展
- `node_name` 快照保存，防止节点后续改名导致历史记录不可读

---

## 3. 后端架构设计

### 3.1 Repository 扩展

在现有 `FMEAGraphRepository` 接口中新增方法：

```python
async def analyze_change_impact(
    self,
    fmea_id: uuid.UUID,
    node_id: str,
    change_type: str,       # "attribute" | "structural"
    field_name: str | None,
    new_value: str | None,
) -> ChangeImpactResult: ...
```

`Neo4jRepository` 和 `JSONBRepository` 各自实现此方法。

### 3.2 Pydantic Schema

```python
# backend/app/schemas/change_impact.py

class AffectedNode(BaseModel):
    node_id: str
    node_type: str
    name: str
    path: list[str]           # 从变更节点到该节点的路径节点名列表
    impact_type: str          # "upstream" | "downstream" | "direct"
    hop_distance: int
    risk_change: dict | None  # {severity: {old, new}, ap: {old, new}}

class ImpactSummary(BaseModel):
    total_affected: int
    failure_modes_affected: int
    controls_affected: int
    ap_upgraded_count: int
    max_hop_distance: int

class ChangeImpactResult(BaseModel):
    """Repository 返回的纯分析结果，不含评分（评分由 Service 单点计算）"""
    affected_nodes: list[AffectedNode]
    summary: ImpactSummary

class ChangeImpactAnalyzeRequest(BaseModel):
    fmea_id: uuid.UUID
    node_id: str
    node_type: str
    node_name: str
    change_type: Literal["attribute", "structural"]
    field_name: str | None = None
    new_value: str | None = None

class ChangeImpactAnalysisResponse(BaseModel):
    id: uuid.UUID
    fmea_id: uuid.UUID
    product_line_code: str
    node_id: str
    node_type: str
    node_name: str
    change_type: str
    field_name: str | None
    old_value: str | None
    new_value: str | None
    scope: str
    status: str
    impact_score: int
    impact_result: ChangeImpactResult
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
```

### 3.3 Service 层

```python
# backend/app/services/change_impact_service.py

class ChangeImpactService:
    def __init__(self, db: AsyncSession, graph_repo: FMEAGraphRepository):
        self._db = db
        self._graph_repo = graph_repo

    async def analyze(
        self,
        fmea_id: uuid.UUID,
        node_id: str,
        node_type: str,
        node_name: str,
        change_type: str,
        field_name: str | None,
        new_value: str | None,
        user_id: uuid.UUID,
    ) -> ChangeImpactAnalysis:
        # 1. 调用 Repository 执行图遍历分析
        result = await self._graph_repo.analyze_change_impact(
            fmea_id, node_id, change_type, field_name, new_value
        )

        # 2. 计算影响评分
        impact_score = self._compute_impact_score(result)

        # 3. 持久化
        analysis = ChangeImpactAnalysis(...)
        self._db.add(analysis)

        # 4. 审计日志
        await self._create_audit_log(
            fmea_id=fmea_id,
            action="change_impact_analyzed",
            detail=f"变更影响分析: {change_type} on {node_id}, score={impact_score}",
            user_id=user_id,
        )

        await self._db.commit()
        return analysis

    def _compute_impact_score(self, result: ChangeImpactResult) -> int:
        """Service 单点计算影响评分，确保表字段与响应一致"""
        score = result.summary.failure_modes_affected * 2
        score += result.summary.ap_upgraded_count * 3
        if result.summary.max_hop_distance > 2:
            score += 2
        return min(score, 10)
```

### 3.4 API 路由

```python
# backend/app/api/change_impact.py

from app.core.product_line_filter import enforce_product_line_access
from app.services.fmea_service import get_fmea_by_id  # 或等效查询

router = APIRouter(prefix="/api/change-impact", tags=["变更影响分析"])

@router.post("/analyze", response_model=ChangeImpactAnalysisResponse)
async def analyze_change_impact(
    body: ChangeImpactAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
    graph_repo: FMEAGraphRepository = Depends(get_graph_repository),
):
    """执行变更影响分析并持久化结果。前置校验产品线访问权限。"""
    # 1. 产品线越权校验
    fmea = await get_fmea_by_id(db, body.fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)

    # 2. 执行分析
    service = ChangeImpactService(db, graph_repo)
    return await service.analyze(
        fmea_id=body.fmea_id,
        node_id=body.node_id,
        node_type=body.node_type,
        node_name=body.node_name,
        change_type=body.change_type,
        field_name=body.field_name,
        new_value=body.new_value,
        user_id=user.id,
    )

@router.get("/fmea/{fmea_id}", response_model=list[ChangeImpactAnalysisResponse])
async def list_fmea_change_impacts(
    fmea_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取某个 FMEA 的所有变更影响分析历史"""
    fmea = await get_fmea_by_id(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)
    ...

@router.get("/{analysis_id}", response_model=ChangeImpactAnalysisResponse)
async def get_change_impact_detail(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取某次分析的详细结果"""
    analysis = await get_change_impact_by_id(db, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    await enforce_product_line_access(user, analysis.product_line_code, db)
    ...
```

### 3.5 权限设计

| 操作 | 权限要求 |
|------|----------|
| 执行分析 | `require_engineer_or_admin` |
| 查看历史 | `get_current_user`（所有登录用户） |
| 删除记录 | admin only（预留） |

---

## 4. 核心算法设计

### 4.1 图遍历策略

**属性变更场景：**

1. 获取节点 N 的完整属性
2. 根据字段 F 和节点类型判断传播方向：

| 字段类型 | 传播方向 | 影响类型 |
|----------|----------|----------|
| 设计参数类（dimension, material, tolerance） | downstream | 结构性影响 |
| 风险评分类（severity, occurrence, detection） | bidirectional | 风险重评估 |
| 名称/描述类 | none | 信息更新 |

3. 执行图遍历：
   - downstream：沿出边遍历（HAS_FUNCTION → FUNCTION_MAPPED_TO → HAS_FAILURE_MODE → EFFECT_OF）
   - upstream：沿入边遍历（CAUSE_OF, PREVENTED_BY, DETECTED_BY）
   - 最大深度：下游 5 跳，上游 3 跳

   **重要**：物理组件节点（Component/ProcessStep/ProcessWorkElement）不直接连接到 FailureMode，必须通过功能节点中转。下游遍历边集合必须包含 `HAS_FUNCTION` 和 `FUNCTION_MAPPED_TO`，否则从组件发起的变更将漏报。

4. 对每个访问节点记录：hop_distance、path、impact_type

**结构变更场景：**

| 操作 | 传播方向 | 影响 |
|------|----------|------|
| 新增节点 | upstream | 检查父节点完整性 |
| 删除节点 | downstream | 孤儿节点检测、失效链断裂 |
| 修改节点类型 | bidirectional | 边类型兼容性检查 |

### 4.2 风险变化预测

AP（Action Priority）由完整的 S/O/D 组合决定，单体节点无法独立计算。因此，当变更可能引发风险重评估时，算法必须从图中重构关联的 FMEARow Context。

```python
def predict_risk_change(graph_data, affected_node, field_name, new_value):
    """
    预测受影响节点的风险变化。
    对于 FailureMode 节点，需要从图中重构完整的 S/O/D 上下文来计算 AP。
    """
    node = affected_node
    node_type = node.get("type", "")

    # 场景 1：直接修改 S/O/D 评分字段
    if field_name in ["severity", "occurrence", "detection"]:
        # 如果修改的是 FailureMode 自身的评分，直接计算新旧 AP
        if node_type == "FailureMode":
            old_s = node.get("severity", 0)
            old_o = node.get("occurrence", 0)
            old_d = node.get("detection", 0)
            new_val = int(new_value)
            # 构建新值
            new_s = new_val if field_name == "severity" else old_s
            new_o = new_val if field_name == "occurrence" else old_o
            new_d = new_val if field_name == "detection" else old_d
            old_ap = compute_ap(old_s, old_o, old_d)
            new_ap = compute_ap(new_s, new_o, new_d)
            return {
                field_name: {"old": node.get(field_name), "new": new_val},
                "ap": {"old": old_ap, "new": new_ap} if old_ap != new_ap else None
            }
        # 如果修改的是 Cause 的 O/D，需要关联到对应的 FailureMode
        elif node_type in ["FailureCause"]:
            # 从图中找到关联的 FailureMode，重构完整 S/O/D
            failure_mode = _find_related_failure_mode(graph_data, node["id"])
            if failure_mode:
                old_s = failure_mode.get("severity", 0)
                old_o = failure_mode.get("occurrence", 0)
                old_d = failure_mode.get("detection", 0)
                new_val = int(new_value)
                new_o = new_val if field_name == "occurrence" else old_o
                new_d = new_val if field_name == "detection" else old_d
                old_ap = compute_ap(old_s, old_o, old_d)
                new_ap = compute_ap(old_s, new_o, new_d)
                return {
                    field_name: {"old": node.get(field_name), "new": new_val},
                    "ap": {"old": old_ap, "new": new_ap} if old_ap != new_ap else None
                }

    # 场景 2：设计参数变更（Component/ProcessStep）
    if node_type in ["Component", "ProcessStep", "ProcessWorkElement"] and field_name == "design_parameter":
        # 设计参数变更可能影响下游 FailureMode 的 severity
        # 先从图中重构受影响 FailureMode 的完整 FMEARow Context
        failure_modes = _find_downstream_failure_modes(graph_data, node["id"])
        if failure_modes:
            # 标记需要重新评估，AP 变化需人工确认
            return {
                "severity": {"old": None, "new": None, "reason": "needs_reassessment"},
                "affected_failure_modes": [fm["name"] for fm in failure_modes]
            }

    return None

def _find_related_failure_mode(graph_data, cause_id):
    """从 Cause 节点出发，沿 CAUSE_OF 边找到关联的 FailureMode。"""
    edges = graph_data.get("edges", [])
    nodes = {n["id"]: n for n in graph_data.get("nodes", [])}
    for e in edges:
        if e["source"] == cause_id and e["type"] == "CAUSE_OF":
            return nodes.get(e["target"])
    return None

def _find_downstream_failure_modes(graph_data, start_node_id):
    """从起始节点出发，沿下游边找到所有 FailureMode 节点。"""
    edges = graph_data.get("edges", [])
    nodes = {n["id"]: n for n in graph_data.get("nodes", [])}
    downstream_edges = ["HAS_FUNCTION", "FUNCTION_MAPPED_TO", "HAS_FAILURE_MODE"]
    # 简化的 BFS，限制深度为 3
    from collections import deque
    queue = deque([(start_node_id, 0)])
    visited = {start_node_id}
    failure_modes = []
    while queue:
        current, depth = queue.popleft()
        if depth >= 3:
            continue
        for e in edges:
            if e["source"] == current and e["type"] in downstream_edges:
                next_id = e["target"]
                if next_id not in visited:
                    visited.add(next_id)
                    node = nodes.get(next_id)
                    if node and node.get("type") == "FailureMode":
                        failure_modes.append(node)
                    queue.append((next_id, depth + 1))
    return failure_modes
```

**说明：**
- 当变更直接影响 S/O/D 时，算法从图中重构完整的 FMEARow Context，调用 `compute_ap()` 精确计算 AP 变化
- 当变更间接影响（如设计参数变更）时，标记为 "needs_reassessment"，列出受影响的 FailureMode 供人工确认
- 架构预留 LLM 接入点（Phase 4 可升级为更智能的风险预测）

### 4.3 影响评分算法

```python
def compute_impact_score(summary):
    score = summary.failure_modes_affected * 2
    score += summary.ap_upgraded_count * 3
    if summary.max_hop_distance > 2:
        score += 2
    return min(score, 10)
```

| 评分 | 颜色 | 含义 |
|------|------|------|
| 1-3 | 绿色 | 低风险，局部影响 |
| 4-6 | 黄色 | 中风险，需要关注 |
| 7-10 | 红色 | 高风险，建议重新评审 FMEA |

### 4.4 Neo4j 遍历实现

```cypher
-- 下游遍历（最大 5 跳），去重并取最短路径
MATCH path = (start:GraphNode {fmea_id: $fmea_id, node_id: $node_id})
  -[*1..5]->(end:GraphNode)
WHERE start.node_id <> end.node_id
WITH end, path ORDER BY length(path) ASC
WITH end, head(collect(path)) as shortest_path
RETURN
  end.node_id as node_id,
  end.type as node_type,
  end.name as name,
  length(shortest_path) as hop_distance,
  [n in nodes(shortest_path) | n.name] as path_names
ORDER BY hop_distance
```

### 4.5 JSONB 遍历实现

**不直接复用现有 `_trace_chain`**，因为当前实现缺少深度限制、路径追踪和边类型过滤能力。

JSONB 版本新增专用 BFS：

```python
def _bfs_with_path(graph_data, start_node_id, edge_filter, max_depth):
    """
    广度优先遍历，返回带路径信息的受影响节点。
    - edge_filter: 边类型白名单函数
    - max_depth: 最大遍历深度
    - 返回: [{node_id, node_type, name, path, hop_distance}, ...]
    """
    nodes = {n["id"]: n for n in graph_data.get("nodes", [])}
    edges = graph_data.get("edges", [])
    
    # 构建邻接表（按 edge_filter 过滤）
    adj = defaultdict(list)
    for e in edges:
        if edge_filter(e.get("type")):
            adj[e["source"]].append(e["target"])
    
    # BFS
    visited = set([start_node_id])
    queue = deque([(start_node_id, [start_node_id], 0)])
    results = []
    
    while queue:
        current_id, path, depth = queue.popleft()
        if depth >= max_depth:
            continue
        
        for next_id in adj.get(current_id, []):
            if next_id not in visited:
                visited.add(next_id)
                new_path = path + [next_id]
                node = nodes.get(next_id)
                if node:
                    results.append({
                        "node_id": next_id,
                        "node_type": node.get("type", ""),
                        "name": node.get("name", ""),
                        "path": [nodes[p].get("name", p) for p in new_path if p in nodes],
                        "hop_distance": depth + 1,
                    })
                queue.append((next_id, new_path, depth + 1))
    
    return results
```

**边类型白名单：**

| 传播方向 | 允许的边类型 |
|----------|-------------|
| downstream | `HAS_FUNCTION`, `FUNCTION_MAPPED_TO`, `HAS_FAILURE_MODE`, `EFFECT_OF`, `HAS_PROCESS_STEP` |
| upstream | `CAUSE_OF`, `PREVENTED_BY`, `DETECTED_BY`, `OPTIMIZED_BY` |

---

## 5. 前端架构设计

### 5.1 路由与页面

```typescript
// App.tsx 新增路由
{ path: "/change-impact", element: <ChangeImpactPage /> }
```

### 5.2 `ChangeImpactPage` 布局

左右分栏（40%/60%）：

**左栏 — 变更分析历史列表：**
- 搜索/过滤：FMEA 编号、节点名称、变更类型
- 表格列：时间、FMEA 编号、节点名称、变更类型、影响评分、操作
- 影响评分用 Tag 颜色区分：绿(1-3) / 黄(4-6) / 红(7-10)

**右栏 — 分析详情面板：**
- 顶部：变更信息卡片
- 中部：摘要卡片（受影响总数、FailureMode 数、AP 升级数）
- 下部：受影响节点列表（可展开显示路径）
- 底部操作："在图谱中查看"按钮

### 5.3 组件清单

```
frontend/src/components/change-impact/
├── ImpactReportPanel.tsx      # 分析结果展示（核心组件，多处复用）
├── ImpactScoreTag.tsx         # 影响评分标签（绿/黄/红）
├── AffectedNodeList.tsx       # 受影响节点列表（可展开）
├── ChangeHistoryTable.tsx     # 历史列表表格
└── index.ts
```

### 5.4 FMEA 编辑器集成

在 `FMEAEditorPage.tsx` 的节点详情面板中新增：

```tsx
<Card title="变更影响分析" size="small">
  <Space direction="vertical" style={{ width: "100%" }}>
    <Text type="secondary">分析此节点的变更对上下游的影响范围</Text>
    <Button
      type="primary"
      icon={<RadarChartOutlined />}
      onClick={() => setImpactModalOpen(true)}
      disabled={isViewer}
    >
      分析影响范围
    </Button>
  </Space>
</Card>
```

点击后弹出 Modal：选择变更类型 → 输入新值 → 执行分析 → 展示 `ImpactReportPanel`。

### 5.5 与知识图谱联动

**Phase 1 方案：复用现有 FMEA 编辑器中的"图谱" tab**

当前全局知识图谱页面（`/knowledge-graph`）不接收 `fmea_id`、`highlight_node` 等参数。优先复用已有能力：

```typescript
const graphUrl = `/fmea/${analysis.fmea_id}?tab=graph&highlightNode=${analysis.node_id}`;
```

跳转后：
- FMEA 编辑器自动切换到"图谱" tab
- `highlightNode` 参数使图谱自动聚焦到变更节点
- 用户在图谱中可手动查看上下游关联

**Phase 4 扩展（预留）：**
如需在全局知识图谱中高亮多条影响路径，需先扩展 `KnowledgeGraphPage` 支持 `fmea_id`、`highlight_node`、`highlight_affected` 参数解析。当前设计不实现此扩展，仅预留 URL 格式：
```typescript
// 预留格式，待 KnowledgeGraphPage 扩展后启用
const graphUrl = `/knowledge-graph?` + new URLSearchParams({
  fmea_id: analysis.fmea_id,
  highlight_node: analysis.node_id,
  highlight_affected: affectedNodeIds.join(","),
});
```

### 5.6 API Client

```typescript
// frontend/src/api/changeImpact.ts

export interface AnalyzeChangeImpactRequest {
  fmea_id: string;
  node_id: string;
  node_type: string;
  node_name: string;
  change_type: "attribute" | "structural";
  field_name?: string;
  new_value?: string;
}

export async function analyzeChangeImpact(
  data: AnalyzeChangeImpactRequest
): Promise<ChangeImpactAnalysis> {
  const resp = await client.post("/change-impact/analyze", data);
  return resp.data;
}

export async function listChangeImpacts(
  fmeaId: string
): Promise<ChangeImpactAnalysis[]> {
  const resp = await client.get(`/change-impact/fmea/${fmeaId}`);
  return resp.data;
}

export async function getChangeImpact(
  id: string
): Promise<ChangeImpactAnalysis> {
  const resp = await client.get(`/change-impact/${id}`);
  return resp.data;
}
```

**注意：** 前端 axios client 的 `baseURL` 为 `/api`，所以上述路径实际请求的是 `/api/change-impact/...`，与后端路由前缀一致。见 `frontend/src/api/client.ts`。

---

## 6. 交互流程

### 6.1 完整用户流程

```
[工程师在 FMEA 编辑器中查看 Component 节点]
  ↓
点击"分析影响范围"按钮
  ↓
弹出 Modal：
  - 变更类型：attribute（自动选中）
  - 字段：design_parameter（自动选中）
  - 新值：[用户输入]
  ↓
点击"执行分析"
  ↓
后端：图遍历 → 生成报告 → 持久化 → 返回结果
  ↓
前端展示 ImpactReportPanel：
  - 摘要：受影响 5 节点 / 2 FailureMode / 1 AP 升级
  - 列表：逐层展开影响路径
  ↓
用户点击"查看图谱"
  ↓
跳转 `/fmea/{id}?tab=graph&highlightNode={node}`，在 FMEA 编辑器图谱 tab 中聚焦变更节点
```

### 6.2 边界情况处理

| 场景 | 处理方式 |
|------|----------|
| 变更节点孤立（无上下游） | 返回空结果，`impact_score=0`，提示"该节点无上下游关联" |
| 图遍历超时 | `status` 设为 `failed`，前端提示"分析超时，请稍后重试" |
| 新值与旧值相同 | 前端校验拦截，提示"新值与当前值相同" |
| FMEA 状态为 `archived` | 允许查看历史，但禁用分析按钮 |
| 大量受影响节点（>50） | 列表分页展示 |
| viewer 角色 | 隐藏"分析影响范围"按钮，只读查看历史 |

---

## 7. 与现有模块的集成

| 模块 | 集成方式 |
|------|----------|
| **AuditLog** | Service 层自动写入 `change_impact_analyzed` 记录 |
| **知识图谱** | 跳转 FMEA 编辑器图谱 tab（`/fmea/{id}?tab=graph&highlightNode={node}`）；全局知识图谱联动预留 |
| **FMEA 状态机** | 预留：高风险变更（score ≥ 7）可触发状态回退到 `rework` |
| **D7 预防复发** | 预留：分析结果可作为 D7 步骤的输入数据 |
| **产品线路由器** | 分析记录按 `product_line_code` 隔离 |

---

## 8. 新增与修改文件清单

### 8.1 新增文件

| 文件路径 | 说明 |
|----------|------|
| `backend/alembic/versions/xxx_add_change_impact_analysis.py` | 数据库迁移 |
| `backend/app/models/change_impact.py` | SQLAlchemy 模型 |
| `backend/app/schemas/change_impact.py` | Pydantic Schema |
| `backend/app/services/change_impact_service.py` | Service 层 |
| `backend/app/api/change_impact.py` | API 路由 |
| `frontend/src/api/changeImpact.ts` | API Client |
| `frontend/src/components/change-impact/ImpactReportPanel.tsx` | 报告面板组件 |
| `frontend/src/components/change-impact/ImpactScoreTag.tsx` | 评分标签组件 |
| `frontend/src/components/change-impact/AffectedNodeList.tsx` | 节点列表组件 |
| `frontend/src/components/change-impact/ChangeHistoryTable.tsx` | 历史表格组件 |
| `frontend/src/components/change-impact/index.ts` | 组件导出 |
| `frontend/src/pages/ChangeImpactPage.tsx` | 主页面 |

### 8.2 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `backend/app/graph/jsonb_repository.py` | 新增 `analyze_change_impact` 方法 |
| `backend/app/graph/neo4j_repository.py` | 新增 `analyze_change_impact` 方法 |
| `backend/app/main.py` | 注册 `/change-impact` 路由 |
| `frontend/src/App.tsx` | 新增 `/change-impact` 路由 |
| `frontend/src/components/layout/AppLayout.tsx` | 新增侧边栏菜单项"变更影响分析" |
| `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` | 节点详情面板新增分析入口 |

---

## 9. 验收标准

### 9.1 功能验收

- [ ] 属性变更分析：修改 Component 设计参数，正确追溯下游 FailureMode
- [ ] 结构变更分析：删除节点，正确检测孤儿节点和失效链断裂
- [ ] 影响评分：评分算法正确，1-10 范围，颜色区分
- [ ] 持久化：分析结果保存到数据库，历史列表可查看
- [ ] 审计日志：每次分析自动写入 AuditLog
- [ ] 权限控制：viewer 无法执行分析，engineer 及以上可以
- [ ] 知识图谱联动：点击"查看图谱"正确高亮影响路径

### 9.2 性能验收

- [ ] Neo4j 场景：1000 节点 FMEA 的分析响应时间 < 2s
- [ ] JSONB 场景：500 节点 FMEA 的分析响应时间 < 3s
- [ ] 超时时长：图遍历超时阈值 10s

### 9.3 兼容性验收

- [ ] 同时支持 Neo4j 和 JSONB 两种 Repository 实现
- [ ] 不影响现有 FMEA 编辑器功能
- [ ] 不影响现有知识图谱页面功能

---

## 10. 后续扩展点（Phase 4）

1. **跨文档分析**：利用 `product_line_code` + 节点名称匹配，分析变更跨 FMEA 的影响
2. **LLM 风险预测**：将规则引擎升级为 LLM 驱动的智能风险预测
3. **变更审批流**：高风险变更（score ≥ 7）自动触发审批流程
4. **预警推送**：高风险变更自动通知相关责任人
5. **多实体支持**：API 扩展 `entity_type` 参数，支持控制计划、CAPA 等模块的变更分析
