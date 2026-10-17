"""Data freshness per ward (VIEW-12): is the feed alive, so "no data" isn't read as "no resistance"?

A ward's silence is judged against its own recent sample rate: with λ samples/day, the chance
of d silent days is exp(-λ·d) (Poisson). Busy wards go stale after a day; ICU needs several.
"""

import math
from datetime import date, timedelta

import pandas as pd

from app.config import FRESHNESS_ALPHA, FRESHNESS_RATE_LOOKBACK_DAYS, FRESHNESS_WARN_ALPHA
from app.data.dataset import Dataset


def ward_freshness(ds: Dataset, as_of: date) -> list[dict]:
    cultures = ds.cultures[ds.cultures.sample_date <= pd.Timestamp(as_of)]
    out = []
    for ward in ds.wards.itertuples(index=False):
        dates = cultures.sample_date[cultures.ward_code == ward.ward_code]
        if dates.empty:
            out.append(_entry(ward, None, None, None, None, "no_data"))
            continue
        last = dates.iloc[-1].date()
        lookback_start = last - timedelta(days=FRESHNESS_RATE_LOOKBACK_DAYS - 1)
        lookback_days = (last - max(lookback_start, ds.start.date())).days + 1
        recent = dates[dates >= pd.Timestamp(lookback_start)]
        rate = len(recent) / lookback_days
        silent_days = (as_of - last).days
        p_silence = math.exp(-rate * silent_days)
        if p_silence < FRESHNESS_ALPHA:
            status = "stale"
        elif p_silence < FRESHNESS_WARN_ALPHA:
            status = "delayed"
        else:
            status = "ok"
        out.append(_entry(ward, last, silent_days, rate, p_silence, status))
    return out


def _entry(ward, last, silent_days, rate, p_silence, status) -> dict:
    return {
        "ward_code": ward.ward_code,
        "ward_en": ward.ward_en,
        "last_sample": last.isoformat() if last else None,
        "days_since_last": silent_days,
        "samples_per_day": round(rate, 2) if rate is not None else None,
        "p_silence": p_silence,
        "status": status,
    }
