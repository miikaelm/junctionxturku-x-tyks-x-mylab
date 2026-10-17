"""Ward × time overview (V5): one row per ward, one column per time bin ending on the as-of date.

Two kinds of metric:
- phenotype counts: new ESBL / MRSA / VRE / CPE cases per bin (repeat positives of the same
  patient removed, as in the cluster detector);
- a resistance rate: first isolates per ward and bin (DATA-02), shown as a percentage only with
  n ≥ 30 (STAT-01), otherwise as counts.
Cells can carry markers for alerts first raised in that ward and bin, so a change in colour can be
read next to what the detectors said about it.
"""

from datetime import date, timedelta

import pandas as pd

from app.data.dataset import Dataset
from app.data.first_isolate import FIRST_ISOLATE_KEY
from app.detectors.cluster import new_cases
from app.stats.proportions import estimate

TOTAL = "ALL"


def bins(ds: Dataset, as_of: date, n: int, days: int) -> list[dict]:
    """n consecutive bins of `days` days, the last ending on as_of; none before the data starts."""
    out = []
    for k in range(n - 1, -1, -1):
        end = as_of - timedelta(days=k * days)
        start = end - timedelta(days=days - 1)
        if end < ds.start.date():
            continue
        out.append({"start": start.isoformat(), "end": end.isoformat()})
    return out


def _bin_index(dates: pd.Series, as_of: date, days: int, n: int) -> pd.Series:
    """Column index of each date (0 = oldest bin), or -1 outside the bins."""
    back = (pd.Timestamp(as_of) - dates).dt.days // days
    return (n - 1 - back).where((back >= 0) & (back < n), -1).astype(int)


def phenotype_grid(ds: Dataset, as_of: date, phenotype: str, n: int, days: int) -> dict:
    cols = bins(ds, as_of, n, days)
    n = len(cols)
    cases = new_cases(ds)
    cases = cases[cases.phenotype.eq(phenotype) & (cases.sample_date <= pd.Timestamp(as_of))]
    idx = _bin_index(cases.sample_date, as_of, days, n)
    cases = cases.assign(col=idx)[idx >= 0]
    table = pd.crosstab(cases.ward_code, cases.col).reindex(
        index=list(ds.wards.ward_code), columns=range(n), fill_value=0
    )
    table.loc[TOTAL] = table.sum()
    rows = [
        {"ward": ward, "cells": [{"value": int(v)} for v in values]}
        for ward, values in zip(table.index, table.to_numpy())
    ]
    return {"kind": "count", "bins": cols, "rows": rows}


def rate_grid(
    ds: Dataset, as_of: date, specimen: str, organism: str, code: str, n: int, days: int
) -> dict:
    cols = bins(ds, as_of, n, days)
    n = len(cols)
    iso = ds.isolates[
        ds.isolates.specimen.eq(specimen)
        & ds.isolates.organism.eq(organism)
        & (ds.isolates.sample_date <= pd.Timestamp(as_of))
    ]
    idx = _bin_index(iso.sample_date, as_of, days, n)
    iso = iso.assign(col=idx)[idx >= 0]
    ast = ds.ast[ds.ast.antibiotic_code.eq(code)][["isolate_id", "resistant"]]

    def counts(first: pd.DataFrame, by: list[str]) -> pd.DataFrame:
        return first.merge(ast, on="isolate_id").groupby(by).resistant.agg(n="size", r="sum")

    per_ward = counts(
        iso.drop_duplicates(["ward_code", "col", *FIRST_ISOLATE_KEY]), ["ward_code", "col"]
    )
    total = counts(iso.drop_duplicates(["col", *FIRST_ISOLATE_KEY]), ["col"])
    rows = []
    for ward in [*ds.wards.ward_code, TOTAL]:
        cells = []
        for c in range(n):
            key = c if ward == TOTAL else (ward, c)
            table = total if ward == TOTAL else per_ward
            nn, r = (int(table.n[key]), int(table.r[key])) if key in table.index else (0, 0)
            cells.append(estimate(r, nn))
        rows.append({"ward": ward, "cells": cells})
    return {"kind": "rate", "bins": cols, "rows": rows}


def add_markers(grid: dict, events: list[dict]) -> dict:
    """Attach alerts (ward, first_seen, …) to the cell of their ward and bin, and to the total."""
    starts = [date.fromisoformat(b["start"]) for b in grid["bins"]]
    ends = [date.fromisoformat(b["end"]) for b in grid["bins"]]
    by_ward = {row["ward"]: row for row in grid["rows"]}
    for e in events:
        day = date.fromisoformat(e["first_seen"])
        col = next((i for i, (s, t) in enumerate(zip(starts, ends)) if s <= day <= t), None)
        if col is None:
            continue
        for ward in (e["ward"], TOTAL):
            if ward in by_ward:
                by_ward[ward]["cells"][col].setdefault("alerts", []).append(e)
    return grid
