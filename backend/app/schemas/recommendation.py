from typing import Literal
from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    trigger_type: Literal[
        "failure_mode", "failure_effect", "failure_cause", "measure", "optimization"
    ]
    context: dict = Field(default_factory=dict)
    scope: Literal["global", "current_product_line"] = "global"
    include_graph: bool = True


class SuggestionItem(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["rule", "graph", "llm"] = "rule"
    explanation: str = ""
    # 来源文档标注（仅 source == "graph" 时填充）
    source_fmea_id: str | None = None
    source_document_no: str | None = None
    source_product_line_code: str | None = None
    source_product_line_name: str | None = None
    source_node_type: str | None = None
    source_node_id: str | None = None
    similarity_score: float | None = None
    match_reason: str | None = None


class RecommendResponse(BaseModel):
    suggestions: list[SuggestionItem]
    source: Literal["rule", "graph", "hybrid", "rule_fallback", "graph_enriched"]
    cached: bool = False
    llm_available: bool = False
    graph_match_count: int = 0
    effective_scope: Literal["global", "current_product_line"] = "global"


class SuggestionList(BaseModel):
    """LLM 输出校验模型。"""
    suggestions: list[SuggestionItem]


# --- 独立调试端点 schema ---

class SimilarNodesRequest(BaseModel):
    node_type: str
    query_text: str
    scope: Literal["global", "current_product_line"] = "global"
    product_line_code: str
    limit: int = Field(10, ge=1, le=100)
    min_similarity: float = Field(0.3, ge=0.0, le=1.0)


class SimilarNodeMatch(BaseModel):
    node_id: str
    name: str
    node_type: str
    fmea_id: str
    document_no: str
    product_line_code: str | None = None
    product_line_name: str | None = None
    similarity_score: float
    match_reason: str


class SimilarNodesResponse(BaseModel):
    matches: list[SimilarNodeMatch]
    total: int
    effective_scope: Literal["global", "current_product_line"] = "global"
