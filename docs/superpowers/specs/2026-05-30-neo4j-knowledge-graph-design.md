# Neo4j 知识图谱基础设施设计

**日期**: 2026-05-30
**模块**: Phase 3 — AI + 知识图谱增强（基础设施子集）
**状态**: Draft

---

## 1. 目标

为 OpenQMS 建立 Neo4j 图数据库作为 FMEA 图数据的只读投影层，支持后续的知识图谱可视化、跨 FMEA 聚合查询和 AI 推荐功能。

**范围：** 最小基础设施 — 不含 AI/LLM/可视化。本次只做：

1. Neo4j Community Docker 容器部署
2. `graph_sync_outbox` 表 + Alembic 迁移
3. `GraphProjectionService` — JSONB → Neo4j 节点/边映射
4. `GraphSyncWorker` — 异步轮询 outbox 投影到 Neo4j（PG 行级锁 + 事件去重）
5. `FMEAGraphRepository` 抽象接口 + JSONB 实现 + Neo4j 实现
6. 全量重建 CLI 命令（含 retry-failed 兜底）
7. 基础图查询 API（影响链、原因链、跨 FMEA 统计）

**不包含：** 图谱可视化、LLM RAG、智能推荐、多人协同、FMEA 删除功能（当前 API 无 delete path，后续版本补充）。

---

## 2. 架构

```
PostgreSQL (主存储)
  fmea_documents.graph_data  ← source of truth
  graph_sync_outbox          ← 事件表
       │
       │ FMEA save/approve 同一事务 INSERT outbox
       ▼
Graph Sync Worker (asyncio 轮询)
  - 轮询 pending outbox (5s 间隔)
  - PG 行级锁领取任务: SELECT ... FOR UPDATE SKIP LOCKED
  - 按 aggregate_id 去重，跳过同 ID 旧事件
  - 解析 JSONB → MERGE Neo4j
  - 标记 completed / failed
       │
       ▼
Neo4j Community (只读投影)
  可随时从 PG 全量重建
  不承担审批、审计、回滚职责
```

### 核心原则

1. **PG 是唯一 source of truth** — Neo4j 数据可随时从 PG 全量重建
2. **Neo4j 是 read model** — 不直接写入，所有写入通过 worker
3. **业务代码零耦合** — FMEA service 只多一行 INSERT outbox
4. **异步解耦** — 5-10 秒同步延迟，失败可重试，不阻塞主业务
5. **查询走接口** — `FMEAGraphRepository` 抽象层，当前 JSONB + Neo4j 双实现

---

## 3. 数据库设计

### 3.1 graph_sync_outbox 表

```sql
CREATE TABLE graph_sync_outbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type  VARCHAR(50) NOT NULL DEFAULT 'fmea',
    aggregate_id    UUID NOT NULL,                    -- fmea_id
    event_type      VARCHAR(50) NOT NULL,             -- fmea.updated / fmea.approved
    payload         JSONB DEFAULT '{}',               -- 轻量 metadata: {version, product_line_code, fmea_type}
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/processing/completed/dead
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ
);

-- 只查 pending 任务（failed 重试也重置为 pending，通过 next_attempt_at 控制退避）
CREATE INDEX idx_outbox_pending ON graph_sync_outbox (next_attempt_at)
    WHERE status = 'pending';
```

**加锁机制：** Worker 使用 PG 行级锁 `SELECT ... FOR UPDATE SKIP LOCKED` 原子领取任务，无需 Redis。多 worker 实例可安全并发消费。

**事件去重：** Worker 取出一批任务后，按 `aggregate_id` 分组，每个 fmea_id 只处理最新一条事件。被跳过的旧事件直接标记 `completed`（payload 记录 `dedup_skipped: true`）。

**死信处理：** 超过 `max_attempts` 的任务标记为 `dead`。全量重建 CLI 提供 `--retry-failed` 参数重置 dead 任务为 pending。

### 3.2 Neo4j 节点模型

将 FMEA JSONB 的 `GraphNode` 和 `GraphEdge` 映射为 Neo4j 节点和关系：

**节点标签：**

| Neo4j Label | 来源 GraphNode.type | 关键属性 |
|---|---|---|
| `FMEDocument` | (虚拟节点) | fmea_id, document_no, title, fmea_type, product_line_code, status, version |
| `ProcessItem` / `System` | ProcessItem / System | fmea_id, name |
| `ProcessStep` / `Subsystem` | ProcessStep / Subsystem | fmea_id, name, process_number |
| `ProcessWorkElement` / `Component` | ProcessWorkElement / Component | fmea_id, name, classification |
| `Function` | *Function / ProcessItemFunction 等 | fmea_id, name, requirement, specification |
| `FailureMode` | FailureMode | fmea_id, name, severity, occurrence, detection, ap |
| `FailureEffect` | FailureEffect | fmea_id, name, severity_plant, severity_customer |
| `FailureCause` | FailureCause | fmea_id, name |
| `Control` | PreventionControl / DetectionControl | fmea_id, name, control_type (prevention|detection) |
| `RecommendedAction` | RecommendedAction | fmea_id, name, responsible, due_date, status, action_taken, revised_severity, revised_occurrence, revised_detection, revised_ap |

**每个节点统一属性：**
- `fmea_id: UUID` — 指向 PG 源文档
- `node_id: String` — 原 JSONB 中的 node.id
- `name: String`
- `product_line_code: String`

**关系类型（对应 GraphEdge.type）：**

```
-[:HAS_PROCESS_STEP]->
-[:HAS_WORK_ELEMENT]->
-[:FUNCTION_MAPPED_TO]->
-[:HAS_FAILURE_MODE]->
-[:EFFECT_OF]->
-[:CAUSE_OF]->
-[:PREVENTED_BY]->
-[:DETECTED_BY]->
-[:OPTIMIZED_BY]->
-[:HAS_FUNCTION]->
```

**Neo4j 约束与索引（首次启动时创建）：**

```cypher
-- 唯一性约束（保证幂等全删全建时数据一致）
CREATE CONSTRAINT fmea_doc_id IF NOT EXISTS FOR (d:FMEDocument) REQUIRE d.fmea_id IS UNIQUE;
CREATE CONSTRAINT graph_node_id IF NOT EXISTS FOR (n:GraphNode) REQUIRE (n.fmea_id, n.node_id) IS UNIQUE;

-- 性能索引
CREATE INDEX graph_node_fmea IF NOT EXISTS FOR (n:GraphNode) ON (n.fmea_id);
CREATE INDEX graph_node_type IF NOT EXISTS FOR (n:GraphNode) ON (n.type);
CREATE INDEX graph_node_product_line IF NOT EXISTS FOR (n:GraphNode) ON (n.product_line_code);
```

### 3.3 同步策略

| event_type | Neo4j 操作 |
|---|---|
| `fmea.updated` | 先 DELETE 该 fmea_id 全部节点/边，再 CREATE（幂等） |
| `fmea.approved` | 同 updated + FMEDocument.status = 'approved' |

**全量重建（CLI 操作，不走 outbox）：**
1. 清空 Neo4j 全部数据：`MATCH (n) DETACH DELETE n`
2. 重新创建约束和索引
3. 遍历 PG 所有 FMEA 文档，逐个调用 `sync_fmea_to_neo4j`
4. `--retry-failed` 模式：将 outbox 中 `dead` 状态的任务重置为 `pending` 并由 worker 处理

**幂等性：** 每次同步先全删再全建，不做增量 diff。FMEA 单文档节点数通常 50-200 个，全删全建性能可接受。

**租户隔离：** 所有跨 FMEA 查询（`find_similar_nodes`、`get_cross_fmea_stats`）强制要求 `product_line_code` 参数，Neo4j 查询通过 `product_line_code` 属性过滤，防止数据越权。

---

## 4. 后端代码架构

### 4.1 新增文件

```
backend/app/
├── models/
│   └── graph_sync_outbox.py         # SQLAlchemy ORM 模型
├── services/
│   ├── graph_projection_service.py  # JSONB → Neo4j 映射
│   └── graph_sync_worker.py         # 异步轮询 worker
├── graph/
│   ├── __init__.py
│   ├── repository.py                # FMEAGraphRepository 抽象接口
│   ├── jsonb_repository.py          # 当前实现：PG JSONB 查询
│   └── neo4j_repository.py          # Neo4j 实现：Cypher 查询
├── api/
│   └── graph.py                     # 图查询 API 路由
└── cli/
    └── graph_rebuild.py             # 全量重建 CLI
```

### 4.2 FMEAGraphRepository 接口

```python
class FMEAGraphRepository(ABC):
    @abstractmethod
    async def get_impact_chain(self, fmea_id: UUID, node_id: str) -> dict:
        """下游影响链：FailureMode → FailureEffect → Controls"""

    @abstractmethod
    async def get_cause_chain(self, fmea_id: UUID, node_id: str) -> dict:
        """上游原因链：FailureMode ← FailureCause"""

    @abstractmethod
    async def find_similar_nodes(
        self, node_type: str, name_keyword: str,
        product_line_code: str | None = None, limit: int = 20
    ) -> list[dict]:
        """跨 FMEA 搜索相似节点（知识库基础）"""

    @abstractmethod
    async def get_cross_fmea_stats(
        self, product_line_code: str | None = None
    ) -> dict:
        """跨 FMEA 聚合统计：节点类型分布、高频失效模式等"""
```

### 4.3 GraphProjectionService

```python
class GraphProjectionService:
    def __init__(self, neo4j_driver, db_session):
        self.neo4j = neo4j_driver
        self.db = db_session

    async def sync_fmea_to_neo4j(self, fmea_id: UUID) -> None:
        """1. PG 读 graph_data → 2. Neo4j 全删+全建"""

    async def delete_fmea_from_neo4j(self, fmea_id: UUID) -> None:
        """DETACH DELETE"""

    async def full_rebuild(self) -> dict:
        """遍历所有 FMEA，逐个同步。返回 {total, synced, failed}"""
```

### 4.4 GraphSyncWorker

```python
class GraphSyncWorker:
    POLL_INTERVAL = 5        # 秒
    BATCH_SIZE = 10          # 每次拉取任务数
    MAX_RETRY_DELAY = 3600   # 最大重试延迟 1 小时

    async def run(self) -> None:
        """主循环：轮询 → 加锁 → 去重 → 同步 → 标记"""

    async def _poll_and_lock(self) -> list:
        """
        原子领取任务（PG 行级锁）：
        BEGIN;
        SELECT * FROM graph_sync_outbox
          WHERE status = 'pending' AND next_attempt_at <= NOW()
          ORDER BY next_attempt_at
          LIMIT 10
          FOR UPDATE SKIP LOCKED;
        UPDATE ... SET status = 'processing' WHERE id IN (...);
        COMMIT;
        """

    async def _deduplicate(self, tasks: list) -> list:
        """
        按 aggregate_id 分组，每个 fmea_id 只保留最新一条事件。
        被跳过的旧事件标记 completed（payload: {dedup_skipped: true}）。
        """

    async def _process_task(self, task) -> None: ...
    async def _mark_completed(self, task) -> None: ...
    async def _mark_failed(self, task, error: str) -> None:
        """
        attempt_count += 1
        if attempt_count >= max_attempts: status = 'dead'
        else: status = 'pending', next_attempt_at = NOW() + backoff(attempt_count)
        """

    # 重试退避：exponential backoff
    # attempt 1 → 10s, attempt 2 → 30s, attempt 3 → 90s, attempt 4 → 270s, attempt 5 → dead
```

### 4.5 Graph Query API

```python
# backend/app/api/graph.py
router = APIRouter(prefix="/api/graph", tags=["graph"])

GET  /api/graph/fmea/{fmea_id}/impact/{node_id}   # 影响链
GET  /api/graph/fmea/{fmea_id}/cause/{node_id}    # 原因链
GET  /api/graph/similar                            # 跨 FMEA 相似节点搜索
GET  /api/graph/stats                              # 跨 FMEA 聚合统计
POST /api/graph/rebuild                            # 触发全量重建 (admin only)
```

### 4.6 FMEA Service 集成点（最小改动）

在 `fmea_service.py` 的 `update_fmea()` 和 `transition_fmea()` 中：

```python
# 在现有事务内，commit 前
outbox = GraphSyncOutbox(
    aggregate_type="fmea",
    aggregate_id=fmea.fmea_id,
    event_type="fmea.updated",  # 或 "fmea.approved"
    payload={"version": fmea.version, "product_line_code": fmea.product_line_code}
)
session.add(outbox)
```

约 5 行新增代码，不改变现有逻辑流程。

---

## 5. Docker 部署

### 5.1 docker-compose.yml 新增

```yaml
services:
  neo4j:
    image: neo4j:5-community
    ports:
      - "7474:7474"   # Neo4j Browser
      - "7687:7687"   # Bolt protocol
    environment:
      NEO4J_AUTH: neo4j/openqms2026
      NEO4J_server_memory_pagecache_size: 128M
      NEO4J_server_memory_heap_initial__size: 256M
      NEO4J_server_memory_heap_max__size: 512M
    volumes:
      - neo4j_data:/data
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p openqms2026 'RETURN 1'"]
      interval: 10s
      timeout: 5s
      retries: 5

  graph-worker:
    build: ./backend
    command: python -m app.services.graph_sync_worker
    depends_on:
      neo4j:
        condition: service_healthy
      db:
        condition: service_healthy
    environment:
      # Worker 需要 SECRET_KEY 避免 config 导入崩溃
      SECRET_KEY: ${SECRET_KEY:-dev-secret-key-change-in-production}
      DATABASE_URL: postgresql+asyncpg://openqms:openqms@db:5432/openqms
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: openqms2026

volumes:
  neo4j_data:
```

**注意：** 确保 `db` 服务在 docker-compose.yml 中配置了 `healthcheck`（如 `pg_isready`），否则 `graph-worker` 的 `depends_on: condition: service_healthy` 会报错。

### 5.2 配置

在 `backend/app/config.py` 新增：

```python
NEO4J_URI: str = "bolt://localhost:7687"
NEO4J_USER: str = "neo4j"
NEO4J_PASSWORD: str = "openqms2026"
NEO4J_DATABASE: str = "neo4j"  # Community Edition 只能用默认 db
```

---

## 6. Alembic 迁移

新增迁移文件 `add_graph_sync_outbox.py`，包含：

1. `CREATE TABLE graph_sync_outbox` 及其索引
2. 回滚 `DROP TABLE graph_sync_outbox`

---

## 7. 依赖

新增 Python 包（`requirements.txt`）：

```
neo4j>=5.0,<6.0       # Neo4j Python driver (async)
```

不引入其他新依赖。Worker 使用标准 `asyncio`。

---

## 8. 实现优先级

按以下顺序实现：

1. **Docker + 配置** — Neo4j 容器、config.py、neo4j driver 连接、约束初始化
2. **Outbox 模型 + 迁移** — SQLAlchemy 模型、Alembic 迁移
3. **FMEA Service 集成** — update/transition 中写 outbox（5 行代码）
4. **GraphProjectionService** — JSONB → Neo4j 映射逻辑
5. **GraphSyncWorker** — PG 行级锁轮询、事件去重、同步、退避重试
6. **FMEAGraphRepository** — 抽象接口 + JSONB 实现 + Neo4j 实现
7. **Graph Query API** — 路由 + 权限 + product_line_code 强制隔离
8. **全量重建 CLI** — `python -m app.cli.graph_rebuild` + `--retry-failed` 兜底
9. **测试** — 投影映射正确性、worker 去重/重试逻辑、全量重建

---

## 9. 验收标准

- [ ] `docker compose up` 启动 Neo4j + graph-worker
- [ ] 创建/编辑 FMEA 后，outbox 自动写入
- [ ] worker 在 10 秒内将 FMEA 图数据同步到 Neo4j
- [ ] Neo4j Browser 可查询到正确的节点和关系
- [ ] Neo4j 唯一性约束生效，全量重建不产生重复节点
- [ ] 图查询 API 返回正确的影响链和原因链
- [ ] 跨 FMEA 查询强制 product_line_code 过滤
- [ ] 全量重建命令先清空 Neo4j 再从 PG 重建所有数据
- [ ] `--retry-failed` 可重置 dead 状态任务
- [ ] 同一 FMEA 5 秒内多次保存，worker 去重只同步一次
- [ ] worker 失败自动退避重试，超过 5 次标记为 dead
- [ ] Neo4j 完全清空后，全量重建可恢复所有数据
