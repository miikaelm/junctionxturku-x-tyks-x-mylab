"""HTTP API (API-01). The frontend is a client of the same endpoints external systems use.

Every data endpoint takes `as_of` (LIVE-01): results are computed as if that day were today.
"""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app import config
from app.alerts import engine
from app.alerts.detail import episode_detail
from app.alerts.triage import STATUSES, TriageStore, get_triage_store
from app.data.dataset import get_dataset
from app.data.freshness import feed_status, ward_freshness
from app.data.loader import get_tables
from app.data.scope import ALL_LABEL, INSTITUTION_LABELS, Scope
from app.stats.antibiogram import build_antibiogram

router = APIRouter(prefix="/api")

AsOf = Query(None, description="Compute as if this day were today (default: scenario today)")
Store = Annotated[TriageStore, Depends(get_triage_store)]


def resolve_as_of(as_of: date | None) -> date:
    as_of = as_of or config.DEFAULT_AS_OF
    if as_of < get_dataset().start.date():
        raise HTTPException(422, f"as_of is before the first sample ({get_dataset().start.date()})")
    return as_of


@router.get("/health")
def health() -> dict:
    cultures = get_tables().cultures
    return {
        "status": "ok",
        "cultures": len(cultures),
        "data_start": cultures.sample_date.min().date().isoformat(),
        "data_end": cultures.sample_date.max().date().isoformat(),
    }


@router.get("/meta")
def meta() -> dict:
    """Code tables and display settings the client needs to build filters and colour cells."""
    ds = get_dataset()
    return {
        "data_start": ds.start.date().isoformat(),
        "data_end": ds.end.date().isoformat(),
        "default_as_of": config.DEFAULT_AS_OF.isoformat(),
        "wards": ds.wards.to_dict(orient="records"),
        "locations": [
            {"code": code, "label": label, "level": "institution"}
            for code, label in INSTITUTION_LABELS.items()
        ]
        + [{"code": "all", "label": ALL_LABEL, "level": "all"}],
        "specimens": ["urine", "blood", "wound"],
        "organisms": sorted(ds.isolates.organism.unique()),
        "age_bands": [label for label, _, _ in config.AGE_BANDS],
        "alert_types": [
            {"key": key, "label": cfg["label"], "severity": cfg["severity"]}
            for key, cfg in config.ALERT_TYPES.items()
        ],
        "severities": config.SEVERITY_ORDER,
        "triage_statuses": list(STATUSES),
        "thresholds": {
            "min_isolates": config.MIN_ISOLATES_FOR_PERCENT,
            "good_below": config.RESISTANCE_GOOD_BELOW,
            "warn_below": config.RESISTANCE_WARN_BELOW,
            "ci_level": config.CI_LEVEL,
        },
    }


@router.get("/antibiogram")
def antibiogram(
    location: str = Query("all", description="Ward code, 'hospital', 'primary_care' or 'all'"),
    specimen: Literal["urine", "blood", "wound"] = "urine",
    sex: Literal["F", "M"] | None = None,
    age_band: str | None = None,
    hospital_acquired: bool | None = None,
    as_of: date | None = AsOf,
) -> dict:
    """Organism × antibiotic resistance: last 4 weeks and last 12 months, with fallbacks."""
    ds = get_dataset()
    if age_band is not None and age_band not in {b for b, _, _ in config.AGE_BANDS}:
        raise HTTPException(422, f"unknown age_band: {age_band}")
    scope = Scope(location, specimen, sex, age_band, hospital_acquired)
    try:
        scope.level(ds.wards)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return build_antibiogram(ds, scope, resolve_as_of(as_of))


@router.get("/freshness")
def freshness(as_of: date | None = AsOf) -> dict:
    """Last sample per ward and whether its silence is unusual (VIEW-12)."""
    as_of = resolve_as_of(as_of)
    return {"as_of": as_of.isoformat(), "wards": ward_freshness(get_dataset(), as_of)}


@router.get("/feed")
def feed(as_of: date | None = AsOf) -> dict:
    """Feed status per ward: freshness, daily volume of the last 8 weeks, last week vs expected
    (V7). Data-gap alerts come from /alerts?type=data_gap."""
    as_of = resolve_as_of(as_of)
    return {"as_of": as_of.isoformat(), "wards": feed_status(get_dataset(), as_of)}


def _ward_filter(location: str | None) -> set[str] | None:
    if location is None:
        return None
    try:
        return Scope(location).ward_codes(get_dataset().wards)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/alerts")
def alerts(
    store: Store,
    location: str | None = Query(None, description="Ward code, institution or 'all'"),
    type: Annotated[list[str] | None, Query(description="Alert types to include")] = None,
    include_resolved: bool = Query(False, description="Also list alerts resolved recently"),
    as_of: date | None = AsOf,
) -> dict:
    """Alerts as they stood on the as-of date (V3 inbox, V1 alert strip), most urgent first."""
    as_of = resolve_as_of(as_of)
    if type and not set(type) <= set(config.ALERT_TYPES):
        raise HTTPException(422, f"unknown alert type in {type}")
    items = engine.alerts_at(
        get_dataset(),
        as_of,
        store,
        wards=_ward_filter(location),
        types=set(type) if type else None,
        include_resolved=include_resolved,
    )
    return {"as_of": as_of.isoformat(), "counts": engine.counts(items), "alerts": items}


@router.get("/alerts/{alert_id}")
def alert_detail(
    alert_id: str,
    store: Store,
    as_of: date | None = AsOf,
) -> dict:
    """One alert with why it fired, its history, case line list and timeline (V4, ANOM-06)."""
    as_of = resolve_as_of(as_of)
    ds = get_dataset()
    summary = next(
        (
            a
            for a in engine.alerts_at(ds, as_of, store, include_resolved=True)
            if a["id"] == alert_id
        ),
        None,
    )
    episode = engine.find_episode(ds, alert_id, as_of)
    if episode is None:
        raise HTTPException(404, f"no alert {alert_id} as of {as_of}")
    if summary is None:  # resolved longer ago than the inbox looks back
        summary = engine.summarize(ds, episode, as_of, store)
    return {
        "as_of": as_of.isoformat(),
        **summary,
        **episode_detail(ds, episode, as_of),
        "triage_history": store.history(alert_id, as_of),
    }


class TriageAction(BaseModel):
    status: Literal["new", "investigating", "confirmed", "dismissed"]
    note: str = ""
    as_of: date | None = None


@router.post("/alerts/{alert_id}/triage")
def triage(alert_id: str, action: TriageAction, store: Store) -> dict:
    """Record a triage step (NOTIF-06). It applies from its as-of date on, so replay stays true."""
    as_of = resolve_as_of(action.as_of)
    if engine.find_episode(get_dataset(), alert_id, as_of) is None:
        raise HTTPException(404, f"no alert {alert_id} as of {as_of}")
    entry = store.add(alert_id, action.status, as_of, action.note)
    return {"id": alert_id, **entry}


@router.delete("/triage")
def reset_triage(store: Store) -> dict:
    """Clear all triage state (demo reset)."""
    store.clear()
    return {"status": "cleared"}
