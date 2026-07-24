"""Step 4b: existing sources factory_id isolation (R17/R18).

Verifies that SemanticSearchSource.retrieve, HistoricalCAPASource._search and
HistoricalCAPAMeasureSource._search add a `factory_id` filter to their SQL
WHERE clause when context.factory_id is set, and omit it (None guard) when
context.factory_id is None.

Two verification layers:
1. Mock db.execute to capture emitted SQL + params for every affected source.
2. Behavioral double-factory test using the real migrated DB: seed CAPAs and
   DocumentEmbedding rows in two factories, then assert only factory A's rows
   are returned when context.factory_id=factory_A.
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text

from app.models.capa import CAPAEightD
from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.product_line import ProductLine
from app.services.recommendation_sources import (
    HistoricalCAPASource,
    HistoricalCAPAMeasureSource,
    SemanticSearchSource,
)
from app.services.recommendation_types import RecommendationContext


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


# ── HistoricalCAPAMeasureSource (mock SQL capture) ───────────────────────────

@pytest.mark.asyncio
async def test_historical_capa_measure_adds_factory_filter_when_factory_id_set():
    """context.factory_id set → SQL contains de.factory_id + capa.factory_id and param flows through."""
    db = MagicMock()
    captured = _capture_execute_mappings(db)
    src = HistoricalCAPAMeasureSource(db, _make_embedding())

    factory_a = uuid.uuid4()
    ctx = RecommendationContext(
        capa_data={"d4_root_cause": "螺栓尺寸超差", "product_line_code": "PL-A"},
        user_product_lines=None,
        stage="d5",
        factory_id=factory_a,
    )
    await src.retrieve(ctx)

    assert "de.factory_id = :factory_id" in captured["sql"]
    assert "capa.factory_id = :factory_id" in captured["sql"]
    assert captured["params"].get("factory_id") == factory_a


@pytest.mark.asyncio
async def test_historical_capa_measure_omits_factory_filter_when_factory_id_none():
    """None guard: context.factory_id=None → no factory filter, no factory_id param."""
    db = MagicMock()
    captured = _capture_execute_mappings(db)
    src = HistoricalCAPAMeasureSource(db, _make_embedding())

    ctx = RecommendationContext(
        capa_data={"d4_root_cause": "螺栓尺寸超差", "product_line_code": "PL-A"},
        user_product_lines=None,
        stage="d5",
        factory_id=None,
    )
    await src.retrieve(ctx)

    assert "factory_id" not in captured["sql"]
    assert "factory_id" not in captured["params"]


@pytest.mark.asyncio
async def test_historical_capa_measure_none_factory_returns_rows():
    """None guard: factory_id=None → query runs and returns measure candidates when rows match."""
    db = MagicMock()
    capa_id = uuid.uuid4()
    rows = [{
        "entity_id": capa_id,
        "chunk_text": "螺栓尺寸超差",
        "similarity": 0.75,
        "document_no": "8D-A-001",
        "severity": "严重",
        "source_updated_at": "2026-05-01",
        "d5_correction": "增加温控",
        "product_line_code": "PL-A",
    }]
    captured = _capture_execute_mappings(db, rows=rows)
    src = HistoricalCAPAMeasureSource(db, _make_embedding())

    ctx = RecommendationContext(
        capa_data={"d4_root_cause": "螺栓尺寸超差", "product_line_code": "PL-A"},
        user_product_lines=None,
        stage="d5",
        factory_id=None,
    )
    candidates = await src.retrieve(ctx)
    assert len(candidates) >= 1
    assert candidates[0].metadata.get("historical_capa_id") == str(capa_id)
    assert "factory_id" not in captured["sql"]


# ── Behavioral double-factory isolation tests (real migrated DB) ──────────────

async def _embedding_dim(db) -> int | None:
    """Query the actual pgvector dimension configured for document_embeddings.

    Returns None when the column is absent (e.g. a create_all test schema), so
    behavioral tests can skip gracefully while still running in the fully
    migrated CI database.
    """
    result = await db.execute(text("""
        SELECT atttypmod FROM pg_attribute
        WHERE attrelid = 'document_embeddings'::regclass AND attname = 'embedding'
    """))
    row = result.fetchone()
    return row[0] if row else None


def _vec_str(dim: int, hot_idx: int) -> str:
    """Return a pgvector literal with a single hot dimension (orthogonal to other hot indices)."""
    parts = ["0.0"] * dim
    parts[hot_idx] = "1.0"
    return "[" + ",".join(parts) + "]"


async def _seed_factory_b(db):
    suffix = uuid.uuid4().hex[:8]
    factory_b = Factory(code=f"FB-{suffix}", name="Factory B")
    db.add(factory_b)
    await db.flush()
    await db.refresh(factory_b)

    pl_b = ProductLine(code=f"PL-B-{suffix}", name=f"Product Line B {suffix}", factory_id=factory_b.id)
    db.add(pl_b)
    await db.flush()
    return factory_b, pl_b


async def _seed_capa(db, factory_id, pl_code, user_id, suffix):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-{suffix}",
        title=f"CAPA {suffix}",
        product_line_code=pl_code,
        factory_id=factory_id,
        status="D8_CLOSURE",
        severity="严重",
        d2_description=f"问题 {suffix}",
        d4_root_cause=f"根因 {suffix}",
        d5_correction=f"措施 {suffix}",
        created_by=user_id,
    )
    db.add(capa)
    await db.flush()
    await db.refresh(capa)
    return capa


async def _seed_fmea_doc(db, factory_id, pl_code, user_id, suffix):
    node_id = str(uuid.uuid4())
    doc = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=f"PFMEA-{suffix}",
        title=f"FMEA {suffix}",
        fmea_type="PFMEA",
        product_line_code=pl_code,
        factory_id=factory_id,
        created_by=user_id,
        status="approved",
        graph_data={
            "nodes": [
                {"id": node_id, "type": "FailureCause", "name": f"cause {suffix}", "description": f"desc {suffix}"}
            ],
            "edges": [],
        },
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc, node_id


async def _seed_embedding(
    db,
    dim: int,
    entity_type: str,
    entity_id: uuid.UUID,
    entity_field: str,
    chunk_text: str,
    factory_id: uuid.UUID,
    pl_code: str,
    model: str,
    hot_idx: int = 0,
    node_id: str | None = None,
    metadata: dict | None = None,
):
    emb_id = uuid.uuid4()
    await db.execute(
        text("""
            INSERT INTO document_embeddings
                (id, entity_type, entity_id, node_id, entity_field, chunk_index, chunk_text,
                 embedding, product_line_code, factory_id, metadata, embedding_model)
            VALUES
                (:id, :entity_type, :entity_id, :node_id, :entity_field, 0, :chunk_text,
                 CAST(:embedding AS vector), :product_line_code, :factory_id, :metadata, :embedding_model)
        """),
        {
            "id": emb_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "node_id": node_id,
            "entity_field": entity_field,
            "chunk_text": chunk_text,
            "embedding": _vec_str(dim, hot_idx),
            "product_line_code": pl_code,
            "factory_id": factory_id,
            "metadata": json.dumps(metadata) if metadata else "{}",
            "embedding_model": model,
        },
    )
    await db.flush()
    return emb_id


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_semantic_search_blocks_cross_factory_rows(db, default_factory, admin_user):
    """Real DB: factory A semantic query must not return factory B's FMEA candidates."""
    suffix_a = f"A-{uuid.uuid4().hex[:8]}"
    suffix_b = f"B-{uuid.uuid4().hex[:8]}"
    factory_b, pl_b = await _seed_factory_b(db)
    pl_a_code = "DC-DC-100"
    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present (pgvector schema not available)")

    fmea_a, node_id_a = await _seed_fmea_doc(db, default_factory.id, pl_a_code, admin_user.user_id, suffix_a)
    fmea_b, node_id_b = await _seed_fmea_doc(db, factory_b.id, pl_b.code, admin_user.user_id, suffix_b)

    await _seed_embedding(
        db, dim, "fmea_node", fmea_a.fmea_id, "name", f"desc {suffix_a}",
        default_factory.id, pl_a_code, "test-model", hot_idx=0, node_id=node_id_a,
        metadata={"node_type": "FailureCause"},
    )
    await _seed_embedding(
        db, dim, "fmea_node", fmea_b.fmea_id, "name", f"desc {suffix_b}",
        factory_b.id, pl_b.code, "test-model", hot_idx=1, node_id=node_id_b,
        metadata={"node_type": "FailureCause"},
    )

    query_vec = [0.0] * dim
    query_vec[0] = 1.0

    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[query_vec])
    src = SemanticSearchSource(db, emb)

    fmea_a_dict = {
        "fmea_id": str(fmea_a.fmea_id),
        "document_no": fmea_a.document_no,
        "product_line_code": fmea_a.product_line_code,
        "graph_data": fmea_a.graph_data,
    }
    fmea_b_dict = {
        "fmea_id": str(fmea_b.fmea_id),
        "document_no": fmea_b.document_no,
        "product_line_code": fmea_b.product_line_code,
        "graph_data": fmea_b.graph_data,
    }

    ctx = RecommendationContext(
        capa_data={"d2_description": f"问题 {suffix_a}", "product_line_code": pl_a_code},
        user_product_lines=None,
        stage="d4",
        factory_id=default_factory.id,
        fmea_docs=[fmea_a_dict, fmea_b_dict],
    )

    candidates = await src.retrieve(ctx)

    returned_nos = {c.metadata.get("fmea_document_no") for c in candidates}
    assert fmea_a.document_no in returned_nos
    assert fmea_b.document_no not in returned_nos
    assert all(c.metadata.get("fmea_id") == str(fmea_a.fmea_id) for c in candidates)


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_historical_capa_blocks_cross_factory_rows(db, default_factory, admin_user):
    """Real DB: factory A CAPA query must not return factory B's CAPA candidates."""
    suffix_a = f"A-{uuid.uuid4().hex[:8]}"
    suffix_b = f"B-{uuid.uuid4().hex[:8]}"
    factory_b, pl_b = await _seed_factory_b(db)
    pl_a_code = "DC-DC-100"
    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present (pgvector schema not available)")

    capa_a = await _seed_capa(db, default_factory.id, pl_a_code, admin_user.user_id, suffix_a)
    capa_b = await _seed_capa(db, factory_b.id, pl_b.code, admin_user.user_id, suffix_b)

    await _seed_embedding(
        db, dim, "capa", capa_a.report_id, "d2_description", capa_a.d2_description,
        default_factory.id, pl_a_code, "test-model", hot_idx=0,
    )
    await _seed_embedding(
        db, dim, "capa", capa_b.report_id, "d2_description", capa_b.d2_description,
        factory_b.id, pl_b.code, "test-model", hot_idx=1,
    )

    query_vec = [0.0] * dim
    query_vec[0] = 1.0

    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[query_vec])
    src = HistoricalCAPASource(db, emb)

    ctx = RecommendationContext(
        capa_data={"d2_description": capa_a.d2_description, "product_line_code": pl_a_code},
        user_product_lines=None,
        stage="d4",
        factory_id=default_factory.id,
    )

    candidates = await src.retrieve(ctx)

    returned_nos = {c.metadata.get("document_no") for c in candidates}
    assert capa_a.document_no in returned_nos
    assert capa_b.document_no not in returned_nos


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_historical_capa_measure_blocks_cross_factory_rows(db, default_factory, admin_user):
    """Real DB: factory A CAPA measure query must not return factory B's measure candidates."""
    suffix_a = f"A-{uuid.uuid4().hex[:8]}"
    suffix_b = f"B-{uuid.uuid4().hex[:8]}"
    factory_b, pl_b = await _seed_factory_b(db)
    pl_a_code = "DC-DC-100"
    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present (pgvector schema not available)")

    capa_a = await _seed_capa(db, default_factory.id, pl_a_code, admin_user.user_id, suffix_a)
    capa_b = await _seed_capa(db, factory_b.id, pl_b.code, admin_user.user_id, suffix_b)

    await _seed_embedding(
        db, dim, "capa", capa_a.report_id, "d4_root_cause", capa_a.d4_root_cause,
        default_factory.id, pl_a_code, "test-model", hot_idx=0,
    )
    await _seed_embedding(
        db, dim, "capa", capa_b.report_id, "d4_root_cause", capa_b.d4_root_cause,
        factory_b.id, pl_b.code, "test-model", hot_idx=1,
    )

    query_vec = [0.0] * dim
    query_vec[0] = 1.0

    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[query_vec])
    src = HistoricalCAPAMeasureSource(db, emb)

    ctx = RecommendationContext(
        capa_data={"d4_root_cause": capa_a.d4_root_cause, "product_line_code": pl_a_code},
        user_product_lines=None,
        stage="d5",
        factory_id=default_factory.id,
    )

    candidates = await src.retrieve(ctx)

    returned_nos = {c.metadata.get("document_no") for c in candidates}
    assert capa_a.document_no in returned_nos
    assert capa_b.document_no not in returned_nos
