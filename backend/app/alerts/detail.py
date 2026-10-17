"""Alert detail for the investigation view (V4, ANOM-06): why the alert fired, its firing
history, a line list of the cases and a timeline of the signal on the ward.

Line lists are patient-level data. They are meant for infection control and lab roles (NF-03);
role-based access arrives with the role picker (VIEW-08).
"""

from datetime import date, timedelta

import pandas as pd

from app.alerts.engine import Episode
from app.alerts.sentinel import sentinel_matches
from app.config import PHENOTYPES, RECENT_WINDOW_DAYS
from app.data.dataset import Dataset
from app.data.first_isolate import first_isolates
from app.data.scope import Scope
from app.data.windows import Window
from app.detectors.cluster import new_cases
from app.detectors.novelty import novelty_events
from app.stats.antibiogram import resistance_counts
from app.stats.proportions import estimate

TIMELINE_WEEKS = 26
RATE_TIMELINE_BLOCKS = 13  # 4-week blocks ≈ one year
GAP_TIMELINE_DAYS = 56


def episode_detail(ds: Dataset, episode: Episode, as_of: date) -> dict:
    fs = episode.up_to(as_of)
    return {
        "trigger": {"day": fs[0].day.isoformat(), "title": fs[0].title, "evidence": fs[0].evidence},
        "history": [
            {
                "day": f.day.isoformat(),
                "title": f.title,
                "p_value": f.evidence.get("p_value"),
                "q_value": f.evidence.get("q_value"),
            }
            for f in fs
        ],
        "cases": line_list(ds, _case_ids(ds, episode, as_of), _highlight(episode)),
        "timeline": _timeline(ds, episode, as_of),
    }


def line_list(ds: Dataset, isolate_ids: list[str], highlight: str | None = None) -> list[dict]:
    iso = ds.isolates[ds.isolates.isolate_id.isin(isolate_ids)]
    ast = ds.ast[ds.ast.isolate_id.isin(isolate_ids)]
    resistant = ast[ast.resistant].groupby("isolate_id").antibiotic_code.agg(list)
    tested = ast.groupby("isolate_id").antibiotic_code.agg(list)
    rows = []
    for i in iso.itertuples(index=False):
        days_in = (
            int((i.sample_date - i.admission_date).days) if pd.notna(i.admission_date) else None
        )
        r = resistant.get(i.isolate_id, [])
        rows.append(
            {
                "isolate_id": i.isolate_id,
                "date": i.sample_date.date().isoformat(),
                "patient_id": i.patient_id,
                "sex": i.sex,
                "age": int(i.age_years),
                "ward": i.ward_code,
                "specimen": i.specimen,
                "organism": i.organism,
                "phenotypes": [p for p in PHENOTYPES if getattr(i, p.lower()) == 1],
                "days_since_admission": days_in,
                "hospital_acquired": bool(i.hospital_acquired),
                "resistant": r,
                "tested": len(tested.get(i.isolate_id, [])),
                "highlight": highlight in r if highlight else None,
            }
        )
    return rows


def _highlight(episode: Episode) -> str | None:
    """For rate shifts: the antibiotic whose resistance to mark in the line list."""
    return (
        episode.firings[-1].evidence.get("antibiotic_code")
        if episode.type == "rate_shift"
        else None
    )


def _case_ids(ds: Dataset, episode: Episode, as_of: date) -> list[str]:
    fs = episode.up_to(as_of)
    if episode.type == "rate_shift":
        # First isolates of the shifted organism in the latest 4-week window.
        ev = fs[-1].evidence
        window = Window("recent", "", date.fromisoformat(ev["window"]["start"]), fs[-1].day)
        iso = Scope(episode.ward, ev["specimen"]).apply(ds.isolates)
        iso = first_isolates(iso[window.mask(iso.sample_date)])
        return list(iso.isolate_id[iso.organism.eq(ev["organism"])])
    ids: list[str] = []
    for f in fs:
        ids.extend(i for i in f.isolate_ids if i not in ids)
    return ids


def _timeline(ds: Dataset, episode: Episode, as_of: date) -> dict:
    ev = episode.up_to(as_of)[-1].evidence
    if episode.type == "rate_shift":
        return _rate_timeline(ds, episode, ev, as_of)
    if episode.type == "data_gap":
        dates = ds.cultures.sample_date[ds.cultures.ward_code.eq(episode.ward)]
        points = _bins(dates, as_of, days=1, n=GAP_TIMELINE_DAYS)
        return {
            "kind": "counts",
            "label": f"Samples per day on {episode.ward}",
            "unit": "day",
            "expected": ev["samples_per_day"],
            "points": points,
        }

    dates = _subject_dates(ds, episode, as_of)
    expected = None
    if episode.type == "cluster":
        window_days = (
            date.fromisoformat(ev["window"]["end"]) - date.fromisoformat(ev["window"]["start"])
        ).days + 1
        expected = round(ev["expected"] / window_days * 7, 2)
    label = episode.subject.split("|")[0]
    return {
        "kind": "counts",
        "label": f"{label} cases per week on {episode.ward}",
        "unit": "week",
        "expected": expected,
        "points": _bins(dates, as_of, days=7, n=TIMELINE_WEEKS),
    }


def _subject_dates(ds: Dataset, episode: Episode, as_of: date) -> pd.Series:
    if episode.type == "cluster":
        ev = new_cases(ds)
        ev = ev[ev.phenotype.eq(episode.subject)]
    elif episode.type == "novelty":
        ev = novelty_events(ds, as_of)
        ev = ev[ev["item"].eq(episode.subject)]
    else:  # sentinel: subject is "<marker>|<patient>"
        ev = sentinel_matches(ds, as_of)
        ev = ev[ev.marker.eq(episode.subject.split("|")[0])]
    return ev.sample_date[ev.ward_code.eq(episode.ward)]


def _bins(dates: pd.Series, as_of: date, *, days: int, n: int) -> list[dict]:
    """Counts in n consecutive bins of `days` days, the last one ending on as_of."""
    out = []
    for k in range(n - 1, -1, -1):
        end = as_of - timedelta(days=k * days)
        start = end - timedelta(days=days - 1)
        count = int(dates.between(pd.Timestamp(start), pd.Timestamp(end)).sum())
        out.append({"start": start.isoformat(), "end": end.isoformat(), "value": count})
    return out


def _rate_timeline(ds: Dataset, episode: Episode, ev: dict, as_of: date) -> dict:
    scope = Scope(episode.ward, ev["specimen"])
    points = []
    for k in range(RATE_TIMELINE_BLOCKS - 1, -1, -1):
        end = as_of - timedelta(days=k * RECENT_WINDOW_DAYS)
        start = end - timedelta(days=RECENT_WINDOW_DAYS - 1)
        counts, _ = resistance_counts(ds, scope, Window("block", "", start, end))
        n, r = counts.get((ev["organism"], ev["antibiotic_code"]), (0, 0))
        points.append({"start": start.isoformat(), "end": end.isoformat(), **estimate(r, n)})
    return {
        "kind": "rate",
        "label": f"{ev['organism']} {ev['antibiotic']} resistance on {episode.ward} "
        f"({ev['specimen']}), per 4 weeks",
        "unit": "4 weeks",
        "expected": ev["expected"]["pct"],
        "points": points,
    }
