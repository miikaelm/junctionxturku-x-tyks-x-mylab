"""Per-dataset result caches keyed by as-of date, with pinned dates (NF-01).

Slow results (stewardship findings, trend tests) are kept per as-of date. Dates pinned at startup
(today and the demo dates, see app.demo) are never evicted, so scrubbing the time cursor through
replay doesn't push them out again.
"""

import threading
from datetime import date

PINNED: set[date] = set()


class Memo:
    def __init__(self, maxsize: int):
        self.maxsize = maxsize
        self._data: dict[tuple, tuple[object, date, object]] = {}
        # The startup warm-up and requests run in different threads.
        self._lock = threading.Lock()

    def get(self, ds, key: tuple, default=None):
        with self._lock:
            hit = self._data.get((id(ds), *key))
        return hit[2] if hit is not None and hit[0] is ds else default

    def put(self, ds, key: tuple, as_of: date, value) -> None:
        full = (id(ds), *key)
        with self._lock:
            self._data.pop(full, None)
            # Results of an older dataset (before an ingest) go first, pinned or not.
            for k in [k for k, v in self._data.items() if v[0] is not ds]:
                del self._data[k]
            while len(self._data) >= self.maxsize:
                old = next((k for k, v in self._data.items() if v[1] not in PINNED), None)
                if old is None:
                    break
                del self._data[old]
            self._data[full] = (ds, as_of, value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
