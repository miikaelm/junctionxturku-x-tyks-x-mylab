"""Alert detail for the investigation view (V4, ANOM-06): why the alert fired, its firing
history, a line list of the cases and a timeline of the signal on the ward.

Cluster and multi-ward alerts also say how alike their cases' resistance profiles are
(ANOM-05), and alerts with cases list where those patients were sampled next (PAT-03).

Line lists are patient-level data, meant for infection control and lab roles (NF-03): the
clinician role in the web app shows only the aggregate parts.
"""

from datetime import date, timedelta

import pandas as pd

from app.alerts.engine import Episode
from app.alerts.sentinel import sentinel_matches
from app.config import FOLLOWUP_DAYS, PHENOTYPES, RECENT_WINDOW_DAYS
from app.data.dataset import Dataset
from app.data.first_isolate import first_isolates
from app.data.scope import Scope
from app.data.windows import Window
from app.detectors.carrier import reappearances
from app.detectors.cluster import new_cases
from app.detectors.multi_ward import profiled_cases
from app.detectors.novelty import novelty_events
from app.patients.registry import carrier_flags, phenotype_positives
from app.stats.antibiogram import resistance_counts
from app.stats.profiles import cluster_similarity
from app.stats.proportions import estimate

TIMELINE_WEEKS = 26
TIMELINE_TAIL_DAYS = 28  # how far past the last signal an alert's chart runs
RATE_TIMELINE_BLOCKS = 13  # 4-week blocks ≈ one year
GAP_TIMELINE_DAYS = 56


def episode_detail(ds: Dataset, episode: Episode, as_of: date) -> dict:
    fs = episode.up_to(as_of)
    case_ids = _case_ids(ds, episode, as_of)
    cases = line_list(ds, case_ids, _highlight(episode))
    similarity = None
    if episode.type in ("cluster", "multi_ward"):
        ev = fs[0].evidence
        similarity = cluster_similarity(
            ds, case_ids, ev["phenotype"], date.fromisoformat(ev["window"]["start"])
        )
        if similarity:
            for c in cases:
                c["profile"] = similarity["case_profiles"].get(c["isolate_id"])
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
        "cases": cases,
        "similarity": similarity,
        # Not for carrier alerts: their "cases" are old positives; the patient page shows the path.
        "followup": followup(ds, cases, as_of)
        if episode.type not in ("data_gap", "carrier")
        else None,
        "patient": _patient(ds, episode, as_of),
        # The chart ends a few weeks after the alert's last signal (or at as_of, if sooner), so
        # an old alert shows its own period, not the weeks before today.
        "timeline": _timeline(
            ds, episode, min(as_of, fs[-1].day + timedelta(days=TIMELINE_TAIL_DAYS))
        ),
    }


def followup(ds: Dataset, cases: list[dict], as_of: date) -> dict:
    """Where the patients behind an alert were sampled after their case, on other wards, within
    FOLLOWUP_DAYS (PAT-03): a follow-up list for infection control. Inferred from sample dates;
    there are no transfer records, so this shows where they were seen, not how they moved."""
    first_case: dict[str, dict] = {}
    for c in sorted(cases, key=lambda c: c["date"]):
        first_case.setdefault(c["patient_id"], c)
    cul = ds.cultures[
        ds.cultures.patient_id.isin(first_case) & (ds.cultures.sample_date <= pd.Timestamp(as_of))
    ]
    patients = []
    per_ward: dict[str, dict] = {}
    for pid, case in first_case.items():
        start = pd.Timestamp(case["date"])
        later = cul[
            cul.patient_id.eq(pid)
            & (cul.sample_date > start)
            & (cul.sample_date <= start + pd.Timedelta(days=FOLLOWUP_DAYS))
            & cul.ward_code.ne(case["ward"])
        ].drop_duplicates(["sample_date", "ward_code"])
        if later.empty:
            continue
        seen = [
            {"date": r.sample_date.date().isoformat(), "ward": r.ward_code, "specimen": r.specimen}
            for r in later.itertuples(index=False)
        ]
        patients.append(
            {"patient_id": pid, "case_date": case["date"], "case_ward": case["ward"], "seen": seen}
        )
        for s in seen:
            w = per_ward.setdefault(
                s["ward"], {"ward": s["ward"], "patients": set(), "first": s["date"]}
            )
            w["patients"].add(pid)
            w["first"] = min(w["first"], s["date"])
    wards = sorted(
        ({**w, "patients": len(w["patients"])} for w in per_ward.values()),
        key=lambda w: (-w["patients"], w["first"]),
    )
    return {
        "days": FOLLOWUP_DAYS,
        "case_patients": len(first_case),
        "patients": patients,
        "wards": wards,
    }


def _patient(ds: Dataset, episode: Episode, as_of: date) -> dict | None:
    """For a carrier alert: the patient's current flags (PAT-01)."""
    if episode.type != "carrier":
        return None
    return {"patient_id": episode.subject, "flags": carrier_flags(ds, episode.subject, as_of)}


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
    if episode.type == "carrier":
        # The positive results the carrier flag rests on.
        pos = phenotype_positives(ds, as_of)
        return list(dict.fromkeys(pos.isolate_id[pos.patient_id.eq(episode.subject)]))
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

    if episode.type == "carrier":
        ev = reappearances(ds, as_of)
        return {
            "kind": "counts",
            "label": f"Known carriers sampled per week on {episode.ward}",
            "unit": "week",
            "expected": None,
            "points": _bins(
                ev.sample_date[ev.ward_code.eq(episode.ward)], as_of, days=7, n=TIMELINE_WEEKS
            ),
        }
    if episode.type == "multi_ward":
        cases = profiled_cases(ds)
        dates = cases.sample_date[cases.strain.eq(episode.subject)]
        return {
            "kind": "counts",
            "label": f"{ev['phenotype']} {ev['organism']} ({ev['profile_label']}) cases per week, all wards",
            "unit": "week",
            "expected": round(
                ev["expected"]
                / (
                    date.fromisoformat(ev["window"]["end"])
                    - date.fromisoformat(ev["window"]["start"])
                ).days
                * 7,
                2,
            ),
            "points": _bins(dates, as_of, days=7, n=TIMELINE_WEEKS),
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
