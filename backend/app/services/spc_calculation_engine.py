import math
from typing import List, Dict, Any, Optional

# X-bar R control chart constants (n=2 to 10)
# A2, D3, D4 from standard tables
XBAR_R_CONSTANTS = {
    2: {"A2": 1.880, "D3": 0.000, "D4": 3.267, "d2": 1.128},
    3: {"A2": 1.023, "D3": 0.000, "D4": 2.574, "d2": 1.693},
    4: {"A2": 0.729, "D3": 0.000, "D4": 2.282, "d2": 2.059},
    5: {"A2": 0.577, "D3": 0.000, "D4": 2.114, "d2": 2.326},
    6: {"A2": 0.483, "D3": 0.000, "D4": 2.004, "d2": 2.534},
    7: {"A2": 0.419, "D3": 0.076, "D4": 1.924, "d2": 2.704},
    8: {"A2": 0.373, "D3": 0.136, "D4": 1.864, "d2": 2.847},
    9: {"A2": 0.337, "D3": 0.184, "D4": 1.816, "d2": 2.970},
    10: {"A2": 0.308, "D3": 0.223, "D4": 1.777, "d2": 3.078},
}


def calculate_xbar_r_limits(values_2d: List[List[float]]) -> Dict[str, Optional[float]]:
    """Calculate X-bar R control limits from subgroup data."""
    if not values_2d:
        return {"ucl": None, "lcl": None, "cl": None, "r_ucl": None, "r_lcl": None, "r_cl": None}

    n = len(values_2d[0])
    if n < 2 or n > 10:
        raise ValueError(f"subgroup_size must be between 2 and 10, got {n}")

    if len(values_2d) < 2:
        return {"ucl": None, "lcl": None, "cl": None, "r_ucl": None, "r_lcl": None, "r_cl": None}

    # Validate all subgroups have same size
    for group in values_2d:
        if len(group) != n:
            raise ValueError("All subgroups must have the same size")

    subgroup_means = [sum(group) / len(group) for group in values_2d]
    subgroup_ranges = [max(group) - min(group) for group in values_2d]

    xbar_bar = sum(subgroup_means) / len(subgroup_means)
    r_bar = sum(subgroup_ranges) / len(subgroup_ranges)

    const = XBAR_R_CONSTANTS[n]
    A2 = const["A2"]
    D3 = const["D3"]
    D4 = const["D4"]

    return {
        "ucl": round(xbar_bar + A2 * r_bar, 4),
        "lcl": round(xbar_bar - A2 * r_bar, 4),
        "cl": round(xbar_bar, 4),
        "r_ucl": round(D4 * r_bar, 4),
        "r_lcl": round(D3 * r_bar, 4),
        "r_cl": round(r_bar, 4),
    }


def calculate_imr_limits(values_1d: List[float]) -> Dict[str, Optional[float]]:
    """Calculate I-MR control limits from individual values."""
    if not values_1d or len(values_1d) < 2:
        return {"ucl": None, "lcl": None, "cl": None, "r_ucl": None, "r_lcl": None, "r_cl": None}

    x_bar = sum(values_1d) / len(values_1d)
    mr_values = [abs(values_1d[i] - values_1d[i - 1]) for i in range(1, len(values_1d))]
    mr_bar = sum(mr_values) / len(mr_values)

    return {
        "ucl": round(x_bar + 2.66 * mr_bar, 4),
        "lcl": round(x_bar - 2.66 * mr_bar, 4),
        "cl": round(x_bar, 4),
        "r_ucl": round(3.267 * mr_bar, 4),
        "r_lcl": 0.0,
        "r_cl": round(mr_bar, 4),
    }


def calculate_histogram_data(values_1d: List[float], bins: int = 20) -> List[Dict[str, Any]]:
    """Calculate histogram bin data."""
    if not values_1d:
        return []

    min_val = min(values_1d)
    max_val = max(values_1d)
    if min_val == max_val:
        return [{"bin_start": min_val, "bin_end": max_val, "count": len(values_1d)}]

    bin_width = (max_val - min_val) / bins
    counts = [0] * bins

    for v in values_1d:
        idx = min(int((v - min_val) / bin_width), bins - 1)
        counts[idx] += 1

    result = []
    for i in range(bins):
        result.append({
            "bin_start": round(min_val + i * bin_width, 4),
            "bin_end": round(min_val + (i + 1) * bin_width, 4),
            "count": counts[i],
        })
    return result


SEVERITY_MAP = {
    1: "critical",
    2: "major",
    3: "major",
    4: "minor",
    5: "major",
    6: "major",
    7: "minor",
    8: "minor",
}


def evaluate_western_electric(subgroup_stats: List[float], limits: Dict[str, float],
                               rules_config: Dict[str, bool]) -> List[Dict[str, Any]]:
    """Evaluate Western Electric rules against subgroup statistics."""
    alarms = []
    ucl = limits.get("ucl")
    lcl = limits.get("lcl")
    cl = limits.get("cl")

    if ucl is None or lcl is None or cl is None or not subgroup_stats:
        return alarms

    sigma = (ucl - lcl) / 6
    zone_1u = cl + sigma
    zone_1l = cl - sigma
    zone_2u = cl + 2 * sigma
    zone_2l = cl - 2 * sigma

    def add_alarm(idx: int, rule_no: int):
        if rules_config.get(f"rule_{rule_no}", True):
            alarms.append({
                "rule_no": rule_no,
                "batch_index": idx,
                "severity": SEVERITY_MAP.get(rule_no, "minor"),
            })

    # Rule 1: Any point beyond 3 sigma
    for i, val in enumerate(subgroup_stats):
        if val > ucl or val < lcl:
            add_alarm(i, 1)

    # Rule 2: 9 points same side of center line
    for i in range(8, len(subgroup_stats)):
        window = subgroup_stats[i - 8:i + 1]
        if all(v > cl for v in window) or all(v < cl for v in window):
            add_alarm(i, 2)

    # Rule 3: 6 points trending up or down
    for i in range(5, len(subgroup_stats)):
        window = subgroup_stats[i - 5:i + 1]
        if all(window[j] < window[j + 1] for j in range(5)):
            add_alarm(i, 3)
        elif all(window[j] > window[j + 1] for j in range(5)):
            add_alarm(i, 3)

    # Rule 4: 14 points alternating up and down
    for i in range(13, len(subgroup_stats)):
        window = subgroup_stats[i - 13:i + 1]
        if all((window[j] < window[j + 1]) != (window[j + 1] < window[j + 2]) for j in range(12)):
            add_alarm(i, 4)

    # Rule 5: 2 of 3 points beyond 2 sigma (same side)
    for i in range(2, len(subgroup_stats)):
        window = subgroup_stats[i - 2:i + 1]
        above = sum(1 for v in window if v > zone_2u)
        below = sum(1 for v in window if v < zone_2l)
        if above >= 2 or below >= 2:
            add_alarm(i, 5)

    # Rule 6: 4 of 5 points beyond 1 sigma (same side)
    for i in range(4, len(subgroup_stats)):
        window = subgroup_stats[i - 4:i + 1]
        above = sum(1 for v in window if v > zone_1u)
        below = sum(1 for v in window if v < zone_1l)
        if above >= 4 or below >= 4:
            add_alarm(i, 6)

    # Rule 7: 15 points within 1 sigma
    for i in range(14, len(subgroup_stats)):
        window = subgroup_stats[i - 14:i + 1]
        if all(zone_1l <= v <= zone_1u for v in window):
            add_alarm(i, 7)

    # Rule 8: 8 points beyond 1 sigma (both sides)
    for i in range(7, len(subgroup_stats)):
        window = subgroup_stats[i - 7:i + 1]
        outside = sum(1 for v in window if v > zone_1u or v < zone_1l)
        if outside >= 8:
            add_alarm(i, 8)

    return alarms


def _sample_std(values: List[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    return math.sqrt(variance)


def calculate_cp_cpk(values_1d: List[float], usl: float, lsl: float) -> Dict[str, float]:
    """Calculate Cp and Cpk using sample standard deviation for short-term sigma."""
    if not values_1d or len(values_1d) < 2:
        return {"cp": 0.0, "cpk": 0.0, "cpu": 0.0, "cpl": 0.0}

    mean = sum(values_1d) / len(values_1d)

    # Use sample standard deviation as short-term estimate
    sigma = _sample_std(values_1d)
    if sigma == 0:
        return {"cp": 0.0, "cpk": 0.0, "cpu": 0.0, "cpl": 0.0}

    cp = (usl - lsl) / (6 * sigma)
    cpu = (usl - mean) / (3 * sigma)
    cpl = (mean - lsl) / (3 * sigma)
    cpk = min(cpu, cpl)

    return {
        "cp": round(cp, 4),
        "cpk": round(cpk, 4),
        "cpu": round(cpu, 4),
        "cpl": round(cpl, 4),
    }


def calculate_pp_ppk(values_1d: List[float], usl: float, lsl: float) -> Dict[str, float]:
    """Calculate Pp and Ppk using overall standard deviation."""
    if not values_1d or len(values_1d) < 2:
        return {"pp": 0.0, "ppk": 0.0, "ppu": 0.0, "ppl": 0.0}

    mean = sum(values_1d) / len(values_1d)
    sigma = _sample_std(values_1d)
    if sigma == 0:
        return {"pp": 0.0, "ppk": 0.0, "ppu": 0.0, "ppl": 0.0}

    pp = (usl - lsl) / (6 * sigma)
    ppu = (usl - mean) / (3 * sigma)
    ppl = (mean - lsl) / (3 * sigma)
    ppk = min(ppu, ppl)

    return {
        "pp": round(pp, 4),
        "ppk": round(ppk, 4),
        "ppu": round(ppu, 4),
        "ppl": round(ppl, 4),
    }


def calculate_cm(values_1d: List[float], usl: float, lsl: float) -> Dict[str, float]:
    """Calculate Cm and Cmk (machine capability, very short term)."""
    if not values_1d or len(values_1d) < 2:
        return {"cm": 0.0, "cmk": 0.0}

    mean = sum(values_1d) / len(values_1d)
    sigma = _sample_std(values_1d)
    if sigma == 0:
        return {"cm": 0.0, "cmk": 0.0}

    cm = (usl - lsl) / (6 * sigma)
    cmk = min((usl - mean) / (3 * sigma), (mean - lsl) / (3 * sigma))

    return {
        "cm": round(cm, 4),
        "cmk": round(cmk, 4),
    }


def calculate_ppm(values_1d: List[float], usl: float, lsl: float) -> Dict[str, float]:
    """Calculate theoretical and actual PPM (parts per million out of spec)."""
    if not values_1d:
        return {"theoretical_ppm": 0.0, "actual_ppm": 0.0}

    mean = sum(values_1d) / len(values_1d)
    sigma = _sample_std(values_1d)

    # Actual PPM: count out of spec
    out_of_spec = sum(1 for v in values_1d if v > usl or v < lsl)
    actual_ppm = (out_of_spec / len(values_1d)) * 1_000_000

    # Theoretical PPM: based on normal distribution
    if sigma > 0:
        z_upper = (usl - mean) / sigma
        z_lower = (mean - lsl) / sigma
        # Using standard normal CDF approximation
        def _cdf(z):
            return 0.5 * (1 + math.erf(z / math.sqrt(2)))
        theoretical_ppm = ((1 - _cdf(z_upper)) + (1 - _cdf(z_lower))) * 1_000_000
    else:
        theoretical_ppm = 0.0

    return {
        "theoretical_ppm": round(theoretical_ppm, 2),
        "actual_ppm": round(actual_ppm, 2),
    }


def get_capability_grade(cpk: float) -> str:
    if cpk >= 1.67:
        return "优秀"
    elif cpk >= 1.33:
        return "合格"
    elif cpk >= 1.0:
        return "警告"
    else:
        return "不合格"


def get_capability_advice(cpk: float) -> str:
    if cpk >= 1.67:
        return "过程能力充足，维持现状。"
    elif cpk >= 1.33:
        return "过程能力可接受，持续监控。"
    elif cpk >= 1.0:
        return "过程能力不足，需分析变异来源并采取改进措施。"
    else:
        return "过程能力严重不足，立即停止生产并启动整改。"


def calculate_p_limits(batches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """P chart: proportion nonconforming. Variable sample size supported."""
    if not batches:
        return {"cl": None, "ucl_list": [], "lcl_list": []}
    total_defects = sum(b["defect_count"] for b in batches)
    total_inspected = sum(b["inspected_count"] for b in batches)
    if total_inspected == 0:
        return {"cl": None, "ucl_list": [], "lcl_list": []}
    p_bar = total_defects / total_inspected
    ucl_list = []
    lcl_list = []
    for b in batches:
        n = b["inspected_count"]
        if n == 0:
            ucl_list.append(None)
            lcl_list.append(0.0)
            continue
        spread = 3 * math.sqrt(p_bar * (1 - p_bar) / n)
        ucl_list.append(round(p_bar + spread, 4))
        lcl_list.append(max(0.0, round(p_bar - spread, 4)))
    return {"cl": round(p_bar, 4), "ucl_list": ucl_list, "lcl_list": lcl_list}


def calculate_np_limits(batches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """NP chart: number nonconforming. Fixed sample size required."""
    if not batches:
        return {"cl": None, "ucl": None, "lcl": None}
    n_values = [b["inspected_count"] for b in batches]
    if len(set(n_values)) > 1:
        raise ValueError("NP图要求每批次样本量固定一致")
    n = n_values[0]
    np_bar = sum(b["defect_count"] for b in batches) / len(batches)
    p_bar = np_bar / n if n > 0 else 0
    spread = 3 * math.sqrt(np_bar * (1 - p_bar))
    return {
        "cl": round(np_bar, 4),
        "ucl": round(np_bar + spread, 4),
        "lcl": max(0.0, round(np_bar - spread, 4)),
    }


def calculate_c_limits(batches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """C chart: count of defects per inspection unit. Fixed unit size assumed."""
    if not batches:
        return {"cl": None, "ucl": None, "lcl": None}
    c_bar = sum(b["defect_count"] for b in batches) / len(batches)
    spread = 3 * math.sqrt(c_bar)
    return {
        "cl": round(c_bar, 4),
        "ucl": round(c_bar + spread, 4),
        "lcl": max(0.0, round(c_bar - spread, 4)),
    }


def calculate_u_limits(batches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """U chart: defects per unit. Variable sample size supported."""
    if not batches:
        return {"cl": None, "ucl_list": [], "lcl_list": []}
    total_defects = sum(b["defect_count"] for b in batches)
    total_inspected = sum(b["inspected_count"] for b in batches)
    if total_inspected == 0:
        return {"cl": None, "ucl_list": [], "lcl_list": []}
    u_bar = total_defects / total_inspected
    ucl_list = []
    lcl_list = []
    for b in batches:
        n = b["inspected_count"]
        if n == 0:
            ucl_list.append(None)
            lcl_list.append(0.0)
            continue
        spread = 3 * math.sqrt(u_bar / n)
        ucl_list.append(round(u_bar + spread, 4))
        lcl_list.append(max(0.0, round(u_bar - spread, 4)))
    return {"cl": round(u_bar, 4), "ucl_list": ucl_list, "lcl_list": lcl_list}
