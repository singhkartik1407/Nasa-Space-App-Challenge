"""Detections endpoints for filtering, viewport querying, and single observation inspection."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from backend.schemas.detections import (
    DetectionDetailResponse,
    DetectionListResponse,
    MapAggregateResponse,
)
from backend.services.duckdb_service import duckdb_service

router = APIRouter(prefix="/api/v1", tags=["Detections"])


@router.get("/detections", response_model=DetectionListResponse)
def list_detections(
    sensor: str = Query(default="ALL", description="Filter by sensor: 'MODIS', 'VIIRS', or 'ALL'"),
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Start date (YYYY-MM-DD, UTC)"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="End date (YYYY-MM-DD, UTC)"),
    min_lat: Optional[float] = Query(default=None, ge=-90.0, le=90.0, description="Minimum latitude"),
    max_lat: Optional[float] = Query(default=None, ge=-90.0, le=90.0, description="Maximum latitude"),
    min_lon: Optional[float] = Query(default=None, ge=-180.0, le=180.0, description="Minimum longitude"),
    max_lon: Optional[float] = Query(default=None, ge=-180.0, le=180.0, description="Maximum longitude"),
    daynight: Optional[str] = Query(default=None, description="Day/Night: 'D' or 'N'"),
    min_frp: Optional[float] = Query(default=None, ge=0.0, description="Minimum FRP (MW)"),
    max_frp: Optional[float] = Query(default=None, ge=0.0, description="Maximum FRP (MW)"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=500, description="Page size (max 500)"),
    sort_by: str = Query(default="acq_datetime_utc", description="Sort field: acq_datetime_utc, frp_mw, latitude, longitude"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$", description="Sort order: asc or desc"),
) -> DetectionListResponse:
    """Retrieve paginated active fire observations with optional sensor, viewport, and date filters."""
    result = duckdb_service.get_detections(
        sensor=sensor,
        start_date=start_date,
        end_date=end_date,
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
        daynight=daynight,
        min_frp=min_frp,
        max_frp=max_frp,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return DetectionListResponse(**result)


@router.get("/detections/{row_id}", response_model=DetectionDetailResponse)
def get_detection(row_id: str) -> DetectionDetailResponse:
    """Retrieve full detail for a single observation row by its unique row_id, including candidate matches."""
    record = duckdb_service.get_detection_by_id(row_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Detection with row_id '{row_id}' not found.",
        )
    return DetectionDetailResponse(**record)


@router.get("/map/aggregate", response_model=MapAggregateResponse)
def get_map_aggregation(
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Start date (YYYY-MM-DD, UTC)"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="End date (YYYY-MM-DD, UTC)"),
    sensor: str = Query(default="ALL", description="Filter by sensor: 'MODIS', 'VIIRS', or 'ALL'"),
    platform: Optional[str] = Query(default=None, description="Satellite platform: 'Terra', 'Aqua', 'Suomi-NPP'"),
    daynight: Optional[str] = Query(default=None, description="Day/Night: 'D' or 'N'"),
    min_lat: Optional[float] = Query(default=None, ge=-90.0, le=90.0, description="Minimum latitude"),
    max_lat: Optional[float] = Query(default=None, ge=-90.0, le=90.0, description="Maximum latitude"),
    min_lon: Optional[float] = Query(default=None, ge=-180.0, le=180.0, description="Minimum longitude"),
    max_lon: Optional[float] = Query(default=None, ge=-180.0, le=180.0, description="Maximum longitude"),
    resolution_deg: float = Query(default=0.5, ge=0.05, le=2.0, description="Spatial grid cell resolution in degrees"),
    zoom: Optional[float] = Query(default=None, ge=0.0, le=24.0, description="Map zoom level (optional, informs resolution)"),
) -> MapAggregateResponse:
    """Return multi-resolution spatial aggregation grid cells for national and regional overview visualization."""
    s_date = start_date if isinstance(start_date, str) else None
    e_date = end_date if isinstance(end_date, str) else None
    s_sensor = sensor if isinstance(sensor, str) else "ALL"
    s_platform = platform if isinstance(platform, str) else None
    s_daynight = daynight if isinstance(daynight, str) else None
    s_min_lat = min_lat if isinstance(min_lat, (int, float)) else None
    s_max_lat = max_lat if isinstance(max_lat, (int, float)) else None
    s_min_lon = min_lon if isinstance(min_lon, (int, float)) else None
    s_max_lon = max_lon if isinstance(max_lon, (int, float)) else None
    s_res = float(resolution_deg) if isinstance(resolution_deg, (int, float)) else 0.5
    s_zoom = float(zoom) if isinstance(zoom, (int, float)) else None

    effective_res = s_res
    if s_zoom is not None and s_res == 0.5:
        if s_zoom >= 6.0:
            effective_res = 0.15
        else:
            effective_res = 0.5

    result = duckdb_service.get_map_aggregation(
        start_date=s_date,
        end_date=e_date,
        sensor=s_sensor,
        platform=s_platform,
        daynight=s_daynight,
        min_lat=s_min_lat,
        max_lat=s_max_lat,
        min_lon=s_min_lon,
        max_lon=s_max_lon,
        resolution_deg=effective_res,
        zoom=s_zoom,
    )
    return MapAggregateResponse(**result)
