# 全局知识库模块设计文档

**日期**: 2026-05-31
**模块**: 全局知识库 (Global Knowledge Base)
**阶段**: Phase 3 — AI + 知识图谱增强
**状态**: Approved

---

## 1. 目标

实现 OpenQMS 全局知识库：跨产品线 FMEA 聚合查询 + 数据脱敏，为前端知识图谱可视化提供数据支撑。

**范围：**
1. 补齐图查询 API 的 stats/similar 字段（AP 分布、高风险节点列表、平均 RPN）
2. 后端 AP 计算工具（AIAG-VDA 标准）
3. 数据脱敏机制
4. 前端全局知识库页面（统计卡片 + 风险列表 + 搜索）

**依赖：** Neo4j 基础设施（已完成）

---

## 2. 架构

```
PostgreSQL (FMEA graph_data JSONB)
  │
  ├── JSONBRepository ──┐
  │                      ├──→ FMEAGraphRepository 接口 ──→ api/graph.py ──→ 前端
  ├── Neo4jRepository ──┘        ↑
  │                              │
  └── Neo4j (Graph Projection) ──┘
```

**核心原则：**
- 全局查询走 `FMEAGraphRepository` 抽象层，前端不感知底层存储
- 脱敏在 API 层统一处理，Repository 返回原始数据
- AP 计算复用 AIAG-VDA 标准，前后端逻辑一致

---

## 3. 后端增强

### 3.1 AP 计算工具

文件：`backend/app/utils/ap_calculator.py`

复刻前端 `frontend/src/utils/fmea.ts` 的 `calculateAP` 逻辑到 Python：

```python
def calculate_ap(s: int, o: int, d: int) -> str:
    """基于 AIAG-VDA FMEA Handbook (2019) Appendix C1.5 计算 Action Priority.
    返回 'H' | 'M' | 'L' | '' (超出范围时)
    """
```

### 3.2 Repository 字段补齐

**`JSONBRepository.get_cross_fmea_stats`** 需补充：
- `ap_distribution`: {H: count, M: count, L: count}
- `high_ap_nodes`: [{node_id, name, ap, rpn, fmea_id, document_no}]
- `avg_rpn`: float
- `top_failure_modes`: [{name, rpn, fmea_id}]

**`Neo4jRepository.get_cross_fmea_stats`** 同步补齐相同字段。

**`find_similar_nodes`** 两端实现都需补充返回 `document_no`。

### 3.3 数据脱敏

文件：`backend/app/api/graph.py`

在全局查询端点（`/similar`、`/stats`）中，对返回结果进行脱敏：

| 脱敏字段 | 处理方式 |
|---------|---------|
| 人员相关 | 过滤 created_by / updated_by / approved_by 等 |
| 内部编号 | 保留 document_no（对外编号），脱敏内部系统 ID |
| 产品名称 | 保留产品类型，隐藏具体型号 |

脱敏逻辑封装为 `_sanitize_global_response(data)` 辅助函数。

---

## 4. 前端页面

### 4.1 数据契约

```typescript
// api/graph.ts
interface CrossFmeaStats {
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

interface SimilarNode {
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
│  高风险节点列表 (AP=H)                                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 名称          │ RPN  │ AP │ 来源文档      │ 操作      │  │
│  │ 焊接不良      │ 720  │ H  │ PFMEA-2026-001│ 查看图谱  │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  TOP10 失效模式                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 名称          │ RPN  │ 来源文档                        │  │
│  │ ...                                                    │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 交互流程

1. **页面加载**：读取当前产品线 → 调用 `getCrossFmeaStats(productLineCode)`
2. **产品线切换**：重新拉取 stats 数据
3. **搜索节点**：输入关键词 + 选择节点类型 → 防抖 300ms → 调用 `searchSimilarNodes` → 结果列表展示
4. **查看图谱**：点击"查看图谱" → 跳转 `/fmea/:id?tab=graph&highlightNode=:nodeId`
5. **影响/原因分析**：列表中节点支持快捷操作（后续与可视化模块联动）

---

## 5. 文件清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `backend/app/utils/ap_calculator.py` | AP 计算工具（AIAG-VDA 标准） |
| `frontend/src/api/graph.ts` | 图查询 API 客户端 |
| `frontend/src/pages/graph/KnowledgeGraphPage.tsx` | 全局知识库页面 |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `backend/app/graph/jsonb_repository.py` | 补齐 stats/similar 字段，添加 AP 计算 |
| `backend/app/graph/neo4j_repository.py` | 补齐 stats 字段 |
| `backend/app/api/graph.py` | 添加脱敏逻辑 |
| `frontend/src/App.tsx` | 注册 `/knowledge-graph` 路由 |

---

## 6. 验收标准

- [ ] `GET /api/graph/stats` 返回完整的 `ap_distribution`、`high_ap_nodes`、`avg_rpn`、`top_failure_modes`
- [ ] `GET /api/graph/similar` 返回结果包含 `document_no`
- [ ] 后端 AP 计算与前端 `calculateAP` 结果一致（相同 S/O/D 输入产出相同 H/M/L）
- [ ] 全局查询返回的数据已脱敏（无人员信息、无内部敏感字段）
- [ ] 前端全局知识库页面可正常展示统计卡片、风险列表、搜索结果
- [ ] 支持按产品线过滤（复用全局 ProductLineSelector）
- [ ] 中文 UI
- [ ] `npm run build` 通过，无 TypeScript 错误
