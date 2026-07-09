"""Tests for RecommendationOrchestrator BLOCKED path (Task A2).

When self.pc is None (no LLM configured), run() returns immediately
with items=[], blocked=True, and 12 structured StageRun rows.
"""

import asyncio
import uuid

import pytest

from app.services.recommendation_orchestrator import RecommendationOrchestrator
from app.services.recommendation_types import (
    RecommendationContext,
    RecommendationResult,
    StageRun,
)


@pytest.fixture
def pc_none_orchestrator():
    """Orchestrator with pc=None (simulates no LLM configured)."""
    return RecommendationOrchestrator(db=None, pc=None, embedding_provider=None)


@pytest.fixture
def basic_d4_context():
    """Minimal D4 context for blocked-path testing."""
    return RecommendationContext(
        capa_data={
            "d2_description": "Part out of spec",
            "d4_root_cause": "",
            "report_id": None,
            "product_line_code": "PL",
            "fmea_ref_id": None,
            "fmea_node_id": None,
        },
        user_product_lines=None,
        stage="d4",
        factory_id=None,
        fmea_docs=[],
        linked_fmea=None,
    )


async def test_run_blocked_when_pc_none(pc_none_orchestrator, basic_d4_context):
    """When pc=None, run() returns blocked immediately without executing pipeline."""
    result = await pc_none_orchestrator.run(
        basic_d4_context, user=None, report_id=None, factory_id=None, tenant_schema=None
    )
    assert result.blocked is True
    assert result.items == []
    assert len(result.stages) == 12

    # Stage 1 (上下文采集) = done
    s1 = next(s for s in result.stages if s.index == 1)
    assert s1.status == "done"

    # Stage 11 (LLM 融合排序) = blocked
    s11 = next(s for s in result.stages if s.index == 11)
    assert s11.status == "blocked"
    assert "未配置" in s11.summary

    # All other stages = skipped
    others = [s for s in result.stages if s.index not in (1, 11)]
    assert all(s.status == "skipped" for s in others)


async def test_blocked_stages_count_and_order(pc_none_orchestrator, basic_d4_context):
    """Blocked stages must cover all 12 indices in sorted order."""
    result = await pc_none_orchestrator.run(
        basic_d4_context, user=None, report_id=None, factory_id=None, tenant_schema=None
    )
    indices = [s.index for s in result.stages]
    assert indices == list(range(1, 13))


async def test_blocked_stages_source_kinds(pc_none_orchestrator, basic_d4_context):
    """Each blocked stage must carry correct source from STAGE_PLAN."""
    result = await pc_none_orchestrator.run(
        basic_d4_context, user=None, report_id=None, factory_id=None, tenant_schema=None
    )
    source_map = {s.index: s.source for s in result.stages}
    # Stage 1 internal, 2 fmea_graph, 3 semantic_search, etc.
    assert source_map[1] == "internal"
    assert source_map[2] == "fmea_graph"
    assert source_map[3] == "semantic_search"
    assert source_map[11] == "llm"
    assert source_map[12] == "internal"
