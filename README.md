# FireScope

**Exploring India's historical NASA MODIS and VIIRS active-fire observations through transparent cross-sensor candidate matching.**

> **Status:** Prototype built for the NASA Space Apps Challenge. A full-stack MVP (data pipeline, API and web client) exists, but it is under active development and is not an operational wildfire monitoring or alerting system.

FireScope is an active-fire observation harmonization and analysis platform. It brings two NASA FIRMS sensor families into one explorable view without pretending they are identical:

- **MODIS** Collection 6.1 (Terra and Aqua), nominal 1 km pixels
- **Suomi-NPP VIIRS** 375 m Collection 2

The common comparison window in the current backend configuration is **21 January 2012 to 14 July 2026**, inclusive, covering India.

## Table of contents

- [Overview](#overview)
- [Current capabilities](#current-capabilities)
- [Screenshots and demo](#screenshots-and-demo)
- [Data sources](#data-sources)
- [Methodology and scientific ground rules](#methodology-and-scientific-ground-rules)
- [Audited results](#audited-results)
- [Technology stack](#technology-stack)
- [Repository structure](#repository-structure)
- [Setup and run locally](#setup-and-run-locally)
- [Data processing pipeline](#data-processing-pipeline)
- [API overview](#api-overview)
- [Limitations and responsible interpretation](#limitations-and-responsible-interpretation)
- [Planned work](#planned-work)

## Overview

Satellites have tracked active-fire hotspots for more than two decades, but MODIS and VIIRS differ in pixel size, overpass timing and confidence scales, so their records cannot be compared directly. FireScope preserves every original detection and records *candidate relationships* between MODIS and VIIRS detections that are close in space and time. This lets researchers and analysts see where the two sensors agree, where they differ, and how sensitive those relationships are to the matching rules.

## Current capabilities

Each item below corresponds to code in this repository.

- **Analytical backend.** A FastAPI service queries normalized Parquet files directly through an embedded DuckDB engine. Mutable metadata (matching jobs, review annotations) is stored with SQLAlchemy, using SQLite by default and a configurable `DATABASE_URL`.
- **Cross-sensor candidate matching.** Footprint-aware, UTC-based matching with named profiles (for example Profile A: 1 h, 0 km buffer; Profile B: 3 h, 0 km buffer). Candidate generation in the pipeline uses a scikit-learn haversine BallTree.
- **Retained unmatched records.** Detections without a counterpart are kept and labeled `coverage_unverified`.
- **REST API.** Health, metadata, overview, detections, multi-resolution map aggregation, candidate pairs, analytics, matching jobs and review annotations (see [API overview](#api-overview)).
- **Web client (React + TypeScript + Vite).** Dashboard, Fire map, Activity calendar, Analytics and Match explorer pages, plus Data sources, Settings and Documentation pages. The map uses MapLibre GL, with an optional Google Maps (deck.gl) view.
- **Tests and checks.** 30 backend test functions in `tests/`; `scripts\test_backend.cmd` runs them with a direct-route verification script, and `scripts\test_frontend.cmd` runs a strict TypeScript check and a production build. `IMPLEMENTATION_STATUS.md` reports the 30 tests and the frontend build passing on the maintainer's machine.
- **Historical batch matching.** `scripts\batch_match_historical.py` processes months progressively and tracks progress in `data\harmonized\manifest.json`.

## Screenshots and demo

<!-- TODO (owner): add real screenshots of the running application and/or a verified demo link here. -->

_No screenshots or hosted demo are available yet._

## Data sources

| Product | Platform | Notes |
|---|---|---|
| MODIS Collection 6.1 active fire | Terra, Aqua | Version strings are preserved as published (`6.03` for 2012-2022, `61.03` for 2023-2026 in the processed data) |
| VIIRS 375 m Collection 2 active fire | Suomi-NPP | Version `2` |

Source: [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) (Fire Information for Resource Management System). FireScope is an independent project and is not endorsed by NASA.

Raw and processed data are **not stored in this repository** (see [`.gitignore`](.gitignore)). The backend expects normalized Parquet files at `data/processed/common_period/` (see `backend/config.py`).

## Methodology and scientific ground rules

1. **Observations are not fires.** A FIRMS record is a satellite thermal-anomaly pixel detection, not automatically a unique physical wildfire.
2. **Candidates are not confirmed matches.** A cross-sensor pair means two detections are close in space (using pixel footprints) and time. It does not prove they are the same physical fire.
3. **Missing counterparts are not false detections.** Absence of a counterpart is labeled `coverage_unverified`, never "false detection" or "sensor-exclusive". Causes can include resolution, overpass timing, sensitivity and cloud cover.
4. **FRP is kept per instrument.** Fire Radiative Power differs across sensors; MODIS and VIIRS FRP are never summed.
5. **UTC is canonical.** Calculations, filtering and storage use UTC. Displays in Indian Standard Time are labeled.
6. **Original values are preserved.** Sensor-specific confidence values and product versions are kept verbatim; MODIS and VIIRS confidence is not treated as interchangeable.
7. **Connected components are not events.** Graph components of candidate pairs are mathematical groupings, not distinct wildfire events.
8. **A date range is not coverage.** A requested date range does not prove complete satellite observation on every day.

Matching profiles evaluate combined pixel footprints and the UTC time difference. Profiles A and B use a 0 km buffer with 1 h and 3 h time windows; the audited superset envelope screens up to 6 h with a buffer of up to 0.5 km. See [`FIRESCOPE_FINAL_SCIENTIFIC_CONSISTENCY_REPORT.md`](FIRESCOPE_FINAL_SCIENTIFIC_CONSISTENCY_REPORT.md) for the maintainers' audit.

## Audited results

These figures come from the maintainers' own consistency audit (see the report and `historical_*.csv` files in the repository root). They describe candidate relationships, not confirmed fires.

| Period | Status | MODIS detections | VIIRS detections | Profile A pairs (1 h) | Profile B pairs (3 h) | Superset edges (6 h) |
|---|---|---:|---:|---:|---:|---:|
| March 2012 (pilot) | Validated | 30,161 | 182,644 | 44,941 | 60,179 | 86,863 |
| March 2024 (pilot) | Validated | 14,139 | 103,369 | 19,949 | 24,815 | 38,250 |
| Full archive (175 months) | 173 completed, 2 validated | 1,232,096 | 8,725,086 | 1,319,525 | 1,815,450 | 2,753,852 |

Audit files in the repository root:

- `historical_profile_consistency.csv`: monthly profile definitions and validation
- `historical_superset_envelope_audit.csv`: screening envelope verification
- `historical_boundary_completeness_audit.csv`: window comparisons and overpass analysis
- `historical_manifest_integrity.csv`: per-month file presence, row counts and duplicate checks
- `historical_candidate_totals_by_profile.csv`: annual observations and candidate pairs by profile

## Technology stack

**Backend and data:** Python, FastAPI, Uvicorn, DuckDB, pandas, NumPy, PyArrow, scikit-learn, SQLAlchemy, Pydantic, pytest ([`requirements.txt`](requirements.txt))

**Frontend:** React 19, TypeScript, Vite, MapLibre GL, react-map-gl, deck.gl, TanStack Query, Recharts, React Router, Vitest ([`frontend/package.json`](frontend/package.json))

## Repository structure

```text
.
|-- backend/              FastAPI app: routers, schemas, services, domain thresholds
|-- frontend/             React + TypeScript + Vite web client
|-- scripts/              Pipeline scripts (01-09, batch matching) and Windows .cmd launchers
|-- tests/                Backend unit and regression tests
|-- reports/audit/        Audit outputs for the March 2012 and March 2024 pilot periods
|-- API_CONTRACT.md       API contract and frontend integration mapping
|-- IMPLEMENTATION_STATUS.md   Implementation and verification report
|-- FIRESCOPE_FINAL_SCIENTIFIC_CONSISTENCY_REPORT.md   Final audit report
|-- historical_*.csv      Audit tables
|-- requirements.txt      Python dependencies
`-- run_pipeline_example.bat   Example pipeline run (see below)
```

The `data/` directory (raw, processed and harmonized files) is not committed.

## Setup and run locally

The launcher scripts are Windows `.cmd` files; run them from Command Prompt. The commands below come from the scripts in this repository.

### Prerequisites

- Python 3.11 to 3.13
- Node.js `^20.19.0`, `^22.12.0` or `>=24` (from `frontend/package-lock.json`)
- The normalized Parquet data files described in [Data sources](#data-sources). The backend readiness check in `setup_backend.cmd` expects them.

### Backend

```cmd
python -m venv .venv
scripts\setup_backend.cmd
scripts\run_backend.cmd
```

The API runs at `http://127.0.0.1:8000`, with interactive docs at `http://127.0.0.1:8000/docs`.

### Frontend

```cmd
cd frontend
npm ci
copy .env.example .env.local
cd ..
scripts\run_frontend.cmd
```

The dev server runs at `http://127.0.0.1:5173`.

`frontend/.env.example` sets `VITE_USE_MOCK_DATA=true`. To use the live backend, set `VITE_USE_MOCK_DATA=false` in `.env.local`. Supported variables:

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend API base URL (example: `http://localhost:8000/api/v1`) |
| `VITE_USE_MOCK_DATA` | `true` uses mock data where available; `false` uses the live API |
| `VITE_GOOGLE_MAPS_API_KEY` | Optional, enables the Google Maps view. Never commit a key. |
| `VITE_GOOGLE_MAPS_MAP_ID` | Optional Google Maps map ID |

### Both services at once

```cmd
scripts\run_demo.cmd
```

### Tests

```cmd
scripts\test_backend.cmd
scripts\test_frontend.cmd
```

## Data processing pipeline

The `scripts/` folder holds the numbered pipeline stages (`01_create_structure.py` through `09_audit_threshold_component_sensitivity_period.py`), `batch_match_historical.py` and `run_batch_matching.cmd`. `run_pipeline_example.bat` shows an earlier end-to-end example (structure, convert and audit, match, analytics) using FIRMS CSV files you place in `data\raw\modis` and `data\raw\viirs`. Edit the filenames inside it first. Its example matching parameters (`--time-hours 3 --buffer-km 0.5`) differ from the named profiles above.

Download FIRMS data from [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) according to its terms of use. Full-history global files are very large; this project is scoped to India.

## API overview

All routes except `/health` and `/ready` are under `/api/v1`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe |
| `GET` | `/ready` | Data readiness and row counts |
| `GET` | `/api/v1/metadata` | Supported window, sensors, versions and matching profiles |
| `GET` | `/api/v1/overview` | Summary cards |
| `GET` | `/api/v1/detections` | Paginated detections with viewport, date, sensor and FRP filters |
| `GET` | `/api/v1/detections/{row_id}` | Detection detail with attached candidates |
| `GET` | `/api/v1/map/aggregate` | Multi-resolution spatial aggregation |
| `GET` | `/api/v1/candidates` | Paginated candidate pairs (Profile A or B) |
| `GET` | `/api/v1/candidates/{candidate_id}` | Candidate pair detail |
| `GET` | `/api/v1/analytics/activity` | Daily or monthly detection series (UTC or IST) |
| `GET` | `/api/v1/analytics/frp` | Sensor-separated FRP percentiles |
| `GET` | `/api/v1/analytics/sensors` | Sensor specifications and product versions |
| `GET` | `/api/v1/analytics/relationships` | Graph component and degree sensitivity metrics |
| `POST` | `/api/v1/matching/jobs` | Submit a candidate matching job |
| `GET` | `/api/v1/matching/jobs/{job_id}` | Matching job progress |
| `POST` | `/api/v1/review/annotations` | Save a review annotation |
| `GET` | `/api/v1/review/annotations` | List review annotations |

See [`API_CONTRACT.md`](API_CONTRACT.md) for schemas and frontend mapping.

## Limitations and responsible interpretation

- Detections are pixel observations, not a count of unique fires.
- Candidate pairs are spatial-temporal proximity relationships, not proof of the same fire.
- Unmatched detections are not confirmed sensor-exclusive fires, and a missing record does not prove a sensor had no coverage.
- Matching thresholds are experimental parameters, not established universal limits.
- Footprint matching is a practical approximation of pixel geometry, not an exact reconstruction.
- The project works on historical data. It is not real-time, operational alerting, or validated physical-fire tracking.
- Processed data is not included in the repository, so the application cannot be run end to end from a fresh clone alone.

## Planned work

These items come from project planning and are **not implemented yet**. <!-- TODO (owner): confirm and edit this list. -->

- Filtered CSV export of detections and candidate pairs
- Historical anomaly analytics against monthly medians
- User-adjustable matching thresholds in the interface
- Additional VIIRS platforms (NOAA-20, NOAA-21)
