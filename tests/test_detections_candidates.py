"""Integration tests for Detections and Candidates endpoints."""
import pytest


def test_detections_pagination_and_filtering(client):
    response = client.get("/api/v1/detections?sensor=MODIS&start_date=2024-03-01&end_date=2024-03-02&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["page_size"] == 10
    assert data["pagination"]["total_items"] > 0
    assert data["items"][0]["sensor"] == "MODIS"
    assert "row_id" in data["items"][0]
    assert "acq_datetime_utc" in data["items"][0]


def test_detections_bbox_filtering(client):
    # Query within bounding box around central India (lat 20-22, lon 78-80)
    response = client.get(
        "/api/v1/detections?start_date=2024-03-01&end_date=2024-03-05"
        "&min_lat=20.0&max_lat=22.0&min_lon=78.0&max_lon=80.0&page_size=20"
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert 20.0 <= item["latitude"] <= 22.0
        assert 78.0 <= item["longitude"] <= 80.0


def test_detection_by_row_id(client):
    # First get a valid row_id from detections
    list_res = client.get("/api/v1/detections?sensor=MODIS&start_date=2024-03-01&end_date=2024-03-01&page_size=1")
    assert list_res.status_code == 200
    row_id = list_res.json()["items"][0]["row_id"]

    # Now fetch detail
    detail_res = client.get(f"/api/v1/detections/{row_id}")
    assert detail_res.status_code == 200
    data = detail_res.json()
    assert data["row_id"] == row_id
    assert data["sensor"] == "MODIS"
    assert "candidate_matches" in data


def test_detection_not_found(client):
    response = client.get("/api/v1/detections/non_existent_row_id_12345")
    assert response.status_code == 404


def test_candidates_profile_a_and_b(client):
    # Test March 2024 Profile A
    res_a = client.get("/api/v1/candidates?start_date=2024-03-01&end_date=2024-03-31&profile=A&page_size=25")
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["pagination"]["total_items"] == 19949
    assert len(data_a["items"]) == 25
    assert data_a["profile"]["id"] == "A"

    # All items must strictly satisfy Profile A thresholds (time <= 60 min, distance <= radii sum + 0)
    for item in data_a["items"]:
        assert item["time_diff_minutes"] <= 60.0
        assert item["distance_km"] <= item["footprint_radius_sum_km"] + 0.001

    # Test March 2024 Profile B
    res_b = client.get("/api/v1/candidates?start_date=2024-03-01&end_date=2024-03-31&profile=B&page_size=25")
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["pagination"]["total_items"] == 24815
    assert data_b["profile"]["id"] == "B"


def test_candidate_by_id(client):
    # Fetch first candidate edge ID
    cand_list = client.get("/api/v1/candidates?start_date=2024-03-01&end_date=2024-03-31&profile=A&page_size=1")
    assert cand_list.status_code == 200
    cand_id = cand_list.json()["items"][0]["candidate_id"]

    # Retrieve candidate detail
    detail_res = client.get(f"/api/v1/candidates/{cand_id}")
    assert detail_res.status_code == 200
    cand = detail_res.json()
    assert cand["candidate_id"] == cand_id
    assert "modis_row_id" in cand
    assert "viirs_row_id" in cand
    assert "distance_km" in cand
    assert "time_diff_minutes" in cand
    assert "modis_frp_mw" in cand
    assert "viirs_frp_mw" in cand
