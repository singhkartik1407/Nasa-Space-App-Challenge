"""API routers package for FireScope backend."""
from backend.routers.health import router as health_router
from backend.routers.metadata import router as metadata_router
from backend.routers.overview import router as overview_router
from backend.routers.detections import router as detections_router
from backend.routers.candidates import router as candidates_router
from backend.routers.analytics import router as analytics_router
from backend.routers.jobs import router as jobs_router

__all__ = [
    "health_router",
    "metadata_router",
    "overview_router",
    "detections_router",
    "candidates_router",
    "analytics_router",
    "jobs_router",
]
