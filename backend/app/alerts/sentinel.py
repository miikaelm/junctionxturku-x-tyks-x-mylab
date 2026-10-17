"""Sentinel events (NOTIF-01): rare, critical findings alert immediately, without statistics.

One case = one alert: each matching isolate fires on its sample day. Repeat positives of the
same patient and marker on the same ward join that patient's alert (alert episodes, see
alerts/engine.py). Each alert also says how long it has been since the marker was last seen on
the ward, the same information the novelty detector (ANOM-08) gives for other phenotypes.
"""

from datetime import date

import pandas as pd

from app.config import SENTINEL_RULES
from app.data.dataset import Dataset
from app.detectors.common import Firing, days_since_previous


def sentinel_matches(ds: Dataset, horizon: date) -> pd.DataFrame:
    """One row per isolate matching any rule, with `reasons` (rule keys, in rule order)."""
    iso = ds.isolates[ds.isolates.sample_date <= pd.Timestamp(horizon)]
    resistant = ds.ast[ds.ast.resistant]
    reasons: dict[str, list[str]] = {}
    for rule in SENTINEL_RULES:
        if "phenotype" in rule:
            ids = iso.isolate_id[iso[rule["phenotype"].lower()].eq(1)]
        else:
            hit = resistant[resistant.antibiotic_code.eq(rule["antibiotic"])]
            if "organisms" in rule:
                hit = hit[hit.organism.isin(rule["organisms"])]
            ids = hit.isolate_id
        for isolate_id in ids:
            reasons.setdefault(isolate_id, []).append(rule["key"])
    matches = iso[iso.isolate_id.isin(reasons)].copy()
    matches["reasons"] = matches.isolate_id.map(reasons)
    matches["marker"] = matches.reasons.str[0]
    return matches


def detect_sentinels(ds: Dataset, horizon: date, since: date | None = None) -> list[Firing]:
    matches = sentinel_matches(ds, horizon)
    # "First in N days" per ward and marker, over all of that marker's cases.
    per_day = matches.drop_duplicates(["ward_code", "marker", "sample_date"])
    novelty = days_since_previous(per_day, ["ward_code", "marker"], ds.start)
    novelty = novelty.set_index(["ward_code", "marker", "sample_date"])[["gap_days", "first_ever"]]

    labels = {r["key"]: r["label"] for r in SENTINEL_RULES}
    firings = []
    if since:  # the "first in N days" note above still looks at all earlier cases
        matches = matches[matches.sample_date >= pd.Timestamp(since)]
    for m in matches.itertuples(index=False):
        gap, first_ever = novelty.loc[(m.ward_code, m.marker, m.sample_date)]
        seen = (
            f"first on this ward since records began ({gap} days)"
            if first_ever
            else (f"previous on this ward {gap} days earlier" if gap > 0 else "")
        )
        firings.append(
            Firing(
                type="sentinel",
                ward=m.ward_code,
                subject=f"{m.marker}|{m.patient_id}",
                day=m.sample_date.date(),
                title=f"{labels[m.marker]}: {m.organism} ({m.specimen})",
                evidence={
                    "method": "Rule: any single case triggers an alert",
                    "reasons": [labels[r] for r in m.reasons],
                    "marker": m.marker,
                    "patient_id": m.patient_id,
                    "organism": m.organism,
                    "specimen": m.specimen,
                    "gap_days": int(gap),
                    "first_ever": bool(first_ever),
                    "seen_note": seen,
                },
                isolate_ids=(m.isolate_id,),
            )
        )
    return firings
