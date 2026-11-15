"""Pydantic schemas for platform, sensor, and threshold metadata."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


class SensorInfo(BaseModel):
    sensor: str
    satellites: List[str]
    nominal_pixel_resolution_km: float
    versions: List[str]
    frp_unit: str = "MW"


class ThresholdProfileSchema(BaseModel):
    id: str
    name: str
    label: str
    time_limit_minutes: float
    additional_buffer_km: float
    role: str
    description: str
    is_default: bool
    is_selectable: bool


class AuditedPeriodSummary(BaseModel):
    period_id: str
    start_date: str
    end_date: str
    modis_detections: int
    viirs_detections: int
    candidate_superset_edges: int
    profile_a_edges: int
    profile_b_edges: int
    modis_version: str
    viirs_version: str


class ProcessedMatchingPeriod(BaseModel):
    period_id: str
    start_date: str
    end_date: str
    modis_detections: int
    viirs_detections: int
    candidate_superset_edges: int
    profile_a_edges: int
    profile_b_edges: int
    status: str = "COMPLETED"
    is_pilot: bool = False


class DatasetWindow(BaseModel):
    start_date: str
    end_date: str
    canonical_timezone: str
    display_timezones: List[str]
    total_days: int


class MetadataResponse(BaseModel):
    dataset_window: DatasetWindow
    sensors: List[SensorInfo]
    threshold_profiles: List[ThresholdProfileSchema]
    default_profile: str
    alternative_profile: str
    audited_pilot_periods: List[AuditedPeriodSummary]
    processed_matching_periods: List[ProcessedMatchingPeriod] = []
    scientific_guidelines: List[str]
