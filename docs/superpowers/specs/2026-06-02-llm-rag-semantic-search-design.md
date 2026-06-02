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
| 异步写入 | Outbox 模式 | 复用现有 graph_sync_outbox 基础设施 |
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
    entity_id UUID NOT NULL,               -- 源记录 ID
    entity_field VARCHAR(50) NOT NULL,     -- 嵌入的字段名
    chunk_index INT NOT NULL DEFAULT 0,   -- 分块索引（当前每个字段一个块，预留未来大文本分块）
    chunk_text TEXT NOT NULL,              -- 被嵌入的文本（用于展示和重新嵌入）
    embedding vector($DIMENSIONS) NOT NULL, -- 嵌入向量（维度由 EMBEDDING_DIMENSIONS 环境变量决定，部署时固定）
    product_line_code VARCHAR(20),         -- 产品线过滤
    metadata JSONB DEFAULT '{}',           -- 附加上下文（document_no, node_type, severity, status 等）
    embedding_model VARCHAR(50) NOT NULL,  -- 使用的嵌入模型
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (entity_type, entity_id, entity_field, chunk_index)
);

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

-- 触发器自动更新 tsv
CREATE OR REPLACE FUNCTION update_embedding_tsv() RETURNS trigger AS $$
BEGIN
    NEW.tsv := to_tsvector('zhcfg', NEW.chunk_text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### 各实体的嵌入字段映射

| entity_type | entity_id 指向 | entity_field | chunk_text 来源 |
|-------------|---------------|--------------|----------------|
| fmea_node | fmea_documents.fmea_id | `{node_type}.{node_id}.name` | 节点 name + requirement + specification（FMEA 特殊：entity_id 指向 fmea_id，节点信息在 metadata.node_id 中） |
| capa | capa_eightd.report_id | `d2_description` | 问题描述 |
| capa | capa_eightd.report_id | `d4_root_cause` | 根因分析 |
| capa | capa_eightd.report_id | `d5_correction` | 纠正措施 |
| capa | capa_eightd.report_id | `d7_prevention` | 预防措施 |
| audit_finding | audit_findings.id | `description` | 发现描述 |
| audit_finding | audit_findings.id | `root_cause` | 根因 |
| audit_finding | audit_findings.id | `corrective_action` | 纠正措施 |
| complaint | customer_complaints.id | `defect_desc` | 缺陷描述 |
| complaint | customer_complaints.id | `root_cause` | 根因 |
| complaint | customer_complaints.id | `corrective_action` | 纠正措施 |
| scar | supplier_scars.id | `description` | 问题描述 |
| scar | supplier_scars.id | `resolution_summary` | 解决方案 |
| rma | rma_records.id | `analysis_result` | 分析结果 |
| rma | rma_records.id | `corrective_action` | 纠正措施 |

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

### 异步生成 — Outbox 模式

复用 `graph_sync_outbox` 表，新增 `event_type = 'embedding_sync'`：

1. **触发**：各模块 CRUD 服务在写入后插入 outbox 事件（`event_type = 'embedding_sync'`，`aggregate_type = 'document_embedding'`）
2. **Worker 路由分发**：现有 `graph_sync_worker.py` 硬编码了 FMEA→Neo4j 同步逻辑且不检查 `event_type`。必须重构 Worker 的 `run_worker` 循环，按 `event_type` 路由：
   - `event_type = 'graph_sync'`（现有）→ 调用 `projection.sync_fmea_to_neo4j()`
   - `event_type = 'embedding_sync'`（新增）→ 调用 `EmbeddingService.process_embedding_event()`
   - 去重函数 `deduplicate_tasks` 也需按 `event_type` 分组，避免 embedding 事件被 FMEA 去重逻辑丢弃
3. **批量处理**：合并多个待处理事件，单次 API 调用最多 2048 条文本
4. **幂等**：`UNIQUE (entity_type, entity_id, entity_field, chunk_index)` 保证 upsert 安全

### 初始回填

```bash
python -m app.services.embedding_backfill [--batch-size 100] [--entity-type fmea_node]
```

遍历所有现有记录，批量生成 embedding。支持按实体类型过滤。

### 模型切换

当 `embedding_model` 变更时，回填命令检测到 `embedding_model` 不匹配的记录并重新嵌入。

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
def reciprocal_rank_fusion(results_lists: list[list], k: int = 60) -> list:
    scores = {}
    for results in results_lists:
        for rank, item in enumerate(results):
            scores[item.id] = scores.get(item.id, 0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

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

1. 调用 `semantic_search()` 检索 Top-N 相关文档块
2. 拼接为 RAG context（每块带来源标注：entity_type + document_no）
3. 构建 prompt：系统指令 + context + 用户问题
4. 调用 `LLMProvider.complete()` 生成回答 — **关键适配**：现有 `complete()` 方法内部对所有 LLM 响应执行 `json.loads()`，不支持纯文本输出。因此 RAG prompt 必须要求 LLM 返回 JSON 格式：
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
5. 返回回答 + 引用来源列表

### Prompt 模板

```
你是一个质量管理系统助手。根据以下历史质量记录回答用户问题。

## 相关记录
{context_chunks_with_sources}

## 用户问题
{question}

请用中文回答。在回答中引用来源时使用 [1], [2] 等编号。
如果记录中没有相关信息，请如实说明。
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
      "entity_id": "uuid",
      "entity_field": "FailureMode.abc123.name",
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

需要使用 `pgvector/pgvector:pg15` 替代官方 `postgres:15-alpine` 镜像。

**pgvector 扩展**：镜像自带，初始化脚本直接 `CREATE EXTENSION IF NOT EXISTS vector;`

**中文分词 zhparser**：pgvector 官方镜像**不包含** zhparser。需要自定义 Dockerfile：

```dockerfile
FROM pgvector/pgvector:pg15
RUN apt-get update && apt-get install -y build-essential postgresql-server-dev-15 git
# 安装 scws（zhparser 依赖）
RUN git clone https://github.com/xutils/scws.git && cd scws && ./configure && make && make install
# 安装 zhparser
RUN git clone https://github.com/amutu/zhparser.git && cd zhparser && make && make install
```

初始化脚本：
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS zhparser;
CREATE TEXT SEARCH CONFIGURATION zhcfg (PARSER = zhparser);
ALTER TEXT SEARCH CONFIGURATION zhcfg ADD MAPPING FOR n,v,a,i,e,l WITH simple;
```

**降级方案**：如果 zhparser 编译复杂度过高，可退而使用 PostgreSQL 内置的 `pg_trgm` 扩展做三元组匹配，或在应用层用 `jieba` 分词后以空格分隔传入 `to_tsquery('simple', ...)`。

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
1. Alembic 迁移：pgvector 扩展 + document_embeddings 表 + tsvector 索引
2. EmbeddingProvider 抽象 + OpenAI/Ollama 实现
3. Docker Compose 更新（pgvector 镜像 + 可选 Ollama）

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
| 向量维度不匹配 | 模型切换后查询失败 | embedding_model 字段 + 重新索引命令 |
