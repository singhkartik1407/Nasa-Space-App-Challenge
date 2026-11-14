"""Integration tests for Foundation endpoints (/health, /ready, /metadata, /overview)."""
import pytest


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "app_name" in data
    assert "app_version" in data


def test_ready_endpoint(client):
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["modis_parquet_exists"] is True
    assert data["viirs_parquet_exists"] is True
    assert data["modis_total_rows"] == 1232096
    assert data["viirs_total_rows"] == 8725086


def test_metadata_endpoint(client):
    response = client.get("/api/v1/metadata")
    assert response.status_code == 200
    data = response.json()
    assert data["dataset_window"]["start_date"] == "2012-01-21"
    assert data["dataset_window"]["end_date"] == "2026-07-14"
    assert data["default_profile"] == "A"
    assert data["alternative_profile"] == "B"
    assert len(data["threshold_profiles"]) == 5
    assert len(data["audited_pilot_periods"]) == 2


def test_overview_endpoint_2012_march_profile_a(client):
    response = client.get("/api/v1/overview?start_date=2012-03-01&end_date=2012-03-31&profile=A")
    assert response.status_code == 200
    data = response.json()

    # Exact reconciliation with March 2012 audit
    assert data["detections"]["modis_detection_count"] == 30161
    assert data["detections"]["viirs_detection_count"] == 182644
    assert data["detections"]["total_observations"] == 30161 + 182644

    assert data["matching"]["available"] is True
    assert data["matching"]["candidate_edge_count"] == 44941
    assert data["matching"]["modis_with_candidates"] == 13137
    assert data["matching"]["viirs_with_candidates"] == 27902
    assert data["matching"]["modis_without_candidates"] == 30161 - 13137
    assert data["matching"]["viirs_without_candidates"] == 182644 - 27902


def test_overview_endpoint_2012_march_profile_b(client):
    response = client.get("/api/v1/overview?start_date=2012-03-01&end_date=2012-03-31&profile=B")
    assert response.status_code == 200
    data = response.json()

    assert data["matching"]["candidate_edge_count"] == 60179
    assert data["matching"]["modis_with_candidates"] == 16764
    assert data["matching"]["viirs_with_candidates"] == 35923


def test_overview_endpoint_2024_march_profile_a(client):
    response = client.get("/api/v1/overview?start_date=2024-03-01&end_date=2024-03-31&profile=A")
    assert response.status_code == 200
    data = response.json()

    # Exact reconciliation with March 2024 audit
    assert data["detections"]["modis_detection_count"] == 14139
    assert data["detections"]["viirs_detection_count"] == 103369

    assert data["matching"]["available"] is True
    assert data["matching"]["candidate_edge_count"] == 19949
    assert data["matching"]["modis_with_candidates"] == 5179
    assert data["matching"]["viirs_with_candidates"] == 11829


def test_overview_endpoint_2024_march_profile_b(client):
    response = client.get("/api/v1/overview?start_date=2024-03-01&end_date=2024-03-31&profile=B")
    assert response.status_code == 200
    data = response.json()

    assert data["matching"]["candidate_edge_count"] == 24815
    assert data["matching"]["modis_with_candidates"] == 6460
    assert data["matching"]["viirs_with_candidates"] == 14737
