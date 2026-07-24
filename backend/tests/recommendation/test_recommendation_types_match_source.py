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


def test_d4_schema_exposes_risk_from_metadata():
    """FMEA 命中候选的 AP/S/O/D 从 metadata 流入 D4 响应字段。"""
    cand = RecommendationCandidate(
        source="fmea_graph", content="螺栓老化", category=None, confidence=0.6,
        match_reason="关联 FMEA 失效原因",
        metadata={"ap": "M", "severity": 8, "occurrence": 5, "detection": 3,
                  "failure_mode_node_id": "fm-1"},
    )
    s = cand.to_d4_schema()
    assert s["ap"] == "M"
    assert s["severity"] == 8
    assert s["occurrence"] == 5
    assert s["detection"] == 3


def test_d4_schema_rule_engine_fallback_ap_only():
    """规则引擎兜底候选仅 AP=M，S/O/D 留空（不臆造）。"""
    cand = RecommendationCandidate(
        source="rule_engine", content="零部件老化", category=None, confidence=0.25,
        match_reason="规则引擎推断", metadata={"ap": "M"},
    )
    s = cand.to_d4_schema()
    assert s["ap"] == "M"
    assert s["severity"] is None
    assert s["occurrence"] is None
    assert s["detection"] is None


def test_d5_suggestion_exposes_risk_from_metadata():
    cand = RecommendationCandidate(
        source="rule_engine_measure", content="优化设计参数", category="预防措施",
        confidence=0.33, match_reason="AP=M 规则建议",
        metadata={"basis": "AP=M", "ap": "M", "severity": 8, "occurrence": 5, "detection": 3},
    )
    s = cand.to_d5_suggestion_schema()
    assert s["ap"] == "M"
    assert s["severity"] == 8
    assert s["occurrence"] == 5
    assert s["detection"] == 3
