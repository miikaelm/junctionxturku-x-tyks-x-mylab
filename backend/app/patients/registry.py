"""Carrier registry (PAT-01) and the patient record behind the patient-context API (API-03).

A patient becomes a known carrier of a phenotype (ESBL / MRSA / VRE / CPE) on the sample date of
their first isolate carrying it. Derived from results only, so the registry at any as-of date
uses no later data (LIVE-01). Flags don't expire unless config.CARRIER_FLAG_DAYS is set: in
practice they are cleared by negative screening, which this data does not record.

Patient-level data: for infection control, lab and patient-context calls (NF-03).
"""

from datetime import date, timedelta

import pandas as pd

from app.config import CARRIER_FLAG_DAYS, CARRIER_PHENOTYPES, PHENOTYPES
from app.data.dataset import Dataset


def phenotype_positives(ds: Dataset, as_of: date | None = None) -> pd.DataFrame:
    """One row per isolate × carrier phenotype it carries (sorted by date)."""
    iso = ds.isolates
    if as_of is not None:
        iso = iso[iso.sample_date <= pd.Timestamp(as_of)]
    parts = [iso[iso[p.lower()].eq(1)].assign(phenotype=p) for p in CARRIER_PHENOTYPES]
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values(["sample_date", "isolate_id"], kind="stable").reset_index(drop=True)


def carriers(ds: Dataset, as_of: date) -> pd.DataFrame:
    """The registry on `as_of`: one row per patient × phenotype with the first and last positive.

    Columns: patient_id, phenotype, first_positive, first_ward, first_organism, last_positive,
    last_ward, positives, organisms (list), wards (list), sex, birth_year, home_area.
    """
    pos = phenotype_positives(ds, as_of)
    if pos.empty:
        return pd.DataFrame(
            columns=[
                "patient_id", "phenotype", "first_positive", "first_ward", "first_organism",
                "last_positive", "last_ward", "positives", "organisms", "wards",
            ]
        )  # fmt: skip
    g = pos.groupby(["patient_id", "phenotype"], sort=False)
    reg = g.agg(
        first_positive=("sample_date", "first"),
        first_ward=("ward_code", "first"),
        first_organism=("organism", "first"),
        last_positive=("sample_date", "last"),
        last_ward=("ward_code", "last"),
        positives=("isolate_id", "size"),
        organisms=("organism", lambda s: sorted(set(s))),
        wards=("ward_code", lambda s: list(dict.fromkeys(s))),
    ).reset_index()
    if CARRIER_FLAG_DAYS is not None:
        cutoff = pd.Timestamp(as_of - timedelta(days=CARRIER_FLAG_DAYS))
        reg = reg[reg.last_positive >= cutoff]
    return reg.sort_values(["first_positive", "patient_id"], ascending=[False, True]).reset_index(
        drop=True
    )


def carrier_flags(ds: Dataset, patient_id: str, as_of: date) -> list[dict]:
    reg = carriers(ds, as_of)
    return [flag_dict(r) for r in reg[reg.patient_id.eq(patient_id)].itertuples(index=False)]


def flag_dict(r) -> dict:
    return {
        "patient_id": r.patient_id,
        "phenotype": r.phenotype,
        "first_positive": r.first_positive.date().isoformat(),
        "first_ward": r.first_ward,
        "first_organism": r.first_organism,
        "last_positive": r.last_positive.date().isoformat(),
        "last_ward": r.last_ward,
        "positives": int(r.positives),
        "organisms": list(r.organisms),
        "wards": list(r.wards),
    }


def patient_exists(ds: Dataset, patient_id: str) -> bool:
    return bool(ds.cultures.patient_id.eq(patient_id).any())


def patient_record(ds: Dataset, patient_id: str, as_of: date) -> dict | None:
    """Demographics, carrier flags and every sample up to as_of with its findings."""
    cul = ds.cultures[
        ds.cultures.patient_id.eq(patient_id) & (ds.cultures.sample_date <= pd.Timestamp(as_of))
    ]
    if cul.empty:
        return None
    iso = ds.isolates[ds.isolates.culture_id.isin(cul.culture_id)]
    ast = ds.ast[ds.ast.isolate_id.isin(iso.isolate_id) & ds.ast.resistant]
    resistant = ast.groupby("isolate_id").antibiotic_code.agg(list)
    by_culture: dict[str, list[dict]] = {}
    for i in iso.itertuples(index=False):
        by_culture.setdefault(i.culture_id, []).append(
            {
                "isolate_id": i.isolate_id,
                "organism": i.organism,
                "phenotypes": [p for p in PHENOTYPES if getattr(i, p.lower()) == 1],
                "resistant": resistant.get(i.isolate_id, []),
            }
        )
    last = cul.iloc[-1]
    samples = [
        {
            "culture_id": c.culture_id,
            "date": c.sample_date.date().isoformat(),
            "ward": c.ward_code,
            "ward_type": c.ward_type,
            "specimen": c.specimen,
            "result": c.result,
            "admission_date": None
            if pd.isna(c.admission_date)
            else c.admission_date.date().isoformat(),
            "hospital_acquired": bool(c.hospital_acquired),
            "isolates": by_culture.get(c.culture_id, []),
        }
        for c in cul.itertuples(index=False)
    ]
    return {
        "patient_id": patient_id,
        "sex": last.sex,
        "birth_year": int(last.birth_year),
        "age": as_of.year - int(last.birth_year),
        "home_area": last.home_area,
        "last_ward": last.ward_code,
        "last_sample": last.sample_date.date().isoformat(),
        "flags": carrier_flags(ds, patient_id, as_of),
        "samples": samples[::-1],  # newest first
    }
