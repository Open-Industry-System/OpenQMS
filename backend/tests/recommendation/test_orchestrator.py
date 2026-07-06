import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.recommendation_orchestrator import RecommendationOrchestrator, STAGE_PLAN
from app.services.recommendation_types import RecommendationContext


def _ctx(stage="d4", linked_fmea=None):
    return RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "d4_root_cause": "", "fmea_ref_id": None,
                   "fmea_node_id": None, "product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"], stage=stage, fmea_docs=[], linked_fmea=linked_fmea)


@pytest.mark.asyncio
async def test_stages_exactly_12_unique_indexes(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), None, None)
    # stub sources to return [] so all done(0)/skipped
    result = await orch.run(_ctx(), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    assert len(result.stages) == 12
    assert {s.index for s in result.stages} == set(range(1, 13))


@pytest.mark.asyncio
async def test_fusion_before_llm_order(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)
    # FusionEngine.merge is sync; use MagicMock (not AsyncMock) so it returns [] not a coroutine
    merge_spy = MagicMock(return_value=[])
    orch.fusion.merge = merge_spy
    enrich_spy = AsyncMock()
    from app.services.llm_fusion_layer import LLMOutcome
    enrich_spy.return_value = LLMOutcome(candidates=[], attempted=0)
    orch.llm_layer.enrich = enrich_spy
    await orch.run(_ctx(), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    # enrich 收到 merge 的输出（[]），不是 raw 召回 — 顺序 fusion→LLM
    assert enrich_spy.await_args.args[0] == []


@pytest.mark.asyncio
async def test_llm_all_failed_is_error(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)
    from app.services.llm_fusion_layer import LLMOutcome
    orch.llm_layer.enrich = AsyncMock(return_value=LLMOutcome(candidates=[], attempted=2, succeeded=0, failed=2))
    result = await orch.run(_ctx(), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s11 = next(s for s in result.stages if s.index == 11)
    assert s11.status == "error" and s11.llm_attempted == 2


@pytest.mark.asyncio
async def test_llm_exception_isolated(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)
    orch.llm_layer.enrich = AsyncMock(side_effect=RuntimeError("boom"))
    result = await orch.run(_ctx(), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s11 = next(s for s in result.stages if s.index == 11)
    assert s11.status == "error" and s11.llm_attempted == 0
    assert len(result.stages) == 12  # stage 12 仍发射


@pytest.mark.asyncio
async def test_d5_stage2_skipped_when_no_cause(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), None, None)
    result = await orch.run(_ctx(stage="d5"), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s2 = next(s for s in result.stages if s.index == 2)
    assert s2.status == "skipped"


@pytest.mark.asyncio
async def test_per_stage_protocol_violation_is_error(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), None, None)
    # 让某新源（注册后）should_skip 不存在 — 通过 _sources 注入坏源
    bad = MagicMock()
    # MagicMock 删除属性后 getattr 返回 None（不会自动重建），借此测试缺失 should_skip 路径
    del bad.should_skip  # ensure missing
    orch._sources["spc_anomaly"] = bad
    result = await orch.run(_ctx(), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s6 = next(s for s in result.stages if s.index == 6)
    assert s6.status == "error"
