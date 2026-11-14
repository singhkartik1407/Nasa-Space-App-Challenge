"""Pydantic schemas for activity, FRP, sensor comparison, and relationship analytics."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ActivityBucket(BaseModel):
    time_bucket: str
    modis_count: int
    viirs_count: int


class ActivityResponse(BaseModel):
    interval: str
    timezone: str
    start_date: str
    end_date: str
    data: List[ActivityBucket]


class SensorFrpDistribution(BaseModel):
    sensor: str
    detection_count: int
    total_frp_mw: float
    mean_frp_mw: float
    median_frp_mw: float
    p25_frp_mw: float
    p75_frp_mw: float
    p95_frp_mw: float
    max_frp_mw: float


class FrpAnalyticsResponse(BaseModel):
    period: Dict[str, str]
    unit: str = "MW"
    modis: SensorFrpDistribution
    viirs: SensorFrpDistribution
    note: str


class SensorVersionItem(BaseModel):
    version: str
    count: int


class SensorSummaryDetail(BaseModel):
    sensor: str
    nominal_pixel_resolution_km: float
    common_period_detections: int
    version_distribution: List[SensorVersionItem]
    satellites: List[str]


class SensorAnalyticsResponse(BaseModel):
    modis: SensorSummaryDetail
    viirs: SensorSummaryDetail


class ProfileSensitivityItem(BaseModel):
    profile: str
    candidate_edges: int
    modis_with_candidates: int
    viirs_with_candidates: int
    components: int
    one_to_one_components: int
    one_to_one_share_pct: float
    components_over_5km: int
    components_over_3h: int


class RelationshipAnalyticsResponse(BaseModel):
    period: str
    modis_detections: int
    viirs_detections: int
    candidate_superset_edges: int
    profile_sensitivity: List[ProfileSensitivityItem]
    graph_interpretation: str
