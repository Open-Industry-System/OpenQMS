import hashlib
from typing import Literal

from pydantic import BaseModel, Field


def compute_recommendation_id(trigger_type: str, anchor: str, name: str, source: str) -> str:
    """Deterministic content-hash id for a suggestion. Idempotent across re-fetch
    of the same suggestion; distinct across source/name. Suggestions are transient
    (not persisted), so a content hash — not a DB id — is the natural key for
    adoption-audit dedupe. Zero migration."""
    raw = f"{trigger_type}|{anchor}|{name}|{source}"
    return "rec_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


class RecommendRequest(BaseModel):
    trigger_type: Literal[
        "failure_mode", "failure_effect", "failure_cause", "measure", "optimization",
        "dfmea_tool", "dfmea_trend",
        "pfmea_tool", "pfmea_trend",
        "prevention_control", "detection_control",
    ]
    context: dict = Field(default_factory=dict)
    scope: Literal["global", "current_product_type", "current_product_line"] = "global"
    include_graph: bool = True


class SuggestionItem(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["rule", "graph", "semantic_search", "lessons_learned", "llm"] = "rule"
    recommendation_id: str | None = None  # backend-stamped content hash (Phase-1 Task P1.4)
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


class SourceExecution(BaseModel):
    source: str
    status: Literal["success", "empty", "unavailable", "error"]
    hit_count: int = 0
    latency_ms: int = 0


class ContextExecution(BaseModel):
    current_product_structure: Literal["assembled", "unavailable"] = "assembled"


class GenerationExecution(BaseModel):
    llm: Literal["success", "unavailable", "error"] = "unavailable"


class RecommendResponse(BaseModel):
    suggestions: list[SuggestionItem]
    source: Literal["rule", "graph", "hybrid", "rule_fallback", "graph_enriched"]
    cached: bool = False
    llm_available: bool = False
    graph_match_count: int = 0
    effective_scope: Literal["global", "current_product_type", "current_product_line"] = "global"
    source_executions: list[SourceExecution] = Field(default_factory=list)
    context_execution: ContextExecution = Field(default_factory=ContextExecution)
    generation_execution: GenerationExecution = Field(default_factory=GenerationExecution)


class SuggestionList(BaseModel):
    """LLM 输出校验模型。"""
    suggestions: list[SuggestionItem]


# --- 独立调试端点 schema ---

class SimilarNodesRequest(BaseModel):
    node_type: str
    query_text: str
    scope: Literal["global", "current_product_type", "current_product_line"] = "global"
    product_line_code: str | None = None   # now optional; codes resolved server-side
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
    effective_scope: Literal["global", "current_product_type", "current_product_line"] = "global"
