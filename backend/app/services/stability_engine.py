"""Stability calculation engine — Xbar-R control limits."""


from app.models.stability import StabilityMeasurement, StabilityResult, StabilityStudy

# AIAG SPC constants for subgroup size n
A2_TABLE = {2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483, 7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308}
D3_TABLE = {2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0.076, 8: 0.136, 9: 0.184, 10: 0.223}
D4_TABLE = {2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114, 6: 2.004, 7: 1.924, 8: 1.864, 9: 1.816, 10: 1.777}
D2_TABLE = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534, 7: 2.704, 8: 2.847, 9: 2.970, 10: 3.078}


def compute_stability(study: StabilityStudy, measurements: list[StabilityMeasurement]) -> StabilityResult:
    n = len(measurements)
    if n < 2:
        raise ValueError("need at least 2 subgroups for stability study")

    means = [m.sample_mean for m in measurements]
    ranges = [m.sample_range for m in measurements]

    xbar_bar = sum(means) / n
    r_bar = sum(ranges) / n

    subgroup_size = study.subgroup_size
    a2 = A2_TABLE.get(subgroup_size, 0.577)
    d3 = D3_TABLE.get(subgroup_size, 0)
    d4 = D4_TABLE.get(subgroup_size, 2.114)

    # Xbar control limits
    ucl_mean = xbar_bar + a2 * r_bar
    lcl_mean = xbar_bar - a2 * r_bar
    cl_mean = xbar_bar

    # R control limits
    ucl_range = d4 * r_bar
    lcl_range = d3 * r_bar
    cl_range = r_bar

    # Cpk estimate (if reference value and tolerance available)
    cpk = None
    if study.reference_value is not None:
        sigma = r_bar / D2_TABLE.get(subgroup_size, 2.326)
        tol_upper = getattr(study, "tolerance_upper", None)
        tol_lower = getattr(study, "tolerance_lower", None)
        if tol_upper is not None and tol_lower is not None:
            cpu = (tol_upper - xbar_bar) / (3 * sigma) if sigma > 0 else 0
            cpl = (xbar_bar - tol_lower) / (3 * sigma) if sigma > 0 else 0
            cpk = min(cpu, cpl)
        else:
            # Use reference value as target
            cpu = (study.reference_value + 3 * sigma - xbar_bar) / (3 * sigma) if sigma > 0 else 0
            cpl = (xbar_bar - (study.reference_value - 3 * sigma)) / (3 * sigma) if sigma > 0 else 0
            cpk = min(cpu, cpl)

    # Conclusion: accept if no points outside control limits (simplified)
    out_of_control = any(m > ucl_mean or m < lcl_mean for m in means)
    conclusion = "不可接受" if out_of_control else "可接受"

    return StabilityResult(
        study_id=study.study_id,
        factory_id=study.factory_id,
        ucl_mean=ucl_mean,
        lcl_mean=lcl_mean,
        cl_mean=cl_mean,
        ucl_range=ucl_range,
        lcl_range=lcl_range,
        cl_range=cl_range,
        cpk=cpk,
        conclusion=conclusion,
    )
