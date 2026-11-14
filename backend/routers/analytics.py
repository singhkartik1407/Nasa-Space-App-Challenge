"""Analytics endpoints for activity timeseries, sensor-separated FRP, sensor specs, and graph metrics."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Query
from backend.schemas.analytics import (
    ActivityResponse,
    FrpAnalyticsResponse,
    RelationshipAnalyticsResponse,
    SensorAnalyticsResponse,
)
from backend.services.duckdb_service import duckdb_service

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/activity", response_model=ActivityResponse)
def get_activity(
    start_date: str = Query(default="2024-03-01", pattern=r"^\d{4}-\d{2}-\d{2}$", description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(default="2024-03-31", pattern=r"^\d{4}-\d{2}-\d{2}$", description="End date (YYYY-MM-DD)"),
    interval: str = Query(default="day", pattern="^(day|month)$", description="Aggregation interval: 'day' or 'month'"),
    timezone: str = Query(default="UTC", pattern="^(UTC|IST)$", description="Display timezone: UTC or IST (+05:30)"),
) -> ActivityResponse:
    """Return daily or monthly observation count timeseries separated by sensor with timezone labeling."""
    data = duckdb_service.get_activity_analytics(
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        tz_name=timezone,
    )
    return ActivityResponse(**data)


@router.get("/frp", response_model=FrpAnalyticsResponse)
def get_frp_analytics(
    start_date: str = Query(default="2024-03-01", pattern=r"^\d{4}-\d{2}-\d{2}$", description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(default="2024-03-31", pattern=r"^\d{4}-\d{2}-\d{2}$", description="End date (YYYY-MM-DD)"),
) -> FrpAnalyticsResponse:
    """Return sensor-separated FRP distribution metrics (mean, median, p25, p75, p95, max, total)."""
    data = duckdb_service.get_frp_analytics(start_date=start_date, end_date=end_date)
    return FrpAnalyticsResponse(**data)


@router.get("/sensors", response_model=SensorAnalyticsResponse)
def get_sensors_analytics() -> SensorAnalyticsResponse:
    """Return sensor specifications, product versions, and overall common-period distribution."""
    data = duckdb_service.get_sensors_analytics()
    return SensorAnalyticsResponse(**data)


@router.get("/relationships", response_model=RelationshipAnalyticsResponse)
def get_relationship_analytics(
    period: str = Query(default="2024-03", description="Audited period ID: '2012-03' or '2024-03'"),
) -> RelationshipAnalyticsResponse:
    """Return candidate graph structure, degree sensitivity, and component breakdown for audited periods."""
    data = duckdb_service.get_relationships_analytics(period_id=period)
    return RelationshipAnalyticsResponse(**data)
