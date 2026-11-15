# FireScope — Final Historical Pipeline Scientific Consistency Audit Report

**Date:** 15 November 2026
**Workspace:** `D:\FireScope`
**Evaluation Scope:** 175 Calendar Months (January 21, 2012 through July 14, 2026)
**Authoritative Archive:** 9,957,182 Observations (1,232,096 MODIS + 8,725,086 VIIRS)
**Generated Edge Volume:** 2,753,852 Globally Unique Candidate Pairs
**Audit Deliverables:**
- `historical_profile_consistency.csv`
- `historical_superset_envelope_audit.csv`
- `historical_boundary_completeness_audit.csv`
- `historical_manifest_integrity.csv`
- `historical_candidate_totals_by_profile.csv`

---

## 1. Critical Finding: Matching Profile Definition Consistency

### 1.1 Canonical Definitions vs Prior Prose Discrepancy
An audit of the codebase, backend configuration, domain logic, and underlying Parquet datasets was conducted to investigate the discrepancy regarding **Profile B**:

```
========================================================================================================================
                                     PROFILE DEFINITION RECONCILIATION AUDIT
========================================================================================================================
 Component / Layer              Profile A Definition                Profile B Definition             Audit Finding
------------------------------------------------------------------------------------------------------------------------
 backend/domain/thresholds.py    A_1h_0km (1.0h, 0.0km buffer)       B_3h_0km (3.0h, 0.0km buffer)    CANONICAL BASELINE
 scripts/03_match_sensors_v2.py  A_1h_0km (1.0h, 0.0km buffer)       B_3h_0km (3.0h, 0.0km buffer)    CANONICAL BASELINE
 scripts/batch_match_historical  A_1h_0km (1.0h, 0.0km buffer)       B_3h_0km (3.0h, 0.0km buffer)    CANONICAL BASELINE
 data/harmonized/manifest.json   A_1h_0km (1.0h, 0.0km buffer)       B_3h_0km (3.0h, 0.0km buffer)    CANONICAL BASELINE
 reports/audit/matching_*/meta   A_1h_0km (1.0h, 0.0km buffer)       B_3h_0km (3.0h, 0.0km buffer)    CANONICAL BASELINE
 frontend/src/MatchExplorer.tsx  Profile A (1h, 0km)                 Profile B (3h, 0km) — Alt        CANONICAL BASELINE
 Prior Acceptance Report Prose   Profile A (1h, 0km)                 2h limit, 1km buffer [ERRONEOUS] TYPO IN REPORT PROSE
========================================================================================================================
```

> [!IMPORTANT]
> **Resolution of Profile B Definition:**
> 1. The mention of *"2 hours, 1 km additional buffer"* in the previous acceptance report summary was **strictly a typographical error in the markdown prose**.
> 2. No software code, database schema, batch matching script, or Parquet file ever implemented or executed a 2h / 1km threshold.
> 3. Every single one of the 175 processed months was generated and stored using the canonical scientific definition:
>    $$\text{Profile B} \equiv \Delta t \le 3.0\,\text{hours}, \quad d \le r_{\text{MODIS}} + r_{\text{VIIRS}} + 0.0\,\text{km}$$
> 4. The validated benchmark counts for **March 2012** (Profile A: **44,941**, Profile B: **60,179**) and **March 2024** (Profile A: **19,949**, Profile B: **24,815**) are preserved with 100% fidelity.
> 5. Full monthly profile definitions and pair counts are cataloged in `historical_profile_consistency.csv`.

---

## 2. Candidate Superset Envelope Validation

### 2.1 Screening Envelope Analysis
In `scripts/03_match_sensors_v2.py`, the initial spatial search uses BallTree radius queries governed by:
- `BASE_TIME_HOURS = 6.0` ($\Delta t \le 360.0\,\text{minutes}$)
- `BASE_BUFFER_KM = 0.50` ($d \le r_{\text{MODIS}} + r_{\text{VIIRS}} + 0.50\,\text{km}$)

This configuration represents **Profile E** (`E_6h_050km`), which forms the superset envelope for all 175 monthly Parquet files.

```
========================================================================================================================
                               CANDIDATE SUPERSET ENVELOPE AUDIT (ALL 175 MONTHS)
========================================================================================================================
 Profile ID  Profile Name   Time Limit   Added Buffer   Supported by Archive?   Missing Pairs Relative to Mathematical Rule
------------------------------------------------------------------------------------------------------------------------
 Profile A   A_1h_0km       1.0 hour     0.00 km        YES (100% complete)     0 missing pairs
 Profile B   B_3h_0km       3.0 hours    0.00 km        YES (100% complete)     0 missing pairs
 Profile C   C_3h_025km     3.0 hours    0.25 km        YES (100% complete)     0 missing pairs
 Profile D   D_3h_050km     3.0 hours    0.50 km        YES (100% complete)     0 missing pairs
 Profile E   E_6h_050km     6.0 hours    0.50 km        YES (SUPERSET BOUNDARY) 0 missing pairs
 Profile X*  Hypothetical   12.0 hours   3.00 km        NO                      Not supported (screened at 6h / 0.5km)
========================================================================================================================
* Note: A 12-hour / 3-km envelope was mentioned as a theoretical proposal in earlier notes, but the authoritative historical
  Parquet archive was produced with a 6.0-hour / 0.50-km BallTree envelope.
```

### 2.2 Envelope Audit Findings
- **Observed Maximum Time Delta:** Exactly $6.0000\,\text{hours}$ across all 2,753,852 candidate pairs.
- **Observed Maximum Spatial Buffer:** Exactly $0.5000\,\text{km}$ beyond $r_{\text{MODIS}} + r_{\text{VIIRS}}$.
- **Missing Pairs for Canonical Profiles A–E:** Exactly **0** missing pairs across all 175 months. Every candidate pair meeting Profiles A, B, C, D, or E is guaranteed to be present within the superset Parquet files.
- Full per-month envelope metrics and percentile statistics are recorded in `historical_superset_envelope_audit.csv`.

---

## 3. Monthly Boundary Completeness & Empirical Window Testing

### 3.1 Scope of Boundary Evidence
To establish boundary completeness beyond merely verifying zero duplicate pairs across adjacent months, two distinct types of evidence were gathered:
1. **Explicit Empirical Continuous-Window Comparisons (2 Representative Windows Tested):**
   - Independent monthly generation vs. continuous multi-month generation evaluated on:
     - `2024-07-01` to `2024-08-31` (Monsoon low-activity baseline).
     - `2018-12-01` to `2019-01-31` (Calendar year transition).
2. **Archive-Wide Data Timestamp Audit (All 175 Monthly Partitions):**
   - Direct SQL inspection across all 2,753,852 generated candidate edges in the historical archive to detect any pairs where $\text{MODIS month} \ne \text{VIIRS month}$.

> [!IMPORTANT]
> **Audit Boundary Distinction:**
> - Continuous-window re-matching was **explicitly tested on the two representative adjacent windows**, yielding 100% mathematical set identity.
> - Continuous-window re-matching was **NOT** executed individually for all 174 adjacent month pairs across the 14.5-year archive (which would have required 174 multi-month BallTree reruns).
> - Instead, completeness across the remaining boundaries is directly supported by the full-archive SQL data audit confirming zero cross-month pairs, with satellite orbital overpass schedules providing supporting physical context.

```mermaid
flowchart LR
    subgraph S1["Explicit Empirical Continuous-Window Tests (2 Tested Windows)"]
        M1["Separate Monthly Processing (Sum of M1 + M2)"]
        M2["Continuous Window Processing (M1 to M2 combined)"]
        M1 <-->|Set Difference| M2
        M2 -.-> R1["2024-07 vs 2024-08: Comb ONLY = 0, Sep ONLY = 0<br/>2018-12 vs 2019-01: Comb ONLY = 0, Sep ONLY = 0"]
    end

    subgraph S2["Archive-Wide SQL Timestamp Audit (All 175 Partitions)"]
        A1["2,753,852 Historical Candidate Edges"] -->|WHERE substr(modis,1,7) != substr(viirs,1,7)| A2["Cross-Month Pairs Found: EXACTLY 0"]
        A2 -.-> R2["Supporting Context: Sun-synchronous overpass gap (~20:00 to ~05:00 UTC)"]
    end
```

### 3.2 Explicit Empirical Verification Results

| Test Case | Period | Test Type | M1 Pairs | M2 Pairs | Sum Separate | Combined Window | Combined ONLY | Separate ONLY | Set Difference | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Monsoon Baseline** | 2024-07-01 to 2024-08-31 | Continuous Window Set Comparison | 156 | 183 | **339** | **339** | **0** | **0** | **0** | **EMPIRICAL TEST PASSED (100% Identical)** |
| **Year Transition** | 2018-12-01 to 2019-01-31 | Continuous Window Set Comparison | 5,604 | 10,182 | **15,786** | **15,786** | **0** | **0** | **0** | **EMPIRICAL TEST PASSED (100% Identical)** |
| **Full Archive** | 2012-01 to 2026-07 | SQL Timestamp Integrity Audit | — | — | **2,753,852** | N/A | N/A | N/A | N/A | **DATA AUDIT VERIFIED (0 Cross-Month Pairs)** |

### 3.3 Supporting Orbital Context & Month Assignment Determinism
1. **Deterministic Month Assignment:** Every candidate pair is deterministically anchored to the acquisition timestamp of the MODIS detection (`modis_row_id`). In `03_match_sensors_v2.py`, VIIRS is staged with a $\pm 6\,\text{hour}$ temporal buffer (`start_day - 6h` to `end_day + 6h`).
2. **Sun-Synchronous Orbital Geometry over India (IST = UTC+05:30):**
   - Terra: ~05:00 UTC (~10:30 IST) & ~17:00 UTC (~22:30 IST).
   - Aqua & Suomi-NPP: ~08:00 UTC (~13:30 IST) & ~20:00 UTC (~01:30 IST).
3. **Physical Overpass Gap as Supporting Context:** Between ~20:00 UTC and ~05:00 UTC, an approximate 9-hour observation gap occurs over India. UTC midnight falls within this interval. While this orbital schedule explains why cross-boundary pairs are absent, the empirical evidence rests on the data audit of all 2,753,852 rows and the two continuous-window set comparisons.
- All evidence records are logged in `historical_boundary_completeness_audit.csv`.

---

## 4. Full Archive Reconciliation & Manifest Integrity

### 4.1 Grand Reconciliation Summary

```
========================================================================================================================
                                     HISTORICAL ARCHIVE SUMMARY (2012–2026)
========================================================================================================================
 Metric                                Target Expected         Actual Verified         Reconciliation Status
------------------------------------------------------------------------------------------------------------------------
 Calendar Months                       175                     175                     100.0% Complete
 Validated Pilot Months                2 (2012-03, 2024-03)    2 (2012-03, 2024-03)    Preserved Untouched
 Completed Historical Months           173                     173                     100.0% Complete
 Failed / Pending Months               0                       0                       Zero Failures / Zero Pending
 MODIS Common-Period Detections        1,232,096               1,232,096               Exact Reconciliation
 VIIRS Common-Period Detections        8,725,086               8,725,086               Exact Reconciliation
 Total Raw Satellite Observations      9,957,182               9,957,182               Exact Reconciliation
 Candidate Superset Edges (Profile E)  2,753,852               2,753,852               Exact Reconciliation
 Profile A Candidate Pairs (1h, 0km)   1,319,525               1,319,525               Exact Reconciliation
 Profile B Candidate Pairs (3h, 0km)   1,815,450               1,815,450               Exact Reconciliation
 Profile C Candidate Pairs (3h, .25km) 2,157,006               2,157,006               Exact Reconciliation
 Profile D Candidate Pairs (3h, .50km) 2,446,283               2,446,283               Exact Reconciliation
 Intra-Month Duplicate Edges           0                       0                       Zero Duplicate Pairs
 Global Duplicate Edges in Archive     0                       0                       Zero Duplicate Pairs
 Non-Null Candidate IDs                100%                    100%                    All Keys Well-Formed Strings
========================================================================================================================
```

### 4.2 Yearly Candidate Aggregation Table

```
========================================================================================================================
                                      ANNUAL BREAKDOWN ACROSS CANONICAL PROFILES
========================================================================================================================
 Year   Months    MODIS Obs    VIIRS Obs   Superset (Prof E)   Profile A (1h)   Profile B (3h)   Profile C (.25k)   Profile D (.50k)
------------------------------------------------------------------------------------------------------------------------
 2012     12         91,784      588,485             215,642          107,702          146,824            174,750            198,659
 2013     12         71,341      498,116             159,212           82,859          110,044            130,815            148,503
 2014     12         76,738      544,467             185,720           95,741          124,848            149,070            170,037
 2015     12         68,626      485,756             161,920           89,371          109,565            131,244            149,810
 2016     12         88,987      681,943             220,402          115,848          147,590            176,402            201,296
 2017     12         82,665      604,151             202,823          103,397          139,779            164,175            184,398
 2018     12         91,197      650,470             215,047          110,771          147,132            172,934            193,826
 2019     12         75,623      537,746             187,186           91,795          125,648            148,878            168,250
 2020     12         76,113      489,632             161,385           80,813          106,435            128,133            147,653
 2021     12        111,318      771,938             292,836          144,601          194,816            232,759            265,349
 2022     12         81,615      591,594             188,559           96,773          123,667            147,007            167,060
 2023     12         78,494      579,733             158,860           80,989          102,692            121,198            136,392
 2024     12         74,029      552,312             141,550           63,992           87,244            102,985            115,755
 2025     12         94,917      646,376             164,697           46,167           98,504            116,309            131,152
 2026      7         68,649      502,367              98,013            8,706           50,662             60,347             68,143
------------------------------------------------------------------------------------------------------------------------
 TOTAL   175      1,232,096    8,725,086           2,753,852        1,319,525        1,815,450          2,157,006          2,446,283
========================================================================================================================
```
- Full per-month manifest integrity records are saved in `historical_manifest_integrity.csv`.
- The profile breakdown is saved in `historical_candidate_totals_by_profile.csv`.

---

## 5. Scientific Status Governance & System Integrity

1. **Immutable Distinction of Status:**
   - **`VALIDATED`:** Reserved strictly for **March 2012** and **March 2024**, which underwent manual review sampling, component sensitivity auditing, and human inspection.
   - **`COMPLETED`:** Assigned to the other 173 months where batch execution, Parquet serialization, row verification, and boundary continuity succeeded automatically.
   - Automated execution never promotes an output to `VALIDATED`.
2. **Four-Tier Scientific Ontology:**
   - **Satellite Observation:** A raw FIRMS active fire pixel thermal anomaly (MODIS 1 km or VIIRS 375 m).
   - **Candidate Edge:** A geometric spatial-temporal association between a MODIS and VIIRS detection satisfying footprint and time limits.
   - **Candidate Graph Component:** A mathematical connected component in the bipartite association graph; **not a physical fire identity**.
   - **Ground-Truth Wildfire:** A physical combustion event requiring independent ground or aerial validation.

---

## 6. Verification Checklist & Deliverables Confirmation

- [x] Profile consistency audited: Profile A (`1h, 0km`) and Profile B (`3h, 0km`) confirmed canonical; prose typo resolved.
- [x] All 175 months audited for superset envelope adherence ($6.0\,\text{h}$, $0.50\,\text{km}$).
- [x] Zero missing candidate pairs for canonical Profiles A, B, C, D, and E.
- [x] Explicit empirical continuous-window comparisons executed for 2 representative boundary periods; 100% mathematical set identity demonstrated.
- [x] Archive-wide SQL data audit confirming zero cross-month candidate pairs across all 2,753,852 edges.
- [x] Physical sun-synchronous overpass gap over India documented as supporting context.
- [x] All 9,957,182 observations and 2,753,852 candidate edges reconciled across all 175 months.
- [x] Zero intra-month and zero inter-month duplicate edges.
- [x] 5 audit CSVs generated in `D:\FireScope`.
- [x] Backend automated tests (30/30) and frontend production build verified.
