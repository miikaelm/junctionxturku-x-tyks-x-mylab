"""Notifications outside the app (NOTIF-03, NOTIF-05, API-04).

A *subscription* says who gets what, and how: a role and wards (infection control gets every
ward, a ward doctor their own), a minimum severity, optional alert types, the events
("alert", "carrier_flag", "digest") and a channel:
  - "webhook": a real HTTP POST of JSON to another system, e.g. the patient record (API-04);
  - "email", "teams": simulated, the rendered message is logged instead of sent.

Messages come from the alert timeline, so they are deterministic: `planned(start, end)` lists
every message the subscriptions get for alerts first raised (and carrier flags first set) in
those days. The notifications view shows them for the days before the time cursor, consistent
with replay. When new data is actually ingested (DATA-05), the messages for the new days are
delivered: webhooks are POSTed in the background and every attempt is logged.

A weekly digest (each Monday, for the 7 days before) goes to subscriptions with "digest".
Subscriptions live in config.STATE_DIR / subscriptions.json, seeded with demo defaults.
"""

import json
import threading
import urllib.error
import urllib.request
from collections import deque
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app import config
from app.alerts import engine
from app.alerts.triage import TriageStore, get_triage_store
from app.data import store as data_store
from app.data.dataset import Dataset
from app.patients.registry import carriers

CHANNELS = ("webhook", "email", "teams")
EVENTS = ("alert", "carrier_flag", "digest")
ROLES = ("clinician", "infection_control", "lab", "system")

DEFAULT_SUBSCRIPTIONS = [
    {
        "id": "infection-control",
        "name": "Infection control team",
        "role": "infection_control",
        "channel": "email",
        "target": "infection-control@tyks.example",
        "wards": None,
        "min_severity": "medium",
        "types": None,
        "include_routine": False,
        "events": ["alert"],
    },
    {
        "id": "uro-on-call",
        "name": "Urology ward doctor on call",
        "role": "clinician",
        "channel": "teams",
        "target": "Urology on-call channel",
        "wards": ["URO"],
        "min_severity": "medium",
        "types": None,
        "include_routine": True,
        "events": ["alert"],
    },
    {
        "id": "icu-on-call",
        "name": "ICU doctor on call",
        "role": "clinician",
        "channel": "teams",
        "target": "ICU on-call channel",
        "wards": ["ICU"],
        "min_severity": "medium",
        "types": None,
        "include_routine": True,
        "events": ["alert"],
    },
    {
        "id": "microbiologist",
        "name": "Clinical microbiologist",
        "role": "lab",
        "channel": "email",
        "target": "microbiology@tyks.example",
        "wards": None,
        "min_severity": "high",
        "types": None,
        "include_routine": False,
        "events": ["alert", "digest"],
    },
    {
        "id": "patient-record",
        "name": "Patient record system (webhook)",
        "role": "system",
        "channel": "webhook",
        "target": f"{config.API_BASE_URL}/api/mock-ehr/inbox",
        "wards": None,
        "min_severity": "medium",
        "types": ["sentinel", "carrier", "cluster", "multi_ward"],
        "include_routine": True,
        "events": ["alert", "carrier_flag"],
    },
]


class SubscriptionStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._subs: list[dict] = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else [dict(s) for s in DEFAULT_SUBSCRIPTIONS]
        )

    def all(self) -> list[dict]:
        return [dict(s) for s in self._subs]

    def get(self, sub_id: str) -> dict | None:
        return next((dict(s) for s in self._subs if s["id"] == sub_id), None)

    def put(self, sub: dict) -> dict:
        with self._lock:
            self._subs = [s for s in self._subs if s["id"] != sub["id"]] + [sub]
            self._save()
        return sub

    def delete(self, sub_id: str) -> bool:
        with self._lock:
            before = len(self._subs)
            self._subs = [s for s in self._subs if s["id"] != sub_id]
            self._save()
            return len(self._subs) < before

    def reset(self) -> None:
        with self._lock:
            self._subs = [dict(s) for s in DEFAULT_SUBSCRIPTIONS]
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._subs, indent=1), encoding="utf-8")


@lru_cache(maxsize=1)
def get_subscription_store() -> SubscriptionStore:
    return SubscriptionStore(config.STATE_DIR / "subscriptions.json")


def matches(sub: dict, alert: dict) -> bool:
    if "alert" not in sub["events"]:
        return False
    if alert["routine"] and not sub.get("include_routine"):
        return False
    if sub.get("wards") and not set(sub["wards"]) & set(alert["wards"]):
        return False
    if sub.get("types") and alert["type"] not in sub["types"]:
        return False
    sev = config.SEVERITY_ORDER
    return sev.index(alert["severity"]) <= sev.index(sub.get("min_severity") or "info")


def _alert_link(alert_id: str) -> str:
    return f"{config.UI_BASE_URL}/#/alerts/{alert_id}"


def _render(sub: dict, event: str, subject: str, text: str, payload: dict) -> dict:
    """The message as the channel would carry it."""
    if sub["channel"] == "webhook":
        return {"content_type": "application/json", "body": payload}
    if sub["channel"] == "email":
        return {"subject": f"[AEI] {subject}", "body": text}
    return {"body": f"**{subject}**\n{text}"}  # Teams-style chat message


def message(sub: dict, day: date, event: str, subject: str, text: str, payload: dict) -> dict:
    return {
        "day": day.isoformat(),
        "subscription": sub["id"],
        "name": sub["name"],
        "role": sub["role"],
        "channel": sub["channel"],
        "target": sub["target"],
        "event": event,
        "subject": subject,
        **_render(sub, event, subject, text, payload),
        "ref": payload.get("alert", {}).get("id") or payload.get("carrier", {}).get("patient_id"),
    }


def planned(
    ds: Dataset, store: TriageStore, subs: list[dict], start: date, end: date
) -> list[dict]:
    """Every message the subscriptions get for days start..end (inclusive), newest first."""
    out: list[dict] = []
    names = ds.wards.set_index("ward_code").ward_en.to_dict()
    for e in engine.timeline(ds, end):
        if not (start <= e.first <= end):
            continue
        a = engine.summarize(ds, e, e.first, store, names)
        alert = {
            k: a[k]
            for k in (
                "id",
                "type",
                "type_label",
                "severity",
                "wards",
                "title",
                "first_seen",
                "onset",
            )
        }
        alert["link"] = _alert_link(a["id"])
        where = ", ".join(a["wards"])
        subject = f"{a['severity'].capitalize()}: {a['type_label']} on {where}"
        text = f"{a['title']}\nFirst seen {a['first_seen']}. Open: {alert['link']}"
        for sub in subs:
            if matches(sub, a):
                out.append(
                    message(
                        sub,
                        e.first,
                        "alert.new",
                        subject,
                        text,
                        {"event": "alert.new", "alert": alert},
                    )
                )

    flag_subs = [s for s in subs if "carrier_flag" in s["events"]]
    if flag_subs:
        reg = carriers(ds, end)
        new = reg[reg.first_positive.between(pd.Timestamp(start), pd.Timestamp(end))]
        for f in new.itertuples(index=False):
            carrier = {
                "patient_id": f.patient_id,
                "phenotype": f.phenotype,
                "first_positive": f.first_positive.date().isoformat(),
                "ward": f.first_ward,
                "organism": f.first_organism,
            }
            subject = f"New {f.phenotype} carrier: patient {f.patient_id}"
            text = f"First positive {carrier['first_positive']} on {f.first_ward} ({f.first_organism})."
            for sub in flag_subs:
                if sub.get("wards") and f.first_ward not in sub["wards"]:
                    continue
                out.append(
                    message(
                        sub,
                        f.first_positive.date(),
                        "carrier.flagged",
                        subject,
                        text,
                        {"event": "carrier.flagged", "carrier": carrier},
                    )
                )

    digest_subs = [s for s in subs if "digest" in s["events"]]
    day = start
    while digest_subs and day <= end:
        if day.weekday() == 0:  # Monday: the week before
            d = digest(ds, store, day - timedelta(days=1), "week", with_trends=False)
            subject = f"Weekly AEI digest {d['start']} – {d['end']}"
            for sub in digest_subs:
                out.append(
                    message(
                        sub, day, "digest", subject, d["text"], {"event": "digest", "digest": d}
                    )
                )
        day += timedelta(days=1)
    out.sort(key=lambda m: m["day"], reverse=True)
    return out


def digest(
    ds: Dataset, store: TriageStore, as_of: date, period: str, with_trends: bool = True
) -> dict:
    """What happened in the period up to as_of (NOTIF-05, AI-03 groundwork): new alerts by type
    and ward, still-active alerts, new carriers, data gaps, and (optionally) trend findings."""
    days = config.DIGEST_PERIODS[period]
    start = as_of - timedelta(days=days - 1)
    names = ds.wards.set_index("ward_code").ward_en.to_dict()
    new = [
        engine.summarize(ds, e, as_of, store, names)
        for e in engine.timeline(ds, as_of)
        if start <= e.first <= as_of
    ]
    signals = [a for a in new if not a["routine"]]
    by_type: dict[str, int] = {}
    for a in signals:
        by_type[a["type_label"]] = by_type.get(a["type_label"], 0) + 1
    reg = carriers(ds, as_of)
    new_carriers = reg[reg.first_positive.between(pd.Timestamp(start), pd.Timestamp(as_of))]
    active = [a for a in engine.alerts_at(ds, as_of, store) if not a["routine"]]
    out = {
        "period": period,
        "start": start.isoformat(),
        "end": as_of.isoformat(),
        "new_alerts": len(signals),
        "by_type": by_type,
        "alerts": [
            {k: a[k] for k in ("id", "type_label", "severity", "wards", "title", "first_seen")}
            for a in sorted(signals, key=lambda a: config.SEVERITY_ORDER.index(a["severity"]))
        ],
        "carrier_reappearances": sum(a["routine"] for a in new),
        "new_carriers": new_carriers.phenotype.value_counts().to_dict(),
        "active_alerts": len(active),
        "trends": None,
    }
    if with_trends:
        from app.stats import trends  # heavy; only for the full digest

        f = trends.findings(ds, as_of)
        out["trends"] = {
            "significant": [
                f"{t['location_label']} {t['specimen']} {t['organism']} × {t['antibiotic_code']}: "
                f"{t['trend']['pp_per_year']:+} pp/year"
                for t in f["trends"]
            ],
            "crossed_up": [
                f"{c['location_label']} {c['organism']} × {c['antibiotic_code']}: "
                f"{c['prev_12m']['pct']} → {c['last_12m']['pct']} %"
                for c in f["crossings"]
                if c["direction"] == "up" and c["clearly"]
            ],
        }
    out["text"] = _digest_text(out)
    return out


def _digest_text(d: dict) -> str:
    lines = [f"AEI digest {d['start']} – {d['end']}"]
    if d["new_alerts"]:
        kinds = ", ".join(f"{n} {k.lower()}" for k, n in d["by_type"].items())
        lines.append(f"New alerts: {d['new_alerts']} ({kinds}).")
        lines += [
            f"- {a['severity']}: {', '.join(a['wards'])}: {a['title']}" for a in d["alerts"][:8]
        ]
    else:
        lines.append("No new alerts.")
    lines.append(f"Still active: {d['active_alerts']}.")
    if d["new_carriers"]:
        lines.append(
            "New carriers: " + ", ".join(f"{n} {p}" for p, n in d["new_carriers"].items()) + "."
        )
    lines.append(f"Known carriers sampled on hospital wards: {d['carrier_reappearances']}.")
    if d["trends"]:
        if d["trends"]["significant"]:
            lines.append("Long-term trends: " + "; ".join(d["trends"]["significant"]) + ".")
        if d["trends"]["crossed_up"]:
            lines.append("Clearly above 20 %: " + "; ".join(d["trends"]["crossed_up"]) + ".")
    return "\n".join(lines)


# ---------- live delivery (on ingest) ----------

DELIVERIES: deque[dict] = deque(maxlen=500)


def deliver(messages: list[dict]) -> None:
    """Send webhooks in the background; log simulated channels at once."""
    for m in messages:
        entry = {
            "at": datetime.now().isoformat(timespec="seconds"),
            **{
                k: m[k]
                for k in ("day", "subscription", "name", "channel", "target", "event", "subject")
            },
        }
        if m["channel"] != "webhook":
            DELIVERIES.appendleft({**entry, "status": "simulated"})
            continue
        entry["status"] = "sending"
        DELIVERIES.appendleft(entry)
        threading.Thread(target=_post, args=(entry, m["target"], m["body"]), daemon=True).start()


def _post(entry: dict, url: str, payload: dict) -> None:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "AEI-webhook/1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.WEBHOOK_TIMEOUT_SECONDS) as res:
            entry["status"] = f"delivered ({res.status})"
    except urllib.error.HTTPError as e:
        entry["status"] = f"failed ({e.code})"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        entry["status"] = f"failed ({getattr(e, 'reason', e)})"


def on_ingest(old: Dataset, new: Dataset, since: date | None) -> None:
    """Ingest hook: deliver the messages for the days the new data added."""
    if since is None:
        return
    start, end = old.end.date() + timedelta(days=1), new.end.date()
    if end < start:
        return
    try:
        subs = get_subscription_store().all()
        deliver(planned(new, get_triage_store(), subs, start, end))
    except Exception as e:  # noqa: BLE001 (a failed notification must never fail an ingest)
        DELIVERIES.appendleft(
            {"at": datetime.now().isoformat(timespec="seconds"), "status": f"error: {e}"}
        )


data_store.INGEST_HOOKS.append(on_ingest)


# ---------- mock receiver: the "patient record system" end of the webhook (V11 demo) ----------

MOCK_INBOX: deque[dict] = deque(maxlen=200)
