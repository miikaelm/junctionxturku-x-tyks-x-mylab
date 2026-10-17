"""Slow drift and long-term trends (ANOM-03), for the stewardship trend explorer (V6).

Every location (all, each institution, each ward) × specimen × organism × antibiotic is a series
of calendar quarters, counting first isolates per quarter (DATA-02); the quarter containing the
as-of date runs up to it. Trend test: Cochran–Armitage (the score test for a linear trend in a
proportion), with the matching weighted least-squares line as the fitted trend. Gates leave out
thin series, and Benjamini–Hochberg runs across every series that passed them (STAT-08).
Intrinsic pairs are never tested (DATA-07).

Threshold crossings compare the last 12 months with the 12 months before against the empirical-
use limit (config.EMPIRICAL_THRESHOLD_PCT), with n ≥ 30 in both (STAT-01).

This is the "not daily" workflow: findings feed V6, not the alert inbox.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact, norm

from app.config import (
    ANNUAL_WINDOW_DAYS,
    EMPIRICAL_THRESHOLD_PCT,
    MIN_ISOLATES_FOR_PERCENT,
    TREND_MIN_CHANGE_PP,
    TREND_MIN_QUARTERS,
    TREND_MIN_TOTAL_N,
)
from app.data.dataset import Dataset
from app.data.first_isolate import FIRST_ISOLATE_KEY, first_isolates
from app.data.intrinsic import INTRINSIC_RESISTANCE
from app.data.scope import Scope
from app.detectors.common import bh_qvalues, significant
from app.stats.proportions import estimate

SERIES = ["loc", "specimen", "organism", "antibiotic_code"]

_memo: dict[tuple, tuple[Dataset, object]] = {}


def _cached(ds: Dataset, key: tuple, compute):
    full = (id(ds), *key)
    hit = _memo.get(full)
    if hit is not None and hit[0] is ds:
        return hit[1]
    value = compute()
    if len(_memo) >= 16:
        _memo.clear()
    _memo[full] = (ds, value)
    return value


def _locations(iso: pd.DataFrame) -> pd.DataFrame:
    """Each isolate once per location level that contains it: all, its institution, its ward."""
    return pd.concat(
        [iso.assign(loc="all"), iso.assign(loc=iso.institution), iso.assign(loc=iso.ward_code)],
        ignore_index=True,
    )


def _counts(ds: Dataset, first: pd.DataFrame, period: str) -> pd.DataFrame:
    """n and r per series × period, from first isolates carrying `loc` and `period` columns."""
    ast = first[["isolate_id", "loc", "specimen", period]].merge(ds.ast, on="isolate_id")
    intrinsic = pd.MultiIndex.from_tuples(
        [(o, a) for o, codes in INTRINSIC_RESISTANCE.items() for a in codes]
    )
    ast = ast[~pd.MultiIndex.from_frame(ast[["organism", "antibiotic_code"]]).isin(intrinsic)]
    return ast.groupby([*SERIES, period]).resistant.agg(n="size", r="sum").reset_index()


def quarters(ds: Dataset, as_of: date) -> pd.PeriodIndex:
    return pd.period_range(ds.start, pd.Timestamp(as_of), freq="Q")


def quarterly_counts(ds: Dataset, as_of: date) -> pd.DataFrame:
    def compute():
        iso = ds.isolates[ds.isolates.sample_date <= pd.Timestamp(as_of)]
        iso = _locations(iso.assign(quarter=iso.sample_date.dt.to_period("Q")))
        first = iso.drop_duplicates(["loc", "quarter", *FIRST_ISOLATE_KEY])
        out = _counts(ds, first, "quarter")
        q0 = quarters(ds, as_of)[0]
        out["x"] = [(q - q0).n / 4 for q in out.quarter]  # time in years
        return out

    return _cached(ds, ("quarters", as_of), compute)


def year_counts(ds: Dataset, as_of: date) -> pd.DataFrame:
    """n, r per series for the last 12 months (block 0) and the 12 months before (block 1)."""

    def compute():
        iso = ds.isolates[ds.isolates.sample_date <= pd.Timestamp(as_of)]
        block = (pd.Timestamp(as_of) - iso.sample_date).dt.days // ANNUAL_WINDOW_DAYS
        iso = _locations(iso.assign(block=block)[block <= 1])
        first = iso.drop_duplicates(["loc", "block", *FIRST_ISOLATE_KEY])
        return _counts(ds, first, "block")

    return _cached(ds, ("years", as_of), compute)


def trend_tests(q: pd.DataFrame) -> pd.DataFrame:
    """Cochran–Armitage statistics per series from per-quarter n, r and time x (years)."""
    q = q.assign(nx=q.n * q.x, nxx=q.n * q.x * q.x, rx=q.r * q.x)
    g = q.groupby(SERIES).agg(
        N=("n", "sum"),
        R=("r", "sum"),
        Sx=("nx", "sum"),
        Sxx=("nxx", "sum"),
        Sxr=("rx", "sum"),
        quarters=("n", "size"),
        x_first=("x", "min"),
        x_last=("x", "max"),
    )
    pbar = g.R / g.N
    sxx = g.Sxx - g.Sx**2 / g.N
    t = g.Sxr - pbar * g.Sx
    var = pbar * (1 - pbar) * sxx
    with np.errstate(divide="ignore", invalid="ignore"):
        z = t / np.sqrt(var)
        slope = t / sxx  # proportion per year
    g["p_bar"] = pbar
    g["x_mean"] = g.Sx / g.N
    g["slope"] = slope
    g["z"] = z
    g["p_value"] = 2 * norm.sf(np.abs(z))
    g["change_pp"] = 100 * slope * (g.x_last - g.x_first)
    g["eligible"] = (
        (g.quarters >= TREND_MIN_QUARTERS) & (g.N >= TREND_MIN_TOTAL_N) & (var > 0)
    ).to_numpy()
    tested = g.eligible & (g.change_pp.abs() >= TREND_MIN_CHANGE_PP)
    g["q_value"] = np.nan
    g.loc[tested, "q_value"] = bh_qvalues(g.p_value[tested].to_numpy(), m=int(g.eligible.sum()))
    g["significant"] = tested & significant(g.q_value.fillna(1).to_numpy())
    return g


def all_trend_tests(ds: Dataset, as_of: date) -> pd.DataFrame:
    return _cached(ds, ("tests", as_of), lambda: trend_tests(quarterly_counts(ds, as_of)))


def findings(ds: Dataset, as_of: date) -> dict:
    """Significant trends and threshold crossings across all locations (V6 findings list)."""
    tests = all_trend_tests(ds, as_of)
    years = year_counts(ds, as_of).set_index([*SERIES, "block"])
    labels = _location_labels(ds)
    names = ds.antibiotics.set_index("antibiotic_code").antibiotic

    def base(key) -> dict:
        loc, specimen, organism, code = key
        out = {
            "location": loc,
            "location_label": labels[loc],
            "level": _level(ds, loc),
            "specimen": specimen,
            "organism": organism,
            "antibiotic_code": code,
            "antibiotic": names[code],
        }
        for block, name in ((0, "last_12m"), (1, "prev_12m")):
            n, r = years.loc[(*key, block), ["n", "r"]] if (*key, block) in years.index else (0, 0)
            out[name] = estimate(int(r), int(n))
        return out

    trends = []
    for key, row in tests[tests.significant].iterrows():
        trends.append({**base(key), "trend": _trend_dict(row)})
    trends.sort(key=lambda f: (f["trend"]["direction"] != "up", f["trend"]["q_value"]))

    crossings = []
    y0 = years.xs(0, level="block")
    y1 = years.xs(1, level="block")
    both = y0.join(y1, lsuffix="0", rsuffix="1", how="inner")
    both = both[(both.n0 >= MIN_ISOLATES_FOR_PERCENT) & (both.n1 >= MIN_ISOLATES_FOR_PERCENT)]
    pct0, pct1 = 100 * both.r0 / both.n0, 100 * both.r1 / both.n1
    up = (pct1 < EMPIRICAL_THRESHOLD_PCT) & (pct0 >= EMPIRICAL_THRESHOLD_PCT)
    down = (pct1 >= EMPIRICAL_THRESHOLD_PCT) & (pct0 < EMPIRICAL_THRESHOLD_PCT)
    for key in both.index[up | down]:
        f = base(key)
        f["direction"] = "up" if up[key] else "down"
        # The 95 % interval of the last 12 months lies entirely on the new side of the line.
        f["clearly"] = bool(
            f["last_12m"]["ci_low"] >= EMPIRICAL_THRESHOLD_PCT
            if f["direction"] == "up"
            else f["last_12m"]["ci_high"] < EMPIRICAL_THRESHOLD_PCT
        )
        if key in tests.index:
            f["trend"] = _trend_dict(tests.loc[key])
        crossings.append(f)
    crossings.sort(key=lambda f: (f["direction"] != "up", -f["last_12m"]["pct"]))

    return {
        "as_of": as_of.isoformat(),
        "threshold_pct": EMPIRICAL_THRESHOLD_PCT,
        "tested": int(tests.eligible.sum()),
        "trends": trends,
        "crossings": crossings,
    }


def _trend_dict(row: pd.Series) -> dict:
    q = row.q_value
    return {
        "direction": "up" if row.slope > 0 else "down",
        "pp_per_year": round(100 * float(row.slope), 1),
        "change_pp": round(float(row.change_pp), 1),
        "p_value": float(row.p_value),
        "q_value": None if pd.isna(q) else float(q),
        "significant": bool(row.significant),
        "eligible": bool(row.eligible),
        "n": int(row.N),
        "quarters": int(row.quarters),
    }


def series(ds: Dataset, scope: Scope, organism: str, code: str, as_of: date) -> dict:
    """One location × specimen × organism × antibiotic: quarterly points with the fitted trend,
    the threshold, calendar years and the last 12 months vs the 12 months before."""
    key = (scope.location, scope.specimen, organism, code)
    q = quarterly_counts(ds, as_of)
    q = q[(q[SERIES] == pd.Series(dict(zip(SERIES, key)))).all(axis=1)].set_index("quarter")
    tests = all_trend_tests(ds, as_of)
    test = tests.loc[key] if key in tests.index else None

    start, end = ds.start.date(), as_of
    points = []
    for period in quarters(ds, as_of):
        n, r = (int(q.n[period]), int(q.r[period])) if period in q.index else (0, 0)
        x = (period - quarters(ds, as_of)[0]).n / 4
        fitted = None
        if test is not None and test.N > 0 and np.isfinite(test.slope):
            fitted = round(100 * float(test.p_bar + test.slope * (x - test.x_mean)), 1)
        points.append(
            {
                "label": f"{period.year} Q{period.quarter}",
                "start": max(period.start_time.date(), start).isoformat(),
                "end": min(period.end_time.date(), end).isoformat(),
                "fitted": fitted,
                **estimate(r, n),
            }
        )

    crossing = None
    if test is not None and test.slope and np.isfinite(test.slope):
        x_star = test.x_mean + (EMPIRICAL_THRESHOLD_PCT / 100 - test.p_bar) / test.slope
        if test.x_first <= x_star <= test.x_last:
            q0 = quarters(ds, as_of)[0]
            crossing = (q0 + int(x_star * 4)).strftime("%Y Q%q")

    return {
        "as_of": as_of.isoformat(),
        "scope": scope.to_dict(ds.wards),
        "organism": organism,
        "antibiotic_code": code,
        "antibiotic": ds.antibiotics.set_index("antibiotic_code").antibiotic[code],
        "threshold_pct": EMPIRICAL_THRESHOLD_PCT,
        "points": points,
        "trend": _trend_dict(test) if test is not None else None,
        "trend_crosses_threshold": crossing,
        "years": _calendar_years(ds, scope, organism, code, as_of),
        "year_vs_year": _year_vs_year(ds, scope, organism, code, as_of),
    }


def _rate(ds: Dataset, scope: Scope, organism: str, code: str, start: date, end: date) -> dict:
    iso = scope.apply(ds.isolates)
    iso = iso[iso.sample_date.between(pd.Timestamp(start), pd.Timestamp(end))]
    iso = first_isolates(iso[iso.organism.eq(organism)])
    ast = ds.ast[ds.ast.isolate_id.isin(iso.isolate_id) & ds.ast.antibiotic_code.eq(code)]
    return estimate(int(ast.resistant.sum()), len(ast))


def _calendar_years(ds, scope, organism, code, as_of) -> list[dict]:
    out = []
    for year in range(ds.start.year, as_of.year + 1):
        start = max(date(year, 1, 1), ds.start.date())
        end = min(date(year, 12, 31), as_of)
        out.append(
            {
                "year": year,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "partial": start != date(year, 1, 1) or end != date(year, 12, 31),
                **_rate(ds, scope, organism, code, start, end),
            }
        )
    return out


def _year_vs_year(ds, scope, organism, code, as_of) -> dict:
    last_start = as_of - timedelta(days=ANNUAL_WINDOW_DAYS - 1)
    prev_end = last_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=ANNUAL_WINDOW_DAYS - 1)
    last = _rate(ds, scope, organism, code, last_start, as_of)
    prev = _rate(ds, scope, organism, code, prev_start, prev_end)
    p = None
    if last["n"] and prev["n"]:
        table = [[last["r"], last["n"] - last["r"]], [prev["r"], prev["n"] - prev["r"]]]
        p = float(fisher_exact(table)[1])
    return {
        "last": {"start": last_start.isoformat(), "end": as_of.isoformat(), **last},
        "previous": {"start": prev_start.isoformat(), "end": prev_end.isoformat(), **prev},
        "p_value": p,
        "method": "Fisher exact test (two-sided), first isolates per 12-month window",
    }


def _location_labels(ds: Dataset) -> dict[str, str]:
    locs = ["all", "hospital", "primary_care", *ds.wards.ward_code]
    return {loc: Scope(loc).label(ds.wards) for loc in locs}


def _level(ds: Dataset, loc: str) -> str:
    return Scope(loc).level(ds.wards)
