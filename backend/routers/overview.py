"""Overview endpoint providing high-level metrics for dashboard cards."""
from __future__ import annotations

from fastapi import APIRouter, Query
from backend.schemas.overview import OverviewResponse
from backend.services.duckdb_service import duckdb_service

router = APIRouter(prefix="/api/v1", tags=["Overview"])


@router.get("/overview", response_model=OverviewResponse)
def get_overview(
    start_date: str = Query(default="2024-03-01", pattern=r"^\d{4}-\d{2}-\d{2}$", description="Start date (YYYY-MM-DD, UTC)"),
    end_date: str = Query(default="2024-03-31", pattern=r"^\d{4}-\d{2}-\d{2}$", description="End date (YYYY-MM-DD, UTC)"),
    profile: str = Query(default="A", description="Candidate matching profile (A=1h/0km default, B=3h/0km)"),
) -> OverviewResponse:
    """Return summary indicators, sensor-separated observation counts, FRP aggregates, and candidate matching counts."""
    data = duckdb_service.get_overview(
        start_date_str=start_date,
        end_date_str=end_date,
        profile_id=profile,
    )
    return OverviewResponse(**data)
