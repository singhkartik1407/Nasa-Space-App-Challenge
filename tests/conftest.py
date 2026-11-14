"""Pytest fixtures for FireScope test suite without Starlette TestClient deadlocks."""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse
import pytest
from fastapi import HTTPException, Response

from backend.database import Base, SessionLocal, engine, init_db
from backend.routers.analytics import (
    get_activity,
    get_frp_analytics,
    get_relationship_analytics,
    get_sensors_analytics,
)
from backend.routers.candidates import get_candidate, list_candidates
from backend.routers.detections import get_detection, list_detections
from backend.routers.health import get_health, get_ready
from backend.routers.jobs import (
    create_matching_job,
    create_review_annotation,
    get_matching_job,
    list_review_annotations,
)
from backend.routers.metadata import get_metadata
from backend.routers.overview import get_overview
from backend.schemas.jobs import CreateJobRequest, ReviewAnnotationCreate


class MockResponse:
    def __init__(self, status_code: int, data: any):
        self.status_code = status_code
        self._data = data

    def json(self):
        if hasattr(self._data, "model_dump"):
            return self._data.model_dump(mode="json")
        elif isinstance(self._data, list):
            return [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in self._data]
        elif isinstance(self._data, dict):
            return self._data
        return self._data


class DirectAppClient:
    """Fast, deadlock-free client directly invoking typed FastAPI route handlers."""

    def __init__(self):
        init_db()

    def get(self, url: str) -> MockResponse:
        parsed = urlparse(url)
        path = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        try:
            if path == "/health":
                res = get_health()
                return MockResponse(200, res)

            elif path == "/ready":
                resp = Response()
                res = get_ready(resp)
                return MockResponse(resp.status_code or 200, res)

            elif path == "/api/v1/metadata":
                res = get_metadata()
                return MockResponse(200, res)

            elif path == "/api/v1/overview":
                s_date = query.get("start_date", "2024-03-01")
                e_date = query.get("end_date", "2024-03-31")
                prof = query.get("profile", "A")
                res = get_overview(start_date=s_date, end_date=e_date, profile=prof)
                return MockResponse(200, res)

            elif path == "/api/v1/detections":
                kwargs = {
                    "sensor": query.get("sensor", "ALL"),
                    "start_date": query.get("start_date"),
                    "end_date": query.get("end_date"),
                    "daynight": query.get("daynight"),
                    "page": int(query.get("page", 1)),
                    "page_size": int(query.get("page_size", 50)),
                    "sort_by": query.get("sort_by", "acq_datetime_utc"),
                    "sort_order": query.get("sort_order", "desc"),
                }
                if "min_lat" in query:
                    kwargs["min_lat"] = float(query["min_lat"])
                if "max_lat" in query:
                    kwargs["max_lat"] = float(query["max_lat"])
                if "min_lon" in query:
                    kwargs["min_lon"] = float(query["min_lon"])
                if "max_lon" in query:
                    kwargs["max_lon"] = float(query["max_lon"])
                if "min_frp" in query:
                    kwargs["min_frp"] = float(query["min_frp"])
                if "max_frp" in query:
                    kwargs["max_frp"] = float(query["max_frp"])

                res = list_detections(**kwargs)
                return MockResponse(200, res)

            elif path.startswith("/api/v1/detections/"):
                row_id = path.replace("/api/v1/detections/", "")
                res = get_detection(row_id)
                return MockResponse(200, res)

            elif path == "/api/v1/candidates":
                kwargs = {
                    "profile": query.get("profile", "A"),
                    "start_date": query.get("start_date", "2024-03-01"),
                    "end_date": query.get("end_date", "2024-03-31"),
                    "page": int(query.get("page", 1)),
                    "page_size": int(query.get("page_size", 50)),
                    "sort_by": query.get("sort_by", "distance_km"),
                    "sort_order": query.get("sort_order", "asc"),
                }
                if "min_lat" in query:
                    kwargs["min_lat"] = float(query["min_lat"])
                if "max_lat" in query:
                    kwargs["max_lat"] = float(query["max_lat"])
                if "min_lon" in query:
                    kwargs["min_lon"] = float(query["min_lon"])
                if "max_lon" in query:
                    kwargs["max_lon"] = float(query["max_lon"])
                if "min_distance_km" in query:
                    kwargs["min_distance_km"] = float(query["min_distance_km"])
                if "max_distance_km" in query:
                    kwargs["max_distance_km"] = float(query["max_distance_km"])

                res = list_candidates(**kwargs)
                return MockResponse(200, res)

            elif path.startswith("/api/v1/candidates/"):
                candidate_id = path.replace("/api/v1/candidates/", "")
                res = get_candidate(candidate_id)
                return MockResponse(200, res)

            elif path == "/api/v1/analytics/activity":
                s_date = query.get("start_date", "2024-03-01")
                e_date = query.get("end_date", "2024-03-31")
                interval = query.get("interval", "day")
                tz_name = query.get("timezone", "UTC")
                res = get_activity(start_date=s_date, end_date=e_date, interval=interval, timezone=tz_name)
                return MockResponse(200, res)

            elif path == "/api/v1/analytics/frp":
                s_date = query.get("start_date", "2024-03-01")
                e_date = query.get("end_date", "2024-03-31")
                res = get_frp_analytics(start_date=s_date, end_date=e_date)
                return MockResponse(200, res)

            elif path == "/api/v1/analytics/sensors":
                res = get_sensors_analytics()
                return MockResponse(200, res)

            elif path == "/api/v1/analytics/relationships":
                period = query.get("period", "2024-03")
                res = get_relationship_analytics(period=period)
                return MockResponse(200, res)

            elif path.startswith("/api/v1/matching/jobs/"):
                job_id = path.replace("/api/v1/matching/jobs/", "")
                db = SessionLocal()
                try:
                    res = get_matching_job(job_id, db)
                    return MockResponse(200, res)
                finally:
                    db.close()

            elif path == "/api/v1/review/annotations":
                db = SessionLocal()
                try:
                    res = list_review_annotations(db)
                    return MockResponse(200, res)
                finally:
                    db.close()

            return MockResponse(404, {"detail": f"Route not found: {path}"})

        except HTTPException as he:
            return MockResponse(he.status_code, {"detail": he.detail})
        except Exception as e:
            return MockResponse(500, {"detail": str(e)})

    def post(self, url: str, json: dict = None) -> MockResponse:
        parsed = urlparse(url)
        path = parsed.path
        data = json or {}

        try:
            if path == "/api/v1/matching/jobs":
                req = CreateJobRequest(**data)
                db = SessionLocal()
                try:
                    res = create_matching_job(req, db)
                    return MockResponse(201, res)
                finally:
                    db.close()

            elif path == "/api/v1/review/annotations":
                req = ReviewAnnotationCreate(**data)
                db = SessionLocal()
                try:
                    res = create_review_annotation(req, db)
                    return MockResponse(201, res)
                finally:
                    db.close()

            return MockResponse(404, {"detail": f"Route not found: {path}"})

        except HTTPException as he:
            return MockResponse(he.status_code, {"detail": he.detail})
        except Exception as e:
            return MockResponse(500, {"detail": str(e)})


@pytest.fixture(scope="session")
def client():
    """Create test client for testing."""
    return DirectAppClient()


@pytest.fixture(scope="function")
def db_session():
    """Create isolated database session for testing."""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
