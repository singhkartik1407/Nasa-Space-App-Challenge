"""Pydantic schemas for matching job execution and review annotations."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Start date YYYY-MM-DD")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="End date YYYY-MM-DD")
    profile_id: str = Field(default="A", description="Profile ID (A, B, C, D, E)")


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # PENDING, RUNNING, COMPLETED, FAILED
    progress_percent: float
    start_date: str
    end_date: str
    profile_id: str
    created_at: datetime
    updated_at: datetime
    modis_rows_processed: Optional[int] = None
    viirs_rows_processed: Optional[int] = None
    candidate_edges_count: Optional[int] = None
    output_dir: Optional[str] = None
    error_message: Optional[str] = None


class ReviewAnnotationCreate(BaseModel):
    candidate_pair_id: str
    modis_row_id: str
    viirs_row_id: str
    adjudication: str = Field(..., description="MATCH, NON_MATCH, UNCERTAIN")
    notes: Optional[str] = None
    reviewer: Optional[str] = None


class ReviewAnnotationResponse(BaseModel):
    id: int
    candidate_pair_id: str
    modis_row_id: str
    viirs_row_id: str
    adjudication: str
    notes: Optional[str] = None
    reviewer: Optional[str] = None
    created_at: datetime
