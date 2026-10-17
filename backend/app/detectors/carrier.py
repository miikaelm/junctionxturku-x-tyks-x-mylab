"""Carrier re-appearance (PAT-02): a known carrier is sampled on a hospital ward.

A patient is a known carrier of a phenotype from the day after their first positive (carrier
registry, PAT-01). When such a patient gets any new sample on a hospital ward (config
CARRIER_ALERT_INSTITUTIONS), that ward is alerted on the sample day, before the culture result
is known, so contact precautions can start. No alert when the patient was already sampled on
the same ward within CARRIER_REVISIT_DAYS: the ward already knows.

Rule-based, like the sentinels: no statistics. Patient movement is inferred from sample dates
only; there are no admission or transfer records.
"""

from datetime import date

import pandas as pd

from app.config import CARRIER_ALERT_INSTITUTIONS, CARRIER_FLAG_DAYS, CARRIER_REVISIT_DAYS
from app.data.dataset import Dataset
from app.detectors.common import Firing
from app.patients.registry import phenotype_positives


def reappearances(ds: Dataset, horizon: date) -> pd.DataFrame:
    """One row per (patient, ward, day) on which a known carrier was sampled on a hospital ward
    they hadn't been sampled on recently, with the flags known the day before (`flags`)."""
    cul = ds.cultures[ds.cultures.sample_date <= pd.Timestamp(horizon)]
    visits = cul.drop_duplicates(["patient_id", "ward_code", "sample_date"])[
        ["patient_id", "ward_code", "institution", "sample_date", "specimen", "admission_date"]
    ].copy()
    prev_here = visits.groupby(["patient_id", "ward_code"]).sample_date.shift()
    visits["days_since_here"] = (visits.sample_date - prev_here).dt.days
    # The patient's previous sample on any ward (where they came from, as far as samples show).
    prev = cul.drop_duplicates(["patient_id", "sample_date", "ward_code"])
    by_patient = prev.groupby("patient_id")
    prev = prev.assign(
        prev_ward=by_patient.ward_code.shift(), prev_date=by_patient.sample_date.shift()
    )
    visits = visits.merge(
        prev[["patient_id", "ward_code", "sample_date", "prev_ward", "prev_date"]],
        on=["patient_id", "ward_code", "sample_date"],
        how="left",
    )
    new_here = visits.days_since_here.isna() | (visits.days_since_here > CARRIER_REVISIT_DAYS)
    visits = visits[new_here & visits.institution.isin(CARRIER_ALERT_INSTITUTIONS)]

    pos = phenotype_positives(ds, horizon)
    hist = pos[["patient_id", "phenotype", "sample_date", "ward_code", "organism"]].rename(
        columns={"sample_date": "pos_date", "ward_code": "pos_ward"}
    )
    m = visits.merge(hist, on="patient_id")
    m = m[m.pos_date < m.sample_date]  # positives known before this sample
    if CARRIER_FLAG_DAYS is not None:
        m = m[(m.sample_date - m.pos_date).dt.days <= CARRIER_FLAG_DAYS]
    if m.empty:
        return m.assign(flags=[])

    key = ["patient_id", "ward_code", "sample_date"]
    flags = (
        m.groupby([*key, "phenotype"], sort=False)
        .agg(
            first_positive=("pos_date", "min"),
            first_ward=("pos_ward", "first"),
            last_positive=("pos_date", "max"),
            last_ward=("pos_ward", "last"),
            positives=("pos_date", "size"),
            organisms=("organism", lambda s: sorted(set(s))),
        )
        .reset_index()
    )
    flags["flag"] = [
        {
            "phenotype": f.phenotype,
            "first_positive": f.first_positive.date().isoformat(),
            "first_ward": f.first_ward,
            "last_positive": f.last_positive.date().isoformat(),
            "last_ward": f.last_ward,
            "positives": int(f.positives),
            "organisms": f.organisms,
        }
        for f in flags.itertuples(index=False)
    ]
    per_visit = flags.groupby(key, sort=False).flag.agg(list).rename("flags").reset_index()
    out = visits.merge(per_visit, on=key)
    return out.sort_values(["sample_date", "patient_id"], kind="stable").reset_index(drop=True)


def detect_carriers(ds: Dataset, horizon: date, since: date | None = None) -> list[Firing]:
    events = reappearances(ds, horizon)
    if since:
        events = events[events.sample_date >= pd.Timestamp(since)]
    firings = []
    for e in events.itertuples(index=False):
        phenotypes = [f["phenotype"] for f in e.flags]
        first = min(e.flags, key=lambda f: f["first_positive"])
        moved = (
            None
            if pd.isna(e.prev_ward) or e.prev_ward == e.ward_code
            else {"ward": e.prev_ward, "date": e.prev_date.date().isoformat()}
        )
        firings.append(
            Firing(
                type="carrier",
                ward=e.ward_code,
                subject=e.patient_id,
                day=e.sample_date.date(),
                title=(
                    f"Known {' + '.join(phenotypes)} carrier sampled: patient {e.patient_id} "
                    f"(positive since {first['first_positive']}, {first['first_ward']})"
                ),
                evidence={
                    "method": "Rule: a known carrier (earlier positive result) gets a new sample "
                    f"on a hospital ward not visited in the last {CARRIER_REVISIT_DAYS} days",
                    "patient_id": e.patient_id,
                    "phenotypes": phenotypes,
                    "flags": e.flags,
                    "specimen": e.specimen,
                    "inpatient": not pd.isna(e.admission_date),
                    "admission_date": None
                    if pd.isna(e.admission_date)
                    else e.admission_date.date().isoformat(),
                    "previous_sample": moved,
                    "revisit_days": CARRIER_REVISIT_DAYS,
                },
            )
        )
    return firings
