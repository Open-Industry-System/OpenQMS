from app.services.recommendation_types import RecommendationCandidate, RecommendationResult, StageRun


def test_stage_run_defaults():
    s = StageRun(index=3, name="semantic", source="semantic_search", status="done")
    assert s.hit_count == 0 and s.summary == "" and s.error is None
    assert s.llm_attempted is None and s.llm_succeeded is None and s.llm_failed is None


def test_to_d4_schema_emits_stage_index():
    c = RecommendationCandidate(source="fmea_graph", content="x", category=None, confidence=0.5,
                                 match_reason="r", metadata={"stage_index": 2, "failure_cause_node_id": "c1"})
    assert c.to_d4_schema()["stage_index"] == 2


def test_to_d5_suggestion_schema_emits_stage_index():
    c = RecommendationCandidate(source="rule_engine_measure", content="m", category="预防措施",
                                confidence=0.5, match_reason="r", metadata={"stage_index": 10})
    assert c.to_d5_suggestion_schema()["stage_index"] == 10
    assert c.to_d5_suggestion_schema()["match_source"] == "rule"


def test_recommendation_result_has_stages():
    r = RecommendationResult(items=[], stages=[StageRun(1, "ctx", "internal", "done")])
    assert len(r.stages) == 1
