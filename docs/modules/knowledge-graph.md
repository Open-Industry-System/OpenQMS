# 知识图谱与变更影响分析模块 — 用户手册

> 最后更新: 2026-06-13 | 适用版本: OpenQMS v1.0

---

## 1. 功能概述

知识图谱与变更影响分析模块基于 FMEA 图数据构建跨文档的知识关联网络，为质量工程师提供以下能力：

| 子模块 | 路由 | 功能范围 |
|--------|------|----------|
| 知识图谱 | `/knowledge-graph` | 跨 FMEA 风险总览、关键词/语义搜索相似节点、全局知识库统计 |
| 变更影响分析 | `/change-impact` | 变更影响分析历史查看、影响报告详情、在图谱中定位受影响节点 |

两个子模块通过 FMEA 编辑器紧密集成：在 FMEA 图谱编辑器中可直接发起变更影响分析（需 FMEA EDIT 权限），分析结果可跳转回图谱查看。

---

## 2. 适用角色与权限

### 2.1 知识图谱 (`knowledge_graph`)

知识图谱模块使用独立的 ModuleKey 权限控制：

| 角色 | PermissionLevel | 说明 |
|------|:---------------:|------|
| admin | 1 (VIEW) | 可查看跨产品线全局统计（已脱敏） |
| manager | 1 (VIEW) | 可查看所属产品线的统计数据和相似节点搜索 |
| quality_engineer | 无权限行 | 默认不可访问（需 admin 手动赋权） |
| field_qe / planning_qe / supplier_qe / customer_qe | 无权限行 | 默认不可访问 |
| viewer | 无权限行 | 默认不可访问 |

> **权限说明：** `knowledge_graph` 模块当前仅对 admin 和 manager 授予 VIEW 权限。其他角色若需访问，需要 admin 在角色权限管理中为对应角色添加 `knowledge_graph` 模块的权限行。前端路由 `/knowledge-graph` 不检查模块权限，仅检查登录状态，但 API 层会根据角色权限过滤数据（例如 `global-stats` 端点要求 ADMIN 权限，`similar-nodes` 端点无全局权限时自动降级搜索范围）。

**API 权限对照：**

| API 端点 | 最低权限 | 说明 |
|----------|----------|------|
| `GET /api/graph/stats` | 仅登录 | 跨 FMEA 聚合统计（按产品线） |
| `GET /api/graph/global-stats` | ADMIN | 跨产品线全局统计（数据脱敏） |
| `GET /api/graph/similar` | 仅登录 | 关键词搜索相似节点（按产品线） |
| `POST /api/graph/similar-nodes` | 仅登录（无 KNOWLEDGE_GRAPH VIEW 时 scope 自动降级） | 语义相似搜索 |
| `GET /api/graph/fmea/{id}/impact/{node}` | 仅登录 | 下游影响链 |
| `GET /api/graph/fmea/{id}/cause/{node}` | 仅登录 | 上游原因链 |
| `POST /api/graph/rebuild` | ADMIN | 触发 Neo4j 全量重建 |

### 2.2 变更影响分析 (`change-impact`)

变更影响分析模块不使用独立的 ModuleKey 权限，而是复用 FMEA 模块权限：

| 操作 | 最低权限 | 说明 |
|------|----------|------|
| 发起变更影响分析 | FMEA EDIT (3) | 需要 FMEA 编辑权限 |
| 查看分析历史 | FMEA VIEW (1) | 需要 FMEA 查看权限 |
| 查看分析详情 | FMEA VIEW (1) | 需要 FMEA 查看权限 |

> **注意：** 前端路由 `/change-impact` 不检查模块权限，仅检查登录状态。API 层通过 FMEA 模块权限控制访问。此外，工厂隔离（factory scope）同样适用于变更影响分析：用户只能看到所属工厂的数据。

---

## 3. 知识图谱

### 3.1 页面入口与布局

从侧边栏点击 **"知识图谱"** 进入 `/knowledge-graph` 页面。页面顶部为产品线选择器，页面主体分为三个 Tab：

| Tab | 图标 | 说明 |
|-----|------|------|
| 总览 / 风险地图 | BarChartOutlined | 跨 FMEA 聚合统计面板 |
| 历史关键词搜索 | SearchOutlined | 按节点类型和关键词搜索 |
| 语义搜索 | RobotOutlined | 基于相似度评分的智能搜索 |

> 若未选择产品线，页面显示"请先选择产品线"空状态。

### 3.2 总览 / 风险地图

选择产品线后，系统调用 `GET /api/graph/stats?product_line_code=xxx` 获取该产品线下所有已审批 FMEA 的聚合统计信息。

**展示内容：**

| 指标 | 说明 |
|------|------|
| FMEA 总数 | 该产品线下已审批通过的 FMEA 文档数量 |
| 节点总数 | 所有 FMEA 图数据中的节点总量 |
| 高优先级失效模式 (AP=H) | Action Priority 为 "H"（高）的失效模式数量，以红色火焰图标突出显示 |
| 平均 RPN | 所有失效模式的平均风险优先数（取最高 RPN 行） |

**AP 分布卡片：** 以 Tag 形式展示 AP 等级分布：
- 红色 Tag：高 (H) — 高优先级失效模式数量
- 橙色 Tag：中 (M) — 中优先级失效模式数量
- 绿色 Tag：低 (L) — 低优先级失效模式数量

**高优先级失效模式 Top 10 表格：** 列出 AP=H 的失效模式，包含以下列：

| 列 | 说明 |
|----|------|
| 失效模式 | 节点名称 |
| RPN | 风险优先数 |
| 来源 FMEA | 关联的 FMEA 文档编号，点击可跳转到该 FMEA 的图谱 Tab 并高亮此节点 |
| 操作 | "查看图谱"按钮，跳转到对应 FMEA 图谱 |

**节点类型分布卡片：** 以 Tag 列表展示各节点类型的数量，例如 `ProcessStep: 15`、`FailureMode: 8` 等。

### 3.3 历史关键词搜索

在"历史关键词搜索" Tab 中，用户可按节点类型和关键词在当前产品线内搜索 FMEA 节点。

**操作步骤：**

1. 在下拉框中选择节点类型：
   - 失效模式 (`FailureMode`)
   - 失效原因 (`FailureCause`)
   - 失效影响 (`FailureEffect`)
   - 功能 (`Function`)
2. 在搜索框中输入关键词
3. 点击搜索或按回车

系统调用 `GET /api/graph/similar?node_type=xxx&name_keyword=xxx&product_line_code=xxx` 进行关键词匹配搜索。

**搜索结果表格：**

| 列 | 说明 |
|----|------|
| 名称 | 匹配到的节点名称 |
| 类型 | 节点类型 |
| 来源 FMEA | 关联 FMEA 文档编号，点击可跳转 |
| 操作 | "查看"按钮，跳转到 FMEA 图谱并高亮该节点 |

### 3.4 语义搜索

语义搜索 Tab（`SemanticSearchTab` 组件）提供基于相似度评分的智能搜索，调用 `POST /api/graph/similar-nodes` 端点。

**搜索范围：**

- **当前产品线 (`current_product_line`)：** 仅搜索用户所属产品线的已审批 FMEA 节点
- **全局 (`global`)：** 搜索所有产品线的已审批 FMEA 节点。若无 `knowledge_graph` VIEW 权限，系统自动将 global 请求降级为 `current_product_line`

**相似度机制：** 系统通过 `compute_similarity()` 函数计算查询文本与节点名称的相似度评分（0.0–1.0），低于 `min_similarity`（默认 0.3）的结果被过滤。

**返回字段：**

| 字段 | 说明 |
|------|------|
| node_id | 节点 ID |
| name | 节点名称（无全局权限时跨产品线节点名称脱敏） |
| type | 节点类型 |
| fmea_id | 来源 FMEA ID |
| document_no | 来源 FMEA 编号 |
| product_line_code | 产品线代码 |
| product_line_name | 产品线名称 |
| similarity_score | 相似度评分（0–1） |
| match_reason | 匹配原因说明 |

> **数据脱敏：** 当用户缺少 `knowledge_graph` 全局权限时，跨产品线的搜索结果中节点名称会被脱敏处理（保留前 2 个字符，其余替换为 `***`），防止信息泄露。

### 3.5 全局统计（Admin Only）

Admin 角色可访问 `GET /api/graph/global-stats` 端点，查看跨所有产品线的聚合统计。该端点：

- 不接受 `product_line_code` 参数（传入则返回 400 错误）
- 返回数据经过白名单重建和名称脱敏处理（`mask_name()` 函数）
- 脱敏规则：保留名称前 2 个字符，其余替换为 `***`；长度 ≤2 的名称仅保留首字符 + `***`

### 3.6 图谱重建

Admin 角色可通过 `POST /api/graph/rebuild` 端点触发 Neo4j 全量重建。该操作：

- 以异步后台任务执行，立即返回成功响应
- 清空 Neo4j 中所有现有数据
- 重新创建约束和索引
- 遍历 PostgreSQL 中所有 FMEA 文档，逐个投影到 Neo4j
- 适用于 Neo4j 数据不一致或大规模数据修复场景

---

## 4. 变更影响分析

### 4.1 功能说明

变更影响分析用于评估 FMEA 图数据中单个节点发生变更时，对关联节点的潜在影响范围和风险等级变化。典型场景包括：

- **属性变更：** 修改失效模式的严重度 (S)、发生度 (O)、探测度 (D)
- **结构变更：** 增加、删除或移动图中的节点和连接

### 4.2 发起分析

变更影响分析有两种入口：

**入口 1：FMEA 编辑器内**

在 FMEA 图谱编辑器（`/fmea/:id?tab=graph`）中，选中节点后可发起变更影响分析。系统自动填充 `fmea_id`、`node_id`、`node_type`、`node_name` 等参数，用户仅需选择变更类型和填写变更字段。

**入口 2：变更影响分析页面**

在 `/change-impact` 页面查看历史分析记录，但不支持从该页面直接发起新分析。

### 4.3 API 调用

```
POST /api/change-impact/analyze
```

**请求参数 (`ChangeImpactAnalyzeRequest`)：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| fmea_id | UUID | 是 | 所属 FMEA 文档 ID |
| node_id | string | 是 | 变更节点 ID |
| node_type | string | 是 | 节点类型（如 `FailureMode`、`FailureCause`） |
| node_name | string | 是 | 节点名称 |
| change_type | string | 是 | 变更类型：`attribute`（属性变更）或 `structural`（结构变更） |
| field_name | string | 否 | 变更字段名（如 `severity`、`occurrence`、`detection`） |
| new_value | string | 否 | 变更后的值 |

**权限要求：** FMEA 模块 EDIT 权限（Level 3+）。

### 4.4 分析逻辑

系统根据变更类型和字段选择不同的遍历策略：

#### 变更类型：属性变更 (`attribute`)

| 变更字段 | 遍历方向 | 说明 |
|----------|----------|------|
| `name` / `description` | 无遍历 | 名称和描述的变更不影响其他节点的风险等级 |
| `severity` / `occurrence` / `detection` | 双向（downstream + upstream） | S/O/D 变更会同时影响下游失效效应和控制措施，以及上游失效原因 |
| 其他字段 | 下游 (downstream) | 默认追踪下游影响链 |

#### 变更类型：结构变更 (`structural`)

仅追踪下游 (downstream) 方向。

#### 边类型过滤

**下行遍历（downstream）使用的边类型：**

| 边类型 | 说明 |
|--------|------|
| `HAS_FUNCTION` | 过程步骤/工作元素 → 功能 |
| `FUNCTION_MAPPED_TO` | 功能 → 失效模式 |
| `HAS_FAILURE_MODE` | 结构节点 → 失效模式 |
| `EFFECT_OF` | 失效模式 → 失效影响 |
| `HAS_PROCESS_STEP` | 过程项 → 过程步骤 |
| `HAS_CHILD` | 父节点 → 子节点 |

**上行遍历（upstream）使用的边类型：**

| 边类型 | 说明 |
|--------|------|
| `CAUSE_OF` | 失效原因 → 失效模式 |
| `PREVENTED_BY` | 预防控制 → 失效原因 |
| `DETECTED_BY` | 探测控制 → 失效原因/失效模式 |
| `OPTIMIZED_BY` | 优化措施 → 失效模式 |

> BFS 遍历最大深度为 5 跳。

### 4.5 风险变化计算

系统对受影响的 FailureMode 和 FailureCause 节点计算风险等级变化：

**场景 1：FailureMode 自身 S/O/D 变更**

重新计算 RPN 和 AP（Action Priority），对比变更前后的 AP 等级。

**场景 2：FailureCause 的 O/D 变更影响关联 FailureMode**

找到该 Cause 关联的 FailureMode，重新计算最大 RPN 行的 O/D/AP，对比变更前后。

**场景 3：Component/ProcessStep 的 design_parameter 变更**

对关联的 FailureMode 标记 `needs_reassessment: true`，表示需要人工重新评估。

### 4.6 影响评分算法

影响评分由 Service 层单点计算（0–10 分）：

```
score = failure_modes_affected × 2 + ap_upgraded_count × 3 + (max_hop_distance > 2 ? 2 : 0)
score = min(score, 10)  // 封顶 10 分
```

| 因素 | 权重 | 说明 |
|------|------|------|
| 受影响失效模式数 | 2 分/个 | 直接影响的 FailureMode 数量 |
| AP 升级数 | 3 分/个 | AP 等级提升（L→M、M→H 等）的数量 |
| 远距离影响 | +2 分 | 最大跳数 > 2 时额外加分 |

**评分等级对应颜色：**

| 评分 | 等级 | 颜色 |
|:----:|------|------|
| 0–3 | 低 | 绿色 |
| 4–6 | 中 | 橙色 |
| 7–10 | 高 | 红色 |

### 4.7 分析结果页面

访问 `/change-impact` 页面，左侧为分析历史表格，右侧为选中记录的详情面板。

**分析历史表格 (`ChangeHistoryTable`)：**

| 列 | 说明 |
|----|------|
| 时间 | 分析创建时间 |
| 节点名 | 变更节点名称 |
| 变更类型 | "属性"或"结构" |
| 影响评分 | 影响评分 Tag（颜色编码） |
| 受影响节点数 | summary.total_affected |

**分析详情面板 (`ImpactReportPanel`)：**

1. **变更信息卡片：** 显示节点名、类型、变更类型（属性/结构 Tag）、字段名、新值
2. **统计卡片行：**
   - 影响评分（ImpactScoreTag）
   - 受影响节点数
   - FailureMode 数
   - AP 升级数
3. **受影响节点列表 (`AffectedNodeList`)：** 可展开列表，每个节点显示：
   - 节点名称和类型
   - 影响类型 Tag（upstream/downstream/direct）
   - 跳数距离（hop_distance）
   - 路径可视化
   - 风险变化详情（old_ap → new_ap）
4. **"在图谱中查看"按钮：** 跳转到 `/fmea/{fmea_id}?tab=graph&highlightNode={node_id}`

### 4.8 API 查询端点

| 端点 | 方法 | 说明 | 权限 |
|------|------|------|------|
| `/api/change-impact/analyze` | POST | 发起变更影响分析 | FMEA EDIT |
| `/api/change-impact` | GET | 查询所有分析记录（支持 product_line_code 分页筛选） | FMEA VIEW |
| `/api/change-impact/fmea/{fmea_id}` | GET | 按指定 FMEA 查询分析记录 | FMEA VIEW |
| `/api/change-impact/{analysis_id}` | GET | 获取单条分析详情 | FMEA VIEW |

**列表查询参数：**

| 参数 | 说明 |
|------|------|
| `product_line_code` | 可选，按产品线筛选 |
| `page` | 页码，默认 1 |
| `page_size` | 每页条数，默认 20，最大 1000 |

---

## 5. 技术架构

### 5.1 双后端存储架构

知识图谱模块采用 **Repository 模式**，提供两种可切换的图存储后端：

| 后端 | 类 | 适用场景 | 配置 |
|------|-----|----------|------|
| PostgreSQL JSONB | `JSONBRepository` | 开发/测试环境，或 Neo4j 不可用时的 fallback | `GRAPH_REPOSITORY=jsonb`（默认） |
| Neo4j | `Neo4jRepository` | 生产环境，需要跨文档图遍历和复杂查询 | `GRAPH_REPOSITORY=neo4j` |

选择逻辑在 `app/graph/deps.py` 中根据 `settings.GRAPH_REPOSITORY` 配置自动注入对应的 Repository 实现。

### 5.2 Neo4j 数据投影

FMEA 图数据存储在 PostgreSQL 的 `graph_data` JSONB 列中，通过 Outbox 模式异步投影到 Neo4j：

```
FMEA 创建/更新/状态变更
        ↓
  GraphSyncOutbox 入队（event_type: fmea.created / fmea.updated / fmea.status_changed）
        ↓
  GraphSyncWorker 轮询（5s 间隔，FOR UPDATE SKIP LOCKED）
        ↓
  GraphProjectionService 生成 Cypher 语句（DELETE + CREATE 幂等投影）
        ↓
  Neo4j 写事务执行
```

**节点投影属性：**

| 属性 | 来源 |
|------|------|
| `node_id` | 图节点 `id` |
| `name` | 图节点 `name` |
| `type` | 图节点 `type` |
| `process_number` / `classification` / `requirement` / `specification` | 节点业务属性 |
| `severity` / `occurrence` / `detection` / `ap` / `rpn` | 风险参数 |

**边投影：** 仅投影白名单中的边类型（`ALLOWED_EDGE_TYPES`），防止用户输入注入 Cypher 查询。

**节点标签映射：** `PreventionControl` 和 `DetectionControl` 在 Neo4j 中映射为 `Control` 标签。

### 5.3 Outbox 可靠性保障

`GraphSyncOutbox` 表实现异步可靠投影：

| 字段 | 说明 |
|------|------|
| `status` | `pending` → `processing` → `completed` / `dead` |
| `attempt_count` | 重试次数，最多 5 次 |
| `next_attempt_at` | 下次重试时间（指数退避：10s → 30s → 90s → 270s） |
| `last_error` | 最近一次失败信息 |

**Worker 机制：**

- 轮询间隔：5 秒
- 批量大小：10 条
- 并发控制：PostgreSQL `FOR UPDATE SKIP LOCKED` 原子抢占
- 僵死恢复：启动时清理超过 10 分钟的 `processing` 状态任务
- 去重：同一 `aggregate_id`（即 FMEA ID）只保留最新一条事件

### 5.4 数据模型

#### 知识图谱核心实体

```
FMEADocument (PostgreSQL)
  ├── fmea_id: UUID (PK)
  ├── document_no: str (编号，如 PFMEA-2026-001)
  ├── product_line_code: str
  ├── status: str (draft/submitted/approved/rejected)
  ├── graph_data: JSONB        ← 图数据主存储
  │     ├── nodes: [{id, name, type, severity, occurrence, detection, ap, ...}]
  │     └── edges: [{source, target, type}]
  └── ...
```

#### Neo4j 投影结构

```
(:FMEDocument {fmea_id, document_no, product_line_code})
(:GraphNode {node_id, name, type, severity, occurrence, detection, ap, rpn, ...})
(:Control {node_id, name, type, ...})  ← PreventionControl / DetectionControl 的统一标签

(:FMEDocument)-[:HAS_NODE]->(:GraphNode)
(:GraphNode)-[:HAS_PROCESS_STEP]->(:GraphNode)
(:GraphNode)-[:HAS_FAILURE_MODE]->(:GraphNode)
(:GraphNode)-[:EFFECT_OF]->(:GraphNode)
(:GraphNode)-[:CAUSE_OF]->(:GraphNode)
(:GraphNode)-[:PREVENTED_BY]->(:Control)
(:GraphNode)-[:DETECTED_BY]->(:Control)
...
```

#### 变更影响分析实体

```
ChangeImpactAnalysis (PostgreSQL)
  ├── id: UUID (PK)
  ├── fmea_id: UUID (FK → fmea_documents)
  ├── product_line_code: str
  ├── factory_id: UUID (FK → factories)
  ├── node_id: str           ← 变更节点 ID
  ├── node_type: str         ← 变更节点类型
  ├── node_name: str         ← 变更节点名称
  ├── change_type: str       ← "attribute" 或 "structural"
  ├── field_name: str?       ← 变更字段名
  ├── old_value: str?        ← 变更前值
  ├── new_value: str?        ← 变更后值
  ├── scope: str             ← 分析范围（当前为 "single_fmea"）
  ├── status: str            ← 分析状态（"completed"）
  ├── impact_score: int      ← 影响评分（0-10）
  ├── impact_result: JSONB   ← ChangeImpactResult 完整结果
  ├── created_by: UUID (FK → users)
  └── created_at: datetime
```

### 5.5 Docker 部署

`docker-compose.yml` 中包含以下服务：

| 服务 | 说明 | 端口 |
|------|------|------|
| `neo4j` | Neo4j 5 Community | 7474 (HTTP), 7687 (Bolt) |
| `graph-worker` | GraphSyncWorker 进程 | 无外部端口 |

**Neo4j 配置：**

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `NEO4J_URI` | `bolt://localhost:7687` | Bolt 协议连接地址 |
| `NEO4J_USER` | `neo4j` | 用户名 |
| `NEO4J_PASSWORD` | `openqms2026` | 密码 |
| `NEO4J_DATABASE` | `neo4j` | 数据库名 |
| `GRAPH_REPOSITORY` | `jsonb` | 图存储后端选择 |

**手动全量重建命令：**

```bash
# Docker 环境中
docker compose exec backend python -m app.cli.graph_rebuild

# 带失败任务重置
docker compose exec backend python -m app.cli.graph_rebuild --retry-failed
```

---

## 6. 常见问题

### Q1：知识图谱页面显示"请先选择产品线"

知识图谱的统计和搜索功能都依赖产品线上下文。请在页面顶部的产品线选择器中选择一个产品线后再操作。

### Q2：非 admin/manager 角色能否访问知识图谱？

前端路由 `/knowledge-graph` 仅检查登录状态，不检查模块权限，因此所有登录用户都能进入页面。但 API 层有权限控制：

- `global-stats` 端点要求 ADMIN 权限
- `similar-nodes` 端点中，无 `knowledge_graph` VIEW 权限的用户请求会被自动降级为当前产品线范围搜索
- 跨产品线的节点名称会被脱敏处理

若需要完整访问权限，请让 admin 在角色权限管理中为对应角色添加 `knowledge_graph` 模块的 VIEW 权限。

### Q3：变更影响分析页面看不到任何记录

变更影响分析不会自动执行，需要在 FMEA 图谱编辑器中手动触发。请先进入某个 FMEA 文档的图谱 Tab，选中节点后发起分析。

### Q4：影响评分为 0 是否意味着无影响？

评分公式中 `failure_modes_affected × 2 + ap_upgraded_count × 3 + (max_hop_distance > 2 ? 2 : 0)` 可能为 0，但受影响节点列表可能不为空。评分为 0 仅表示没有受影响的 FailureMode、没有 AP 升级、且最大跳数 ≤ 2。仍需关注受影响节点列表中的具体内容。

### Q5：Neo4j 和 JSONB 后端有什么区别？

| 特性 | JSONB | Neo4j |
|------|-------|-------|
| 部署依赖 | 无额外依赖 | 需要 Neo4j 服务 |
| 跨文档查询 | 遍历所有 FMEA 的 JSONB | Cypher 图查询 |
| 实时性 | 读取 PostgreSQL 最新数据 | 依赖 Outbox 异步同步（延迟约 5 秒） |
| 性能 | 文档数量较多时较慢 | 图遍历性能更优 |
| 适用场景 | 开发、测试、小规模部署 | 生产环境、大规模数据 |

生产环境推荐使用 Neo4j 后端。当 `GRAPH_REPOSITORY=jsonb` 时，所有图查询直接从 PostgreSQL 的 JSONB 字段计算，无需 Neo4j 和 Worker。

### Q6：GraphSyncWorker 重试策略是什么？

Worker 使用指数退避重试：第 1 次失败后等待 10 秒，第 2 次 30 秒，第 3 次 90 秒，第 4 次 270 秒，第 5 次失败后标记为 `dead` 不再重试。可通过 `python -m app.cli.graph_rebuild --retry-failed` 重置 dead 任务。

### Q7：全局统计的数据是否安全？

`global-stats` 端点仅 admin 可访问，且返回数据经过白名单重建和名称脱敏处理。节点名称仅保留前 2 个字符，其余替换为 `***`，防止跨产品线敏感信息泄露。`similar-nodes` 端点对无全局权限的跨产品线节点也进行同样的脱敏处理。

### Q8：变更影响分析中 "属性变更" 和 "结构变更" 有什么区别？

- **属性变更 (`attribute`)：** 修改已有节点的字段值，如修改失效模式的 S/O/D 值。系统会根据变更的字段类型决定遍历方向——S/O/D 变更双向遍历，名称/描述变更不遍历。
- **结构变更 (`structural`)：** 增加、删除或移动图中的节点和连接。系统仅追踪下游影响链。

### Q9：FMEA 图谱中的节点如何关联到知识图谱？

FMEA 文档的 `graph_data` JSONB 字段中的所有节点（通过 Neo4j 投影或 JSONB 直接查询）构成了知识图谱的节点集。图的边（`edges`）定义了节点间的关联关系。知识图谱的搜索和统计功能就是基于这些节点和边进行跨文档聚合的。