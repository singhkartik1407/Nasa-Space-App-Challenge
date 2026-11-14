"""Pydantic schemas for candidate pair edges and detailed pair view."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from backend.schemas.common import PaginationMeta
from backend.schemas.overview import ProfileBrief


class CandidateEdgeItem(BaseModel):
    candidate_id: str
    modis_row_id: str
    viirs_row_id: str
    distance_km: float
    time_diff_minutes: float
    modis_footprint_radius_km: float
    viirs_footprint_radius_km: float
    footprint_radius_sum_km: float
    modis_datetime_utc: str
    viirs_datetime_utc: str
    modis_latitude: float
    modis_longitude: float
    viirs_latitude: float
    viirs_longitude: float
    modis_satellite: str
    viirs_satellite: str
    modis_frp_mw: Optional[float] = None
    viirs_frp_mw: Optional[float] = None
    modis_confidence_raw: Optional[str] = None
    viirs_confidence_raw: Optional[str] = None
    modis_version: Optional[str] = None
    viirs_version: Optional[str] = None


class CandidateListResponse(BaseModel):
    items: List[CandidateEdgeItem]
    profile: ProfileBrief
    pagination: PaginationMeta
    source_parquet: Optional[str] = None
    message: Optional[str] = None


class CandidateDetailResponse(BaseModel):
    candidate_id: str
    modis_row_id: str
    viirs_row_id: str
    distance_km: float
    time_diff_minutes: float
    modis_footprint_radius_km: float
    viirs_footprint_radius_km: float
    footprint_radius_sum_km: float
    max_rule_threshold_km: float
    modis_datetime_utc: str
    viirs_datetime_utc: str
    modis_latitude: float
    modis_longitude: float
    viirs_latitude: float
    viirs_longitude: float
    modis_scan_km: Optional[float] = None
    modis_track_km: Optional[float] = None
    viirs_scan_km: Optional[float] = None
    viirs_track_km: Optional[float] = None
    modis_satellite: str
    viirs_satellite: str
    modis_frp_mw: Optional[float] = None
    viirs_frp_mw: Optional[float] = None
    modis_confidence_raw: Optional[str] = None
    viirs_confidence_raw: Optional[str] = None
    modis_daynight: Optional[str] = None
    viirs_daynight: Optional[str] = None
    modis_version: Optional[str] = None
    viirs_version: Optional[str] = None
    modis_raw_version: Optional[str] = None
    viirs_raw_version: Optional[str] = None
    modis_source_file: Optional[str] = None
    viirs_source_file: Optional[str] = None
    modis_pixel_size_assumed: Optional[bool] = None
    viirs_pixel_size_assumed: Optional[bool] = None
