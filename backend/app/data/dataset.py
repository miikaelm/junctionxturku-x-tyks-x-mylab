"""Joined, analysis-ready frames (DATA-01) with derived fields (DATA-03, age bands).

Every downstream computation works on these frames. They are sorted by sample date so that
`drop_duplicates(keep="first")` picks the earliest isolate (DATA-02).
"""

from dataclasses import dataclass

import pandas as pd

from app.config import AGE_BANDS, HOSPITAL_ACQUIRED_MIN_DAYS
from app.data.loader import Tables


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


CULTURE_COLS = [
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


def _derive_cultures(cultures: pd.DataFrame, patients: pd.DataFrame) -> pd.DataFrame:
    out = cultures.merge(patients, on="patient_id", how="left")
    out["hospital_acquired"] = hospital_acquired(out)
    out["age_band"] = age_band(out.age_years)
    return out


def _derive_ast(susceptibility: pd.DataFrame) -> pd.DataFrame:
    ast = susceptibility[["isolate_id", "organism", "antibiotic_code"]].copy()
    ast["resistant"] = susceptibility.result.eq("R")
    return ast


def _by_date(df: pd.DataFrame, id_col: str) -> pd.DataFrame:
    """Sorted by sample date, so drop_duplicates(keep="first") picks the earliest (DATA-02)."""
    return df.sort_values(["sample_date", id_col], kind="stable").reset_index(drop=True)


def _pairs(ast: pd.DataFrame) -> frozenset[tuple[str, str]]:
    return frozenset(
        ast[["organism", "antibiotic_code"]].drop_duplicates().itertuples(index=False, name=None)
    )


def build_dataset(tables: Tables) -> Dataset:
    cultures = _by_date(_derive_cultures(tables.cultures, tables.patients), "culture_id")
    isolates = tables.isolates.merge(cultures[CULTURE_COLS], on="culture_id", how="inner")
    ast = _derive_ast(tables.susceptibility)
    return Dataset(
        cultures=cultures,
        isolates=_by_date(isolates, "isolate_id"),
        ast=ast,
        antibiotics=tables.antibiotics,
        wards=tables.wards,
        tested_pairs=_pairs(ast),
    )


def extend_dataset(ds: Dataset, patients: pd.DataFrame, batch: Tables) -> Dataset:
    """`ds` with a batch of new rows appended (DATA-05). Only the new rows are joined and
    derived; existing rows are reused. New isolates may belong to cultures received earlier
    (results arrive after the sample), so they join against all cultures."""
    new_cultures = _derive_cultures(batch.cultures, patients)
    cultures = _by_date(pd.concat([ds.cultures, new_cultures], ignore_index=True), "culture_id")
    new_isolates = batch.isolates.merge(cultures[CULTURE_COLS], on="culture_id", how="inner")
    new_ast = _derive_ast(batch.susceptibility)
    return Dataset(
        cultures=cultures,
        isolates=_by_date(pd.concat([ds.isolates, new_isolates], ignore_index=True), "isolate_id"),
        ast=pd.concat([ds.ast, new_ast], ignore_index=True),
        antibiotics=ds.antibiotics,
        wards=ds.wards,
        tested_pairs=ds.tested_pairs | _pairs(new_ast),
    )


def get_dataset() -> Dataset:
    """The current dataset: everything received so far (see app/data/store.py)."""
    from app.data.store import get_store  # the store builds on this module

    return get_store().dataset
