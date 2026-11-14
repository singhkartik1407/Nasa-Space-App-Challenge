"""Pydantic schemas for the dashboard overview endpoint."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class SensorFrpSummary(BaseModel):
    sensor: str
    total_frp_mw: float
    mean_frp_mw: float
    median_frp_mw: float
    max_frp_mw: float


class DetectionCountsSummary(BaseModel):
    modis_detection_count: int
    viirs_detection_count: int
    total_observations: int
    note: str


class FrpSummaryGroup(BaseModel):
    modis: SensorFrpSummary
    viirs: SensorFrpSummary
    interpretation: str


class MatchingOverviewSummary(BaseModel):
    available: bool
    candidate_edge_count: int
    modis_with_candidates: int
    viirs_with_candidates: int
    modis_without_candidates: int
    viirs_without_candidates: int
    exclusivity_interpretation: str
    candidate_source_file: Optional[str] = None


class ProfileBrief(BaseModel):
    id: str
    name: str
    label: str
    time_limit_minutes: float
    additional_buffer_km: float
    role: str


class QueryPeriod(BaseModel):
    start_date: str
    end_date: str
    timezone: str = "UTC"


class OverviewResponse(BaseModel):
    query_period: QueryPeriod
    profile: ProfileBrief
    detections: DetectionCountsSummary
    frp_mw: FrpSummaryGroup
    matching: MatchingOverviewSummary
