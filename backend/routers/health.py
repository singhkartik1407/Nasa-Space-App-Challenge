"""Health and readiness check endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Response, status
from backend.config import settings
from backend.schemas.common import HealthResponse, ReadyResponse
from backend.services.duckdb_service import duckdb_service

router = APIRouter(tags=["Health & System"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Basic liveness probe checking that the application process is running."""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        app_version=settings.app_version,
        environment=settings.app_env,
    )


@router.get("/ready", response_model=ReadyResponse)
def get_ready(response: Response) -> ReadyResponse:
    """Readiness probe checking that required Parquet data files exist and DuckDB is queryable."""
    res = duckdb_service.check_readiness()
    if not res.get("ready"):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(
            ready=False,
            status="unready",
            modis_parquet_exists=res.get("modis_parquet_exists", False),
            viirs_parquet_exists=res.get("viirs_parquet_exists", False),
            error=res.get("error", "Data storage unavailable"),
        )

    return ReadyResponse(
        ready=True,
        status="ready",
        modis_parquet_exists=res["modis_parquet_exists"],
        viirs_parquet_exists=res["viirs_parquet_exists"],
        modis_total_rows=res.get("modis_total_rows"),
        viirs_total_rows=res.get("viirs_total_rows"),
    )
