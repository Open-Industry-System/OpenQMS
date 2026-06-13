from typing import Any

from pydantic import BaseModel, Field


class LessonsLearnedRequest(BaseModel):
    """POST /api/{module}/{id}/lessons-learned request body."""
    problem_description: str | None = Field(
        default=None,
        description="Optional problem description for better matching. Falls back to document title if empty.",
    )


class LessonCard(BaseModel):
    """Single lesson learned card."""
    id: str
    title: str
    summary: str
    source_type: str  # "fmea" | "capa" | "audit"
    source_document_no: str
    source_id: str
    source_product_line: str
    same_product_line: bool
    confidence: float = Field(ge=0.0, le=1.0)
    match_reason: str
    root_cause: str | None = None
    action: str | None = None
    severity: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # audit_id, audit_category, etc.


class LessonCategories(BaseModel):
    """Categorized lessons by source type."""
    fmea: list[LessonCard]
    capa: list[LessonCard]
    audit: list[LessonCard]


class LessonsLearnedResponse(BaseModel):
    """POST /api/{module}/{id}/lessons-learned response."""
    highlights: list[LessonCard]
    categories: LessonCategories
    source: str  # e.g. "historical_fmea + semantic_search + historical_capa"
    cached: bool = False
