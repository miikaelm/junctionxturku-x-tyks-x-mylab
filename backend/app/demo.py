"""Demo support: which dates to compute ahead (NF-01) and the mock patient record's setup (V11).

Warming runs in a background thread at startup. It fills the per-date caches of the slow results
(the stewardship collection: every ward × infection avoid list plus the trend tests, ~10 s per
date cold) for today, the mock patient record's date and the day each alert of WARM_ALERT_TYPES was
raised, and pins those dates so replay doesn't evict them. The dates come from the alert history,
not from the answer key.
"""

import logging
import time
from datetime import date

from app import config, memo
from app.alerts import engine, stewardship
from app.data.dataset import Dataset

# uvicorn's logger, so the warm-up shows in the server console.
log = logging.getLogger("uvicorn.error")


def warm_dates(ds: Dataset, today: date) -> list[date]:
    dates = [today, config.EHR_DEMO["as_of"]]
    for e in engine.timeline(ds, today):
        if e.type in config.WARM_ALERT_TYPES and e.first <= today:
            dates.append(e.first)
    out: list[date] = []
    for d in dates:
        if ds.start.date() <= d <= today and d not in out:
            out.append(d)
    return out


def warm(ds: Dataset, today: date) -> list[date]:
    engine.warm(ds, today)
    dates = warm_dates(ds, today)
    memo.PINNED.update(dates)
    start = time.perf_counter()
    for d in dates:
        t = time.perf_counter()
        stewardship.findings(ds, d, stewardship.get_stewardship_store())
        log.info("AEI warm-up: %s ready in %.1f s", d, time.perf_counter() - t)
    log.info("AEI warm-up done: %d dates in %.0f s", len(dates), time.perf_counter() - start)
    return dates


def ehr_demo() -> dict:
    return {
        "as_of": config.EHR_DEMO["as_of"].isoformat(),
        "ward": config.EHR_DEMO["ward"],
        "patients": list(config.EHR_DEMO["patients"]),
    }
