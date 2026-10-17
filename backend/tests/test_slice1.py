from dataclasses import replace
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.data.dataset import build_dataset, get_dataset, hospital_acquired
from app.data.first_isolate import first_isolates
from app.data.freshness import ward_freshness
from app.data.loader import get_tables
from app.data.scope import Scope
from app.data.windows import annual, recent
from app.main import app
from app.stats.antibiogram import build_antibiogram
from app.stats.proportions import estimate, wilson_interval

client = TestClient(app)


def test_wilson_matches_reference_values():
    lo, hi = wilson_interval(3, 10)
    assert lo == pytest.approx(0.108, abs=1e-3)
    assert hi == pytest.approx(0.603, abs=1e-3)
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_estimate_gates_percentages_on_min_n():
    assert estimate(7, 11)["sufficient"] is False
    assert estimate(3, 30)["sufficient"] is True
    assert estimate(0, 0)["pct"] is None


def test_first_isolate_keeps_earliest_per_patient_organism_specimen():
    df = pd.DataFrame(
        {
            "isolate_id": ["a", "b", "c", "d"],
            "patient_id": ["P1", "P1", "P1", "P2"],
            "organism": ["E. coli", "E. coli", "E. coli", "E. coli"],
            "specimen": ["urine", "urine", "blood", "urine"],
            "sample_date": pd.to_datetime(["2025-01-01", "2025-01-05", "2025-01-06", "2025-01-02"]),
        }
    )
    assert list(first_isolates(df).isolate_id) == ["a", "c", "d"]


def test_hospital_acquired_from_hospital_day_three():
    df = pd.DataFrame(
        {
            "sample_date": pd.to_datetime(["2025-01-03", "2025-01-02", "2025-01-05"]),
            "admission_date": pd.to_datetime(["2025-01-01", "2025-01-01", None]),
        }
    )
    assert list(hospital_acquired(df)) == [True, False, False]


def test_windows_end_on_as_of():
    as_of = date(2026, 9, 27)
    assert recent(as_of).start == date(2026, 8, 31) and recent(as_of).days == 28
    assert annual(as_of).days == 365 and annual(as_of).end == as_of


def test_fallback_chain():
    wards = get_dataset().wards
    assert [s.location for s in Scope("GER").chain(wards)] == ["GER", "hospital", "all"]
    assert [s.location for s in Scope("PHC-S").chain(wards)] == ["PHC-S", "primary_care", "all"]


def _cell(body, organism, code):
    row = next(o for o in body["organisms"] if o["organism"] == organism)
    return row["cells"][code]


def test_antibiogram_rules():
    ds = get_dataset()
    as_of = date(2026, 9, 27)
    blood = build_antibiogram(ds, Scope("all", "blood"), as_of)
    assert {"MEC", "TMP", "NIT"}.isdisjoint(a["code"] for a in blood["antibiotics"])

    urine = build_antibiogram(ds, Scope("GER", "urine"), as_of)
    assert _cell(urine, "Klebsiella pneumoniae", "AMP")["intrinsic"] is True
    assert _cell(urine, "Escherichia coli", "CIP")["intrinsic"] is False
    assert _cell(urine, "Pseudomonas aeruginosa", "AMP") is None  # never tested

    # ICU wound Pseudomonas is too thin on the ward → falls back to hospital level.
    wound = build_antibiogram(ds, Scope("ICU", "wound"), as_of)
    annual_cell = _cell(wound, "Pseudomonas aeruginosa", "CIP")["annual"]
    assert annual_cell["levels"][0]["sufficient"] is False
    assert annual_cell["shown"] == 1


def test_as_of_uses_no_future_data():
    """Computing at an earlier as-of on the full data equals computing on truncated data."""
    as_of = date(2025, 7, 5)
    tables = get_tables()
    keep = tables.cultures.culture_id[tables.cultures.sample_date <= pd.Timestamp(as_of)]
    truncated = build_dataset(
        replace(
            tables,
            cultures=tables.cultures[tables.cultures.culture_id.isin(keep)],
            isolates=tables.isolates[tables.isolates.culture_id.isin(keep)],
            susceptibility=tables.susceptibility[tables.susceptibility.culture_id.isin(keep)],
        )
    )
    scope = Scope("URO", "urine")
    assert build_antibiogram(get_dataset(), scope, as_of) == build_antibiogram(
        truncated, scope, as_of
    )
    assert ward_freshness(get_dataset(), as_of) == ward_freshness(truncated, as_of)


def test_freshness_flags_silent_ward():
    by_ward = {w["ward_code"]: w for w in ward_freshness(get_dataset(), date(2025, 12, 10))}
    assert by_ward["PHC-S"]["status"] == "stale"
    assert by_ward["PHC-S"]["days_since_last"] == 3
    assert by_ward["ED"]["status"] == "ok"


def test_api_endpoints():
    assert client.get("/api/meta").json()["thresholds"]["min_isolates"] == 30
    body = client.get("/api/antibiogram", params={"location": "URO", "specimen": "urine"}).json()
    assert body["scope"]["label"] == "Urology"
    assert [lvl["location"] for lvl in body["levels"]] == ["URO", "hospital", "all"]
    assert client.get("/api/antibiogram", params={"location": "XX"}).status_code == 422
    assert client.get("/api/freshness", params={"as_of": "2020-01-01"}).status_code == 422
