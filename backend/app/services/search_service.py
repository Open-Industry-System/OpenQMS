"""Search service: hybrid vector + fulltext search with RRF fusion, and RAG Q&A."""
import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.models.user import User
from app.schemas.search import QAResponse, QASource, SearchResultItem, SemanticSearchResponse

logger = logging.getLogger(__name__)

# Map entity_type to Module permission enum
ENTITY_MODULE_MAP = {
    "fmea_node": Module.FMEA,
    "capa": Module.CAPA,
    "audit_finding": Module.AUDIT,
    "complaint": Module.CUSTOMER_QUALITY,
    "scar": Module.SCAR,
    "rma": Module.CUSTOMER_QUALITY,
}


class SearchService:
    def __init__(self, db: AsyncSession, llm_provider=None, embedding_provider=None):
        self.db = db
        self.llm = llm_provider
        self.embedding = embedding_provider

    async def _get_user_product_lines(self, user: User) -> list[str] | None:
        """Get product lines the user has access to. Returns None for admin (all)."""
        from sqlalchemy import select

        from app.models.role import UserProductLine

        if user.role_definition and user.role_definition.role_key == "admin":
            return None  # None means no filter (all)

        result = await self.db.execute(
            select(UserProductLine.product_line_code).where(UserProductLine.user_id == user.user_id)
        )
        codes = [row[0] for row in result.fetchall()]
        return codes if codes else []

    async def semantic_search(
        self,
        query: str,
        user: User,
        product_line_code: str | None = None,
        product_type_code: str | None = None,
        entity_types: list[str] | None = None,
        limit: int = 20,
    ) -> SemanticSearchResponse:
        """Hybrid search: vector cosine + fulltext, merged with RRF."""
        start = time.monotonic()

        # Derive user's accessible product lines
        user_pls = await self._get_user_product_lines(user)

        # Build filter conditions
        filters = []
        params: dict = {"fetch_limit": limit * 3}

        if product_line_code:
            if user_pls is not None and product_line_code not in user_pls:
                elapsed = int((time.monotonic() - start) * 1000)
                return SemanticSearchResponse(results=[], total=0, query_time_ms=elapsed)
            filters.append("product_line_code = :product_line_code")
            params["product_line_code"] = product_line_code
        else:
            if user_pls is not None:
                filters.append("product_line_code = ANY(:user_product_lines)")
                params["user_product_lines"] = user_pls

        if product_type_code and not product_line_code:
            from app.models.product_line import ProductLine
            from sqlalchemy import select

            type_pls = await self.db.execute(
                select(ProductLine.code).where(ProductLine.product_type_code == product_type_code)
            )
            codes = [r[0] for r in type_pls.fetchall()]
            if codes:
                filters.append("product_line_code = ANY(:product_type_codes)")
                params["product_type_codes"] = codes
            else:
                filters.append("1 = 0")

        # Pre-filter by accessible modules
        accessible_modules = []
        for entity_type, module in ENTITY_MODULE_MAP.items():
            level = await get_user_permission(user, module, self.db)
            if level >= PermissionLevel.VIEW:
                accessible_modules.append(entity_type)
        if not accessible_modules:
            elapsed = int((time.monotonic() - start) * 1000)
            return SemanticSearchResponse(results=[], total=0, query_time_ms=elapsed)

        if entity_types:
            allowed = [t for t in entity_types if t in accessible_modules]
        else:
            allowed = accessible_modules
        if not allowed:
            elapsed = int((time.monotonic() - start) * 1000)
            return SemanticSearchResponse(results=[], total=0, query_time_ms=elapsed)

        filters.append("entity_type = ANY(:entity_types)")
        params["entity_types"] = allowed

        where_clause = " AND ".join(filters) if filters else "TRUE"

        # Vector search
        vector_results = []
        if self.embedding:
            query_vector = await self.embedding.embed([query])
            if query_vector:
                vec_str = "[" + ",".join(str(v) for v in query_vector[0]) + "]"
                params["query_vector"] = vec_str
                result = await self.db.execute(
                    text(f"""
                        SELECT id, entity_type, entity_id, node_id, entity_field,
                               chunk_text, product_line_code, metadata,
                               1 - (embedding <=> CAST(:query_vector AS vector)) AS score
                        FROM document_embeddings
                        WHERE {where_clause}
                        ORDER BY embedding <=> CAST(:query_vector AS vector)
                        LIMIT :fetch_limit
                    """),
                    params,
                )
                vector_results = [dict(row._mapping) for row in result.fetchall()]

        # Fulltext search
        fulltext_results = []
        try:
            result = await self.db.execute(
                text(f"""
                    SELECT id, entity_type, entity_id, node_id, entity_field,
                           chunk_text, product_line_code, metadata,
                           ts_rank(tsv, query) AS score
                    FROM document_embeddings,
                         plainto_tsquery('zhcfg', :query) query
                    WHERE tsv @@ query AND {where_clause}
                    ORDER BY ts_rank(tsv, query) DESC
                    LIMIT :fetch_limit
                """),
                {**params, "query": query},
            )
            fulltext_results = [dict(row._mapping) for row in result.fetchall()]
        except Exception as e:
            logger.warning(f"Fulltext search failed (zhcfg may not be available): {e}")

        # RRF fusion
        vector_weight = settings.SEARCH_VECTOR_WEIGHT
        fulltext_weight = settings.SEARCH_FULLTEXT_WEIGHT
        k = 60

        scores: dict[str, float] = {}
        item_map: dict[str, dict] = {}

        for rank, item in enumerate(vector_results):
            item_id = str(item["id"])
            scores[item_id] = scores.get(item_id, 0) + vector_weight / (k + rank)
            item_map[item_id] = {**item, "source": "vector"}

        for rank, item in enumerate(fulltext_results):
            item_id = str(item["id"])
            scores[item_id] = scores.get(item_id, 0) + fulltext_weight / (k + rank)
            if item_id not in item_map:
                item_map[item_id] = {**item, "source": "fulltext"}
            else:
                item_map[item_id]["source"] = "hybrid"

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:limit]

        results = []
        for item_id in sorted_ids:
            item = item_map[item_id]
            item["score"] = round(scores[item_id], 4)
            results.append(SearchResultItem(**item))

        elapsed = int((time.monotonic() - start) * 1000)
        return SemanticSearchResponse(results=results, total=len(results), query_time_ms=elapsed)

    async def ask(
        self,
        question: str,
        user: User,
        product_line_code: str | None = None,
        product_type_code: str | None = None,
        max_context_chunks: int = 10,
    ) -> QAResponse:
        """RAG Q&A: search + LLM answer with citations."""
        start = time.monotonic()

        search_result = await self.semantic_search(
            query=question,
            user=user,
            product_line_code=product_line_code,
            product_type_code=product_type_code,
            limit=max_context_chunks,
        )

        if not search_result.results:
            elapsed = int((time.monotonic() - start) * 1000)
            return QAResponse(
                answer="未找到相关记录。",
                sources=[],
                llm_available=self.llm is not None,
                query_time_ms=elapsed,
            )

        sources = []
        for r in search_result.results:
            sources.append(QASource(
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                document_no=r.metadata.get("document_no", ""),
                chunk_text=r.chunk_text,
                relevance_score=r.score,
            ))

        if not self.llm:
            elapsed = int((time.monotonic() - start) * 1000)
            answer_parts = ["未配置 LLM，无法生成智能回答。以下是相关搜索结果：\n"]
            for i, s in enumerate(sources, 1):
                answer_parts.append(f"[{i}] {s.document_no} — {s.chunk_text[:100]}...")
            return QAResponse(
                answer="\n".join(answer_parts),
                sources=sources,
                llm_available=False,
                query_time_ms=elapsed,
            )

        context_parts = []
        for i, s in enumerate(sources, 1):
            context_parts.append(f"[{i}] ({s.entity_type}) {s.document_no}: {s.chunk_text}")
        context = "\n".join(context_parts)

        prompt = f"""你是一个质量管理系统助手。根据以下历史质量记录回答用户问题。

## 相关记录
{context}

## 用户问题
{question}

## 输出要求
请用中文回答。在回答中引用来源时使用 [1], [2] 等编号。
如果记录中没有相关信息，请如实说明。

**必须只返回以下 JSON 格式，不要添加任何其他文本、markdown 围栏或解释：**
{{"answer": "你的回答内容"}}"""

        try:
            rag_schema = {
                "type": "object",
                "properties": {
                    "answer": {"type": "string", "description": "基于上下文生成的回答，支持 markdown 格式"}
                },
                "required": ["answer"],
            }
            llm_response = await self.llm.complete(prompt=prompt, response_schema=rag_schema)
            answer = llm_response.get("answer", "生成回答失败。")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            answer = f"LLM 调用失败: {e}"

        elapsed = int((time.monotonic() - start) * 1000)
        return QAResponse(
            answer=answer,
            sources=sources,
            llm_available=True,
            query_time_ms=elapsed,
        )
