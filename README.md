# FireScope — Active Fire Harmonization Platform

FireScope harmonizes NASA FIRMS active-fire observations across two sensor families:
- **MODIS** Collection 6.1 (Terra and Aqua)
- **Suomi-NPP VIIRS** Collection 2 (375 m)

It provides high-performance analytical queries directly over normalized Parquet files using DuckDB, evaluates cross-sensor spatiotemporal candidate relationships under configurable threshold profiles (Profile A conservative default, Profile B higher-recall alternative), and serves a stable REST API for frontend dashboards and map views.

---

## Important Scientific Ground Rules

1. **Observations vs Fires:** A FIRMS record is a satellite active-fire/thermal-anomaly pixel detection, not automatically an isolated physical wildfire.
2. **Candidate Correspondences:** Cross-sensor pairs indicate spatiotemporal proximity within combined footprint bounds; they are **not confirmed ground-truth matches**.
3. **Coverage Unverified:** Absence of a counterpart detection is labeled as `coverage_unverified`, never as "false detection" or "sensor-exclusive".
4. **Instrument-Separated FRP:** Fire Radiative Power (MW) differs across instruments due to pixel footprint and sensor saturation characteristics. **Never sum MODIS and VIIRS FRP together**.
5. **Canonical Timezone:** All internal calculations, filtering, and storage operate in **UTC**. Displays in Indian Standard Time (IST) are labeled explicitly.
6. **Product Versions:** MODIS transitioned from `6.03` (2012–2022) to `61.03` (2023–2026); VIIRS is version `2`. Version strings are preserved verbatim.

---

## Windows Command Prompt (CMD) Execution

All operations must be run using standard Windows Command Prompt (`cmd.exe`).

### 1. Environment Setup

Run the backend setup script from a CMD prompt:

```cmd
cd /d D:\FireScope
scripts\setup_backend.cmd
```

This verifies the `.venv` virtual environment, installs backend dependencies (`fastapi`, `uvicorn`, `duckdb`, `pydantic`, `sqlalchemy`, `pytest`), registers package discovery, and verifies data readiness.

### 2. Start the Backend API

```cmd
cd /d D:\FireScope
scripts\run_backend.cmd
```

- **API Base URL:** `http://127.0.0.1:8000`
- **Interactive OpenAPI Documentation:** `http://127.0.0.1:8000/docs`
- **ReDoc Documentation:** `http://127.0.0.1:8000/redoc`

### 3. Run the Automated Test Suite

```cmd
cd /d D:\FireScope
scripts\test_backend.cmd
```

Runs all 26 pytest unit and integration tests and verifies route handlers against audited March 2012 and March 2024 pilot figures.

---

## Target Architecture & Data Separation

```
D:\FireScope\
├── data/
│   ├── processed/common_period/      <- Read-only normalized Parquet inputs (MODIS: 1.23M rows, VIIRS: 8.73M rows)
│   └── harmonized/                   <- Derived candidate pair superset Parquet files (2012-03, 2024-03)
├── backend/
│   ├── config.py                     <- Environment settings & CORS
│   ├── database.py                   <- Metadata DB engine (PostgreSQL-ready with local SQLite fallback)
│   ├── models.py                     <- SQLAlchemy ORM models (MatchingJob, ReviewAnnotation)
│   ├── domain/thresholds.py          <- Shared footprint geometry and threshold profile rules
│   ├── services/duckdb_service.py    <- High-performance Parquet query service via DuckDB
│   ├── schemas/                      <- Pydantic v2 schemas for all requests/responses
│   ├── routers/                      <- FastAPI routers (health, metadata, overview, detections, candidates, analytics, jobs)
│   └── main.py                       <- FastAPI app factory, CORS, and lifespan
├── tests/                            <- 26 unit and regression test cases
├── scripts/
│   ├── setup_backend.cmd             <- One-click backend setup launcher
│   ├── run_backend.cmd               <- Server launcher (uvicorn)
│   └── test_backend.cmd              <- Test suite runner
└── API_CONTRACT.md                   <- Frozen API specifications and frontend integration guide
```

---

## API Surface Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Application liveness probe |
| `GET` | `/ready` | Parquet data storage readiness and row counts |
| `GET` | `/api/v1/metadata` | Supported window, sensors, versions, and matching profiles |
| `GET` | `/api/v1/overview` | High-level summary cards (counts, FRP, matching status) |
| `GET` | `/api/v1/detections` | Paginated fire detections with viewport, date, sensor, and FRP filters |
| `GET` | `/api/v1/detections/{row_id}` | Detailed detection inspection with attached candidate matches |
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

See `API_CONTRACT.md` for complete query parameter descriptions, JSON schemas, and code examples.
