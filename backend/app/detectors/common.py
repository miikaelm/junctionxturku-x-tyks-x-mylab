"""Shared pieces for the anomaly detectors (ANOM-*) and sentinel rules (NOTIF-01).

Every detector scans the whole timeline once and returns `Firing`s: "on day t, using only data
up to t, this test was positive". Because no firing looks past its own day, the alerts at any
as-of date are simply the firings up to that date (LIVE-01), so the timeline can be computed
once and cached.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.config import FDR_Q, PHENOTYPES
from app.data.dataset import Dataset


@dataclass(frozen=True)
class Firing:
    type: str  # key in config.ALERT_TYPES
    ward: str
    subject: str  # what the alert is about, stable across firings (e.g. "MRSA")
    day: date  # evaluation day; the firing used no data after it
    title: str
    evidence: dict = field(default_factory=dict)  # why it fired (ANOM-06)
    isolate_ids: tuple[str, ...] = ()  # cases supporting this firing


def bh_qvalues(p: np.ndarray, m: int | None = None) -> np.ndarray:
    """Benjamini–Hochberg adjusted p-values (STAT-08).

    `m` is the size of the family; hypotheses not passed in count as p = 1 (never rejected).
    """
    p = np.asarray(p, dtype=float)
    if p.size == 0:
        return p
    m = max(m or p.size, p.size)
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, p.size + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(q)
    out[order] = np.minimum(q, 1.0)
    return out


def significant(q: np.ndarray) -> np.ndarray:
    return q <= FDR_Q


def day_index(ds: Dataset, dates: pd.Series) -> np.ndarray:
    return (dates - ds.start).dt.days.to_numpy()


def to_date(ds: Dataset, idx: int) -> date:
    return ds.start.date() + timedelta(days=int(idx))


def n_days(ds: Dataset, horizon: date) -> int:
    return (horizon - ds.start.date()).days + 1


def daily_counts(ds: Dataset, dates: pd.Series, horizon: date) -> np.ndarray:
    idx = day_index(ds, dates)
    return np.bincount(idx, minlength=n_days(ds, horizon))[: n_days(ds, horizon)]


def window_sums(cum: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    """Sum of daily counts over [start, end] (inclusive) from a cumulative array with a leading
    zero (cum[i] = sum of days < i). Empty or out-of-range windows sum to 0."""
    start = np.clip(start, 0, None)
    end = np.clip(end, -1, None)
    return np.where(end >= start, cum[..., end + 1] - cum[..., start], 0)


def cumulative(counts: np.ndarray) -> np.ndarray:
    pad = np.zeros(counts.shape[:-1] + (1,), dtype=counts.dtype)
    return np.concatenate([pad, np.cumsum(counts, axis=-1)], axis=-1)


def phenotype_cases(ds: Dataset) -> pd.DataFrame:
    """One row per isolate carrying a resistance phenotype (ESBL / MRSA / VRE / CPE)."""
    parts = [ds.isolates[ds.isolates[p.lower()].eq(1)].assign(phenotype=p) for p in PHENOTYPES]
    cases = pd.concat(parts, ignore_index=True)
    return cases.sort_values(["sample_date", "isolate_id"], kind="stable").reset_index(drop=True)


def days_since_previous(events: pd.DataFrame, keys: list[str], start: pd.Timestamp) -> pd.DataFrame:
    """For date-sorted events, the days since the previous event with the same keys.

    Adds `gap_days` and `first_ever` (no earlier event: the gap counts from `start`, the first
    day of the data, so it means "at least this long").
    """
    prev = events.groupby(keys, sort=False).sample_date.shift()
    out = events.assign(first_ever=prev.isna())
    out["gap_days"] = (out.sample_date - prev.fillna(start)).dt.days
    return out
