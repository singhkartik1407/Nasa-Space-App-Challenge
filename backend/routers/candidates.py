"""Candidates endpoints for querying cross-sensor candidate relationships."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from backend.schemas.candidates import CandidateDetailResponse, CandidateListResponse
from backend.services.duckdb_service import duckdb_service

router = APIRouter(prefix="/api/v1", tags=["Candidates"])


@router.get("/candidates", response_model=CandidateListResponse)
def list_candidates(
    profile: str = Query(default="A", description="Profile ID (A=1h/0km default, B=3h/0km alternative, C, D, E)"),
    start_date: Optional[str] = Query(default="2024-03-01", pattern=r"^\d{4}-\d{2}-\d{2}$", description="Start date (YYYY-MM-DD, UTC)"),
    end_date: Optional[str] = Query(default="2024-03-31", pattern=r"^\d{4}-\d{2}-\d{2}$", description="End date (YYYY-MM-DD, UTC)"),
    min_lat: Optional[float] = Query(default=None, ge=-90.0, le=90.0, description="Minimum latitude"),
    max_lat: Optional[float] = Query(default=None, ge=-90.0, le=90.0, description="Maximum latitude"),
    min_lon: Optional[float] = Query(default=None, ge=-180.0, le=180.0, description="Minimum longitude"),
    max_lon: Optional[float] = Query(default=None, ge=-180.0, le=180.0, description="Maximum longitude"),
    min_distance_km: Optional[float] = Query(default=None, ge=0.0, description="Minimum distance between centers (km)"),
    max_distance_km: Optional[float] = Query(default=None, ge=0.0, description="Maximum distance between centers (km)"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=500, description="Page size (max 500)"),
    sort_by: str = Query(default="distance_km", description="Sort field: distance_km, time_diff_minutes"),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$", description="Sort order: asc or desc"),
) -> CandidateListResponse:
    """Retrieve candidate cross-sensor pairs evaluated under the specified matching profile."""
    result = duckdb_service.get_candidates(
        profile_id=profile,
        start_date=start_date,
        end_date=end_date,
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
        min_distance_km=min_distance_km,
        max_distance_km=max_distance_km,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return CandidateListResponse(**result)


@router.get("/candidates/{candidate_id}", response_model=CandidateDetailResponse)
def get_candidate(candidate_id: str) -> CandidateDetailResponse:
    """Retrieve complete pair detail for a single candidate relationship (candidate_id format: {modis_id}__{viirs_id})."""
    record = duckdb_service.get_candidate_by_id(candidate_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate relationship '{candidate_id}' not found.",
        )
    return CandidateDetailResponse(**record)
