"""CAPA lessons 抽取服务（Task 13 + Task 14）。

从 d7_prevention / d8_closure 文本切句、去重、启发式分类、upsert 到 capa_lessons_learned，
并为每条 lesson enqueue embedding outbox 事件（同事务，savepoint 包裹，fail-closed）。
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa_lesson import CapaLessonLearned
from app.services.embedding_outbox import enqueue_embedding


async def _extract_d8_with_cleanup(
    db: AsyncSession,
    capa,
    new_d8_closure: str,
) -> list[CapaLessonLearned]:
    """d8_closure 更新时 delete-and-rebuild d8 lessons（savepoint + embedding 清理 + fail-closed）。

    R4+R13: 传 new_d8_closure 文本，不先 mutate capa.d8_closure。
    任意步骤失败 → savepoint rollback，旧 d8 lessons 集合保持不变，capa.d8_closure 未被修改。
    """
    capa_id = capa.report_id
    factory_id = capa.factory_id

    try:
        async with db.begin_nested():
            # ① 取旧 d8 lesson_ids
            result = await db.execute(
                text("""
                    SELECT lesson_id FROM capa_lessons_learned
                    WHERE capa_id = :capa_id AND source_d_step = 'd8' AND factory_id = :factory_id
                """),
                {"capa_id": capa_id, "factory_id": factory_id},
            )
            old_ids = [row[0] for row in result.fetchall()]

            if old_ids:
                # ② 取消 pending outbox 事件（Fix 5：真实表名 embedding_sync_outbox）
                await db.execute(
                    text("""
                        UPDATE embedding_sync_outbox
                        SET status = 'cancelled'
                        WHERE entity_type = 'capa_lesson' AND entity_id = ANY(:ids) AND status = 'pending'
                    """),
                    {"ids": old_ids},
                )
                # ③ 删除旧 embeddings
                await db.execute(
                    text("""
                        DELETE FROM document_embeddings
                        WHERE entity_type = 'capa_lesson' AND entity_id = ANY(:ids)
                    """),
                    {"ids": old_ids},
                )
                # ④ 删除旧 d8 lesson 行
                await db.execute(
                    text("""
                        DELETE FROM capa_lessons_learned
                        WHERE capa_id = :capa_id AND source_d_step = 'd8' AND factory_id = :factory_id
                    """),
                    {"capa_id": capa_id, "factory_id": factory_id},
                )

            # ⑤ 用新文本重新抽取（R13：text_override 传新文本，不读 capa.d8_closure）
            lessons = await _extract_lessons(db, capa, "d8", text_override=new_d8_closure)

            # ⑥ 写 LESSON_EXTRACTED 审计
            db.add(AuditLog(
                table_name="capa_eightd",
                record_id=capa_id,
                action="LESSON_EXTRACTED",
                changed_fields={"source_d_step": "d8"},
                operated_by=None,
                factory_id=factory_id,
                correlation_id=uuid.uuid5(
                    uuid.NAMESPACE_URL, f"lesson_extract_d8:{capa_id}"
                ),
            ))
        return lessons
    except Exception as exc:
        # savepoint 已 rollback；fail-closed：阻止 d8_closure 字段 mutation
        raise ValueError("D8 lessons 抽取失败，无法保存闭环总结，请重试") from exc


async def _extract_lessons(
    db: AsyncSession,
    capa,
    source_d_step: str,
    text_override: str | None = None,
) -> list[CapaLessonLearned]:
    """从 capa 抽取 lessons 并 upsert + enqueue embedding。

    text_override 非 None → 用它（Task 14 d8 抽取传新 d8_closure，不 mutate capa 字段）；
    None → 读 capa.d7_prevention（source_d_step="d7"）或 capa.d8_closure（="d8"）。
    """
    if text_override is not None:
        raw = text_override
    elif source_d_step == "d7":
        raw = capa.d7_prevention or ""
    elif source_d_step == "d8":
        raw = capa.d8_closure or ""
    else:
        raise ValueError(f"unsupported source_d_step: {source_d_step}")

    sentences = _split_sentences(raw)
    if not sentences:
        return []

    capa_id = capa.report_id
    factory_id = capa.factory_id
    product_line_code = capa.product_line_code

    seen: dict[str, str] = {}  # normalized -> sentence
    for s in sentences:
        norm = _normalize(s)
        if not norm or norm in seen:
            continue
        seen[norm] = s

    lessons: list[CapaLessonLearned] = []
    for norm, sentence in seen.items():
        lesson_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"capa_lesson:{capa_id}:{source_d_step}:{norm}",
        )
        category = _category_for(sentence)
        values = {
            "lesson_id": lesson_id,
            "capa_id": capa_id,
            "factory_id": factory_id,
            "product_line_code": product_line_code,
            "lesson_text": sentence,
            "lesson_text_normalized": norm,
            "category": category,
            "source_d_step": source_d_step,
            "tags": [],
        }
        stmt = pg_insert(CapaLessonLearned).values(**values).on_conflict_do_update(
            index_elements=["lesson_id"],
            set_={
                "category": category,
                "tags": [],
                "updated_at": datetime.now(UTC),
            },
        )
        await db.execute(stmt)
        # enqueue_embedding BEFORE savepoint exit / commit（防 outbox 行丢失）
        await enqueue_embedding(db, "capa_lesson", lesson_id, product_line_code, factory_id)
        lessons.append(
            CapaLessonLearned(
                lesson_id=lesson_id,
                capa_id=capa_id,
                factory_id=factory_id,
                product_line_code=product_line_code,
                lesson_text=sentence,
                lesson_text_normalized=norm,
                category=category,
                source_d_step=source_d_step,
                tags=[],
            )
        )
    return lessons


def _split_sentences(text: str) -> list[str]:
    """按句号 / 换行切句，过滤空句。"""
    if not text:
        return []
    parts: list[str] = []
    for chunk in text.replace("\r\n", "\n").split("\n"):
        for s in chunk.split("。"):
            s = s.strip()
            if s:
                parts.append(s)
    return parts


def _normalize(text: str) -> str:
    return "".join(text.lower().split())


def _category_for(text: str) -> str:
    low = text.lower()
    if any(k in low for k in ("预防", "防呆", "poka")):
        return "prevention"
    if any(k in low for k in ("检测", "探测", "检验")):
        return "detection"
    if any(k in low for k in ("体系", "流程", "制度")):
        return "systemic"
    return "process"
