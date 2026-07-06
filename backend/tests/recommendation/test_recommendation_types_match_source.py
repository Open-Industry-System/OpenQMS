from app.services.recommendation_types import RecommendationCandidate


def _cand(source: str) -> RecommendationCandidate:
    return RecommendationCandidate(
        source=source, content="x", category="预防措施",
        confidence=0.5, match_reason="r", metadata={},
    )


def test_d5_suggestion_rule_engine_measure_maps_to_rule():
    s = _cand("rule_engine_measure").to_d5_suggestion_schema()
    assert s["match_source"] == "rule"


def test_d5_suggestion_historical_capa_keeps_source():
    s = _cand("historical_capa").to_d5_suggestion_schema()
    assert s["match_source"] == "historical_capa"
    assert s["source_capa_id"] is None  # metadata 无 historical_capa_id


def test_d5_suggestion_semantic_search_emits_source():
    s = _cand("semantic_search").to_d5_suggestion_schema()
    assert s["match_source"] == "semantic_search"
