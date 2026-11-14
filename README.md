# FireScope — MODIS / Suomi-NPP VIIRS starter pipeline

This starter project creates a reproducible first-pass data pipeline for the India FIRMS downloads you selected:

- MODIS Collection 6.1 (Terra/Aqua)
- Suomi-NPP VIIRS Collection 2 (375 m)

It preserves original fields, creates standardized Parquet files, audits data quality, explores cross-sensor candidate matches, retains unmatched observations, and creates monthly/annual analytics.

## Important scientific interpretation

1. A row in FIRMS is a satellite active-fire/thermal-anomaly pixel detection, not automatically a unique wildfire.
2. The matching algorithm creates **candidate correspondences**, not confirmed identical fires.
3. Unmatched means no cross-sensor candidate was found under the selected settings. It does not mean that the observation is false.
4. The code uses `scan` and `track` as approximate pixel dimensions in km when supplied. The half-diagonal is used as an approximate footprint radius. This is not a precise reconstruction of the sensor footprint or a direct geolocation-error estimate.
5. Missing scan/track values are replaced with nominal fallback values (MODIS 1.0 km; VIIRS 0.375 km) and should be reported as assumed. Inspect the audit before trusting a match result.
6. MODIS and VIIRS confidence fields are retained as raw sensor-specific values; they are not placed on a common scale.
7. Detection counts and FRP sums are reported per sensor. Do not add MODIS and VIIRS detections and call the sum a unique-fire count.

## 1. Install Python and dependencies (Windows)

Use Python 3.11 or 3.12. Open PowerShell or Command Prompt in the extracted `FireScope_Starter` folder:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `py -3.12` is unavailable, use `python -m venv .venv` with your installed Python version.

## 2. Create the folders

```powershell
python scripts\01_create_structure.py
```

Copy the original downloaded files into:

- `data\raw\modis\` — your MODIS C6.1 CSV
- `data\raw\viirs\` — your Suomi-NPP VIIRS C2 CSV

Do not edit the originals. The conversion script accepts a CSV or a ZIP containing exactly one CSV.

## 3. Convert CSV to Parquet and audit

Replace the two example filenames with your actual filenames:

```powershell
python scripts\02_convert_and_audit.py --modis "data\raw\modis\YOUR_MODIS_FILE.csv" --viirs "data\raw\viirs\YOUR_VIIRS_FILE.csv" --root .
```

For a ZIP input, pass the ZIP path. If the ZIP contains multiple CSV files, extract it first and pass the relevant CSV.

The script reads in chunks (default 250,000 rows) to reduce memory use. Change it with `--chunksize 100000` if your computer has limited RAM.

Outputs:

- `data\processed\modis_normalized.parquet`
- `data\processed\viirs_normalized.parquet`
- `reports\audit\*_audit_summary.json`
- `reports\audit\*_data_quality_report.csv` and combined `data_quality_report.csv`
- annual/monthly counts, platform/confidence/day-night counts, scan/track summaries, duplicate groups, and FRP summaries

The normalized Parquet files retain every input field in `raw_<field>` columns and add standardized columns such as `latitude`, `longitude`, `acq_datetime_utc`, `scan_km`, `track_km`, `frp_mw`, `confidence_raw`, `satellite`, and `row_id`.

## 4. Run exploratory MODIS–VIIRS matching

Start with the default three-hour window and 0.5 km additional buffer:

```powershell
python scripts\03_match_sensors.py --root . --time-hours 3 --buffer-km 0.5
```

Compare sensitivity with these additional runs. Each run overwrites the previous matching output, so copy the `data\harmonized` folder and `matching_summary.json` to a named experiment folder before changing parameters:

```powershell
python scripts\03_match_sensors.py --root . --time-hours 1 --buffer-km 0
python scripts\03_match_sensors.py --root . --time-hours 6 --buffer-km 1
python scripts\03_match_sensors.py --root . --time-hours 3 --buffer-km 2
```

These values are experiment settings, not universal scientific thresholds. Keep a record of which parameter combination produced each result. The script also records when nominal pixel-size fallbacks or the maximum search-radius cap were used. The script uses a haversine distance between pixel centres and a footprint-aware candidate threshold. It processes VIIRS records from the same UTC date and adjacent dates to handle matches near midnight.

Outputs:

- `match_candidates.parquet` — candidate edges between original detection IDs
- `candidate_match_pairs_classified.parquet` — candidate counts and ambiguity labels
- `matched_detection_pairs.parquet` — candidate rows joined to selected fields from both original normalized detections
- `unmatched_modis.parquet`
- `unmatched_viirs.parquet`
- `event_groups.parquet` — provisional MODIS-anchored candidate groups; not confirmed fire events
- `reports\audit\matching_summary.json`
- `reports\audit\candidate_pair_metrics.csv` — distance/time summaries and exploratory FRP correlation
- `reports\audit\candidate_relationship_counts.csv` — single versus ambiguous candidate relationships

## 5. Build calendar and historical analytics

```powershell
python scripts\04_build_analytics.py --root .
```

Outputs are saved in `reports\analytics`:

- `monthly_sensor_activity.csv`
- `annual_sensor_activity.csv`
- `monthly_harmonization_activity.csv`
- `calendar_*.csv` — year-by-month matrices for the frontend heatmap
- `monthly_historical_anomalies.csv` — robust anomaly calculation using prior years for the same calendar month
- `analytics_manifest.json` — definitions and interpretation notes

The first and last partial months are excluded from full-month anomaly calculations. At least three prior years are required before a robust anomaly score is calculated. A zero historical MAD is reported rather than producing an unstable score.

## 6. Recommended first quality checks

Before interpreting matches, open these files:

1. `reports\audit\combined_audit_summary.json`
2. `reports\audit\modis_scan_track_summary.csv`
3. `reports\audit\viirs_scan_track_summary.csv`
4. `reports\audit\modis_duplicate_groups.csv` and `viirs_duplicate_groups.csv`
5. `reports\audit\modis_confidence_counts.csv`
6. `reports\audit\viirs_confidence_counts.csv`
7. `reports\audit\matching_summary.json`
8. `reports\analytics\monthly_historical_anomalies.csv`

Check actual date coverage, missing scan/track values, coordinate validity, duplicate-key groups, sensor platforms, and confidence categories. Do not automatically delete duplicate-looking records; first determine whether they are true duplicate rows or separate observations.

## 7. What this starter does not do yet

- It does not download data from NASA automatically; you provide the FIRMS archive CSVs.
- It does not infer the physical perimeter or ignition point of a fire.
- It does not make a scientifically validated correction for off-nadir geolocation displacement.
- It does not classify VIIRS-only detections as small fires or MODIS-only detections as large fires.
- It does not create a global harmonized product; this pipeline operates on the India files you provide.
- The provisional event groups are candidate groupings and require further spatial/temporal extent checks before being called fire events.

## Reference documentation

- NASA FIRMS Archive Download: https://firms.modaps.eosdis.nasa.gov/download/
- NASA FIRMS Active Fire Data: https://firms.modaps.eosdis.nasa.gov/content/active_fire/
- MODIS FIRMS field descriptions: https://firms2.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_MODIS_Firehotspots.html
- VIIRS FIRMS field descriptions: https://firms2.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html
