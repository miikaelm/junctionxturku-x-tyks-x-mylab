"""Alert engine: runs every detector over the timeline and turns firings into alerts.

An alert is an *episode*: consecutive firings of one detector for one ward and subject, at most
the type's `episode_gap` days apart (config.ALERT_TYPES). The alert list at an as-of date uses
only the firings up to that date (LIVE-01), so replaying a date shows exactly the alerts that
would have been raised then, each with its first-seen date, and an alert stays active for the
type's `active_days` after its last firing (NOTIF-04 severity, lifecycle).

Detectors look at no data after their own evaluation day, so the whole timeline is computed
once per dataset and cached; each request only filters it.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.alerts.sentinel import detect_sentinels
from app.alerts.triage import TriageStore
from app.config import (
    ALERT_TYPES,
    DISMISS_SUPPRESS_DAYS,
    RESOLVED_LOOKBACK_DAYS,
    SEVERITY_ORDER,
)
from app.data.dataset import Dataset
from app.detectors.cluster import detect_clusters
from app.detectors.common import Firing
from app.detectors.data_gap import detect_data_gaps
from app.detectors.novelty import detect_novelty
from app.detectors.rate_shift import detect_rate_shifts

DETECTORS = [
    detect_sentinels,
    detect_clusters,
    detect_rate_shifts,
    detect_novelty,
    detect_data_gaps,
]


@dataclass(frozen=True)
class Episode:
    type: str
    ward: str
    subject: str
    firings: tuple[Firing, ...]  # sorted by day

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


def build_episodes(firings: list[Firing]) -> list[Episode]:
    by_key: dict[tuple[str, str, str], list[Firing]] = {}
    for f in sorted(firings, key=lambda f: f.day):
        by_key.setdefault((f.type, f.ward, f.subject), []).append(f)
    episodes = []
    for (type_, ward, subject), fs in by_key.items():
        gap = ALERT_TYPES[type_]["episode_gap"]
        current = [fs[0]]
        for f in fs[1:]:
            if (f.day - current[-1].day).days > gap:
                episodes.append(Episode(type_, ward, subject, tuple(current)))
                current = []
            current.append(f)
        episodes.append(Episode(type_, ward, subject, tuple(current)))
    return sorted(episodes, key=lambda e: (e.first, e.id))


_cache: dict[tuple[int, date], tuple[Dataset, list[Episode]]] = {}


def timeline(ds: Dataset, as_of: date) -> list[Episode]:
    """All alert episodes, computed through max(data end, as_of). Cached per dataset."""
    horizon = max(ds.end.date(), as_of)
    key = (id(ds), horizon)
    hit = _cache.get(key)
    if hit is not None and hit[0] is ds:
        return hit[1]
    firings = [f for detect in DETECTORS for f in detect(ds, horizon)]
    episodes = build_episodes(firings)
    if len(_cache) >= 4:
        _cache.clear()
    _cache[key] = (ds, episodes)
    return episodes


def summarize(ds: Dataset, episode: Episode, as_of: date, store: TriageStore) -> dict:
    fs = episode.up_to(as_of)
    cfg = ALERT_TYPES[episode.type]
    last = fs[-1]
    active = (as_of - last.day).days <= cfg["active_days"]
    triage = store.current(episode.id, as_of)
    ward_names = ds.wards.set_index("ward_code").ward_en
    return {
        "id": episode.id,
        "type": episode.type,
        "type_label": cfg["label"],
        "severity": cfg["severity"],
        "ward": episode.ward,
        "ward_en": ward_names.get(episode.ward, episode.ward),
        "subject": episode.subject,
        "title": last.title,
        "first_seen": episode.first.isoformat(),
        "last_seen": last.day.isoformat(),
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
    summaries = [summarize(ds, e, as_of, store) for e in timeline(ds, as_of) if e.first <= as_of]
    _suppress_dismissed_duplicates(summaries)

    lookback = (as_of - timedelta(days=RESOLVED_LOOKBACK_DAYS)).isoformat()
    out = [
        s
        for s in summaries
        if (wards is None or s["ward"] in wards)
        and (types is None or s["type"] in types)
        and (s["state"] == "active" or (include_resolved and s["last_seen"] >= lookback))
    ]
    out.sort(key=lambda s: s["last_seen"], reverse=True)
    out.sort(key=lambda s: (s["state"] != "active", SEVERITY_ORDER.index(s["severity"])))
    return out


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


def counts(alerts: list[dict]) -> dict:
    active = [a for a in alerts if a["state"] == "active"]
    return {
        "active": len(active),
        "new": sum(a["triage"]["status"] == "new" for a in active),
        "by_severity": {
            sev: sum(a["severity"] == sev for a in active)
            for sev in SEVERITY_ORDER
            if any(a["severity"] == sev for a in active)
        },
    }


def warm(ds: Dataset, as_of: date) -> None:
    """Compute the timeline ahead of the first request (a few seconds on the full data)."""
    timeline(ds, as_of)
