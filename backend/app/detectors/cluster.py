"""Outbreak / cluster detector (ANOM-01).

For every ward × phenotype (ESBL, MRSA, VRE, CPE), each day:
  observed  = new cases in the last CLUSTER_WINDOW_DAYS,
  expected  = the ward's own case rate over the CLUSTER_BASELINE_DAYS before that window,
  p         = P(X ≥ observed) under Poisson(expected).
A "new case" is a patient's positive that isn't a repeat of the same phenotype on the same ward
within CLUSTER_CASE_DEDUP_DAYS (re-sampling a known carrier is not a new case).

The test runs only on days a new case arrives (the alert fires with the case that tips it) and
needs at least CLUSTER_MIN_CASES. P-values are FDR-corrected across all ward × phenotype pairs
of the same day (STAT-08). Hospital-acquired cases are counted in the evidence, since
transmission on the ward is what infection control needs to act on.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import poisson

from app.config import (
    CLUSTER_BASELINE_DAYS,
    CLUSTER_BASELINE_PSEUDOCOUNT,
    CLUSTER_CASE_DEDUP_DAYS,
    CLUSTER_MIN_CASES,
    CLUSTER_WINDOW_DAYS,
    MIN_BASELINE_DAYS,
    PHENOTYPES,
)
from app.data.dataset import Dataset
from app.detectors.common import (
    Firing,
    bh_qvalues,
    cumulative,
    daily_counts,
    days_since_previous,
    n_days,
    phenotype_cases,
    significant,
    to_date,
    window_sums,
)


def new_cases(ds: Dataset) -> pd.DataFrame:
    """Phenotype positives that count as new cases on their ward (repeats removed)."""
    cases = phenotype_cases(ds)
    # One row per patient × phenotype × ward × day (two isolates the same day are one case).
    cases = cases.drop_duplicates(["patient_id", "phenotype", "ward_code", "sample_date"])
    cases = days_since_previous(cases, ["patient_id", "phenotype", "ward_code"], ds.start)
    return cases[cases.first_ever | (cases.gap_days > CLUSTER_CASE_DEDUP_DAYS)]


def detect_clusters(ds: Dataset, horizon: date) -> list[Firing]:
    cases = new_cases(ds)
    combos = [(w, p) for w in ds.wards.ward_code for p in PHENOTYPES]
    counts = np.stack(
        [
            daily_counts(
                ds, cases.sample_date[cases.ward_code.eq(w) & cases.phenotype.eq(p)], horizon
            )
            for w, p in combos
        ]
    )
    cum = cumulative(counts)
    t = np.arange(n_days(ds, horizon))
    W, B = CLUSTER_WINDOW_DAYS, CLUSTER_BASELINE_DAYS

    observed = window_sums(cum, t - W + 1, t)
    base_end = t - W
    base_start = np.clip(base_end - B + 1, 0, None)
    base_days = base_end - base_start + 1
    baseline = window_sums(cum, base_start, base_end)
    with np.errstate(divide="ignore", invalid="ignore"):
        expected = (baseline + CLUSTER_BASELINE_PSEUDOCOUNT) / base_days * W

    tested = (base_days >= MIN_BASELINE_DAYS) & (counts > 0) & (observed >= CLUSTER_MIN_CASES)
    p = np.ones_like(expected, dtype=float)
    p[tested] = poisson.sf(observed[tested] - 1, expected[tested])

    firings = []
    for day in np.flatnonzero(tested.any(axis=0)):
        q = bh_qvalues(p[:, day], m=len(combos))
        for i in np.flatnonzero(significant(q) & tested[:, day]):
            ward, phenotype = combos[i]
            firings.append(
                _firing(
                    ds,
                    cases,
                    ward,
                    phenotype,
                    to_date(ds, day),
                    observed=int(observed[i, day]),
                    expected=float(expected[i, day]),
                    baseline_cases=int(baseline[i, day]),
                    baseline_days=int(base_days[day]),
                    p=float(p[i, day]),
                    q=float(q[i]),
                )
            )
    return firings


def _firing(
    ds, cases, ward, phenotype, day, *, observed, expected, baseline_cases, baseline_days, p, q
) -> Firing:
    win_start = day - timedelta(days=CLUSTER_WINDOW_DAYS - 1)
    in_window = cases[
        cases.ward_code.eq(ward)
        & cases.phenotype.eq(phenotype)
        & cases.sample_date.between(pd.Timestamp(win_start), pd.Timestamp(day))
    ]
    hospital_acquired = int(in_window.hospital_acquired.sum())
    base_end = win_start - timedelta(days=1)
    return Firing(
        type="cluster",
        ward=ward,
        subject=phenotype,
        day=day,
        title=(
            f"{phenotype} cluster: {observed} new cases in {CLUSTER_WINDOW_DAYS} days "
            f"(expected {expected:.1f})"
        ),
        evidence={
            "method": "Poisson test of new cases in the window vs the ward's own baseline rate, "
            "Benjamini–Hochberg FDR across all ward × phenotype pairs that day",
            "observed": observed,
            "expected": round(expected, 2),
            "ratio": round(observed / expected, 1) if expected else None,
            "p_value": p,
            "q_value": q,
            "window": {"start": win_start.isoformat(), "end": day.isoformat()},
            "baseline": {
                "start": (base_end - timedelta(days=baseline_days - 1)).isoformat(),
                "end": base_end.isoformat(),
                "cases": baseline_cases,
                "days": baseline_days,
            },
            "hospital_acquired": hospital_acquired,
            "phenotype": phenotype,
            "organisms": in_window.organism.value_counts().to_dict(),
        },
        isolate_ids=tuple(in_window.isolate_id),
    )
