"""CAPA lessons 抽取服务（Task 13）。

从 d7_prevention / d8_closure 文本切句、去重、启发式分类、upsert 到 capa_lessons_learned，
并为每条 lesson enqueue embedding outbox 事件（同事务，savepoint 包裹，fail-closed）。
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capa_lesson import CapaLessonLearned
from app.services.embedding_outbox import enqueue_embedding


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