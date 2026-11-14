"""Main FastAPI application factory and entry point for FireScope."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.database import init_db
from backend.routers import (
    analytics_router,
    candidates_router,
    detections_router,
    health_router,
    jobs_router,
    metadata_router,
    overview_router,
)
from backend.services.duckdb_service import duckdb_service

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("firescope")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle management."""
    logger.info("Starting FireScope API version %s...", settings.app_version)
    # 1. Initialize metadata database
    try:
        init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)

    # 2. Check DuckDB / Parquet readiness
    readiness = duckdb_service.check_readiness()
    if readiness.get("ready"):
        logger.info(
            "Parquet data sources verified. MODIS rows: %s, VIIRS rows: %s",
            readiness.get("modis_total_rows"),
            readiness.get("viirs_total_rows"),
        )
    else:
        logger.warning("DuckDB data readiness check reported issues: %s", readiness.get("error"))

    yield
    logger.info("Shutting down FireScope API.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "FireScope REST API harmonizing NASA FIRMS active-fire observations "
            "from MODIS (Terra/Aqua) and Suomi-NPP VIIRS (375 m). "
            "Provides high-performance analytical queries directly over Parquet via DuckDB."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Configure CORS for frontend development and production origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler for uncaught server errors
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred during request processing.",
                "detail": str(exc) if settings.debug else "Internal server error",
            },
        )

    # Include routers
    app.include_router(health_router)
    app.include_router(metadata_router)
    app.include_router(overview_router)
    app.include_router(detections_router)
    app.include_router(candidates_router)
    app.include_router(analytics_router)
    app.include_router(jobs_router)

    @app.get("/", tags=["Health & System"])
    def root():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "status": "online",
            "docs": "/docs",
            "metadata": f"{settings.api_prefix}/metadata",
            "overview": f"{settings.api_prefix}/overview",
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
