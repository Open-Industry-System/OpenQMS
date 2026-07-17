"""embedding_sync_worker capa_lesson + factory_id 写入测试（Task 13）。

R14：worker 支持与首次 enqueue 同 commit 落地。
R15：upsert_embeddings INSERT 含 factory_id 列。
R16：fmea_node 分支也带 factory_id（回归）。
R17：6 元组 table_field_map，所有 entity_type 都写 factory_id。
R18：capa 通用路径回归（5→6 元组改造后）。
R9：capa_lesson upsert 前重查存在性，已删则丢弃。
"""
import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.models.capa import CAPAEightD
from app.models.capa_lesson import CapaLessonLearned
from app.models.document_embedding import DocumentEmbedding, EmbeddingSyncOutbox
from app.models.fmea import FMEADocument
from app.services.embedding_sync_worker import mark_failed, process_batch_once

pytestmark = pytest.mark.requires_db


async def _embedding_column_exists(db) -> tuple[bool, int | None]:
    """Return (exists, atttypmod) for document_embeddings.embedding vector column."""
    row = await db.execute(
        text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid='document_embeddings'::regclass AND attname='embedding'"
        )
    )
    r = row.fetchone()
    if r is None or r[0] in (None, 0, -1):
        return False, None
    return True, r[0]


@pytest_asyncio.fixture
async def vector_db(db):
    """Skip module tests if the test DB lacks the pgvector embedding column.
    Returns (db, dimensions) so the fake provider can match the table vector dim."""
    exists, dim = await _embedding_column_exists(db)
    if not exists:
        pytest.skip("document_embeddings.embedding vector column not available")
    return db, dim


class _FakeProvider:
    """Mock embedding provider — returns fixed vectors matching table dims, no network."""

    def __init__(self, dimensions: int = 1536):
        self._model = "fake-test-model"
        self._dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self._dimensions for _ in texts]

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def aclose(self):
        pass


async def _seed_outbox(
    db,
    entity_type,
    entity_id,
    *,
    factory_id,
    product_line_code="DC-DC-100",
    content_hash=None,
    retry_count=0,
    max_attempts=5,
):
    """Insert a pending embedding_sync_outbox event directly."""
    await db.execute(
        text(
            "INSERT INTO embedding_sync_outbox "
            "(id, entity_type, entity_id, product_line_code, factory_id, status, "
            " next_attempt_at, content_hash, retry_count, max_attempts) "
            "VALUES (gen_random_uuid(), :et, :eid, :plc, :fid, 'pending', NOW(), "
            " :ch, :rc, :ma)"
        ),
        {
            "et": entity_type,
            "eid": entity_id,
            "plc": product_line_code,
            "fid": factory_id,
            "ch": content_hash,
            "rc": retry_count,
            "ma": max_attempts,
        },
    )
    await db.flush()


async def _seed_knowledge_entry(
    db,
    *,
    factory_id,
    entry_id=None,
    content_hash="h1" * 32,
    embedding_text="lesson summary for knowledge entry embedding",
    embedding_status="pending",
):
    from app.models.knowledge_entry import KnowledgeEntry

    eid = entry_id or uuid.uuid4()
    entry = KnowledgeEntry(
        entry_id=eid,
        source_type="capa",
        source_id=uuid.uuid4(),
        factory_id=factory_id,
        product_line_code="DC-DC-100",
        document_no=f"8D-KNOW-{uuid.uuid4().hex[:6]}",
        title="knowledge entry title",
        severity="一般",
        fields={"lesson_summary": embedding_text, "tags": ["a", "b", "c"]},
        status="active",
        llm_status="done",
        embedding_text=embedding_text,
        content_hash=content_hash,
        embedding_status=embedding_status,
        embedding_id=None,
    )
    db.add(entry)
    await db.flush()
    return entry


# ── capa_lesson 处理 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_worker_processes_capa_lesson(vector_db, default_factory, admin_user):
    db, dim = vector_db
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-LESSON-WORK-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        created_by=admin_user.user_id,
        status="D8_CLOSURE",
        d7_prevention="预防内容",
    )
    db.add(capa)
    await db.flush()
    lesson_id = uuid.uuid5(uuid.NAMESPACE_URL, "capa_lesson:test:capa_lesson_worker")
    lesson = CapaLessonLearned(
        lesson_id=lesson_id,
        capa_id=capa.report_id,
        factory_id=default_factory.id,
        product_line_code="DC-DC-100",
        lesson_text="防呆工装避免误装。",
        lesson_text_normalized="防呆工装避免误装。",
        category="prevention",
        source_d_step="d7",
        tags=[],
    )
    db.add(lesson)
    await db.flush()
    await _seed_outbox(db, "capa_lesson", lesson_id, factory_id=default_factory.id)

    provider = _FakeProvider(dimensions=dim)
    await process_batch_once(db, provider)

    de = await db.scalar(
        select(DocumentEmbedding).where(
            DocumentEmbedding.entity_type == "capa_lesson",
            DocumentEmbedding.entity_id == lesson_id,
        )
    )
    assert de is not None
    assert de.entity_field == "lesson_text"
    # R17：显式断言 factory_id 写入（非空 + 正确工厂）
    assert de.factory_id == default_factory.id


@pytest.mark.asyncio
async def test_worker_skips_deleted_lesson(vector_db, default_factory, admin_user):
    db, dim = vector_db
    lesson_id = uuid.uuid5(uuid.NAMESPACE_URL, "capa_lesson:test:skip_deleted")
    # 不创建 lesson 行（模拟 lesson 已被删），只 seed outbox 事件
    await _seed_outbox(db, "capa_lesson", lesson_id, factory_id=default_factory.id)

    provider = _FakeProvider(dimensions=dim)
    await process_batch_once(db, provider)

    de = await db.scalar(
        select(DocumentEmbedding).where(DocumentEmbedding.entity_type == "capa_lesson")
    )
    assert de is None  # R9：不写 stale embedding


# ── R16: fmea_node 回归 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_worker_processes_fmea_node_factory_id(vector_db, default_factory, admin_user):
    db, dim = vector_db
    fmea_id = uuid.uuid4()
    graph = {
        "nodes": [
            {"id": "fm-1", "type": "FailureMode", "name": "虚焊",
             "description": "焊点虚焊", "requirement": "", "specification": ""},
        ],
        "edges": [],
    }
    fmea = FMEADocument(
        fmea_id=fmea_id,
        document_no=f"PFMEA-WORK-{uuid.uuid4().hex[:6]}",
        title="t",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="draft",
        created_by=admin_user.user_id,
        graph_data=graph,
    )
    db.add(fmea)
    await db.flush()
    await _seed_outbox(db, "fmea_node", fmea_id, factory_id=default_factory.id)

    provider = _FakeProvider(dimensions=dim)
    await process_batch_once(db, provider)

    de = await db.scalar(
        select(DocumentEmbedding).where(
            DocumentEmbedding.entity_type == "fmea_node",
            DocumentEmbedding.entity_id == fmea_id,
        )
    )
    assert de is not None
    assert de.factory_id == default_factory.id


# ── mark_failed error path (regression: events must not be left in processing) ──


@pytest.mark.asyncio
async def test_worker_mark_failed_on_embed_error(vector_db, default_factory, admin_user):
    db, dim = vector_db
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-FAIL-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        created_by=admin_user.user_id,
        status="D8_CLOSURE",
        d7_prevention="预防内容",
    )
    db.add(capa)
    await db.flush()
    await _seed_outbox(db, "capa", capa.report_id, factory_id=default_factory.id)

    class _FailingProvider(_FakeProvider):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("embed failed")

    provider = _FailingProvider(dimensions=dim)
    await process_batch_once(db, provider)

    row = await db.execute(
        text("SELECT status, retry_count, last_error FROM embedding_sync_outbox WHERE entity_id = :eid"),
        {"eid": capa.report_id},
    )
    event = row.fetchone()
    assert event is not None
    assert event[0] != "processing"
    assert event[1] == 1
    assert event[2] is not None
    assert "embed failed" in event[2]


# ── R18: capa 通用路径回归 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_worker_processes_capa_factory_id(vector_db, default_factory, admin_user):
    db, dim = vector_db
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-WORK-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        created_by=admin_user.user_id,
        status="D8_CLOSURE",
        d2_description="描述内容",
        d4_root_cause="根因内容",
        d5_correction="纠正内容",
        d7_prevention="预防内容",
    )
    db.add(capa)
    await db.flush()
    await _seed_outbox(db, "capa", capa.report_id, factory_id=default_factory.id)

    provider = _FakeProvider(dimensions=dim)
    await process_batch_once(db, provider)

    de = await db.scalar(
        select(DocumentEmbedding).where(
            DocumentEmbedding.entity_type == "capa",
            DocumentEmbedding.entity_id == capa.report_id,
        )
    )
    assert de is not None
    assert de.factory_id == default_factory.id


# ── knowledge_entry (US-E2E-01.8 Task 2) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_persists_content_hash(db, default_factory):
    from app.services.embedding_outbox import enqueue_embedding

    eid = uuid.uuid4()
    await enqueue_embedding(
        db, "knowledge_entry", eid, "DC-DC-100", default_factory.id, content_hash="abc"
    )
    await db.commit()
    row = await db.execute(
        text("SELECT content_hash FROM embedding_sync_outbox WHERE entity_id=:e"),
        {"e": eid},
    )
    assert row.scalar() == "abc"


@pytest.mark.asyncio
async def test_worker_ready_and_stale_hash(vector_db, default_factory, admin_user):
    db, dim = vector_db
    h1 = "a" * 64
    h0 = "b" * 64
    entry = await _seed_knowledge_entry(
        db,
        factory_id=default_factory.id,
        content_hash=h1,
        embedding_text="ready path knowledge text",
    )
    await _seed_outbox(
        db,
        "knowledge_entry",
        entry.entry_id,
        factory_id=default_factory.id,
        content_hash=h1,
    )

    provider = _FakeProvider(dimensions=dim)
    await process_batch_once(db, provider)

    await db.refresh(entry)
    assert entry.embedding_status == "ready"
    assert entry.embedding_id is not None

    de = await db.scalar(
        select(DocumentEmbedding).where(
            DocumentEmbedding.entity_type == "knowledge_entry",
            DocumentEmbedding.entity_id == entry.entry_id,
        )
    )
    assert de is not None
    assert de.id == entry.embedding_id
    assert de.chunk_text == "ready path knowledge text"
    assert de.factory_id == default_factory.id
    first_updated = de.updated_at

    # Stale outbox: entry stays at H1, event carries H0 → complete without overwrite
    await _seed_outbox(
        db,
        "knowledge_entry",
        entry.entry_id,
        factory_id=default_factory.id,
        content_hash=h0,
    )
    await process_batch_once(db, provider)

    await db.refresh(entry)
    assert entry.embedding_status == "ready"
    assert entry.embedding_id == de.id

    de2 = await db.scalar(
        select(DocumentEmbedding).where(
            DocumentEmbedding.entity_type == "knowledge_entry",
            DocumentEmbedding.entity_id == entry.entry_id,
        )
    )
    assert de2 is not None
    assert de2.id == de.id
    assert de2.chunk_text == "ready path knowledge text"
    assert de2.updated_at == first_updated

    stale_status = await db.scalar(
        text(
            "SELECT status FROM embedding_sync_outbox "
            "WHERE entity_id = :eid AND content_hash = :h"
        ),
        {"eid": entry.entry_id, "h": h0},
    )
    assert stale_status == "completed"


@pytest.mark.asyncio
async def test_worker_dead_letter_marks_failed(vector_db, default_factory, admin_user):
    db, dim = vector_db
    h1 = "c" * 64
    entry = await _seed_knowledge_entry(
        db,
        factory_id=default_factory.id,
        content_hash=h1,
        embedding_text="dead letter knowledge text",
    )
    await _seed_outbox(
        db,
        "knowledge_entry",
        entry.entry_id,
        factory_id=default_factory.id,
        content_hash=h1,
        retry_count=4,
        max_attempts=5,
    )

    class _FailingProvider(_FakeProvider):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("embed failed")

    provider = _FailingProvider(dimensions=dim)
    await process_batch_once(db, provider)

    await db.refresh(entry)
    assert entry.embedding_status == "failed"
    assert entry.embedding_id is None

    event = (
        await db.execute(
            text(
                "SELECT status, retry_count, last_error FROM embedding_sync_outbox "
                "WHERE entity_id = :eid"
            ),
            {"eid": entry.entry_id},
        )
    ).fetchone()
    assert event is not None
    assert event[0] == "dead_letter"
    assert event[1] == 5
    assert "embed failed" in (event[2] or "")


@pytest.mark.asyncio
async def test_worker_dead_letter_stale_hash_does_not_mark_failed(
    vector_db, default_factory, admin_user
):
    """Old-hash dead_letter must not flip a newer resink entry to failed."""
    db, _dim = vector_db
    old_hash = ("e" * 64)
    new_hash = ("f" * 64)
    entry = await _seed_knowledge_entry(
        db,
        factory_id=default_factory.id,
        content_hash=new_hash,  # entry already resunk to new content
        embedding_text="newer content after resink",
        embedding_status="pending",
    )
    event_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO embedding_sync_outbox "
            "(id, entity_type, entity_id, product_line_code, factory_id, status, "
            " next_attempt_at, content_hash, retry_count, max_attempts) "
            "VALUES (:id, 'knowledge_entry', :eid, 'DC-DC-100', :fid, 'processing', "
            " NOW(), :ch, 4, 5)"
        ),
        {
            "id": event_id,
            "eid": entry.entry_id,
            "fid": default_factory.id,
            "ch": old_hash,
        },
    )
    await db.flush()

    await mark_failed(
        db,
        str(event_id),
        "stale event embed failed",
        retry_count=4,
        max_attempts=5,
        entity_type="knowledge_entry",
        entity_id=entry.entry_id,
        content_hash=old_hash,
    )

    await db.refresh(entry)
    # Entry stays pending — old-hash dead_letter must not flip newer entry
    assert entry.embedding_status == "pending"
    assert entry.content_hash == new_hash

    event = (
        await db.execute(
            text(
                "SELECT status FROM embedding_sync_outbox WHERE id = :id"
            ),
            {"id": event_id},
        )
    ).fetchone()
    assert event is not None
    assert event[0] == "dead_letter"


@pytest.mark.asyncio
async def test_worker_transient_fail_keeps_pending(vector_db, default_factory, admin_user):
    db, dim = vector_db
    h1 = "d" * 64
    entry = await _seed_knowledge_entry(
        db,
        factory_id=default_factory.id,
        content_hash=h1,
        embedding_text="transient fail knowledge text",
    )
    await _seed_outbox(
        db,
        "knowledge_entry",
        entry.entry_id,
        factory_id=default_factory.id,
        content_hash=h1,
        retry_count=0,
        max_attempts=5,
    )

    class _FailingProvider(_FakeProvider):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("transient embed failed")

    provider = _FailingProvider(dimensions=dim)
    await process_batch_once(db, provider)

    await db.refresh(entry)
    assert entry.embedding_status == "pending"
    assert entry.embedding_id is None

    event = (
        await db.execute(
            text(
                "SELECT status, retry_count FROM embedding_sync_outbox WHERE entity_id = :eid"
            ),
            {"eid": entry.entry_id},
        )
    ).fetchone()
    assert event is not None
    assert event[0] == "pending"
    assert event[1] == 1