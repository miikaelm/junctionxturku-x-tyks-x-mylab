"""Joined, analysis-ready frames (DATA-01) with derived fields (DATA-03, age bands).

Every downstream computation works on these frames. They are sorted by sample date so that
`drop_duplicates(keep="first")` picks the earliest isolate (DATA-02).
"""

from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from app.config import AGE_BANDS, HOSPITAL_ACQUIRED_MIN_DAYS
from app.data.loader import Tables, get_tables


@dataclass(frozen=True)
class Dataset:
    cultures: pd.DataFrame  # one row per culture, with patient fields and derived flags
    isolates: pd.DataFrame  # one row per isolate, with its culture's fields
    ast: pd.DataFrame  # isolate_id, organism, antibiotic_code, resistant
    antibiotics: pd.DataFrame
    wards: pd.DataFrame
    tested_pairs: frozenset[tuple[str, str]]  # (organism, antibiotic_code) present in the data

    @property
    def start(self) -> pd.Timestamp:
        return self.cultures.sample_date.min()

    @property
    def end(self) -> pd.Timestamp:
        return self.cultures.sample_date.max()


def age_band(age: pd.Series) -> pd.Series:
    bins = [lo - 0.5 for _, lo, _ in AGE_BANDS] + [AGE_BANDS[-1][2] + 0.5]
    return pd.cut(age, bins=bins, labels=[label for label, _, _ in AGE_BANDS]).astype(str)


def hospital_acquired(cultures: pd.DataFrame) -> pd.Series:
    """Inpatient sample taken on hospital day 3 or later (admission day = day 1)."""
    days = (cultures.sample_date - cultures.admission_date).dt.days
    return days.ge(HOSPITAL_ACQUIRED_MIN_DAYS).fillna(False).astype(bool)


def build_dataset(tables: Tables) -> Dataset:
    cultures = tables.cultures.merge(tables.patients, on="patient_id", how="left")
    cultures["hospital_acquired"] = hospital_acquired(cultures)
    cultures["age_band"] = age_band(cultures.age_years)
    cultures = cultures.sort_values(["sample_date", "culture_id"], kind="stable")
    cultures = cultures.reset_index(drop=True)

    culture_cols = [
        "culture_id",
        "patient_id",
        "sample_date",
        "ward_code",
        "ward_type",
        "institution",
        "specimen",
        "admission_date",
        "hospital_acquired",
        "age_years",
        "age_band",
        "sex",
        "home_area",
    ]
    isolates = tables.isolates.merge(cultures[culture_cols], on="culture_id", how="inner")
    isolates = isolates.sort_values(["sample_date", "isolate_id"], kind="stable")
    isolates = isolates.reset_index(drop=True)

    ast = tables.susceptibility[["isolate_id", "organism", "antibiotic_code"]].copy()
    ast["resistant"] = tables.susceptibility.result.eq("R")

    tested = frozenset(
        ast[["organism", "antibiotic_code"]].drop_duplicates().itertuples(index=False, name=None)
    )
    return Dataset(
        cultures=cultures,
        isolates=isolates,
        ast=ast,
        antibiotics=tables.antibiotics,
        wards=tables.wards,
        tested_pairs=tested,
    )


@lru_cache(maxsize=1)
def get_dataset() -> Dataset:
    return build_dataset(get_tables())
