from app.models.recommendation_cache import RecommendationCache


def test_recommendation_cache_has_stage_runs_column():
    col = RecommendationCache.__table__.columns.get("stage_runs")
    assert col is not None
    assert col.nullable is True
