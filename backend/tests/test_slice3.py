"""Slice 3: replay, trends, subgroup discovery, ward overview, incremental ingestion.

As in slice 2, the planted events of PROJECT.md §8 appear only here, as a validation set.
"""

from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.alerts import engine
from app.alerts.triage import TriageStore, get_triage_store
from app.data.dataset import build_dataset, get_dataset
from app.data.loader import get_tables
from app.data.scope import Scope
from app.data.store import DataStore, IngestError, batch_from_records
from app.data.windows import annual
from app.main import app
from app.stats import trends
from app.stats.subgroups import discover

TODAY = date(2026, 9, 27)


@pytest.fixture
def store(tmp_path):
    return TriageStore(tmp_path / "triage.json")


@pytest.fixture
def client(store):
    app.dependency_overrides[get_triage_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_cochran_armitage_matches_textbook():
    # Agresti, Categorical Data Analysis: alcohol and malformation, scores 0, 0.5, 1.5, 4, 7.
    q = pd.DataFrame(
        {
            "loc": "x",
            "specimen": "x",
            "organism": "x",
            "antibiotic_code": "x",
            "x": [0, 0.5, 1.5, 4, 7],
            "n": [17066 + 48, 14464 + 38, 788 + 5, 126 + 1, 37 + 1],
            "r": [48, 38, 5, 1, 1],
        }
    )
    z = trends.trend_tests(q).z.iloc[0]
    n = q.n.sum()
    assert z**2 * (n - 1) / n == pytest.approx(6.57, abs=0.01)


def test_trends_find_the_slow_tmp_drift_and_little_else():
    found = trends.findings(get_dataset(), TODAY)
    keys = {
        (f["location"], f["specimen"], f["organism"], f["antibiotic_code"]) for f in found["trends"]
    }
    assert ("all", "urine", "Escherichia coli", "TMP") in keys  # E4
    assert len(found["trends"]) <= 3  # FDR over ~500 series
    tmp = trends.series(get_dataset(), Scope("all", "urine"), "Escherichia coli", "TMP", TODAY)
    assert tmp["trend"]["direction"] == "up" and tmp["trend"]["significant"]
    assert tmp["trend_crosses_threshold"].startswith("2025")  # crosses ~20 % in 2025
    assert [y["year"] for y in tmp["years"]] == [2023, 2024, 2025, 2026]
    assert tmp["years"][0]["partial"] and not tmp["years"][1]["partial"]


def test_trends_use_no_future_data():
    as_of = date(2025, 3, 31)
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
    assert trends.findings(get_dataset(), as_of) == trends.findings(truncated, as_of)


def test_subgroups_rediscover_the_sex_effect():
    result = discover(get_dataset(), Scope("all", "urine"), annual(TODAY))
    sex = [
        f
        for f in result["findings"]
        if f["dimension"] == "sex" and f["organism"] == "Escherichia coli"
    ]
    assert any(f["antibiotic_code"] == "CIP" and f["high"] == "Men" for f in sex)
    assert result["compared"] > 100 and len(result["findings"]) <= 6
    # A ward is one ward: no "by ward" comparison inside it.
    ward = discover(get_dataset(), Scope("GER", "urine"), annual(TODAY))
    assert "ward_code" not in {d["key"] for d in ward["dimensions"]}


def test_default_split_and_its_overrides(client):
    def ecoli(**params):
        body = client.get("/api/antibiogram", params={"location": "GER", **params}).json()
        return next(o for o in body["organisms"] if o["organism"] == "Escherichia coli")

    split = ecoli()["split"]
    assert split["by"] == "sex" and split["default"]
    assert [r["label"] for r in split["rows"]] == ["Women", "Men"]
    assert "split" not in ecoli(sex="M")  # already filtered by sex
    assert "split" not in ecoli(split_by="none")
    custom = client.get(
        "/api/antibiogram",
        params={"location": "GER", "split_by": "age_band", "split_organism": "Proteus mirabilis"},
    ).json()
    assert [o["organism"] for o in custom["organisms"] if "split" in o] == ["Proteus mirabilis"]


def test_incremental_ingest_matches_full_rebuild(store):
    held = DataStore(get_tables(), date(2026, 8, 1))
    engine.timeline(held.dataset, held.today())  # cached, so ingests take the incremental path
    first = held.receive_held_back(1)
    assert first["recomputed_from"] == "2026-08-01" and first["version"] == 2
    while held.held_back is not None and not held.held_back.cultures.empty:
        held.receive_held_back(31)
    assert held.today() == TODAY

    full = get_dataset()
    for name in ("cultures", "isolates", "ast"):
        a = getattr(held.dataset, name).reset_index(drop=True)
        b = getattr(full, name).reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b, check_dtype=False)
    assert engine.alerts_at(held.dataset, TODAY, store, include_resolved=True) == engine.alerts_at(
        full, TODAY, store, include_resolved=True
    )


def test_ingest_rejects_bad_batches():
    held = DataStore(get_tables(), date(2026, 9, 20))
    tables = held.tables
    culture = tables.cultures.iloc[[-1]].assign(culture_id="NEW1", patient_id="P_UNKNOWN")
    records = {"cultures": culture.astype(str).to_dict(orient="records")}
    with pytest.raises(IngestError, match="unknown ids"):
        held.ingest(batch_from_records(records, tables))
    dup = {"cultures": tables.cultures.iloc[[0]].astype(str).to_dict(orient="records")}
    with pytest.raises(IngestError, match="already received"):
        held.ingest(batch_from_records(dup, tables))
    assert held.version == 1  # nothing changed


def test_ingest_api_and_status(client):
    status = client.get("/api/status").json()
    assert status["today"] == TODAY.isoformat() and status["held_back"] is None
    assert client.post("/api/ingest/held-back").status_code == 409
    assert client.post("/api/ingest", json={"cultures": []}).status_code == 422
    assert client.post("/api/ingest", json={"nope": []}).status_code == 422


def test_replay_events_and_detection_latency(client):
    events = client.get("/api/replay/events").json()["events"]

    def first(type_, ward, subject):
        hits = [
            e
            for e in events
            if e["type"] == type_ and e["ward"] == ward and e["subject"] == subject
        ]
        return min(hits, key=lambda e: e["first_seen"])

    for e in events:
        assert e["replay_from"] <= e["onset"] <= e["first_seen"]
        assert (
            e["detection_days"]
            == (date.fromisoformat(e["first_seen"]) - date.fromisoformat(e["onset"])).days
        )

    # ANOM-07 against the answer key (§8): days from the event's start to the first alert.
    def latency(event, start):
        return (date.fromisoformat(event["first_seen"]) - start).days

    e1 = first("cluster", "URO", "ESBL")
    assert latency(e1, date(2025, 6, 4)) <= 7
    e2 = [
        e
        for e in events
        if e["type"] == "novelty" and e["ward"] == "ICU" and e["first_seen"] == "2026-03-03"
    ]
    assert e2 and e2[0]["detection_days"] == 0
    e3 = first("data_gap", "PHC-S", "feed")
    assert e3["onset"] == "2025-12-08" and latency(e3, date(2025, 12, 8)) <= 1
    assert all(e["detection_days"] == 0 for e in events if e["type"] == "sentinel")


def test_overview_grid_shows_the_icu_mrsa_cluster(client):
    body = client.get(
        "/api/overview", params={"metric": "phenotype", "phenotype": "MRSA", "as_of": "2026-04-01"}
    ).json()
    assert len(body["bins"]) == 26 and body["bins"][-1]["end"] == "2026-04-01"
    icu = next(r for r in body["rows"] if r["ward"] == "ICU")
    assert sum(c["value"] for c in icu["cells"][-5:]) >= 10
    assert {a["type"] for c in icu["cells"] for a in c.get("alerts", [])} >= {"novelty", "cluster"}
    total = next(r for r in body["rows"] if r["ward"] == "ALL")
    per_ward = np.array(
        [[c["value"] for c in r["cells"]] for r in body["rows"] if r["ward"] != "ALL"]
    )
    assert [c["value"] for c in total["cells"]] == list(per_ward.sum(axis=0))

    rate = client.get(
        "/api/overview",
        params={
            "metric": "rate",
            "specimen": "urine",
            "organism": "Escherichia coli",
            "antibiotic": "CRO",
            "bins": 13,
            "bin_days": 28,
            "as_of": "2025-07-01",
        },
    ).json()
    uro = next(r for r in rate["rows"] if r["ward"] == "URO")
    assert uro["cells"][-1]["r"] >= 15 and uro["cells"][-1]["sufficient"]
    assert rate["bins"][0]["start"] == (date(2025, 7, 1) - timedelta(days=13 * 28 - 1)).isoformat()
