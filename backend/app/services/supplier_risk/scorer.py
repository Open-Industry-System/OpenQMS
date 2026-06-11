"""Risk score calculator with weighted dimensions and critical bypass.

Denominator uses ALL active rule weights (not just triggered) to reflect risk accumulation.
Critical bypass: if any critical rule triggered, risk_score = max(calculated, 61).
"""
from dataclasses import dataclass

CATEGORY_WEIGHTS = {"quality": 0.50, "delivery": 0.30, "compliance": 0.20}
RISK_THRESHOLDS = [(30, "low"), (60, "medium"), (80, "high"), (101, "critical")]


@dataclass
class RiskScore:
    risk_score: float
    risk_level: str
    quality_score: float
    delivery_score: float
    compliance_score: float


def calculate_risk_score(results: list, configs: list) -> RiskScore:
    """Calculate weighted risk score from rule results.

    Args:
        results: list of RuleResult objects from rule engine
        configs: list of config objects with .rule_id, .weight, .category, .enabled

    Denominator uses ALL active (enabled) rule weights per category, not just triggered ones.
    This means triggering a single rule in a category gives a proportional score, not 100.
    """
    category_scores = {}
    for cat, cat_weight in CATEGORY_WEIGHTS.items():
        active_weights = sum(c.weight for c in configs if c.category == cat and c.enabled)
        if active_weights == 0:
            category_scores[cat] = 0.0
            continue
        triggered = sum(r.score * _get_weight(configs, r.rule_id) for r in results if r.category == cat and r.triggered)
        category_scores[cat] = triggered / active_weights

    overall = sum(category_scores[cat] * w for cat, w in CATEGORY_WEIGHTS.items())

    # Critical bypass
    if any(r.triggered and r.critical for r in results):
        overall = max(overall, 61.0)

    level = "low"
    for threshold, label in RISK_THRESHOLDS:
        if overall < threshold:
            break
        level = label

    return RiskScore(
        risk_score=round(overall, 2),
        risk_level=level,
        quality_score=round(category_scores["quality"], 2),
        delivery_score=round(category_scores["delivery"], 2),
        compliance_score=round(category_scores["compliance"], 2),
    )


def _get_weight(configs, rule_id: str) -> float:
    for c in configs:
        if c.rule_id == rule_id:
            return c.weight
    return 1.0
