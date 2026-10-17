"""Time windows relative to the as-of date (DATA-04, LIVE-01). No window ever extends past as_of."""

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app.config import ANNUAL_WINDOW_DAYS, RECENT_WINDOW_DAYS


@dataclass(frozen=True)
class Window:
    key: str
    label: str
    start: date  # inclusive
    end: date  # inclusive

    def mask(self, dates: pd.Series) -> pd.Series:
        return dates.between(pd.Timestamp(self.start), pd.Timestamp(self.end))

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "days": self.days,
        }


def rolling(as_of: date, days: int, key: str, label: str) -> Window:
    return Window(key, label, as_of - timedelta(days=days - 1), as_of)


def recent(as_of: date) -> Window:
    return rolling(as_of, RECENT_WINDOW_DAYS, "recent", "Last 4 weeks")


def annual(as_of: date) -> Window:
    return rolling(as_of, ANNUAL_WINDOW_DAYS, "annual", "Last 12 months")


def calendar_year(as_of: date, year: int | None = None) -> Window:
    year = year or as_of.year
    end = min(date(year, 12, 31), as_of)
    return Window("year", str(year), date(year, 1, 1), end)


def custom(as_of: date, start: date, end: date) -> Window:
    end = min(end, as_of)
    if start > end:
        raise ValueError("window start is after its end (or after the as-of date)")
    return Window("custom", f"{start.isoformat()} – {end.isoformat()}", start, end)
