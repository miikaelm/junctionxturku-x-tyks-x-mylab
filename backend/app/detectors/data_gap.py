"""Data-quality gap detector (ANOM-04): "no data" must never read as "no resistance".

Two daily tests per ward, both against the ward's own recent sample rate:
- Silence: the same Poisson test as the freshness badge (VIEW-12). With λ samples/day over the
  FRESHNESS_RATE_LOOKBACK_DAYS up to the last sample, d silent days have probability exp(−λd).
- Low volume: samples in the last GAP_VOLUME_WINDOW_DAYS vs the same-length expectation from
  the FRESHNESS_RATE_LOOKBACK_DAYS before (Poisson lower tail). Catches a feed that thins out
  without stopping.
Either fires below GAP_ALERT_ALPHA, much stricter than the badge (see config).
"""

from datetime import date, timedelta

import numpy as np
from scipy.stats import poisson

from app.config import FRESHNESS_RATE_LOOKBACK_DAYS, GAP_ALERT_ALPHA, GAP_VOLUME_WINDOW_DAYS
from app.data.dataset import Dataset
from app.detectors.common import (
    Firing,
    cumulative,
    daily_counts,
    first_index,
    n_days,
    to_date,
    window_sums,
)


def detect_data_gaps(ds: Dataset, horizon: date, since: date | None = None) -> list[Firing]:
    t = np.arange(n_days(ds, horizon))
    L, V = FRESHNESS_RATE_LOOKBACK_DAYS, GAP_VOLUME_WINDOW_DAYS
    firings = []
    for ward in ds.wards.itertuples(index=False):
        dates = ds.cultures.sample_date[ds.cultures.ward_code == ward.ward_code]
        counts = daily_counts(ds, dates, horizon)
        cum = cumulative(counts)

        # Silence since the last sample (freshness rule).
        last = np.maximum.accumulate(np.where(counts > 0, t, -1))
        lb_start = np.clip(last - L + 1, 0, None)
        rate = window_sums(cum, lb_start, last) / np.maximum(last - lb_start + 1, 1)
        silent = t - last
        p_silence = np.exp(-rate * silent)
        silence = (last >= 0) & (p_silence < GAP_ALERT_ALPHA)

        # Low volume in the last week vs the lookback period before it.
        observed = window_sums(cum, t - V + 1, t)
        expected = window_sums(cum, t - V - L + 1, t - V) / L * V
        p_low = poisson.cdf(observed, expected)
        low = (t - V - L + 1 >= 0) & (p_low < GAP_ALERT_ALPHA)

        for i in np.flatnonzero((silence | low) & (t >= first_index(ds, since))):
            day = to_date(ds, i)
            if silence[i]:
                title = f"No samples for {silent[i]} days (usually {rate[i]:.1f} per day)"
            else:
                title = f"Only {observed[i]} samples in {V} days (expected ~{expected[i]:.0f})"
            firings.append(
                Firing(
                    type="data_gap",
                    ward=ward.ward_code,
                    subject="feed",
                    day=day,
                    title=title,
                    evidence={
                        "method": "Poisson test of the ward's silence / weekly volume against "
                        "its own recent sample rate",
                        "silent_days": int(silent[i]),
                        "last_sample": to_date(ds, last[i]).isoformat(),
                        "samples_per_day": round(float(rate[i]), 2),
                        "p_silence": float(p_silence[i]),
                        "observed": int(observed[i]),
                        "expected": round(float(expected[i]), 1),
                        "p_low_volume": float(p_low[i]),
                        "p_value": float(min(p_silence[i], p_low[i])),
                        "window": {
                            "start": (day - timedelta(days=V - 1)).isoformat(),
                            "end": day.isoformat(),
                        },
                    },
                )
            )
    return firings
