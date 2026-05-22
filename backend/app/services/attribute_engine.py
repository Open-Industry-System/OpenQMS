"""Attribute study calculation engine — effectiveness, miss rate, false alarm rate, Kappa."""

from collections import defaultdict

from app.models.attribute import AttributeStudy, AttributeMeasurement, AttributeResult


def compute_attribute(study: AttributeStudy, measurements: list[AttributeMeasurement]) -> AttributeResult:
    if not measurements:
        raise ValueError("no measurements for attribute study")

    # Group by appraiser and part
    appraiser_decisions: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    part_standard: dict[str, str] = {}

    for m in measurements:
        appraiser_decisions[m.appraiser_name][m.part_no].append(m.appraiser_decision)
        part_standard[m.part_no] = m.known_standard

    # Effectiveness = correct decisions / total decisions
    total_decisions = 0
    correct_decisions = 0
    miss_count = 0
    false_alarm_count = 0
    standard_accept_count = 0
    standard_reject_count = 0

    for appraiser, parts in appraiser_decisions.items():
        for part_no, decisions in parts.items():
            standard = part_standard[part_no]
            # Use majority decision for this appraiser×part
            decision = max(set(decisions), key=decisions.count)
            total_decisions += 1
            if decision == standard:
                correct_decisions += 1
            if standard == "接受" or standard == "1":
                standard_accept_count += 1
                if decision != standard:
                    miss_count += 1
            else:
                standard_reject_count += 1
                if decision != standard:
                    false_alarm_count += 1

    effectiveness = (correct_decisions / total_decisions * 100) if total_decisions > 0 else 0
    miss_rate = (miss_count / standard_accept_count * 100) if standard_accept_count > 0 else 0
    false_alarm_rate = (false_alarm_count / standard_reject_count * 100) if standard_reject_count > 0 else 0

    # Kappa calculations (simplified)
    kappa_within = _compute_kappa_within(appraiser_decisions)
    kappa_vs_standard = _compute_kappa_vs_standard(appraiser_decisions, part_standard)
    kappa_between = _compute_kappa_between(appraiser_decisions)

    # Conclusion: AIAG guidelines — effectiveness ≥ 90%, miss rate ≤ 2%, false alarm ≤ 5%
    if effectiveness >= 90 and miss_rate <= 2 and false_alarm_rate <= 5:
        conclusion = "可接受"
    elif effectiveness >= 80:
        conclusion = "条件接受"
    else:
        conclusion = "不可接受"

    return AttributeResult(
        study_id=study.study_id,
        effectiveness=effectiveness,
        miss_rate=miss_rate,
        false_alarm_rate=false_alarm_rate,
        kappa_within=kappa_within,
        kappa_vs_standard=kappa_vs_standard,
        kappa_between=kappa_between,
        conclusion=conclusion,
    )


def _compute_kappa_within(appraiser_decisions: dict) -> float | None:
    """Cohen's Kappa for intra-appraiser consistency (trials)."""
    # Simplified: check if all trials for same appraiser×part agree
    agreements = 0
    total = 0
    for parts in appraiser_decisions.values():
        for decisions in parts.values():
            if len(decisions) > 1:
                total += 1
                if len(set(decisions)) == 1:
                    agreements += 1
    if total == 0:
        return None
    return agreements / total


def _compute_kappa_vs_standard(appraiser_decisions: dict, part_standard: dict) -> float | None:
    """Agreement between appraiser decisions and known standard."""
    agreements = 0
    total = 0
    for appraiser, parts in appraiser_decisions.items():
        for part_no, decisions in parts.items():
            standard = part_standard[part_no]
            decision = max(set(decisions), key=decisions.count)
            total += 1
            if decision == standard:
                agreements += 1
    if total == 0:
        return None
    return agreements / total


def _compute_kappa_between(appraiser_decisions: dict) -> float | None:
    """Simplified inter-appraiser agreement."""
    # For each part, check if all appraisers agree
    parts_all: set[str] = set()
    for parts in appraiser_decisions.values():
        parts_all.update(parts.keys())
    if len(appraiser_decisions) < 2:
        return None
    agreements = 0
    for part_no in parts_all:
        decisions = []
        for appraiser in appraiser_decisions:
            if part_no in appraiser_decisions[appraiser]:
                d = appraiser_decisions[appraiser][part_no]
                decisions.append(max(set(d), key=d.count))
        if len(decisions) > 1 and len(set(decisions)) == 1:
            agreements += 1
    return agreements / len(parts_all) if parts_all else None
