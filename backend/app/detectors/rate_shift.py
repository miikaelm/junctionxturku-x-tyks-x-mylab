"""Sudden resistance-rate shift detector (ANOM-02).

Once a week (end of ISO week), for every ward × specimen × organism × antibiotic:
  recent   = first isolates in the last RECENT_WINDOW_DAYS (4 weeks),
  baseline = first isolates in the ANNUAL_WINDOW_DAYS (12 months) before that,
  test     = one-sided Fisher exact test "recent resistance is higher than baseline".
First isolates are taken per ward and window (DATA-02). Gates: enough isolates in both periods
and an increase of at least RATE_SHIFT_MIN_INCREASE_PP; intrinsic pairs are never tested
(DATA-07). P-values are FDR-corrected across all cells tested that week (STAT-08).
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import hypergeom

from app.config import (
    ANNUAL_WINDOW_DAYS,
    MIN_BASELINE_DAYS,
    RATE_SHIFT_EVAL_WEEKDAY,
    RATE_SHIFT_MIN_BASELINE_N,
    RATE_SHIFT_MIN_INCREASE_PP,
    RATE_SHIFT_MIN_RECENT_N,
    RECENT_WINDOW_DAYS,
)
from app.data.dataset import Dataset
from app.data.intrinsic import is_intrinsic
from app.detectors.common import (
    Firing,
    bh_qvalues,
    day_index,
    first_index,
    n_days,
    significant,
    to_date,
)
from app.stats.proportions import estimate

STRATUM = ["ward_code", "patient_id", "organism", "specimen"]  # first isolate per ward
CELL = ["ward_code", "specimen", "organism", "antibiotic_code"]


def detect_rate_shifts(ds: Dataset, horizon: date, since: date | None = None) -> list[Firing]:
    iso = ds.isolates[["isolate_id", *STRATUM]].copy()
    iso["day"] = day_index(ds, ds.isolates.sample_date)
    iso_pos = pd.Series(np.arange(len(iso)), index=iso.isolate_id)

    ast = ds.ast.merge(iso[["isolate_id", "ward_code", "specimen"]], on="isolate_id")
    ast = ast[[not is_intrinsic(o, a) for o, a in zip(ast.organism, ast.antibiotic_code)]]
    cell_id, cells = pd.MultiIndex.from_frame(ast[CELL]).factorize()
    ast_iso = iso_pos[ast.isolate_id].to_numpy()
    ast_res = ast.resistant.to_numpy()
    n_cells = len(cells)

    def counts(start: int, end: int) -> tuple[np.ndarray, np.ndarray]:
        window = iso[(iso.day >= start) & (iso.day <= end)]
        first = np.zeros(len(iso), dtype=bool)
        first[window.drop_duplicates(STRATUM).index] = True  # iso is date-sorted
        sel = first[ast_iso]
        n = np.bincount(cell_id[sel], minlength=n_cells)
        r = np.bincount(cell_id[sel], weights=ast_res[sel], minlength=n_cells).astype(int)
        return n, r

    first_day = ds.start.date() + timedelta(days=RECENT_WINDOW_DAYS + MIN_BASELINE_DAYS - 1)
    firings = []
    for t in range(first_index(ds, since), n_days(ds, horizon)):
        day = to_date(ds, t)
        if day.weekday() != RATE_SHIFT_EVAL_WEEKDAY or day < first_day:
            continue
        n1, r1 = counts(t - RECENT_WINDOW_DAYS + 1, t)
        b_end = t - RECENT_WINDOW_DAYS
        n0, r0 = counts(b_end - ANNUAL_WINDOW_DAYS + 1, b_end)

        eligible = (n1 >= RATE_SHIFT_MIN_RECENT_N) & (n0 >= RATE_SHIFT_MIN_BASELINE_N)
        with np.errstate(divide="ignore", invalid="ignore"):
            increase_pp = 100 * (r1 / n1 - r0 / n0)
        tested = eligible & (increase_pp >= RATE_SHIFT_MIN_INCREASE_PP)
        if not tested.any():
            continue
        # One-sided Fisher exact: P(≥ r1 of the r0 + r1 resistant fall in the recent n1).
        idx = np.flatnonzero(tested)
        p = hypergeom.sf(r1[idx] - 1, n0[idx] + n1[idx], r0[idx] + r1[idx], n1[idx])
        m = int(eligible.sum())
        q = bh_qvalues(p, m=m)
        hits: dict[tuple[str, str, str], list[dict]] = {}
        for j in np.flatnonzero(significant(q)):
            i = idx[j]
            ward, specimen, organism, code = cells[i]
            hits.setdefault((ward, specimen, organism), []).append(
                {
                    "antibiotic_code": code,
                    "observed": estimate(int(r1[i]), int(n1[i])),
                    "expected": estimate(int(r0[i]), int(n0[i])),
                    "p_value": float(p[j]),
                    "q_value": float(q[j]),
                }
            )
        for (ward, specimen, organism), shifts in hits.items():
            firings.append(_firing(ds, day, ward, specimen, organism, shifts, m))
    return firings


def _firing(ds, day, ward, specimen, organism, shifts, m) -> Firing:
    """One firing per ward × specimen × organism, listing every antibiotic that shifted."""
    names = ds.antibiotics.set_index("antibiotic_code").antibiotic
    shifts = sorted(shifts, key=lambda s: s["p_value"])
    for s in shifts:
        s["antibiotic"] = names[s["antibiotic_code"]]
        s["increase_pp"] = round(s["observed"]["pct"] - s["expected"]["pct"], 1)
    lead = shifts[0]
    rec, base = lead["observed"], lead["expected"]
    more = f" (+{len(shifts) - 1} more)" if len(shifts) > 1 else ""
    rec_start = day - timedelta(days=RECENT_WINDOW_DAYS - 1)
    base_end = rec_start - timedelta(days=1)
    return Firing(
        type="rate_shift",
        ward=ward,
        subject=f"{specimen}|{organism}",
        day=day,
        title=(
            f"{organism} ({specimen}) {lead['antibiotic']} resistance {rec['pct']:.0f} % "
            f"({rec['r']}/{rec['n']}) in 4 weeks vs {base['pct']:.0f} % before{more}"
        ),
        evidence={
            "method": "One-sided Fisher exact test, last 4 weeks vs previous 12 months (first "
            f"isolates), Benjamini–Hochberg FDR across the {m} ward × organism × antibiotic "
            "cells tested that week",
            "observed": rec,
            "expected": base,
            "p_value": lead["p_value"],
            "q_value": lead["q_value"],
            "window": {"start": rec_start.isoformat(), "end": day.isoformat()},
            "baseline": {
                "start": (base_end - timedelta(days=ANNUAL_WINDOW_DAYS - 1)).isoformat(),
                "end": base_end.isoformat(),
            },
            "specimen": specimen,
            "organism": organism,
            "antibiotic_code": lead["antibiotic_code"],
            "antibiotic": lead["antibiotic"],
            "shifts": shifts,
        },
        isolate_ids=_resistant_cases(ds, rec_start, day, ward, specimen, organism, shifts),
    )


def _resistant_cases(ds, start, end, ward, specimen, organism, shifts) -> tuple[str, ...]:
    """First isolates in the recent window resistant to any of the shifted antibiotics."""
    iso = ds.isolates[
        ds.isolates.ward_code.eq(ward)
        & ds.isolates.specimen.eq(specimen)
        & ds.isolates.sample_date.between(pd.Timestamp(start), pd.Timestamp(end))
    ].drop_duplicates(STRATUM)
    iso = iso[iso.organism.eq(organism)]
    ast = ds.ast[ds.ast.isolate_id.isin(iso.isolate_id)]
    codes = {s["antibiotic_code"] for s in shifts}
    hit = ast.isolate_id[ast.resistant & ast.antibiotic_code.isin(codes)]
    return tuple(iso.isolate_id[iso.isolate_id.isin(hit)])
