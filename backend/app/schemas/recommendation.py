# backend/app/schemas/recommendation.py
from typing import Literal
from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    trigger_type: Literal[
        "failure_mode", "failure_effect", "failure_cause", "measure", "optimization"
    ]
    context: dict = Field(default_factory=dict)


class SuggestionItem(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: Literal["rule", "llm"] = "rule"
    explanation: str = ""


class RecommendResponse(BaseModel):
    suggestions: list[SuggestionItem]
    source: Literal["rule", "hybrid", "rule_fallback"]
    cached: bool = False
    llm_available: bool = False


class SuggestionList(BaseModel):
    """LLM 输出校验模型。"""
    suggestions: list[SuggestionItem]
