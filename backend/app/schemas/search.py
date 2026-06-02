"""Pydantic schemas for semantic search and RAG Q&A."""
import uuid
from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    node_id: str | None = None
    entity_field: str
    chunk_text: str
    score: float
    source: str  # "vector" | "fulltext" | "hybrid"
    metadata: dict = {}
    product_line_code: str | None = None


class SemanticSearchResponse(BaseModel):
    results: list[SearchResultItem]
    total: int
    query_time_ms: int


class QASource(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    document_no: str = ""
    chunk_text: str
    relevance_score: float


class QAResponse(BaseModel):
    answer: str
    sources: list[QASource]
    llm_available: bool
    query_time_ms: int


class QARequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    product_line_code: str | None = None
    max_context_chunks: int = Field(default=10, ge=1, le=20)


class ReindexResponse(BaseModel):
    message: str
    enqueued: int
