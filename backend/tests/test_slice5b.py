"""Slice 5b: the avoid list says why (UX-07): recent rises name the outbreak behind them, and
long-standing flags are stewardship findings with a review status (ANOM-10).

E1 (the URO ESBL outbreak) and E4 (the E. coli trimethoprim drift) of PROJECT.md §8 appear only
here, as validation cases.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.alerts import stewardship
from app.alerts.anomalies import recent_rises
from app.alerts.triage import TriageStore, get_triage_store
from app.config import (
    AVOID_SINCE_STEP_DAYS,
    EMPIRICAL_THRESHOLD_PCT,
    RISE_CAUSE_MIN_CASES,
    STEWARDSHIP_STATUSES,
)
from app.data.dataset import get_dataset
from app.data.scope import Scope
from app.main import app
from app.stats.avoid import avoid

E1_DAY = date(2025, 6, 27)
URO_TMP = "stewardship.URO.urine.escherichia-coli.TMP"


@pytest.fixture
def store(tmp_path):
    return TriageStore(tmp_path / "triage.json")


@pytest.fixture
def reviews(tmp_path):
    return TriageStore(tmp_path / "stewardship.json", STEWARDSHIP_STATUSES)


@pytest.fixture
def client(store, reviews):
    app.dependency_overrides[get_triage_store] = lambda: store
    app.dependency_overrides[stewardship.get_stewardship_store] = lambda: reviews
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_recent_rises_name_the_outbreak_they_come_from(store):
    rises = recent_rises(get_dataset(), E1_DAY, store, {"URO"}, "urine")
    cro = next(r for r in rises if r["code"] == "CRO")
    cause = cro["cause"]
    assert cause and cause["type_label"] == "Outbreak / cluster" and "URO" in cause["wards"]
    assert RISE_CAUSE_MIN_CASES <= cause["matching"] <= cause["of"] == cro["observed"]["r"]
    # A dismissed outbreak is no longer offered as the cause.
    store.add(cause["alert_id"], "dismissed", E1_DAY)
    again = recent_rises(get_dataset(), E1_DAY, store, {"URO"}, "urine")
    assert all(r["cause"] is None for r in again)


def test_findings_kinds_follow_the_data(reviews):
    ds = get_dataset()
    f = stewardship.findings(ds, E1_DAY, reviews)["findings"]
    by_id = {x["id"]: x for x in f}
    tmp = by_id[URO_TMP]  # E4 shows on URO as a crossing in spring 2025
    assert tmp["kind"] == "crossed" and tmp["since"]["date"].startswith("2025")
    assert tmp["last_12m"]["pct"] >= EMPIRICAL_THRESHOLD_PCT and "URO" in tmp["wards"]
    for x in f:
        if x["kind"] == "standing":
            assert x["since"]["at_least"]
        if x["kind"] == "rising":
            assert (
                x["last_12m"]["pct"] < EMPIRICAL_THRESHOLD_PCT and x["trend"]["direction"] == "up"
            )
    # No data after as-of: before the crossing there is no URO trimethoprim finding.
    early = stewardship.findings(ds, date(2025, 1, 15), reviews)
    assert URO_TMP not in {x["id"] for x in early["findings"] if x["kind"] != "rising"}


def test_review_status_applies_from_its_date_and_resets_on_a_new_crossing(reviews):
    ds = get_dataset()
    reviews.add(URO_TMP, "accepted", date(2024, 6, 1))  # long before this run above the limit
    f = stewardship.finding(ds, E1_DAY, reviews, URO_TMP)
    assert f["review"]["status"] == "new"
    since = date.fromisoformat(f["since"]["date"])
    reviews.add(URO_TMP, "under_review", since + timedelta(days=AVOID_SINCE_STEP_DAYS))
    assert stewardship.finding(ds, E1_DAY, reviews, URO_TMP)["review"]["status"] == "under_review"


def test_avoid_list_carries_findings_only_for_unfiltered_flags(reviews):
    ds = get_dataset()
    base = avoid(ds, Scope("URO"), "uti", E1_DAY)
    out = stewardship.attach(ds, base, Scope("URO"), "uti", E1_DAY, reviews)
    tmp = next(a for a in out["avoid"] if a["code"] == "TMP")
    found = [o["finding"] for o in tmp["organisms"] if "finding" in o]
    assert found and found[0]["id"] == URO_TMP and found[0]["kind"] == "crossed"
    women = Scope("URO", sex="F")
    narrow = stewardship.attach(ds, avoid(ds, women, "uti", E1_DAY), women, "uti", E1_DAY, reviews)
    known = {o["finding"]["id"] for a in out["avoid"] for o in a["organisms"] if "finding" in o}
    for a in narrow["avoid"]:
        for o in a["organisms"]:
            assert "finding" not in o or o["finding"]["id"] in known


def test_stewardship_endpoints(client):
    day = E1_DAY.isoformat()
    lst = client.get("/api/stewardship", params={"as_of": day}).json()
    assert lst["counts"]["crossed"] >= 1 and lst["findings"][0]["kind"] == "crossed"
    r = client.post(
        f"/api/stewardship/{URO_TMP}/review", json={"status": "guideline_updated", "as_of": day}
    )
    assert r.status_code == 200
    one = client.get(f"/api/stewardship/{URO_TMP}", params={"as_of": day}).json()
    assert one["review"]["status"] == "guideline_updated" and len(one["history"]) == 1
    assert (
        client.get("/api/stewardship/stewardship.nowhere", params={"as_of": day}).status_code == 404
    )
    assert (
        client.post(
            "/api/stewardship/stewardship.nowhere/review", json={"status": "accepted"}
        ).status_code
        == 404
    )
    avoid_uro = client.get(
        "/api/avoid", params={"location": "URO", "infection": "uti", "as_of": day}
    ).json()
    tmp = next(a for a in avoid_uro["avoid"] if a["code"] == "TMP")
    assert any(o.get("finding", {}).get("status") == "guideline_updated" for o in tmp["organisms"])
    assert all(r["rise"]["cause"] for r in avoid_uro["recent_rise"])


# ---------- Subgroup exceptions (UX-10) ----------

TODAY = date(2026, 9, 27)


def test_subgroup_exceptions_only_when_they_change_the_answer():
    from app.config import SUBGROUP_MIN_N

    ds = get_dataset()
    for ward in ("URO", "MED-A", "MED-B", "ED"):
        r = avoid(ds, Scope(ward), "uti", TODAY)
        for key, overall in (("avoid", "above"), ("some_patients", "below")):
            for a in r[key]:
                for g in a["subgroups"]:
                    # On the other side of the limit from the whole, with enough data on both sides.
                    assert g["side"] != overall and g["n"] >= SUBGROUP_MIN_N
                    assert g["rest"]["n"] >= SUBGROUP_MIN_N and g["q_value"] < 0.05
                    assert (g["pct"] >= EMPIRICAL_THRESHOLD_PCT) == (g["side"] == "above")
        assert all(a["subgroups"] for a in r["some_patients"])
        assert not any(a["subgroups"] for a in r["no_warning"])
    # Urine E. coli: ciprofloxacin is fine overall on URO but not for men.
    uro = avoid(ds, Scope("URO"), "uti", TODAY)
    cip = next(a for a in uro["some_patients"] if a["code"] == "CIP")
    men = next(g for g in cip["subgroups"] if g["dimension"] == "sex")
    assert men["label"] == "Men" and men["pct"] > 2 * men["rest"]["pct"]
    # A filtered dimension is not split again.
    only_men = avoid(ds, Scope("URO", sex="M"), "uti", TODAY)
    groups = [g for k in ("avoid", "some_patients") for a in only_men[k] for g in a["subgroups"]]
    assert all(g["dimension"] != "sex" for g in groups)


def test_order_check_uses_the_patients_group(client):
    def first(ctx):
        return client.post(
            "/api/cds-services/aei-antibiotic-choice",
            params={"as_of": TODAY.isoformat()},
            json={"hook": "order-select", "context": ctx},
        ).json()["cards"][0]

    base = {"ward": "URO", "infection": "uti", "antibiotic": "CIP"}
    unknown = first(base)
    assert unknown["indicator"] == "warning" and "high in men" in unknown["summary"]
    assert first({**base, "sex": "F", "age": 40})["indicator"] == "info"
    assert first({**base, "sex": "M", "age": 70})["summary"].startswith("Avoid ciprofloxacin")
