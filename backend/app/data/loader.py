"""Load the raw CSV tables (DATA-01). Joins and derived fields build on top of this."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.config import DATA_DIR


@dataclass(frozen=True)
class Tables:
    patients: pd.DataFrame
    cultures: pd.DataFrame
    isolates: pd.DataFrame
    susceptibility: pd.DataFrame
    antibiotics: pd.DataFrame
    wards: pd.DataFrame


def load_tables(data_dir: Path = DATA_DIR) -> Tables:
    return Tables(
        patients=pd.read_csv(data_dir / "patients.csv"),
        cultures=pd.read_csv(
            data_dir / "cultures.csv", parse_dates=["sample_date", "admission_date"]
        ),
        isolates=pd.read_csv(data_dir / "isolates.csv"),
        susceptibility=pd.read_csv(data_dir / "susceptibility.csv"),
        antibiotics=pd.read_csv(data_dir / "antibiotics.csv"),
        wards=pd.read_csv(data_dir / "wards.csv"),
    )


@lru_cache(maxsize=1)
def get_tables() -> Tables:
    return load_tables()
