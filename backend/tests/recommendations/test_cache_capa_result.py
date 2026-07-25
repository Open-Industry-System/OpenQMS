"""Tests for HybridRecommendationPipeline._cache_capa_result and _serialize_capa_suggestions."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.models.capa import CAPAEightD
from app.models.recommendation_cache import RecommendationCache
from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
from app.services.recommendation_types import (
    RecommendationCandidate,
    RecommendationContext,
    RecommendationResult,
    StageRun,
)

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-CACHE-{uuid.uuid4().hex[:8]}",
        title="Cache test CAPA",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        created_by=user_id,
        status="D4_ROOT_CAUSE",
        d2_description="d2",
        d3_interim="d3",
        d4_root_cause="rc",
    )
    db.add(capa)
    await db.flush()
    await db.refresh(capa)
    return capa


def _d4_context(report_id, factory_id):
    return RecommendationContext(
        capa_data={
            "d2_description": "d",
            "d3_interim": "",
            "d4_root_cause": "rc",
            "fmea_ref_id": None,
            "fmea_node_id": None,
            "product_line_code": "DC-DC-100",
            "report_id": str(report_id),
        },
        user_product_lines=None,
        stage="d4",
        factory_id=factory_id,
        fmea_docs=[],
        linked_fmea=None,
    )


def test_serialize_capa_suggestions_d4_is_list_with_kind():
    pipe = HybridRecommendationPipeline(db=MagicMock(), pc=None, embedding_provider=None)
    cand = RecommendationCandidate(
        source="fmea_graph",
        content="cause1",
        category=None,
        confidence=0.5,
        match_reason="r",
        metadata={"stage_index": 2},
    )
    out = pipe._serialize_capa_suggestions("d4", [cand])
    assert isinstance(out, list)
    assert out[0]["kind"] == "d4_cause"
    assert "failure_cause_name" in out[0]


def test_serialize_capa_suggestions_d5_mutually_exclusive():
    pipe = HybridRecommendationPipeline(db=MagicMock(), pc=None, embedding_provider=None)
    ctrl = MagicMock()
    ctrl.to_d5_control_schema.return_value = {"control_node_id": "n1", "name": "c"}
    ctrl.to_d5_suggestion_schema.return_value = {"content": "should not appear"}
    sugg = MagicMock()
    sugg.to_d5_control_schema.return_value = None
    sugg.to_d5_suggestion_schema.return_value = {"content": "s1"}

    out = pipe._serialize_capa_suggestions("d5", [ctrl, sugg])
    kinds = [x["kind"] for x in out]
    assert kinds == ["d5_control", "d5_suggestion"]
    assert len(out) == 2
    # control candidate's suggestion schema must NOT also be emitted
    assert all(x.get("content") != "should not appear" for x in out)


@pytest.mark.asyncio
async def test_cache_capa_result_persists_stage_runs(db, default_factory, admin_user):
    pipe = HybridRecommendationPipeline(db=db, pc=MagicMock(), embedding_provider=None)
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    ctx = _d4_context(capa.report_id, capa.factory_id)
    result = RecommendationResult(
        items=[MagicMock(to_d4_schema=lambda: {"failure_cause_name": "c1"})],
        stages=[StageRun(i, f"s{i}", "internal", "done") for i in range(1, 13)],
        blocked=False,
    )

    await pipe._cache_capa_result(capa.report_id, ctx, result)
    await db.commit()

    row = await db.scalar(
        select(RecommendationCache).where(
            RecommendationCache.report_id == capa.report_id,
            RecommendationCache.trigger_type == "d4",
        )
    )
    assert row is not None
    assert row.doc_type == "capa"
    assert row.stage_runs is not None and len(row.stage_runs) == 12
    assert row.stage_runs[10]["status"] == "done"
    assert row.suggestions is not None and len(row.suggestions) == 1
    assert row.suggestions[0]["kind"] == "d4_cause"


@pytest.mark.asyncio
async def test_cache_capa_result_stage_runs_serialize_failure_degrades(db, default_factory, admin_user):
    pipe = HybridRecommendationPipeline(db=db, pc=MagicMock(), embedding_provider=None)
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    ctx = _d4_context(capa.report_id, capa.factory_id)
    bad_stage = StageRun(11, "LLM", "llm", "bogus_status")
    result = RecommendationResult(
        items=[MagicMock(to_d4_schema=lambda: {"failure_cause_name": "c1"})],
        stages=[bad_stage],
        blocked=False,
    )

    await pipe._cache_capa_result(capa.report_id, ctx, result)
    await db.commit()

    row = await db.scalar(
        select(RecommendationCache).where(RecommendationCache.report_id == capa.report_id)
    )
    assert row is not None
    assert row.stage_runs is None
    assert row.suggestions is not None and len(row.suggestions) == 1
