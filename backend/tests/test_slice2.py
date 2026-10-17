"""Slice 2: detectors, alerts, triage.

The planted events of PROJECT.md §8 appear here only as a validation set: the detectors know
nothing about them, and these tests check that the general methods find them (and little else).
"""

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from statsmodels.stats.multitest import multipletests

from app.alerts import engine
from app.alerts.triage import TriageStore, get_triage_store
from app.data.dataset import build_dataset, get_dataset
from app.data.loader import get_tables
from app.detectors.common import bh_qvalues
from app.main import app

TODAY = date(2026, 9, 27)


@pytest.fixture
def store(tmp_path):
    return TriageStore(tmp_path / "triage.json")


@pytest.fixture
def client(store):
    app.dependency_overrides[get_triage_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def _episodes(type_: str, ward: str | None = None) -> list[engine.Episode]:
    return [
        e
        for e in engine.timeline(get_dataset(), TODAY)
        if e.type == type_ and (ward is None or e.ward == ward)
    ]


def test_bh_matches_statsmodels():
    p = np.array([0.001, 0.04, 0.03, 0.2, 0.0005, 0.5])
    expected = multipletests(p, method="fdr_bh")[1]
    assert bh_qvalues(p) == pytest.approx(expected)
    # Untested hypotheses count towards the family size.
    assert bh_qvalues(np.array([0.01]), m=10)[0] == pytest.approx(0.1)


def test_cluster_finds_planted_outbreaks():
    uro = [e for e in _episodes("cluster", "URO") if e.subject == "ESBL"]
    assert len(uro) == 1 and date(2025, 6, 1) <= uro[0].first <= date(2025, 6, 14)  # E1
    icu = [e for e in _episodes("cluster", "ICU") if e.subject == "MRSA"]
    assert len(icu) == 1 and date(2026, 3, 3) <= icu[0].first <= date(2026, 3, 10)  # E2
    # Hospital-acquired cases are counted in the evidence.
    assert icu[0].firings[-1].evidence["hospital_acquired"] >= 5
    # FDR control keeps other cluster alerts rare over three years.
    assert len(_episodes("cluster")) <= 4


def test_rate_shift_finds_uro_ceftriaxone_jump():
    uro = [e for e in _episodes("rate_shift", "URO") if e.subject == "urine|Escherichia coli"]
    assert uro and date(2025, 6, 8) <= uro[0].first <= date(2025, 6, 22)  # E1
    codes = {s["antibiotic_code"] for f in uro[0].firings for s in f.evidence["shifts"]}
    assert "CRO" in codes
    assert len(_episodes("rate_shift")) <= 4


def test_data_gap_finds_only_the_planted_gap():
    gaps = _episodes("data_gap")
    assert [(e.ward, e.first) for e in gaps] == [("PHC-S", date(2025, 12, 9))]  # E3


def test_novelty_flags_first_icu_mrsa_on_day_one():
    hits = [e for e in _episodes("novelty", "ICU") if e.subject == "MRSA"]
    first = next(e for e in hits if e.first == date(2026, 3, 3))  # E2, before the cluster
    assert first.firings[0].evidence["gap_days"] == 323


def test_sentinels_one_alert_per_case():
    sentinels = _episodes("sentinel")
    markers = [e.subject.split("|")[0] for e in sentinels]
    assert markers.count("CPE") == 12 and markers.count("VRE") == 5  # E5
    vre_ger = next(e for e in sentinels if e.ward == "GER" and e.subject.startswith("VRE"))
    assert vre_ger.first == date(2026, 9, 11) and vre_ger.firings[0].evidence["first_ever"]
    cpe_meda = next(e for e in sentinels if e.ward == "MED-A" and e.first == date(2026, 9, 21))
    assert cpe_meda.firings[0].evidence["gap_days"] == 822
    # Pseudomonas meropenem resistance is background, not a sentinel.
    assert not any(e.firings[0].evidence["organism"] == "Pseudomonas aeruginosa" for e in sentinels)


def test_alerts_at_as_of(store):
    ds = get_dataset()
    active = engine.alerts_at(ds, TODAY, store)
    assert {(a["type"], a["ward"]) for a in active} >= {("sentinel", "GER"), ("sentinel", "MED-A")}
    assert active[0]["severity"] == "critical"
    # The URO outbreak is active in late June 2025 and resolved by September.
    june = engine.alerts_at(ds, date(2025, 6, 20), store, wards={"URO"})
    assert {a["type"] for a in june} == {"cluster", "rate_shift"}
    sept = engine.alerts_at(ds, date(2025, 9, 1), store, wards={"URO"}, include_resolved=True)
    assert sept and all(a["state"] == "resolved" for a in sept)


def test_alerts_use_no_future_data(store):
    as_of = date(2026, 3, 20)
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
    full = engine.alerts_at(get_dataset(), as_of, store, include_resolved=True)
    assert full == engine.alerts_at(truncated, as_of, store, include_resolved=True)


def test_triage_applies_from_its_as_of_date(store):
    store.add("x", "investigating", date(2025, 6, 10), "looking")
    store.add("x", "confirmed", date(2025, 6, 20))
    assert store.current("x", date(2025, 6, 1)) is None
    assert store.current("x", date(2025, 6, 15))["status"] == "investigating"
    assert store.current("x", date(2025, 7, 1))["status"] == "confirmed"
    with pytest.raises(ValueError):
        store.add("x", "maybe", date(2025, 7, 1))


def test_dismissed_alert_suppresses_repeats():
    def summary(id_, first, last, status="new", as_of=None):
        triage = {"status": status, "note": "", "as_of": as_of, "suppressed_by": None}
        return {
            "id": id_,
            "type": "cluster",
            "ward": "GER",
            "subject": "ESBL",
            "first_seen": first,
            "last_seen": last,
            "triage": triage,
        }

    old = summary("a", "2025-01-01", "2025-01-20", "dismissed", "2025-01-21")
    soon = summary("b", "2025-03-01", "2025-03-05")
    later = summary("c", "2026-01-01", "2026-01-02")
    engine._suppress_dismissed_duplicates([old, soon, later])
    assert soon["triage"]["status"] == "dismissed" and soon["triage"]["suppressed_by"] == "a"
    assert later["triage"]["status"] == "new"


def test_alert_api_roundtrip(client):
    body = client.get("/api/alerts", params={"as_of": "2026-03-10", "location": "ICU"}).json()
    cluster = next(a for a in body["alerts"] if a["type"] == "cluster")
    assert body["counts"]["active"] >= 2

    detail = client.get(f"/api/alerts/{cluster['id']}", params={"as_of": "2026-03-10"}).json()
    assert detail["evidence"]["observed"] > detail["evidence"]["expected"]
    assert detail["cases"] and all(c["ward"] == "ICU" for c in detail["cases"])
    assert detail["timeline"]["unit"] == "week" and len(detail["timeline"]["points"]) == 26

    res = client.post(
        f"/api/alerts/{cluster['id']}/triage",
        json={"status": "investigating", "note": "contact precautions", "as_of": "2026-03-10"},
    )
    assert res.status_code == 200
    after = client.get("/api/alerts", params={"as_of": "2026-03-11", "location": "ICU"}).json()
    updated = next(a for a in after["alerts"] if a["id"] == cluster["id"])
    assert updated["triage"]["status"] == "investigating"
    before = client.get("/api/alerts", params={"as_of": "2026-03-09", "location": "ICU"}).json()
    assert (
        next(a for a in before["alerts"] if a["id"] == cluster["id"])["triage"]["status"] == "new"
    )

    # An alert doesn't exist before it first fired.
    assert (
        client.get(f"/api/alerts/{cluster['id']}", params={"as_of": "2026-03-01"}).status_code
        == 404
    )
    assert (
        client.post(f"/api/alerts/{cluster['id']}/triage", json={"status": "bogus"}).status_code
        == 422
    )
    assert client.get("/api/alerts", params={"type": "nope"}).status_code == 422


def test_rate_shift_detail_and_feed(client):
    body = client.get(
        "/api/alerts", params={"as_of": "2025-06-29", "type": "rate_shift", "location": "URO"}
    ).json()
    alert = body["alerts"][0]
    detail = client.get(f"/api/alerts/{alert['id']}", params={"as_of": "2025-06-29"}).json()
    assert detail["timeline"]["kind"] == "rate"
    assert any(c["highlight"] for c in detail["cases"])

    feed = client.get("/api/feed", params={"as_of": "2025-12-12"}).json()
    phc_s = next(w for w in feed["wards"] if w["ward_code"] == "PHC-S")
    assert phc_s["daily"]["counts"][-5:] == [0, 0, 0, 0, 0]
    assert phc_s["last_week"] < phc_s["expected_week"]
