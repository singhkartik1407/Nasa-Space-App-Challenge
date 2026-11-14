"""Integration tests for Analytics, Reconciliation, Jobs, and Review Annotations."""
import pytest


def test_activity_timeseries(client):
    response = client.get("/api/v1/analytics/activity?start_date=2024-03-01&end_date=2024-03-07&interval=day&timezone=UTC")
    assert response.status_code == 200
    data = response.json()
    assert data["interval"] == "day"
    assert data["timezone"] == "UTC"
    assert len(data["data"]) == 7
    # Verify both sensors report counts
    for bucket in data["data"]:
        assert "time_bucket" in bucket
        assert "modis_count" in bucket
        assert "viirs_count" in bucket


def test_frp_analytics_separated(client):
    response = client.get("/api/v1/analytics/frp?start_date=2024-03-01&end_date=2024-03-31")
    assert response.status_code == 200
    data = response.json()
    assert data["unit"] == "MW"
    assert data["modis"]["detection_count"] == 14139
    assert data["viirs"]["detection_count"] == 103369
    assert data["modis"]["mean_frp_mw"] > 0
    assert data["viirs"]["mean_frp_mw"] > 0
    # MODIS typically exhibits higher median FRP than VIIRS due to larger footprint
    assert data["modis"]["median_frp_mw"] > data["viirs"]["median_frp_mw"]


def test_sensors_analytics_versions(client):
    response = client.get("/api/v1/analytics/sensors")
    assert response.status_code == 200
    data = response.json()
    assert data["modis"]["common_period_detections"] == 1232096
    assert data["viirs"]["common_period_detections"] == 8725086
    # Check that versions are recorded verbatim
    modis_versions = [v["version"] for v in data["modis"]["version_distribution"]]
    assert "6.03" in modis_versions
    assert "61.03" in modis_versions
    viirs_versions = [v["version"] for v in data["viirs"]["version_distribution"]]
    assert "2" in viirs_versions


def test_relationships_analytics(client):
    # March 2024 relationships audit
    res_2024 = client.get("/api/v1/analytics/relationships?period=2024-03")
    assert res_2024.status_code == 200
    d_2024 = res_2024.json()
    assert d_2024["modis_detections"] == 14139
    assert d_2024["viirs_detections"] == 103369
    assert d_2024["candidate_superset_edges"] == 38250

    prof_a = next(p for p in d_2024["profile_sensitivity"] if p["profile"].startswith("A"))
    assert prof_a["candidate_edges"] == 19949
    assert prof_a["one_to_one_components"] == 821
    assert prof_a["one_to_one_share_pct"] == 26.80

    prof_b = next(p for p in d_2024["profile_sensitivity"] if p["profile"].startswith("B"))
    assert prof_b["candidate_edges"] == 24815
    assert prof_b["one_to_one_components"] == 1031
    assert prof_b["one_to_one_share_pct"] == 26.73


def test_matching_job_lifecycle(client):
    # Create job for March 2024 pilot
    payload = {
        "start_date": "2024-03-01",
        "end_date": "2024-03-31",
        "profile_id": "A",
    }
    create_res = client.post("/api/v1/matching/jobs", json=payload)
    assert create_res.status_code == 201
    job = create_res.json()
    job_id = job["job_id"]
    assert job["status"] == "COMPLETED"
    assert job["candidate_edges_count"] == 38250

    # Retrieve job status
    get_res = client.get(f"/api/v1/matching/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["job_id"] == job_id


def test_review_annotation_workflow(client):
    payload = {
        "candidate_pair_id": "MODIS_1001__VIIRS_2002",
        "modis_row_id": "MODIS_1001",
        "viirs_row_id": "VIIRS_2002",
        "adjudication": "MATCH",
        "notes": "Co-incident agricultural burn hotspot in Punjab with close temporal alignment",
        "reviewer": "Reviewer_Kartik",
    }
    create_res = client.post("/api/v1/review/annotations", json=payload)
    assert create_res.status_code == 201
    item = create_res.json()
    assert item["adjudication"] == "MATCH"
    assert item["reviewer"] == "Reviewer_Kartik"

    # List annotations
    list_res = client.get("/api/v1/review/annotations")
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(a["candidate_pair_id"] == "MODIS_1001__VIIRS_2002" for a in items)
