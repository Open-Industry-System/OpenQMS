import os
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
import uuid

from app.services.recommendation_service import RecommendationService, RuleEngine
from app.schemas.recommendation import RecommendRequest, SuggestionItem


class StubGraphRepo:
    async def find_similar_nodes_advanced(self, **kwargs):
        return [
            {
                "node_id": "fm_001",
                "name": "焊接虚焊",
                "type": "FailureMode",
                "fmea_id": str(uuid.uuid4()),
                "document_no": "PFMEA-2026-001",
                "product_line_code": "DC-DC-100",
                "product_line_name": "DC-DC 电源模块",
                "similarity_score": 0.75,
                "match_reason": "substring_match",
            }
        ]

    async def get_impact_chain(self, *a, **kw):
        return {"nodes": [], "edges": []}

    async def get_cause_chain(self, *a, **kw):
        return {"nodes": [], "edges": []}

    async def get_cross_fmea_stats(self, *a, **kw):
        return {}

    async def get_global_stats(self):
        return {}

    async def analyze_change_impact(self, *a, **kw):
        from app.schemas.change_impact import ChangeImpactResult, ImpactSummary
        return ChangeImpactResult(affected_nodes=[], summary=ImpactSummary(
            total_affected=0, failure_modes_affected=0, controls_affected=0,
            ap_upgraded_count=0, max_hop_distance=0,
        ))


def test_merge_and_deduplicate_prefers_higher_confidence():
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    a = [SuggestionItem(name="焊接不良", confidence=0.7, source="rule")]
    b = [SuggestionItem(name="焊接不良", confidence=0.85, source="graph")]
    result = svc._merge_and_deduplicate(a, b)
    assert len(result) == 1
    assert result[0].source == "graph"
    assert result[0].confidence == 0.85


def test_merge_and_deduplicate_graph_wins_on_tie():
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    a = [SuggestionItem(name="A", confidence=0.7, source="rule")]
    b = [SuggestionItem(name="A", confidence=0.7, source="graph")]
    result = svc._merge_and_deduplicate(a, b)
    assert result[0].source == "graph"


def test_graph_matches_to_suggestions():
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    matches = [
        {
            "node_id": "n1",
            "name": "焊接不良",
            "type": "FailureMode",
            "fmea_id": "f1",
            "document_no": "PFMEA-001",
            "product_line_code": "DC-DC-100",
            "product_line_name": "DC-DC",
            "similarity_score": 0.75,
            "match_reason": "substring_match",
        }
    ]
    items = svc._graph_matches_to_suggestions(matches, "DC-DC-100")
    assert len(items) == 1
    assert items[0].name == "焊接不良"
    assert items[0].source == "graph"
    assert items[0].confidence == 0.88  # round(0.5 + 0.75 * 0.5, 2)
    assert items[0].source_document_no == "PFMEA-001"


def test_rule_engine_failure_mode():
    engine = RuleEngine()
    result = engine.evaluate("failure_mode", {"function_description": "采集数据"})
    assert len(result.suggestions) > 0
    assert result.quality == "specific"


def test_rule_engine_generic_fallback():
    engine = RuleEngine()
    result = engine.evaluate("failure_mode", {"function_description": "未知操作"})
    assert len(result.suggestions) == 4
    assert result.quality == "generic"


def test_graph_matches_to_suggestions_with_parent_node():
    """neighbor_match 结果 explanation 应包含父节点名称。"""
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    matches = [{
        "node_id": "n1", "name": "密封件老化", "type": "FailureCause",
        "fmea_id": "f1", "document_no": "PFMEA-001",
        "product_line_code": "DC-DC-100", "product_line_name": "DC-DC",
        "similarity_score": 0.75, "match_reason": "substring_match_neighbor",
        "parent_node_name": "密封失效",
    }]
    items = svc._graph_matches_to_suggestions(matches, "DC-DC-100")
    assert "密封失效" in items[0].explanation
    assert items[0].source_node_type == "FailureCause"


def test_need_llm_generic_quality_with_four_suggestions():
    """generic rule 返回 4 条建议时，LLM 仍应被调用（防止条件回退到 len < 3 单一路径）。"""
    assert RecommendationService._need_llm(
        llm_available=True,
        has_specific=False,
        suggestion_count=4,
        rule_quality="generic",
    ) is True


def test_need_llm_len_threshold_without_generic():
    """非 generic + 4 条建议时，不调用 LLM。"""
    assert RecommendationService._need_llm(
        llm_available=True,
        has_specific=False,
        suggestion_count=4,
        rule_quality="specific",
    ) is False


def test_need_llm_no_llm_available():
    """LLM 不可用时，不调用。"""
    assert RecommendationService._need_llm(
        llm_available=False,
        has_specific=False,
        suggestion_count=1,
        rule_quality="generic",
    ) is False


def test_need_llm_has_specific_suggestions():
    """已有针对性(specific)高置信建议时，不调用 LLM。"""
    assert RecommendationService._need_llm(
        llm_available=True,
        has_specific=True,
        suggestion_count=1,
        rule_quality="specific",
    ) is False


def test_need_llm_generic_quality_calls_llm_despite_high_confidence():
    """规则质量为 generic（未针对具体失效模式，如 measure/optimization 的 AP 分级
    通用模板）时，即便 confidence≥0.6(has_specific) 也应调用 LLM 给出针对性建议。"""
    assert RecommendationService._need_llm(
        llm_available=True,
        has_specific=True,
        suggestion_count=7,
        rule_quality="generic",
    ) is True
