# FireScope — Stable API Contract & Frontend Integration Guide

**Document Version:** `1.0.0`  
**Status:** Implemented, Tested, and Frozen for Integration  
**Backend Base URL (Local Development):** `http://127.0.0.1:8000`  
**Interactive OpenAPI Documentation:** `http://127.0.0.1:8000/docs` or `http://127.0.0.1:8000/redoc`

---

## 1. Quick Integration for Frontend Developer

### 1.1 Environment Variable Configuration
Add the backend URL to your frontend `.env` file according to your build tool:

```env
# If using Vite (React, Vue, Svelte):
VITE_API_BASE_URL=http://127.0.0.1:8000

# If using Next.js:
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000

# If using Create-React-App:
REACT_APP_API_BASE_URL=http://127.0.0.1:8000
```

### 1.2 CORS
The backend is already configured to permit cross-origin requests from standard local frontend ports:
- `http://localhost:3000` & `http://127.0.0.1:3000`
- `http://localhost:5173` & `http://127.0.0.1:5173`
- `http://localhost:8080` & `http://127.0.0.1:8080`

If your dev server uses a different port, set `CORS_ORIGINS` in the backend `.env` file.

---

## 2. Scientific & UI Terminology Rules

To maintain scientific integrity in all UI charts, cards, map popups, and legends:

1. **Observations vs Fires:** Detections are satellite pixel anomalies, not unique wildfires. Always label them as `Detections` or `Observations`.
2. **Candidate Matching Profiles:**
   - **Profile A (Default Baseline):** 1-hour time window ($\le 60.0\,\text{min}$), 0.0 km added buffer ($d \le r_{\text{MODIS}} + r_{\text{VIIRS}}$). Conservative baseline.
   - **Profile B (Selectable Alternative):** 3-hour time window ($\le 180.0\,\text{min}$), 0.0 km added buffer ($d \le r_{\text{MODIS}} + r_{\text{VIIRS}}$). Higher-recall alternative.
   - *Note on Historical Consistency:* Profile B is canonical at 3h / 0km buffer across all 175 months. Any reference to 2h / 1km in historical documentation was an erroneous prose typo and does not reflect backend or data thresholds.
   - **Candidate Superset Screening Envelope:** 6-hour time window ($\le 360.0\,\text{min}$), 0.50 km added buffer (Profile E envelope).
   - A candidate pair is a spatiotemporal association under footprint geometry, **NOT a confirmed physical fire identity**.
   - All 175 months (2012-01 to 2026-07) are available dynamically via `GET /api/v1/metadata` (`processed_matching_periods`).
3. **No-Candidate Status:** Always label unmatched observations as **`Coverage Unverified`**. Do not describe them as "sensor-exclusive" or "false detections" (satellite coverage may have been absent).
4. **Graph Components:** Always label component metrics as **`Candidate Graph Components`**, never "Fire Events". Naive graph chaining can bridge separate fires.
5. **Fire Radiative Power (FRP):** FRP values from MODIS and VIIRS use different spatial footprints and saturation thresholds. **Never sum them together**. Always plot and report MODIS FRP and VIIRS FRP in separate series or cards.
6. **Timezone:** Canonical timestamps are strictly in **UTC** (`acq_datetime_utc`). Displaying IST (UTC+05:30) is supported; whenever shown, explicitly label it as **`IST`**.

---

## 3. Endpoint Reference & Response Examples

### Summary Table

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Application liveness probe |
| `GET` | `/ready` | Parquet data storage readiness and row counts |
| `GET` | `/api/v1/metadata` | Supported window, sensors, versions, and matching profiles |
| `GET` | `/api/v1/overview` | High-level summary cards (counts, FRP, matching status) |
| `GET` | `/api/v1/detections` | Paginated fire detections with viewport, date, sensor, and FRP filters |
| `GET` | `/api/v1/detections/{row_id}` | Detailed detection inspection with attached candidate matches |
| `GET` | `/api/v1/map/aggregate` | Multi-resolution spatial aggregation grid cells (0.5°/0.15°) for national & regional visualization |
| `GET` | `/api/v1/candidates` | Paginated candidate pairs under Profile A or B with bbox filter |
| `GET` | `/api/v1/candidates/{candidate_id}` | Complete candidate pair detail and footprint geometry metrics |
| `GET` | `/api/v1/analytics/activity` | Daily or monthly detection timeseries (UTC or IST) |
| `GET` | `/api/v1/analytics/frp` | Sensor-separated FRP percentiles (p25, median, p75, p95, max) |
| `GET` | `/api/v1/analytics/sensors` | MODIS vs VIIRS sensor specifications and product versions |
| `GET` | `/api/v1/analytics/relationships` | Graph component and degree sensitivity metrics |
| `POST` | `/api/v1/matching/jobs` | Submit/trigger candidate matching job for a date window |
| `GET` | `/api/v1/matching/jobs/{job_id}` | Get matching job execution progress and output paths |
| `POST` | `/api/v1/review/annotations` | Save human/expert adjudication for review sample pairs |
| `GET` | `/api/v1/review/annotations` | List saved review annotations |

---

### 3.1 `GET /health` & `GET /ready`

#### `GET /health`
```json
{
  "status": "ok",
  "app_name": "FireScope API",
  "app_version": "1.0.0",
  "environment": "development"
}
```

#### `GET /ready`
```json
{
  "ready": true,
  "status": "ready",
  "modis_parquet_exists": true,
  "viirs_parquet_exists": true,
  "modis_total_rows": 1232096,
  "viirs_total_rows": 8725086,
  "error": null
}
```

---

### 3.2 `GET /api/v1/metadata`
Returns global platform constants, available profiles, and pilot audited periods.

```json
{
  "dataset_window": {
    "start_date": "2012-01-21",
    "end_date": "2026-07-14",
    "canonical_timezone": "UTC",
    "display_timezones": ["UTC", "IST"],
    "total_days": 5254
  },
  "sensors": [
    {
      "sensor": "MODIS",
      "satellites": ["Terra", "Aqua"],
      "nominal_pixel_resolution_km": 1.0,
      "versions": ["6.03 (2012-2022)", "61.03 (2023-2026)"],
      "frp_unit": "MW"
    },
    {
      "sensor": "VIIRS",
      "satellites": ["Suomi-NPP (SNPP)"],
      "nominal_pixel_resolution_km": 0.375,
      "versions": ["2 (2012-2026)"],
      "frp_unit": "MW"
    }
  ],
  "threshold_profiles": [
    {
      "id": "A",
      "name": "A_1h_0km",
      "label": "Profile A (1h limit, 0km buffer)",
      "time_limit_minutes": 60.0,
      "additional_buffer_km": 0.0,
      "role": "Provisional MVP Default",
      "description": "Conservative candidate baseline with strict 1-hour time window and zero additional spatial buffer.",
      "is_default": true,
      "is_selectable": true
    },
    {
      "id": "B",
      "name": "B_3h_0km",
      "label": "Profile B (3h limit, 0km buffer)",
      "time_limit_minutes": 180.0,
      "additional_buffer_km": 0.0,
      "role": "Higher-Recall Alternative",
      "description": "Selectable alternative allowing up to 3 hours temporal separation without added spatial buffer.",
      "is_default": false,
      "is_selectable": true
    }
  ],
  "default_profile": "A",
  "alternative_profile": "B",
  "audited_pilot_periods": [
    {
      "period_id": "2012-03",
      "start_date": "2012-03-01",
      "end_date": "2012-03-31",
      "modis_detections": 30161,
      "viirs_detections": 182644,
      "candidate_superset_edges": 86863,
      "profile_a_edges": 44941,
      "profile_b_edges": 60179,
      "modis_version": "6.03",
      "viirs_version": "2"
    },
    {
      "period_id": "2024-03",
      "start_date": "2024-03-01",
      "end_date": "2024-03-31",
      "modis_detections": 14139,
      "viirs_detections": 103369,
      "candidate_superset_edges": 38250,
      "profile_a_edges": 19949,
      "profile_b_edges": 24815,
      "modis_version": "61.03",
      "viirs_version": "2"
    }
  ]
}
```

---

### 3.3 `GET /api/v1/overview`
**Query Parameters:**
- `start_date` (string, `YYYY-MM-DD`, default: `2024-03-01`)
- `end_date` (string, `YYYY-MM-DD`, default: `2024-03-31`)
- `profile` (string, `A` or `B`, default: `A`)

**Example Request:**
`GET /api/v1/overview?start_date=2024-03-01&end_date=2024-03-31&profile=A`

**Response Example:**
```json
{
  "query_period": {
    "start_date": "2024-03-01",
    "end_date": "2024-03-31",
    "timezone": "UTC"
  },
  "profile": {
    "id": "A",
    "name": "A_1h_0km",
    "label": "Profile A (1h limit, 0km buffer)",
    "time_limit_minutes": 60.0,
    "additional_buffer_km": 0.0,
    "role": "Provisional MVP Default"
  },
  "detections": {
    "modis_detection_count": 14139,
    "viirs_detection_count": 103369,
    "total_observations": 117508,
    "note": "Total observations is the sum of sensor detections, NOT unique physical fires."
  },
  "frp_mw": {
    "modis": {
      "sensor": "MODIS",
      "total_frp_mw": 636329.8,
      "mean_frp_mw": 45.0,
      "median_frp_mw": 21.8,
      "max_frp_mw": 1827.4
    },
    "viirs": {
      "sensor": "VIIRS",
      "total_frp_mw": 974120.3,
      "mean_frp_mw": 9.42,
      "median_frp_mw": 4.88,
      "max_frp_mw": 2684.1
    },
    "interpretation": "FRP is instrument-specific; values cannot be added across sensors."
  },
  "matching": {
    "available": true,
    "candidate_edge_count": 19949,
    "modis_with_candidates": 5179,
    "viirs_with_candidates": 11829,
    "modis_without_candidates": 8960,
    "viirs_without_candidates": 91540,
    "exclusivity_interpretation": "coverage_unverified; absence of candidate is not evidence of fire absence",
    "candidate_source_file": "D:/FireScope/data/harmonized/matching_20240301_20240331/candidate_pairs_superset.parquet"
  }
}
```

---

### 3.4 `GET /api/v1/detections`
Retrieves bounded, paginated detection records. Designed for map viewports and table browsing.

**Query Parameters:**
- `sensor` (`ALL`, `MODIS`, `VIIRS`, default: `ALL`)
- `start_date` (`YYYY-MM-DD`, optional)
- `end_date` (`YYYY-MM-DD`, optional)
- `min_lat`, `max_lat`, `min_lon`, `max_lon` (floats for viewport bounding box)
- `daynight` (`D` or `N`, optional)
- `min_frp`, `max_frp` (floats, optional)
- `page` (int, default: `1`)
- `page_size` (int, default: `50`, max: `500`)
- `sort_by` (`acq_datetime_utc`, `frp_mw`, `latitude`, `longitude`, default: `acq_datetime_utc`)
- `sort_order` (`asc` or `desc`, default: `desc`)

**Response Example:**
```json
{
  "items": [
    {
      "row_id": "MODIS_fire_archive_M-C61_846371_000001006087",
      "sensor": "MODIS",
      "satellite": "Terra",
      "latitude": 21.8423,
      "longitude": 84.1294,
      "acq_datetime_utc": "2024-03-31T05:24:00Z",
      "scan_km": 1.1,
      "track_km": 1.05,
      "pixel_area_km2": 1.155,
      "frp_mw": 34.2,
      "confidence_raw": "82",
      "daynight": "D",
      "version": "61.03",
      "source_product": "MODIS_C61",
      "source_file": "MODIS_2024.parquet",
      "source_row": 1006087
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_items": 1313,
    "total_pages": 27,
    "has_next": true,
    "has_prev": false
  },
  "filters_applied": {
    "sensor": "MODIS",
    "start_date": "2024-03-01",
    "end_date": "2024-03-05"
  }
}
```

---

### 3.5 `GET /api/v1/detections/{row_id}`
Detailed inspection for one row, including any attached candidate matches.

**Response Example:**
```json
{
  "row_id": "MODIS_fire_archive_M-C61_846371_000001010481",
  "sensor": "MODIS",
  "satellite": "Aqua",
  "latitude": 22.145,
  "longitude": 82.351,
  "acq_datetime_utc": "2024-03-15T08:12:00Z",
  "scan_km": 1.3,
  "track_km": 1.1,
  "pixel_area_km2": 1.43,
  "frp_mw": 52.8,
  "confidence_raw": "88",
  "daynight": "D",
  "version": "61.03",
  "candidate_matches_count": 1,
  "candidate_matches": [
    {
      "candidate_id": "MODIS_fire_archive_M-C61_846371_000001010481__VIIRS_fire_archive_SV-C2_846372_000007124767",
      "modis_row_id": "MODIS_fire_archive_M-C61_846371_000001010481",
      "viirs_row_id": "VIIRS_fire_archive_SV-C2_846372_000007124767",
      "distance_km": 0.42,
      "time_diff_minutes": 18.0,
      "footprint_radius_sum_km": 1.12,
      "modis_datetime_utc": "2024-03-15T08:12:00Z",
      "viirs_datetime_utc": "2024-03-15T08:30:00Z",
      "modis_frp_mw": 52.8,
      "viirs_frp_mw": 14.6
    }
  ]
}
```

---

### 3.6 `GET /api/v1/map/aggregate`
Multi-resolution spatial grid aggregation directly from Parquet. Enables national overview visualization of millions of observations without client memory bottlenecks.

**Query Parameters:**
- `start_date` (`YYYY-MM-DD`, optional, default: start of common period `2012-01-21`)
- `end_date` (`YYYY-MM-DD`, optional, default: end of common period `2026-07-14`)
- `sensor` (`ALL`, `MODIS`, `VIIRS`, default: `ALL`)
- `platform` (`Terra`, `Aqua`, `Suomi-NPP`, optional)
- `daynight` (`D` or `N`, optional)
- `min_lat`, `max_lat`, `min_lon`, `max_lon` (viewport bounding box, optional)
- `resolution_deg` (float, e.g. `0.5` for overview ~50km, `0.15` for regional ~15km, default: `0.5`)
- `zoom` (float, optional; auto-adapts resolution to `0.15` when zoom $\ge 6$)

**Response Example (GeoJSON FeatureCollection):**
```json
{
  "type": "FeatureCollection",
  "query": {
    "start_date": "2012-01-21",
    "end_date": "2026-07-14",
    "sensor": "ALL",
    "resolution_deg": 0.5,
    "bbox": null
  },
  "summary": {
    "total_cells": 1267,
    "total_observations": 9957182,
    "modis_observations": 1232096,
    "viirs_observations": 8725086,
    "resolution_deg": 0.5
  },
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [86.5, 24.0]
      },
      "properties": {
        "cell_id": "cell_0.5_24.00_86.50",
        "latitude": 24.0,
        "longitude": 86.5,
        "total_count": 126874,
        "modis_count": 9720,
        "viirs_count": 117154,
        "modis_avg_frp": 10.77,
        "viirs_avg_frp": 2.53,
        "resolution_deg": 0.5
      }
    }
  ]
}
```

---

### 3.7 `GET /api/v1/candidates`
**Query Parameters:**
- `profile` (`A` default, `B` selectable)
- `start_date`, `end_date` (`YYYY-MM-DD`)
- `min_lat`, `max_lat`, `min_lon`, `max_lon` (viewport bounding box)
- `min_distance_km`, `max_distance_km`
- `page`, `page_size` (max 500)
- `sort_by` (`distance_km`, `time_diff_minutes`)
- `sort_order` (`asc` or `desc`)

**Response Example:**
```json
{
  "items": [
    {
      "candidate_id": "MODIS_fire_archive_M-C61_846371_000001010481__VIIRS_fire_archive_SV-C2_846372_000007124767",
      "modis_row_id": "MODIS_fire_archive_M-C61_846371_000001010481",
      "viirs_row_id": "VIIRS_fire_archive_SV-C2_846372_000007124767",
      "distance_km": 0.010,
      "time_diff_minutes": 32.0,
      "modis_footprint_radius_km": 0.78,
      "viirs_footprint_radius_km": 0.31,
      "footprint_radius_sum_km": 1.09,
      "modis_datetime_utc": "2024-03-15 08:12:00+00:00",
      "viirs_datetime_utc": "2024-03-15 08:44:00+00:00",
      "modis_latitude": 22.145,
      "modis_longitude": 82.351,
      "viirs_latitude": 22.1451,
      "viirs_longitude": 82.3511,
      "modis_satellite": "Aqua",
      "viirs_satellite": "Suomi-NPP",
      "modis_frp_mw": 52.8,
      "viirs_frp_mw": 14.6,
      "modis_version": "61.03",
      "viirs_version": "2"
    }
  ],
  "profile": {
    "id": "A",
    "name": "A_1h_0km",
    "label": "Profile A (1h limit, 0km buffer)",
    "time_limit_minutes": 60.0,
    "additional_buffer_km": 0.0,
    "role": "Provisional MVP Default"
  },
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_items": 19949,
    "total_pages": 399,
    "has_next": true,
    "has_prev": false
  }
}
```

---

### 3.7 `GET /api/v1/analytics/activity`
Provides daily or monthly observation counts per sensor.

**Query Parameters:**
- `start_date`, `end_date` (`YYYY-MM-DD`)
- `interval` (`day` or `month`, default: `day`)
- `timezone` (`UTC` or `IST`, default: `UTC`)

**Response Example:**
```json
{
  "interval": "day",
  "timezone": "UTC",
  "start_date": "2024-03-01",
  "end_date": "2024-03-07",
  "data": [
    {"time_bucket": "2024-03-01", "modis_count": 329, "viirs_count": 2060},
    {"time_bucket": "2024-03-02", "modis_count": 295, "viirs_count": 2338},
    {"time_bucket": "2024-03-03", "modis_count": 257, "viirs_count": 2111},
    {"time_bucket": "2024-03-04", "modis_count": 196, "viirs_count": 1640},
    {"time_bucket": "2024-03-05", "modis_count": 236, "viirs_count": 2409},
    {"time_bucket": "2024-03-06", "modis_count": 513, "viirs_count": 2350},
    {"time_bucket": "2024-03-07", "modis_count": 377, "viirs_count": 3012}
  ]
}
```

---

### 3.8 `GET /api/v1/analytics/frp`
Sensor-separated FRP distribution metrics.

**Response Example:**
```json
{
  "period": {"start_date": "2024-03-01", "end_date": "2024-03-31", "timezone": "UTC"},
  "unit": "MW",
  "modis": {
    "sensor": "MODIS",
    "detection_count": 14139,
    "total_frp_mw": 636329.8,
    "mean_frp_mw": 45.0,
    "median_frp_mw": 21.8,
    "p25_frp_mw": 11.4,
    "p75_frp_mw": 48.2,
    "p95_frp_mw": 158.0,
    "max_frp_mw": 1827.4
  },
  "viirs": {
    "sensor": "VIIRS",
    "detection_count": 103369,
    "total_frp_mw": 974120.3,
    "mean_frp_mw": 9.42,
    "median_frp_mw": 4.88,
    "p25_frp_mw": 2.31,
    "p75_frp_mw": 10.4,
    "p95_frp_mw": 32.1,
    "max_frp_mw": 2684.1
  },
  "note": "MODIS and VIIRS FRP metrics must remain separated due to sensor footprint and saturation differences."
}
```

---

### 3.9 `POST /api/v1/matching/jobs` & `GET /api/v1/matching/jobs/{job_id}`

#### Submit Job
`POST /api/v1/matching/jobs`
```json
{
  "start_date": "2024-03-01",
  "end_date": "2024-03-31",
  "profile_id": "A"
}
```

#### Status Response (`201 Created` / `200 OK`)
```json
{
  "job_id": "job_97da7c99cc51",
  "status": "COMPLETED",
  "progress_percent": 100.0,
  "start_date": "2024-03-01",
  "end_date": "2024-03-31",
  "profile_id": "A",
  "created_at": "2026-11-14T10:30:00Z",
  "updated_at": "2026-11-14T10:30:01Z",
  "modis_rows_processed": 14139,
  "viirs_rows_processed": 103369,
  "candidate_edges_count": 38250,
  "output_dir": "data/harmonized/matching_20240301_20240331",
  "error_message": null
}
```

---

### 3.10 `POST /api/v1/review/annotations` & `GET /api/v1/review/annotations`

#### Save Expert Adjudication
`POST /api/v1/review/annotations`
```json
{
  "candidate_pair_id": "MODIS_1001__VIIRS_2002",
  "modis_row_id": "MODIS_1001",
  "viirs_row_id": "VIIRS_2002",
  "adjudication": "MATCH",
  "notes": "Co-incident agricultural hotspot with consistent brightness temperature and wind-aligned smoke dispersion",
  "reviewer": "Reviewer_Name"
}
```

#### Response (`201 Created`)
```json
{
  "id": 1,
  "candidate_pair_id": "MODIS_1001__VIIRS_2002",
  "modis_row_id": "MODIS_1001",
  "viirs_row_id": "VIIRS_2002",
  "adjudication": "MATCH",
  "notes": "Co-incident agricultural hotspot with consistent brightness temperature and wind-aligned smoke dispersion",
  "reviewer": "Reviewer_Name",
  "created_at": "2026-11-14T10:32:00Z"
}
```

---

## 4. Frontend Example API Client Helper (TypeScript / JavaScript)

```typescript
// src/api/client.ts
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export async function fetchOverview(startDate = "2024-03-01", endDate = "2024-03-31", profile = "A") {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate, profile });
  const res = await fetch(`${BASE_URL}/api/v1/overview?${params}`);
  if (!res.ok) throw new Error(`Overview fetch failed: ${res.statusText}`);
  return res.json();
}

export async function fetchDetections(options: {
  sensor?: string;
  startDate?: string;
  endDate?: string;
  minLat?: number;
  maxLat?: number;
  minLon?: number;
  maxLon?: number;
  page?: number;
  pageSize?: number;
}) {
  const params = new URLSearchParams();
  if (options.sensor) params.set("sensor", options.sensor);
  if (options.startDate) params.set("start_date", options.startDate);
  if (options.endDate) params.set("end_date", options.endDate);
  if (options.minLat != null) params.set("min_lat", options.minLat.toString());
  if (options.maxLat != null) params.set("max_lat", options.maxLat.toString());
  if (options.minLon != null) params.set("min_lon", options.minLon.toString());
  if (options.maxLon != null) params.set("max_lon", options.maxLon.toString());
  if (options.page) params.set("page", options.page.toString());
  if (options.pageSize) params.set("page_size", options.pageSize.toString());

  const res = await fetch(`${BASE_URL}/api/v1/detections?${params}`);
  if (!res.ok) throw new Error(`Detections fetch failed: ${res.statusText}`);
  return res.json();
}

export async function fetchCandidates(profile = "A", startDate = "2024-03-01", endDate = "2024-03-31", page = 1) {
  const params = new URLSearchParams({
    profile,
    start_date: startDate,
    end_date: endDate,
    page: page.toString(),
  });
  const res = await fetch(`${BASE_URL}/api/v1/candidates?${params}`);
  if (!res.ok) throw new Error(`Candidates fetch failed: ${res.statusText}`);
  return res.json();
}
```
