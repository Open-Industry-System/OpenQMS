"""US-E2E-01.8: CAPA knowledge sink on D8 close (fail-closed)."""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaD7NodeAction, CapaRootCauseVerification
from app.models.capa_d3 import CapaD3ImpactReport, CapaD3ImportRun
from app.models.knowledge_entry import KnowledgeEntry
from app.models.supplier_risk import SupplierRiskAlert
from app.services.agent import provider_adapter
from app.services.agent.provider_adapter import ProviderNotConfiguredError
from app.services.embedding_outbox import delete_embeddings_for_entity, enqueue_embedding

logger = logging.getLogger(__name__)

_FIELD_MAX_CHARS = 2000

_LLM_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["lesson_summary", "tags"],
    "properties": {
        "lesson_summary": {"type": "string", "minLength": 1},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 8,
        },
    },
}


class KnowledgeSinkBlockedError(Exception):
    """LLM unavailable — fail closed with outcome=blocked."""

    def __init__(self, message: str = "知识库沉淀需要 LLM，当前未配置", *, reason: str = "llm_unavailable"):
        super().__init__(message)
        self.reason = reason
        self.message = message


class KnowledgeSinkFailedError(Exception):
    """LLM call/schema/validation failed — fail closed with outcome=failed."""

    def __init__(self, message: str, *, reason: str = "llm_failed"):
        super().__init__(message)
        self.reason = reason
        self.message = message


def _clip(value: str | None, max_chars: int = _FIELD_MAX_CHARS) -> str:
    text_v = value or ""
    if len(text_v) <= max_chars:
        return text_v
    return text_v[: max_chars - 1] + "…"


async def _assemble_d3(db: AsyncSession, capa: CAPAEightD) -> str:
    base = capa.d3_interim or ""
    # Optional: append current done D3 impact/report summary when present
    try:
        run = await db.scalar(
            select(CapaD3ImportRun)
            .where(
                CapaD3ImportRun.capa_id == capa.report_id,
                CapaD3ImportRun.factory_id == capa.factory_id,
                CapaD3ImportRun.is_current == True,  # noqa: E712
            )
            .limit(1)
        )
        if run is None:
            return base
        report = await db.scalar(
            select(CapaD3ImpactReport)
            .where(
                CapaD3ImpactReport.run_id == run.run_id,
                CapaD3ImpactReport.factory_id == capa.factory_id,
                CapaD3ImpactReport.is_current == True,  # noqa: E712
                CapaD3ImpactReport.status == "done",
            )
            .limit(1)
        )
        if report is None:
            return base
        parts: list[str] = []
        if report.risk_level:
            parts.append(f"风险等级={report.risk_level}")
        if report.risk_explanation:
            parts.append(report.risk_explanation.strip())
        if report.batches:
            parts.append(f"批次={report.batches}")
        if not parts:
            return base
        scope = "；".join(parts)
        if base:
            return f"{base}\n受影响范围：{scope}"
        return f"受影响范围：{scope}"
    except Exception:
        logger.exception("D3 impact summary load failed; falling back to interim only")
        return base


async def _assemble_d4(db: AsyncSession, capa: CAPAEightD) -> str:
    current = (capa.d4_root_cause or "").strip()
    if not current:
        return ""
    verif = await db.scalar(
        select(CapaRootCauseVerification)
        .where(
            CapaRootCauseVerification.capa_id == capa.report_id,
            CapaRootCauseVerification.factory_id == capa.factory_id,
            CapaRootCauseVerification.conclusion == "passed",
            CapaRootCauseVerification.root_cause_text == current,
        )
        .order_by(
            CapaRootCauseVerification.verified_at.desc().nulls_last(),
            CapaRootCauseVerification.created_at.desc(),
        )
        .limit(1)
    )
    if verif is None:
        return current
    bits = [current]
    if verif.method:
        bits.append(f"method={verif.method}")
    if verif.verified_at is not None:
        bits.append(f"verified_at={verif.verified_at.isoformat()}")
    return " | ".join(bits)


async def _assemble_d7(db: AsyncSession, capa: CAPAEightD) -> str:
    rows = (
        await db.execute(
            select(CapaD7NodeAction).where(
                CapaD7NodeAction.capa_id == capa.report_id,
                CapaD7NodeAction.factory_id == capa.factory_id,
                CapaD7NodeAction.action.in_(("confirmed", "auto_filled")),
            )
        )
    ).scalars().all()
    if not rows:
        return capa.d7_prevention or ""
    lines: list[str] = []
    for r in rows:
        parts = [
            f"fm={r.failure_mode_node_id}",
            f"action={r.action}",
        ]
        if r.fmea_id is not None:
            parts.append(f"fmea_id={r.fmea_id}")
        prev = r.prevention_control_name_after or r.prevention_control_name_before
        if prev:
            parts.append(f"prevention={prev}")
        if r.reason:
            parts.append(f"reason={r.reason}")
        lines.append("; ".join(parts))
    return "\n".join(lines)


async def _assemble_linkage(db: AsyncSession, capa: CAPAEightD) -> dict:
    fmea_ids: list[str] = []
    seen: set[str] = set()

    def _add(fid):
        if fid is None:
            return
        s = str(fid)
        if s not in seen:
            seen.add(s)
            fmea_ids.append(s)

    # Header link
    _add(capa.fmea_ref_id)

    # D4 source_ref fmea_ids
    try:
        verifs = (
            await db.execute(
                select(CapaRootCauseVerification).where(
                    CapaRootCauseVerification.capa_id == capa.report_id,
                    CapaRootCauseVerification.factory_id == capa.factory_id,
                )
            )
        ).scalars().all()
        for v in verifs:
            ref = v.source_ref or {}
            if isinstance(ref, dict) and ref.get("fmea_id"):
                _add(ref["fmea_id"])
    except Exception:
        logger.exception("D4 source_ref fmea collection failed")

    # D7 node actions
    try:
        d7_rows = (
            await db.execute(
                select(CapaD7NodeAction.fmea_id).where(
                    CapaD7NodeAction.capa_id == capa.report_id,
                    CapaD7NodeAction.factory_id == capa.factory_id,
                    CapaD7NodeAction.fmea_id.is_not(None),
                )
            )
        ).scalars().all()
        for fid in d7_rows:
            _add(fid)
    except Exception:
        logger.exception("D7 fmea_id collection failed")

    scar_id = str(capa.scar_ref_id) if capa.scar_ref_id else None

    alert_ids: list[str] = []
    try:
        alerts = (
            await db.execute(
                select(SupplierRiskAlert.alert_id).where(
                    SupplierRiskAlert.linked_capa_id == capa.report_id,
                    SupplierRiskAlert.factory_id == capa.factory_id,
                )
            )
        ).scalars().all()
        alert_ids = [str(a) for a in alerts]
    except Exception:
        logger.exception("SupplierRiskAlert collection failed")

    return {
        "fmea_ids": fmea_ids,
        "scar_id": scar_id,
        "supplier_risk_alert_ids": alert_ids,
    }


async def _assemble_deterministic_fields(db: AsyncSession, capa: CAPAEightD) -> dict:
    d3 = await _assemble_d3(db, capa)
    d4 = await _assemble_d4(db, capa)
    d7 = await _assemble_d7(db, capa)
    linkage = await _assemble_linkage(db, capa)
    return {
        "d2": _clip(capa.d2_description or ""),
        "d3": _clip(d3),
        "d4_root_cause": _clip(d4),
        "d5": _clip(capa.d5_correction or ""),
        "d7_node_action": _clip(d7),
        "linkage": linkage,
        "closure": _clip(capa.d8_closure or ""),
    }


def _build_embedding_text(
    document_no: str,
    title: str,
    severity: str | None,
    fields: dict,
) -> str:
    tags = fields.get("tags") or []
    tag_str = ", ".join(str(t) for t in tags)
    return (
        f"[{document_no}] {title}\n"
        f"严重度: {severity or ''}\n"
        f"D2: {fields.get('d2', '')}\n"
        f"D3: {fields.get('d3', '')}\n"
        f"D4: {fields.get('d4_root_cause', '')}\n"
        f"D5: {fields.get('d5', '')}\n"
        f"D7: {fields.get('d7_node_action', '')}\n"
        f"关闭: {fields.get('closure', '')}\n"
        f"摘要: {fields.get('lesson_summary', '')}\n"
        f"标签: {tag_str}"
    )


def _build_prompt(capa: CAPAEightD, fields: dict) -> str:
    blocks = (
        f"document_no: {capa.document_no}\n"
        f"title: {capa.title}\n"
        f"severity: {capa.severity or ''}\n"
        f"product_line_code: {capa.product_line_code}\n"
        f"D2: {fields['d2']}\n"
        f"D3: {fields['d3']}\n"
        f"D4: {fields['d4_root_cause']}\n"
        f"D5: {fields['d5']}\n"
        f"D7: {fields['d7_node_action']}\n"
        f"linkage: {fields['linkage']}\n"
        f"closure: {fields['closure']}\n"
    )
    return (
        "你是质量知识库编辑。根据以下 8D 确定性字段，生成 JSON："
        '{"lesson_summary": string(非空), "tags": string[3..8]}。'
        "lesson_summary 用中文总结可复用的经验教训；tags 为短标签。"
        "只输出 JSON，不要 markdown。\n\n"
        f"{blocks}"
    )


async def sink_capa_on_close(
    db: AsyncSession,
    capa: CAPAEightD,
    user_id: uuid.UUID,
    *,
    manual: bool = False,
) -> KnowledgeEntry:
    """Fail-closed knowledge sink. Does not commit and does not mutate capa.status."""
    # 1. LLM availability
    try:
        pc = await provider_adapter.build_client(db)
    except ProviderNotConfiguredError as e:
        raise KnowledgeSinkBlockedError(
            "知识库沉淀需要 LLM，当前未配置", reason="llm_unavailable"
        ) from e
    if pc is None:
        raise KnowledgeSinkBlockedError(
            "知识库沉淀需要 LLM，当前未配置", reason="llm_unavailable"
        )

    # 2. Deterministic fields
    fields = await _assemble_deterministic_fields(db, capa)

    # 3. LLM summary + tags
    prompt = _build_prompt(capa, fields)
    try:
        raw = await provider_adapter.complete_json(pc, prompt, _LLM_RESPONSE_SCHEMA)
    except Exception as e:
        raise KnowledgeSinkFailedError(f"LLM 调用失败: {e}", reason="llm_failed") from e

    if not isinstance(raw, dict):
        raise KnowledgeSinkFailedError("LLM 返回非对象", reason="llm_failed")

    summary = raw.get("lesson_summary")
    tags = raw.get("tags")
    if not isinstance(summary, str) or not summary.strip():
        raise KnowledgeSinkFailedError("lesson_summary 为空或非法", reason="llm_failed")
    if not isinstance(tags, list) or not (3 <= len(tags) <= 8):
        raise KnowledgeSinkFailedError(
            f"tags 须为长度 3–8 的字符串列表，实际={tags!r}", reason="llm_failed"
        )
    if not all(isinstance(t, str) and t.strip() for t in tags):
        raise KnowledgeSinkFailedError("tags 元素须为非空字符串", reason="llm_failed")

    fields["lesson_summary"] = summary.strip()
    fields["tags"] = [t.strip() for t in tags]

    # 4. Assemble entry identity + embedding_text / content_hash
    entry_id = uuid.uuid5(uuid.NAMESPACE_URL, f"knowledge:capa:{capa.report_id}")
    embedding_text = _build_embedding_text(
        capa.document_no, capa.title, capa.severity, fields
    )
    content_hash = hashlib.sha256(embedding_text.encode()).hexdigest()
    now = datetime.now(UTC)

    # 5. Atomic upsert ON CONFLICT (source_type, source_id).
    # Do NOT overwrite status (keep active if already active; conflict path
    # also leaves status untouched so concurrent first-sink races resolve to
    # one row without SELECT-FOR-UPDATE races).
    upsert_stmt = (
        pg_insert(KnowledgeEntry)
        .values(
            entry_id=entry_id,
            source_type="capa",
            source_id=capa.report_id,
            factory_id=capa.factory_id,
            product_line_code=capa.product_line_code,
            document_no=capa.document_no,
            title=capa.title,
            severity=capa.severity,
            fields=fields,
            status="active",
            llm_status="done",
            embedding_text=embedding_text,
            content_hash=content_hash,
            embedding_status="pending",
            embedding_id=None,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_knowledge_entries_source",
            set_={
                "factory_id": capa.factory_id,
                "product_line_code": capa.product_line_code,
                "document_no": capa.document_no,
                "title": capa.title,
                "severity": capa.severity,
                "fields": fields,
                "llm_status": "done",
                "embedding_text": embedding_text,
                "content_hash": content_hash,
                "embedding_status": "pending",
                "embedding_id": None,
                "updated_at": now,
                # status intentionally omitted — leave active / do not flip
            },
        )
        .returning(KnowledgeEntry.entry_id)
    )
    result = await db.execute(upsert_stmt)
    returned_entry_id = result.scalar_one()
    # Refresh only the knowledge entry (do NOT expire_all — that would
    # invalidate `capa` and trigger async lazy-load MissingGreenlet).
    entry = await db.get(
        KnowledgeEntry, returned_entry_id, populate_existing=True
    )
    if entry is None:
        # Fallback natural-key load if get misses (e.g. identity-map race)
        entry = await db.scalar(
            select(KnowledgeEntry)
            .where(
                KnowledgeEntry.source_type == "capa",
                KnowledgeEntry.source_id == capa.report_id,
            )
            .execution_options(populate_existing=True)
        )
    if entry is None:
        raise KnowledgeSinkFailedError(
            "知识库 upsert 后无法读取条目", reason="db_error"
        )
    await db.flush()

    # Cancel pending outbox; leave processing for content_hash stale-drop
    await db.execute(
        text(
            """
            UPDATE embedding_sync_outbox
            SET status = 'cancelled'
            WHERE entity_type = 'knowledge_entry'
              AND entity_id = :id
              AND status = 'pending'
            """
        ),
        {"id": entry.entry_id},
    )
    await delete_embeddings_for_entity(db, "knowledge_entry", entry.entry_id)

    # 6. Enqueue with content_hash (must be before commit)
    await enqueue_embedding(
        db,
        "knowledge_entry",
        entry.entry_id,
        capa.product_line_code,
        capa.factory_id,
        content_hash=content_hash,
    )

    # 7. Audit KNOWLEDGE_SUNK — UUID fields as str
    db.add(
        AuditLog(
            table_name="capa_eightd",
            record_id=capa.report_id,
            action="KNOWLEDGE_SUNK",
            changed_fields={
                "entry_id": str(entry.entry_id),
                "product_line_code": capa.product_line_code,
                "document_no": capa.document_no,
                "content_hash": content_hash,
                "manual": manual,
                "embedding_status": "pending",
            },
            operated_by=user_id,
            factory_id=capa.factory_id,
        )
    )

    return entry
