# backend/tests/test_recommendation_observability_schema.py
from app.schemas.recommendation import (
    ContextExecution, GenerationExecution, RecommendResponse,
    SourceExecution, SuggestionItem, compute_recommendation_id,
)


def test_source_execution_status_enum():
    SourceExecution(source="graph", status="success", hit_count=3, latency_ms=12)
    for ok in ("success", "empty", "unavailable", "error"):
        SourceExecution(source="semantic_search", status=ok)
    import pytest
    with pytest.raises(Exception):
        SourceExecution(source="graph", status="bogus")


def test_suggestion_item_source_widened_and_recommendation_id():
    for s in ("rule", "graph", "semantic_search", "lessons_learned", "llm"):
        item = SuggestionItem(name="x", confidence=0.5, source=s)
        assert item.source == s
        assert item.recommendation_id is None  # default until stamped
    item2 = SuggestionItem(name="x", confidence=0.5, source="llm", recommendation_id="rec_1")
    assert item2.recommendation_id == "rec_1"


def test_recommend_response_has_observability_fields():
    r = RecommendResponse(
        suggestions=[], source="hybrid",
        source_executions=[SourceExecution(source="graph", status="empty")],
        context_execution=ContextExecution(current_product_structure="assembled"),
        generation_execution=GenerationExecution(llm="success"),
    )
    assert r.source_executions[0].source == "graph"
    assert r.context_execution.current_product_structure == "assembled"
    assert r.generation_execution.llm == "success"
    r2 = RecommendResponse(suggestions=[], source="rule")
    assert r2.source_executions == []
    assert r2.generation_execution.llm == "unavailable"


def test_compute_recommendation_id_deterministic_and_scoped():
    a = compute_recommendation_id("failure_mode", "焊接", "电流不足", "graph")
    b = compute_recommendation_id("failure_mode", "焊接", "电流不足", "graph")
    c = compute_recommendation_id("failure_mode", "焊接", "电流不足", "llm")
    d = compute_recommendation_id("failure_mode", "焊接", "电压不足", "graph")
    assert a == b                      # deterministic
    assert a.startswith("rec_") and len(a) == 16
    assert a != c                      # source is part of the hash
    assert a != d                      # name is part of the hash
