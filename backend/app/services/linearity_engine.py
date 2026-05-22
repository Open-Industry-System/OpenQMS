"""Linearity calculation engine — linear regression of bias vs reference value."""

import math

from app.models.linearity import LinearityStudy, LinearityMeasurement, LinearityResult


def compute_linearity(study: LinearityStudy, measurements: list[LinearityMeasurement]) -> LinearityResult:
    n = len(measurements)
    if n < 2:
        raise ValueError("need at least 2 measurements for linearity study")

    x = [m.reference_value for m in measurements]
    y = [m.measured_value - m.reference_value for m in measurements]  # bias

    x_mean = sum(x) / n
    y_mean = sum(y) / n

    ss_xy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    ss_xx = sum((xi - x_mean) ** 2 for xi in x)

    slope = ss_xy / ss_xx if ss_xx != 0 else 0
    intercept = y_mean - slope * x_mean

    # R-squared
    ss_yy = sum((yi - y_mean) ** 2 for yi in y)
    r_squared = (ss_xy ** 2) / (ss_xx * ss_yy) if ss_xx != 0 and ss_yy != 0 else 0

    # Linearity = slope × process variation (use tolerance if available)
    tolerance = 0
    if study.tolerance_upper is not None and study.tolerance_lower is not None:
        tolerance = study.tolerance_upper - study.tolerance_lower
    process_var = tolerance if tolerance > 0 else max(x) - min(x)
    linearity = abs(slope) * process_var
    linearity_percent = (linearity / process_var * 100) if process_var > 0 else None

    # Bias at lower and upper reference values
    bias_at_lower = slope * min(x) + intercept
    bias_at_upper = slope * max(x) + intercept

    # Conclusion: accept if |linearity%| < 5% and R² > 0.8
    conclusion = "可接受" if (linearity_percent is not None and linearity_percent < 5 and r_squared > 0.8) else "不可接受"

    return LinearityResult(
        study_id=study.study_id,
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
        linearity=linearity,
        linearity_percent=linearity_percent,
        bias_at_lower=bias_at_lower,
        bias_at_upper=bias_at_upper,
        conclusion=conclusion,
    )
