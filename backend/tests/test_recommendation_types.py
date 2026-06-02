from app.services.recommendation_types import RecommendationContext, RecommendationCandidate


def test_recommendation_context_creation():
    ctx = RecommendationContext(
        capa_data={"d2_description": "焊接虚焊"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
    )
    assert ctx.stage == "d4"
    assert ctx.fmea_docs is None


def test_recommendation_candidate_creation():
    c = RecommendationCandidate(
        source="fmea_graph",
        content="焊接参数偏移",
        category=None,
        confidence=0.6,
        match_reason="关联 FMEA 失效原因",
        metadata={"fmea_id": "abc"},
    )
    assert c.source == "fmea_graph"
    assert c.metadata["fmea_id"] == "abc"
