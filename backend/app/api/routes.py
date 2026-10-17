"""HTTP API (API-01). The frontend is a client of the same endpoints external systems use.

Every data endpoint takes `as_of` (LIVE-01): results are computed as if that day were today.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app import config
from app.data.dataset import get_dataset
from app.data.freshness import ward_freshness
from app.data.loader import get_tables
from app.data.scope import ALL_LABEL, INSTITUTION_LABELS, Scope
from app.stats.antibiogram import build_antibiogram

router = APIRouter(prefix="/api")

AsOf = Query(None, description="Compute as if this day were today (default: scenario today)")


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
