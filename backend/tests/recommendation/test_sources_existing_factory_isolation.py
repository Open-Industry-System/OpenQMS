"""Step 4b: existing sources factory_id isolation (R17/R18).

Verifies that SemanticSearchSource.retrieve and HistoricalCAPASource._search
add a `factory_id` filter to their SQL WHERE clause when context.factory_id is
set, and omit it (None guard) when context.factory_id is None.

Approach: the production vector queries require the pgvector `embedding` column
(created via raw-SQL migration, absent from the create_all test schema). We
therefore intercept db.execute to capture the emitted SQL + params and assert
the factory filter is present/absent — this directly tests the R17/R18 change
without depending on the vector column. The factory_id value is also asserted
to flow through to the SQL params.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.recommendation_sources import HistoricalCAPASource, SemanticSearchSource
from app.services.recommendation_types import RecommendationContext

pytestmark = pytest.mark.requires_db


def _make_embedding():
    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[[0.1] * 768])
    return emb


def _capture_execute(mock_db):
    """Capture the (sql_text, params) of the first db.execute call."""
    captured = {}

    async def _fake_execute(stmt, params=None):
        captured["sql"] = str(stmt)
        captured["params"] = params or {}
        # Return an empty result so retrieve() produces no candidates
        result = MagicMock()
        result.fetchall.return_value = []
        result.mappings.return_value = iter([])
        return result

    mock_db.execute = AsyncMock(side_effect=_fake_execute)
    return captured


# ── SemanticSearchSource ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_semantic_search_adds_factory_filter_when_factory_id_set():
    """context.factory_id set → SQL contains `de.factory_id = :factory_id` and param flows through."""
    db = MagicMock()
    captured = _capture_execute(db)
    src = SemanticSearchSource(db, _make_embedding())

    factory_a = uuid.uuid4()
    ctx = RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "product_line_code": "PL-A"},
        user_product_lines=None,  # admin: no PL filter
        stage="d4",
        factory_id=factory_a,
        fmea_docs=[],
    )
    await src.retrieve(ctx)

    assert "de.factory_id = :factory_id" in captured["sql"]
    assert captured["params"].get("factory_id") == factory_a


@pytest.mark.asyncio
async def test_semantic_search_omits_factory_filter_when_factory_id_none():
    """None guard: context.factory_id=None → no factory filter in SQL, no factory_id param."""
    db = MagicMock()
    captured = _capture_execute(db)
    src = SemanticSearchSource(db, _make_embedding())

    ctx = RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "product_line_code": "PL-A"},
        user_product_lines=None,
        stage="d4",
        factory_id=None,
        fmea_docs=[],
    )
    await src.retrieve(ctx)

    assert "factory_id" not in captured["sql"]
    assert "factory_id" not in captured["params"]


# ── HistoricalCAPASource ─────────────────────────────────────────────────────

def _capture_execute_mappings(mock_db, rows=None):
    """Capture (sql_text, params); return `rows` from mappings()."""
    captured = {}

    async def _fake_execute(stmt, params=None):
        captured["sql"] = str(stmt)
        captured["params"] = params or {}
        result = MagicMock()
        result.mappings.return_value = iter(rows or [])
        return result

    mock_db.execute = AsyncMock(side_effect=_fake_execute)
    return captured


@pytest.mark.asyncio
async def test_historical_capa_adds_factory_filter_when_factory_id_set():
    """context.factory_id set → SQL contains de.factory_id + capa.factory_id and param flows through."""
    db = MagicMock()
    captured = _capture_execute_mappings(db)
    src = HistoricalCAPASource(db, _make_embedding())

    factory_a = uuid.uuid4()
    ctx = RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "product_line_code": "PL-A"},
        user_product_lines=None,
        stage="d4",
        factory_id=factory_a,
    )
    await src.retrieve(ctx)

    assert "de.factory_id = :factory_id" in captured["sql"]
    assert "capa.factory_id = :factory_id" in captured["sql"]
    assert captured["params"].get("factory_id") == factory_a


@pytest.mark.asyncio
async def test_historical_capa_omits_factory_filter_when_factory_id_none():
    """None guard: context.factory_id=None → no factory filter, no factory_id param."""
    db = MagicMock()
    captured = _capture_execute_mappings(db)
    src = HistoricalCAPASource(db, _make_embedding())

    ctx = RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "product_line_code": "PL-A"},
        user_product_lines=None,
        stage="d4",
        factory_id=None,
    )
    await src.retrieve(ctx)

    assert "factory_id" not in captured["sql"]
    assert "factory_id" not in captured["params"]


# ── None guard regression: query doesn't crash, returns non-empty when rows exist ──

@pytest.mark.asyncio
async def test_historical_capa_none_factory_returns_rows():
    """None guard: factory_id=None → query runs and returns candidates when rows match."""
    db = MagicMock()
    capa_id = uuid.uuid4()
    rows = [{
        "entity_id": capa_id,
        "chunk_text": "螺栓尺寸超差",
        "similarity": 0.75,
        "document_no": "8D-A-001",
        "severity": "严重",
        "source_updated_at": "2026-05-01",
        "d4_root_cause": "螺栓尺寸超差",
        "d5_correction": "增加温控",
        "product_line_code": "PL-A",
    }]
    captured = _capture_execute_mappings(db, rows=rows)
    src = HistoricalCAPASource(db, _make_embedding())

    ctx = RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "product_line_code": "PL-A"},
        user_product_lines=None,
        stage="d4",
        factory_id=None,
    )
    candidates = await src.retrieve(ctx)
    # Non-empty return — None guard didn't crash the query
    assert len(candidates) >= 1
    assert candidates[0].metadata.get("historical_capa_id") == str(capa_id)
    # And no factory filter was applied
    assert "factory_id" not in captured["sql"]
