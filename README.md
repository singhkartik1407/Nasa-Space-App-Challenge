# FireScope — Active Fire Harmonization Platform

FireScope is an active-fire satellite observation harmonization and analysis platform bridging NASA FIRMS data across two sensor families:
- **MODIS** Collection 6.1 (Terra and Aqua satellites)
- **Suomi-NPP VIIRS** Collection 2 (375 m nominal resolution)

The system features:
- High-performance analytical queries directly over normalized Parquet files (9.95M+ observations) using an embedded **DuckDB** engine.
- Cross-sensor candidate relationship matching evaluating footprint overlap and temporal proximity under **Profile A** (conservative default: $\Delta t \le 1\,\text{h}$, $0\,\text{km}$ buffer) and **Profile B** (alternative: $\Delta t \le 3\,\text{h}$, $0\,\text{km}$ buffer).
- Production-grade **FastAPI** backend with automated testing, SQLite local metadata persistence, and PostgreSQL-ready schema.
- High-performance **React + TypeScript + Vite** frontend featuring MapLibre WebGL fire mapping, interactive Recharts analytics, live candidate inspection, and full scientific safeguards.

---

## Important Scientific Ground Rules

1. **Observations vs Fires:** A FIRMS record is a satellite active-fire/thermal-anomaly pixel detection, not automatically an isolated physical wildfire.
2. **Candidate Correspondences:** Cross-sensor pairs indicate spatiotemporal proximity within combined footprint bounds; they are **not confirmed ground-truth matches**.
3. **Coverage Unverified:** Absence of a counterpart detection is labeled as `coverage_unverified`, never as "false detection" or "sensor-exclusive".
4. **Instrument-Separated FRP:** Fire Radiative Power (MW) differs across instruments due to pixel footprint and sensor saturation characteristics. **Never sum MODIS and VIIRS FRP together**.
5. **Canonical Timezone:** All internal calculations, filtering, and storage operate in **UTC**. Displays in Indian Standard Time (IST) are labeled explicitly.
6. **Product Versions:** MODIS transitioned from `6.03` (2012–2022) to `61.03` (2023–2026); VIIRS is version `2`. Version strings are preserved verbatim.
7. **Graph Connected Components:** Connected components of candidate pairs are mathematical graph groupings, not distinct wildfire events.

---

## Audited Pilot Period Reconciliation

The backend and frontend strictly reproduce the verified benchmark reconciliation counts across both pilot periods:

| Pilot Period | MODIS Detections | VIIRS Detections | Profile A Pairs ($\Delta t \le 1\text{h}$) | Profile B Pairs ($\Delta t \le 3\text{h}$) |
|---|---:|---:|---:|---:|
| **March 2012** | 30,161 | 182,644 | 44,941 | 60,179 |
| **March 2024** | 14,139 | 103,369 | 19,949 | 24,815 |

---

## Windows Command Prompt (CMD) Execution

All operations must be run using standard Windows Command Prompt (`cmd.exe`). Do not use PowerShell.

### 1. One-Click Full Demo Launcher

To launch both the FastAPI backend and the Vite frontend simultaneously in dedicated windows:

```cmd
cd /d D:\FireScope
scripts\run_demo.cmd
```

This spawns:
- **Backend API:** `http://127.0.0.1:8000` (Docs: `http://127.0.0.1:8000/docs`)
- **Frontend UI:** `http://127.0.0.1:5173`

### 2. Individual Service Launchers

**Backend Setup & Launch:**
```cmd
cd /d D:\FireScope
scripts\setup_backend.cmd
scripts\run_backend.cmd
```

**Frontend Dev Server:**
```cmd
cd /d D:\FireScope
scripts\run_frontend.cmd
```

### 3. Automated Test Suites

**Backend Tests (26 Pytest + Direct Handler Checks):**
```cmd
cd /d D:\FireScope
scripts\test_backend.cmd
```

**Frontend Checks (TypeScript strict check + Vite production build):**
```cmd
cd /d D:\FireScope
scripts\test_frontend.cmd
```

---

## Application Structure

```
D:\FireScope\
├── data/
│   ├── processed/common_period/      <- Read-only normalized Parquet inputs (MODIS: 1.23M rows, VIIRS: 8.73M rows)
│   └── harmonized/                   <- Harmonized candidate superset Parquet files (2012-03, 2024-03)
├── backend/
│   ├── config.py                     <- Environment settings & CORS
│   ├── database.py                   <- Metadata DB engine (SQLite fallback, PostgreSQL-ready)
│   ├── models.py                     <- SQLAlchemy ORM models (MatchingJob, ReviewAnnotation)
│   ├── domain/thresholds.py          <- Footprint geometry (Haversine, ellipse) and Profiles A-E
│   ├── services/duckdb_service.py    <- Zero-copy Parquet analytical queries via DuckDB
│   ├── schemas/                      <- Pydantic v2 schemas for all requests/responses
│   ├── routers/                      <- FastAPI routers (health, metadata, overview, detections, candidates, analytics, jobs)
│   └── main.py                       <- FastAPI app factory, CORS, and lifespan
├── frontend/                         <- React + TypeScript + Vite Web Client
│   ├── src/
│   │   ├── components/               <- 8 Integrated Views:
│   │   │   ├── Dashboard             <- Live overview cards, global date/sensor filters
│   │   │   ├── FireMap               <- MapLibre WebGL raster map with MODIS/VIIRS overlays & inspection popups
│   │   │   ├── ActivityCalendar      <- Live monthly observation breakdown per sensor
│   │   │   ├── AnalyticsOverview     <- Sensor-separated FRP percentiles & Profile sensitivity
│   │   │   ├── MatchExplorer         <- Profile A/B candidate pairs inspection table
│   │   │   ├── DataSources           <- Live backend readiness & dataset metadata
│   │   │   ├── SettingsPage          <- Live backend connectivity, ping latency, & engine stats
│   │   │   └── DocumentationPage     <- Scientific methodology and data dictionary
│   │   ├── lib/api/                  <- Type-safe API client adapters
│   │   └── App.tsx                   <- Global filter state and navigation coordinator
│   ├── .env                          <- Default environment (VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1)
│   └── .env.local                    <- Local overrides (never committed)
├── tests/                            <- 26 unit and regression test cases
├── scripts/
│   ├── setup_backend.cmd             <- One-click backend dependency & data setup
│   ├── run_backend.cmd               <- Launch FastAPI via Uvicorn on 127.0.0.1:8000
│   ├── test_backend.cmd              <- Run backend test suite
│   ├── run_frontend.cmd              <- Launch Vite dev server on 127.0.0.1:5173
│   ├── test_frontend.cmd             <- Run TypeScript verification & Vite build
│   └── run_demo.cmd                  <- Launch both backend & frontend for demo
├── API_CONTRACT.md                   <- Complete API contract and frontend integration mapping
└── IMPLEMENTATION_STATUS.md          <- System implementation and verification report
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

See `API_CONTRACT.md` for full schema details, code examples, and frontend mapping tables.
