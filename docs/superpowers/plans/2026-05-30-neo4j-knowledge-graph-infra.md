# Neo4j 知识图谱基础设施 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 Neo4j 图数据库作为 FMEA 图数据的只读投影层，支持后续知识图谱可视化、跨 FMEA 聚合查询和 AI 推荐功能。

**Architecture:** PostgreSQL 保持 source of truth，FMEA 保存时写 outbox 表，独立 worker 异步轮询 outbox 投影到 Neo4j。图查询通过 `FMEAGraphRepository` 抽象接口，当前 JSONB + Neo4j 双实现。

**Tech Stack:** Neo4j 5 Community (Docker) + neo4j Python driver 5.x (async) + SQLAlchemy 2.0 (outbox model) + asyncio (worker)

---

## File Structure

**New files:**
- `backend/app/models/graph_sync_outbox.py` — Outbox ORM model
- `backend/app/graph/__init__.py` — Package init
- `backend/app/graph/repository.py` — FMEAGraphRepository 抽象接口
- `backend/app/graph/jsonb_repository.py` — JSONB 实现
- `backend/app/graph/neo4j_repository.py` — Neo4j 实现
- `backend/app/graph/neo4j_driver.py` — Neo4j driver 单例 + 约束初始化
- `backend/app/services/graph_projection_service.py` — JSONB → Neo4j 映射
- `backend/app/services/graph_sync_worker.py` — 异步轮询 worker
- `backend/app/api/graph.py` — 图查询 API 路由
- `backend/app/cli/__init__.py` — Package init
- `backend/app/cli/graph_rebuild.py` — 全量重建 CLI
- `backend/alembic/versions/027_add_graph_sync_outbox.py` — Outbox 迁移
- `backend/tests/test_graph_projection.py` — 投影映射测试
- `backend/tests/test_graph_sync_worker.py` — Worker 逻辑测试

**Modified files:**
- `backend/requirements.txt` — 新增 neo4j driver
- `backend/app/config.py` — 新增 Neo4j 配置项
- `backend/app/models/__init__.py` — 注册 Outbox model
- `backend/app/services/fmea_service.py:133-224` — 三个函数加 outbox 写入
- `backend/app/main.py:40-96` — 注册 graph router
- `docker-compose.yml` — 新增 neo4j + graph-worker 服务

---

### Task 1: Neo4j 配置与依赖

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`

- [ ] **Step 1: 添加 neo4j driver 到 requirements.txt**

在 `backend/requirements.txt` 末尾追加：

```
neo4j>=5.0,<6.0
```

- [ ] **Step 2: 添加 Neo4j 配置到 config.py**

在 `backend/app/config.py` 的 `Settings` 类中，`ALGORITHM` 字段之后添加：

```python
    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "openqms2026"
    NEO4J_DATABASE: str = "neo4j"
```

- [ ] **Step 3: 安装依赖**

Run: `cd backend && pip install 'neo4j>=5.0,<6.0'`

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt backend/app/config.py
git commit -m "feat: add neo4j driver dependency and config settings"
```

---

### Task 2: Outbox 模型与 Alembic 迁移

**Files:**
- Create: `backend/app/models/graph_sync_outbox.py`
- Create: `backend/alembic/versions/027_add_graph_sync_outbox.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 创建 Outbox ORM 模型**

创建 `backend/app/models/graph_sync_outbox.py`：

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GraphSyncOutbox(Base):
    __tablename__ = "graph_sync_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False, default="fmea")
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending / processing / completed / dead
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: 注册到 models/__init__.py**

在 `backend/app/models/__init__.py` 末尾的 import 区追加：

```python
from app.models.graph_sync_outbox import GraphSyncOutbox
```

在 `__all__` 列表末尾追加 `"GraphSyncOutbox"`。

- [ ] **Step 3: 创建 Alembic 迁移**

创建 `backend/alembic/versions/027_add_graph_sync_outbox.py`：

```python
"""add graph_sync_outbox table for Neo4j projection sync

Revision ID: 027
Revises: 20260530
Create Date: 2026-05-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = '027'
down_revision: Union[str, None] = '20260530'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'graph_sync_outbox',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('aggregate_type', sa.String(50), nullable=False, server_default='fmea'),
        sa.Column('aggregate_id', UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('payload', JSONB, nullable=False, server_default='{}'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'idx_outbox_pending', 'graph_sync_outbox', ['next_attempt_at'],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index('idx_outbox_pending')
    op.drop_table('graph_sync_outbox')
```

- [ ] **Step 4: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: `Running upgrade 20260530 -> 027, add graph_sync_outbox table...`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/graph_sync_outbox.py backend/app/models/__init__.py backend/alembic/versions/027_add_graph_sync_outbox.py
git commit -m "feat: add graph_sync_outbox model and Alembic migration"
```

---

### Task 3: FMEA Service 集成 Outbox 写入

**Files:**
- Modify: `backend/app/services/fmea_service.py:1-229`

- [ ] **Step 1: 在 fmea_service.py 顶部添加 import**

在 `backend/app/services/fmea_service.py` 现有 import 末尾追加：

```python
from app.models.graph_sync_outbox import GraphSyncOutbox
```

- [ ] **Step 2: 在 create_fmea() 中添加 outbox 写入**

在 `backend/app/services/fmea_service.py` 的 `create_fmea()` 函数中，`db.add(audit_log)` 之后、`try: await db.commit()` 之前（约第 131-133 行），插入：

```python
    # Outbox: enqueue Neo4j projection sync
    db.add(GraphSyncOutbox(
        aggregate_type="fmea",
        aggregate_id=fmea_id,
        event_type="fmea.created",
        payload={"version": 1, "product_line_code": product_line_code, "fmea_type": fmea_type},
    ))
```

- [ ] **Step 3: 在 update_fmea() 中添加 outbox 写入**

在 `update_fmea()` 函数中，`db.add(audit_log)` 之后、`await db.commit()` 之前（约第 172-174 行），插入：

```python
    # Outbox: enqueue Neo4j projection sync
    db.add(GraphSyncOutbox(
        aggregate_type="fmea",
        aggregate_id=fmea.fmea_id,
        event_type="fmea.updated",
        payload={"version": fmea.version, "product_line_code": fmea.product_line_code},
    ))
```

注意：这段代码要放在 `if changed_fields:` 块内部（与 audit_log 同级），这样无变更时不写 outbox。

- [ ] **Step 4: 在 transition_fmea() 中添加 outbox 写入**

在 `transition_fmea()` 函数中，`db.add(audit_log)` 之后、`await db.commit()` 之前（约第 222-224 行），插入：

```python
    # Outbox: enqueue Neo4j projection sync
    db.add(GraphSyncOutbox(
        aggregate_type="fmea",
        aggregate_id=fmea.fmea_id,
        event_type="fmea.approved" if target == FMEAState.APPROVED else "fmea.updated",
        payload={"version": fmea.version, "product_line_code": fmea.product_line_code, "status": target_status},
    ))
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/fmea_service.py
git commit -m "feat: write graph_sync_outbox in FMEA create/update/transition"
```

---

### Task 4: Neo4j Driver 单例与约束初始化

**Files:**
- Create: `backend/app/graph/__init__.py`
- Create: `backend/app/graph/neo4j_driver.py`

- [ ] **Step 1: 创建 graph 包**

创建 `backend/app/graph/__init__.py`：

```python
```

（空文件，仅做包标记）

- [ ] **Step 2: 创建 Neo4j driver 模块**

创建 `backend/app/graph/neo4j_driver.py`：

```python
from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from app.config import settings

_driver: AsyncDriver | None = None


async def get_neo4j_driver() -> AsyncDriver:
    """获取或创建 Neo4j async driver 单例。"""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


async def close_neo4j_driver() -> None:
    """关闭 Neo4j driver 连接池。"""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def ensure_constraints() -> None:
    """创建 Neo4j 唯一性约束和索引（幂等）。"""
    driver = await get_neo4j_driver()
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        await session.run(
            "CREATE CONSTRAINT fmea_doc_id IF NOT EXISTS "
            "FOR (d:FMEDocument) REQUIRE d.fmea_id IS UNIQUE"
        )
        await session.run(
            "CREATE CONSTRAINT graph_node_id IF NOT EXISTS "
            "FOR (n:GraphNode) REQUIRE (n.fmea_id, n.node_id) IS UNIQUE"
        )
        await session.run(
            "CREATE INDEX graph_node_fmea IF NOT EXISTS "
            "FOR (n:GraphNode) ON (n.fmea_id)"
        )
        await session.run(
            "CREATE INDEX graph_node_type IF NOT EXISTS "
            "FOR (n:GraphNode) ON (n.type)"
        )
        await session.run(
            "CREATE INDEX graph_node_product_line IF NOT EXISTS "
            "FOR (n:GraphNode) ON (n.product_line_code)"
        )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/graph/__init__.py backend/app/graph/neo4j_driver.py
git commit -m "feat: add Neo4j async driver singleton with constraint initialization"
```

---

### Task 5: GraphProjectionService — JSONB → Neo4j 映射

**Files:**
- Create: `backend/app/services/graph_projection_service.py`

- [ ] **Step 1: 写测试**

创建 `backend/tests/test_graph_projection.py`：

```python
"""测试 GraphProjectionService 的 Cypher 构建逻辑（不连 Neo4j，只测映射）。"""
import pytest
from app.services.graph_projection_service import build_cypher_sync


SAMPLE_GRAPH = {
    "nodes": [
        {"id": "sys_1", "type": "System", "name": "BMS", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "fm_1", "type": "FailureMode", "name": "电压漂移", "severity": 8, "occurrence": 5, "detection": 4, "ap": "H"},
        {"id": "fe_1", "type": "FailureEffect", "name": "热失控", "severity": 10},
        {"id": "fc_1", "type": "FailureCause", "name": "温漂", "severity": 0, "occurrence": 5, "detection": 0},
        {"id": "pc_1", "type": "PreventionControl", "name": "AEC-Q100 认证"},
        {"id": "dc_1", "type": "DetectionControl", "name": "上电自检", "detection": 4},
    ],
    "edges": [
        {"source": "sys_1", "target": "fm_1", "type": "HAS_FAILURE_MODE"},
        {"source": "fm_1", "target": "fe_1", "type": "EFFECT_OF"},
        {"source": "fc_1", "target": "fm_1", "type": "CAUSE_OF"},
        {"source": "fc_1", "target": "pc_1", "type": "PREVENTED_BY"},
        {"source": "fc_1", "target": "dc_1", "type": "DETECTED_BY"},
    ],
}


def test_build_cypher_sync_returns_delete_doc_nodes_edges():
    """build_cypher_sync 应返回：1 DELETE + 1 FMEDoc + N nodes + M edges。"""
    statements = build_cypher_sync(
        fmea_id="00000000-0000-0000-0000-000000000001",
        document_no="PFMEA-2026-001",
        title="测试",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        status="draft",
        version=1,
        graph_data=SAMPLE_GRAPH,
    )
    # 1 DELETE + 1 FMEDoc + 6 nodes + 5 edges = 13
    assert len(statements) == 13
    # 第一条是 DELETE
    assert "DETACH DELETE" in statements[0][0]
    # 第二条是 FMEDocument
    assert "FMEDocument" in statements[1][0]
    # 后续是节点和边创建
    node_stmts = [s for s in statements if "CREATE (n:GraphNode" in s[0]]
    edge_stmts = [s for s in statements if "MATCH (s:GraphNode" in s[0]]
    assert len(node_stmts) == 6
    assert len(edge_stmts) == 5


def test_build_cypher_sync_maps_node_types_to_labels():
    """每个节点应有 GraphNode + 具体类型双标签。"""
    statements = build_cypher_sync(
        fmea_id="00000000-0000-0000-0000-000000000001",
        document_no="PFMEA-2026-001",
        title="测试",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        status="draft",
        version=1,
        graph_data=SAMPLE_GRAPH,
    )
    node_stmts = [s[0] for s in statements if "GraphNode" in s[0] and "MATCH" not in s[0]]
    cypher_text = " ".join(node_stmts)
    assert ":GraphNode:FailureMode" in cypher_text
    assert ":GraphNode:System" in cypher_text
    # PreventionControl/DetectionControl → Control
    assert ":GraphNode:Control" in cypher_text


def test_build_cypher_sync_empty_graph():
    """空 graph_data 也能正常生成（只做 DELETE）。"""
    statements = build_cypher_sync(
        fmea_id="00000000-0000-0000-0000-000000000001",
        document_no="PFMEA-2026-001",
        title="空文档",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        status="draft",
        version=1,
        graph_data={"nodes": [], "edges": []},
    )
    assert len(statements) == 1  # 只有 DELETE
    assert "DETACH DELETE" in statements[0][0]


def test_build_cypher_sync_skips_unknown_types():
    """未知节点类型和边类型被安全跳过，不进入 Cypher。"""
    graph = {
        "nodes": [
            {"id": "x1", "type": "EvilNode", "name": "bad", "severity": 0, "occurrence": 0, "detection": 0},
            {"id": "x2", "type": "FailureMode", "name": "ok", "severity": 0, "occurrence": 0, "detection": 0},
        ],
        "edges": [
            {"source": "x2", "target": "x2", "type": "EVIL_RELATIONSHIP"},
            {"source": "x2", "target": "x2", "type": "CAUSE_OF"},
        ],
    }
    statements = build_cypher_sync(
        fmea_id="00000000-0000-0000-0000-000000000001",
        document_no="T-001", title="t", fmea_type="PFMEA",
        product_line_code="DC-DC-100", status="draft", version=1,
        graph_data=graph,
    )
    cypher_text = " ".join(s[0] for s in statements)
    assert "EvilNode" not in cypher_text
    assert "EVIL_RELATIONSHIP" not in cypher_text
    assert "FailureMode" in cypher_text
    assert "CAUSE_OF" in cypher_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=openqms-local-dev-2026-jwt-signing-key python -m pytest tests/test_graph_projection.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.graph_projection_service'`

- [ ] **Step 3: 实现 GraphProjectionService**

创建 `backend/app/services/graph_projection_service.py`：

```python
"""GraphProjectionService: 将 FMEA JSONB graph_data 映射为 Neo4j Cypher 语句。

核心逻辑是 build_cypher_sync()：给定一个 FMEA 文档的完整数据，生成一组
(Cypher, params) 元组，worker 逐条执行实现幂等投影。
"""
import uuid
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── 白名单：防止用户输入直接进入 Cypher ──

ALLOWED_NODE_TYPES: set[str] = {
    "ProcessItem", "System", "ProcessStep", "Subsystem",
    "ProcessWorkElement", "Component",
    "ProcessItemFunction", "ProcessStepFunction", "ProcessWorkElementFunction",
    "Function",
    "FailureMode", "FailureEffect", "FailureCause",
    "PreventionControl", "DetectionControl",
    "RecommendedAction",
}

NODE_TYPE_LABEL_MAP: dict[str, str] = {
    "PreventionControl": "Control",
    "DetectionControl": "Control",
    # 其他类型保持原名
}

ALLOWED_EDGE_TYPES: set[str] = {
    "HAS_PROCESS_STEP", "HAS_WORK_ELEMENT", "HAS_FUNCTION",
    "FUNCTION_MAPPED_TO", "HAS_FAILURE_MODE",
    "EFFECT_OF", "CAUSE_OF",
    "PREVENTED_BY", "DETECTED_BY", "OPTIMIZED_BY",
}


def _node_properties(node: dict) -> dict[str, Any]:
    """从 GraphNode JSONB 提取 Neo4j 节点属性。"""
    props: dict[str, Any] = {
        "node_id": node["id"],
        "name": node.get("name", ""),
        "type": node["type"],
    }
    for key in ("process_number", "classification", "requirement", "specification",
                "severity", "occurrence", "detection", "ap",
                "revised_severity", "revised_occurrence", "revised_detection", "revised_ap",
                "severity_plant", "severity_customer", "severity_user",
                "responsible", "due_date", "status", "action_taken", "completion_date"):
        val = node.get(key)
        if val is not None and val != 0 and val != "":
            props[key] = val

    if node["type"] in ("PreventionControl", "DetectionControl"):
        props["control_type"] = "prevention" if node["type"] == "PreventionControl" else "detection"

    return props


def build_cypher_sync(
    fmea_id: str,
    document_no: str,
    title: str,
    fmea_type: str,
    product_line_code: str,
    status: str,
    version: int,
    graph_data: dict,
) -> list[tuple[str, dict]]:
    """为单个 FMEA 文档生成完整的 Neo4j 投影 Cypher 语句序列。

    策略：逐条生成简单、参数化的 Cypher（不用动态字符串拼接标签/关系类型）。
    每个 (cypher, params) 对应一条独立语句，在同一个 Neo4j transaction 中顺序执行。

    Returns: [(cypher, params), ...] — 按顺序在同一个 Neo4j write transaction 中执行即为幂等同步。
    """
    statements: list[tuple[str, dict]] = []

    # Step 1: DELETE existing projection for this fmea_id
    statements.append((
        "MATCH (n) WHERE n.fmea_id = $fmea_id DETACH DELETE n",
        {"fmea_id": fmea_id},
    ))

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    if not nodes:
        return statements

    # Step 2: CREATE FMEDocument node
    statements.append((
        "CREATE (d:FMEDocument {fmea_id: $fmea_id, document_no: $document_no, "
        "title: $title, fmea_type: $fmea_type, product_line_code: $product_line_code, "
        "status: $status, version: $version})",
        {
            "fmea_id": fmea_id,
            "document_no": document_no,
            "title": title,
            "fmea_type": fmea_type,
            "product_line_code": product_line_code,
            "status": status,
            "version": version,
        },
    ))

    # Step 3: CREATE each GraphNode (逐条，标签在白名单内直接拼接)
    for node in nodes:
        raw_type = node.get("type", "")
        if raw_type not in ALLOWED_NODE_TYPES:
            logger.warning(f"Skipping unknown node type: {raw_type}")
            continue

        label = NODE_TYPE_LABEL_MAP.get(raw_type, raw_type)
        props = _node_properties(node)
        props["fmea_id"] = fmea_id
        props["product_line_code"] = product_line_code

        statements.append((
            f"CREATE (n:GraphNode:{label}) SET n += $props",
            {"props": props},
        ))

    # Step 4: CREATE edges — MATCH by (fmea_id, node_id) for exact binding
    node_ids = {n["id"] for n in nodes if n.get("type") in ALLOWED_NODE_TYPES}
    for edge in edges:
        edge_type = edge.get("type", "")
        source = edge.get("source", "")
        target = edge.get("target", "")

        if edge_type not in ALLOWED_EDGE_TYPES:
            logger.warning(f"Skipping unknown edge type: {edge_type}")
            continue
        if source not in node_ids or target not in node_ids:
            continue

        statements.append((
            f"MATCH (s:GraphNode {{fmea_id: $fmea_id, node_id: $source}}), "
            f"(t:GraphNode {{fmea_id: $fmea_id, node_id: $target}}) "
            f"CREATE (s)-[:{edge_type}]->(t)",
            {"fmea_id": fmea_id, "source": source, "target": target},
        ))

    return statements


class GraphProjectionService:
    """JSONB → Neo4j 投影服务。"""

    def __init__(self, neo4j_driver, db_session_factory):
        self._driver = neo4j_driver
        self._session_factory = db_session_factory

    async def sync_fmea_to_neo4j(self, fmea_id: uuid.UUID) -> None:
        """从 PG 读取 FMEA → 生成 Cypher → 执行到 Neo4j。"""
        from app.models.fmea import FMEADocument
        from sqlalchemy import select

        async with self._session_factory() as db:
            result = await db.execute(
                select(FMEADocument).where(FMEADocument.fmea_id == fmea_id)
            )
            fmea = result.scalar_one_or_none()
            if fmea is None:
                return

        statements = build_cypher_sync(
            fmea_id=str(fmea.fmea_id),
            document_no=fmea.document_no,
            title=fmea.title,
            fmea_type=fmea.fmea_type,
            product_line_code=fmea.product_line_code,
            status=fmea.status,
            version=fmea.version,
            graph_data=fmea.graph_data or {"nodes": [], "edges": []},
        )

        async def _tx(tx):
            for cypher, params in statements:
                result = await tx.run(cypher, params)
                await result.consume()  # 确保每条语句执行完成并检查错误

        async with self._driver.session(database="neo4j") as session:
            await session.execute_write(_tx)

    async def full_rebuild(self) -> dict:
        """全量重建：清空 Neo4j + 遍历所有 FMEA 逐个同步。"""
        from app.models.fmea import FMEADocument
        from sqlalchemy import select, func

        total = 0
        synced = 0
        failed = 0

        # 清空 Neo4j
        async with self._driver.session(database="neo4j") as session:
            await session.run("MATCH (n) DETACH DELETE n")

        # 重新创建约束
        from app.graph.neo4j_driver import ensure_constraints
        await ensure_constraints()

        # 遍历所有 FMEA
        async with self._session_factory() as db:
            count_result = await db.execute(select(func.count(FMEADocument.fmea_id)))
            total = count_result.scalar() or 0

            result = await db.execute(select(FMEADocument))
            fmeas = result.scalars().all()

        for fmea in fmeas:
            try:
                await self.sync_fmea_to_neo4j(fmea.fmea_id)
                synced += 1
            except Exception:
                failed += 1

        return {"total": total, "synced": synced, "failed": failed}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=openqms-local-dev-2026-jwt-signing-key python -m pytest tests/test_graph_projection.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/graph_projection_service.py backend/tests/test_graph_projection.py
git commit -m "feat: add GraphProjectionService with JSONB → Neo4j Cypher mapping"
```

---

### Task 6: GraphSyncWorker — 异步轮询

**Files:**
- Create: `backend/app/services/graph_sync_worker.py`

- [ ] **Step 1: 写测试**

创建 `backend/tests/test_graph_sync_worker.py`：

```python
"""测试 GraphSyncWorker 的去重和退避逻辑（不连 Neo4j/PG，纯逻辑测试）。"""
import pytest
from app.services.graph_sync_worker import deduplicate_tasks, backoff_delay


def _make_task(aggregate_id: str, event_type: str, created_offset: float = 0):
    """构造简化 task 对象用于去重测试。"""
    from datetime import datetime, timezone, timedelta
    return {
        "id": f"task-{aggregate_id}-{event_type}",
        "aggregate_id": aggregate_id,
        "event_type": event_type,
        "created_at": datetime.now(timezone.utc) - timedelta(seconds=created_offset),
    }


class TestDeduplicate:
    def test_same_aggregate_keeps_newest(self):
        """同一 fmea_id 多条事件只保留最新一条。"""
        tasks = [
            _make_task("fmea-1", "fmea.updated", created_offset=30),
            _make_task("fmea-1", "fmea.updated", created_offset=10),
            _make_task("fmea-1", "fmea.approved", created_offset=0),
        ]
        result = deduplicate_tasks(tasks)
        assert len(result["process"]) == 1
        assert result["process"][0]["event_type"] == "fmea.approved"
        assert len(result["skip"]) == 2

    def test_different_aggregates_all_kept(self):
        """不同 fmea_id 不互相去重。"""
        tasks = [
            _make_task("fmea-1", "fmea.updated"),
            _make_task("fmea-2", "fmea.created"),
        ]
        result = deduplicate_tasks(tasks)
        assert len(result["process"]) == 2
        assert len(result["skip"]) == 0

    def test_empty_input(self):
        result = deduplicate_tasks([])
        assert result["process"] == []
        assert result["skip"] == []


class TestBackoff:
    def test_first_retry_10s(self):
        assert backoff_delay(1) == 10

    def test_second_retry_30s(self):
        assert backoff_delay(2) == 30

    def test_third_retry_90s(self):
        assert backoff_delay(3) == 90

    def test_fourth_retry_270s(self):
        assert backoff_delay(4) == 270

    def test_fifth_is_dead(self):
        """第 5 次不应返回退避，应直接标记 dead。"""
        assert backoff_delay(5) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=openqms-local-dev-2026-jwt-signing-key python -m pytest tests/test_graph_sync_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.graph_sync_worker'`

- [ ] **Step 3: 实现 GraphSyncWorker**

创建 `backend/app/services/graph_sync_worker.py`：

```python
"""GraphSyncWorker: 异步轮询 outbox 表，投影 FMEA 图数据到 Neo4j。

运行方式:
    python -m app.services.graph_sync_worker
    或 docker compose up graph-worker
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.graph_sync_outbox import GraphSyncOutbox
from app.graph.neo4j_driver import get_neo4j_driver, ensure_constraints
from app.services.graph_projection_service import GraphProjectionService

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5
BATCH_SIZE = 10


def backoff_delay(attempt: int) -> int | None:
    """Exponential backoff: 10s → 30s → 90s → 270s。第 5 次返回 None (dead)。"""
    if attempt >= 5:
        return None
    delays = {1: 10, 2: 30, 3: 90, 4: 270}
    return delays.get(attempt, 270)


def deduplicate_tasks(tasks: list[dict]) -> dict[str, list[dict]]:
    """按 aggregate_id 分组，每个 fmea_id 只保留 created_at 最新的一条事件。

    Returns: {"process": [...], "skip": [...]}
    """
    if not tasks:
        return {"process": [], "skip": []}

    latest: dict[str, dict] = {}
    for task in tasks:
        aid = task["aggregate_id"]
        if aid not in latest or task["created_at"] > latest[aid]["created_at"]:
            if aid in latest:
                # 之前的那条要 skip
                pass
            latest[aid] = task

    process = list(latest.values())
    process_ids = {t["id"] for t in process}
    skip = [t for t in tasks if t["id"] not in process_ids]

    return {"process": process, "skip": skip}


async def _poll_and_lock(db: AsyncSession) -> list[GraphSyncOutbox]:
    """使用 PG FOR UPDATE SKIP LOCKED 原子领取一批 pending 任务。

    同时回收超过 10 分钟仍在 processing 的任务（Worker 崩溃残留）。
    """
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(minutes=10)

    # 先回收 stale processing 任务
    await db.execute(
        update(GraphSyncOutbox)
        .where(
            and_(
                GraphSyncOutbox.status == "processing",
                GraphSyncOutbox.locked_at < stale_cutoff,
            )
        )
        .values(status="pending", locked_at=None)
    )
    await db.flush()

    # 领取 pending 任务
    result = await db.execute(
        select(GraphSyncOutbox)
        .where(
            and_(
                GraphSyncOutbox.status == "pending",
                GraphSyncOutbox.next_attempt_at <= now,
            )
        )
        .order_by(GraphSyncOutbox.next_attempt_at)
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)
    )
    tasks = list(result.scalars().all())

    if tasks:
        task_ids = [t.id for t in tasks]
        await db.execute(
            update(GraphSyncOutbox)
            .where(GraphSyncOutbox.id.in_(task_ids))
            .values(status="processing", locked_at=now)
        )
        await db.commit()

    return tasks


async def _cleanup_stale_processing() -> int:
    """将 status='processing' 且超过 10 分钟的任务重置为 pending。

    Worker 启动时调用，清理上次崩溃残留。
    """
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with async_session() as db:
        result = await db.execute(
            update(GraphSyncOutbox)
            .where(
                and_(
                    GraphSyncOutbox.status == "processing",
                    GraphSyncOutbox.locked_at < stale_cutoff,
                )
            )
            .values(status="pending", locked_at=None)
            .returning(GraphSyncOutbox.id)
        )
        reset_ids = list(result.scalars().all())
        await db.commit()
    return len(reset_ids)


async def _mark_completed(db: AsyncSession, task_id: uuid.UUID) -> None:
    await db.execute(
        update(GraphSyncOutbox)
        .where(GraphSyncOutbox.id == task_id)
        .values(status="completed", processed_at=datetime.now(timezone.utc))
    )
    await db.commit()


async def _mark_failed(db: AsyncSession, task: GraphSyncOutbox, error: str) -> None:
    new_attempt = task.attempt_count + 1
    delay = backoff_delay(new_attempt)

    if delay is None:
        # Dead letter
        await db.execute(
            update(GraphSyncOutbox)
            .where(GraphSyncOutbox.id == task.id)
            .values(
                status="dead",
                attempt_count=new_attempt,
                last_error=error,
                processed_at=datetime.now(timezone.utc),
            )
        )
    else:
        await db.execute(
            update(GraphSyncOutbox)
            .where(GraphSyncOutbox.id == task.id)
            .values(
                status="pending",
                attempt_count=new_attempt,
                last_error=error,
                next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=delay),
            )
        )
    await db.commit()


async def run_worker() -> None:
    """Worker 主入口：无限循环轮询 outbox。"""
    logging.basicConfig(level=logging.INFO)
    logger.info("GraphSyncWorker starting...")

    driver = await get_neo4j_driver()
    await ensure_constraints()
    projection = GraphProjectionService(driver, async_session)

    logger.info("Neo4j connected, constraints ensured. Polling outbox...")

    # 启动时清理上次崩溃残留的 processing 任务
    stale_count = await _cleanup_stale_processing()
    if stale_count:
        logger.info(f"Cleaned up {stale_count} stale processing tasks")

    while True:
        try:
            async with async_session() as db:
                tasks = await _poll_and_lock(db)

            if not tasks:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            # Deduplicate
            task_dicts = [
                {
                    "id": str(t.id),
                    "aggregate_id": str(t.aggregate_id),
                    "event_type": t.event_type,
                    "created_at": t.created_at,
                }
                for t in tasks
            ]
            deduped = deduplicate_tasks(task_dicts)

            # Mark skipped tasks as completed
            process_ids = {t["id"] for t in deduped["process"]}
            for task in tasks:
                if str(task.id) not in process_ids:
                    async with async_session() as db:
                        await _mark_completed(db, task.id)

            # Process deduplicated tasks
            for task in tasks:
                if str(task.id) not in process_ids:
                    continue
                try:
                    await projection.sync_fmea_to_neo4j(task.aggregate_id)
                    async with async_session() as db:
                        await _mark_completed(db, task.id)
                    logger.info(f"Synced FMEA {task.aggregate_id} to Neo4j")
                except Exception as e:
                    logger.error(f"Failed to sync FMEA {task.aggregate_id}: {e}")
                    async with async_session() as db:
                        await _mark_failed(db, task, str(e))

        except Exception as e:
            logger.error(f"Worker poll error: {e}")
            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_worker())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=openqms-local-dev-2026-jwt-signing-key python -m pytest tests/test_graph_sync_worker.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/graph_sync_worker.py backend/tests/test_graph_sync_worker.py
git commit -m "feat: add GraphSyncWorker with PG locking, dedup, exponential backoff"
```

---

### Task 7: FMEAGraphRepository — 抽象接口 + 双实现

**Files:**
- Create: `backend/app/graph/repository.py`
- Create: `backend/app/graph/jsonb_repository.py`
- Create: `backend/app/graph/neo4j_repository.py`

- [ ] **Step 1: 创建抽象接口**

创建 `backend/app/graph/repository.py`：

```python
"""FMEAGraphRepository: 图查询抽象接口。

当前提供两个实现：
- JSONBRepository: 从 PG JSONB 读取（无需 Neo4j）
- Neo4jRepository: 从 Neo4j 读取（需要 worker 同步完成）
"""
import uuid
from abc import ABC, abstractmethod
from typing import Any


class FMEAGraphRepository(ABC):
    @abstractmethod
    async def get_impact_chain(self, fmea_id: uuid.UUID, node_id: str) -> dict:
        """下游影响链：指定节点 → FailureEffect → Controls"""

    @abstractmethod
    async def get_cause_chain(self, fmea_id: uuid.UUID, node_id: str) -> dict:
        """上游原因链：指定节点 ← FailureCause"""

    @abstractmethod
    async def find_similar_nodes(
        self, node_type: str, name_keyword: str, product_line_code: str, limit: int = 20
    ) -> list[dict]:
        """跨 FMEA 搜索相似节点。product_line_code 必填。"""

    @abstractmethod
    async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
        """跨 FMEA 聚合统计。product_line_code 必填。"""
```

- [ ] **Step 2: 创建 JSONB 实现**

创建 `backend/app/graph/jsonb_repository.py`：

```python
"""JSONB 实现：从 PostgreSQL graph_data JSONB 字段执行图查询。

不需要 Neo4j，适合开发/测试环境或 Neo4j 不可用时的 fallback。
"""
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fmea import FMEADocument
from app.graph.repository import FMEAGraphRepository


class JSONBRepository(FMEAGraphRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_impact_chain(self, fmea_id: uuid.UUID, node_id: str) -> dict:
        fmea = await self._get_fmea(fmea_id)
        if not fmea or not fmea.graph_data:
            return {"nodes": [], "edges": []}
        return self._trace_chain(fmea.graph_data, node_id, direction="downstream")

    async def get_cause_chain(self, fmea_id: uuid.UUID, node_id: str) -> dict:
        fmea = await self._get_fmea(fmea_id)
        if not fmea or not fmea.graph_data:
            return {"nodes": [], "edges": []}
        return self._trace_chain(fmea.graph_data, node_id, direction="upstream")

    async def find_similar_nodes(
        self, node_type: str, name_keyword: str, product_line_code: str, limit: int = 20
    ) -> list[dict]:
        query = select(FMEADocument).where(FMEADocument.product_line_code == product_line_code)
        result = await self._db.execute(query)
        fmeas = result.scalars().all()

        matches = []
        for fmea in fmeas:
            if not fmea.graph_data:
                continue
            for node in fmea.graph_data.get("nodes", []):
                if node.get("type") == node_type and name_keyword.lower() in node.get("name", "").lower():
                    matches.append({
                        "node_id": node["id"],
                        "name": node["name"],
                        "type": node["type"],
                        "fmea_id": str(fmea.fmea_id),
                        "document_no": fmea.document_no,
                    })
                    if len(matches) >= limit:
                        return matches
        return matches

    async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
        query = select(FMEADocument).where(FMEADocument.product_line_code == product_line_code)
        result = await self._db.execute(query)
        fmeas = result.scalars().all()

        type_counts: dict[str, int] = {}
        high_risk_modes: list[dict] = []
        total_nodes = 0

        for fmea in fmeas:
            if not fmea.graph_data:
                continue
            for node in fmea.graph_data.get("nodes", []):
                total_nodes += 1
                t = node.get("type", "Unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
                if node.get("type") == "FailureMode":
                    s = node.get("severity", 0)
                    o = node.get("occurrence", 0)
                    d = node.get("detection", 0)
                    if s * o * d >= 100:
                        high_risk_modes.append({
                            "name": node.get("name", ""),
                            "rpn": s * o * d,
                            "fmea_id": str(fmea.fmea_id),
                            "document_no": fmea.document_no,
                        })

        return {
            "total_fmeas": len(fmeas),
            "total_nodes": total_nodes,
            "node_type_distribution": type_counts,
            "high_risk_failure_modes": sorted(high_risk_modes, key=lambda x: x["rpn"], reverse=True)[:10],
        }

    async def _get_fmea(self, fmea_id: uuid.UUID) -> FMEADocument | None:
        result = await self._db.execute(
            select(FMEADocument).where(FMEADocument.fmea_id == fmea_id)
        )
        return result.scalar_one_or_none()

    def _trace_chain(self, graph_data: dict, start_node_id: str, direction: str) -> dict:
        """BFS 遍历图，收集影响链或原因链。"""
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        node_map = {n["id"]: n for n in nodes}

        visited_nodes = set()
        result_nodes = []
        result_edges = []
        queue = [start_node_id]

        while queue:
            current = queue.pop(0)
            if current in visited_nodes:
                continue
            visited_nodes.add(current)
            if current in node_map:
                result_nodes.append(node_map[current])

            for idx, edge in enumerate(edges):
                src = edge.get("source", "")
                tgt = edge.get("target", "")
                edge_type = edge.get("type", "")
                # 用 (source, target, type, index) 做唯一标识，因为 edge 没有 id 字段
                edge_key = (src, tgt, edge_type, idx)

                if direction == "downstream" and src == current and edge_key not in {e["_key"] for e in result_edges}:
                    result_edges.append({"source": src, "target": tgt, "type": edge_type, "_key": edge_key})
                    queue.append(tgt)
                elif direction == "upstream" and tgt == current and edge_key not in {e["_key"] for e in result_edges}:
                    result_edges.append({"source": src, "target": tgt, "type": edge_type, "_key": edge_key})
                    queue.append(src)

        # 去掉内部 _key
        for e in result_edges:
            e.pop("_key", None)

        return {"nodes": result_nodes, "edges": result_edges}
```

- [ ] **Step 3: 创建 Neo4j 实现**

创建 `backend/app/graph/neo4j_repository.py`：

```python
"""Neo4j 实现：使用 Cypher 查询图投影。

需要 worker 同步完成后数据才可用。
"""
import uuid
from typing import Any

from neo4j import AsyncDriver

from app.graph.repository import FMEAGraphRepository
from app.config import settings


class Neo4jRepository(FMEAGraphRepository):
    def __init__(self, driver: AsyncDriver):
        self._driver = driver

    async def get_impact_chain(self, fmea_id: uuid.UUID, node_id: str) -> dict:
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(
                "MATCH path = (start:GraphNode {fmea_id: $fmea_id, node_id: $node_id})"
                "-[*1..3]->(end:GraphNode) "
                "RETURN nodes(path) AS ns, relationships(path) AS rs",
                fmea_id=str(fmea_id), node_id=node_id,
            )
            return await self._path_result_to_dict(result)

    async def get_cause_chain(self, fmea_id: uuid.UUID, node_id: str) -> dict:
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(
                "MATCH path = (start:GraphNode {fmea_id: $fmea_id, node_id: $node_id})"
                "<-[*1..3]-(end:GraphNode) "
                "RETURN nodes(path) AS ns, relationships(path) AS rs",
                fmea_id=str(fmea_id), node_id=node_id,
            )
            return await self._path_result_to_dict(result)

    async def find_similar_nodes(
        self, node_type: str, name_keyword: str, product_line_code: str, limit: int = 20
    ) -> list[dict]:
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(
                "MATCH (n:GraphNode) "
                "WHERE n.type = $node_type AND n.product_line_code = $product_line_code "
                "AND toLower(n.name) CONTAINS toLower($keyword) "
                "RETURN n.node_id AS node_id, n.name AS name, n.type AS type, "
                "n.fmea_id AS fmea_id "
                "LIMIT $limit",
                node_type=node_type, product_line_code=product_line_code,
                keyword=name_keyword, limit=limit,
            )
            records = await result.data()
            return records

    async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
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

            # 高风险失效模式
            risk_result = await session.run(
                "MATCH (n:GraphNode:FailureMode) WHERE n.product_line_code = $pl "
                "AND n.severity * n.occurrence * n.detection >= 100 "
                "RETURN n.name AS name, n.severity * n.occurrence * n.detection AS rpn, "
                "n.fmea_id AS fmea_id "
                "ORDER BY rpn DESC LIMIT 10",
                pl=product_line_code,
            )
            risk_records = await risk_result.data()

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
                "high_risk_failure_modes": risk_records,
            }

    async def _path_result_to_dict(self, result) -> dict:
        """将 Neo4j path 查询结果转为 {nodes, edges} dict。"""
        nodes = []
        edges = []
        seen_node_ids = set()
        seen_edge_ids = set()

        records = await result.data()
        for record in records:
            ns = record.get("ns", [])
            rs = record.get("rs", [])
            for node in ns:
                nid = dict(node).get("node_id")
                if nid and nid not in seen_node_ids:
                    seen_node_ids.add(nid)
                    nodes.append(dict(node))
            for rel in rs:
                edge_key = (rel.start_node.id, rel.end_node.id, rel.type)
                if edge_key not in seen_edge_ids:
                    seen_edge_ids.add(edge_key)
                    edges.append({
                        "source": dict(rel.start_node).get("node_id", ""),
                        "target": dict(rel.end_node).get("node_id", ""),
                        "type": rel.type,
                    })

        return {"nodes": nodes, "edges": edges}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/graph/repository.py backend/app/graph/jsonb_repository.py backend/app/graph/neo4j_repository.py
git commit -m "feat: add FMEAGraphRepository interface with JSONB and Neo4j implementations"
```

---

### Task 8: Graph Query API 路由

**Files:**
- Create: `backend/app/api/graph.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 graph API 路由**

创建 `backend/app/api/graph.py`：

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.graph.repository import FMEAGraphRepository
from app.graph.jsonb_repository import JSONBRepository

router = APIRouter(prefix="/api/graph", tags=["graph"])


def _repo(db: AsyncSession = Depends(get_db)) -> FMEAGraphRepository:
    """当前默认使用 JSONB 实现。Neo4j 可用时可切换。"""
    return JSONBRepository(db)


@router.get("/fmea/{fmea_id}/impact/{node_id}")
async def impact_chain(
    fmea_id: uuid.UUID,
    node_id: str,
    repo: FMEAGraphRepository = Depends(_repo),
    _user: User = Depends(get_current_user),
):
    """下游影响链：从指定节点出发追踪失效效应和控制措施。"""
    return await repo.get_impact_chain(fmea_id, node_id)


@router.get("/fmea/{fmea_id}/cause/{node_id}")
async def cause_chain(
    fmea_id: uuid.UUID,
    node_id: str,
    repo: FMEAGraphRepository = Depends(_repo),
    _user: User = Depends(get_current_user),
):
    """上游原因链：从指定节点出发追踪失效原因。"""
    return await repo.get_cause_chain(fmea_id, node_id)


@router.get("/similar")
async def similar_nodes(
    node_type: str = Query(..., description="节点类型，如 FailureMode"),
    name_keyword: str = Query(..., min_length=1, description="名称关键词"),
    product_line_code: str = Query(..., description="产品线代码（必填，租户隔离）"),
    limit: int = Query(20, ge=1, le=100),
    repo: FMEAGraphRepository = Depends(_repo),
    _user: User = Depends(get_current_user),
):
    """跨 FMEA 搜索相似节点。product_line_code 必填。"""
    return await repo.find_similar_nodes(node_type, name_keyword, product_line_code, limit)


@router.get("/stats")
async def cross_fmea_stats(
    product_line_code: str = Query(..., description="产品线代码（必填，租户隔离）"),
    repo: FMEAGraphRepository = Depends(_repo),
    _user: User = Depends(get_current_user),
):
    """跨 FMEA 聚合统计。product_line_code 必填。"""
    return await repo.get_cross_fmea_stats(product_line_code)


@router.post("/rebuild")
async def trigger_rebuild(
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_admin),
):
    """触发全量重建 (admin only)。异步执行，秒回防超时。"""
    async def _do_rebuild():
        from app.services.graph_projection_service import GraphProjectionService
        from app.graph.neo4j_driver import get_neo4j_driver
        from app.database import async_session

        driver = await get_neo4j_driver()
        projection = GraphProjectionService(driver, async_session)
        await projection.full_rebuild()

    background_tasks.add_task(_do_rebuild)
    return {"message": "Graph rebuild started in background"}
```

- [ ] **Step 2: 注册 router 到 main.py**

在 `backend/app/main.py` 的 import 区追加：

```python
from app.api.graph import router as graph_router
```

在 router 注册区（`app.include_router(shipment_router)` 之后）追加：

```python
app.include_router(graph_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/graph.py backend/app/main.py
git commit -m "feat: add graph query API routes with product_line isolation"
```

---

### Task 9: 全量重建 CLI

**Files:**
- Create: `backend/app/cli/__init__.py`
- Create: `backend/app/cli/graph_rebuild.py`

- [ ] **Step 1: 创建 CLI 包**

创建 `backend/app/cli/__init__.py`：

```python
```

- [ ] **Step 2: 创建全量重建 CLI**

创建 `backend/app/cli/graph_rebuild.py`：

```python
"""全量重建 Neo4j 图投影。

用法:
    python -m app.cli.graph_rebuild              # 全量重建
    python -m app.cli.graph_rebuild --retry-failed  # 重置 dead 任务
"""
import asyncio
import argparse
import sys

from app.database import async_session
from app.graph.neo4j_driver import get_neo4j_driver, ensure_constraints
from app.services.graph_projection_service import GraphProjectionService
from app.models.graph_sync_outbox import GraphSyncOutbox

from sqlalchemy import select, update, func


async def retry_failed() -> int:
    """将 outbox 中 dead 状态的任务重置为 pending。"""
    async with async_session() as db:
        result = await db.execute(
            update(GraphSyncOutbox)
            .where(GraphSyncOutbox.status == "dead")
            .values(status="pending", attempt_count=0, next_attempt_at=func.now())
            .returning(GraphSyncOutbox.id)
        )
        reset_ids = result.scalars().all()
        await db.commit()
    return len(reset_ids)


async def full_rebuild() -> dict:
    """清空 Neo4j 并从 PG 全量重建。"""
    driver = await get_neo4j_driver()
    await ensure_constraints()
    projection = GraphProjectionService(driver, async_session)
    return await projection.full_rebuild()


def main():
    parser = argparse.ArgumentParser(description="Neo4j graph projection rebuild")
    parser.add_argument("--retry-failed", action="store_true", help="Reset dead outbox tasks to pending")
    args = parser.parse_args()

    if args.retry_failed:
        count = asyncio.run(retry_failed())
        print(f"Reset {count} dead tasks to pending.")
    else:
        result = asyncio.run(full_rebuild())
        print(f"Full rebuild complete: {result}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/cli/__init__.py backend/app/cli/graph_rebuild.py
git commit -m "feat: add graph rebuild CLI with --retry-failed support"
```

---

### Task 10: Docker Compose Neo4j + Worker

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: 添加 Neo4j 和 graph-worker 服务**

在 `docker-compose.yml` 的 `frontend` 服务之后、`volumes:` 之前，追加：

```yaml

  neo4j:
    image: neo4j:5-community
    ports:
      - "7474:7474"
      - "7687:7687"
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
      SECRET_KEY: openqms-local-dev-2026-jwt-signing-key
      DATABASE_URL: postgresql+asyncpg://qms:qms_dev_2026@db:5432/qms
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: openqms2026
```

在 `volumes:` 部分追加 `neo4j_data:`：

```yaml
volumes:
  pgdata:
  neo4j_data:
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add Neo4j and graph-worker services to Docker Compose"
```

---

### Task 11: 端到端验证

- [ ] **Step 1: Run all tests**

Run: `cd backend && SECRET_KEY=openqms-local-dev-2026-jwt-signing-key python -m pytest tests/test_graph_projection.py tests/test_graph_sync_worker.py -v`
Expected: All passed

- [ ] **Step 2: Run Alembic migration**

Run: `cd backend && alembic upgrade head`
Expected: No errors

- [ ] **Step 3: Verify outbox model importable**

Run: `cd backend && SECRET_KEY=openqms-local-dev-2026-jwt-signing-key python -c "from app.models.graph_sync_outbox import GraphSyncOutbox; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Verify API starts**

Run: `cd backend && SECRET_KEY=openqms-local-dev-2026-jwt-signing-key python -c "from app.main import app; print([r.path for r in app.routes if '/graph' in getattr(r, 'path', '')])"`
Expected: 包含 `/api/graph/fmea/{fmea_id}/impact/{node_id}` 等 5 条路由
