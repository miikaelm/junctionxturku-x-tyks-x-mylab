"""Cumulative antibiogram for a scope: organism × antibiotic resistance, last 4 weeks next to
last 12 months (VIEW-01), with the place fallback (STAT-04) and time fallback (STAT-05).

Each cell carries the estimate at every level of the location hierarchy, so the client can
show the most specific reliable number and explain what it fell back from.
"""

from datetime import date

import pandas as pd

from app.data import windows
from app.data.dataset import Dataset
from app.data.first_isolate import first_isolates
from app.data.intrinsic import is_intrinsic
from app.data.scope import Scope
from app.data.windows import Window
from app.stats.proportions import estimate

Counts = dict[tuple[str, str], tuple[int, int]]


def resistance_counts(ds: Dataset, scope: Scope, window: Window) -> tuple[Counts, pd.Series]:
    """(n, r) per (organism, antibiotic_code) and first-isolate count per organism."""
    iso = scope.apply(ds.isolates)
    iso = first_isolates(iso[window.mask(iso.sample_date)])
    ast = ds.ast[ds.ast.isolate_id.isin(iso.isolate_id)]
    grouped = ast.groupby(["organism", "antibiotic_code"]).resistant.agg(n="size", r="sum")
    counts = {key: (int(n), int(r)) for key, n, r in zip(grouped.index, grouped.n, grouped.r)}
    return counts, iso.organism.value_counts()


def reported_antibiotics(ds: Dataset, specimen: str) -> pd.DataFrame:
    """Agents reportable for this specimen (DATA-06: urine-only agents only for urine)."""
    abx = ds.antibiotics
    return abx[abx.reported_for.eq("all") | abx.reported_for.eq(specimen)]


def build_antibiogram(ds: Dataset, scope: Scope, as_of: date) -> dict:
    if not scope.specimen:
        raise ValueError("an antibiogram needs a specimen type")
    wins = [windows.recent(as_of), windows.annual(as_of)]
    chain = scope.chain(ds.wards)
    results = {w.key: [resistance_counts(ds, s, w) for s in chain] for w in wins}

    # Stable rows: every organism ever seen in this specimen up to as_of, most common here first.
    seen = ds.isolates[
        ds.isolates.specimen.eq(scope.specimen) & (ds.isolates.sample_date <= pd.Timestamp(as_of))
    ]
    own_annual = results["annual"][0][1]
    all_annual = results["annual"][-1][1]
    organisms = sorted(
        seen.organism.unique(),
        key=lambda o: (-own_annual.get(o, 0), -all_annual.get(o, 0), o),
    )

    abx = reported_antibiotics(ds, scope.specimen)
    abx = abx[
        [any((o, code) in ds.tested_pairs for o in organisms) for code in abx.antibiotic_code]
    ]

    own_total = int(own_annual.sum())
    rows = []
    for org in organisms:
        cells: dict[str, dict | None] = {}
        for code in abx.antibiotic_code:
            if (org, code) not in ds.tested_pairs:
                cells[code] = None  # never tested / not reported for this organism
                continue
            cell: dict = {"intrinsic": is_intrinsic(org, code)}
            for w in wins:
                levels = [_estimate_for(counts, org, code) for counts, _ in results[w.key]]
                shown = next((i for i, e in enumerate(levels) if e["sufficient"]), None)
                cell[w.key] = {"levels": levels, "shown": shown}
            if cell["recent"]["levels"][0]["sufficient"]:
                cell["headline"] = "recent"
            elif cell["annual"]["shown"] is not None:
                cell["headline"] = "annual"
            else:
                cell["headline"] = None
            cells[code] = cell
        rows.append(
            {
                "organism": org,
                "isolates": {
                    w.key: [int(org_counts.get(org, 0)) for _, org_counts in results[w.key]]
                    for w in wins
                },
                "share_annual": round(own_annual.get(org, 0) / own_total, 3) if own_total else 0,
                "cells": cells,
            }
        )

    return {
        "as_of": as_of.isoformat(),
        "scope": scope.to_dict(ds.wards),
        "levels": [
            {"level": s.level(ds.wards), "location": s.location, "label": s.label(ds.wards)}
            for s in chain
        ],
        "windows": [w.to_dict() for w in wins],
        "antibiotics": [
            {
                "code": a.antibiotic_code,
                "name": a.antibiotic,
                "name_fi": a.antibiotic_fi,
                "class": a["class"],
                "reported_for": a.reported_for,
            }
            for _, a in abx.iterrows()
        ],
        "organisms": rows,
    }


def _estimate_for(counts: Counts, organism: str, code: str) -> dict:
    n, r = counts.get((organism, code), (0, 0))
    return estimate(r, n)
