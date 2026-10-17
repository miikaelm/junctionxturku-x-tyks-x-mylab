"""Slice 5: the exceptions-first views' data: anomalies per ward / institution / Varha (UX-02/03)
and the clinician's "what not to use" list (UX-05)."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.alerts.anomalies import anomalies
from app.alerts.triage import TriageStore, get_triage_store
from app.config import EMPIRICAL_THRESHOLD_PCT, MIN_ISOLATES_FOR_PERCENT
from app.data.dataset import get_dataset
from app.data.first_isolate import first_isolates
from app.data.scope import Scope
from app.main import app
from app.stats.avoid import avoid

TODAY = date(2026, 9, 27)
E1_DAY = date(2025, 6, 20)  # the URO ESBL outbreak (PROJECT.md §8) is active


@pytest.fixture
def store(tmp_path):
    return TriageStore(tmp_path / "triage.json")


@pytest.fixture
def client(store):
    app.dependency_overrides[get_triage_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


def _rate(ds, location, organism, code, end):
    iso = Scope(location, "urine").apply(ds.isolates)
    start = end - timedelta(days=364)
    iso = first_isolates(iso[iso.sample_date.between(str(start), str(end))])
    iso = iso[iso.organism.eq(organism)]
    ast = ds.ast[ds.ast.isolate_id.isin(iso.isolate_id) & ds.ast.antibiotic_code.eq(code)]
    return 100 * ast.resistant.mean(), len(ast)


def test_avoid_flags_only_resistance_at_or_above_the_limit():
    ds = get_dataset()
    r = avoid(ds, Scope("URO"), "uti", TODAY)
    assert {"TMP", "AMP"} <= {a["code"] for a in r["avoid"]}
    for a in r["avoid"]:
        above = [o for o in a["organisms"] if o["status"] == "above"]
        assert above and all(o["pct"] >= EMPIRICAL_THRESHOLD_PCT for o in above)
        assert all(o["n"] >= MIN_ISOLATES_FOR_PERCENT for o in above)
        assert a["since"] <= TODAY.isoformat()
    for a in r["no_warning"]:
        assert all(o["pct"] < EMPIRICAL_THRESHOLD_PCT for o in a["organisms"] if "pct" in o)
    # Vancomycin and clindamycin don't act on E. coli: not suited, never "no warning"
    assert {"VAN", "CLI"} <= {a["code"] for a in r["not_suited"]}
    # The cefoxitin screen is not a treatment
    every = r["avoid"] + r["no_warning"] + r["not_suited"] + r["unknown"]
    assert "FOX" not in {a["code"] for a in every}


def test_avoid_since_is_the_start_of_the_run_above_the_limit():
    ds = get_dataset()
    r = avoid(ds, Scope("URO"), "uti", TODAY)
    tmp = next(a for a in r["avoid"] if a["code"] == "TMP")
    ecoli = next(o for o in tmp["organisms"] if o["organism"] == "Escherichia coli")
    assert not ecoli["since"]["at_least"]
    since = date.fromisoformat(ecoli["since"]["date"])
    assert _rate(ds, "URO", "Escherichia coli", "TMP", since)[0] >= EMPIRICAL_THRESHOLD_PCT
    assert _rate(ds, "URO", "Escherichia coli", "TMP", since - timedelta(days=30))[0] < 20


def test_avoid_uses_no_data_after_as_of():
    ds = get_dataset()
    r = avoid(ds, Scope("URO"), "uti", E1_DAY)
    assert r["window"]["end"] == E1_DAY.isoformat()
    amp = next(a for a in r["avoid"] if a["code"] == "AMP")
    ecoli = next(o for o in amp["organisms"] if o["organism"] == "Escherichia coli")
    pct, n = _rate(ds, "URO", "Escherichia coli", "AMP", E1_DAY)
    assert (ecoli["n"], ecoli["pct"]) == (n, round(pct, 1))


def test_anomalies_count_alerts_and_feed_problems_not_chronic_resistance(store):
    ds = get_dataset()
    a = anomalies(ds, E1_DAY, store)
    uro = a["wards"]["URO"]
    assert any(x["type"] == "cluster" and "ESBL" in x["title"] for x in uro["alerts"])
    assert all(
        x["type"] not in ("carrier", "data_gap") for w in a["wards"].values() for x in w["alerts"]
    )
    tyks = next(i for i in a["institutions"] if i["key"] == "tyks")
    assert set(tyks["wards"]) == set(ds.wards.ward_code[ds.wards.institution.eq("hospital")])
    ids = {x["id"] for c in tyks["wards"] for x in a["wards"][c]["alerts"]}
    feed = sum(a["wards"][c]["feed"] is not None for c in tyks["wards"])
    assert tyks["anomalies"] == len(ids) + feed
    assert "URO" not in tyks["calm"] and set(tyks["calm"]) | {"URO"} <= set(tyks["wards"])
    # Each health centre is an institution of its own; nothing has an overall resistance %
    assert {i["key"] for i in a["institutions"]} == {"tyks", "PHC-N", "PHC-S"}
    assert "pct" not in a["varha"] and all("pct" not in i for i in a["institutions"])


def test_dismissed_alerts_are_not_anomalies(store):
    ds = get_dataset()
    before = anomalies(ds, E1_DAY, store)["wards"]["URO"]
    cluster = next(x for x in before["alerts"] if x["type"] == "cluster")
    store.add(cluster["id"], "dismissed", E1_DAY)
    after = anomalies(ds, E1_DAY, store)["wards"]["URO"]
    assert cluster["id"] not in {x["id"] for x in after["alerts"]}
    assert after["anomalies"] == before["anomalies"] - 1


def test_endpoints(client):
    r = client.get("/api/anomalies", params={"as_of": E1_DAY.isoformat()})
    assert r.status_code == 200 and r.json()["varha"]["anomalies"] >= 1
    r = client.get("/api/avoid", params={"location": "URO", "infection": "uti"})
    assert r.status_code == 200 and r.json()["avoid"]
    assert client.get("/api/avoid", params={"location": "NOPE"}).status_code == 422
    meta = client.get("/api/meta").json()
    assert meta["varha"]["hospital"]["label"] == "Tyks"
    assert all("action" in t for t in meta["alert_types"])


def test_recent_rises_join_the_avoid_list_and_the_order_check(client):
    # During the URO ESBL outbreak the 12-month ceftriaxone figure is still low, but a resistance
    # shift is active: the avoid list and the order-select hook must both say so.
    r = client.get(
        "/api/avoid", params={"location": "URO", "infection": "uti", "as_of": E1_DAY.isoformat()}
    ).json()
    risen = {x["code"]: x for x in r["recent_rise"]}
    assert "CRO" in risen and risen["CRO"]["rise"]["observed"]["pct"] >= EMPIRICAL_THRESHOLD_PCT
    assert "CRO" not in {x["code"] for x in r["no_warning"]}
    assert not set(risen) & {x["code"] for x in r["avoid"]}
    cards = client.post(
        "/api/cds-services/aei-antibiotic-choice",
        params={"as_of": E1_DAY.isoformat()},
        json={
            "hook": "order-select",
            "context": {"ward": "URO", "infection": "uti", "antibiotic": "CRO"},
        },
    ).json()["cards"]
    assert cards[0]["indicator"] == "warning" and "risen" in cards[0]["summary"]
