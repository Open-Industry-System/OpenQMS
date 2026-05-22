"""GRR calculation engine — AIAG MSA 4th Edition, average-and-range method."""

import math
from collections import defaultdict

from app.models.grr import GrrStudy, GrrMeasurement, GrrResult


# AIAG MSA 4th Ed constants (include 5.15 process spread factor)
# K1: repeatability, based on number of trials (d2 for large g)
K1_TABLE = {2: 4.56, 3: 3.05}
# K2: reproducibility, based on number of appraisers (d2* for g=1)
K2_TABLE = {2: 3.65, 3: 2.70}
# K3: part variation, based on number of parts (d2* for g=1)
K3_TABLE = {
    2: 3.65,
    3: 2.70,
    4: 2.30,
    5: 2.08,
    6: 1.93,
    7: 1.82,
    8: 1.74,
    9: 1.67,
    10: 1.62,
}


def _get_k(table: dict[int, float], key: int) -> float:
    if key in table:
        return table[key]
    # Linear interpolation for values outside table
    keys = sorted(table.keys())
    if key < keys[0]:
        return table[keys[0]]
    if key > keys[-1]:
        # Extrapolate: K roughly proportional to 1/sqrt(m)
        return table[keys[-1]] * math.sqrt(keys[-1] / key)
    # Interpolate
    for i in range(len(keys) - 1):
        if keys[i] <= key <= keys[i + 1]:
            t = (key - keys[i]) / (keys[i + 1] - keys[i])
            return table[keys[i]] * (1 - t) + table[keys[i + 1]] * t
    return table[keys[-1]]


def compute_grr(study: GrrStudy, measurements: list[GrrMeasurement]) -> GrrResult:
    """Compute GRR using average-and-range method."""
    a = study.appraiser_count
    p = study.part_count
    r = study.trial_count

    # Group measurements: appraiser → part → [trial values]
    data: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for m in measurements:
        data[m.appraiser_name][m.part_no].append(m.value)

    # Compute cell means and ranges
    appraiser_means: dict[str, float] = {}
    all_ranges: list[float] = []
    part_means: dict[str, list[float]] = defaultdict(list)

    for appraiser, parts in data.items():
        appraiser_values: list[float] = []
        for part, values in parts.items():
            if len(values) != r:
                raise ValueError(
                    f"missing measurements for {appraiser}, part {part}: "
                    f"expected {r}, got {len(values)}"
                )
            cell_mean = sum(values) / r
            cell_range = max(values) - min(values)
            appraiser_values.append(cell_mean)
            part_means[part].append(cell_mean)
            all_ranges.append(cell_range)
        appraiser_means[appraiser] = sum(appraiser_values) / len(appraiser_values)

    # Average range
    R_bar = sum(all_ranges) / len(all_ranges) if all_ranges else 0

    # Appraiser mean diff
    if len(appraiser_means) >= 2:
        X_bar_diff = max(appraiser_means.values()) - min(appraiser_means.values())
    else:
        X_bar_diff = 0

    # Part mean range
    part_mean_values = [
        sum(vals) / len(vals) for vals in part_means.values()
    ]
    R_p = (
        max(part_mean_values) - min(part_mean_values)
        if len(part_mean_values) >= 2
        else 0
    )

    # K coefficients
    K1 = _get_k(K1_TABLE, r)
    K2 = _get_k(K2_TABLE, a)
    K3 = _get_k(K3_TABLE, p)

    # EV (Equipment Variation / Repeatability)
    EV = R_bar * K1

    # AV (Appraiser Variation / Reproducibility)
    av_sq = (X_bar_diff * K2) ** 2 - (EV ** 2) / (p * r)
    AV = math.sqrt(max(av_sq, 0))

    # GRR
    GRR = math.sqrt(EV ** 2 + AV ** 2)

    # PV (Part Variation)
    PV = R_p * K3

    # TV (Total Variation)
    TV = math.sqrt(GRR ** 2 + PV ** 2)

    # ndc (Number of Distinct Categories)
    ndc = 1.41 * (PV / GRR) if GRR > 0 else 999

    # Percentages
    tolerance = None
    if study.tolerance_upper is not None and study.tolerance_lower is not None:
        tolerance = study.tolerance_upper - study.tolerance_lower

    grr_percent_tol = (GRR / tolerance * 100) if tolerance and tolerance > 0 else None
    grr_percent_tv = (GRR / TV * 100) if TV > 0 else 100
    ev_percent = (EV / TV * 100) if TV > 0 else 0
    av_percent = (AV / TV * 100) if TV > 0 else 0
    pv_percent = (PV / TV * 100) if TV > 0 else 0

    # Conclusion (Chinese labels per project convention)
    if grr_percent_tol is not None:
        if grr_percent_tol < 10 and ndc >= 5:
            conclusion = "可接受"
        elif grr_percent_tol <= 30 and ndc >= 2:
            conclusion = "条件接受"
        else:
            conclusion = "不可接受"
    else:
        if grr_percent_tv < 10 and ndc >= 5:
            conclusion = "可接受"
        elif grr_percent_tv <= 30 and ndc >= 2:
            conclusion = "条件接受"
        else:
            conclusion = "不可接受"

    return GrrResult(
        study_id=study.study_id,
        ev=EV,
        av=AV,
        grr=GRR,
        pv=PV,
        tv=TV,
        ndc=ndc,
        grr_percent_tol=grr_percent_tol if grr_percent_tol is not None else 0,
        grr_percent_tv=grr_percent_tv,
        ev_percent=ev_percent,
        av_percent=av_percent,
        pv_percent=pv_percent,
        conclusion=conclusion,
    )
