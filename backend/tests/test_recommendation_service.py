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


def test_default_llm_timeout_covers_normal_provider_latency(monkeypatch):
    """FMEA recommendations should not time out normal OpenAI-compatible calls.

    Ark/DeepSeek-compatible endpoints commonly take around 9s for the FMEA
    JSON prompt; the default must leave enough room or the UI falls back to
    "AI 建议暂不可用" despite a configured provider.
    """
    monkeypatch.setattr("app.services.recommendation_service.settings.LLM_TIMEOUT", 5)

    svc = RecommendationService(db=None, llm_provider=object(), graph_repo=StubGraphRepo())

    assert svc.llm_timeout >= 15


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


def test_recommend_request_accepts_new_triggers():
    """RecommendRequest schema 接受新 trigger_type；service 不抛未路由错误。"""
    req = RecommendRequest(trigger_type="prevention_control", context={"failure_mode": "采集数据失效", "ap": "H"})
    assert req.trigger_type == "prevention_control"
    engine = RuleEngine()
    result = engine.evaluate(req.trigger_type, req.context)
    assert len(result.suggestions) > 0


def test_rule_engine_prevention_control_returns_only_prevention():
    """prevention_control trigger 必须只返回预防项，不混入探测项。"""
    engine = RuleEngine()
    result = engine.evaluate("prevention_control", {"failure_mode": "采集数据失效", "ap": "H"})
    assert len(result.suggestions) > 0
    # 预防项 explanation 标注「预防措施」；不得出现检测专属词
    for s in result.suggestions:
        assert "预防" in s.explanation
    detection_only_keywords = ["在线实时监测", "自诊断功能", "出厂100%功能测试", "传感器信号校验", "气密性测试", "接触电阻测试"]
    names = [s.name for s in result.suggestions]
    for kw in detection_only_keywords:
        assert kw not in names, f"探测项 {kw} 不应出现在 prevention_control 结果中"


def test_rule_engine_detection_control_returns_only_detection():
    """detection_control trigger 必须只返回探测项。"""
    engine = RuleEngine()
    result = engine.evaluate("detection_control", {"failure_mode": "采集数据失效", "ap": "H"})
    assert len(result.suggestions) > 0
    for s in result.suggestions:
        assert "检测" in s.explanation or "探测" in s.explanation
    prevention_only_keywords = ["冗余设计", "降额设计", "失效安全设计", "传感器冗余布置", "信号滤波设计", "双重密封结构", "防松结构设计"]
    names = [s.name for s in result.suggestions]
    for kw in prevention_only_keywords:
        assert kw not in names, f"预防项 {kw} 不应出现在 detection_control 结果中"


def test_rule_engine_measure_still_returns_mixed():
    """旧 measure trigger 行为不变：仍返回预防+探测混合。"""
    engine = RuleEngine()
    result = engine.evaluate("measure", {"failure_mode": "采集数据失效", "ap": "H"})
    assert len(result.suggestions) > 0
    explanations = " ".join(s.explanation for s in result.suggestions)
    assert "预防" in explanations
    assert "检测" in explanations


def test_extract_neighbors_prevention_control_only_prevented_by():
    """prevention_control 图谱增强只取 PREVENTED_BY 邻居，不含 DETECTED_BY。"""
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    match = {
        "node_id": "fm1", "fmea_id": str(uuid.uuid4()),
    }
    # StubGraphRepo 不提供 graph_data；直接测 _extract_neighbors_from_match 的边逻辑
    # 需要注入 graph_data。改用最小桩：覆写 _get_graph_data_by_fmea_id。
    async def fake_graph_data(_fmea_id):
        return {
            "nodes": [
                {"id": "fm1", "type": "FailureMode", "name": "m"},
                {"id": "fc1", "type": "FailureCause", "name": "c"},
                {"id": "pc1", "type": "PreventionControl", "name": "预防A"},
                {"id": "dc1", "type": "DetectionControl", "name": "探测B"},
            ],
            "edges": [
                {"source": "fc1", "target": "fm1", "type": "CAUSE_OF"},
                {"source": "fc1", "target": "pc1", "type": "PREVENTED_BY"},
                {"source": "fc1", "target": "dc1", "type": "DETECTED_BY"},
            ],
        }
    svc._get_graph_data_by_fmea_id = fake_graph_data  # type: ignore[method-assign]

    import asyncio
    nodes = asyncio.get_event_loop().run_until_complete(
        svc._extract_neighbors_from_match(match, "prevention_control")
    )
    names = [n["name"] for n in nodes]
    assert "预防A" in names
    assert "探测B" not in names


def test_extract_neighbors_detection_control_only_detected_by():
    """detection_control 图谱增强只取 DETECTED_BY 邻居。"""
    svc = RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())
    match = {"node_id": "fm1", "fmea_id": str(uuid.uuid4())}
    async def fake_graph_data(_fmea_id):
        return {
            "nodes": [
                {"id": "fm1", "type": "FailureMode", "name": "m"},
                {"id": "fc1", "type": "FailureCause", "name": "c"},
                {"id": "pc1", "type": "PreventionControl", "name": "预防A"},
                {"id": "dc1", "type": "DetectionControl", "name": "探测B"},
            ],
            "edges": [
                {"source": "fc1", "target": "fm1", "type": "CAUSE_OF"},
                {"source": "fc1", "target": "pc1", "type": "PREVENTED_BY"},
                {"source": "fc1", "target": "dc1", "type": "DETECTED_BY"},
            ],
        }
    svc._get_graph_data_by_fmea_id = fake_graph_data  # type: ignore[method-assign]

    import asyncio
    nodes = asyncio.get_event_loop().run_until_complete(
        svc._extract_neighbors_from_match(match, "detection_control")
    )
    names = [n["name"] for n in nodes]
    assert "探测B" in names
    assert "预防A" not in names
