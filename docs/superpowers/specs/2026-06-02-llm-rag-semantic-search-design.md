# LLM RAG 语义搜索设计文档

**日期**: 2026-06-02  
**状态**: 待审批  
**范围**: Phase 3 — AI + 知识图谱增强

---

## 1. 概述

### 目标

为 OpenQMS 添加基于向量嵌入的语义搜索和 RAG 问答能力，替代现有的纯关键词子串匹配搜索。用户可以用自然语言搜索历史质量记录（FMEA、CAPA、审核发现、客诉、SCAR、RMA），并获得 LLM 生成的回答及引用来源。

### 核心能力

1. **语义搜索** — 自然语言查询，向量相似度 + 全文检索混合搜索，按相关度排序
2. **RAG 问答** — 基于检索结果生成 LLM 回答，附带来源引用链接

### 不在范围内

- 全局搜索栏（header）— 记入后续 roadmap
- 多语言 embedding — 当前仅支持中英文混合
- 实时协同搜索 — 无 WebSocket 推送

---

## 2. 架构

### 整体架构

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   前端 UI    │────▶│  Search API  │────▶│ SearchService    │
│ (语义搜索Tab)│◀────│  /api/search │◀────│ (混合检索+RAG)   │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                          ┌────────────────────────┼────────────────────┐
                          │                        │                    │
                   ┌──────▼──────┐  ┌──────────────▼──┐  ┌─────────────▼────────┐
                   │ pgvector    │  │ PostgreSQL      │  │ LLMProvider          │
                   │ cosine 搜索 │  │ tsvector 全文检索│  │ (Claude/OpenAI/Local) │
                   └─────────────┘  └─────────────────┘  └──────────────────────┘
                          ▲
                          │ 写入
                   ┌──────┴──────┐
                   │ Embedding   │
                   │ Sync Worker │
                   │ (Outbox)    │
                   └──────┬──────┘
                          │
                   ┌──────▼──────┐
                   │ Embedding   │
                   │ Provider    │
                   │ (OpenAI/    │
                   │  Ollama)    │
                   └─────────────┘
```

### 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 向量存储 | pgvector | 零新基础设施，复用现有 PostgreSQL |
| 向量索引 | HNSW | 比 IVFFlat 更适合增量更新，查询性能更好 |
| 全文检索 | PostgreSQL tsvector + GIN | 原生支持，中文需 zhparser 扩展 |
| 混合排序 | RRF (倒数排名融合) | 简单有效的多路结果融合算法 |
| Embedding 生成 | OpenAI API + Ollama | 可配置，复用现有 provider 模式 |
| 异步写入 | 独立 Outbox 模式 | 新建 embedding_sync_outbox + 独立 worker，避免与 graph worker 冲突 |
| LLM 问答 | 现有 LLMProvider | 复用 Claude/OpenAI/Local 三提供商 |

---

## 3. 数据模型

### pgvector 扩展

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### document_embeddings 表

```sql
CREATE TABLE document_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(20) NOT NULL,      -- fmea_node, capa, audit_finding, complaint, scar, rma
    entity_id UUID NOT NULL,               -- 源记录 ID（fmea_id / report_id / finding_id 等）
    node_id VARCHAR(36),                   -- FMEA 图节点 ID（仅 entity_type=fmea_node 时有值）
    entity_field VARCHAR(50) NOT NULL,     -- 嵌入的字段名（如 name, d4_root_cause, description）
    chunk_index INT NOT NULL DEFAULT 0,    -- 分块索引（当前每个字段一个块，预留未来大文本分块）
    chunk_text TEXT NOT NULL,              -- 被嵌入的文本（用于展示和重新嵌入）
    embedding vector($DIMENSIONS) NOT NULL, -- 嵌入向量（维度由 EMBEDDING_DIMENSIONS 环境变量决定，部署时固定）
    product_line_code VARCHAR(20),         -- 产品线过滤
    metadata JSONB DEFAULT '{}',           -- 附加上下文（document_no, node_type, severity, status 等）
    embedding_model VARCHAR(50) NOT NULL,  -- 使用的嵌入模型
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- 注意：不使用单个 UNIQUE 约束，因为 node_id 对非 FMEA 实体为 NULL，PostgreSQL 中 NULL != NULL
    -- 会导致非 FMEA 记录无法去重。改用两个 partial unique index（见下方）
);

-- 幂等去重：FMEA 节点（node_id 非空）
CREATE UNIQUE INDEX idx_embedding_uniq_fmea ON document_embeddings
    (entity_type, entity_id, node_id, entity_field, chunk_index)
    WHERE node_id IS NOT NULL;

-- 幂等去重：非 FMEA 实体（node_id 为空）
CREATE UNIQUE INDEX idx_embedding_uniq_other ON document_embeddings
    (entity_type, entity_id, entity_field, chunk_index)
    WHERE node_id IS NULL;

-- HNSW 索引（近似最近邻）
CREATE INDEX idx_embedding_hnsw ON document_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 实体过滤索引
CREATE INDEX idx_embedding_entity ON document_embeddings
    (entity_type, product_line_code);
```

### 全文检索列

```sql
-- 添加 tsvector 列（中文使用 zhparser 分词）
ALTER TABLE document_embeddings ADD COLUMN tsv tsvector;
CREATE INDEX idx_embedding_tsv ON document_embeddings USING gin(tsv);

-- 触发器函数
CREATE OR REPLACE FUNCTION update_embedding_tsv() RETURNS trigger AS $$
BEGIN
    NEW.tsv := to_tsvector('zhcfg', NEW.chunk_text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 绑定触发器到表（必须显式创建，否则函数不会自动执行）
CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE
    ON document_embeddings FOR EACH ROW EXECUTE FUNCTION update_embedding_tsv();
```

### 各实体的嵌入字段映射

| entity_type | entity_id 指向 | node_id | entity_field | chunk_text 来源 |
|-------------|---------------|---------|--------------|----------------|
| fmea_node | fmea_documents.fmea_id | graph node UUID | `name` | 节点 name + requirement + specification |
| capa | capa_eightd.report_id | NULL | `d2_description` | 问题描述 |
| capa | capa_eightd.report_id | NULL | `d4_root_cause` | 根因分析 |
| capa | capa_eightd.report_id | NULL | `d5_correction` | 纠正措施 |
| capa | capa_eightd.report_id | NULL | `d7_prevention` | 预防措施 |
| audit_finding | audit_findings.finding_id | NULL | `description` | 发现描述 |
| audit_finding | audit_findings.finding_id | NULL | `root_cause` | 根因 |
| audit_finding | audit_findings.finding_id | NULL | `corrective_action` | 纠正措施 |
| complaint | customer_complaints.complaint_id | NULL | `defect_desc` | 缺陷描述 |
| complaint | customer_complaints.complaint_id | NULL | `root_cause` | 根因 |
| complaint | customer_complaints.complaint_id | NULL | `corrective_action` | 纠正措施 |
| scar | supplier_scars.scar_id | NULL | `description` | 问题描述 |
| scar | supplier_scars.scar_id | NULL | `resolution_summary` | 解决方案 |
| rma | rma_records.rma_id | NULL | `analysis_result` | 分析结果 |
| rma | rma_records.rma_id | NULL | `corrective_action` | 纠正措施 |

---

## 4. Embedding 生成管线

### EmbeddingProvider 抽象

```python
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def model_name(self) -> str: ...
    @property
    def dimensions(self) -> int: ...
```

**实现**：
- `OpenAIEmbeddingProvider` — `text-embedding-3-small`，1536 维
- `OllamaEmbeddingProvider` — `nomic-embed-text`（768 维）或 `BGE-M3`（1024 维）

**环境变量**：
- `EMBEDDING_PROVIDER`: `openai | ollama`（默认跟随 `LLM_PROVIDER`）
- `EMBEDDING_MODEL`: 可选覆盖
- `EMBEDDING_BASE_URL`: Ollama 地址

### 异步生成 — 独立 Outbox 模式

**不复用** `graph_sync_outbox`。现有 worker 硬编码 FMEA→Neo4j 逻辑且不检查 event_type，强行复用会导致运行异常。新建独立的 `embedding_sync_outbox` 表和 `embedding_sync_worker` 进程。

```sql
CREATE TABLE embedding_sync_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(20) NOT NULL,      -- fmea_node, capa, audit_finding, complaint, scar, rma
    entity_id UUID NOT NULL,
    product_line_code VARCHAR(20),
    -- 可靠性字段（镜像 graph_sync_outbox）
    status VARCHAR(20) DEFAULT 'pending',  -- pending / processing / completed / dead_letter
    retry_count INT DEFAULT 0,
    max_attempts INT DEFAULT 5,
    next_attempt_at TIMESTAMPTZ DEFAULT NOW(),
    locked_at TIMESTAMPTZ,                 -- Worker 领取时设置，用于 FOR UPDATE SKIP LOCKED
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);
-- Worker 领取 pending 事件的索引
CREATE INDEX idx_embedding_outbox_pending ON embedding_sync_outbox (next_attempt_at)
    WHERE status = 'pending';
```

Worker 使用 `FOR UPDATE SKIP LOCKED` 安全领取事件，exponential backoff 从 10s 到 270s，超过 `max_attempts` 后标记为 `dead_letter`。

1. **触发**：各模块 CRUD 服务在写入后插入 `embedding_sync_outbox` 事件
2. **独立 Worker**：`embedding_sync_worker.py`（独立进程，`python -m app.services.embedding_sync_worker`），仅处理 embedding 事件，不触碰 graph_sync_outbox
3. **批量处理（关键优化）**：Worker 一次领取 N 个 pending 事件（默认 N=64），按以下流程处理：
   - 根据每个事件的 `entity_type` + `entity_id` 查询对应的 `chunk_text`
   - **收集所有 chunk_text 到一个列表**，统一调用一次 `EmbeddingProvider.embed(texts)`（单次 HTTP 请求）
   - 将返回的向量按顺序分发，upsert 到 `document_embeddings` 表
   - 标记 outbox 事件为 completed
   - 这样 N 个实体只需 1 次 API 调用，而非 N 次，网络延迟降低一个数量级
4. **幂等**：`UNIQUE (entity_type, entity_id, entity_field, chunk_index)` 保证 upsert 安全
5. **重试与死信**：复用现有 exponential backoff 模式（10s→270s，5 次后标记 dead_letter）

### 初始回填

```bash
python -m app.services.embedding_backfill [--batch-size 100] [--entity-type fmea_node]
```

遍历所有现有记录，批量生成 embedding。支持按实体类型过滤。

### 模型切换

当 `embedding_model` 变更时，回填命令检测到 `embedding_model` 不匹配的记录并重新嵌入。

### 孤儿向量清理

`document_embeddings` 采用多态关联（entity_id 指向 6 个不同业务表），无法声明物理外键级联删除。必须在应用层保证删除一致性：

**物理删除**：各业务模块的 CRUD 服务在执行物理删除时，必须在同一事务中清除对应 embedding：

```python
# 示例：删除 CAPA 时同步清理
async def delete_capa(db: AsyncSession, report_id: UUID):
    await db.execute(delete(CAPA).where(CAPA.report_id == report_id))
    await db.execute(
        delete(DocumentEmbedding).where(
            DocumentEmbedding.entity_type == "capa",
            DocumentEmbedding.entity_id == report_id
        )
    )
    await db.commit()
```

各模块同理：FMEA 删除时清理 `entity_type='fmea_node' AND entity_id=fmea_id`；审核发现、客诉、SCAR、RMA 类推。

**逻辑删除（Soft Delete）**：对于采用 `is_deleted` 或状态标记删除的模块，搜索 SQL 必须排除已删除实体。在 SearchService 中做后过滤或在 SQL JOIN 时排除。

**兜底清理（可选）**：定期运行脚本检查孤儿向量（embedding 存在但源记录不存在），清理残留数据。

---

## 5. 搜索与检索

### 混合搜索策略

**向量搜索**：pgvector cosine 距离近邻，返回 Top-K

```sql
SELECT id, entity_type, entity_id, entity_field, chunk_text, metadata,
       1 - (embedding <=> $query_vector) AS similarity
FROM document_embeddings
WHERE product_line_code = $product_line
  AND entity_type = ANY($entity_types)
ORDER BY embedding <=> $query_vector
LIMIT $k;
```

**全文检索**：tsvector + plainto_tsquery

```sql
SELECT id, entity_type, entity_id, entity_field, chunk_text, metadata,
       ts_rank(tsv, query) AS rank
FROM document_embeddings, plainto_tsquery('zhcfg', $query) query
WHERE tsv @@ query
  AND product_line_code = $product_line
  AND entity_type = ANY($entity_types)
ORDER BY rank DESC
LIMIT $k;
```

**RRF 融合**：

```python
def reciprocal_rank_fusion(
    results_lists: list[list],
    weights: list[float] = [0.7, 0.3],  # [vector_weight, fulltext_weight]
    k: int = 60,
) -> list:
    """Weighted RRF: score = sum(w_i / (k + rank_i)) for each result."""
    scores = {}
    for weight, results in zip(weights, results_lists):
        for rank, item in enumerate(results):
            scores[item.id] = scores.get(item.id, 0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

权重通过环境变量 `SEARCH_VECTOR_WEIGHT`（默认 0.7）和 `SEARCH_FULLTEXT_WEIGHT`（默认 0.3）配置，传入 `weights` 参数。

### SearchService

```python
class SearchService:
    async def semantic_search(
        self,
        query: str,
        product_line_code: str | None = None,
        entity_types: list[str] | None = None,
        limit: int = 20,
    ) -> SearchResults: ...

    async def ask(
        self,
        question: str,
        product_line_code: str | None = None,
        max_context_chunks: int = 10,
    ) -> QAResponse: ...
```

### Q&A 流程

1. 调用 `semantic_search()` 检索 Top-N 相关文档块（含权限过滤）
2. 拼接为 RAG context（每块带来源标注：entity_type + document_no）
3. 构建 prompt：系统指令 + context + 用户问题
4. 调用 LLM 生成回答 — **接口适配**：

   **方案 A（推荐）：JSON Schema 包装**，复用现有 `complete()` 接口，RAG prompt 要求 LLM 返回 JSON：
   ```python
   rag_schema = {
       "type": "object",
       "properties": {
           "answer": {"type": "string", "description": "基于上下文生成的回答，支持 markdown 格式"}
       },
       "required": ["answer"]
   }
   llm_response = await self.llm_provider.complete(prompt=rag_prompt, response_schema=rag_schema)
   answer = llm_response.get("answer", "")
   ```

   **方案 B：新增 `complete_text()` 方法**，在 `LLMProvider` 协议中扩展一个不做 `json.loads()` 的接口：
   ```python
   class LLMProvider(Protocol):
       async def complete(self, prompt: str, response_schema: dict) -> dict: ...
       async def complete_text(self, prompt: str) -> str: ...  # 新增，直接返回原始文本
   ```
   各提供商实现 `complete_text()` 时跳过 JSON 解析，直接返回 `text`。RAG 调用方使用此方法。

   **实现时选择方案 A**（最小改动），如果后续有更多非 JSON 输出场景再引入方案 B。

5. 返回回答 + 引用来源列表

### Prompt 模板

**重要**：现有 `LLMProvider.complete()` 对所有响应执行 `json.loads()`，Claude 和 Local provider 的 `response_schema` 仅作为 prompt 指令传入，不是 API 级强约束（不像 OpenAI 的 `response_format={"type": "json_object"}`）。因此 prompt 必须**显式要求只返回 JSON**，不能有 markdown 围栏或其他文本。

```
你是一个质量管理系统助手。根据以下历史质量记录回答用户问题。

## 相关记录
{context_chunks_with_sources}

## 用户问题
{question}

## 输出要求
请用中文回答。在回答中引用来源时使用 [1], [2] 等编号。
如果记录中没有相关信息，请如实说明。

**必须只返回以下 JSON 格式，不要添加任何其他文本、markdown 围栏或解释：**
{"answer": "你的回答内容"}
```

---

## 6. API 设计

### 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/search/semantic` | 语义搜索 |
| POST | `/api/search/ask` | RAG 问答 |
| POST | `/api/search/reindex` | 触发重新索引（admin） |

### 语义搜索

```
GET /api/search/semantic?q=焊接虚焊&entity_types=fmea_node,capa&product_line_code=DC-DC-100&limit=20
```

**响应**：
```json
{
  "results": [
    {
      "entity_type": "fmea_node",
      "entity_id": "fmea-uuid",
      "node_id": "node-uuid-abc123",
      "entity_field": "name",
      "chunk_text": "焊接虚焊导致接触不良",
      "score": 0.92,
      "source": "hybrid",
      "metadata": {
        "document_no": "PFMEA-2026-001",
        "node_type": "FailureMode"
      }
    }
  ],
  "total": 42,
  "query_time_ms": 85
}
```

**说明**：`entity_id` 指向源文档 ID（如 fmea_id），`node_id` 仅 FMEA 节点有值（用于跳转到图编辑器高亮节点），`entity_field` 只存字段名（如 `name`、`d4_root_cause`）。

### RAG 问答

```
POST /api/search/ask
{
  "question": "焊接虚焊的历史根因和措施有哪些？",
  "product_line_code": "DC-DC-100",
  "max_context_chunks": 10
}
```

**响应**：
```json
{
  "answer": "根据历史记录，焊接虚焊主要有以下根因：...",
  "sources": [
    {
      "entity_type": "fmea_node",
      "entity_id": "uuid",
      "document_no": "PFMEA-2026-001",
      "chunk_text": "焊接虚焊导致接触不良",
      "relevance_score": 0.92
    }
  ],
  "llm_available": true,
  "query_time_ms": 2300
}
```

### 权限

| 端点 | viewer | engineer | manager | admin |
|------|:------:|:--------:|:-------:|:-----:|
| semantic search | ✅ | ✅ | ✅ | ✅ |
| ask | ❌ | ✅ | ✅ | ✅ |
| reindex | ❌ | ❌ | ❌ | ✅ |

### 结果级权限过滤

搜索结果横跨 FMEA、CAPA、审核、客诉、SCAR、RMA 六个模块，不能仅用路由级角色检查。必须在 SearchService 中做 **per-source authorization**：

1. **检索前过滤**：在 SQL 查询中加入 `product_line_code` 过滤（用户只能搜索其有权访问的产品线）
2. **检索后过滤**：对返回的每条结果，根据 `entity_type` 映射到对应模块权限，调用现有权限检查：
   - `fmea_node` → 检查 FMEA 模块读权限
   - `capa` → 检查 CAPA 模块读权限
   - `audit_finding` → 检查审核模块读权限
   - `complaint` → 检查客诉模块读权限（CUSTOMER_QUALITY）
   - `scar` → 检查 SCAR 模块读权限
   - `rma` → 检查客诉模块读权限（CUSTOMER_QUALITY，RMA 路由挂在 customer_quality 下，无独立模块枚举）
3. **Q&A 同理**：RAG context 仅包含用户有权访问的文档块，prompt 中不出现无权限数据

```python
# 伪代码
async def filter_by_permission(results: list, user: User) -> list:
    accessible = []
    for r in results:
        module = ENTITY_MODULE_MAP[r.entity_type]  # e.g. "fmea" → ModulePermission.FMEA
        if has_module_access(user, module, r.product_line_code):
            accessible.append(r)
    return accessible
```

---

## 7. 前端设计

### KnowledgeGraphPage 第三个 Tab

在现有 `风险概览` 和 `关键词搜索` 旁增加 `语义搜索` Tab。

**搜索模式**：
- 顶部搜索框 + 搜索/问答切换按钮
- 过滤器：实体类型（多选）、产品线（下拉）
- 结果列表：卡片式展示，含实体类型图标、来源文档号、匹配文本、相似度分数、跳转链接

**问答模式**：
- 点击 `问答` 按钮切换
- 结果区显示 LLM 回答（Markdown 渲染）+ 引用来源列表
- LLM 不可用时按钮置灰，提示"当前仅支持搜索模式"

**交互细节**：
- 搜索输入 500ms 防抖
- Enter 触发搜索
- 结果跳转：FMEA → `/fmea/:id` 并高亮节点；CAPA → `/capa/:id`
- 空状态：显示热门搜索建议
- 加载态：Skeleton + 打字机效果（问答）

### 新增文件

- `frontend/src/api/search.ts` — API 函数
- `frontend/src/pages/graph/SemanticSearchTab.tsx` — 语义搜索 Tab 组件
- `frontend/src/components/search/QAAnswer.tsx` — 问答结果组件

---

## 8. 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EMBEDDING_PROVIDER` | (跟随 LLM_PROVIDER) | `openai` 或 `ollama` |
| `EMBEDDING_MODEL` | (provider 默认) | 嵌入模型名称 |
| `EMBEDDING_BASE_URL` | `http://ollama:11434` | Ollama 地址 |
| `EMBEDDING_DIMENSIONS` | `1536` | 向量维度（部署时固定，切换模型需重建表） |
| `SEARCH_VECTOR_WEIGHT` | `0.7` | 向量搜索在 RRF 中的权重 |
| `SEARCH_FULLTEXT_WEIGHT` | `0.3` | 全文搜索在 RRF 中的权重 |

---

## 9. Docker Compose 变更

### PostgreSQL 安装扩展

**镜像**：使用 `pgvector/pgvector:pg15` 替代官方 `postgres:15-alpine`（自带 pgvector 扩展）。

**中文分词 zhparser**：pgvector 官方镜像不包含 zhparser，需要自定义 Dockerfile。创建 `docker/postgres/Dockerfile`：

```dockerfile
FROM pgvector/pgvector:pg15
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential postgresql-server-dev-15 git ca-certificates && \
    # scws（zhparser 依赖）
    git clone https://github.com/xutils/scws.git /tmp/scws && \
    cd /tmp/scws && ./configure && make && make install && ldconfig && \
    # zhparser
    git clone https://github.com/amutu/zhparser.git /tmp/zhparser && \
    cd /tmp/zhparser && make USE_PGXS=1 && make USE_PGXS=1 install && \
    # 清理
    apt-get purge -y build-essential git && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* /tmp/scws /tmp/zhparser
```

docker-compose.yml 中 `db` 服务改为 `build: ./docker/postgres` 而非 `image: postgres:15-alpine`。

**扩展创建 — Alembic 迁移**：不依赖 Docker init 脚本（已有 volume 时 init 脚本不重新执行）。在 Alembic 迁移中创建扩展：

```python
# alembic/versions/020_add_vector_extensions.py
import logging
from sqlalchemy import text

logger = logging.getLogger("alembic.migration")

def upgrade():
    # pgvector：必须安装（Docker 镜像自带，本地需手动安装）
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # zhparser：显式预检查，避免 PostgreSQL 事务 abort
    # （PostgreSQL 中语句失败会导致整个事务进入 aborted 状态，try/catch 无法恢复）
    conn = op.get_bind()
    has_zhparser = conn.execute(
        text("SELECT 1 FROM pg_available_extensions WHERE name = 'zhparser'")
    ).fetchone()

    if has_zhparser:
        op.execute("CREATE EXTENSION IF NOT EXISTS zhparser")
        op.execute("""
            CREATE TEXT SEARCH CONFIGURATION zhcfg (PARSER = zhparser);
            ALTER TEXT SEARCH CONFIGURATION zhcfg ADD MAPPING FOR n,v,a,i,e,l WITH simple;
        """)
        logger.info("zhparser installed, zhcfg created with zhparser parser")
    else:
        # 降级：使用 simple 配置（按空格分词，中文效果有限但零依赖）
        op.execute("CREATE TEXT SEARCH CONFIGURATION zhcfg (COPY = simple)")
        logger.warning("zhparser not available, zhcfg created with simple config (Chinese tokenization degraded)")

def downgrade():
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS zhcfg")
    op.execute("DROP EXTENSION IF EXISTS zhparser")  # IF EXISTS 防止本地环境报错
    op.execute("DROP EXTENSION IF EXISTS vector")
```

**降级方案**：如果 zhparser 编译失败，全文检索退化为 `websearch_to_tsquery('simple', ...)`（按空格分词，对中文效果有限但零依赖），或在应用层用 `jieba` 分词后拼接空格传入 `to_tsquery('simple', ...)`。向量搜索不受影响，仍可独立工作。

### Ollama 服务（可选）

```yaml
ollama:
  image: ollama/ollama:latest
  volumes:
    - ollama_data:/root/.ollama
  ports:
    - "11434:11434"
  deploy:
    resources:
      limits:
        memory: 2G
```

---

## 10. 实现计划

### 阶段 1：基础设施
1. Alembic 迁移：pgvector 扩展 + zhparser 扩展（容错降级）+ document_embeddings 表 + tsvector 索引 + 触发器 + embedding_sync_outbox 表
2. EmbeddingProvider 抽象 + OpenAI/Ollama 实现
3. Docker Compose 更新（自定义 pgvector+zhparser 镜像 + 可选 Ollama）

### 阶段 2：写入管线
4. Outbox 事件：各模块 CRUD 服务触发 embedding_sync 事件
5. Worker 处理：embedding 生成 + upsert
6. 回填命令

### 阶段 3：搜索服务
7. SearchService：向量搜索 + 全文检索 + RRF 融合
8. Q&A 服务：RAG prompt + LLM 调用
9. API 端点：/search/semantic + /search/ask + /search/reindex

### 阶段 4：前端
10. search.ts API 函数
11. SemanticSearchTab 组件
12. QAAnswer 组件
13. 集成到 KnowledgeGraphPage

### 阶段 5：测试与优化
14. 搜索质量调优（RRF 权重、Top-K、chunk 策略）
15. 性能测试（索引参数、批量大小）

---

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 中文分词质量 | 搜索准确率 | 使用 zhparser + 用户反馈调优 |
| Embedding API 延迟 | 写入延迟 | 异步 outbox + 批量处理 |
| pgvector 性能上限 | 大数据量查询慢 | HNSW 索引 + 按产品线分区 |
| LLM 不可用 | Q&A 功能降级 | 降级到纯搜索模式，UI 明确提示 |
| 向量维度变更 | 模型切换后写入失败 | 见下方详细缓解方案 |
| 本地开发无 zhparser | Alembic 迁移中断 | 迁移脚本 try-catch 降级到 simple 配置 |

### 向量维度变更的详细缓解方案

pgvector 的 `vector(N)` 类型在 DDL 时固定维度，PostgreSQL 会拒绝插入维度不符的向量。且 `ALTER COLUMN TYPE vector(M)` 无法将已有向量从 N 维 cast 到 M 维（数据不兼容）。模型切换如果涉及维度变更（如 OpenAI 1536 → Ollama 768），必须重建数据：

**安全迁移步骤**（Alembic 迁移）：

```python
def upgrade(new_dim: int):
    # 1. 停止 embedding_sync_worker（避免迁移期间写入）
    # 通过环境变量 EMBEDDING_WORKER_ENABLED=false 或 docker compose stop embedding-worker

    # 2. 删除旧索引
    op.execute("DROP INDEX IF EXISTS idx_embedding_hnsw")

    # 3. 清空旧向量数据（维度不兼容，无法保留）
    op.execute("DELETE FROM document_embeddings")

    # 4. 变更列维度
    op.execute(f"ALTER TABLE document_embeddings ALTER COLUMN embedding TYPE vector({new_dim})")

    # 5. 重建 HNSW 索引
    op.execute(f"""
        CREATE INDEX idx_embedding_hnsw ON document_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # 6. 清空 outbox（旧事件的 embedding 已删除，需要重新触发）
    op.execute("DELETE FROM embedding_sync_outbox")
```

**操作流程**：
1. 停止 embedding-worker
2. 修改 `EMBEDDING_DIMENSIONS` 和 `EMBEDDING_MODEL` 环境变量
3. 运行 Alembic 迁移（清空向量 → 变更列 → 重建索引）
4. 重启 embedding-worker
5. 执行回填命令重新生成全部 embedding
6. 期间搜索功能降级（向量搜索不可用，全文检索仍可工作）

**注意**：生产环境建议在低峰期执行，或采用"新建列→回填→切换→删旧列"的零停机方案（更复杂，按需实施）。
