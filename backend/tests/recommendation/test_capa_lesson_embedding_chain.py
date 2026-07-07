"""CAPA lesson embedding chain integration tests (Task 15).

End-to-end verification of the full chain:
  _extract_lessons / _extract_d8_with_cleanup
  -> enqueue_embedding
  -> embedding_sync_worker.process_batch_once
  -> document_embeddings
  -> LessonsLearnedSource.retrieve
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, text

from app.models.capa import CAPAEightD
from app.models.capa_lesson import CapaLessonLearned
from app.models.document_embedding import DocumentEmbedding, EmbeddingSyncOutbox
from app.services.capa_service import advance_capa, update_capa
from app.services.embedding_sync_worker import process_batch_once
from app.services.recommendation_sources_extra import LessonsLearnedSource
from app.services.recommendation_types import RecommendationContext

pytestmark = pytest.mark.requires_db


async def _embedding_dim(db) -> int | None:
    """Return pgvector dimension for document_embeddings.embedding, or None if unavailable."""
    result = await db.execute(text("""
        SELECT atttypmod FROM pg_attribute
        WHERE attrelid = 'document_embeddings'::regclass AND attname = 'embedding'
    """))
    row = result.fetchone()
    return row[0] if row else None


def _make_provider(dim: int):
    """Return a mock embedding provider that returns a unit vector per input text."""
    provider = MagicMock()
    # unit vector: all components equal, L2 norm = 1
    value = 1.0 / (dim ** 0.5)
    provider.embed = AsyncMock(side_effect=lambda texts: [[value] * dim for _ in texts])
    provider.model_name = "test-model"
    return provider


async def _make_capa(
    db,
    factory_id,
    user_id,
    status="D7_PREVENTION",
    d7_prevention=None,
    d8_closure=None,
):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-LESSON-{uuid.uuid4().hex[:6]}",
        title="Lesson chain test",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        created_by=user_id,
        status=status,
        d7_prevention=d7_prevention,
        d8_closure=d8_closure,
    )
    db.add(capa)
    await db.flush()
    await db.refresh(capa)
    return capa


@pytest.mark.asyncio
async def test_capa_lesson_chain_d7_to_retrieval(db, default_factory, admin_user):
    """D7 lessons are extracted on D7->D8 advance, embedded, and retrieved."""
    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present (pgvector schema not available)")

    d7_text = "预防螺栓尺寸超差。增加首检频次。"
    capa = await _make_capa(
        db,
        default_factory.id,
        admin_user.user_id,
        status="D7_PREVENTION",
        d7_prevention=d7_text,
    )

    # No linked FMEA -> D7 gate trivially passes; advance extracts d7 lessons.
    advanced = await advance_capa(db, capa, admin_user.user_id)
    assert advanced.status == "D8_CLOSURE"

    lessons = (
        await db.execute(
            select(CapaLessonLearned).where(
                CapaLessonLearned.capa_id == capa.report_id,
                CapaLessonLearned.source_d_step == "d7",
                CapaLessonLearned.factory_id == default_factory.id,
            )
        )
    ).scalars().all()
    assert len(lessons) == 2
    lesson_ids = {str(l.lesson_id) for l in lessons}
    lesson_texts = {l.lesson_text for l in lessons}
    assert "预防螺栓尺寸超差" in lesson_texts
    assert "增加首检频次" in lesson_texts

    outbox = (
        await db.execute(
            select(EmbeddingSyncOutbox).where(
                EmbeddingSyncOutbox.entity_type == "capa_lesson",
                EmbeddingSyncOutbox.entity_id.in_([l.lesson_id for l in lessons]),
                EmbeddingSyncOutbox.factory_id == default_factory.id,
            )
        )
    ).scalars().all()
    assert len(outbox) == 2
    assert all(o.status == "pending" for o in outbox)

    provider = _make_provider(dim)
    await process_batch_once(db, provider)

    embeddings = (
        await db.execute(
            select(DocumentEmbedding).where(
                DocumentEmbedding.entity_type == "capa_lesson",
                DocumentEmbedding.entity_id.in_([l.lesson_id for l in lessons]),
                DocumentEmbedding.entity_field == "lesson_text",
                DocumentEmbedding.factory_id == default_factory.id,
            )
        )
    ).scalars().all()
    assert len(embeddings) == 2
    assert all(e.embedding_model == "test-model" for e in embeddings)

    ctx = RecommendationContext(
        capa_data={
            "d2_description": "螺栓尺寸超差",
            "product_line_code": "DC-DC-100",
            "report_id": capa.report_id,
        },
        stage="d4",
        factory_id=default_factory.id,
        user_product_lines=["DC-DC-100"],
    )
    cands = await LessonsLearnedSource(db, provider).retrieve(ctx)
    assert len(cands) > 0
    assert all(c.source == "lessons_learned" for c in cands)
    returned_capa_ids = {c.metadata.get("source_capa_id") for c in cands}
    assert str(capa.report_id) in returned_capa_ids
    returned_lesson_ids = {c.metadata.get("lesson_id") for c in cands}
    assert returned_lesson_ids & lesson_ids
    assert all(c.metadata.get("factory_id") == str(default_factory.id) for c in cands)
    assert any("预防螺栓尺寸超差" in c.content for c in cands)


@pytest.mark.asyncio
async def test_capa_lesson_chain_d8_edit_to_retrieval(db, default_factory, admin_user):
    """d8_closure edits delete-and-rebuild d8 lessons + embeddings; stale text no longer hits."""
    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present (pgvector schema not available)")

    capa = await _make_capa(
        db,
        default_factory.id,
        admin_user.user_id,
        status="D8_CLOSURE",
    )

    d8_text = "更新作业指导书。培训操作员。"
    await update_capa(db, capa, {"d8_closure": d8_text}, admin_user.user_id)

    lessons = (
        await db.execute(
            select(CapaLessonLearned).where(
                CapaLessonLearned.capa_id == capa.report_id,
                CapaLessonLearned.source_d_step == "d8",
                CapaLessonLearned.factory_id == default_factory.id,
            )
        )
    ).scalars().all()
    assert len(lessons) == 2
    initial_lesson_ids = {l.lesson_id for l in lessons}

    provider = _make_provider(dim)
    await process_batch_once(db, provider)

    embeddings_initial = (
        await db.execute(
            select(DocumentEmbedding).where(
                DocumentEmbedding.entity_type == "capa_lesson",
                DocumentEmbedding.entity_id.in_(initial_lesson_ids),
                DocumentEmbedding.factory_id == default_factory.id,
            )
        )
    ).scalars().all()
    assert len(embeddings_initial) == 2

    # Edit d8_closure: remove the training sentence.
    d8_text_edited = "更新作业指导书。"
    await update_capa(db, capa, {"d8_closure": d8_text_edited}, admin_user.user_id)

    lessons_after = (
        await db.execute(
            select(CapaLessonLearned).where(
                CapaLessonLearned.capa_id == capa.report_id,
                CapaLessonLearned.source_d_step == "d8",
                CapaLessonLearned.factory_id == default_factory.id,
            )
        )
    ).scalars().all()
    assert len(lessons_after) == 1
    kept_lesson = lessons_after[0]
    assert kept_lesson.lesson_text == "更新作业指导书"

    # Old embeddings for the deleted lesson should have been cleaned up.
    embeddings_old = (
        await db.execute(
            select(DocumentEmbedding).where(
                DocumentEmbedding.entity_type == "capa_lesson",
                DocumentEmbedding.entity_id.in_(initial_lesson_ids),
                DocumentEmbedding.factory_id == default_factory.id,
            )
        )
    ).scalars().all()
    assert len(embeddings_old) == 0

    # Process the new pending outbox event.
    await process_batch_once(db, provider)

    embeddings_after = (
        await db.execute(
            select(DocumentEmbedding).where(
                DocumentEmbedding.entity_type == "capa_lesson",
                DocumentEmbedding.entity_id == kept_lesson.lesson_id,
                DocumentEmbedding.entity_field == "lesson_text",
                DocumentEmbedding.factory_id == default_factory.id,
            )
        )
    ).scalars().all()
    assert len(embeddings_after) == 1

    # Query matching the kept text: should return the kept lesson.
    ctx_kept = RecommendationContext(
        capa_data={
            "d2_description": "更新作业指导书",
            "product_line_code": "DC-DC-100",
            "report_id": capa.report_id,
        },
        stage="d4",
        factory_id=default_factory.id,
        user_product_lines=["DC-DC-100"],
    )
    cands_kept = await LessonsLearnedSource(db, provider).retrieve(ctx_kept)
    assert len(cands_kept) > 0
    assert any(c.metadata.get("lesson_id") == str(kept_lesson.lesson_id) for c in cands_kept)

    # Query matching the deleted text: the deleted lesson_id must not be returned.
    ctx_deleted = RecommendationContext(
        capa_data={
            "d2_description": "培训操作员",
            "product_line_code": "DC-DC-100",
            "report_id": capa.report_id,
        },
        stage="d4",
        factory_id=default_factory.id,
        user_product_lines=["DC-DC-100"],
    )
    cands_deleted = await LessonsLearnedSource(db, provider).retrieve(ctx_deleted)
    deleted_lesson_ids = {str(lid) for lid in initial_lesson_ids if lid != kept_lesson.lesson_id}
    returned_deleted_lesson_ids = {
        c.metadata.get("lesson_id") for c in cands_deleted
    }
    assert not (returned_deleted_lesson_ids & deleted_lesson_ids), (
        "deleted lesson_id should not appear in retrieve results"
    )
