"""Domain logic package for FireScope."""
from backend.domain.thresholds import (
    DEFAULT_PROFILE_ID,
    PROFILES,
    ThresholdProfile,
    compute_footprint_radius,
    get_profile,
    haversine_distance_km,
)

__all__ = [
    "DEFAULT_PROFILE_ID",
    "PROFILES",
    "ThresholdProfile",
    "compute_footprint_radius",
    "get_profile",
    "haversine_distance_km",
]
