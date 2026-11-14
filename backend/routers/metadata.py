"""Metadata endpoint exposing sensor definitions, versions, timezones, and profiles."""
from __future__ import annotations

from fastapi import APIRouter
from backend.schemas.metadata import MetadataResponse
from backend.services.duckdb_service import duckdb_service

router = APIRouter(prefix="/api/v1", tags=["Metadata"])


@router.get("/metadata", response_model=MetadataResponse)
def get_metadata() -> MetadataResponse:
    """Return platform metadata, common-period calendar boundaries, supported sensors, and matching profiles."""
    return MetadataResponse(**duckdb_service.get_metadata())
