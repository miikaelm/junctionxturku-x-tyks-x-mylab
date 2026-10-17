"""Proportion estimates with honest uncertainty (STAT-01, STAT-02, STAT-03)."""

import math

from scipy.stats import norm

from app.config import CI_LEVEL, MIN_ISOLATES_FOR_PERCENT


def wilson_interval(k: int, n: int, level: float = CI_LEVEL) -> tuple[float, float]:
    """Wilson score interval for k successes out of n, as fractions in [0, 1]."""
    if n == 0:
        return 0.0, 1.0
    z = norm.ppf(0.5 + level / 2)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def estimate(r: int, n: int) -> dict:
    """Resistance estimate for r resistant of n first isolates. Percentages are 0–100."""
    lo, hi = wilson_interval(r, n)
    return {
        "n": int(n),
        "r": int(r),
        "pct": round(100 * r / n, 1) if n else None,
        "ci_low": round(100 * lo, 1),
        "ci_high": round(100 * hi, 1),
        "sufficient": n >= MIN_ISOLATES_FOR_PERCENT,
    }
