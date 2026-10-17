"""Alert triage workflow (NOTIF-06): new → investigating → confirmed / dismissed.

Each triage action is stored with the as-of date it was taken at, so replaying an earlier
date shows the alert as it was then (LIVE-01): an action counts only from its as-of date on.
State lives in a small JSON file (config.STATE_DIR), separate from the dataset.
"""

import json
import threading
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

from app.config import STATE_DIR

STATUSES = ("new", "investigating", "confirmed", "dismissed")


class TriageStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, list[dict]] = {}
        if path.exists():
            self._data = json.loads(path.read_text(encoding="utf-8"))

    def history(self, alert_id: str, as_of: date | None = None) -> list[dict]:
        entries = self._data.get(alert_id, [])
        if as_of is None:
            return list(entries)
        return [e for e in entries if e["as_of"] <= as_of.isoformat()]

    def current(self, alert_id: str, as_of: date) -> dict | None:
        """The latest action taken at or before `as_of`, or None (status "new")."""
        entries = self.history(alert_id, as_of)
        return entries[-1] if entries else None

    def add(self, alert_id: str, status: str, as_of: date, note: str = "") -> dict:
        if status not in STATUSES:
            raise ValueError(f"unknown triage status: {status}")
        entry = {
            "status": status,
            "as_of": as_of.isoformat(),
            "note": note,
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        with self._lock:
            entries = self._data.setdefault(alert_id, [])
            entries.append(entry)
            # Keep entries ordered by as-of (stable for equal dates) so `current` is the last.
            entries.sort(key=lambda e: e["as_of"])
            self._save()
        return entry

    def clear(self) -> None:
        with self._lock:
            self._data = {}
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=1), encoding="utf-8")


@lru_cache(maxsize=1)
def get_triage_store() -> TriageStore:
    return TriageStore(STATE_DIR / "triage.json")
