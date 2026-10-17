"""Slice 6: the national reference (DATA-08), every filter on the antibiogram (VIEW-02), the
order check against the patient's own results with order-sign (API-02), and the demo warm-up (NF-01).
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import config, demo, memo
from app.alerts.triage import TriageStore, get_triage_store
from app.data import national
from app.data.dataset import get_dataset
from app.main import app
from app.memo import Memo

TODAY = date(2026, 9, 27)
EHR_DAY = config.EHR_DEMO["as_of"]
CARRIER, EMPIRIC = config.EHR_DEMO["patients"]


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_triage_store] = lambda: TriageStore(tmp_path / "triage.json")
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_national_reference_lookup():
    # Urine E. coli is split by sex in Finres; without a sex the two are pooled by n.
    women = national.lookup("Escherichia coli", "urine", "TMP", "F")
    men = national.lookup("Escherichia coli", "urine", "TMP", "M")
    both = national.lookup("Escherichia coli", "urine", "TMP")
    assert (women["pct"], men["pct"]) == (16.0, 16.4) and women["group"] == "women"
    assert both["n"] == women["n"] + men["n"] and women["pct"] <= both["pct"] <= men["pct"]
    assert both["pooled"] and not women["pooled"]
    # Wound is compared with pus; a specimen-specific value beats an all-specimens one.
    assert national.lookup("Pseudomonas aeruginosa", "wound", "CIP")["specimen_label"] == "pus"
    assert (
        national.lookup("Klebsiella oxytoca", "urine", "CXM")["specimen_label"] == "all specimens"
    )
    assert national.lookup("Staphylococcus aureus", "blood", "FOX")["pct"] == 2.8  # MRSA share
    assert national.lookup("Escherichia coli", "urine", "AMP") is None  # not reported
    assert national.lookup("Escherichia coli", None, "TMP") is None


def test_antibiogram_has_every_filter_and_any_period(client):
    base = {"location": "hospital", "specimen": "urine", "as_of": TODAY.isoformat()}
    full = client.get("/api/antibiogram", params=base).json()
    assert [w["key"] for w in full["windows"]] == ["recent", "annual"] and not full["period"]
    ecoli = full["organisms"][0]
    assert ecoli["organism"] == "Escherichia coli"
    assert ecoli["cells"]["TMP"]["national"]["source"] == national.SOURCE["label"]

    year = client.get(
        "/api/antibiogram", params={**base, "year": 2025, "ward_type": "in", "home_area": "North"}
    ).json()
    assert year["period"] and year["windows"][0]["start"] == "2025-01-01"
    assert year["scope"]["ward_type"] == "in" and year["scope"]["home_area"] == "North"
    cell = year["organisms"][0]["cells"]["TMP"]
    assert cell["headline"] == "year" and "recent" not in cell
    assert year["organisms"][0]["isolates"]["year"][0] < ecoli["isolates"]["annual"][0]

    june = client.get(
        "/api/antibiogram",
        params={
            **base,
            "location": "URO",
            "period_start": "2025-06-01",
            "period_end": "2025-06-30",
        },
    ).json()
    assert june["windows"][0] == {
        "key": "custom",
        "label": "2025-06-01 – 2025-06-30",
        "start": "2025-06-01",
        "end": "2025-06-30",
        "days": 30,
    }
    # No period runs past the as-of date.
    capped = client.get(
        "/api/antibiogram",
        params={**base, "period_start": "2025-01-01", "as_of": "2025-03-01"},
    ).json()
    assert capped["windows"][0]["end"] == "2025-03-01"
    assert client.get("/api/antibiogram", params={**base, "year": 2019}).status_code == 422
    assert client.get("/api/antibiogram", params={**base, "home_area": "Mars"}).status_code == 422


def test_trend_series_and_findings_carry_the_national_figure(client):
    s = client.get(
        "/api/trends/series",
        params={"organism": "Escherichia coli", "antibiotic": "TMP", "specimen": "urine"},
    ).json()
    assert s["national"]["year"] == 2023 and s["national"]["pooled"]
    ref = client.get("/api/national").json()
    assert ref["source"]["year"] == 2023 and len(ref["values"]) > 30


def _cards(client, service, ctx, day=EHR_DAY):
    return client.post(
        f"/api/cds-services/{service}",
        params={"as_of": day.isoformat()},
        json={"hook": "order-select", "context": {"ward": "URO", "infection": "uti", **ctx}},
    ).json()["cards"]


def test_order_check_reads_the_patients_own_results(client):
    cards = _cards(client, "aei-antibiotic-choice", {"patientId": CARRIER, "antibiotic": "CRO"})
    # The patient's own resistant isolate outranks the ward's figures and comes first.
    assert cards[0]["indicator"] == "critical" and "own" in cards[0]["summary"]
    assert any("risen" in c["summary"] for c in cards)
    # Carriage is told when the record opens, a resistance shift per antibiotic: neither repeated.
    assert not any("carrier" in c["summary"] for c in cards)
    assert not any("resistance shift" in c["summary"] for c in cards)
    alt = next(c for c in cards if c.get("suggestions"))
    swaps = {
        s["actions"][0]["resource"]["medicationCodeableConcept"]["coding"][0]["code"]
        for s in alt["suggestions"]
    }
    patient = client.get(f"/api/patients/{CARRIER}", params={"as_of": EHR_DAY.isoformat()}).json()
    resisted = {c for s in patient["samples"] for i in s["isolates"] for c in i["resistant"]}
    assert (
        swaps and not swaps & resisted and "MEM" not in swaps
    )  # no reserve agent when others exist
    # A susceptible own result is mentioned, without a warning.
    mec = _cards(client, "aei-antibiotic-choice", {"patientId": CARRIER, "antibiotic": "MEC"})
    assert any("susceptible" in c["summary"] and c["indicator"] == "info" for c in mec)


def test_order_sign_interrupts_only_when_there_is_a_reason(client):
    services = client.get("/api/cds-services").json()["services"]
    assert {s["hook"] for s in services} == {"order-select", "order-sign", "patient-view"}
    stop = _cards(client, "aei-antibiotic-sign", {"patientId": EMPIRIC, "antibiotic": "TMP"})
    assert stop and all(c["indicator"] != "info" or c.get("suggestions") for c in stop)
    assert all(c["overrideReasons"] for c in stop if c["indicator"] != "info")
    # Alternatives: WHO AWaRe Access agents before Watch ones.
    alt = next(c for c in stop if c.get("suggestions"))
    groups = [
        config.AWARE_GROUPS[
            s["actions"][0]["resource"]["medicationCodeableConcept"]["coding"][0]["code"]
        ]
        for s in alt["suggestions"]
    ]
    assert groups == sorted(groups, key=["Access", "Watch"].index) and groups[0] == "Access"
    assert _cards(client, "aei-antibiotic-sign", {"patientId": EMPIRIC, "antibiotic": "MEC"}) == []
    ok = client.post(
        "/api/cds-services/aei-antibiotic-sign/feedback",
        json={"feedback": [{"card": stop[0]["uuid"], "outcome": "overridden"}]},
    )
    assert ok.json() == {"ok": True}
    log = client.get("/api/cds-services/aei-antibiotic-sign/feedback").json()["feedback"]
    assert log[0]["outcome"] == "overridden"


def test_demo_dates_come_from_the_alert_history():
    ds = get_dataset()
    dates = demo.warm_dates(ds, TODAY)
    assert dates[:2] == [TODAY, EHR_DAY] and len(dates) == len(set(dates))
    assert all(ds.start.date() <= d <= TODAY for d in dates)
    early = demo.warm_dates(ds, date(2024, 1, 1))
    assert early[0] == date(2024, 1, 1) and EHR_DAY not in early  # nothing after as-of


def test_memo_keeps_pinned_dates():
    m = Memo(2)
    ds = object()
    pinned, a, b = date(2025, 6, 27), date(2025, 1, 1), date(2025, 2, 1)
    memo.PINNED.add(pinned)
    try:
        m.put(ds, (pinned,), pinned, "keep")
        m.put(ds, (a,), a, "a")
        m.put(ds, (b,), b, "b")
        assert m.get(ds, (pinned,)) == "keep" and m.get(ds, (a,)) is None and m.get(ds, (b,)) == "b"
        other = object()  # a new dataset (after an ingest) drops the old one's results
        m.put(other, (a,), a, "new")
        assert m.get(ds, (pinned,)) is None and m.get(other, (a,)) == "new"
    finally:
        memo.PINNED.discard(pinned)


def test_trend_findings_work_before_two_years_of_data(client):
    # Before Oct 2024 there are no 12 months before the last 12: no crossings, no crash.
    early = client.get("/api/trends/findings", params={"as_of": "2024-09-19"}).json()
    assert early["crossings"] == []
    assert client.get("/api/stewardship", params={"as_of": "2024-09-19"}).status_code == 200
