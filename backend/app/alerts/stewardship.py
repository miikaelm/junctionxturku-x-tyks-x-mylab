"""Stewardship findings (ANOM-10): long-standing resistance with an owner and a status.

High resistance that has held for months is not an alert: it is on every ward and would keep the
inbox full, and nobody needs to investigate it. It does raise a question for lab / stewardship:
does the local empirical guideline still fit? A finding is one location × specimen × organism ×
antibiotic that
- is on a ward's avoid list (UX-05): a main organism of an infection ≥ the empirical-use limit over
  the last 12 months. "crossed" when the run above the limit began inside the data (the date is
  known), "standing" when it reaches back to where the data starts;
- or rises significantly over the quarters (ANOM-03) while still under the limit: "rising".

The location is the level the figure comes from (a ward, or a broader level the ward falls back
to), so a finding shared by several wards' lists is one finding. Its review status (new → under
review → guideline updated / accepted) is stored like triage, with the as-of date it was set at.
A status set before the current run above the limit began does not carry over: a finding that
dropped below and crossed again is new again.
"""

import re
from datetime import date, timedelta
from functools import lru_cache

from app.alerts.triage import TriageStore
from app.config import (
    AVOID_SINCE_STEP_DAYS,
    EMPIRICAL_THRESHOLD_PCT,
    STATE_DIR,
    STEWARDSHIP_KINDS,
    STEWARDSHIP_STATUS_LABELS,
    STEWARDSHIP_STATUSES,
    THERAPY_INFECTIONS,
)
from app.data.dataset import Dataset
from app.data.scope import Scope
from app.stats import trends
from app.stats.avoid import avoid

KIND_ORDER = list(STEWARDSHIP_KINDS)

_memo: dict[tuple, tuple[Dataset, dict]] = {}


@lru_cache(maxsize=1)
def get_stewardship_store() -> TriageStore:
    return TriageStore(STATE_DIR / "stewardship.json", STEWARDSHIP_STATUSES)


def finding_id(location: str, specimen: str, organism: str, code: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", organism.lower()).strip("-")
    return f"stewardship.{location}.{specimen}.{slug}.{code}"


def status(
    store: TriageStore, finding_key: str, kind: str, since: dict | None, as_of: date
) -> dict:
    entries = store.history(finding_key, as_of)
    if kind == "crossed" and since:
        # "since" moves in monthly steps with the as-of date: allow one step of slack.
        start = date.fromisoformat(since["date"]) - timedelta(days=AVOID_SINCE_STEP_DAYS)
        entries = [e for e in entries if e["as_of"] >= start.isoformat()]
    cur = entries[-1] if entries else None
    key = cur["status"] if cur else "new"
    return {
        "status": key,
        "label": STEWARDSHIP_STATUS_LABELS[key],
        "note": cur["note"] if cur else "",
        "as_of": cur["as_of"] if cur else None,
    }


def findings(ds: Dataset, as_of: date, store: TriageStore) -> dict:
    """Every finding as of `as_of`, with its review status; crossed first, then rising."""
    items = [
        {**f, "review": status(store, f["id"], f["kind"], f["since"], as_of)}
        for f in _collect(ds, as_of).values()
    ]
    items.sort(
        key=lambda f: (
            KIND_ORDER.index(f["kind"]),
            f["review"]["status"] != "new",
            -(f["last_12m"]["pct"] or 0),
        )
    )
    return {
        "as_of": as_of.isoformat(),
        "threshold_pct": EMPIRICAL_THRESHOLD_PCT,
        "kinds": [{"key": k, "label": v} for k, v in STEWARDSHIP_KINDS.items()],
        "statuses": [{"key": k, "label": v} for k, v in STEWARDSHIP_STATUS_LABELS.items()],
        "findings": items,
        "counts": {
            "new": sum(f["review"]["status"] == "new" and f["kind"] != "standing" for f in items),
            **{k: sum(f["kind"] == k for f in items) for k in KIND_ORDER},
        },
    }


def finding(ds: Dataset, as_of: date, store: TriageStore, fid: str) -> dict | None:
    f = _collect(ds, as_of).get(fid)
    if f is None:
        return None
    return {
        **f,
        "review": status(store, fid, f["kind"], f["since"], as_of),
        "history": store.history(fid, as_of),
    }


def attach(
    ds: Dataset, result: dict, scope: Scope, infection: str, as_of: date, store: TriageStore
) -> dict:
    """Give each flagged organism on an avoid list its finding and review status (UX-07). With
    patient filters, only flags that are also on the unfiltered list have a finding."""
    base = avoid(ds, Scope(scope.location), infection, as_of)
    known = {
        finding_id(o["location"], base["specimen"], o["organism"], a["code"])
        for a in base["avoid"]
        for o in a["organisms"]
        if o["status"] == "above"
    }
    out = {**result, "avoid": []}
    for a in result["avoid"]:
        organisms = []
        for o in a["organisms"]:
            fid = o["status"] == "above" and finding_id(
                o["location"], result["specimen"], o["organism"], a["code"]
            )
            if fid and fid in known:
                kind = "standing" if o["since"]["at_least"] else "crossed"
                o = {
                    **o,
                    "finding": {
                        "id": fid,
                        "kind": kind,
                        **status(store, fid, kind, o["since"], as_of),
                    },
                }
            organisms.append(o)
        out["avoid"].append({**a, "organisms": organisms})
    return out


def _collect(ds: Dataset, as_of: date) -> dict[str, dict]:
    key = (id(ds), as_of)
    hit = _memo.get(key)
    if hit is not None and hit[0] is ds:
        return hit[1]
    found: dict[str, dict] = {}
    for ward in ds.wards.ward_code:
        for infection, cfg in THERAPY_INFECTIONS.items():
            r = avoid(ds, Scope(ward), infection, as_of)
            for a in r["avoid"]:
                for o in a["organisms"]:
                    if o["status"] != "above":
                        continue
                    fid = finding_id(o["location"], r["specimen"], o["organism"], a["code"])
                    f = found.get(fid)
                    if f is None:
                        f = found[fid] = {
                            "id": fid,
                            "kind": "standing" if o["since"]["at_least"] else "crossed",
                            "location": o["location"],
                            "location_label": o["level_label"],
                            "level": o["level"],
                            "specimen": r["specimen"],
                            "infections": [],
                            "organism": o["organism"],
                            "antibiotic_code": a["code"],
                            "antibiotic": a["name"],
                            "reserve": a["reserve"],
                            "last_12m": _estimate(o),
                            "since": o["since"],
                            "direction": o["direction"],
                            "trend": None,
                            "wards": [],
                        }
                    if cfg["label"] not in f["infections"]:
                        f["infections"].append(cfg["label"])
                    if ward not in f["wards"]:
                        f["wards"].append(ward)

    # Significant upward trends (ANOM-03): attached to the matching finding, or a finding of their
    # own while still under the limit. The trend explorer (V6) keeps the full list.
    labels = {cfg["specimen"]: cfg["label"] for cfg in THERAPY_INFECTIONS.values()}
    for t in trends.findings(ds, as_of)["trends"]:
        if t["trend"]["direction"] != "up":
            continue
        fid = finding_id(t["location"], t["specimen"], t["organism"], t["antibiotic_code"])
        if fid in found:
            found[fid]["trend"] = t["trend"]
        elif (t["last_12m"]["pct"] or 0) < EMPIRICAL_THRESHOLD_PCT:
            found[fid] = {
                "id": fid,
                "kind": "rising",
                "location": t["location"],
                "location_label": t["location_label"],
                "level": t["level"],
                "specimen": t["specimen"],
                "infections": [labels[t["specimen"]]] if t["specimen"] in labels else [],
                "organism": t["organism"],
                "antibiotic_code": t["antibiotic_code"],
                "antibiotic": t["antibiotic"],
                "reserve": False,
                "last_12m": t["last_12m"],
                "since": None,
                "direction": "rising",
                "trend": t["trend"],
                "wards": [],
            }

    if len(_memo) >= 8:
        _memo.clear()
    _memo[key] = (ds, found)
    return found


def _estimate(o: dict) -> dict:
    return {k: o[k] for k in ("r", "n", "pct", "ci_low", "ci_high", "sufficient") if k in o}
