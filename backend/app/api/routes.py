"""HTTP API (API-01). The frontend is a client of the same endpoints external systems use.

Every data endpoint takes `as_of` (LIVE-01): results are computed as if that day were today.
"""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from app import config
from app.alerts import engine
from app.alerts.detail import episode_detail
from app.alerts.triage import STATUSES, TriageStore, get_triage_store
from app.data import windows
from app.data.dataset import get_dataset
from app.data.freshness import feed_status, ward_freshness
from app.data.intrinsic import INTRINSIC_RESISTANCE
from app.data.scope import ALL_LABEL, INSTITUTION_LABELS, Scope
from app.data.store import IngestError, batch_from_records, get_store
from app.stats import overview, trends
from app.stats.antibiogram import SPLIT_DIMENSIONS, Split, build_antibiogram
from app.stats.subgroups import discover

router = APIRouter(prefix="/api")

AsOf = Query(None, description="Compute as if this day were today (default: scenario today)")
Store = Annotated[TriageStore, Depends(get_triage_store)]
Specimen = Literal["urine", "blood", "wound"]
SplitBy = Literal["sex", "age_band", "hospital_acquired", "ward_type", "home_area", "none"]


def resolve_as_of(as_of: date | None) -> date:
    as_of = as_of or get_store().today()
    if as_of < get_dataset().start.date():
        raise HTTPException(422, f"as_of is before the first sample ({get_dataset().start.date()})")
    return as_of


def _scope(location: str, specimen: str | None = None, **filters) -> Scope:
    scope = Scope(location, specimen, **filters)
    try:
        scope.level(get_dataset().wards)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return scope


@router.get("/health")
def health() -> dict:
    cultures = get_store().tables.cultures
    return {
        "status": "ok",
        "cultures": len(cultures),
        "data_start": cultures.sample_date.min().date().isoformat(),
        "data_end": cultures.sample_date.max().date().isoformat(),
    }


@router.get("/status")
def status() -> dict:
    """Data version, received range and the last ingest (DATA-05). Clients poll this to notice
    new data."""
    return get_store().status()


@router.get("/meta")
def meta() -> dict:
    """Code tables and display settings the client needs to build filters and colour cells."""
    ds = get_dataset()
    names = ds.antibiotics.set_index("antibiotic_code").antibiotic
    return {
        "data_start": ds.start.date().isoformat(),
        "data_end": ds.end.date().isoformat(),
        "default_as_of": get_store().today().isoformat(),
        "data_version": get_store().version,
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
        "home_areas": sorted(ds.cultures.home_area.dropna().unique()),
        "split_dimensions": [
            {"key": d, "label": config.SUBGROUP_DIMENSIONS[d]} for d in SPLIT_DIMENSIONS
        ],
        "phenotypes": config.PHENOTYPES,
        "key_rates": [
            {**k, "antibiotic_name": names[k["antibiotic"]]} for k in config.HEATMAP_KEY_RATES
        ],
        "tested_pairs": sorted([list(p) for p in ds.tested_pairs]),
        "intrinsic": {o: sorted(c) for o, c in INTRINSIC_RESISTANCE.items()},
        "antibiotics": [
            {"code": a.antibiotic_code, "name": a.antibiotic, "reported_for": a.reported_for}
            for a in ds.antibiotics.itertuples(index=False)
        ],
        "thresholds": {
            "min_isolates": config.MIN_ISOLATES_FOR_PERCENT,
            "good_below": config.RESISTANCE_GOOD_BELOW,
            "warn_below": config.RESISTANCE_WARN_BELOW,
            "ci_level": config.CI_LEVEL,
            "empirical_pct": config.EMPIRICAL_THRESHOLD_PCT,
        },
    }


@router.get("/antibiogram")
def antibiogram(
    location: str = Query("all", description="Ward code, 'hospital', 'primary_care' or 'all'"),
    specimen: Specimen = "urine",
    sex: Literal["F", "M"] | None = None,
    age_band: str | None = None,
    hospital_acquired: bool | None = None,
    split_by: Annotated[
        SplitBy | None,
        Query(
            description="Split one organism into sub-rows by this dimension. 'none': no split; "
            "omitted: the clinically known default split for the specimen (STAT-07)"
        ),
    ] = None,
    split_organism: str | None = None,
    as_of: date | None = AsOf,
) -> dict:
    """Organism × antibiotic resistance: last 4 weeks and last 12 months, with fallbacks."""
    ds = get_dataset()
    if age_band is not None and age_band not in {b for b, _, _ in config.AGE_BANDS}:
        raise HTTPException(422, f"unknown age_band: {age_band}")
    scope = _scope(
        location, specimen, sex=sex, age_band=age_band, hospital_acquired=hospital_acquired
    )
    split = None
    if split_by is None:
        default = next((d for d in config.DEFAULT_SPLITS if d["specimen"] == specimen), None)
        if default and getattr(scope, default["by"]) is None:
            split = Split(default["organism"], default["by"], default=True)
    elif split_by != "none":
        if not split_organism:
            raise HTTPException(422, "split_by needs split_organism")
        if getattr(scope, split_by) is not None:
            raise HTTPException(422, f"already filtered by {split_by}")
        split = Split(split_organism, split_by)
    return build_antibiogram(ds, scope, resolve_as_of(as_of), split)


@router.get("/subgroups")
def subgroups(
    location: str = Query("all"),
    specimen: Specimen = "urine",
    window: Literal["annual", "all"] = Query(
        "annual", description="Last 12 months, or all data up to as_of"
    ),
    as_of: date | None = AsOf,
) -> dict:
    """Where resistance differs notably between patient groups (STAT-09), FDR-controlled."""
    as_of = resolve_as_of(as_of)
    ds = get_dataset()
    win = (
        windows.annual(as_of)
        if window == "annual"
        else windows.custom(as_of, ds.start.date(), as_of)
    )
    return {"as_of": as_of.isoformat(), **discover(ds, _scope(location, specimen), win)}


@router.get("/trends/findings")
def trend_findings(as_of: date | None = AsOf) -> dict:
    """Significant long-term trends and empirical-threshold crossings, all locations (ANOM-03)."""
    return trends.findings(get_dataset(), resolve_as_of(as_of))


@router.get("/trends/series")
def trend_series(
    organism: str,
    antibiotic: str,
    location: str = Query("all"),
    specimen: Specimen = "urine",
    as_of: date | None = AsOf,
) -> dict:
    """Quarterly resistance with the fitted trend, calendar years and year-vs-year (V6)."""
    ds = get_dataset()
    if (organism, antibiotic) not in ds.tested_pairs:
        raise HTTPException(422, f"{organism} is not tested for {antibiotic}")
    scope = _scope(location, specimen)
    return trends.series(ds, scope, organism, antibiotic, resolve_as_of(as_of))


@router.get("/overview")
def ward_overview(
    metric: Literal["phenotype", "rate"] = "phenotype",
    phenotype: str = "ESBL",
    specimen: Specimen = "urine",
    organism: str | None = None,
    antibiotic: str | None = None,
    bins: int = Query(26, ge=4, le=104),
    bin_days: int = Query(7, ge=1, le=91),
    as_of: date | None = AsOf,
) -> dict:
    """Ward × time grid of phenotype cases or a resistance rate, with alert markers (V5)."""
    as_of = resolve_as_of(as_of)
    ds = get_dataset()
    if metric == "phenotype":
        if phenotype not in config.PHENOTYPES:
            raise HTTPException(422, f"unknown phenotype: {phenotype}")
        grid = overview.phenotype_grid(ds, as_of, phenotype, bins, bin_days)

        def related(e: engine.Episode) -> bool:
            return e.subject == phenotype or e.subject.startswith(f"{phenotype}|")
    else:
        if not organism or not antibiotic or (organism, antibiotic) not in ds.tested_pairs:
            raise HTTPException(422, "a rate needs a tested organism and antibiotic")
        grid = overview.rate_grid(ds, as_of, specimen, organism, antibiotic, bins, bin_days)

        def related(e: engine.Episode) -> bool:
            return (
                e.type == "rate_shift"
                and e.subject == f"{specimen}|{organism}"
                and any(
                    s["antibiotic_code"] == antibiotic
                    for f in e.up_to(as_of)
                    for s in f.evidence["shifts"]
                )
            )

    events = [
        {
            "id": e.id,
            "type": e.type,
            "type_label": config.ALERT_TYPES[e.type]["label"],
            "severity": config.ALERT_TYPES[e.type]["severity"],
            "ward": e.ward,
            "first_seen": e.first.isoformat(),
            "title": e.firings[0].title,
        }
        for e in engine.timeline(ds, as_of)
        if e.first <= as_of and related(e)
    ]
    ward_names = ds.wards.set_index("ward_code").ward_en.to_dict()
    for row in grid["rows"]:
        row["label"] = ward_names.get(row["ward"], ALL_LABEL)
    return {
        "as_of": as_of.isoformat(),
        "metric": metric,
        "phenotype": phenotype if metric == "phenotype" else None,
        "specimen": specimen if metric == "rate" else None,
        "organism": organism,
        "antibiotic": antibiotic,
        "bin_days": bin_days,
        **overview.add_markers(grid, events),
    }


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


@router.get("/replay/events")
def replay_events(store: Store) -> dict:
    """Every alert raised up to today, with a replay start before its onset (LIVE-04) and its
    detection latency (ANOM-07)."""
    today = get_store().today()
    events = engine.replay_events(get_dataset(), today, store)
    return {"today": today.isoformat(), "events": events}


@router.post("/ingest")
def ingest(
    records: Annotated[
        dict[str, list[dict]],
        Body(
            description="New rows per table (patients, cultures, isolates, susceptibility), with "
            "the same columns as the CSVs. Checked as a whole: nothing changes if a check fails."
        ),
    ],
) -> dict:
    """Receive new lab data (DATA-05). Alerts are recomputed only from the earliest sample date
    the batch touches."""
    store = get_store()
    try:
        return store.ingest(batch_from_records(records, store.tables))
    except IngestError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/ingest/held-back")
def ingest_held_back(days: int = Query(1, ge=1, le=31)) -> dict:
    """Simulated lab feed: receive the next days of held-back data through the same ingestion
    path (only when the server was started with AEI_HOLD_BACK_FROM)."""
    try:
        return get_store().receive_held_back(days)
    except IngestError as e:
        raise HTTPException(409, str(e)) from e


@router.delete("/triage")
def reset_triage(store: Store) -> dict:
    """Clear all triage state (demo reset)."""
    store.clear()
    return {"status": "cleared"}
