import pytest
from app.services.fusion_engine import FusionEngine
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext


class TestFusionEngine:
    def test_deduplicate_by_normalized_text(self):
        engine = FusionEngine()
        candidates = [
            RecommendationCandidate("semantic_search", "焊接虚焊", None, 0.7, "", {}),
            RecommendationCandidate("historical_capa", "焊接虚焊", None, 0.8, "", {}),
        ]
        ctx = RecommendationContext({"d2_description": ""}, None, "d4")
        result = engine.merge(candidates, ctx)
        assert len(result) == 1
        assert result[0].source == "historical_capa"  # higher confidence first

    def test_source_priority_applied(self):
        engine = FusionEngine()
        candidates = [
            RecommendationCandidate("rule_engine", "规则建议", None, 0.9, "", {}),
            RecommendationCandidate("fmea_graph", "图匹配", None, 0.6, "", {}),
        ]
        ctx = RecommendationContext({"d2_description": ""}, None, "d4")
        result = engine.merge(candidates, ctx)
        # fmea_graph priority 1.0 > rule_engine 0.5
        # 0.6 * 1.0 = 0.6 vs 0.9 * 0.5 = 0.45
        assert result[0].source == "fmea_graph"

    def test_product_line_bonus(self):
        engine = FusionEngine()
        candidates = [
            RecommendationCandidate("semantic_search", "A", None, 0.7, "", {"product_line_code": "DC-DC-100"}),
            RecommendationCandidate("semantic_search", "B", None, 0.7, "", {"product_line_code": "OTHER"}),
        ]
        ctx = RecommendationContext({"product_line_code": "DC-DC-100"}, None, "d4")
        result = engine.merge(candidates, ctx)
        # A: 0.7 * 0.7 + 0.05 = 0.54; B: 0.7 * 0.7 + 0 = 0.49
        assert result[0].content == "A"

    def test_cap_at_10(self):
        engine = FusionEngine()
        candidates = [
            RecommendationCandidate("rule_engine", f"item_{i}", None, 0.5, "", {})
            for i in range(15)
        ]
        ctx = RecommendationContext({}, None, "d4")
        result = engine.merge(candidates, ctx)
        assert len(result) == 10

    def test_severity_bonus(self):
        engine = FusionEngine()
        candidates = [
            RecommendationCandidate("semantic_search", "A", None, 0.7, "", {"severity": "严重"}),
            RecommendationCandidate("semantic_search", "B", None, 0.7, "", {"severity": "轻微"}),
        ]
        ctx = RecommendationContext({"severity": "严重"}, None, "d4")
        result = engine.merge(candidates, ctx)
        # A: 0.7 * 0.7 + 0.03 = 0.52; B: 0.7 * 0.7 + 0 = 0.49
        assert result[0].content == "A"

    def test_confidence_cap_at_095(self):
        engine = FusionEngine()
        candidates = [
            RecommendationCandidate("fmea_graph", "A", None, 1.0, "", {}),
        ]
        ctx = RecommendationContext({}, None, "d4")
        result = engine.merge(candidates, ctx)
        assert result[0].confidence == 0.95

    def test_unknown_source_fallback_priority(self):
        engine = FusionEngine()
        candidates = [
            RecommendationCandidate("unknown_source", "A", None, 0.8, "", {}),
        ]
        ctx = RecommendationContext({}, None, "d4")
        result = engine.merge(candidates, ctx)
        # 0.8 * 0.5 (unknown fallback) + 0.05 (None==None product_line) + 0.03 (None==None severity) = 0.48
        assert result[0].confidence == 0.48

    def test_does_not_mutate_original_candidates(self):
        engine = FusionEngine()
        original = RecommendationCandidate("fmea_graph", "A", None, 0.6, "", {})
        candidates = [original]
        ctx = RecommendationContext({}, None, "d4")
        engine.merge(candidates, ctx)
        assert original.confidence == 0.6
