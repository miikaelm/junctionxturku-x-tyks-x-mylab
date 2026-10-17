"""Therapy helper (V2, VIEW-04): which antibiotic is likely to work for this infection here.

A weighted-incidence syndromic antibiogram (WISCA). Before the culture result, the organism is
unknown, so an agent's *coverage* is the chance it works against whatever organism turns out
to cause the infection:

    coverage(agent) = Σ_organism  share(organism) × susceptible(organism, agent)

with shares and susceptibility from first isolates of the infection's specimen in the last 12
months, in the ward's population matching the patient (sex, age band, hospital-acquired). The
population falls back ward → institution → all locations (STAT-04) until it has
THERAPY_MIN_ISOLATES isolates. The 95 % interval comes from Monte Carlo draws: shares from a
Dirichlet and each susceptibility from a Beta posterior (Jeffreys priors), as in published WISCA
methods.

Intrinsic resistance counts as not covered. An agent never tested on an organism counts as not
covered too, and its share is reported as "not tested", so a gap in the data never looks like
good coverage. S. aureus β-lactam susceptibility is inferred from the cefoxitin screen (EUCAST
expert rule). Decision support, not a prescription.
"""

from dataclasses import replace
from datetime import date

import numpy as np

from app.config import (
    THERAPY_DRAWS,
    THERAPY_EXCLUDE,
    THERAPY_GOOD_COVERAGE,
    THERAPY_INFECTIONS,
    THERAPY_INFERRED,
    THERAPY_MAX_UNKNOWN_SHARE,
    THERAPY_MIN_ISOLATES,
    THERAPY_RESERVE,
    THERAPY_WARN_COVERAGE,
)
from app.data import windows
from app.data.dataset import Dataset
from app.data.first_isolate import first_isolates
from app.data.intrinsic import is_intrinsic
from app.data.scope import Scope
from app.stats.antibiogram import reported_antibiotics

PRIOR = 0.5  # Jeffreys


def coverage_tier(pct: float) -> str:
    if pct >= THERAPY_GOOD_COVERAGE:
        return "good"
    if pct >= THERAPY_WARN_COVERAGE:
        return "warn"
    return "bad"


def therapy(ds: Dataset, scope: Scope, infection: str, as_of: date) -> dict:
    if infection not in THERAPY_INFECTIONS:
        raise ValueError(f"unknown infection type: {infection}")
    spec = THERAPY_INFECTIONS[infection]
    scope = replace(scope, specimen=spec["specimen"])
    window = windows.annual(as_of)

    chain = scope.chain(ds.wards)
    tried = []
    for level in chain:
        iso = level.apply(ds.isolates)
        iso = first_isolates(iso[window.mask(iso.sample_date)])
        tried.append({"location": level.location, "label": level.label(ds.wards), "n": len(iso)})
        if len(iso) >= THERAPY_MIN_ISOLATES:
            break
    used = level
    sufficient = len(iso) >= THERAPY_MIN_ISOLATES

    org_n = iso.organism.value_counts()
    organisms = list(org_n.index)
    n_total = int(org_n.sum())
    ast = ds.ast[ds.ast.isolate_id.isin(iso.isolate_id)]
    tab = ast.groupby(["organism", "antibiotic_code"]).resistant.agg(n="size", r="sum")

    def counts(org: str, code: str) -> tuple[int, int] | None:
        if (org, code) in tab.index:
            row = tab.loc[(org, code)]
            return int(row.n), int(row.r)
        return None

    abx = reported_antibiotics(ds, spec["specimen"])
    abx = abx[~abx.antibiotic_code.isin(THERAPY_EXCLUDE)]

    rng = np.random.default_rng(20261017)
    shares = org_n.to_numpy(dtype=float) / n_total if n_total else np.array([])
    weights = rng.dirichlet(org_n.to_numpy(dtype=float) + PRIOR, THERAPY_DRAWS) if n_total else None

    ranked, unranked = [], []
    for a in abx.to_dict("records"):
        code = a["antibiotic_code"]
        parts = []
        susc_draws = np.zeros((THERAPY_DRAWS, len(organisms)))
        point = 0.0
        unknown = 0.0
        for j, org in enumerate(organisms):
            share = float(shares[j])
            entry = {"organism": org, "share": round(share, 3), "n_isolates": int(org_n[org])}
            c = counts(org, code)
            source = THERAPY_INFERRED.get((org, code))
            if c is None and source:
                c = counts(org, source)  # inferred from the screen (EUCAST expert rule)
            if is_intrinsic(org, code):
                entry.update(status="intrinsic", susceptible_pct=0.0)
            elif c is None:
                entry.update(status="not_tested", susceptible_pct=None)
                unknown += share
            else:
                n, r = c
                entry.update(
                    status="inferred" if source and counts(org, code) is None else "tested",
                    n=n,
                    r=r,
                    susceptible_pct=round(100 * (n - r) / n, 1),
                )
                if entry["status"] == "inferred":
                    entry["inferred_from"] = source
                susc_draws[:, j] = rng.beta(n - r + PRIOR, r + PRIOR, THERAPY_DRAWS)
                point += share * (n - r) / n
            parts.append(entry)
        if weights is not None:
            cov = (weights * susc_draws).sum(axis=1)
            lo, hi = np.percentile(cov, [2.5, 97.5])
        else:
            lo = hi = 0.0
        pct = round(100 * point, 1)
        item = {
            "code": code,
            "name": a["antibiotic"],
            "class": a["class"],
            "coverage_pct": pct,
            "reserve": code in THERAPY_RESERVE,
            "ci_low": round(100 * float(lo), 1),
            "ci_high": round(100 * float(hi), 1),
            "not_tested_share": round(unknown, 3),
            "not_tested": [p["organism"] for p in parts if p["status"] == "not_tested"],
            "tier": coverage_tier(pct),
            "organisms": parts,
        }
        (unranked if unknown > THERAPY_MAX_UNKNOWN_SHARE else ranked).append(item)
    ranked.sort(key=lambda x: (-x["coverage_pct"], x["code"]))
    unranked.sort(key=lambda x: x["code"])

    return {
        "as_of": as_of.isoformat(),
        "infection": infection,
        "infection_label": spec["label"],
        "specimen": spec["specimen"],
        "window": window.to_dict(),
        "scope": scope.to_dict(ds.wards),
        "used": {**used.to_dict(ds.wards), "fell_back": used.location != scope.location},
        "tried": tried,
        "isolates": n_total,
        "sufficient": sufficient,
        "organisms": [
            {"organism": o, "n": int(org_n[o]), "share": round(float(s), 3)}
            for o, s in zip(organisms, shares)
        ],
        "ranked": ranked,
        "unranked": unranked,
        "thresholds": {"good": THERAPY_GOOD_COVERAGE, "warn": THERAPY_WARN_COVERAGE},
        "method": "Weighted-incidence syndromic antibiogram: coverage = Σ organism share × "
        "susceptibility, first isolates of the last 12 months; 95 % interval from "
        f"{THERAPY_DRAWS} Dirichlet × Beta draws. Intrinsic resistance and untested pairs count "
        "as not covered. Decision support, not a prescription.",
    }
