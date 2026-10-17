"""What not to use (UX-05): antibiotics a clinician should avoid for an infection on this ward.

Prescribers usually know what they want to give; they need to know when there is a local reason
not to. An agent is flagged when one of the infection's main organisms (at least
AVOID_MIN_ORGANISM_SHARE of first isolates of its specimen in the last 12 months) is resistant
at or above the empirical-use limit (EMPIRICAL_THRESHOLD_PCT). Each organism × agent uses the
most specific location level with n ≥ 30 (STAT-04), as the antibiogram does.

Each flag says since when (the 12-month rate recomputed at monthly steps back from the as-of
date: the start of the unbroken run above the limit) and the direction (last 12 months vs the
12 months before). Intrinsic resistance is noted, never flagged (it is not local news), and
agents never tested on a main organism say so. Agents that most of the infection's organisms
resist intrinsically (vancomycin for a UTI) are listed as not suited rather than "no warning".
"""

from dataclasses import replace
from datetime import date, timedelta

import pandas as pd
from scipy.stats import fisher_exact

from app.config import (
    ANNUAL_WINDOW_DAYS,
    AVOID_DIRECTION_ALPHA,
    AVOID_DIRECTION_MIN_PP,
    AVOID_MIN_ORGANISM_SHARE,
    AVOID_NOT_SUITED_SHARE,
    AVOID_SINCE_MAX_STEPS,
    AVOID_SINCE_STEP_DAYS,
    EMPIRICAL_THRESHOLD_PCT,
    MIN_ISOLATES_FOR_PERCENT,
    THERAPY_EXCLUDE,
    THERAPY_INFECTIONS,
    THERAPY_RESERVE,
)
from app.data import windows
from app.data.dataset import Dataset
from app.data.first_isolate import first_isolates
from app.data.intrinsic import is_intrinsic
from app.data.scope import Scope
from app.stats.antibiogram import reported_antibiotics
from app.stats.proportions import estimate

_memo: dict[tuple, tuple[Dataset, dict]] = {}


def avoid(ds: Dataset, scope: Scope, infection: str, as_of: date) -> dict:
    key = (id(ds), scope, infection, as_of)
    hit = _memo.get(key)
    if hit is not None and hit[0] is ds:
        return hit[1]
    out = _avoid(ds, scope, infection, as_of)
    if len(_memo) >= 64:
        _memo.clear()
    _memo[key] = (ds, out)
    return out


def _avoid(ds: Dataset, scope: Scope, infection: str, as_of: date) -> dict:
    specimen = THERAPY_INFECTIONS[infection]["specimen"]
    scope = replace(scope, specimen=specimen)
    chain = scope.chain(ds.wards)
    window = windows.annual(as_of)
    firsts = [_firsts(ds, s, window.start, as_of) for s in chain]

    # Main organisms: shares at the most specific level with enough isolates.
    used = next(
        (i for i, f in enumerate(firsts) if len(f) >= MIN_ISOLATES_FOR_PERCENT), len(chain) - 1
    )
    shares = firsts[used].organism.value_counts(normalize=True)
    main = [o for o, s in shares.items() if s >= AVOID_MIN_ORGANISM_SHARE]

    abx = reported_antibiotics(ds, specimen)
    abx = abx[~abx.antibiotic_code.isin(THERAPY_EXCLUDE)]
    counts = [_counts(ds, f) for f in firsts]
    prev_end = window.start - timedelta(days=1)
    prev = [
        _counts(ds, _firsts(ds, s, prev_end - timedelta(days=ANNUAL_WINDOW_DAYS - 1), prev_end))
        for s in chain
    ]

    flagged, clear, not_suited, unknown = [], [], [], []
    for a in abx.to_dict("records"):
        code = a["antibiotic_code"]
        organisms = [
            _organism(ds, chain, counts, prev, org, float(shares[org]), code, as_of) for org in main
        ]
        item = {
            "code": code,
            "name": a["antibiotic"],
            "class": a["class"],
            "reserve": code in THERAPY_RESERVE,
            "organisms": organisms,
        }
        above = [o for o in organisms if o["status"] == "above"]
        if above:
            item["affected_share"] = round(sum(o["share"] for o in above), 3)
            item["worst_pct"] = max(o["pct"] for o in above)
            item["since"] = min(o["since"]["date"] for o in above)
            item["since_at_least"] = any(
                o["since"]["at_least"] for o in above if o["since"]["date"] == item["since"]
            )
            flagged.append(item)
        elif (
            sum(o["share"] for o in organisms if o["status"] == "intrinsic")
            >= AVOID_NOT_SUITED_SHARE
        ):
            not_suited.append(item)
        elif any(o["status"] == "below" for o in organisms):
            clear.append(item)
        else:
            unknown.append(item)

    flagged.sort(key=lambda x: (-x["affected_share"], -x["worst_pct"]))
    return {
        "as_of": as_of.isoformat(),
        "infection": infection,
        "infection_label": THERAPY_INFECTIONS[infection]["label"],
        "specimen": specimen,
        "scope": scope.to_dict(ds.wards),
        "window": window.to_dict(),
        "isolates": len(firsts[used]),
        "organisms_from": {
            "level": chain[used].level(ds.wards),
            "label": chain[used].label(ds.wards),
            "fell_back": used > 0,
        },
        "main_organisms": [{"organism": o, "share": round(float(shares[o]), 3)} for o in main],
        "threshold_pct": EMPIRICAL_THRESHOLD_PCT,
        "avoid": flagged,
        "no_warning": clear,
        "not_suited": not_suited,
        "unknown": unknown,
        "method": (
            f"Flagged when a main organism (≥ {round(100 * AVOID_MIN_ORGANISM_SHARE)} % of first "
            f"isolates) is ≥ {EMPIRICAL_THRESHOLD_PCT:g} % resistant over the last 12 months, "
            f"n ≥ {MIN_ISOLATES_FOR_PERCENT}, using a broader location when there are too few here."
        ),
    }


def _counts(ds: Dataset, firsts: pd.DataFrame) -> pd.DataFrame:
    ast = ds.ast[ds.ast.isolate_id.isin(firsts.isolate_id)]
    return ast.groupby(["organism", "antibiotic_code"]).resistant.agg(n="size", r="sum")


def _organism(ds, chain, counts, prev, org: str, share: float, code: str, as_of: date) -> dict:
    entry = {"organism": org, "share": round(share, 3)}
    if is_intrinsic(org, code):
        return {**entry, "status": "intrinsic"}
    if (org, code) not in ds.tested_pairs:
        return {**entry, "status": "not_tested"}
    key = (org, code)
    level = next(
        (
            i
            for i, c in enumerate(counts)
            if key in c.index and c.n[key] >= MIN_ISOLATES_FOR_PERCENT
        ),
        None,
    )
    if level is None:
        return {**entry, "status": "too_few"}
    est = estimate(int(counts[level].r[key]), int(counts[level].n[key]))
    above = est["pct"] >= EMPIRICAL_THRESHOLD_PCT
    row = {
        **entry,
        "status": "above" if above else "below",
        "location": chain[level].location,
        "level": chain[level].level(ds.wards),
        "level_label": chain[level].label(ds.wards),
        "fell_back": level > 0,
        **est,
        "direction": _direction(est, prev[level], key),
    }
    if above:
        row["since"] = _since(ds, chain[level], org, code, as_of)
    return row


def _firsts(ds: Dataset, scope: Scope, start: date, end: date) -> pd.DataFrame:
    iso = scope.apply(ds.isolates)
    iso = iso[iso.sample_date.between(pd.Timestamp(start), pd.Timestamp(end))]
    return first_isolates(iso)


def _since(ds: Dataset, scope: Scope, org: str, code: str, as_of: date) -> dict:
    """Start of the unbroken run of monthly 12-month rates at or above the limit, up to as_of.
    `at_least` when the run reaches back to where the data (or n ≥ 30) runs out."""
    iso = scope.apply(ds.isolates)
    iso = iso[iso.organism.eq(org)]
    ast = ds.ast[ds.ast.antibiotic_code.eq(code)][["isolate_id", "resistant"]]
    since = as_of
    for k in range(1, AVOID_SINCE_MAX_STEPS + 1):
        end = as_of - timedelta(days=k * AVOID_SINCE_STEP_DAYS)
        start = end - timedelta(days=ANNUAL_WINDOW_DAYS - 1)
        if start < ds.start.date():
            break
        f = first_isolates(iso[iso.sample_date.between(pd.Timestamp(start), pd.Timestamp(end))])
        a = f[["isolate_id"]].merge(ast, on="isolate_id")
        if len(a) < MIN_ISOLATES_FOR_PERCENT:
            break
        if 100 * a.resistant.sum() / len(a) < EMPIRICAL_THRESHOLD_PCT:
            return {"date": since.isoformat(), "at_least": False}
        since = end
    return {"date": since.isoformat(), "at_least": True}


def _direction(last: dict, prev_counts: pd.DataFrame, key: tuple[str, str]) -> str | None:
    """rising / easing / stable: last 12 months vs the 12 months before; None without a baseline."""
    if key not in prev_counts.index:
        return None
    prev = estimate(int(prev_counts.r[key]), int(prev_counts.n[key]))
    if not prev["sufficient"]:
        return None
    diff = last["pct"] - prev["pct"]
    table = [[last["r"], last["n"] - last["r"]], [prev["r"], prev["n"] - prev["r"]]]
    if abs(diff) < AVOID_DIRECTION_MIN_PP or fisher_exact(table)[1] >= AVOID_DIRECTION_ALPHA:
        return "stable"
    return "rising" if diff > 0 else "easing"


def with_recent_rises(result: dict, rises: list[dict]) -> dict:
    """Merge short-term rises (active resistance-shift alerts) into a 12-month avoid list: an agent
    already flagged gets the rise attached; any other agent moves to `recent_rise`."""
    by_code = {r["code"]: r for r in rises}
    names = {
        x["code"]: x for k in ("avoid", "no_warning", "not_suited", "unknown") for x in result[k]
    }
    out = {**result, "recent_rise": []}
    out["avoid"] = [{**x, "recent_rise": by_code.get(x["code"])} for x in result["avoid"]]
    flagged = {x["code"] for x in result["avoid"]}
    for code, rise in by_code.items():
        if code in flagged or code not in names:
            continue
        out["recent_rise"].append({**names[code], "rise": rise})
    moved = {x["code"] for x in out["recent_rise"]}
    out["no_warning"] = [x for x in result["no_warning"] if x["code"] not in moved]
    return out
