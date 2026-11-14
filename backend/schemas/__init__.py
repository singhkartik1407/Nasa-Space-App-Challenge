"""Pydantic schemas package for FireScope API."""
from backend.schemas.common import HealthResponse, PaginationMeta, ReadyResponse
from backend.schemas.metadata import MetadataResponse
from backend.schemas.overview import OverviewResponse
from backend.schemas.detections import DetectionDetailResponse, DetectionItem, DetectionListResponse
from backend.schemas.candidates import CandidateDetailResponse, CandidateEdgeItem, CandidateListResponse
from backend.schemas.analytics import (
    ActivityResponse,
    FrpAnalyticsResponse,
    RelationshipAnalyticsResponse,
    SensorAnalyticsResponse,
)
from backend.schemas.jobs import (
    CreateJobRequest,
    JobStatusResponse,
    ReviewAnnotationCreate,
    ReviewAnnotationResponse,
)

__all__ = [
    "HealthResponse",
    "ReadyResponse",
    "PaginationMeta",
    "MetadataResponse",
    "OverviewResponse",
    "DetectionItem",
    "DetectionDetailResponse",
    "DetectionListResponse",
    "CandidateEdgeItem",
    "CandidateDetailResponse",
    "CandidateListResponse",
    "ActivityResponse",
    "FrpAnalyticsResponse",
    "SensorAnalyticsResponse",
    "RelationshipAnalyticsResponse",
    "CreateJobRequest",
    "JobStatusResponse",
    "ReviewAnnotationCreate",
    "ReviewAnnotationResponse",
]
