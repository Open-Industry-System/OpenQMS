"""US-E2E-01.8 Task 5: KnowledgeEntrySource + KnowledgeAuditError orchestrator re-raise."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, text

from app.models.audit import AuditLog
from app.models.factory import Factory
from app.models.knowledge_entry import KnowledgeEntry
from app.services.recommendation_orchestrator import RecommendationOrchestrator, STAGE_PLAN
from app.services.recommendation_sources_extra import KnowledgeAuditError, KnowledgeEntrySource
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext

pytestmark = pytest.mark.requires_db


# ── helpers ──────────────────────────────────────────────────────────────────


async def _embedding_dim(db) -> int | None:
    result = await db.execute(
        text(
            """
            SELECT atttypmod FROM pg_attribute
            WHERE attrelid = 'document_embeddings'::regclass AND attname = 'embedding'
            """
        )
    )
    row = result.fetchone()
    return row[0] if row else None


def _vec_str(dim: int, hot_idx: int) -> str:
    parts = ["0.0"] * dim
    parts[hot_idx] = "1.0"
    return "[" + ",".join(parts) + "]"


async def _seed_embedding(
    db,
    dim: int,
    entity_id: uuid.UUID,
    factory_id: uuid.UUID,
    pl_code: str,
    chunk_text: str = "knowledge summary",
    hot_idx: int = 0,
) -> uuid.UUID:
    emb_id = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO document_embeddings
                (id, entity_type, entity_id, node_id, entity_field, chunk_index, chunk_text,
                 embedding, product_line_code, factory_id, metadata, embedding_model)
            VALUES
                (:id, 'knowledge_entry', :entity_id, NULL, 'embedding_text', 0, :chunk_text,
                 CAST(:embedding AS vector), :product_line_code, :factory_id, '{}'::jsonb, 'test-model')
            """
        ),
        {
            "id": emb_id,
            "entity_id": entity_id,
            "chunk_text": chunk_text,
            "embedding": _vec_str(dim, hot_idx),
            "product_line_code": pl_code,
            "factory_id": factory_id,
        },
    )
    return emb_id


def _make_entry(
    db,
    *,
    factory_id: uuid.UUID,
    product_line_code: str = "DC-DC-100",
    document_no: str | None = None,
    lesson_summary: str = "沉淀经验摘要",
    embedding_status: str = "ready",
    status: str = "active",
    embedding_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
) -> KnowledgeEntry:
    entry = KnowledgeEntry(
        entry_id=uuid.uuid4(),
        source_type="capa",
        source_id=source_id or uuid.uuid4(),
        factory_id=factory_id,
        product_line_code=product_line_code,
        document_no=document_no or f"8D-KE-{uuid.uuid4().hex[:6]}",
        title="knowledge entry",
        severity="一般",
        fields={
            "d2": "",
            "d3": "",
            "d4_root_cause": "",
            "d5": "",
            "d7_node_action": "",
            "linkage": {"fmea_ids": [], "scar_id": None, "supplier_risk_alert_ids": []},
            "closure": "",
            "lesson_summary": lesson_summary,
            "tags": ["t1"],
        },
        status=status,
        llm_status="done",
        embedding_text=f"[{document_no or 'DOC'}] {lesson_summary}",
        content_hash="a" * 64,
        embedding_status=embedding_status,
        embedding_id=embedding_id,
    )
    db.add(entry)
    return entry


def _ctx(
    *,
    factory_id,
    stage: str = "d4",
    pl: str = "DC-DC-100",
    report_id=None,
    user_product_lines=("DC-DC-100",),
    d2: str = "螺栓尺寸超差",
):
    # Default to list with current PL; pass None for admin-all; pass [] for empty gate.
    if isinstance(user_product_lines, tuple):
        user_product_lines = list(user_product_lines)
    return RecommendationContext(
        capa_data={
            "d2_description": d2,
            "d4_root_cause": "",
            "product_line_code": pl,
            "report_id": str(report_id or uuid.uuid4()),
        },
        user_product_lines=user_product_lines,
        stage=stage,
        factory_id=factory_id,
    )


def _async_stub_source(*candidates):
    class _AsyncSource:
        def __init__(self, cands):
            self.candidates = cands

        async def should_skip(self, context):
            return None

        async def retrieve(self, context):
            return list(self.candidates)

    return _AsyncSource(candidates)


# ── STAGE_PLAN registration ──────────────────────────────────────────────────


def test_stage5_extra_sources_include_knowledge_entry():
    s5 = next(s for s in STAGE_PLAN if s.index == 5)
    assert s5.source_kind == "lessons_learned"
    assert s5.extra_sources_d4 == ["knowledge_entry"]
    assert s5.extra_sources_d5 == ["historical_capa_measure", "knowledge_entry"]


def test_knowledge_entry_registered_in_orchestrator():
    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), MagicMock())
    assert "knowledge_entry" in orch.NEW_SOURCE_KINDS
    assert "knowledge_entry" in orch._sources
    assert orch._sources["knowledge_entry"].name == "knowledge_entry"


# ── should_skip ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_should_skip_no_embedding(db, default_factory):
    src = KnowledgeEntrySource(db, None)
    reason = await src.should_skip(_ctx(factory_id=default_factory.id, user_product_lines=["DC-DC-100"]))
    assert reason == "未配置 embedding"


@pytest.mark.asyncio
async def test_should_skip_no_factory(db):
    src = KnowledgeEntrySource(db, MagicMock())
    reason = await src.should_skip(_ctx(factory_id=None, user_product_lines=["DC-DC-100"]))
    assert reason is not None


@pytest.mark.asyncio
async def test_should_skip_empty_user_product_lines(db, default_factory):
    src = KnowledgeEntrySource(db, MagicMock())
    reason = await src.should_skip(_ctx(factory_id=default_factory.id, user_product_lines=[]))
    assert reason is not None


@pytest.mark.asyncio
async def test_should_skip_no_ready_entries(db, default_factory):
    _make_entry(db, factory_id=default_factory.id, embedding_status="pending")
    await db.flush()
    src = KnowledgeEntrySource(db, MagicMock())
    reason = await src.should_skip(_ctx(factory_id=default_factory.id, user_product_lines=["DC-DC-100"]))
    assert reason is not None


# ── retrieve isolation ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retrieve_filters_factory_and_pl(db, default_factory):
    """Only matching factory + current PL ready entries are returned."""
    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present")

    suffix = uuid.uuid4().hex[:6]
    other = Factory(id=uuid.uuid4(), code=f"OF-{suffix}", name="Other KE factory")
    db.add(other)
    await db.flush()

    match = _make_entry(
        db,
        factory_id=default_factory.id,
        product_line_code="DC-DC-100",
        document_no=f"8D-MATCH-{suffix}",
        lesson_summary="匹配条目摘要",
    )
    wrong_pl = _make_entry(
        db,
        factory_id=default_factory.id,
        product_line_code="AC-AC-200",
        document_no=f"8D-WPL-{suffix}",
        lesson_summary="错误产品线",
    )
    other_factory = _make_entry(
        db,
        factory_id=other.id,
        product_line_code="DC-DC-100",
        document_no=f"8D-OF-{suffix}",
        lesson_summary="其他工厂",
    )
    await db.flush()

    emb_match = await _seed_embedding(db, dim, match.entry_id, default_factory.id, "DC-DC-100", hot_idx=0)
    await _seed_embedding(db, dim, wrong_pl.entry_id, default_factory.id, "AC-AC-200", hot_idx=1)
    await _seed_embedding(db, dim, other_factory.entry_id, other.id, "DC-DC-100", hot_idx=2)
    match.embedding_id = emb_match
    await db.flush()

    query_vec = [0.0] * dim
    query_vec[0] = 1.0
    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[query_vec])

    src = KnowledgeEntrySource(db, emb)
    ctx = _ctx(factory_id=default_factory.id, user_product_lines=["DC-DC-100", "AC-AC-200"])
    cands = await src.retrieve(ctx)

    assert len(cands) >= 1
    entry_ids = {c.metadata.get("entry_id") for c in cands}
    assert str(match.entry_id) in entry_ids
    assert str(wrong_pl.entry_id) not in entry_ids
    assert str(other_factory.entry_id) not in entry_ids
    assert all(c.source == "knowledge_entry" for c in cands)


@pytest.mark.asyncio
async def test_retrieve_user_pl_gate_blocks_other_pl(db, default_factory):
    """If current CAPA PL is not in user_product_lines, return []."""
    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present")

    entry = _make_entry(db, factory_id=default_factory.id, product_line_code="DC-DC-100")
    await db.flush()
    emb_id = await _seed_embedding(db, dim, entry.entry_id, default_factory.id, "DC-DC-100")
    entry.embedding_id = emb_id
    await db.flush()

    query_vec = [0.0] * dim
    query_vec[0] = 1.0
    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[query_vec])
    src = KnowledgeEntrySource(db, emb)

    ctx = _ctx(
        factory_id=default_factory.id,
        pl="DC-DC-100",
        user_product_lines=["OTHER-PL"],
    )
    assert await src.retrieve(ctx) == []


# ── audit on hit ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retrieved_audit_on_hit(db, default_factory):
    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present")

    report_id = uuid.uuid4()
    entry = _make_entry(
        db,
        factory_id=default_factory.id,
        document_no="8D-AUDIT-HIT",
        lesson_summary="审计命中摘要",
    )
    await db.flush()
    emb_id = await _seed_embedding(db, dim, entry.entry_id, default_factory.id, "DC-DC-100")
    entry.embedding_id = emb_id
    await db.flush()

    query_vec = [0.0] * dim
    query_vec[0] = 1.0
    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[query_vec])
    src = KnowledgeEntrySource(db, emb)
    ctx = _ctx(factory_id=default_factory.id, report_id=report_id, user_product_lines=["DC-DC-100"])

    cands = await src.retrieve(ctx)
    assert len(cands) >= 1
    await db.flush()

    logs = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.action == "KNOWLEDGE_RETRIEVED",
                AuditLog.record_id == report_id,
            )
        )
    ).scalars().all()
    assert len(logs) == 1
    log = logs[0]
    assert log.table_name == "capa_eightd"
    assert log.factory_id == default_factory.id
    fields = log.changed_fields or {}
    assert fields.get("hit_count") == len(cands)
    assert fields.get("product_line_code") == "DC-DC-100"
    assert fields.get("stage") == 5
    entry_ids = fields.get("entry_ids") or []
    assert all(isinstance(x, str) for x in entry_ids)
    assert str(entry.entry_id) in entry_ids
    # metadata contract
    assert any(c.metadata.get("entry_id") == str(entry.entry_id) for c in cands)
    assert any(c.metadata.get("document_no") == "8D-AUDIT-HIT" for c in cands)
    assert any(c.metadata.get("capa_id") == str(entry.source_id) for c in cands)


@pytest.mark.asyncio
async def test_no_audit_on_empty_retrieve(db, default_factory):
    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[[1.0, 0.0]])
    src = KnowledgeEntrySource(db, emb)
    report_id = uuid.uuid4()
    ctx = _ctx(factory_id=default_factory.id, report_id=report_id, user_product_lines=["DC-DC-100"])
    # no ready entries → empty (or skip path); force retrieve with no data
    cands = await src.retrieve(ctx)
    assert cands == []
    await db.flush()
    logs = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.action == "KNOWLEDGE_RETRIEVED",
                AuditLog.record_id == report_id,
            )
        )
    ).scalars().all()
    assert logs == []


@pytest.mark.asyncio
async def test_audit_db_add_failure_raises_knowledge_audit_error(db, default_factory, monkeypatch):
    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present")

    entry = _make_entry(db, factory_id=default_factory.id, lesson_summary="fail audit")
    await db.flush()
    emb_id = await _seed_embedding(db, dim, entry.entry_id, default_factory.id, "DC-DC-100")
    entry.embedding_id = emb_id
    await db.flush()

    query_vec = [0.0] * dim
    query_vec[0] = 1.0
    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[query_vec])
    src = KnowledgeEntrySource(db, emb)

    real_add = db.add

    def flaky_add(obj):
        if isinstance(obj, AuditLog) and getattr(obj, "action", None) == "KNOWLEDGE_RETRIEVED":
            raise RuntimeError("audit write failed")
        return real_add(obj)

    monkeypatch.setattr(db, "add", flaky_add)
    ctx = _ctx(factory_id=default_factory.id, user_product_lines=["DC-DC-100"])
    with pytest.raises(KnowledgeAuditError):
        await src.retrieve(ctx)


# ── orchestrator fail-closed ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_error_propagates_through_orchestrator():
    """KnowledgeAuditError from stage-5 extra must escape orchestrator (not 200 path)."""
    from app.services.llm_fusion_layer import LLMOutcome

    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), MagicMock())
    orch.llm_layer.enrich = AsyncMock(
        side_effect=lambda cands, ctx: LLMOutcome(candidates=list(cands), attempted=0)
    )

    ll_cand = RecommendationCandidate(
        source="lessons_learned",
        content="ll",
        category=None,
        confidence=0.8,
        match_reason="ll",
        metadata={"marker": "ll"},
    )
    orch._sources["lessons_learned"] = _async_stub_source(ll_cand)

    ke = _async_stub_source()
    ke.retrieve = AsyncMock(side_effect=KnowledgeAuditError("audit failed"))
    orch._sources["knowledge_entry"] = ke

    ctx = RecommendationContext(
        capa_data={
            "d2_description": "螺栓尺寸超差",
            "d4_root_cause": "",
            "product_line_code": "DC-DC-100",
            "report_id": str(uuid.uuid4()),
        },
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=uuid.uuid4(),
    )

    with pytest.raises(KnowledgeAuditError):
        await orch.run(
            ctx,
            user=MagicMock(user_id="u"),
            report_id="r",
            factory_id="f",
            tenant_schema="t",
        )


@pytest.mark.asyncio
async def test_d4_stage5_runs_knowledge_entry_extra():
    from app.services.llm_fusion_layer import LLMOutcome

    orch = RecommendationOrchestrator(MagicMock(), MagicMock(), MagicMock())
    orch.llm_layer.enrich = AsyncMock(
        side_effect=lambda cands, ctx: LLMOutcome(candidates=list(cands), attempted=0)
    )

    ll_cand = RecommendationCandidate(
        source="lessons_learned",
        content="经验教训",
        category=None,
        confidence=0.8,
        match_reason="ll",
        metadata={"marker": "lessons_learned"},
    )
    ke_cand = RecommendationCandidate(
        source="knowledge_entry",
        content="知识条目",
        category=None,
        confidence=0.7,
        match_reason="知识库命中",
        metadata={"marker": "knowledge_entry", "entry_id": str(uuid.uuid4())},
    )
    orch._sources["lessons_learned"] = _async_stub_source(ll_cand)
    orch._sources["knowledge_entry"] = _async_stub_source(ke_cand)

    ctx = RecommendationContext(
        capa_data={
            "d2_description": "螺栓尺寸超差",
            "d4_root_cause": "",
            "product_line_code": "DC-DC-100",
            "report_id": str(uuid.uuid4()),
        },
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=uuid.uuid4(),
    )
    result = await orch.run(
        ctx,
        user=MagicMock(user_id="u"),
        report_id="r",
        factory_id="f",
        tenant_schema="t",
    )
    s5 = next(s for s in result.stages if s.index == 5)
    assert s5.status == "done"
    assert s5.hit_count == 2
    markers = {c.metadata.get("marker") for c in result.items}
    assert "lessons_learned" in markers
    assert "knowledge_entry" in markers
