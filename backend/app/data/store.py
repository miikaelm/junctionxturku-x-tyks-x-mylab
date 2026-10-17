"""The data received so far, and incremental ingestion (DATA-05).

New rows (patients, cultures, isolates, susceptibility results) arrive in batches in the same
schema as the CSVs, as they would from the lab information system. A batch is validated, only
its own rows are joined and derived (`extend_dataset`), and listeners (the alert engine) re-run
their work only from the earliest sample date the batch touches: everything before that date is
unchanged, because every computation is causal (LIVE-01). Statistics are computed per request,
so they pick up the new rows directly.

With config.HOLD_BACK_FROM set, samples from that date on are held back at startup and can be
received day by day through the same path (a simulated live feed for the demo).
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta
from functools import lru_cache

import pandas as pd

from app import config
from app.data.dataset import Dataset, build_dataset, extend_dataset
from app.data.loader import Tables, get_tables

# Called as hook(old_dataset, new_dataset, since) after each ingest, before the new dataset
# becomes current; `since` is None when no sample data changed. The alert engine registers here.
INGEST_HOOKS: list[Callable[[Dataset, Dataset, date | None], None]] = []

BATCH_TABLES = ("patients", "cultures", "isolates", "susceptibility")
KEYS = {
    "patients": ["patient_id"],
    "cultures": ["culture_id"],
    "isolates": ["isolate_id"],
    "susceptibility": ["isolate_id", "antibiotic_code"],
}
DATE_COLS = {"cultures": ["sample_date", "admission_date"]}


class IngestError(ValueError):
    """The batch was rejected; nothing was changed."""


@dataclass(frozen=True)
class Batch:
    patients: pd.DataFrame
    cultures: pd.DataFrame
    isolates: pd.DataFrame
    susceptibility: pd.DataFrame

    @property
    def rows(self) -> dict[str, int]:
        return {f.name: len(getattr(self, f.name)) for f in fields(self)}


class DataStore:
    def __init__(self, tables: Tables, hold_back_from: date | None = None):
        self._lock = threading.Lock()
        self.held_back: Batch | None = None
        if hold_back_from is not None:
            tables, self.held_back = _split(tables, hold_back_from)
        self.tables = tables
        self.dataset = build_dataset(tables)
        self.version = 1
        self.log: list[dict] = []

    def today(self) -> date:
        """The scenario's "today": the last sample received, unless pinned (config)."""
        return config.AS_OF_OVERRIDE or self.dataset.end.date()

    def status(self) -> dict:
        held = self.held_back
        held_dates = held.cultures.sample_date if held is not None else pd.Series(dtype=object)
        return {
            "version": self.version,
            "data_start": self.dataset.start.date().isoformat(),
            "data_end": self.dataset.end.date().isoformat(),
            "today": self.today().isoformat(),
            "rows": {
                "cultures": len(self.tables.cultures),
                "isolates": len(self.tables.isolates),
                "susceptibility": len(self.tables.susceptibility),
            },
            "held_back": None
            if held_dates.empty
            else {
                "from": held_dates.min().date().isoformat(),
                "to": held_dates.max().date().isoformat(),
                "days": int(held_dates.dt.normalize().nunique()),
                "cultures": len(held_dates),
            },
            "last_ingest": self.log[-1] if self.log else None,
            "ingests": len(self.log),
        }

    def ingest(self, batch: Batch, source: str = "api") -> dict:
        with self._lock:
            t0 = time.perf_counter()
            batch = _normalise(batch, self.tables)
            _validate(batch, self.tables, self.dataset)
            if not any(batch.rows.values()):
                raise IngestError("empty batch")

            old = self.dataset
            patients = pd.concat([self.tables.patients, batch.patients], ignore_index=True)
            new = extend_dataset(old, patients, batch)
            since = _earliest_date(batch, new)
            derived = time.perf_counter() - t0
            for hook in INGEST_HOOKS:
                hook(old, new, since)

            self.tables = Tables(
                patients=patients,
                cultures=pd.concat([self.tables.cultures, batch.cultures], ignore_index=True),
                isolates=pd.concat([self.tables.isolates, batch.isolates], ignore_index=True),
                susceptibility=pd.concat(
                    [self.tables.susceptibility, batch.susceptibility], ignore_index=True
                ),
                antibiotics=self.tables.antibiotics,
                wards=self.tables.wards,
            )
            self.dataset = new
            self.version += 1
            entry = {
                "version": self.version,
                "at": datetime.now().isoformat(timespec="seconds"),
                "source": source,
                "rows": batch.rows,
                "sample_dates": _date_range(batch.cultures.sample_date),
                "recomputed_from": since.isoformat() if since else None,
                "seconds": {
                    "join": round(derived, 3),
                    "total": round(time.perf_counter() - t0, 3),
                },
            }
            self.log.append(entry)
            return entry

    def receive_held_back(self, days: int = 1) -> dict:
        """Simulated feed: ingest the next `days` days of held-back samples."""
        held = self.held_back
        if held is None or held.cultures.empty:
            raise IngestError("no held-back data left to receive")
        first = held.cultures.sample_date.min()
        take = held.cultures.sample_date < first + timedelta(days=days)
        batch, rest = _partition(held, held.cultures.culture_id[take])
        entry = self.ingest(batch, source="simulated lab feed")
        self.held_back = rest
        return entry


def _partition(tables, culture_ids: pd.Series) -> tuple[Batch, Batch]:
    """Rows belonging to these cultures, and the rest. Patients stay with the store."""
    empty = tables.patients.iloc[0:0]

    def part(keep: bool) -> Batch:
        def sel(df):
            return df[df.culture_id.isin(culture_ids) == keep]

        return Batch(empty, sel(tables.cultures), sel(tables.isolates), sel(tables.susceptibility))

    return part(True), part(False)


def _split(tables: Tables, hold_back_from: date) -> tuple[Tables, Batch]:
    held_ids = tables.cultures.culture_id[
        tables.cultures.sample_date >= pd.Timestamp(hold_back_from)
    ]
    held, kept = _partition(tables, held_ids)
    current = Tables(
        patients=tables.patients,
        cultures=kept.cultures,
        isolates=kept.isolates,
        susceptibility=kept.susceptibility,
        antibiotics=tables.antibiotics,
        wards=tables.wards,
    )
    return current, held


def batch_from_records(records: dict[str, list[dict]], tables: Tables) -> Batch:
    """A batch from JSON records (one list per table; missing tables are empty)."""
    unknown = set(records) - set(BATCH_TABLES)
    if unknown:
        raise IngestError(f"unknown tables: {sorted(unknown)}")
    frames = {}
    for name in BATCH_TABLES:
        rows = records.get(name) or []
        columns = getattr(tables, name).columns
        frames[name] = pd.DataFrame(rows) if rows else pd.DataFrame(columns=columns)
    return Batch(**frames)


def _normalise(batch: Batch, tables: Tables) -> Batch:
    """Same columns, order and dtypes as the stored tables; dates parsed."""
    out = {}
    for name in BATCH_TABLES:
        df = getattr(batch, name)
        expected = getattr(tables, name).columns
        missing = [c for c in expected if c not in df.columns]
        if missing:
            raise IngestError(f"{name}: missing columns {missing}")
        df = df[list(expected)].copy()
        for col in DATE_COLS.get(name, []):
            try:
                df[col] = pd.to_datetime(df[col], format="ISO8601")
            except (ValueError, TypeError) as e:
                raise IngestError(f"{name}.{col}: {e}") from e
        for col in expected:
            target = getattr(tables, name)[col].dtype
            if df[col].dtype != target and not df.empty:
                try:
                    df[col] = df[col].astype(target)
                except (ValueError, TypeError) as e:
                    raise IngestError(f"{name}.{col}: expected {target}") from e
        out[name] = df.reset_index(drop=True)
    return Batch(**out)


def _validate(batch: Batch, tables: Tables, ds: Dataset) -> None:
    errors = []
    for name, key in KEYS.items():
        new, old = getattr(batch, name), getattr(tables, name)
        if new.duplicated(key).any():
            errors.append(f"{name}: duplicate {'/'.join(key)} in the batch")
        clash = new[key].merge(old[key], on=key)
        if len(clash):
            errors.append(f"{name}: {len(clash)} rows already received ({'/'.join(key)})")

    def missing(child: pd.Series, *parents: pd.Series) -> int:
        known = pd.concat(parents)
        return int((~child.isin(known)).sum())

    checks = [
        (
            "cultures.patient_id",
            batch.cultures.patient_id,
            tables.patients.patient_id,
            batch.patients.patient_id,
        ),
        ("cultures.ward_code", batch.cultures.ward_code, tables.wards.ward_code),
        (
            "isolates.culture_id",
            batch.isolates.culture_id,
            tables.cultures.culture_id,
            batch.cultures.culture_id,
        ),
        (
            "susceptibility.isolate_id",
            batch.susceptibility.isolate_id,
            tables.isolates.isolate_id,
            batch.isolates.isolate_id,
        ),
        (
            "susceptibility.antibiotic_code",
            batch.susceptibility.antibiotic_code,
            tables.antibiotics.antibiotic_code,
        ),
    ]
    for label, child, *parents in checks:
        if n := missing(child, *parents):
            errors.append(f"{label}: {n} rows reference unknown ids")
    if not batch.susceptibility.result.isin(["S", "R"]).all():
        errors.append("susceptibility.result: only S and R are allowed")
    if (batch.cultures.sample_date < ds.start).any():
        errors.append(f"cultures.sample_date: before the first sample ({ds.start.date()})")
    if errors:
        raise IngestError("; ".join(errors))


def _earliest_date(batch: Batch, ds: Dataset) -> date | None:
    """The earliest sample date the batch adds data to: computations from here on change."""
    touched = pd.concat(
        [
            batch.cultures.culture_id,
            batch.isolates.culture_id,
            batch.susceptibility.culture_id,
        ]
    )
    dates = ds.cultures.sample_date[ds.cultures.culture_id.isin(touched)]
    return dates.min().date() if len(dates) else None


def _date_range(dates: pd.Series) -> dict | None:
    if dates.empty:
        return None
    return {"from": dates.min().date().isoformat(), "to": dates.max().date().isoformat()}


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    return DataStore(get_tables(), config.HOLD_BACK_FROM)
