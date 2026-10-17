"""Anomalies for the exceptions-first drill-down (UX-02/03): Varha → institution → ward.

An anomaly is something that changed or needs action:
- an active alert that is not routine (known carriers sampled are counted apart) and not
  dismissed in triage;
- a feed problem: the ward's data is delayed or stale (VIEW-12) or a data-gap alert is active.
  A ward has at most one feed anomaly, however both tests see it.
Chronic high resistance is not an anomaly; it belongs in the ward's avoid list (UX-05).

Higher levels never get an overall resistance percentage: they count their children's
anomalies. One payload covers every level, so drilling down needs no new request.
"""

from datetime import date

from app.alerts import engine
from app.alerts.triage import TriageStore
from app.config import (
    SEVERITY_ORDER,
    VARHA_FULL,
    VARHA_HOSPITAL,
    VARHA_LABEL,
    VARHA_PLACEHOLDERS,
)
from app.data.dataset import Dataset
from app.data.freshness import ward_freshness

FEED_TYPE = "data_gap"


def anomalies(ds: Dataset, as_of: date, store: TriageStore) -> dict:
    alerts = [
        a
        for a in engine.alerts_at(ds, as_of, store)
        if a["state"] == "active" and a["triage"]["status"] != "dismissed"
    ]
    fresh = {f["ward_code"]: f for f in ward_freshness(ds, as_of)}

    wards = {}
    for w in ds.wards.to_dict("records"):
        code = w["ward_code"]
        here = [a for a in alerts if code in a["wards"]]
        signals = [_brief(a) for a in here if not a["routine"] and a["type"] != FEED_TYPE]
        gap = next((a for a in here if a["type"] == FEED_TYPE), None)
        f = fresh[code]
        feed = None
        if gap is not None or f["status"] in ("delayed", "stale", "no_data"):
            feed = {
                "status": f["status"] if f["status"] != "ok" else "gap",
                "last_sample": f["last_sample"],
                "days_since_last": f["days_since_last"],
                "alert": _brief(gap) if gap else None,
            }
        wards[code] = {
            "ward_code": code,
            "label": w["ward_en"],
            "institution": w["institution"],
            "alerts": signals,
            "feed": feed,
            "carriers": sum(a["routine"] for a in here),
            "anomalies": len(signals) + (feed is not None),
            "new": sum(a["triage"] == "new" for a in signals),
            "worst": _worst(signals, feed),
        }

    institutions = []
    hospital = [c for c, w in wards.items() if w["institution"] == "hospital"]
    if hospital:
        institutions.append(
            _institution(
                VARHA_HOSPITAL["key"],
                VARHA_HOSPITAL["label"],
                VARHA_HOSPITAL["full"],
                "hospital",
                hospital,
                wards,
            )
        )
    for code, w in wards.items():
        if w["institution"] == "primary_care":
            institutions.append(
                _institution(code, w["label"], "Health centre", "health_centre", [code], wards)
            )

    return {
        "as_of": as_of.isoformat(),
        "varha": {
            "label": VARHA_LABEL,
            "full": VARHA_FULL,
            **_totals(list(wards.values())),
        },
        "institutions": institutions,
        "placeholders": VARHA_PLACEHOLDERS,
        "wards": wards,
        "definition": (
            "Anomaly = an active alert (not routine, not dismissed) or a feed problem (data delayed, "
            "stale or a data gap). Long-standing high resistance is not counted: it is in each "
            "ward's avoid list."
        ),
    }


def _brief(a: dict) -> dict:
    keys = (
        "id",
        "type",
        "type_label",
        "severity",
        "title",
        "wards",
        "first_seen",
        "last_seen",
        "onset",
    )
    return {**{k: a[k] for k in keys}, "triage": a["triage"]["status"]}


def _worst(signals: list[dict], feed: dict | None) -> str | None:
    sev = [a["severity"] for a in signals] + (["medium"] if feed else [])
    return min(sev, key=SEVERITY_ORDER.index) if sev else None


def _totals(wards: list[dict]) -> dict:
    """Counts over a set of wards; an alert on several of them counts once."""
    ids = {a["id"]: a for w in wards for a in w["alerts"]}
    feed = sum(w["feed"] is not None for w in wards)
    worst = [w["worst"] for w in wards if w["worst"]]
    return {
        "anomalies": len(ids) + feed,
        "alerts": len(ids),
        "feed_problems": feed,
        "new": sum(a["triage"] == "new" for a in ids.values()),
        "by_severity": {
            s: sum(a["severity"] == s for a in ids.values())
            for s in SEVERITY_ORDER
            if any(a["severity"] == s for a in ids.values())
        },
        "worst": min(worst, key=SEVERITY_ORDER.index) if worst else None,
        "calm": [w["ward_code"] for w in wards if w["anomalies"] == 0],
        "carriers": sum(w["carriers"] for w in wards),
    }


def _institution(key: str, label: str, full: str, kind: str, codes: list[str], wards: dict) -> dict:
    members = [wards[c] for c in codes]
    return {
        "key": key,
        "label": label,
        "full": full,
        "kind": kind,
        "wards": codes,
        **_totals(members),
    }


def recent_rises(
    ds: Dataset, as_of: date, store: TriageStore, wards: set[str], specimen: str
) -> list[dict]:
    """Active resistance-shift alerts on these wards for this specimen, one entry per agent: the
    short-term rise the 12-month avoid list can't show yet (UX-05)."""
    out = {}
    for a in engine.alerts_at(ds, as_of, store, wards=wards, types={"rate_shift"}):
        ev = a["evidence"]
        if a["triage"]["status"] == "dismissed" or ev.get("specimen") != specimen:
            continue
        for s in ev.get("shifts") or [ev]:
            code = s["antibiotic_code"]
            if code in out:
                continue
            out[code] = {
                "code": code,
                "organism": ev["organism"],
                "observed": s["observed"],
                "expected": s["expected"],
                "window": ev["window"],
                "since": a["first_seen"],
                "alert_id": a["id"],
                "ward": a["ward"],
            }
    return list(out.values())
