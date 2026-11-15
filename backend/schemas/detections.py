"""Pydantic schemas for detection records and list responses."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from backend.schemas.common import PaginationMeta


class DetectionItem(BaseModel):
    row_id: str
    sensor: str
    satellite: str
    latitude: float
    longitude: float
    acq_datetime_utc: str
    scan_km: Optional[float] = None
    track_km: Optional[float] = None
    pixel_area_km2: Optional[float] = None
    frp_mw: Optional[float] = None
    confidence_raw: Optional[str] = None
    daynight: Optional[str] = None
    version: Optional[str] = None
    source_product: Optional[str] = None
    source_file: Optional[str] = None
    source_row: Optional[int] = None


class DetectionListResponse(BaseModel):
    items: List[DetectionItem]
    pagination: PaginationMeta
    filters_applied: Dict[str, Any]


class CandidateMatchSummary(BaseModel):
    candidate_id: str
    modis_row_id: str
    viirs_row_id: str
    distance_km: float
    time_diff_minutes: float
    footprint_radius_sum_km: float
    modis_datetime_utc: str
    viirs_datetime_utc: str
    modis_frp_mw: Optional[float] = None
    viirs_frp_mw: Optional[float] = None


class DetectionDetailResponse(BaseModel):
    row_id: str
    sensor: str
    satellite: str
    latitude: float
    longitude: float
    acq_datetime_utc: str
    scan_km: Optional[float] = None
    track_km: Optional[float] = None
    pixel_area_km2: Optional[float] = None
    frp_mw: Optional[float] = None
    confidence_raw: Optional[str] = None
    daynight: Optional[str] = None
    version: Optional[str] = None
    hotspot_type: Optional[str] = None
    source_product: Optional[str] = None
    source_file: Optional[str] = None
    source_row: Optional[int] = None
    candidate_matches_count: int = 0
    candidate_matches: List[CandidateMatchSummary] = []


class MapAggregateCellProperties(BaseModel):
    cell_id: str
    latitude: float
    longitude: float
    total_count: int
    modis_count: int
    viirs_count: int
    modis_avg_frp: float
    viirs_avg_frp: float
    resolution_deg: float


class MapAggregateFeature(BaseModel):
    type: str = "Feature"
    geometry: Dict[str, Any]  # {"type": "Point", "coordinates": [lon, lat]}
    properties: MapAggregateCellProperties


class MapAggregateSummary(BaseModel):
    total_cells: int
    total_observations: int
    modis_observations: int
    viirs_observations: int
    resolution_deg: float


class MapAggregateResponse(BaseModel):
    type: str = "FeatureCollection"
    query: Dict[str, Any]
    summary: MapAggregateSummary
    features: List[MapAggregateFeature]
