"""Automatic subgroup-difference discovery (STAT-09).

For a scope and window, every organism × antibiotic is compared across the levels of each
patient or setting dimension (config.SUBGROUP_DIMENSIONS): "does resistance differ by sex, age
band, onset, home area, ward …?". First isolates are taken once for the whole scope and window
(DATA-02), then split by the dimension of their own sample. Levels with fewer than
SUBGROUP_MIN_N isolates are left out; a comparison needs two levels that remain.

Test: Fisher exact (two levels) or chi-square (more), only where the spread between levels is at
least SUBGROUP_MIN_DIFF_PP. Benjamini–Hochberg runs over every comparison that had enough data
(STAT-08), so a ward with hundreds of comparisons doesn't produce chance "findings".
"""

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, fisher_exact

from app.config import SUBGROUP_DIMENSIONS, SUBGROUP_MIN_DIFF_PP, SUBGROUP_MIN_N
from app.data.dataset import Dataset
from app.data.first_isolate import first_isolates
from app.data.intrinsic import is_intrinsic
from app.data.scope import Scope
from app.data.windows import Window
from app.detectors.common import bh_qvalues, significant
from app.stats.proportions import estimate

VALUE_LABELS = {
    "sex": {"F": "Women", "M": "Men"},
    "hospital_acquired": {True: "Hospital-acquired", False: "Not hospital-acquired"},
    "ward_type": {"in": "Inpatients", "out": "Outpatients"},
}


def value_label(dimension: str, value) -> str:
    if dimension == "age_band":
        return f"{value} years"
    return VALUE_LABELS.get(dimension, {}).get(value, str(value))


def dimensions_for(scope: Scope, wards: pd.DataFrame) -> list[str]:
    """Dimensions that can vary within the scope (a filtered dimension is fixed)."""
    fixed = {
        "sex": scope.sex,
        "age_band": scope.age_band,
        "hospital_acquired": scope.hospital_acquired,
        "ward_type": scope.ward_type,
        "home_area": scope.home_area,
        "ward_code": scope.location if scope.level(wards) == "ward" else None,
    }
    return [d for d in SUBGROUP_DIMENSIONS if fixed[d] is None]


def discover(ds: Dataset, scope: Scope, window: Window) -> dict:
    iso = scope.apply(ds.isolates)
    iso = first_isolates(iso[window.mask(iso.sample_date)])
    dims = dimensions_for(scope, ds.wards)
    ast = iso[["isolate_id", *dims]].merge(ds.ast, on="isolate_id")
    keep = [not is_intrinsic(o, a) for o, a in zip(ast.organism, ast.antibiotic_code)]
    ast = ast[np.array(keep, dtype=bool)]

    rows = []  # one per comparison with enough data
    for dim in dims:
        counts = ast.groupby(["organism", "antibiotic_code", dim]).resistant.agg(n="size", r="sum")
        for (organism, code), sub in counts.groupby(level=[0, 1]):
            sub = sub[sub.n >= SUBGROUP_MIN_N].droplevel([0, 1])
            if len(sub) < 2:
                continue
            pct = 100 * sub.r / sub.n
            rows.append(
                {
                    "dimension": dim,
                    "organism": organism,
                    "code": code,
                    "levels": sub,
                    "diff": float(pct.max() - pct.min()),
                }
            )

    tested = [r for r in rows if r["diff"] >= SUBGROUP_MIN_DIFF_PP and _varies(r["levels"])]
    for r in tested:
        r["p"] = _p_value(r["levels"])
    q = bh_qvalues(np.array([r["p"] for r in tested]), m=len(rows))
    names = ds.antibiotics.set_index("antibiotic_code").antibiotic
    found = []
    for r, qv in zip(tested, q):
        if not significant(np.array([qv]))[0]:
            continue
        found.append(_finding(r, float(qv), names[r["code"]]))
    found.sort(key=lambda f: (f["q_value"], -f["diff_pp"]))
    return {
        "scope": scope.to_dict(ds.wards),
        "window": window.to_dict(),
        "dimensions": [{"key": d, "label": SUBGROUP_DIMENSIONS[d]} for d in dims],
        "compared": len(rows),
        "findings": found,
    }


def _varies(levels: pd.DataFrame) -> bool:
    r, n = levels.r.sum(), levels.n.sum()
    return 0 < r < n


def _p_value(levels: pd.DataFrame) -> float:
    table = np.column_stack([levels.r, levels.n - levels.r])
    if len(levels) == 2:
        return float(fisher_exact(table)[1])
    return float(chi2_contingency(table)[1])


def _finding(r: dict, q: float, antibiotic: str) -> dict:
    dim = r["dimension"]
    levels = [
        {"value": _plain(v), "label": value_label(dim, v), **estimate(int(x.r), int(x.n))}
        for v, x in r["levels"].iterrows()
    ]
    hi = max(levels, key=lambda lv: lv["pct"])
    lo = min(levels, key=lambda lv: lv["pct"])
    return {
        "dimension": dim,
        "dimension_label": SUBGROUP_DIMENSIONS[dim],
        "organism": r["organism"],
        "antibiotic_code": r["code"],
        "antibiotic": antibiotic,
        "levels": levels,
        "high": hi["label"],
        "low": lo["label"],
        "diff_pp": round(r["diff"], 1),
        "p_value": r["p"],
        "q_value": q,
        "text": (
            f"{antibiotic.capitalize()} resistance in {r['organism']} differs by "
            f"{SUBGROUP_DIMENSIONS[dim].lower()}: {hi['label']} {hi['pct']:.0f} % vs "
            f"{lo['label']} {lo['pct']:.0f} %"
        ),
    }


def _plain(v):
    """JSON-friendly level value (numpy bools / strings → Python)."""
    return v.item() if hasattr(v, "item") else v
