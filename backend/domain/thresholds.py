"""Domain models and calculations for sensor footprints and candidate threshold profiles.

Scientific Rules:
- MODIS Collection 6/6.1 and Suomi-NPP VIIRS Collection 2 active-fire detections.
- Half-diagonal footprint radius = 0.5 * sqrt(scan_km^2 + track_km^2).
- Nominal fallback dimensions: MODIS 1.0 km; VIIRS 0.375 km.
- Candidate relationship predicate:
    distance_km <= modis_radius_km + viirs_radius_km + profile.buffer_km
    AND time_diff_minutes <= profile.time_hours * 60.0
- Candidate relationship is a spatial-temporal candidate association, NOT a confirmed physical fire.
- Connected graph components are NOT physical fire identities.
- FRP must be sensor-separated and never summed across sensors as unique fire energy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

EARTH_RADIUS_KM: float = 6371.0088

MODIS_NOMINAL_SCAN_KM: float = 1.0
MODIS_NOMINAL_TRACK_KM: float = 1.0
VIIRS_NOMINAL_SCAN_KM: float = 0.375
VIIRS_NOMINAL_TRACK_KM: float = 0.375


@dataclass(frozen=True)
class ThresholdProfile:
    id: str  # e.g. "A", "B"
    name: str  # e.g. "A_1h_0km"
    label: str  # User-friendly label
    time_hours: float
    time_limit_minutes: float
    additional_buffer_km: float
    role: str
    description: str
    is_default: bool = False
    is_selectable: bool = True

    def meets_threshold(
        self,
        distance_km: float,
        time_diff_minutes: float,
        modis_radius_km: float,
        viirs_radius_km: float,
    ) -> bool:
        """Evaluate if an observation pair satisfies this profile's constraints."""
        if time_diff_minutes > self.time_limit_minutes:
            return False
        max_distance = modis_radius_km + viirs_radius_km + self.additional_buffer_km
        return distance_km <= max_distance


PROFILES: Dict[str, ThresholdProfile] = {
    "A": ThresholdProfile(
        id="A",
        name="A_1h_0km",
        label="Profile A (1h limit, 0km buffer)",
        time_hours=1.0,
        time_limit_minutes=60.0,
        additional_buffer_km=0.0,
        role="Provisional MVP Default",
        description="Conservative candidate baseline with strict 1-hour time window and zero additional spatial buffer.",
        is_default=True,
        is_selectable=True,
    ),
    "B": ThresholdProfile(
        id="B",
        name="B_3h_0km",
        label="Profile B (3h limit, 0km buffer)",
        time_hours=3.0,
        time_limit_minutes=180.0,
        additional_buffer_km=0.0,
        role="Higher-Recall Alternative",
        description="Selectable alternative allowing up to 3 hours temporal separation without added spatial buffer.",
        is_default=False,
        is_selectable=True,
    ),
    "C": ThresholdProfile(
        id="C",
        name="C_3h_025km",
        label="Profile C (3h limit, 0.25km buffer)",
        time_hours=3.0,
        time_limit_minutes=180.0,
        additional_buffer_km=0.25,
        role="Sensitivity Profile",
        description="Sensitivity analysis profile with 3-hour limit and 0.25 km buffer.",
        is_default=False,
        is_selectable=False,
    ),
    "D": ThresholdProfile(
        id="D",
        name="D_3h_050km",
        label="Profile D (3h limit, 0.50km buffer)",
        time_hours=3.0,
        time_limit_minutes=180.0,
        additional_buffer_km=0.50,
        role="Sensitivity Profile",
        description="Sensitivity analysis profile with 3-hour limit and 0.50 km buffer.",
        is_default=False,
        is_selectable=False,
    ),
    "E": ThresholdProfile(
        id="E",
        name="E_6h_050km",
        label="Profile E (6h limit, 0.50km buffer)",
        time_hours=6.0,
        time_limit_minutes=360.0,
        additional_buffer_km=0.50,
        role="Broad Superset",
        description="Broad permissive candidate superset used during initial spatial search.",
        is_default=False,
        is_selectable=False,
    ),
}

DEFAULT_PROFILE_ID = "A"


def get_profile(profile_id: Optional[str]) -> ThresholdProfile:
    """Retrieve profile by ID (e.g. 'A', 'B', 'A_1h_0km'); defaults to Profile A."""
    if not profile_id:
        return PROFILES[DEFAULT_PROFILE_ID]
    pid = profile_id.strip().upper()
    if pid in PROFILES:
        return PROFILES[pid]
    for p in PROFILES.values():
        if p.name.upper() == profile_id.strip().upper():
            return p
    # Fallback to default
    return PROFILES[DEFAULT_PROFILE_ID]


def compute_footprint_radius(
    scan_km: Optional[float],
    track_km: Optional[float],
    sensor: str = "MODIS",
) -> Tuple[float, bool]:
    """Compute approximate half-diagonal footprint radius: 0.5 * sqrt(scan^2 + track^2).

    Returns:
        (radius_km, is_assumed_fallback)
    """
    nominal_scan = MODIS_NOMINAL_SCAN_KM if sensor.upper() == "MODIS" else VIIRS_NOMINAL_SCAN_KM
    nominal_track = MODIS_NOMINAL_TRACK_KM if sensor.upper() == "MODIS" else VIIRS_NOMINAL_TRACK_KM

    assumed = False
    s = scan_km if (scan_km is not None and scan_km > 0 and math.isfinite(scan_km)) else None
    t = track_km if (track_km is not None and track_km > 0 and math.isfinite(track_km)) else None

    if s is None:
        s = nominal_scan
        assumed = True
    if t is None:
        t = nominal_track
        assumed = True

    radius = 0.5 * math.hypot(s, t)
    return radius, assumed


def haversine_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Great-circle distance between two coordinate pairs in km."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_KM * c
