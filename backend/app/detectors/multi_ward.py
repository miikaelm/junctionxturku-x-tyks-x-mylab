"""Multi-ward signal (ANOM-09): the same resistant strain type on several wards at once.

Cases are the cluster detector's new phenotype cases (ESBL / MRSA / VRE / CPE, repeats removed),
grouped by phenotype × organism × core resistance profile (stats/profiles.py; urine-only agents
left out so urine and blood isolates compare). For every profile, each day a new case of it
arrives:
  observed = its new cases in the last MULTIWARD_WINDOW_DAYS on all wards,
  expected = its hospital-wide rate over the year before the window,
and it fires when
  - the cases are on at least 2 wards, and observed is significantly above expected (Poisson,
    Benjamini–Hochberg FDR across the profiles seen in that period, STAT-08), and
  - the excess is not confined to one ward: the cases outside the busiest ward
    (≥ MULTIWARD_MIN_OUTSIDE_CASES) are also above *their* expected count (p < OUTSIDE_ALPHA).
Without the second condition, every single-ward cluster of a common profile would also count
as "multi-ward" whenever an unrelated case of it turned up elsewhere.

The alert names the wards ("seen on URO and GER") and does not claim a direction.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import poisson

from app.config import (
    CLUSTER_BASELINE_DAYS,
    CLUSTER_BASELINE_PSEUDOCOUNT,
    MIN_BASELINE_DAYS,
    MULTIWARD_MIN_CASES,
    MULTIWARD_MIN_OUTSIDE_CASES,
    MULTIWARD_OUTSIDE_ALPHA,
    MULTIWARD_WINDOW_DAYS,
)
from app.data.dataset import Dataset
from app.detectors.cluster import new_cases
from app.detectors.common import (
    Firing,
    bh_qvalues,
    cumulative,
    daily_counts,
    first_index,
    n_days,
    significant,
    to_date,
    window_sums,
)
from app.stats.profiles import profile_keys

MULTI_WARD = "multi"  # the alert's ward: it belongs to several (listed in evidence["wards"])


_profiled: dict[int, tuple[Dataset, pd.DataFrame]] = {}


def profiled_cases(ds: Dataset) -> pd.DataFrame:
    """New phenotype cases with their core profile and strain key (phenotype|organism|profile).
    Cached per dataset: the spread view and alert details ask for it on every request."""
    hit = _profiled.get(id(ds))
    if hit is not None and hit[0] is ds:
        return hit[1]
    cases = _profile(ds)
    if len(_profiled) >= 4:
        _profiled.clear()
    _profiled[id(ds)] = (ds, cases)
    return cases


def _profile(ds: Dataset) -> pd.DataFrame:
    cases = new_cases(ds)
    keys = profile_keys(ds, cases.isolate_id, core=True)
    cases = cases.assign(profile=cases.isolate_id.map(keys).fillna("-"))
    cases["strain"] = cases.phenotype + "|" + cases.organism + "|" + cases.profile
    return cases


def detect_multi_ward(ds: Dataset, horizon: date, since: date | None = None) -> list[Firing]:
    cases = profiled_cases(ds)
    cases = cases[cases.sample_date <= pd.Timestamp(horizon)]
    strains = sorted(cases.strain.unique())
    wards = list(ds.wards.ward_code)
    if not strains:
        return []
    T = n_days(ds, horizon)
    counts = np.zeros((len(strains), len(wards), T), dtype=np.int64)
    for si, s in enumerate(strains):
        for wi, w in enumerate(wards):
            sel = cases.strain.eq(s) & cases.ward_code.eq(w)
            if sel.any():
                counts[si, wi] = daily_counts(ds, cases.sample_date[sel], horizon)
    cum = cumulative(counts)
    t = np.arange(T)
    W, B = MULTIWARD_WINDOW_DAYS, CLUSTER_BASELINE_DAYS
    obs_w = window_sums(cum, t - W + 1, t)  # strain × ward × day
    base_end = t - W
    base_start = np.clip(base_end - B + 1, 0, None)
    base_days = base_end - base_start + 1
    base_w = window_sums(cum, base_start, base_end)

    obs = obs_w.sum(axis=1)
    base = base_w.sum(axis=1)
    main = obs_w.argmax(axis=1)  # busiest ward in the window
    obs_main = np.take_along_axis(obs_w, main[:, None, :], axis=1)[:, 0, :]
    base_main = np.take_along_axis(base_w, main[:, None, :], axis=1)[:, 0, :]
    out_obs = obs - obs_main
    with np.errstate(divide="ignore", invalid="ignore"):
        expected = (base + CLUSTER_BASELINE_PSEUDOCOUNT) / base_days * W
        out_expected = (base - base_main + CLUSTER_BASELINE_PSEUDOCOUNT) / base_days * W
    n_wards = (obs_w > 0).sum(axis=1)
    arrived = counts.sum(axis=1) > 0
    active = (obs + base) > 0  # strains seen in the baseline or window: the FDR family

    tested = (
        (base_days >= MIN_BASELINE_DAYS)
        & arrived
        & (obs >= MULTIWARD_MIN_CASES)
        & (n_wards >= 2)
        & (out_obs >= MULTIWARD_MIN_OUTSIDE_CASES)
    )
    tested[:, : first_index(ds, since)] = False
    p = np.ones(obs.shape, dtype=float)
    p_out = np.ones(obs.shape, dtype=float)
    p[tested] = poisson.sf(obs[tested] - 1, expected[tested])
    p_out[tested] = poisson.sf(out_obs[tested] - 1, out_expected[tested])

    firings = []
    for day in np.flatnonzero(tested.any(axis=0)):
        q = bh_qvalues(p[:, day], m=int(active[:, day].sum()))
        hit = significant(q) & tested[:, day] & (p_out[:, day] < MULTIWARD_OUTSIDE_ALPHA)
        for si in np.flatnonzero(hit):
            firings.append(
                _firing(
                    cases,
                    strains[si],
                    to_date(ds, day),
                    {
                        w: int(obs_w[si, wi, day])
                        for wi, w in enumerate(wards)
                        if obs_w[si, wi, day]
                    },
                    observed=int(obs[si, day]),
                    expected=float(expected[si, day]),
                    outside=(int(out_obs[si, day]), float(out_expected[si, day])),
                    p=float(p[si, day]),
                    p_out=float(p_out[si, day]),
                    q=float(q[si]),
                    base=(int(base[si, day]), int(base_days[day])),
                )
            )
    return firings


def _firing(cases, strain, day, by_ward, *, observed, expected, outside, p, p_out, q, base):
    phenotype, organism, profile = strain.split("|")
    start = day - timedelta(days=MULTIWARD_WINDOW_DAYS - 1)
    in_window = cases[
        cases.strain.eq(strain) & cases.sample_date.between(pd.Timestamp(start), pd.Timestamp(day))
    ]
    wards = sorted(by_ward, key=lambda w: (-by_ward[w], w))
    label = "no acquired R" if profile == "-" else f"R: {profile.replace(',', ', ')}"
    shared = in_window.groupby("patient_id").ward_code.nunique()
    return Firing(
        type="multi_ward",
        ward=MULTI_WARD,
        subject=strain,
        day=day,
        title=f"{phenotype} {organism} ({label}) on {len(wards)} wards: {', '.join(wards)}",
        evidence={
            "method": "Poisson test of one resistance profile's new cases in the window vs its "
            "hospital-wide baseline (Benjamini–Hochberg FDR across profiles), and of the cases "
            "outside the busiest ward vs their own baseline",
            "phenotype": phenotype,
            "organism": organism,
            "profile": profile,
            "profile_label": label,
            "wards": wards,
            "by_ward": by_ward,
            "observed": observed,
            "expected": round(expected, 2),
            "outside_main": {
                "ward": wards[0],
                "observed": outside[0],
                "expected": round(outside[1], 2),
            },
            "p_value": p,
            "p_outside": p_out,
            "q_value": q,
            "window": {"start": start.isoformat(), "end": day.isoformat()},
            "baseline": {"cases": base[0], "days": base[1]},
            "patients_on_several_wards": int((shared > 1).sum()),
        },
        isolate_ids=tuple(in_window.isolate_id),
    )
