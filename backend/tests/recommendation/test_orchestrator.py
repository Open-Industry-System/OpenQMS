import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.recommendation_orchestrator import RecommendationOrchestrator, STAGE_PLAN
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext


def _ctx(stage="d4", linked_fmea=None):
    return RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "d4_root_cause": "", "fmea_ref_id": None,
                   "fmea_node_id": None, "product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"], stage=stage, fmea_docs=[], linked_fmea=linked_fmea)


def _stub_source(*candidates):
    class _Source:
        async def retrieve(self, context):
            return list(candidates)

        def summary(self, candidates):
            return "stub summary"

    return _Source()


def _async_stub_source(*candidates):
    """返回一个可被 await 的 mock source，记录 retrieve 调用，提供新源协议所需的 should_skip。"""
    class _AsyncSource:
        def __init__(self, candidates):
            self.candidates = candidates
            self.retrieve_calls = []

        async def should_skip(self, context):
            return None

        async def retrieve(self, context):
            self.retrieve_calls.append(context)
            return list(self.candidates)

        def summary(self, candidates):
            return "stub summary"

    return _AsyncSource(candidates)


@pytest.mark.asyncio
async def test_stages_exactly_12_unique_indexes(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)
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
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)
    result = await orch.run(_ctx(stage="d5"), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s2 = next(s for s in result.stages if s.index == 2)
    assert s2.status == "skipped"


@pytest.mark.asyncio
async def test_per_stage_protocol_violation_is_error(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)
    # 让某新源（注册后）should_skip 不存在 — 通过 _sources 注入坏源
    bad = MagicMock()
    # MagicMock 删除属性后 getattr 返回 None（不会自动重建），借此测试缺失 should_skip 路径
    del bad.should_skip  # ensure missing
    orch._sources["spc_anomaly"] = bad
    result = await orch.run(_ctx(), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s6 = next(s for s in result.stages if s.index == 6)
    assert s6.status == "error"


@pytest.mark.asyncio
async def test_d5_stage2_direct_lookup_when_embedding_off(monkeypatch):
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)  # embedding=None → stage 3 skipped
    linked = {"fmea_id": "f1", "document_no": "PFMEA-1", "product_line_code": "DC-DC-100",
              "graph_data": {"nodes": [{"id":"c1","type":"FailureCause","name":"螺栓尺寸超差"},
                                       {"id":"fm1","type":"FailureMode","name":"虚焊"}],
                             "edges": [{"source":"c1","target":"fm1","type":"CAUSE_OF"}]}}
    ctx = _ctx(stage="d5", linked_fmea=linked)
    ctx.capa_data["d4_root_cause"] = "螺栓尺寸超差"
    from app.services.recommendation_types import RecommendationCandidate
    orch.d5_control_expander.expand = AsyncMock(return_value=[
        RecommendationCandidate(source="fmea_graph", content="监控", category=None, confidence=0.6,
                                match_reason="扩展控制措施", metadata={"control_node_id":"ctrl1"})
    ])
    result = await orch.run(ctx, user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s2 = next(s for s in result.stages if s.index == 2)
    assert s2.status == "done"  # 直查命中 cause → 扩展 control，不 skipped


@pytest.mark.asyncio
async def test_stage10_d5_uses_rule_engine_measure():
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)
    from app.services.recommendation_types import RecommendationCandidate
    d4_cand = RecommendationCandidate(
        source="rule_engine", content="D4 root cause marker", category=None, confidence=0.8,
        match_reason="D4 rule", metadata={"marker": "d4"})
    d5_cand = RecommendationCandidate(
        source="rule_engine_measure", content="D5 measure marker", category="预防措施", confidence=0.8,
        match_reason="D5 measure rule", metadata={"marker": "d5"})
    orch._sources["rule_engine"] = _stub_source(d4_cand)
    orch._sources["rule_engine_measure"] = _stub_source(d5_cand)

    result = await orch.run(_ctx(stage="d5"), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s10 = next(s for s in result.stages if s.index == 10)
    assert s10.source == "rule_engine_measure"
    assert s10.status == "done"
    markers = {c.metadata.get("marker") for c in result.items}
    assert "d5" in markers
    assert "d4" not in markers


@pytest.mark.asyncio
async def test_stage10_d4_uses_rule_engine():
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)
    from app.services.recommendation_types import RecommendationCandidate
    d4_cand = RecommendationCandidate(
        source="rule_engine", content="D4 root cause marker", category=None, confidence=0.8,
        match_reason="D4 rule", metadata={"marker": "d4"})
    d5_cand = RecommendationCandidate(
        source="rule_engine_measure", content="D5 measure marker", category="预防措施", confidence=0.8,
        match_reason="D5 measure rule", metadata={"marker": "d5"})
    orch._sources["rule_engine"] = _stub_source(d4_cand)
    orch._sources["rule_engine_measure"] = _stub_source(d5_cand)

    result = await orch.run(_ctx(stage="d4"), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s10 = next(s for s in result.stages if s.index == 10)
    assert s10.source == "rule_engine"
    assert s10.status == "done"
    markers = {c.metadata.get("marker") for c in result.items}
    assert "d4" in markers
    assert "d5" not in markers


@pytest.mark.asyncio
async def test_d4_stage3_runs_historical_capa():
    """D4 stage 3 以 semantic_search 为主源，并额外执行 historical_capa。"""
    from app.services.llm_fusion_layer import LLMOutcome
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), MagicMock())
    orch.llm_layer.enrich = AsyncMock(side_effect=lambda cands, ctx: LLMOutcome(candidates=list(cands), attempted=0))

    ss_cand = RecommendationCandidate(
        source="semantic_search", content="语义召回根因", category=None, confidence=0.8,
        match_reason="语义相似", metadata={"marker": "semantic"})
    hist_cand = RecommendationCandidate(
        source="historical_capa", content="历史CAPA根因", category=None, confidence=0.7,
        match_reason="历史 CAPA 相似", metadata={"marker": "historical_capa", "historical_capa_id": "capa-1"})

    orch._sources["semantic_search"] = _async_stub_source(ss_cand)
    orch._sources["historical_capa"] = _async_stub_source(hist_cand)

    result = await orch.run(_ctx(stage="d4"), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s3 = next(s for s in result.stages if s.index == 3)
    assert s3.source == "semantic_search"
    assert s3.status == "done"
    assert s3.hit_count == 2

    markers = {c.metadata.get("marker") for c in result.items}
    assert "semantic" in markers
    assert "historical_capa" in markers
    assert len(orch._sources["historical_capa"].retrieve_calls) == 1


@pytest.mark.asyncio
async def test_d5_stage5_runs_historical_capa_measure():
    """D5 stage 5 以 lessons_learned 为主源，并额外执行 historical_capa_measure。"""
    from app.services.llm_fusion_layer import LLMOutcome
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), MagicMock())
    orch.llm_layer.enrich = AsyncMock(side_effect=lambda cands, ctx: LLMOutcome(candidates=list(cands), attempted=0))

    ll_cand = RecommendationCandidate(
        source="lessons_learned", content="经验教训措施", category="预防措施", confidence=0.8,
        match_reason="经验教训命中", metadata={"marker": "lessons_learned"})
    hist_cand = RecommendationCandidate(
        source="historical_capa_measure", content="历史CAPA措施", category="纠正措施", confidence=0.7,
        match_reason="历史 CAPA 措施命中", metadata={"marker": "historical_capa_measure"})

    orch._sources["lessons_learned"] = _async_stub_source(ll_cand)
    orch._sources["historical_capa_measure"] = _async_stub_source(hist_cand)
    # knowledge_entry is also stage-5 extra; stub empty so MagicMock db is not hit
    orch._sources["knowledge_entry"] = _async_stub_source()

    result = await orch.run(_ctx(stage="d5"), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s5 = next(s for s in result.stages if s.index == 5)
    assert s5.source == "lessons_learned"
    assert s5.status == "done"
    assert s5.hit_count == 2

    markers = {c.metadata.get("marker") for c in result.items}
    assert "lessons_learned" in markers
    assert "historical_capa_measure" in markers
    assert len(orch._sources["historical_capa_measure"].retrieve_calls) == 1


@pytest.mark.asyncio
async def test_d4_stage3_extra_failure_recorded():
    """D4 stage 3 主源成功但额外源失败时，StageRun 仍标 done，且 error/summary 记录失败。"""
    from app.services.llm_fusion_layer import LLMOutcome
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), MagicMock())
    orch.llm_layer.enrich = AsyncMock(side_effect=lambda cands, ctx: LLMOutcome(candidates=list(cands), attempted=0))

    ss_cand = RecommendationCandidate(
        source="semantic_search", content="语义召回根因", category=None, confidence=0.8,
        match_reason="语义相似", metadata={"marker": "semantic"})
    orch._sources["semantic_search"] = _async_stub_source(ss_cand)
    hist_source = _async_stub_source()
    hist_source.retrieve = AsyncMock(side_effect=RuntimeError("boom"))
    orch._sources["historical_capa"] = hist_source

    result = await orch.run(_ctx(stage="d4"), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s3 = next(s for s in result.stages if s.index == 3)
    assert s3.source == "semantic_search"
    assert s3.status == "done"
    assert s3.hit_count == 1
    assert s3.error is not None
    assert "historical_capa" in s3.error
    assert "boom" in s3.error
    assert "extra failures:" in s3.summary

    markers = {c.metadata.get("marker") for c in result.items}
    assert "semantic" in markers


@pytest.mark.asyncio
async def test_d4_stage3_primary_empty_extra_failure_is_error():
    """D4 stage 3 主源返回 0 候选且额外源失败时，StageRun 标 error 而非 done(0)。"""
    from app.services.llm_fusion_layer import LLMOutcome
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), MagicMock())
    orch.llm_layer.enrich = AsyncMock(side_effect=lambda cands, ctx: LLMOutcome(candidates=list(cands), attempted=0))

    orch._sources["semantic_search"] = _async_stub_source()
    hist_source = _async_stub_source()
    hist_source.retrieve = AsyncMock(side_effect=RuntimeError("boom"))
    orch._sources["historical_capa"] = hist_source

    result = await orch.run(_ctx(stage="d4"), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s3 = next(s for s in result.stages if s.index == 3)
    assert s3.source == "semantic_search"
    assert s3.status == "error"
    assert s3.hit_count == 0
    assert s3.error is not None
    assert "historical_capa" in s3.error
    assert "boom" in s3.error


@pytest.mark.asyncio
async def test_d4_stage3_historical_capa_skipped_when_no_embedding():
    """embedding 未配置时，D4 stage 3 因主源/额外源均依赖 embedding 而 skipped。

    Note: A2 blocks the entire pipeline when pc=None. To exercise the pipeline
    and verify per-stage embedding-skipping behavior, pc must be non-None.
    """
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), None)
    result = await orch.run(_ctx(stage="d4"), user=MagicMock(user_id="u"), report_id="r", factory_id="f", tenant_schema="t")
    s3 = next(s for s in result.stages if s.index == 3)
    assert s3.status == "skipped"
    assert "未配置 embedding" in s3.summary
