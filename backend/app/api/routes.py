"""HTTP API (API-01). The frontend is a client of the same endpoints external systems use.

Every data endpoint takes `as_of` (LIVE-01): results are computed as if that day were today.
"""

from datetime import date, datetime, timedelta
from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from app import config, demo
from app.alerts import engine, notify, stewardship
from app.alerts.anomalies import anomalies, recent_rises
from app.alerts.detail import episode_detail
from app.alerts.triage import STATUSES, TriageStore, get_triage_store
from app.data import national, windows
from app.data.dataset import get_dataset
from app.data.freshness import feed_status, ward_freshness
from app.data.intrinsic import INTRINSIC_RESISTANCE
from app.data.scope import ALL_LABEL, INSTITUTION_LABELS, Scope
from app.data.store import IngestError, batch_from_records, get_store
from app.patients.registry import carriers, flag_dict, patient_record
from app.stats import overview, trends
from app.stats.antibiogram import SPLIT_DIMENSIONS, Split, build_antibiogram
from app.stats.avoid import avoid, with_recent_rises
from app.stats.spread import spread
from app.stats.subgroups import discover
from app.stats.therapy import therapy

router = APIRouter(prefix="/api")

AsOf = Query(None, description="Compute as if this day were today (default: scenario today)")
PeriodStart = Query(None, description="A custom period instead of 4 weeks + 12 months (inclusive)")
PeriodEnd = Query(None, description="End of the custom period (default: as_of)")
Store = Annotated[TriageStore, Depends(get_triage_store)]
Reviews = Annotated[TriageStore, Depends(stewardship.get_stewardship_store)]
Subs = Annotated[notify.SubscriptionStore, Depends(notify.get_subscription_store)]
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
            {
                "key": key,
                "label": cfg["label"],
                "severity": cfg["severity"],
                "routine": bool(cfg.get("routine")),
                "action": config.ALERT_ACTIONS.get(key),
            }
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
        "infections": [
            {"key": k, "label": v["label"], "specimen": v["specimen"]}
            for k, v in config.THERAPY_INFECTIONS.items()
        ],
        "varha": {
            "label": config.VARHA_LABEL,
            "full": config.VARHA_FULL,
            "hospital": config.VARHA_HOSPITAL,
        },
        "national_source": national.SOURCE,
        "ehr_demo": demo.ehr_demo(),
        "thresholds": {
            "min_isolates": config.MIN_ISOLATES_FOR_PERCENT,
            "good_below": config.RESISTANCE_GOOD_BELOW,
            "warn_below": config.RESISTANCE_WARN_BELOW,
            "ci_level": config.CI_LEVEL,
            "empirical_pct": config.EMPIRICAL_THRESHOLD_PCT,
            "coverage_good": config.THERAPY_GOOD_COVERAGE,
            "coverage_warn": config.THERAPY_WARN_COVERAGE,
        },
    }


@router.get("/antibiogram")
def antibiogram(
    location: str = Query("all", description="Ward code, 'hospital', 'primary_care' or 'all'"),
    specimen: Specimen = "urine",
    sex: Literal["F", "M"] | None = None,
    age_band: str | None = None,
    hospital_acquired: bool | None = None,
    ward_type: Literal["in", "out"] | None = None,
    home_area: str | None = None,
    year: int | None = Query(None, description="Calendar year instead of 4 weeks + 12 months"),
    period_start: date | None = PeriodStart,
    period_end: date | None = PeriodEnd,
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
    """Organism × antibiotic resistance: last 4 weeks and last 12 months, with fallbacks; or one
    period (a calendar year or a custom range, VIEW-02). Cells carry the national reference."""
    ds = get_dataset()
    day = resolve_as_of(as_of)
    if age_band is not None and age_band not in {b for b, _, _ in config.AGE_BANDS}:
        raise HTTPException(422, f"unknown age_band: {age_band}")
    if home_area is not None and home_area not in set(ds.cultures.home_area.dropna()):
        raise HTTPException(422, f"unknown home_area: {home_area}")
    scope = _scope(
        location,
        specimen,
        sex=sex,
        age_band=age_band,
        hospital_acquired=hospital_acquired,
        ward_type=ward_type,
        home_area=home_area,
    )
    period = None
    try:
        if year is not None:
            if not ds.start.year <= year <= day.year:
                raise ValueError(f"no data for {year} up to {day}")
            period = windows.calendar_year(day, year)
        elif period_start is not None:
            period = windows.custom(day, max(period_start, ds.start.date()), period_end or day)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
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
    return build_antibiogram(ds, scope, day, split, period)


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


@router.get("/national")
def national_reference() -> dict:
    """Finland-level reference values (DATA-08), as published by THL Finres. Reference only."""
    return {"source": national.SOURCE, "values": national.table()}


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
    out = trends.series(ds, scope, organism, antibiotic, resolve_as_of(as_of))
    return {**out, "national": national.lookup(organism, specimen, antibiotic)}


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
            "wards": e.wards(as_of),
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


# ---------- Patients, spread, therapy (slice 4) ----------


@router.get("/therapy")
def therapy_helper(
    location: str = Query(..., description="Ward code, 'hospital', 'primary_care' or 'all'"),
    infection: Literal["uti", "bloodstream", "wound"] = "uti",
    sex: Literal["F", "M"] | None = None,
    age_band: str | None = None,
    hospital_acquired: bool | None = None,
    as_of: date | None = AsOf,
) -> dict:
    """Which antibiotics are likely to cover this infection here (V2, WISCA): coverage =
    Σ organism share × susceptibility, with a 95 % interval and fallbacks."""
    if age_band is not None and age_band not in {b for b, _, _ in config.AGE_BANDS}:
        raise HTTPException(422, f"unknown age_band: {age_band}")
    scope = _scope(location, sex=sex, age_band=age_band, hospital_acquired=hospital_acquired)
    return therapy(get_dataset(), scope, infection, resolve_as_of(as_of))


@router.get("/carriers")
def carrier_registry(
    location: str | None = Query(None, description="Only carriers positive on these wards"),
    phenotype: str | None = None,
    days: int | None = Query(None, ge=1, description="Only flags first set in the last N days"),
    limit: int = Query(200, ge=1, le=5000),
    as_of: date | None = AsOf,
) -> dict:
    """The carrier registry (PAT-01) on the as-of date, newest flags first. Patient-level data:
    for infection control and lab (NF-03)."""
    as_of = resolve_as_of(as_of)
    reg = carriers(get_dataset(), as_of)
    if phenotype:
        reg = reg[reg.phenotype.eq(phenotype)]
    if (wards := _ward_filter(location)) is not None:
        reg = reg[[bool(wards & set(w)) for w in reg.wards]]
    if days:
        reg = reg[reg.first_positive > pd.Timestamp(as_of) - pd.Timedelta(days=days)]
    return {
        "as_of": as_of.isoformat(),
        "total": len(reg),
        "by_phenotype": reg.phenotype.value_counts().to_dict(),
        "carriers": [flag_dict(r) for r in reg.head(limit).itertuples(index=False)],
    }


@router.get("/patients/{patient_id}")
def patient(patient_id: str, store: Store, as_of: date | None = AsOf) -> dict:
    """One patient: carrier flags, samples and active alerts they are part of (PAT-01, API-03)."""
    as_of = resolve_as_of(as_of)
    ds = get_dataset()
    record = patient_record(ds, patient_id, as_of)
    if record is None:
        raise HTTPException(404, f"no samples for patient {patient_id} up to {as_of}")
    return {
        "as_of": as_of.isoformat(),
        **record,
        "alerts": engine.alerts_for_patient(ds, as_of, store, patient_id),
    }


@router.get("/spread")
def spread_view(
    phenotype: str = "ESBL",
    organism: str | None = None,
    profile: str | None = Query(None, description="Core resistance profile key, e.g. AMP,CRO,CXM"),
    days: int = Query(182, ge=14, le=1100),
    as_of: date | None = AsOf,
) -> dict:
    """Where a phenotype appears across wards over time, by resistance profile, with the case
    patients' paths between wards (V10, PAT-03) and the related cluster / multi-ward alerts."""
    if phenotype not in config.PHENOTYPES:
        raise HTTPException(422, f"unknown phenotype: {phenotype}")
    as_of = resolve_as_of(as_of)
    ds = get_dataset()
    return spread(ds, as_of, phenotype, days, engine.timeline(ds, as_of), organism, profile)


# ---------- Notifications and webhooks (slice 4) ----------


class Subscription(BaseModel):
    id: str
    name: str
    role: Literal["clinician", "infection_control", "lab", "system"]
    channel: Literal["webhook", "email", "teams"]
    target: str
    wards: list[str] | None = None
    min_severity: Literal["critical", "high", "medium", "low", "info"] = "medium"
    types: list[str] | None = None
    include_routine: bool = False
    events: list[Literal["alert", "carrier_flag", "digest"]] = ["alert"]


@router.get("/subscriptions")
def list_subscriptions(subs: Subs) -> dict:
    """Who gets which alerts, by role and ward, and how (NOTIF-03)."""
    return {"subscriptions": subs.all()}


@router.put("/subscriptions/{sub_id}")
def put_subscription(sub_id: str, sub: Subscription, subs: Subs) -> dict:
    if sub.id != sub_id:
        raise HTTPException(422, "id in the body must match the path")
    known = set(get_dataset().wards.ward_code)
    if sub.wards and not set(sub.wards) <= known:
        raise HTTPException(422, f"unknown wards: {sorted(set(sub.wards) - known)}")
    if sub.types and not set(sub.types) <= set(config.ALERT_TYPES):
        raise HTTPException(422, "unknown alert type")
    return subs.put(sub.model_dump())


@router.delete("/subscriptions/{sub_id}")
def delete_subscription(sub_id: str, subs: Subs) -> dict:
    if not subs.delete(sub_id):
        raise HTTPException(404, f"no subscription {sub_id}")
    return {"deleted": sub_id}


@router.post("/subscriptions/reset")
def reset_subscriptions(subs: Subs) -> dict:
    subs.reset()
    return {"subscriptions": subs.all()}


@router.post("/subscriptions/{sub_id}/test")
def test_subscription(sub_id: str, subs: Subs) -> dict:
    """Send a test message through the subscription's channel (webhooks are really POSTed)."""
    sub = subs.get(sub_id)
    if sub is None:
        raise HTTPException(404, f"no subscription {sub_id}")
    today = get_store().today()
    msg = notify.message(
        sub,
        today,
        "test",
        "Test message from AEI",
        "If you can read this, delivery works.",
        {"event": "test", "sent": today.isoformat()},
    )
    notify.deliver([msg])
    return {"queued": msg}


@router.get("/notifications")
def notifications(
    store: Store,
    subs: Subs,
    days: int = Query(7, ge=1, le=92),
    subscription: str | None = None,
    as_of: date | None = AsOf,
) -> dict:
    """Messages each subscription got in the days up to as_of (NOTIF-05): the same alerts the
    inbox shows, so replay shows what was sent when. Email and Teams are simulated."""
    as_of = resolve_as_of(as_of)
    chosen = [s for s in subs.all() if subscription in (None, s["id"])]
    start = max(get_dataset().start.date(), as_of - timedelta(days=days - 1))
    messages = notify.planned(get_dataset(), store, chosen, start, as_of)
    return {"as_of": as_of.isoformat(), "start": start.isoformat(), "messages": messages}


@router.get("/notifications/deliveries")
def deliveries() -> dict:
    """Live delivery log: messages sent when new data arrived (DATA-05), webhook results."""
    return {"deliveries": list(notify.DELIVERIES)}


@router.get("/digest")
def digest(
    store: Store,
    period: Literal["week", "month"] = "week",
    as_of: date | None = AsOf,
) -> dict:
    """Periodic summary (NOTIF-05): new alerts, carriers, data gaps, long-term trend findings."""
    return notify.digest(get_dataset(), store, resolve_as_of(as_of), period)


@router.post("/mock-ehr/inbox")
def mock_ehr_receive(payload: Annotated[dict, Body()]) -> dict:
    """Mock receiver standing in for the hospital's patient record system (API-04 demo)."""
    entry = {"received": datetime.now().isoformat(timespec="seconds"), "payload": payload}
    notify.MOCK_INBOX.appendleft(entry)
    return {"ok": True}


@router.get("/mock-ehr/inbox")
def mock_ehr_inbox() -> dict:
    return {"messages": list(notify.MOCK_INBOX)}


@router.delete("/mock-ehr/inbox")
def mock_ehr_clear() -> dict:
    notify.MOCK_INBOX.clear()
    return {"cleared": True}


# ---------- Exceptions first (slice 5) ----------


@router.get("/anomalies")
def anomaly_overview(store: Store, as_of: date | None = AsOf) -> dict:
    """Anomalies per ward, institution and Varha for the exceptions-first drill-down (UX-02/03):
    active non-routine alerts and feed problems; counts only, no overall resistance %."""
    return anomalies(get_dataset(), resolve_as_of(as_of), store)


@router.get("/avoid")
def avoid_list(
    store: Store,
    reviews: Reviews,
    location: str = Query(..., description="Ward code, 'hospital', 'primary_care' or 'all'"),
    infection: Literal["uti", "bloodstream", "wound"] = "uti",
    sex: Literal["F", "M"] | None = None,
    age_band: str | None = None,
    hospital_acquired: bool | None = None,
    as_of: date | None = AsOf,
) -> dict:
    """What not to use for this infection here (UX-05, UX-07): agents a main organism is ≥ 20 %
    resistant to over the last 12 months, with since when, the direction and the stewardship
    finding's review status, plus recent rises (active resistance-shift alerts) the 12-month
    figures don't show yet, with the outbreak they most likely come from."""
    if age_band is not None and age_band not in {b for b, _, _ in config.AGE_BANDS}:
        raise HTTPException(422, f"unknown age_band: {age_band}")
    scope = _scope(location, sex=sex, age_band=age_band, hospital_acquired=hospital_acquired)
    ds, day = get_dataset(), resolve_as_of(as_of)
    result = avoid(ds, scope, infection, day)
    result = stewardship.attach(ds, result, scope, infection, day, reviews)
    rises = recent_rises(ds, day, store, scope.ward_codes(ds.wards), result["specimen"])
    return with_recent_rises(result, rises)


# ---------- Stewardship findings (ANOM-10) ----------


@router.get("/stewardship")
def stewardship_findings(reviews: Reviews, as_of: date | None = AsOf) -> dict:
    """Long-standing resistance for lab / stewardship to review: threshold crossings, agents
    above the limit since before the data, and significant rises still under it."""
    return stewardship.findings(get_dataset(), resolve_as_of(as_of), reviews)


@router.get("/stewardship/{finding_id}")
def stewardship_finding(finding_id: str, reviews: Reviews, as_of: date | None = AsOf) -> dict:
    as_of = resolve_as_of(as_of)
    f = stewardship.finding(get_dataset(), as_of, reviews, finding_id)
    if f is None:
        raise HTTPException(404, f"no finding {finding_id} as of {as_of}")
    ref = national.lookup(f["organism"], f["specimen"], f["antibiotic_code"])
    return {"as_of": as_of.isoformat(), **f, "national": ref}


class ReviewAction(BaseModel):
    status: Literal["new", "under_review", "guideline_updated", "accepted"]
    note: str = ""
    as_of: date | None = None


@router.post("/stewardship/{finding_id}/review")
def review_finding(finding_id: str, action: ReviewAction, reviews: Reviews) -> dict:
    """Record a review step. Like triage, it applies from its as-of date on."""
    as_of = resolve_as_of(action.as_of)
    if stewardship.finding(get_dataset(), as_of, reviews, finding_id) is None:
        raise HTTPException(404, f"no finding {finding_id} as of {as_of}")
    entry = reviews.add(finding_id, action.status, as_of, action.note)
    return {"id": finding_id, **entry}
