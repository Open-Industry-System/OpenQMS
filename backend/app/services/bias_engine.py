"""Bias calculation engine — one-sample t-test against reference value."""

import math

from app.models.bias import BiasMeasurement, BiasResult, BiasStudy


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p: float) -> float:
    # Abramowitz & Stegun approximation
    if p < 0.5:
        t = math.sqrt(-2 * math.log(p))
    else:
        t = math.sqrt(-2 * math.log(1 - p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    numerator = c0 + c1 * t + c2 * t ** 2
    denominator = 1 + d1 * t + d2 * t ** 2 + d3 * t ** 3
    sign = 1 if p >= 0.5 else -1
    return sign * (t - numerator / denominator)


def _t_cdf(t: float, df: int) -> float:
    """Two-tailed p-value."""
    try:
        from scipy import stats
        return 2 * stats.t.sf(abs(t), df)
    except ImportError:
        # Normal approximation for df > 30, otherwise rough approx
        if df > 30:
            return 2 * (1 - _norm_cdf(abs(t)))
        # Coarse approximation for small df
        return 2 * (1 - _norm_cdf(abs(t) * math.sqrt(df / (df - 2))))


def _t_inv(p: float, df: int) -> float:
    try:
        from scipy import stats
        return stats.t.ppf(p, df)
    except ImportError:
        return _norm_ppf(p)


def compute_bias(study: BiasStudy, measurements: list[BiasMeasurement]) -> BiasResult:
    n = len(measurements)
    if n < 2:
        raise ValueError("need at least 2 measurements for bias study")
    values = [m.value for m in measurements]
    mean_val = sum(values) / n
    bias = mean_val - study.reference_value
    variance = sum((v - mean_val) ** 2 for v in values) / (n - 1)
    std_dev = math.sqrt(variance)
    se = std_dev / math.sqrt(n) if std_dev > 0 else 0
    t_stat = bias / se if se > 0 else 0
    df = n - 1
    p_value = _t_cdf(t_stat, df)
    t_crit = abs(_t_inv(0.025, df))
    ci_lower = bias - t_crit * se
    ci_upper = bias + t_crit * se
    # Conclusion: accept if |bias| < 5% of reference or p > 0.05
    ref = abs(study.reference_value) if study.reference_value != 0 else 1
    bias_percent = (bias / ref) * 100
    conclusion = "可接受" if abs(bias_percent) < 5 and p_value > 0.05 else "不可接受"
    return BiasResult(
        study_id=study.study_id,
        mean=mean_val,
        bias=bias,
        bias_percent=bias_percent,
        std_dev=std_dev,
        t_statistic=t_stat,
        p_value=p_value,
        lower_ci=ci_lower,
        upper_ci=ci_upper,
        conclusion=conclusion,
    )
