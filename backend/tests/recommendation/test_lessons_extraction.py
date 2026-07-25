"""D7 + D8 lessons 抽取测试（Task 13 + Task 14）。

advance_capa D7_PREVENTION → D8_CLOSURE 在闸口（Task 12）通过后、状态 mutation 前
于 savepoint 内抽 d7_prevention lessons，fail-closed：抽取失败 → savepoint rollback
+ 状态未 mutate + 无 TRANSITION audit + 无 lesson 行。

update_capa 修改 d8_closure 且 status=D8_CLOSURE 时，savepoint 内 delete-and-rebuild
d8 lessons + 清理旧 embedding/outbox，fail-closed：抽取失败 → 旧 lessons 集合完全不变。
"""
import uuid

import pytest
from sqlalchemy import select, text

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.capa_lesson import CapaLessonLearned
from app.models.document_embedding import DocumentEmbedding
from app.schemas.capa import AdvanceRequest
from app.services.capa_service import advance_capa, update_capa
from app.services.embedding_sync_worker import fetch_chunks, process_batch_once, upsert_embeddings

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, *, d7_prevention="", d8_closure=None, status="D7_PREVENTION"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-LESSON-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        created_by=user_id,
        status=status,
        d5_correction="措施A",
        d7_prevention=d7_prevention,
        d8_closure=d8_closure,
    )
    db.add(capa)
    await db.flush()
    return capa


@pytest.mark.asyncio
async def test_d7_lessons_extracted_on_advance(db, default_factory, admin_user):
    # 无 FMEA → 闸口平凡通过 → 抽 d7_prevention lessons
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        d7_prevention="更新防呆工装避免误装。\n增加检测工序识别偏移。完善流程制度。",
    )
    advanced = await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))
    assert advanced.status == "D7_COMPLETED"

    lessons = (
        await db.execute(
            select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id)
        )
    ).scalars().all()
    assert lessons and all(l.source_d_step == "d7" for l in lessons)
    # 三句非空 → 至少 3 条 lesson
    assert len(lessons) >= 3
    # category 启发式覆盖
    cats = {l.category for l in lessons}
    assert "prevention" in cats  # "防呆"
    assert "detection" in cats  # "检测"
    assert "systemic" in cats  # "流程制度"


@pytest.mark.asyncio
async def test_d7_extraction_failure_blocks_transition(db, default_factory, admin_user, monkeypatch):
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        d7_prevention="预防性措施一。\n预防性措施二。",
    )

    from app.services import capa_lessons_service as svc

    async def _boom(*a, **kw):
        raise RuntimeError("enqueue failed")

    monkeypatch.setattr(svc, "enqueue_embedding", _boom)

    with pytest.raises(ValueError, match="D7 lessons 抽取失败"):
        await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))

    # R4：重查 DB（非仅内存对象）确认状态未推进 + 无 TRANSITION audit + 无 lesson 行
    await db.refresh(capa)
    assert capa.status == "D7_PREVENTION"
    audits = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == capa.report_id,
                AuditLog.action == "TRANSITION",
            )
        )
    ).scalars().all()
    assert len(audits) == 0
    lessons = (
        await db.execute(
            select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id)
        )
    ).scalars().all()
    assert len(lessons) == 0


@pytest.mark.asyncio
async def test_d7_no_d8_closure_extracted(db, default_factory, admin_user):
    # D7→D8 时 d8_closure 为空 → 不产 source_d_step='d8' 行
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        d7_prevention="预防措施。\n检测措施。",
    )
    capa.d8_closure = None
    await db.flush()

    advanced = await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))
    assert advanced.status == "D7_COMPLETED"

    lessons = (
        await db.execute(
            select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id)
        )
    ).scalars().all()
    assert lessons  # d7 lessons 有
    assert not any(l.source_d_step == "d8" for l in lessons)


# ── D8 delete-and-rebuild 测试（Task 14）────────────────────────────────────


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


@pytest.mark.asyncio
async def test_d8_lessons_delete_and_rebuild(db, default_factory, admin_user):
    # 进 D8 + 填 d8_closure 2 句保存 → 2 行 d8 lesson；改 d8_closure（删1改1加1）→ 行数=新句数，旧句 delete
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        status="D8_CLOSURE", d8_closure="初始占位。",
    )
    await update_capa(db, capa, {"d8_closure": "旧经验第一句。旧经验第二句。"}, admin_user.user_id)
    old = {(l.lesson_id, l.lesson_text) for l in (await db.execute(
        select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id,
                                         CapaLessonLearned.source_d_step == "d8"))).scalars().all()}
    assert len(old) == 2

    await update_capa(db, capa, {"d8_closure": "旧经验第一句已修改。全新经验第三句。"}, admin_user.user_id)

    lessons = (await db.execute(
        select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id,
                                         CapaLessonLearned.source_d_step == "d8"))).scalars().all()
    assert len(lessons) == 2
    texts = {l.lesson_text for l in lessons}
    assert texts == {"旧经验第一句已修改", "全新经验第三句"}
    # 旧集合完全不应再存在
    assert not any((l.lesson_id, l.lesson_text) in old for l in lessons)


@pytest.mark.asyncio
async def test_d8_duplicate_sentences_deduped(db, default_factory, admin_user):
    # d8_closure 含重复句 → 去重后 1 行
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        status="D8_CLOSURE", d8_closure="占位。",
    )
    await update_capa(db, capa, {"d8_closure": "重复句。重复句。另一句。"}, admin_user.user_id)

    lessons = (await db.execute(
        select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id,
                                         CapaLessonLearned.source_d_step == "d8"))).scalars().all()
    assert len(lessons) == 2
    texts = {l.lesson_text for l in lessons}
    assert texts == {"重复句", "另一句"}


@pytest.mark.asyncio
async def test_d8_extraction_failure_blocks_save(db, default_factory, admin_user, monkeypatch):
    # 先 seed 旧 d8 lessons；mock enqueue_embedding 抛错 → 保存失败；断言旧 lessons 集合完全不变（非 len==0）
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        status="D8_CLOSURE", d8_closure="占位。",
    )
    await update_capa(db, capa, {"d8_closure": "旧经验A。旧经验B。"}, admin_user.user_id)
    old_lessons = {(l.lesson_id, l.lesson_text) for l in (await db.execute(
        select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id,
                                         CapaLessonLearned.source_d_step == "d8"))).scalars().all()}
    assert old_lessons

    from app.services import capa_lessons_service as svc

    async def _boom(*a, **kw):
        raise RuntimeError("enqueue failed")

    monkeypatch.setattr(svc, "enqueue_embedding", _boom)

    with pytest.raises(ValueError, match="D8 lessons 抽取失败"):
        await update_capa(db, capa, {"d8_closure": "新经验A。新经验B。"}, admin_user.user_id)

    # 重查 DB 确认 d8_closure 仍是旧值 + 旧 d8 lessons 集合完全相同（savepoint rollback 撤销 delete+rebuild）
    await db.refresh(capa)
    assert capa.d8_closure == "旧经验A。旧经验B。"
    new_lessons = {(l.lesson_id, l.lesson_text) for l in (await db.execute(
        select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id,
                                         CapaLessonLearned.source_d_step == "d8"))).scalars().all()}
    assert new_lessons == old_lessons


@pytest.mark.asyncio
async def test_d8_embedding_cleanup(db, default_factory, admin_user):
    # 删改 d8_closure 后，被删句的 document_embeddings（entity_type='capa_lesson'）行已清理
    exists, dim = await _embedding_column_exists(db)
    if not exists:
        pytest.skip("document_embeddings.embedding vector column not available")

    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        status="D8_CLOSURE", d8_closure="占位。",
    )
    await update_capa(db, capa, {"d8_closure": "将被删除的经验。保留的经验。"}, admin_user.user_id)

    # 修正测试库中 status 默认值的引号问题（真实 DB 默认值把 'pending' 存成了带引号字符串），
    # 让 worker 能认领这些事件并写入 embeddings。
    capa_lesson_ids = [l.lesson_id for l in (await db.execute(
        select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id,
                                         CapaLessonLearned.source_d_step == "d8"))).scalars().all()]
    await db.execute(
        text("""
            UPDATE embedding_sync_outbox
            SET status = 'pending'
            WHERE entity_type = 'capa_lesson' AND entity_id = ANY(:ids)
        """),
        {"ids": capa_lesson_ids},
    )
    await db.flush()

    provider = _FakeProvider(dim)
    await process_batch_once(db, provider)

    old_lessons = (await db.execute(
        select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id,
                                         CapaLessonLearned.source_d_step == "d8"))).scalars().all()
    old_ids = [l.lesson_id for l in old_lessons]
    assert old_ids

    old_embeddings = (await db.execute(
        select(DocumentEmbedding).where(DocumentEmbedding.entity_type == "capa_lesson",
                                          DocumentEmbedding.entity_id.in_(old_ids)))).scalars().all()
    assert len(old_embeddings) == len(old_ids)

    # 更新为完全不同的句子 → 旧 lesson_id 集合的 embeddings 应被清空
    await update_capa(db, capa, {"d8_closure": "完全不同的新经验。"}, admin_user.user_id)

    remaining = (await db.execute(
        select(DocumentEmbedding).where(DocumentEmbedding.entity_type == "capa_lesson",
                                          DocumentEmbedding.entity_id.in_(old_ids)))).scalars().all()
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_d8_inflight_worker_race(db, default_factory, admin_user):
    # 模拟 worker 已认领旧 lesson_id job（status='processing'）；cleanup 后 worker 完成 job 时重查 lesson 行不存在 → 丢弃不写 stale
    exists, dim = await _embedding_column_exists(db)
    if not exists:
        pytest.skip("document_embeddings.embedding vector column not available")

    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        status="D8_CLOSURE", d8_closure="占位。",
    )
    await update_capa(db, capa, {"d8_closure": "旧经验A。旧经验B。"}, admin_user.user_id)

    old_lessons = (await db.execute(
        select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id,
                                         CapaLessonLearned.source_d_step == "d8"))).scalars().all()
    assert len(old_lessons) == 2
    old_lesson_id = old_lessons[0].lesson_id

    # 模拟 worker 已认领该事件
    await db.execute(
        text("""
            INSERT INTO embedding_sync_outbox
            (id, entity_type, entity_id, product_line_code, factory_id, status, next_attempt_at)
            VALUES (gen_random_uuid(), 'capa_lesson', :eid, 'DC-DC-100', :fid, 'processing', NOW())
        """),
        {"eid": old_lesson_id, "fid": default_factory.id},
    )
    await db.flush()

    # cleanup 只取消 pending，不碰 processing；但它会删除 lesson 行与 embeddings
    await update_capa(db, capa, {"d8_closure": "完全不同的新经验。"}, admin_user.user_id)

    # 模拟 worker 完成旧事件：fetch_chunks 因 lesson 行不存在返回空
    event = {"entity_type": "capa_lesson", "entity_id": old_lesson_id,
             "product_line_code": "DC-DC-100", "retry_count": 0, "max_attempts": 5}
    chunks = await fetch_chunks(db, [event])
    assert not chunks

    # 再直接驱动 upsert_embeddings（带显式 re-check）也不会写 stale embedding
    provider = _FakeProvider(dim)
    chunk = {
        "entity_type": "capa_lesson",
        "entity_id": old_lesson_id,
        "node_id": None,
        "entity_field": "lesson_text",
        "chunk_text": "stale embedding text",
        "product_line_code": "DC-DC-100",
        "factory_id": default_factory.id,
        "metadata": {},
    }
    await upsert_embeddings(db, [chunk], [[0.1] * dim], provider.model_name)

    de = await db.scalar(
        select(DocumentEmbedding).where(
            DocumentEmbedding.entity_type == "capa_lesson",
            DocumentEmbedding.entity_id == old_lesson_id,
        )
    )
    assert de is None  # R9：不写 stale embedding