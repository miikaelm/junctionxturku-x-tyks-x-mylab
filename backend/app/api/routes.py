"""HTTP API (API-01). The frontend is a client of the same endpoints external systems use."""

from fastapi import APIRouter

from app.data.loader import get_tables

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    cultures = get_tables().cultures
    return {
        "status": "ok",
        "cultures": len(cultures),
        "data_start": cultures.sample_date.min().date().isoformat(),
        "data_end": cultures.sample_date.max().date().isoformat(),
    }
