"""Spread / footprint (V10, PAT-03): where a phenotype appears across wards over time.

For one phenotype (optionally one organism or one resistance profile) in a period up to as_of:
  - every new case (ward, day, patient, core resistance profile), so the same profile on several
    wards stands out (ANOM-09 alerts are listed alongside);
  - the profiles, with the wards each was seen on;
  - each case patient's samples in the period on any ward, to draw their path between wards.

Paths are inferred from sample dates: there are no admission or transfer records, and the
synthetic data does not appear to model transmission. So this shows co-occurrence and where
patients were seen, never who infected whom.
"""

from datetime import date, timedelta

import pandas as pd

from app.config import ALERT_TYPES
from app.data.dataset import Dataset
from app.detectors.multi_ward import profiled_cases

MAX_PROFILES = 8  # distinct colours; rarer profiles share "other"


def spread(
    ds: Dataset,
    as_of: date,
    phenotype: str,
    days: int,
    episodes: list,
    organism: str | None = None,
    profile: str | None = None,
) -> dict:
    start = as_of - timedelta(days=days - 1)
    cases = profiled_cases(ds)
    cases = cases[
        cases.phenotype.eq(phenotype)
        & cases.sample_date.between(pd.Timestamp(start), pd.Timestamp(as_of))
    ]
    if organism:
        cases = cases[cases.organism.eq(organism)]
    if profile:
        cases = cases[cases.profile.eq(profile)]
    cases = cases.assign(strain=cases.organism + "|" + cases.profile)

    groups = (
        cases.groupby("strain")
        .agg(count=("isolate_id", "size"), wards=("ward_code", lambda s: sorted(set(s))))
        .reset_index()
        .sort_values(["count", "strain"], ascending=[False, True])
    )
    profiles = []
    for i, g in enumerate(groups.itertuples(index=False)):
        org, key = g.strain.split("|")
        profiles.append(
            {
                "id": g.strain,
                "organism": org,
                "profile": key,
                "label": "no acquired R" if key == "-" else f"R: {key.replace(',', ', ')}",
                "count": int(g.count),
                "wards": g.wards,
                "colour": i if i < MAX_PROFILES else None,
            }
        )

    # Paths: every sample of the case patients in the period, on any ward.
    pids = set(cases.patient_id)
    cul = ds.cultures[
        ds.cultures.patient_id.isin(pids)
        & ds.cultures.sample_date.between(pd.Timestamp(start), pd.Timestamp(as_of))
    ].drop_duplicates(["patient_id", "sample_date", "ward_code"])
    case_days = set(zip(cases.patient_id, cases.sample_date, cases.ward_code))
    paths = []
    for pid, g in cul.groupby("patient_id", sort=False):
        if g.ward_code.nunique() < 2:
            continue
        paths.append(
            {
                "patient_id": pid,
                "samples": [
                    {
                        "date": r.sample_date.date().isoformat(),
                        "ward": r.ward_code,
                        "case": (pid, r.sample_date, r.ward_code) in case_days,
                    }
                    for r in g.itertuples(index=False)
                ],
            }
        )

    alerts = [
        {
            "id": e.id,
            "type": e.type,
            "type_label": ALERT_TYPES[e.type]["label"],
            "wards": e.wards(as_of),
            "first_seen": e.first.isoformat(),
            "title": e.firings[0].title,
        }
        for e in episodes
        if e.type in ("cluster", "multi_ward")
        and start <= e.first <= as_of
        and e.subject.split("|")[0] == phenotype
    ]
    return {
        "as_of": as_of.isoformat(),
        "start": start.isoformat(),
        "phenotype": phenotype,
        "organism": organism,
        "profile": profile,
        "wards": list(ds.wards.ward_code),
        "cases": [
            {
                "isolate_id": c.isolate_id,
                "date": c.sample_date.date().isoformat(),
                "ward": c.ward_code,
                "patient_id": c.patient_id,
                "organism": c.organism,
                "specimen": c.specimen,
                "profile_id": c.strain,
                "hospital_acquired": bool(c.hospital_acquired),
            }
            for c in cases.itertuples(index=False)
        ],
        "profiles": profiles,
        "shared": [p for p in profiles if len(p["wards"]) >= 2],
        "paths": paths,
        "alerts": alerts,
    }
