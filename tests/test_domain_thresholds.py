"""Unit tests for domain thresholds, footprint geometry, and profile definitions."""
import math
import pytest

from backend.domain.thresholds import (
    PROFILES,
    compute_footprint_radius,
    get_profile,
    haversine_distance_km,
)


def test_footprint_radius_nominal_modis():
    radius, assumed = compute_footprint_radius(None, None, sensor="MODIS")
    assert assumed is True
    # Half-diagonal of 1.0 km x 1.0 km square is 0.5 * sqrt(2) ≈ 0.7071
    assert math.isclose(radius, 0.5 * math.sqrt(2.0), rel_tol=1e-4)


def test_footprint_radius_nominal_viirs():
    radius, assumed = compute_footprint_radius(None, None, sensor="VIIRS")
    assert assumed is True
    # Half-diagonal of 0.375 km x 0.375 km square
    expected = 0.5 * math.hypot(0.375, 0.375)
    assert math.isclose(radius, expected, rel_tol=1e-4)


def test_footprint_radius_explicit_values():
    radius, assumed = compute_footprint_radius(1.2, 1.1, sensor="MODIS")
    assert assumed is False
    expected = 0.5 * math.hypot(1.2, 1.1)
    assert math.isclose(radius, expected, rel_tol=1e-4)


def test_haversine_distance_known_points():
    # Distance between New Delhi (28.6139, 77.2090) and Mumbai (19.0760, 72.8777) ≈ 1148 km
    dist = haversine_distance_km(28.6139, 77.2090, 19.0760, 72.8777)
    assert 1140.0 < dist < 1160.0


def test_haversine_distance_zero():
    dist = haversine_distance_km(20.0, 80.0, 20.0, 80.0)
    assert math.isclose(dist, 0.0, abs_tol=1e-6)


def test_profile_retrieval():
    prof_a = get_profile("A")
    assert prof_a.id == "A"
    assert prof_a.time_hours == 1.0
    assert prof_a.time_limit_minutes == 60.0
    assert prof_a.additional_buffer_km == 0.0
    assert prof_a.is_default is True

    prof_b = get_profile("B")
    assert prof_b.id == "B"
    assert prof_b.time_hours == 3.0
    assert prof_b.time_limit_minutes == 180.0
    assert prof_b.additional_buffer_km == 0.0
    assert prof_b.is_selectable is True


def test_profile_meets_threshold_logic():
    prof_a = get_profile("A")
    prof_b = get_profile("B")

    modis_r = 0.8
    viirs_r = 0.3
    # Max allowed distance under A or B (0 km extra buffer) = 1.1 km

    # Case 1: Within 45 min and 1.0 km -> Meets both A and B
    assert prof_a.meets_threshold(1.0, 45.0, modis_r, viirs_r) is True
    assert prof_b.meets_threshold(1.0, 45.0, modis_r, viirs_r) is True

    # Case 2: 90 min (1.5 hours) and 1.0 km -> Fails A (>60 min), Meets B (<=180 min)
    assert prof_a.meets_threshold(1.0, 90.0, modis_r, viirs_r) is False
    assert prof_b.meets_threshold(1.0, 90.0, modis_r, viirs_r) is True

    # Case 3: 45 min and 1.2 km -> Exceeds max distance (1.1 km) -> Fails both A and B
    assert prof_a.meets_threshold(1.2, 45.0, modis_r, viirs_r) is False
    assert prof_b.meets_threshold(1.2, 45.0, modis_r, viirs_r) is False

    # Case 4: Under Profile C (0.25 km buffer), max distance is 1.35 km -> 1.2 km passes!
    prof_c = get_profile("C")
    assert prof_c.meets_threshold(1.2, 45.0, modis_r, viirs_r) is True
