import os
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest

from app.api.fmea import _recommend_anchor


class TestRecommendAnchor:
    def test_failure_mode_uses_function_description(self):
        assert _recommend_anchor("failure_mode", {"function_description": "电压采集"}) == "电压采集"

    def test_failure_mode_falls_back_to_input_text(self):
        assert _recommend_anchor("failure_mode", {"input_text": "采集"}) == "采集"

    def test_empty_stored_key_does_not_gate_other_filled_field(self):
        # 空的 function_description 不能挡住已填的 input_text（`or` 链式回退）
        assert _recommend_anchor("failure_mode", {"function_description": "", "input_text": "采集"}) == "采集"

    def test_dfmea_tool_uses_task(self):
        assert _recommend_anchor("dfmea_tool", {"task": "分析DC-DC转换器"}) == "分析DC-DC转换器"

    def test_dfmea_trend_falls_back_to_title(self):
        assert _recommend_anchor("dfmea_trend", {"fmea_title": "DC-DC转换器设计FMEA"}) == "DC-DC转换器设计FMEA"

    def test_dfmea_tool_falls_back_to_team(self):
        assert _recommend_anchor("dfmea_tool", {"team": "质量小组"}) == "质量小组"

    def test_dfmea_trigger_input_text_last_resort(self):
        assert _recommend_anchor("dfmea_trend", {"input_text": "客户投诉"}) == "客户投诉"

    def test_dfmea_tool_empty_when_no_context(self):
        assert _recommend_anchor("dfmea_tool", {}) == ""

    def test_other_trigger_uses_failure_mode(self):
        assert _recommend_anchor("failure_effect", {"failure_mode": "焊缝气孔"}) == "焊缝气孔"

    def test_other_trigger_empty_when_no_failure_mode(self):
        assert _recommend_anchor("optimization", {}) == ""
from app.services.recommendation_service import RecommendationService


class StubGraphRepo:
    async def find_similar_nodes_advanced(self, **kwargs):
        return []

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


class TestBuildPromptForToolTrend:
    def _svc(self):
        return RecommendationService(db=None, llm_provider=None, graph_repo=StubGraphRepo())

    def test_tool_template_fills_placeholders(self):
        prompt = self._svc()._build_prompt("dfmea_tool", {
            "fmea_title": "DC-DC转换器设计FMEA",
            "product_line_code": "DC-DC-100",
            "task": "分析电压采集功能",
            "team": "质量小组",
        })
        assert "DC-DC转换器设计FMEA" in prompt
        assert "DC-DC-100" in prompt
        assert "分析电压采集功能" in prompt
        assert "质量小组" in prompt
        # 无残留占位符
        assert "{fmea_title}" not in prompt
        assert "{task}" not in prompt
        assert "{product_line_code}" not in prompt
        assert "{team}" not in prompt

    def test_trend_template_fills_placeholders(self):
        prompt = self._svc()._build_prompt("dfmea_trend", {
            "fmea_title": "DC-DC转换器设计FMEA",
            "product_line_code": "DC-DC-100",
            "task": "分析电压采集功能",
        })
        assert "DC-DC转换器设计FMEA" in prompt
        assert "DC-DC-100" in prompt
        assert "分析电压采集功能" in prompt
        assert "{fmea_title}" not in prompt
        assert "{task}" not in prompt
        assert "{product_line_code}" not in prompt

    def test_missing_context_does_not_raise_and_keeps_body(self):
        # _SafeDict 对缺失键返回 ""，不得抛 KeyError
        prompt = self._svc()._build_prompt("dfmea_tool", {})
        assert "分析工具" in prompt  # 模板正文仍在
        assert "{task}" not in prompt


# --- recommend() 集成：验证新 trigger 走完整链路 + source 分支（spec §9） ---
# 通过 monkeypatch 绕过 db（_get_fmea_or_404 / _get_cached / _assemble_context /
# _cache_result）与权限（get_user_permission），直接驱动 recommend() 逻辑。
# RuleEngine.evaluate 对未知 trigger 返回空、quality="generic"（已核实
# recommendation_service.py:138-140），不抛异常，故无需 patch rules。
from unittest.mock import AsyncMock
import uuid as _uuid

from app.schemas.recommendation import RecommendRequest
from app.core.permissions import PermissionLevel
from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope


class _StubFmea:
    def __init__(self):
        self.id = _uuid.uuid4()
        self.product_line_code = "DC-DC-100"
        self.fmea_type = "DFMEA"
        self.title = "DC-DC转换器设计FMEA"
        self.factory_id = _uuid.uuid4()


class _OkLlm:
    async def complete(self, prompt, kwargs):
        return {"suggestions": [{"name": "边界图", "confidence": 0.85, "explanation": "适合结构分析"}]}


class _ThrowLlm:
    async def complete(self, prompt, kwargs):
        raise RuntimeError("llm boom")


def _stub_request_scope(user):
    """Minimal RequestScope with full access — resolver is patched, so values are not exercised."""
    return RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=None),
        effective_factory_id=None,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=user,
    )


class TestRecommendIntegrationForToolTrend:
    """dfmea_tool/trend 真正走完 recommend()：规则→（可选）LLM→source 分支。"""

    def _svc(self, llm):
        return RecommendationService(db=None, llm_provider=llm, graph_repo=StubGraphRepo())

    def _patch(self, svc, monkeypatch):
        fmea = _StubFmea()
        monkeypatch.setattr(svc, "_get_fmea_or_404", AsyncMock(return_value=fmea))
        monkeypatch.setattr(svc, "_get_cached", AsyncMock(return_value=None))
        monkeypatch.setattr(svc, "_assemble_context", AsyncMock(return_value={}))
        monkeypatch.setattr(svc, "_cache_result", AsyncMock())
        monkeypatch.setattr(
            "app.core.permissions.get_user_permission",
            AsyncMock(return_value=PermissionLevel.VIEW),
        )
        # recommend() now resolves scope -> codes via the resolver (Task 6);
        # patch it so these DB-free tests don't touch a real session.
        monkeypatch.setattr(
            "app.services.recommendation_scope.resolve_product_line_codes",
            AsyncMock(return_value=["DC-DC-100"]),
        )
        return fmea

    async def test_dfmea_tool_with_llm_returns_suggestions(self, monkeypatch):
        svc = self._svc(_OkLlm())
        fmea = self._patch(svc, monkeypatch)
        req = RecommendRequest(
            trigger_type="dfmea_tool",
            context={"task": "分析DC-DC转换器", "fmea_title": fmea.title},
            scope="current_product_line",
            include_graph=False,
        )
        user = object()
        res = await svc.recommend(fmea.id, req, user, _stub_request_scope(user))
        assert any(s.name == "边界图" for s in res.suggestions)
        assert res.source in ("hybrid", "graph_enriched")

    async def test_dfmea_tool_no_llm_returns_empty_with_source_rule(self, monkeypatch):
        svc = self._svc(None)
        fmea = self._patch(svc, monkeypatch)
        req = RecommendRequest(
            trigger_type="dfmea_tool",
            context={"task": "分析DC-DC转换器"},
            scope="current_product_line",
            include_graph=False,
        )
        user = object()
        res = await svc.recommend(fmea.id, req, user, _stub_request_scope(user))
        assert res.suggestions == []
        assert res.source == "rule"

    async def test_dfmea_trend_llm_failure_returns_rule_fallback(self, monkeypatch):
        svc = self._svc(_ThrowLlm())
        fmea = self._patch(svc, monkeypatch)
        req = RecommendRequest(
            trigger_type="dfmea_trend",
            context={"task": "分析DC-DC转换器"},
            scope="current_product_line",
            include_graph=False,
        )
        user = object()
        res = await svc.recommend(fmea.id, req, user, _stub_request_scope(user))
        assert res.source == "rule_fallback"
