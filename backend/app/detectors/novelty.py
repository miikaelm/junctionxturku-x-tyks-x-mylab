"""Novelty detector (ANOM-08): "not seen here for a long time, or ever".

Fires on the *first* case of a phenotype (NOVELTY_PHENOTYPES) or of a rare organism on a ward
when the previous one on that ward was at least NOVELTY_MIN_GAP_DAYS ago. "Never before" only
counts once the data has that much history, so the first months don't flood with alerts.
An organism is rare when it makes up less than NOVELTY_RARE_ORGANISM_MAX_SHARE of all isolates
so far. CPE and VRE are sentinel events instead; their alerts carry the same "first in N days"
note (see alerts/sentinel.py).
"""

from datetime import date

import numpy as np
import pandas as pd

from app.config import NOVELTY_MIN_GAP_DAYS, NOVELTY_PHENOTYPES, NOVELTY_RARE_ORGANISM_MAX_SHARE
from app.data.dataset import Dataset
from app.detectors.common import Firing, days_since_previous


def novelty_events(ds: Dataset, horizon: date) -> pd.DataFrame:
    iso = ds.isolates[ds.isolates.sample_date <= pd.Timestamp(horizon)]
    parts = [iso[iso[p.lower()].eq(1)].assign(item=p, kind="phenotype") for p in NOVELTY_PHENOTYPES]

    # Organism share among all isolates up to and including each isolate's day (causal).
    seen_total = np.arange(1, len(iso) + 1)
    seen_org = iso.groupby("organism").cumcount().to_numpy() + 1
    share = pd.Series(seen_org / seen_total, index=iso.index)
    # Use the share as of the end of the day, so isolates of the same day agree.
    share = share.groupby(iso.sample_date).transform("last")
    rare = iso[share.lt(NOVELTY_RARE_ORGANISM_MAX_SHARE).to_numpy()]
    parts.append(rare.assign(item=rare.organism, kind="organism"))

    events = pd.concat(parts).sort_values(["sample_date", "isolate_id"], kind="stable")
    events = events.drop_duplicates(["ward_code", "item", "sample_date"])
    return days_since_previous(events, ["ward_code", "item"], ds.start)


def detect_novelty(ds: Dataset, horizon: date, since: date | None = None) -> list[Firing]:
    events = novelty_events(ds, horizon)
    hits = events[events.gap_days >= NOVELTY_MIN_GAP_DAYS]
    if since:
        hits = hits[hits.sample_date >= pd.Timestamp(since)]
    firings = []
    for e in hits.itertuples(index=False):
        when = (
            f"first on this ward since records began ({e.gap_days} days)"
            if e.first_ever
            else f"first on this ward in {e.gap_days} days"
        )
        firings.append(
            Firing(
                type="novelty",
                ward=e.ward_code,
                subject=e.item,
                day=e.sample_date.date(),
                title=f"{e.item} ({e.organism}, {e.specimen}): {when}",
                evidence={
                    "method": f"Rule: no {e.item} on this ward for ≥ {NOVELTY_MIN_GAP_DAYS} days",
                    "kind": e.kind,
                    "gap_days": int(e.gap_days),
                    "first_ever": bool(e.first_ever),
                    "previous": None
                    if e.first_ever
                    else (e.sample_date - pd.Timedelta(days=e.gap_days)).date().isoformat(),
                    "min_gap_days": NOVELTY_MIN_GAP_DAYS,
                    "organism": e.organism,
                    "specimen": e.specimen,
                },
                isolate_ids=(e.isolate_id,),
            )
        )
    return firings
