# 知识图谱可视化设计文档

**日期**: 2026-05-31  
**模块**: 知识图谱可视化 (Knowledge Graph Visualization)  
**阶段**: Phase 3 — AI + 知识图谱增强  
**技术栈**: AntV G6 v5 + React 18 + TypeScript

---

## 1. 背景与目标

OpenQMS 后端已完成 Neo4j 知识图谱基础设施（graph_sync_outbox、GraphSyncWorker、GraphProjectionService、图查询 API）。本设计为前端提供交互式图可视化能力，让用户能直观探索 FMEA 失效链、追溯影响范围、发现相似历史案例。

**成功标准**:
- FMEA 编辑器支持"表格/图谱"一键切换，所见即所得
- 独立知识图谱页支持跨 FMEA 聚合浏览与搜索
- 五种核心场景（失效链全貌、追溯影响、追溯原因、历史关键词搜索、风险地图）全部可用
- 首次渲染 < 2s（单 FMEA < 200 节点），交互帧率 > 30fps

---

## 2. 架构设计

### 2.1 文件结构

```
frontend/src/
├── api/graph.ts                    # 图查询 API 客户端
├── components/graph/
│   ├── GraphCanvas.tsx             # 共享 G6 画布（核心）
│   ├── GraphToolbar.tsx            # 工具栏（布局切换/缩放/全屏/缩略图）
│   ├── NodeDetailDrawer.tsx        # 节点详情侧边栏
│   ├── GraphLegend.tsx             # 图例说明
│   └── RiskMapPanel.tsx            # 风险地图统计面板
├── pages/graph/
│   └── KnowledgeGraphPage.tsx      # 独立全局知识图谱页
└── pages/planning/fmea/
    └── FMEAEditorPage.tsx          # 修改：添加"表格/图谱"Tab 切换
```

### 2.2 两个入口

| 入口 | 路由 | 用途 | 数据来源 |
|:---|:---|:---|:---|
| **FMEA 编辑器内嵌** | `/fmea/:id` (新增 Tab) | 查看当前 FMEA 的完整图谱 | `GET /api/fmea/{id}/graph` |
| **全局知识图谱** | `/knowledge-graph` (新路由) | 跨 FMEA 聚合、搜索、分析 | `GET /api/graph/*` |

---

## 3. 技术选型

**选用 AntV G6 v5**（`@antv/g6` 稳定版）。

**理由**:
- 与项目现有 Ant Design 5.x 同属蚂蚁生态，UI 风格一致
- 力导向（force）、层次（dagre）、紧凑树（compact-box）等 10+ 布局算法开箱即用
- 支持 WebGL 渲染，可处理 1000+ 节点
- 内置缩略图（minimap）、鱼眼（fisheye）、画布快照等高级插件
- 中文文档完善，社区活跃

**依赖**:
```bash
npm install @antv/g6
```

---

## 4. 组件设计

### 4.1 数据契约（前后端接口）

为了抹平 Neo4j 数据模型与 G6 渲染模型，前端统一使用以下接口：

```typescript
interface GraphNode {
  id: string;
  label: string;           // Neo4j Node Label，如 "FailureMode"
  properties: {
    name: string;
    severity?: number;
    occurrence?: number;
    detection?: number;
    ap?: string;            // H / M / L
    revised_severity?: number;
    revised_occurrence?: number;
    revised_detection?: number;
    revised_ap?: string;
    status?: string;
    responsible?: string;
    due_date?: string;
    // ... 其他 FMEA 业务字段
    [key: string]: any;
  };
  style?: any;             // G6 动态样式重写（用于高亮/置灰）
}

interface GraphEdge {
  source: string;
  target: string;
  label: string;           // 关系类型，如 "CAUSE_OF"
  properties?: {
    [key: string]: any;
  };
}
```

### 4.2 GraphCanvas（核心画布）

```typescript
interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  mode: 'single-fmea' | 'global';
  layout: 'dagre' | 'force' | 'compact-box';
  highlightNodes?: string[];      // 高亮节点 ID 列表
  dimOthers?: boolean;            // 非高亮节点是否置灰
  onNodeClick?: (node: GraphNode) => void;
  onNodeDoubleClick?: (node: GraphNode) => void;
  onNodeContextMenu?: (node: GraphNode, event: MouseEvent) => void;
}
```

**行为**:
- 初始化时自动计算布局并居中
- 支持滚轮缩放、拖拽画布、框选多节点
- 双击节点：展开/折叠其邻居（仅 single-fmea 模式）。通过 G6 **collapse-expand behavior** 配置实现；需要程序控制时调用元素展开/收起 API。布局重计算时启用 `animate: true` 过渡动画，避免节点位置瞬间跳跃
- 右键节点：弹出菜单（查看详情 / 追溯影响 / 追溯原因）

**布局策略**：
- `single-fmea` 模式默认使用 `dagre`（层次布局，方向 `LR` 从左到右），契合 FMEA 层级因果链的心智模型
- `global` 模式默认使用 `force`（力导向），展示跨 FMEA 的松散关联网络
- 用户可随时通过工具栏切换布局

### 4.3 GraphToolbar

工具栏按钮：
- 布局切换：力导向 ↔ 层次 ↔ 紧凑树
- 缩放：放大 / 缩小 / 适应画布
- 缩略图开关
- 全屏切换
- 下载快照（PNG）

### 4.4 NodeDetailDrawer

右侧 Drawer，展示选中节点的完整属性：
- 节点类型、名称、ID
- FMEA 专有字段：severity、occurrence、detection、RPN（`S × O × D`）
- **AP（Action Priority）评级过程**：根据 S/O/D 查表得出 H/M/L，与 RPN 同时展示（AIAG-VDA 标准兼容）
- 修订后字段：revised_severity、revised_occurrence、revised_detection、revised_AP
- 关联节点快捷跳转列表
- 如果是 FailureMode，同时显示 **RPN 计算过程** 和 **AP 判定逻辑**

---

## 5. 节点与边样式

### 5.1 节点映射表

| 节点类型 | 填充色 | 边框色 | 形状 | 图标 |
|:---|:---|:---|:---|:---|
| System / ProcessItem | `#e6f7ff` | `#1890ff` | 矩形 | 🏭 |
| Subsystem / ProcessStep | `#f0f5ff` | `#69c0ff` | 矩形 | ⚙️ |
| Component / WorkElement | `#e6fffb` | `#36cfc9` | 矩形 | 🔩 |
| Function | `#f6ffed` | `#52c41a` | 圆角矩形 | ✅ |
| **FailureMode** | `#fff1f0` | `#ff4d4f` | **菱形** | ⚠️ |
| FailureEffect | `#fff7e6` | `#fa8c16` | 椭圆 | 🔥 |
| FailureCause | `#fffbe6` | `#faad14` | 椭圆 | 🔍 |
| PreventionControl | `#f6ffed` | `#73d13d` | 圆形 | 🛡️ |
| DetectionControl | `#f9f0ff` | `#722ed1` | 圆形 | 🔬 |
| RecommendedAction | `#f5f5f5` | `#8c8c8c` | 矩形 | 📝 |

### 5.2 边映射表

| 边类型 | 颜色 | 线型 | 箭头 |
|:---|:---|:---|:---|
| `HAS_FAILURE_MODE` / `FUNCTION_MAPPED_TO` | `#8c8c8c` | 实线 | → |
| `EFFECT_OF` | `#fa8c16` | 实线 | → |
| `CAUSE_OF` | `#faad14` | 实线 | → |
| `PREVENTED_BY` | `#73d13d` | 虚线 | → |
| `DETECTED_BY` | `#722ed1` | 虚线 | → |
| `OPTIMIZED_BY` | `#bfbfbf` | 点线 | → |
| `HAS_NODE` (Neo4j) | `#d9d9d9` | 实线 | → |

### 5.3 高亮与置灰

- **高亮路径**: 路径上的节点边框加粗至 3px，边加粗至 2px，颜色统一用 `#ff4d4f` 红色渐变
- **置灰其他**: 非路径节点 opacity 降至 0.2，边 opacity 降至 0.1
- **AP=H 风险脉冲**: 高风险节点添加 CSS 脉冲动画（红色阴影扩散）

---

## 6. 四种场景实现

### 6.1 场景一：失效链全貌

**入口**: FMEA 编辑器 → 图谱 Tab  
**API**: `GET /api/fmea/{id}/graph`  
**实现**:
1. FMEAEditorPage 添加 `activeView: 'table' | 'graph'` state
2. **Tab 切换状态缓存**：在 FMEAEditorPage 中用 `useRef` 或父级 state 缓存图谱数据，切换 Tab 时不重新 Fetch，做到无感秒切；仅在 FMEA 数据变更时刷新缓存
3. 首次切换到 graph 时，调用 `getFmeaGraph(id)` 获取 JSONB 图数据并缓存
4. GraphCanvas 以 `layout='dagre'`（层次布局，方向 LR）初始化，自动展开全部节点
5. 双击节点：调用 `graph.collapse/expand` 切换邻居显隐，**布局重计算启用动画过渡**

### 6.2 场景二：追溯影响范围

**入口**: 两者（编辑器右键菜单 / 全局页面工具栏）  
**API**: `GET /api/graph/fmea/{id}/impact/{nodeId}`  
**实现**:
1. 用户右键节点选择"追溯影响"或点击工具栏"影响分析"按钮
2. 调用 `getImpactChain(fmeaId, nodeId)` 获取下游节点列表
3. GraphCanvas 接收 `highlightNodes=[...nodeIds]`，`dimOthers=true`
4. 高亮路径从选中节点向终端节点延伸，红色渐变

### 6.3 场景三：历史关键词搜索

**入口**: 全局知识图谱页  
**API**: `GET /api/graph/similar?node_type=FailureMode&name_keyword=...&product_line_code=...`  
**说明**: 当前后端实现为关键词模糊匹配（`name CONTAINS keyword`），无 similarity 评分算法。首版命名为"历史关键词搜索"，后续可升级为语义相似度搜索（Neo4j GDS / 向量检索）。  
**实现**:
1. 全局页面顶部提供搜索框 + 节点类型下拉
2. 输入关键词后调用 `searchSimilarNodes(params)`（防抖 300ms）
3. 结果以列表形式展示（名称、节点类型、来源 FMEA 文档号）
4. 点击列表项 → 打开对应 FMEA 的图谱视图，并高亮定位该节点

### 6.4 场景四：全局风险地图（统计 + 列表）

**入口**: 全局知识图谱页 → "风险地图" Tab  
**API**: `GET /api/graph/stats?product_line_code=...`  

**风险定义统一**：以 **AP（Action Priority）** 作为核心风险指标，RPN 作为辅助参考。后端 stats 接口需补充以下字段：

```typescript
interface CrossFmeaStats {
  total_fmeas: number;
  total_nodes: number;
  node_type_distribution: Record<string, number>;
  // AP 优先的风险统计（需后端补充）
  ap_distribution: { H: number; M: number; L: number };
  high_ap_nodes: Array<{ name: string; ap: string; fmea_id: string; document_no: string }>;
  avg_rpn: number;
  top_failure_modes: Array<{ name: string; rpn: number; fmea_id: string }>;
}
```

**实现**:
1. 调用 `getCrossFmeaStats(productLineCode)` 获取聚合数据
2. 顶部统计卡片：FMEA 总数、节点总数、AP 分布（H/M/L 饼图）、平均 RPN
3. 高风险列表：AP=H 的 FailureMode 表格（名称、来源文档、RPN、操作列"查看图谱"）
4. 点击列表项 → 打开对应 FMEA 的图谱视图，该节点自动高亮并脉冲动画
5. 支持按产品线过滤（复用全局 ProductLineSelector）

**注意**：全局页首版以"统计卡片 + 数据列表 + 搜索"为主，不承诺跨 FMEA 的全局画布渲染（后端 `stats` 不返回全局 nodes/edges）。后续如需全局画布，需新增 `GET /api/graph/overview` 接口聚合所有 FMEA 的图数据。

### 6.5 场景五：追溯原因链

**入口**: FMEA 编辑器右键菜单 / 全局页面工具栏  
**API**: `GET /api/graph/fmea/{id}/cause/{nodeId}`  
**实现**:
1. 用户右键节点选择"追溯原因"或点击工具栏"原因分析"按钮
2. 调用 `getCauseChain(fmeaId, nodeId)` 获取上游节点列表（沿 CAUSE_OF 边反向追溯 1-3 层）
3. GraphCanvas 接收 `highlightNodes=[...nodeIds]`，`dimOthers=true`
4. 高亮路径从选中节点向上游原因节点延伸，黄色渐变（与影响链的红色区分）
5. 同时在 NodeDetailDrawer 中展示追溯路径的文字摘要（节点名 → 节点名 → ...）

---

## 7. 数据流

### 7.1 单 FMEA 图谱

```
FMEAEditorPage
  ├── graphData: useRef<{ nodes, edges } | null>   # Tab 切换缓存，避免重复 Fetch
  │
  ├── activeView='graph'
  │     └── 首次切换: getFmeaGraph(fmeaId) → 写入 graphData
  │           └── 后续切换: 直接读取 graphData（无感秒切）
  │                 └── GraphCanvas(nodes, edges, mode='single-fmea')
  │                       └── G6 Graph 实例
  └── activeView='table'
        └── 现有表格编辑器（不变）
        └── 表格保存后: 清空 graphData 缓存，下次切回 graph 时重新拉取
```

### 7.2 全局知识图谱

```
KnowledgeGraphPage
  ├── 视图模式 state: 'overview' | 'risk-map' | 'similar-search' | 'impact-analysis' | 'cause-analysis'
  │
  ├── overview / risk-map: getCrossFmeaStats(productLineCode)
  │     └── 统计卡片 + RiskMapPanel + 高风险节点列表（点击跳转单 FMEA 图谱）
  │
  ├── similar-search: searchSimilarNodes(params)
  │     └── 搜索结果列表（无画布，点击跳转单 FMEA）
  │
  ├── impact-analysis: getImpactChain(fmeaId, nodeId)
  │     └── GraphCanvas(highlightNodes, dimOthers=true) 或嵌入单 FMEA 编辑器
  │
  └── cause-analysis: getCauseChain(fmeaId, nodeId)
        └── GraphCanvas(highlightNodes, dimOthers=true) 或嵌入单 FMEA 编辑器
```

**全局页首版定位**：以统计聚合、列表浏览、跨 FMEA 搜索为核心，不承诺全局画布渲染。单 FMEA 的详细图谱通过链接跳转至 `/fmea/:id?tab=graph` 展示。

---

## 8. 路由与导航

### 8.1 新增路由

```typescript
// App.tsx 新增
<Route path="/knowledge-graph" element={<KnowledgeGraphPage />} />
```

### 8.2 导航入口

- FMEA 编辑器：现有 Tab 栏新增"🕸️ 图谱"Tab
- 侧边栏导航：在"规划"分组下新增"知识图谱"菜单项（指向 `/knowledge-graph`）
- 仪表盘：在 KPI 卡片区域预留"知识图谱"快捷入口（后续迭代）

---

## 9. 错误处理

| 场景 | 行为 |
|:---|:---|
| G6 初始化失败 | 降级为文本列表展示节点关系（列表视图） |
| API 返回空图 | 显示"该 FMEA 暂无图谱数据"空状态 |
| 节点数 > 500 | 提示"节点过多，建议切换至层次布局"，自动启用性能模式（隐藏标签） |
| 图查询超时 | Spin 加载 + 30s 后提示"数据量较大，请稍后重试" |
| Neo4j 未配置 | 全局页面显示"知识图谱功能需要 Neo4j 支持"提示，隐藏相关入口 |

---

## 10. 性能考虑

- **首次渲染**: G6 初始化 + 布局计算异步执行，显示 Spin 遮罩
- **大数据量**: 节点 > 200 时自动启用 `lod`（Level of Detail），缩小后隐藏标签
- **内存管理**: 组件卸载时调用 `graph.destroy()` 释放 G6 实例
- **防抖**: 搜索框输入防抖 300ms，避免频繁调用相似节点 API

---

## 11. 验收标准

### 功能验收
- [ ] FMEA 编辑器支持"表格/图谱"Tab 切换，切换无闪烁（依赖 Tab 缓存）
- [ ] 图谱正确渲染 PFMEA 和 DFMEA 的所有节点类型与边关系
- [ ] 双击节点可展开/折叠邻居，布局重计算有过渡动画，无闪烁跳跃
- [ ] 右键"追溯影响"正确高亮下游路径（红色渐变），其他节点置灰
- [ ] 右键"追溯原因"正确高亮上游路径（黄色渐变），其他节点置灰
- [ ] 全局知识图谱页支持五种视图模式切换（总览/风险地图/关键词搜索/影响分析/原因分析）
- [ ] 历史关键词搜索支持按节点类型和关键词过滤，结果列表可点击跳转至单 FMEA 图谱
- [ ] 风险地图统计卡片展示 AP 分布、平均 RPN、高风险节点列表，数据与后端一致
- [ ] 支持按产品线过滤（租户隔离）
- [ ] 页面支持中文 UI

### 性能验收
- [ ] 单 FMEA 图谱（< 200 节点）首次渲染 < 2s，切换 Tab 无感秒切（缓存命中时 < 100ms）
- [ ] 交互帧率 > 30fps（拖拽、缩放、展开折叠流畅）
- [ ] 节点数 > 500 时自动启用性能模式（隐藏标签），不阻塞主线程

### 健壮性验收
- [ ] G6 初始化失败时降级为文本列表视图，不白屏
- [ ] `npm run build` 通过，无 TypeScript 错误
