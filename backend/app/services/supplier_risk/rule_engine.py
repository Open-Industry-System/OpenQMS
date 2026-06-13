"""Pure-function rule engine for supplier risk evaluation.

Each rule receives a SupplierRiskInput dataclass and a thresholds dict,
and returns a RuleResult. No DB access, no side effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

# ── Data structures ──────────────────────────────────────────────────


@dataclass
class SupplierRiskInput:
    supplier: Any
    inspections: list[Any] = field(default_factory=list)
    scars: list[Any] = field(default_factory=list)
    evaluations: list[Any] = field(default_factory=list)
    certifications: list[Any] = field(default_factory=list)


@dataclass
class RuleResult:
    rule_id: str
    triggered: bool
    score: float  # 0-100, 0 when not triggered
    detail: str
    category: str  # "quality" | "delivery" | "compliance"
    critical: bool = False


# ── Helper ───────────────────────────────────────────────────────────


def _in_window(d: date | None, window_days: int, ref: date | None = None) -> bool:
    """Return True if *d* falls within [ref - window_days, ref]."""
    if d is None:
        return False
    ref = ref or date.today()
    return (ref - d).days <= window_days


# ── R01  PPM超标 ────────────────────────────────────────────────────


def rule_r01_ppm(data: SupplierRiskInput, thresholds: dict) -> RuleResult:
    ppm_limit: int = thresholds.get("ppm_limit", 1000)
    window_days: int = thresholds.get("window_days", 90)

    today = date.today()
    total_lot = 0
    total_defect = 0

    for insp in data.inspections:
        if not _in_window(insp.inspection_date, window_days, today):
            continue
        lot = insp.lot_qty
        if lot is None or lot == 0:
            continue
        total_lot += lot
        if insp.inspection_result == "rejected":
            total_defect += insp.defect_qty

    ppm = (total_defect / total_lot * 1_000_000) if total_lot > 0 else 0

    if ppm > ppm_limit:
        score = min(ppm / ppm_limit * 50, 100)
        return RuleResult(
            rule_id="R01",
            triggered=True,
            score=round(score, 2),
            detail=f"PPM {ppm:.0f} 超过限值 {ppm_limit}",
            category="quality",
        )
    return RuleResult(rule_id="R01", triggered=False, score=0,
                      detail=f"PPM {ppm:.0f} 在限值 {ppm_limit} 以内", category="quality")


# ── R02  批次合格率下降 ──────────────────────────────────────────────


def rule_r02_acceptance_rate_decline(data: SupplierRiskInput, thresholds: dict) -> RuleResult:
    acceptance_rate_min: float = thresholds.get("acceptance_rate_min", 0.9)
    decline_ratio: float = thresholds.get("decline_ratio", 0.1)
    window_days: int = thresholds.get("window_days", 90)
    compare_window_days: int = thresholds.get("compare_window_days", 180)

    today = date.today()
    judged_statuses = {"judged", "closed"}

    def _rate(start_ago: int, end_ago: int) -> float | None:
        """Acceptance rate in period [today - start_ago, today - end_ago)."""
        total = accepted = 0
        for insp in data.inspections:
            if insp.status not in judged_statuses or insp.inspection_date is None:
                continue
            days_ago = (today - insp.inspection_date).days
            if end_ago <= days_ago < start_ago:
                total += 1
                if insp.inspection_result == "accepted":
                    accepted += 1
        return accepted / total if total > 0 else None

    current_rate = _rate(window_days, 0)
    previous_rate = _rate(compare_window_days, window_days)

    scores = []
    details = []

    if current_rate is not None and current_rate < acceptance_rate_min:
        s = (1 - current_rate / acceptance_rate_min) * 100
        scores.append(s)
        details.append(f"当前合格率 {current_rate:.2%} 低于下限 {acceptance_rate_min:.2%}")

    if current_rate is not None and previous_rate is not None and previous_rate > 0:
        decline = (previous_rate - current_rate) / previous_rate
        if decline > decline_ratio:
            s = decline * 100
            scores.append(s)
            details.append(f"合格率下降 {decline:.2%} 超过阈值 {decline_ratio:.2%}")

    if scores:
        score = round(min(max(scores), 100), 2)
        return RuleResult(rule_id="R02", triggered=True, score=score,
                          detail="; ".join(details), category="quality")
    return RuleResult(rule_id="R02", triggered=False, score=0,
                      detail="批次合格率正常", category="quality")


# ── R03  连续拒收 ────────────────────────────────────────────────────


def rule_r03_consecutive_rejection(data: SupplierRiskInput, thresholds: dict) -> RuleResult:
    consecutive_batches: int = thresholds.get("consecutive_batches", 3)
    batch_limit: int = thresholds.get("batch_limit", 10)

    eligible = [
        insp for insp in data.inspections
        if insp.status in ("judged", "closed") and insp.inspection_date is not None
    ]
    eligible.sort(key=lambda x: x.inspection_date, reverse=True)
    eligible = eligible[:batch_limit]

    consecutive = 0
    for insp in eligible:
        if insp.inspection_result == "rejected":
            consecutive += 1
        else:
            break

    if consecutive >= consecutive_batches:
        score = min(consecutive / consecutive_batches * 60, 100)
        return RuleResult(
            rule_id="R03", triggered=True, score=round(score, 2),
            detail=f"连续 {consecutive} 批拒收，超过阈值 {consecutive_batches}",
            category="quality",
        )
    return RuleResult(rule_id="R03", triggered=False, score=0,
                      detail=f"连续拒收 {consecutive} 批，未超阈值", category="quality")


# ── R04  SCAR超期未关闭 ──────────────────────────────────────────────


def rule_r04_scar_overdue(data: SupplierRiskInput, thresholds: dict) -> RuleResult:
    open_days_limit: int = thresholds.get("open_days_limit", 30)

    today = date.today()
    max_overdue = 0

    for scar in data.scars:
        if scar.status == "closed" or scar.issued_date is None:
            continue
        overdue = (today - scar.issued_date).days - open_days_limit
        if overdue > max_overdue:
            max_overdue = overdue

    if max_overdue > 0:
        score = min(max_overdue / open_days_limit * 50, 100)
        return RuleResult(
            rule_id="R04", triggered=True, score=round(score, 2),
            detail=f"SCAR 最长超期 {max_overdue} 天（限值 {open_days_limit} 天）",
            category="quality",
        )
    return RuleResult(rule_id="R04", triggered=False, score=0,
                      detail="无超期未关闭SCAR", category="quality")


# ── R05  SCAR频发 ────────────────────────────────────────────────────


def rule_r05_scar_frequent(data: SupplierRiskInput, thresholds: dict) -> RuleResult:
    scar_count_limit: int = thresholds.get("scar_count_limit", 3)
    window_days: int = thresholds.get("window_days", 90)

    today = date.today()
    count = sum(1 for scar in data.scars
                if scar.issued_date is not None and _in_window(scar.issued_date, window_days, today))

    if count > scar_count_limit:
        score = min(count / scar_count_limit * 50, 100)
        return RuleResult(
            rule_id="R05", triggered=True, score=round(score, 2),
            detail=f"窗口期内 {count} 个SCAR，超过限值 {scar_count_limit}",
            category="quality",
        )
    return RuleResult(rule_id="R05", triggered=False, score=0,
                      detail=f"窗口期内 {count} 个SCAR，未超限值", category="quality")


# ── R06  交付准时率下降 ──────────────────────────────────────────────


def rule_r06_delivery_score_decline(data: SupplierRiskInput, thresholds: dict) -> RuleResult:
    delivery_score_min: float = thresholds.get("delivery_score_min", 70)
    decline_ratio: float = thresholds.get("decline_ratio", 0.15)

    evals = data.evaluations  # already sorted by created_at desc
    if not evals:
        return RuleResult(rule_id="R06", triggered=False, score=0,
                          detail="无评价数据", category="delivery")

    latest = evals[0]
    scores = []
    details = []

    if latest.delivery_score < delivery_score_min:
        s = (1 - latest.delivery_score / delivery_score_min) * 100
        scores.append(s)
        details.append(f"交付分数 {latest.delivery_score:.1f} 低于下限 {delivery_score_min}")

    if len(evals) >= 2:
        prev = evals[1]
        if prev.delivery_score > 0:
            decline = (prev.delivery_score - latest.delivery_score) / prev.delivery_score
            if decline > decline_ratio:
                s = decline * 100
                scores.append(s)
                details.append(f"交付分数下降 {decline:.2%} 超过阈值 {decline_ratio:.2%}")

    if scores:
        score = round(min(max(scores), 100), 2)
        return RuleResult(rule_id="R06", triggered=True, score=score,
                          detail="; ".join(details), category="delivery")
    return RuleResult(rule_id="R06", triggered=False, score=0,
                      detail="交付准时率正常", category="delivery")


# ── R07  评级降级 ────────────────────────────────────────────────────


def rule_r07_grade_downgrade(data: SupplierRiskInput, thresholds: dict) -> RuleResult:
    from_grades: list[str] = thresholds.get("from_grades", ["A", "B"])
    to_grades: list[str] = thresholds.get("to_grades", ["C", "D"])

    evals = data.evaluations
    if len(evals) < 2:
        return RuleResult(rule_id="R07", triggered=False, score=0,
                          detail="评价数据不足，无法比较", category="delivery")

    prev, latest = evals[1], evals[0]
    if prev.grade in from_grades and latest.grade in to_grades:
        return RuleResult(
            rule_id="R07", triggered=True, score=80,
            detail=f"评级从 {prev.grade} 降为 {latest.grade}",
            category="delivery",
        )
    return RuleResult(rule_id="R07", triggered=False, score=0,
                      detail=f"评级 {latest.grade}，无降级", category="delivery")


# ── R08  证书即将过期 ────────────────────────────────────────────────


def rule_r08_cert_expiry(data: SupplierRiskInput, thresholds: dict) -> RuleResult:
    warning_days: list[int] = thresholds.get("warning_days", [90, 60, 30])

    today = date.today()
    max_score = 0
    nearest_days = None

    for cert in data.certifications:
        if cert.expiry_date is None:
            continue
        days_left = (cert.expiry_date - today).days
        if days_left < 0:
            # Already expired — treat as most urgent
            cert_score = 100
        elif days_left < warning_days[2]:  # <30
            cert_score = 100
        elif days_left < warning_days[1]:  # 30-60
            cert_score = 60
        elif days_left < warning_days[0]:  # 60-90
            cert_score = 30
        else:
            cert_score = 0

        if cert_score > max_score:
            max_score = cert_score
            nearest_days = days_left

    if max_score > 0:
        detail = f"最近证书剩余 {nearest_days} 天" if nearest_days is not None else "证书已过期"
        return RuleResult(rule_id="R08", triggered=True, score=max_score,
                          detail=detail, category="compliance")
    return RuleResult(rule_id="R08", triggered=False, score=0,
                      detail="无即将过期证书", category="compliance")


# ── R09  评价分数下滑 ────────────────────────────────────────────────


def rule_r09_score_decline(data: SupplierRiskInput, thresholds: dict) -> RuleResult:
    score_decline_limit: float = thresholds.get("score_decline_limit", 15)

    evals = data.evaluations
    if len(evals) < 2:
        return RuleResult(rule_id="R09", triggered=False, score=0,
                          detail="评价数据不足，无法比较", category="compliance")

    prev, latest = evals[1], evals[0]
    decline = prev.total_score - latest.total_score

    if decline > score_decline_limit:
        score = min(decline / score_decline_limit * 50, 100)
        return RuleResult(
            rule_id="R09", triggered=True, score=round(score, 2),
            detail=f"评价分数下降 {decline:.1f}，超过阈值 {score_decline_limit}",
            category="compliance",
        )
    return RuleResult(rule_id="R09", triggered=False, score=0,
                      detail="评价分数稳定", category="compliance")


# ── R10  安全缺陷检测 ────────────────────────────────────────────────


def rule_r10_safety_defect(data: SupplierRiskInput, thresholds: dict) -> RuleResult:
    keywords: list[str] = thresholds.get("keywords", ["安全", "安全特性", "safety"])

    for insp in data.inspections:
        desc = insp.defect_description
        if desc is None:
            continue
        desc_lower = desc.lower()
        for kw in keywords:
            if kw.lower() in desc_lower:
                return RuleResult(
                    rule_id="R10", triggered=True, score=100,
                    detail=f"检测到安全缺陷关键词「{kw}」",
                    category="compliance", critical=True,
                )

    return RuleResult(rule_id="R10", triggered=False, score=0,
                      detail="未检测到安全缺陷", category="compliance", critical=False)


# ── Registry ─────────────────────────────────────────────────────────


RULE_REGISTRY: list[tuple[str, object, str, int, bool]] = [
    ("R01", rule_r01_ppm, "quality", 15, False),
    ("R02", rule_r02_acceptance_rate_decline, "quality", 12, False),
    ("R03", rule_r03_consecutive_rejection, "quality", 18, False),
    ("R04", rule_r04_scar_overdue, "quality", 10, False),
    ("R05", rule_r05_scar_frequent, "quality", 12, False),
    ("R06", rule_r06_delivery_score_decline, "delivery", 12, False),
    ("R07", rule_r07_grade_downgrade, "delivery", 10, False),
    ("R08", rule_r08_cert_expiry, "compliance", 8, False),
    ("R09", rule_r09_score_decline, "compliance", 8, False),
    ("R10", rule_r10_safety_defect, "compliance", 15, True),
]

_REGISTRY_MAP: dict[str, tuple[object, str, int, bool]] = {
    rid: (fn, cat, w, crit) for rid, fn, cat, w, crit in RULE_REGISTRY
}


# ── Runner ───────────────────────────────────────────────────────────


def run_all_rules(
    data: SupplierRiskInput,
    configs: list[Any],
) -> tuple[list[RuleResult], list[str]]:
    """Execute all enabled rules from *configs*.

    *configs* items must have attributes: ``.rule_id``, ``.enabled``,
    ``.thresholds``, ``.weight``, ``.category``.

    Returns (results, failed_rule_ids).
    """
    results: list[RuleResult] = []
    failed_rule_ids: list[str] = []

    for cfg in configs:
        if not cfg.enabled:
            continue
        entry = _REGISTRY_MAP.get(cfg.rule_id)
        if entry is None:
            failed_rule_ids.append(cfg.rule_id)
            continue
        fn, _cat, _weight, _crit = entry
        try:
            result = fn(data, cfg.thresholds)
        except Exception:
            failed_rule_ids.append(cfg.rule_id)
            continue
        results.append(result)

    return results, failed_rule_ids
