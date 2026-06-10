from __future__ import annotations

import hashlib
import json
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument
from app.models.spc import SPCAlarm, InspectionCharacteristic
from app.schemas.quality_trend import QualityTrendSummary, QualityTrendMetadata
from app.utils.fmea_graph import build_rpn_rows


WINDOW_DAYS = 30
MIN_EFFECTIVE_MODULES = 2
HIGH_RPN_THRESHOLD = 100
RISK_THRESHOLDS = {"medium": 2, "high": 4}


async def build_quality_trend_summary(
    db: AsyncSession,
    filter_codes: list[str],
    allowed_modules: set[str],
    scope_description: str,
    selected_product_line: str | None,
    scope_hash: str = "",
) -> QualityTrendSummary:
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=WINDOW_DAYS)
    previous_start = now - timedelta(days=WINDOW_DAYS * 2)
    omitted_modules = sorted({"spc", "capa", "fmea"} - allowed_modules)
    evidence = []
    actions = []
    score = 0
    effective_modules = set()

    if "spc" in allowed_modules:
        current_q = select(func.count()).where(SPCAlarm.triggered_at >= current_start)
        previous_q = select(func.count()).where(SPCAlarm.triggered_at >= previous_start, SPCAlarm.triggered_at < current_start)
        open_q = select(func.count()).where(SPCAlarm.status == "open", SPCAlarm.acknowledged_at.is_(None))
        if filter_codes:
            current_q = current_q.join(InspectionCharacteristic, SPCAlarm.ic_id == InspectionCharacteristic.ic_id).where(InspectionCharacteristic.product_line.in_(filter_codes))
            previous_q = previous_q.join(InspectionCharacteristic, SPCAlarm.ic_id == InspectionCharacteristic.ic_id).where(InspectionCharacteristic.product_line.in_(filter_codes))
            open_q = open_q.join(InspectionCharacteristic, SPCAlarm.ic_id == InspectionCharacteristic.ic_id).where(InspectionCharacteristic.product_line.in_(filter_codes))
        current_count = await db.scalar(current_q) or 0
        previous_count = await db.scalar(previous_q) or 0
        open_count = await db.scalar(open_q) or 0
        trend_delta = current_count - previous_count
        if current_count or previous_count or open_count:
            effective_modules.add("spc")
        evidence.append({"id": "spc_alarm_count", "label": "SPC 异常告警", "value": current_count, "trend": f"{trend_delta:+d}", "severity": "warning" if current_count else "none"})
        if open_count:
            evidence.append({"id": "spc_open_unack", "label": "未确认告警", "value": open_count, "trend": "-", "severity": "warning"})
            actions.append({"priority": "high", "text": "优先复核未确认 SPC 异常"})
        score += max(0, trend_delta)

    if "capa" in allowed_modules:
        open_capa_q = select(func.count()).where(CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]))
        overdue_capa_q = select(func.count()).where(CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]), CAPAEightD.due_date.isnot(None), CAPAEightD.due_date < now.date())
        if filter_codes:
            open_capa_q = open_capa_q.where(CAPAEightD.product_line_code.in_(filter_codes))
            overdue_capa_q = overdue_capa_q.where(CAPAEightD.product_line_code.in_(filter_codes))
        open_capa = await db.scalar(open_capa_q) or 0
        overdue_capa = await db.scalar(overdue_capa_q) or 0
        if open_capa or overdue_capa:
            effective_modules.add("capa")
        evidence.append({"id": "capa_open_count", "label": "打开 CAPA", "value": open_capa, "trend": "-", "severity": "info" if open_capa else "none"})
        if overdue_capa:
            evidence.append({"id": "capa_overdue_count", "label": "超期 CAPA", "value": overdue_capa, "trend": "-", "severity": "warning"})
            actions.append({"priority": "high", "text": "清理超期 CAPA"})
            score += overdue_capa

    if "fmea" in allowed_modules:
        fmea_q = select(FMEADocument.fmea_id, FMEADocument.graph_data)
        if filter_codes:
            fmea_q = fmea_q.where(FMEADocument.product_line_code.in_(filter_codes))
        result = await db.execute(fmea_q)
        rows = result.all()
        high_rpn = 0
        for row in rows:
            graph = row.graph_data or {}
            for rpn_row in build_rpn_rows(graph.get("nodes", []), graph.get("edges", [])):
                rpn = rpn_row.get("severity", 0) * rpn_row.get("occurrence", 0) * rpn_row.get("detection", 0)
                if rpn >= HIGH_RPN_THRESHOLD:
                    high_rpn += 1
        if rows:
            effective_modules.add("fmea")
        evidence.append({"id": "high_rpn_count", "label": "高 RPN 节点", "value": high_rpn, "trend": "-", "severity": "warning" if high_rpn else "none"})
        if high_rpn:
            actions.append({"priority": "high", "text": "复核高 RPN 风险项"})
            score += high_rpn

    has_enough_data = len(effective_modules) >= MIN_EFFECTIVE_MODULES
    risk_level = "insufficient_data"
    if has_enough_data:
        risk_level = "low"
        if score >= RISK_THRESHOLDS["high"]:
            risk_level = "high"
        elif score >= RISK_THRESHOLDS["medium"]:
            risk_level = "medium"

    if not actions:
        actions.append({"priority": "low", "text": "继续监控关键指标"})

    generated_at = datetime.now(timezone.utc).isoformat()
    metadata = QualityTrendMetadata(
        omitted_modules=omitted_modules,
        available_modules=sorted(effective_modules),
        scope_description=scope_description,
        selected_product_line=selected_product_line,
    )
    summary = QualityTrendSummary(
        risk_level=risk_level,
        headline=_headline_for_level(risk_level),
        evidence=evidence,
        actions=actions,
        data_window_days=WINDOW_DAYS,
        generated_at=generated_at,
        evidence_hash=_hash_evidence(scope_description, sorted(effective_modules), omitted_modules, WINDOW_DAYS, evidence, actions),
        scope_hash=scope_hash,
        ai_available=risk_level not in {"insufficient_data", "low"},
        metadata=metadata,
    )
    return summary


def _headline_for_level(risk_level: str) -> str:
    if risk_level == "high":
        return "质量风险明显上升"
    if risk_level == "medium":
        return "质量风险呈上升趋势"
    if risk_level == "low":
        return "质量趋势暂无明显恶化"
    return "数据不足以判断趋势"


def _hash_evidence(scope_description: str, available_modules: list[str], omitted_modules: list[str], window_days: int, evidence: list[dict], actions: list[dict]) -> str:
    payload = json.dumps({
        "scope_description": scope_description,
        "available_modules": available_modules,
        "omitted_modules": omitted_modules,
        "window_days": window_days,
        "evidence": sorted(evidence, key=lambda x: x["id"]),
        "actions": actions,
    }, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def build_scope_hash(filter_codes: list[str]) -> str:
    payload = json.dumps(filter_codes, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_scope_description(product_line_codes: list[str] | None) -> str:
    if not product_line_codes:
        return "全部可访问产品线"
    if len(product_line_codes) == 1:
        return f"产品线范围：{product_line_codes[0]}"
    return "产品线范围：" + ", ".join(product_line_codes)


import time
import uuid as uuid_mod

from app.models.audit import AuditLog
from app.schemas.quality_trend import QualityTrendInterpretation

_interpret_cache: dict[str, tuple[QualityTrendInterpretation, float]] = {}
_rate_limit: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW = 60.0
RATE_LIMIT_MAX = 5
CACHE_TTL = 30 * 60
LLM_TIMEOUT = 30.0


class RateLimitError(ValueError):
    pass


class LLMNotConfiguredError(ValueError):
    pass


class InsufficientTrendDataError(ValueError):
    pass


class LLMResponseParseError(ValueError):
    pass


async def interpret_quality_trend(
    db,
    user_id: str,
    llm_provider,
    filter_codes: list[str],
    allowed_modules: set[str],
    scope_description: str,
    selected_product_line: str | None,
    scope_hash: str,
) -> QualityTrendInterpretation:
    try:
        _enforce_rate_limit(user_id)
    except RateLimitError:
        await _write_interpret_audit(db, user_id, "rate_limited", {
            "scope_hash": scope_hash,
            "product_line_codes": filter_codes,
        })
        raise

    summary = await build_quality_trend_summary(db, filter_codes, allowed_modules, scope_description, selected_product_line)
    audit_context = {
        "scope_hash": scope_hash,
        "evidence_hash": summary.evidence_hash,
        "risk_level": summary.risk_level,
        "product_line_codes": filter_codes,
        "allowed_modules": sorted(allowed_modules),
        "omitted_modules": summary.metadata.omitted_modules,
        "evidence_ids": [e.id for e in summary.evidence],
    }

    if summary.risk_level == "insufficient_data":
        await _write_interpret_audit(db, user_id, "insufficient_data", audit_context)
        raise InsufficientTrendDataError("数据不足，无法生成 AI 解读")

    if llm_provider is None:
        await _write_interpret_audit(db, user_id, "llm_not_configured", audit_context)
        raise LLMNotConfiguredError("LLM 未配置")

    cache_key = f"{scope_hash}:{summary.data_window_days}:{summary.evidence_hash}"
    cached = _get_cached_interpretation(cache_key)
    if cached:
        await _write_interpret_audit(db, user_id, "cache_hit", audit_context)
        return cached

    prompt = _build_interpret_prompt(summary, allowed_modules, scope_description)
    try:
        raw = await asyncio.wait_for(
            llm_provider.complete(prompt, _interpret_response_schema()),
            timeout=LLM_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        await _write_interpret_audit(db, user_id, "llm_failed", audit_context | {"error": f"LLM 调用超时（>{LLM_TIMEOUT}s）"})
        raise LLMNotConfiguredError("AI 解读服务响应超时，请稍后重试") from exc
    except Exception as exc:
        await _write_interpret_audit(db, user_id, "llm_failed", audit_context | {"error": str(exc)})
        raise

    try:
        result = _parse_interpretation(raw, summary, scope_hash)
    except LLMResponseParseError as exc:
        await _write_interpret_audit(db, user_id, "parse_failed", audit_context | {"error": str(exc)})
        raise

    _set_cached_interpretation(cache_key, result)
    await _write_interpret_audit(db, user_id, "success", audit_context | {"model": result.model})
    return result


def _parse_interpretation(raw: dict, summary, scope_hash: str) -> QualityTrendInterpretation:
    evidence_ids = {e.id for e in summary.evidence}
    refs = set(raw.get("evidence_refs") or [])
    unknown_refs = refs - evidence_ids
    if unknown_refs:
        raise LLMResponseParseError(f"LLM returned unknown evidence_refs: {sorted(unknown_refs)}")
    payload = {
        **raw,
        "model": raw.get("model", "unknown"),
        "evidence_hash": summary.evidence_hash,
        "scope_hash": scope_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
    }
    return QualityTrendInterpretation(**payload)


async def _write_interpret_audit(db, user_id: str, status: str, context: dict) -> None:
    db.add(AuditLog(
        table_name="quality_trends",
        record_id=uuid_mod.uuid4(),
        action="AI_TREND_INTERPRET",
        changed_fields={"status": status},
        old_values=None,
        new_values={"status": status, **context},
        operated_by=uuid_mod.UUID(str(user_id)),
    ))
    await db.commit()


def _get_cached_interpretation(cache_key: str) -> QualityTrendInterpretation | None:
    entry = _interpret_cache.get(cache_key)
    if entry is None:
        return None
    result, ts = entry
    if time.monotonic() - ts > CACHE_TTL:
        del _interpret_cache[cache_key]
        return None
    return result.model_copy(update={"cached": True})


def _set_cached_interpretation(cache_key: str, result: QualityTrendInterpretation) -> None:
    _interpret_cache[cache_key] = (result, time.monotonic())


def _enforce_rate_limit(user_id: str) -> None:
    now = time.monotonic()
    window = []
    for ts in _rate_limit.get(user_id, []):
        if now - ts < RATE_LIMIT_WINDOW:
            window.append(ts)
    if len(window) >= RATE_LIMIT_MAX:
        raise RateLimitError("rate limit exceeded")
    window.append(now)
    _rate_limit[user_id] = window


def _build_interpret_prompt(summary, allowed_modules: set[str], scope_description: str) -> str:
    evidence_text = "\n".join(
        f"- id={e.id} | {e.label}: {e.value} (trend: {e.trend}, severity: {e.severity})"
        for e in summary.evidence
    )
    actions_text = "\n".join(f"- [{a.priority}] {a.text}" for a in summary.actions)
    allowed_ids = ", ".join(e.id for e in summary.evidence)
    return f"""你是一位质量趋势分析专家。请基于以下数据生成结构化解读。

产品线范围：{scope_description}
可用模块：{', '.join(sorted(allowed_modules))}
风险等级：{summary.risk_level}

证据（每条证据都有唯一 id，后续引用时必须使用这些 id）：
{evidence_text}

建议动作：
{actions_text}

请用中文输出以下 JSON 格式。注意：evidence_refs 必须且只能使用上面列出的 evidence id（{allowed_ids}），不要编造 id，也不要用 label 代替 id。
{{
  "summary": "总体趋势判断（一句话）",
  "possible_causes": ["可能原因1", "可能原因2"],
  "impact_scope": ["影响范围"],
  "recommended_actions": [
    {{"priority": "high|medium|low", "action": "具体动作", "reason": "原因"}}
  ],
  "evidence_refs": ["从上面证据列表中选择对应的 id"],
  "confidence": "low|medium|high"
}}"""


def _interpret_response_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "possible_causes": {"type": "array", "items": {"type": "string"}},
            "impact_scope": {"type": "array", "items": {"type": "string"}},
            "recommended_actions": {"type": "array", "items": {"type": "object"}},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": ["summary", "possible_causes", "impact_scope", "recommended_actions", "evidence_refs", "confidence"],
    }
