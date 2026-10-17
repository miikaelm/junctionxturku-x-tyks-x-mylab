"""Slice 4: carrier registry, carrier alerts, profile similarity, multi-ward signal, spread,
therapy helper, CDS Hooks services, subscriptions and webhooks.

As before, the planted events of PROJECT.md §8 appear only here, as a validation set. The
multi-ward test plants its own spread (the organizers' data has none) through the ingest path.
"""

from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.alerts import engine, notify
from app.alerts.detail import episode_detail
from app.alerts.triage import TriageStore, get_triage_store
from app.data.dataset import get_dataset
from app.data.loader import get_tables
from app.data.scope import Scope
from app.data.store import DataStore, batch_from_records
from app.detectors.carrier import reappearances
from app.detectors.multi_ward import detect_multi_ward
from app.main import app
from app.patients.registry import carriers
from app.stats.therapy import therapy

TODAY = date(2026, 9, 27)


@pytest.fixture
def store(tmp_path):
    return TriageStore(tmp_path / "triage.json")


@pytest.fixture
def subs(tmp_path, monkeypatch):
    s = notify.SubscriptionStore(tmp_path / "subscriptions.json")
    monkeypatch.setattr(notify, "get_subscription_store", lambda: s)
    return s


@pytest.fixture
def client(store, subs):
    app.dependency_overrides[get_triage_store] = lambda: store
    app.dependency_overrides[notify.get_subscription_store] = lambda: subs
    yield TestClient(app)
    app.dependency_overrides.clear()


def _episode(type_, ward, year=None):
    eps = engine.timeline(get_dataset(), TODAY)
    return next(
        e for e in eps if e.type == type_ and e.ward == ward and (not year or e.first.year == year)
    )


def test_carrier_registry_matches_the_data_and_uses_no_future_data():
    ds = get_dataset()
    reg = carriers(ds, TODAY)
    assert reg.groupby("phenotype").patient_id.nunique().to_dict() == {
        "CPE": 12,
        "ESBL": 491,
        "MRSA": 110,
        "VRE": 5,
    }
    early = carriers(ds, date(2025, 1, 1))
    assert early.first_positive.max() <= pd.Timestamp("2025-01-01")
    assert len(early) < len(reg)


def test_carrier_alerts_follow_the_rule(store):
    ds = get_dataset()
    ev = reappearances(ds, TODAY)
    assert ev.institution.eq("hospital").all()  # health-centre visits don't alert
    reg = carriers(ds, TODAY).groupby("patient_id").first_positive.min()
    assert (ev.sample_date > ev.patient_id.map(reg)).all()  # flagged before the sample
    # No alert when the patient was sampled on the same ward within the revisit window.
    assert (ev.days_since_here.isna() | (ev.days_since_here > 30)).all()
    # About one per hospital ward per week: routine, so out of the badge and the replay list.
    assert 1000 < len(ev) < 1700
    counts = engine.counts(engine.alerts_at(ds, TODAY, store))
    assert counts["routine"] > 0
    assert not any(e["type"] == "carrier" for e in engine.replay_events(ds, TODAY, store))


def test_profile_similarity_tells_strains_apart():
    ds = get_dataset()
    e1 = episode_detail(ds, _episode("cluster", "URO", 2025), TODAY)["similarity"]
    assert e1["verdict"] == "single_strain" and e1["matching"] >= 0.8 * e1["cases"]
    assert e1["background"]["share"] < 0.3
    e2 = episode_detail(ds, _episode("cluster", "ICU"), TODAY)["similarity"]
    assert e2["verdict"] == "single_strain" and e2["dominant"]["key"] == "CLI,FOX"
    # The small MED-A cluster (not in the answer key) has mixed profiles.
    med = episode_detail(ds, _episode("cluster", "MED-A"), TODAY)["similarity"]
    assert med["verdict"] != "single_strain"


def test_followup_lists_where_cluster_patients_went_next():
    ds = get_dataset()
    d = episode_detail(ds, _episode("cluster", "URO", 2025), TODAY)
    f = d["followup"]
    assert f["case_patients"] >= 20 and f["wards"]
    for p in f["patients"]:
        assert all(s["ward"] != p["case_ward"] and s["date"] > p["case_date"] for s in p["seen"])


def test_multi_ward_signal_is_quiet_on_the_real_data():
    firings = detect_multi_ward(get_dataset(), TODAY)
    assert len(firings) <= 3
    for f in firings:
        assert len(f.evidence["wards"]) >= 2


def _planted_spread(tables, wards=("GER", "MED-B"), start=date(2026, 9, 14)):
    """Three ESBL K. pneumoniae with one uncommon profile on each of two wards in 10 days."""
    resistant = {"AMP", "TZP", "CXM", "CRO", "CIP"}
    panel = ["AMP", "MEC", "TZP", "CXM", "CRO", "MEM", "CIP", "TMP", "NIT"]
    abx = tables.antibiotics.set_index("antibiotic_code")
    w = tables.wards.set_index("ward_code")
    patients, cultures, isolates, ast = [], [], [], []
    for i in range(6):
        ward = wards[i % 2]
        day = start + timedelta(days=i * 2)
        pid, cid = f"PX{i:05d}", f"CX{i:07d}"
        iid = f"{cid}-1"
        patients.append({"patient_id": pid, "sex": "F", "birth_year": 1940, "home_area": "North"})
        cultures.append(
            {
                "culture_id": cid,
                "patient_id": pid,
                "age_years": 86,
                "sample_date": day.isoformat(),
                "iso_year": day.isocalendar()[0],
                "iso_week": day.isocalendar()[1],
                "ward_code": ward,
                "ward_fi": w.ward_fi[ward],
                "ward_en": w.ward_en[ward],
                "ward_type": w.ward_type[ward],
                "institution": w.institution[ward],
                "admission_date": (day - timedelta(days=5)).isoformat(),
                "specimen": "urine",
                "specimen_fi": "virtsa",
                "result": "positive",
                "n_isolates": 1,
            }
        )
        isolates.append(
            {
                "isolate_id": iid,
                "culture_id": cid,
                "isolate_no": 1,
                "organism": "Klebsiella pneumoniae",
                "quantity": ">=10^5",
                "esbl": 1,
                "mrsa": 0,
                "vre": 0,
                "cpe": 0,
            }
        )
        for code in panel:
            ast.append(
                {
                    "isolate_id": iid,
                    "culture_id": cid,
                    "organism": "Klebsiella pneumoniae",
                    "antibiotic": abx.antibiotic[code],
                    "antibiotic_code": code,
                    "antibiotic_fi": abx.antibiotic_fi[code],
                    "result": "R" if code in resistant else "S",
                    "guideline": "EUCAST 2026",
                }
            )
    return {"patients": patients, "cultures": cultures, "isolates": isolates, "susceptibility": ast}


def test_multi_ward_signal_finds_a_planted_spread():
    held = DataStore(get_tables())
    held.ingest(batch_from_records(_planted_spread(held.tables), held.tables), source="test")
    firings = detect_multi_ward(held.dataset, TODAY)
    hits = [f for f in firings if set(f.evidence["wards"]) >= {"GER", "MED-B"}]
    assert hits, [f.title for f in firings]
    assert hits[0].evidence["phenotype"] == "ESBL" and hits[0].day <= date(2026, 9, 24)


def test_therapy_coverage_is_the_weighted_sum():
    ds = get_dataset()
    r = therapy(ds, Scope("URO"), "uti", TODAY)
    assert r["used"]["location"] == "URO" and r["isolates"] >= 30
    for item in r["ranked"] + r["unranked"]:
        expected = sum(
            p["share"] * (p["susceptible_pct"] or 0)
            for p in item["organisms"]
            if p["status"] != "intrinsic"
        )
        assert item["coverage_pct"] == pytest.approx(expected, abs=1.0)
        assert (
            item["ci_low"] <= item["coverage_pct"] + 1
            and item["coverage_pct"] - 1 <= item["ci_high"]
        )
        intrinsic = [p for p in item["organisms"] if p["status"] == "intrinsic"]
        assert all(p["susceptible_pct"] == 0 for p in intrinsic)
    assert "FOX" not in {x["code"] for x in r["ranked"] + r["unranked"]}  # a screen, not a drug
    # Wound S. aureus: β-lactams inferred from the cefoxitin screen.
    w = therapy(ds, Scope("SURG"), "wound", TODAY)
    cxm = next(x for x in w["ranked"] if x["code"] == "CXM")
    sa = next(p for p in cxm["organisms"] if p["organism"] == "Staphylococcus aureus")
    assert sa["status"] == "inferred" and sa["inferred_from"] == "FOX"
    # Too few ICU blood isolates in men 18–64: falls back to a broader level.
    small = therapy(ds, Scope("ICU", sex="M", age_band="18-64"), "bloodstream", TODAY)
    assert small["used"]["fell_back"]


def test_cds_hooks_services(client):
    services = client.get("/api/cds-services").json()["services"]
    assert {s["hook"] for s in services} == {"order-select", "patient-view"}
    cards = client.post(
        "/api/cds-services/aei-antibiotic-choice",
        params={"as_of": "2025-06-20"},
        json={
            "hook": "order-select",
            "context": {"ward": "URO", "infection": "uti", "antibiotic": "CIP"},
        },
    ).json()["cards"]
    summaries = [c["summary"] for c in cards]
    assert summaries[0].startswith("Ciprofloxacin: covers")
    assert any("ESBL cluster" in s for s in summaries)  # the E1 outbreak, active that day
    assert all(c["indicator"] in ("info", "warning", "critical") and c["source"] for c in cards)

    pid = carriers(get_dataset(), TODAY).patient_id.iloc[0]
    view = client.post(
        "/api/cds-services/aei-patient-context",
        json={"hook": "patient-view", "context": {"patientId": pid}},
    ).json()["cards"]
    assert (
        view and "carrier" in view[0]["summary"] and view[0]["indicator"] in ("warning", "critical")
    )
    nobody = client.post(
        "/api/cds-services/aei-patient-context",
        json={"hook": "patient-view", "context": {"patientId": "P_NOBODY"}},
    ).json()
    assert nobody == {"cards": []}


def test_subscriptions_route_alerts_by_role_and_ward(client):
    msgs = client.get("/api/notifications", params={"as_of": "2025-06-08", "days": 3}).json()[
        "messages"
    ]
    ic = [m for m in msgs if m["subscription"] == "infection-control"]
    assert any("cluster" in m["subject"].lower() and "URO" in m["subject"] for m in ic)
    assert not any("carrier" in m["subject"].lower() for m in ic)  # routine: not for IC email
    icu = [m for m in msgs if m["subscription"] == "icu-on-call"]
    assert all("ICU" in m["subject"] for m in icu)
    hook = [m for m in msgs if m["channel"] == "webhook"]
    assert all(m["content_type"] == "application/json" for m in hook)


def test_ingest_delivers_webhooks(subs, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "_post", lambda entry, url, payload: sent.append((url, payload)))
    monkeypatch.setattr(notify.threading, "Thread", _Inline)
    held = DataStore(get_tables(), date(2026, 9, 21))
    engine.timeline(held.dataset, held.today())
    held.receive_held_back(1)  # 2026-09-21: the CPE case on MED-A
    events = [p["event"] for _, p in sent]
    assert "alert.new" in events
    cpe = [p for _, p in sent if p.get("alert", {}).get("type") == "sentinel"]
    assert cpe and "MED-A" in cpe[0]["alert"]["wards"]
    assert any(d["channel"] == "email" and d["status"] == "simulated" for d in notify.DELIVERIES)


class _Inline:
    """threading.Thread stand-in that runs the target at once (deterministic tests)."""

    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)
