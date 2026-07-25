from app.services.recommendation_types import StageRun, RecommendationResult


def test_stage_run_accepts_blocked_status():
    sr = StageRun(index=11, name="LLM 融合", source="llm", status="blocked",
                  hit_count=0, summary="未配置 LLM 凭证")
    assert sr.status == "blocked"


def test_recommendation_result_default_not_blocked():
    r = RecommendationResult(items=[])
    assert r.blocked is False


def test_recommendation_result_blocked_flag():
    r = RecommendationResult(items=[], stages=[StageRun(1, "上下文", "internal", "done")], blocked=True)
    assert r.blocked is True


from app.schemas.recommendation_stage import StageRunSchema
import pytest


def test_stage_run_schema_accepts_blocked():
    s = StageRunSchema(index=11, name="LLM", source="llm", status="blocked",
                      hit_count=0, summary="x")
    assert s.status == "blocked"


def test_stage_run_schema_rejects_unknown_status():
    with pytest.raises(Exception):
        StageRunSchema(index=11, name="LLM", source="llm", status="bogus",
                      hit_count=0, summary="x")
