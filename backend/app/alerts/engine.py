"""Alert engine: runs every detector over the timeline and turns firings into alerts.

An alert is an *episode*: consecutive firings of one detector for one ward and subject, at most
the type's `episode_gap` days apart (config.ALERT_TYPES). The alert list at an as-of date uses
only the firings up to that date (LIVE-01), so replaying a date shows exactly the alerts that
would have been raised then, each with its first-seen date, and an alert stays active for the
type's `active_days` after its last firing (NOTIF-04 severity, lifecycle).

Detectors look at no data after their own evaluation day, so the whole timeline is computed
once per dataset and cached; each request only filters it. After an ingest (DATA-05) the
firings before the batch's earliest sample date are kept and the detectors re-run from there.

Each alert also records its *onset*, the earliest case behind its first firing, so detection
latency (onset → first alert) can be read off any replay (ANOM-07).
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.alerts.sentinel import detect_sentinels
from app.alerts.triage import TriageStore
from app.config import (
    ALERT_TYPES,
    DISMISS_SUPPRESS_DAYS,
    REPLAY_LEAD_DAYS,
    RESOLVED_LOOKBACK_DAYS,
    SEVERITY_ORDER,
)
from app.data import store as data_store
from app.data.dataset import Dataset
from app.detectors.carrier import detect_carriers
from app.detectors.cluster import detect_clusters
from app.detectors.common import Firing
from app.detectors.data_gap import detect_data_gaps
from app.detectors.multi_ward import MULTI_WARD, detect_multi_ward
from app.detectors.novelty import detect_novelty
from app.detectors.rate_shift import detect_rate_shifts

DETECTORS = [
    detect_sentinels,
    detect_clusters,
    detect_rate_shifts,
    detect_novelty,
    detect_data_gaps,
    detect_carriers,
    detect_multi_ward,
]


@dataclass(frozen=True)
class Episode:
    type: str
    ward: str
    subject: str
    firings: tuple[Firing, ...]  # sorted by day
    onset: date  # earliest case behind the first firing (ANOM-07)

    @property
    def key(self) -> tuple[str, str, str]:
        return self.type, self.ward, self.subject

    @property
    def first(self) -> date:
        return self.firings[0].day

    @property
    def id(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", self.subject.lower()).strip("-")
        return f"{self.type}.{self.ward}.{slug}.{self.first:%Y%m%d}"

    def up_to(self, as_of: date) -> list[Firing]:
        return [f for f in self.firings if f.day <= as_of]

    def wards(self, as_of: date) -> list[str]:
        """The wards this alert concerns: one, or several for a multi-ward signal (ANOM-09)."""
        if self.ward != MULTI_WARD:
            return [self.ward]
        return list(dict.fromkeys(w for f in self.up_to(as_of) for w in f.evidence["wards"]))


def build_episodes(ds: Dataset, firings: list[Firing]) -> list[Episode]:
    by_key: dict[tuple[str, str, str], list[Firing]] = {}
    for f in sorted(firings, key=lambda f: f.day):
        by_key.setdefault((f.type, f.ward, f.subject), []).append(f)
    groups = []
    for (type_, ward, subject), fs in by_key.items():
        gap = ALERT_TYPES[type_]["episode_gap"]
        current = [fs[0]]
        for f in fs[1:]:
            if (f.day - current[-1].day).days > gap:
                groups.append((type_, ward, subject, current))
                current = []
            current.append(f)
        groups.append((type_, ward, subject, current))
    sample_dates = ds.isolates.set_index("isolate_id").sample_date
    episodes = [
        Episode(type_, ward, subject, tuple(fs), _onset(fs[0], sample_dates))
        for type_, ward, subject, fs in groups
    ]
    return sorted(episodes, key=lambda e: (e.first, e.id))


def _onset(first: Firing, sample_dates) -> date:
    """When the event behind an alert began, as far as the data shows: the day after the last
    sample for a data gap, else the earliest case the first firing counted."""
    if first.type == "data_gap":
        return date.fromisoformat(first.evidence["last_sample"]) + timedelta(days=1)
    if not first.isolate_ids:
        return first.day
    return min(first.day, sample_dates[list(first.isolate_ids)].min().date())


# id(dataset) → (dataset, horizon, firings, episodes)
_cache: dict[int, tuple[Dataset, date, list[Firing], list[Episode]]] = {}


def timeline(ds: Dataset, as_of: date) -> list[Episode]:
    """All alert episodes, computed through max(data end, as_of). Cached per dataset."""
    horizon = max(ds.end.date(), as_of)
    hit = _cache.get(id(ds))
    if hit is not None and hit[0] is ds and hit[1] >= horizon:
        return hit[3]
    firings = [f for detect in DETECTORS for f in detect(ds, horizon)]
    return _remember(ds, horizon, firings)


def _remember(ds: Dataset, horizon: date, firings: list[Firing]) -> list[Episode]:
    episodes = build_episodes(ds, firings)
    if len(_cache) >= 4:
        _cache.clear()
    _cache[id(ds)] = (ds, horizon, firings, episodes)
    return episodes


def update(old: Dataset, new: Dataset, since: date | None) -> None:
    """Ingest hook (DATA-05): carry the cached timeline over to the new dataset, re-running the
    detectors only for days from `since` (the batch's earliest sample date) on."""
    hit = _cache.get(id(old))
    if hit is None or hit[0] is not old:
        return  # nothing cached yet: computed on the next request
    _, horizon, firings, _ = hit
    if since is None:
        _remember(new, horizon, firings)
        return
    since = min(since, horizon + timedelta(days=1))  # no uncomputed days in between
    horizon = max(horizon, new.end.date())
    kept = [f for f in firings if f.day < since]
    fresh = [f for detect in DETECTORS for f in detect(new, horizon, since)]
    _remember(new, horizon, kept + fresh)


data_store.INGEST_HOOKS.append(update)


def summarize(
    ds: Dataset, episode: Episode, as_of: date, store: TriageStore, ward_names: dict | None = None
) -> dict:
    fs = episode.up_to(as_of)
    cfg = ALERT_TYPES[episode.type]
    last = fs[-1]
    active = (as_of - last.day).days <= cfg["active_days"]
    triage = store.current(episode.id, as_of)
    if ward_names is None:
        ward_names = _ward_names(ds)
    return {
        "id": episode.id,
        "type": episode.type,
        "type_label": cfg["label"],
        "severity": cfg["severity"],
        "routine": is_routine(episode.type),
        "ward": episode.ward,
        "ward_en": "Several wards"
        if episode.ward == MULTI_WARD
        else ward_names.get(episode.ward, episode.ward),
        "wards": episode.wards(as_of),
        "subject": episode.subject,
        "title": last.title,
        "first_seen": episode.first.isoformat(),
        "last_seen": last.day.isoformat(),
        "onset": episode.onset.isoformat(),
        "detection_days": (episode.first - episode.onset).days,
        "firings": len(fs),
        "state": "active" if active else "resolved",
        "resolved_on": None
        if active
        else (last.day + timedelta(days=cfg["active_days"] + 1)).isoformat(),
        "triage": {
            "status": triage["status"] if triage else "new",
            "note": triage["note"] if triage else "",
            "as_of": triage["as_of"] if triage else None,
            "suppressed_by": None,
        },
        "evidence": last.evidence,
    }


def alerts_at(
    ds: Dataset,
    as_of: date,
    store: TriageStore,
    *,
    wards: set[str] | None = None,
    types: set[str] | None = None,
    include_resolved: bool = False,
) -> list[dict]:
    """Alerts as they stood on `as_of`, most urgent first."""
    names = _ward_names(ds)
    summaries = [
        summarize(ds, e, as_of, store, names) for e in timeline(ds, as_of) if e.first <= as_of
    ]
    _suppress_dismissed_duplicates(summaries)

    lookback = (as_of - timedelta(days=RESOLVED_LOOKBACK_DAYS)).isoformat()
    out = [
        s
        for s in summaries
        if (wards is None or not wards.isdisjoint(s["wards"]))
        and (types is None or s["type"] in types)
        and (s["state"] == "active" or (include_resolved and s["last_seen"] >= lookback))
    ]
    out.sort(key=lambda s: s["last_seen"], reverse=True)
    out.sort(key=lambda s: (s["state"] != "active", SEVERITY_ORDER.index(s["severity"])))
    return out


def _ward_names(ds: Dataset) -> dict:
    return ds.wards.set_index("ward_code").ward_en.to_dict()


def _suppress_dismissed_duplicates(summaries: list[dict]) -> None:
    """A new alert repeating a dismissed one (same detector, ward and subject, starting within
    DISMISS_SUPPRESS_DAYS of the dismissed one's last firing) is dismissed too (NOTIF-06)."""
    last_dismissed: dict[tuple[str, str, str], dict] = {}
    for s in sorted(summaries, key=lambda s: s["first_seen"]):
        key = (s["type"], s["ward"], s["subject"])
        prev = last_dismissed.get(key)
        if prev is not None and s["triage"]["as_of"] is None:
            gap = (date.fromisoformat(s["first_seen"]) - date.fromisoformat(prev["last_seen"])).days
            if gap <= DISMISS_SUPPRESS_DAYS:
                s["triage"]["status"] = "dismissed"
                s["triage"]["suppressed_by"] = prev["id"]
        if s["triage"]["status"] == "dismissed":
            last_dismissed[key] = s


def find_episode(ds: Dataset, alert_id: str, as_of: date) -> Episode | None:
    return next((e for e in timeline(ds, as_of) if e.id == alert_id and e.first <= as_of), None)


def is_routine(alert_type: str) -> bool:
    return bool(ALERT_TYPES[alert_type].get("routine"))


def counts(alerts: list[dict]) -> dict:
    """Active alerts by triage and severity. Routine types (carrier re-appearances) are counted
    apart, so they don't drown the signals in the "new" badge."""
    active = [a for a in alerts if a["state"] == "active"]
    routine = [a for a in active if is_routine(a["type"])]
    active = [a for a in active if not is_routine(a["type"])]
    return {
        "active": len(active),
        "new": sum(a["triage"]["status"] == "new" for a in active),
        "routine": len(routine),
        "routine_new": sum(a["triage"]["status"] == "new" for a in routine),
        "by_severity": {
            sev: sum(a["severity"] == sev for a in active)
            for sev in SEVERITY_ORDER
            if any(a["severity"] == sev for a in active)
        },
    }


def replay_events(ds: Dataset, today: date, store: TriageStore) -> list[dict]:
    """Every alert raised up to `today`, newest first, each with a replay start a few days
    before its onset (LIVE-04) and its detection latency (ANOM-07). Built from the alerts
    themselves, so it covers whatever the detectors found."""
    start = ds.start.date()
    names = _ward_names(ds)
    out = []
    for e in timeline(ds, today):
        if e.first > today or is_routine(e.type):
            continue
        cfg = ALERT_TYPES[e.type]
        out.append(
            {
                "id": e.id,
                "type": e.type,
                "type_label": cfg["label"],
                "severity": cfg["severity"],
                "ward": e.ward,
                "wards": e.wards(today),
                "subject": e.subject,
                "title": e.firings[0].title,
                "onset": e.onset.isoformat(),
                "first_seen": e.first.isoformat(),
                "detection_days": (e.first - e.onset).days,
                "replay_from": max(start, e.onset - timedelta(days=REPLAY_LEAD_DAYS)).isoformat(),
                "triage": summarize(ds, e, today, store, names)["triage"]["status"],
            }
        )
    return sorted(out, key=lambda x: x["first_seen"], reverse=True)


def warm(ds: Dataset, as_of: date) -> None:
    """Compute the timeline ahead of the first request (a few seconds on the full data)."""
    timeline(ds, as_of)


def alerts_for_patient(ds: Dataset, as_of: date, store: TriageStore, patient_id: str) -> list[dict]:
    """Active alerts this patient is part of: as a case, a sentinel or a known carrier."""
    isolates = set(ds.isolates.isolate_id[ds.isolates.patient_id.eq(patient_id)])
    by_id = {e.id: e for e in timeline(ds, as_of) if e.first <= as_of}
    out = []
    for a in alerts_at(ds, as_of, store):
        e = by_id[a["id"]]
        if (
            e.subject == patient_id
            or e.subject.endswith(f"|{patient_id}")
            or any(i in isolates for f in e.up_to(as_of) for i in f.isolate_ids)
        ):
            out.append(a)
    return out
