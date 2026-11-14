"""Common Pydantic models for pagination, filtering, and system responses."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PaginationMeta(BaseModel):
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Number of items per page")
    total_items: int = Field(..., ge=0, description="Total matching items across all pages")
    total_pages: int = Field(..., ge=0, description="Total pages available")
    has_next: bool = Field(..., description="Whether a next page exists")
    has_prev: bool = Field(..., description="Whether a previous page exists")


class HealthResponse(BaseModel):
    status: str = "ok"
    app_name: str
    app_version: str
    environment: str


class ReadyResponse(BaseModel):
    ready: bool
    status: str
    modis_parquet_exists: bool
    viirs_parquet_exists: bool
    modis_total_rows: Optional[int] = None
    viirs_total_rows: Optional[int] = None
    error: Optional[str] = None
