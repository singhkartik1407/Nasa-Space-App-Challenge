"""Coverage-aware, monthly MODIS–VIIRS candidate matching for FireScope.

This script creates a broad candidate-pair superset using the most permissive
planned experiment (6 hours and 0.50 km extra buffer). It then evaluates the
five planned threshold configurations without repeating spatial searches.

Important scientific constraints:
- Candidate pairs are not confirmed identical physical fires.
- No-candidate results are not called sensor-exclusive detections.
- Original common-period Parquet files are read-only and never modified.
- All calendar grouping and timestamp calculations are explicitly UTC.

Dependencies already used by the original FireScope pipeline:
  duckdb, numpy, pandas, pyarrow, scikit-learn

Example (one-month pilot):
  python scripts\\03_match_sensors_v2.py --root . --start-date 2012-03-01 --end-date 2012-03-31

After the first run builds the monthly staging datasets, reruns can pass:
  --reuse-staging
"""
from __future__ import annotations

import argparse
import glob
import json
import shutil
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.neighbors import BallTree

EARTH_RADIUS_KM = 6371.0088
BASE_TIME_HOURS = 6.0
BASE_BUFFER_KM = 0.50

EXPERIMENTS = [
    {"experiment": "A_1h_0km", "time_hours": 1.0, "buffer_km": 0.00},
    {"experiment": "B_3h_0km", "time_hours": 3.0, "buffer_km": 0.00},
    {"experiment": "C_3h_025km", "time_hours": 3.0, "buffer_km": 0.25},
    {"experiment": "D_3h_050km", "time_hours": 3.0, "buffer_km": 0.50},
    {"experiment": "E_6h_050km", "time_hours": 6.0, "buffer_km": 0.50},
]

LOAD_COLUMNS = """
    row_id,
    latitude,
    longitude,
    epoch_us(acq_datetime_utc) AS acq_epoch_us,
    scan_km,
    track_km,
    pixel_area_km2,
    satellite,
    frp_mw,
    confidence_raw,
    daynight,
    version,
    raw_version,
    hotspot_type,
    source_product,
    source_file,
    source_row,
    brightness_modis_k,
    brightness_t31_k,
    brightness_ti4_k,
    brightness_ti5_k
"""

PAIR_SCHEMA = pa.schema([
    ("modis_row_id", pa.string()),
    ("viirs_row_id", pa.string()),
    ("distance_km", pa.float64()),
    ("time_diff_minutes", pa.float64()),
    ("modis_footprint_radius_km", pa.float64()),
    ("viirs_footprint_radius_km", pa.float64()),
    ("footprint_radius_sum_km", pa.float64()),
    ("max_rule_threshold_km", pa.float64()),
    ("modis_datetime_utc", pa.string()),
    ("viirs_datetime_utc", pa.string()),
    ("modis_latitude", pa.float64()),
    ("modis_longitude", pa.float64()),
    ("viirs_latitude", pa.float64()),
    ("viirs_longitude", pa.float64()),
    ("modis_scan_km", pa.float64()),
    ("modis_track_km", pa.float64()),
    ("viirs_scan_km", pa.float64()),
    ("viirs_track_km", pa.float64()),
    ("modis_satellite", pa.string()),
    ("viirs_satellite", pa.string()),
    ("modis_frp_mw", pa.float64()),
    ("viirs_frp_mw", pa.float64()),
    ("modis_confidence_raw", pa.string()),
    ("viirs_confidence_raw", pa.string()),
    ("modis_daynight", pa.string()),
    ("viirs_daynight", pa.string()),
    ("modis_version", pa.string()),
    ("viirs_version", pa.string()),
    ("modis_raw_version", pa.string()),
    ("viirs_raw_version", pa.string()),
    ("modis_hotspot_type", pa.string()),
    ("viirs_hotspot_type", pa.string()),
    ("modis_source_product", pa.string()),
    ("viirs_source_product", pa.string()),
    ("modis_source_file", pa.string()),
    ("viirs_source_file", pa.string()),
    ("modis_source_row", pa.int64()),
    ("viirs_source_row", pa.int64()),
    ("modis_brightness_k", pa.float64()),
    ("modis_brightness_t31_k", pa.float64()),
    ("viirs_brightness_ti4_k", pa.float64()),
    ("viirs_brightness_ti5_k", pa.float64()),
    ("modis_pixel_size_assumed", pa.bool_()),
    ("viirs_pixel_size_assumed", pa.bool_()),
])


def sql_path(path: Path) -> str:
    """Return a SQL-safe absolute path using forward slashes."""
    return path.resolve().as_posix().replace("'", "''")


def sql_timestamp(value: datetime) -> str:
    """Render an aware datetime as an explicit UTC TIMESTAMPTZ literal."""
    value_utc = value.astimezone(timezone.utc)
    return value_utc.strftime("%Y-%m-%d %H:%M:%S.%f+00")


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def next_month_start(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def months_between(start_value: date, end_value: date) -> list[date]:
    result: list[date] = []
    current = month_start(start_value)
    final = month_start(end_value)
    while current <= final:
        result.append(current)
        current = next_month_start(current)
    return result


def month_partition_glob(base: Path, value: date) -> str:
    return (base / f"year={value.year}" / f"month={value.month}" / "*.parquet").as_posix()


def partition_exists(pattern: str) -> bool:
    return bool(glob.glob(pattern))


def radius_km(df: pd.DataFrame, nominal_km: float) -> tuple[np.ndarray, np.ndarray]:
    """Approximate half-diagonal radius; inferred/fallback dimensions are flagged."""
    scan = pd.to_numeric(df["scan_km"], errors="coerce").to_numpy(dtype=float)
    track = pd.to_numeric(df["track_km"], errors="coerce").to_numpy(dtype=float)
    bad_scan = ~np.isfinite(scan) | (scan <= 0)
    bad_track = ~np.isfinite(track) | (track <= 0)
    assumed = bad_scan | bad_track

    area = pd.to_numeric(df["pixel_area_km2"], errors="coerce").to_numpy(dtype=float)
    valid_area = np.isfinite(area) & (area > 0)

    both_missing = bad_scan & bad_track & valid_area
    equivalent_side = np.sqrt(np.where(valid_area, area, np.nan))
    scan[both_missing] = equivalent_side[both_missing]
    track[both_missing] = equivalent_side[both_missing]

    bad_scan = ~np.isfinite(scan) | (scan <= 0)
    bad_track = ~np.isfinite(track) | (track <= 0)
    one_missing = bad_scan ^ bad_track
    can_infer_other = one_missing & valid_area
    fill_track = bad_track & can_infer_other & (scan > 0)
    fill_scan = bad_scan & can_infer_other & (track > 0)
    track[fill_track] = area[fill_track] / scan[fill_track]
    scan[fill_scan] = area[fill_scan] / track[fill_scan]

    scan[~np.isfinite(scan) | (scan <= 0)] = nominal_km
    track[~np.isfinite(track) | (track <= 0)] = nominal_km
    return 0.5 * np.hypot(scan, track), assumed


def haversine_pairs_km(
    m_lat: np.ndarray,
    m_lon: np.ndarray,
    v_lat: np.ndarray,
    v_lon: np.ndarray,
) -> np.ndarray:
    """Vectorized great-circle distance for paired latitude/longitude arrays."""
    lat1 = np.radians(m_lat)
    lon1 = np.radians(m_lon)
    lat2 = np.radians(v_lat)
    lon2 = np.radians(v_lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def as_string_array(series: pd.Series) -> np.ndarray:
    values = series.astype("string")
    return values.to_numpy(dtype=object, na_value=None)


def utc_iso_array(epoch_us: np.ndarray) -> np.ndarray:
    return (
        pd.to_datetime(epoch_us, unit="us", utc=True)
        .strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        .to_numpy(dtype=object)
    )


def fetch_partition_window(
    con: duckdb.DuckDBPyConnection,
    stage_base: Path,
    window_start: datetime,
    window_end: datetime,
) -> pd.DataFrame:
    """Read VIIRS records from only the month partitions intersecting the window."""
    start_date = window_start.date()
    end_date = (window_end - timedelta(microseconds=1)).date()
    partition_months = months_between(start_date, end_date)
    selects: list[str] = []

    for part_month in partition_months:
        pattern = month_partition_glob(stage_base, part_month)
        if not partition_exists(pattern):
            continue
        selects.append(
            f"""SELECT {LOAD_COLUMNS}
                FROM read_parquet('{pattern.replace("'", "''")}')
                WHERE acq_datetime_utc >= TIMESTAMPTZ '{sql_timestamp(window_start)}'
                  AND acq_datetime_utc <  TIMESTAMPTZ '{sql_timestamp(window_end)}'"""
        )

    if not selects:
        return pd.DataFrame()
    return con.execute(" UNION ALL ".join(selects)).fetchdf()


def fetch_modis_month(
    con: duckdb.DuckDBPyConnection,
    stage_base: Path,
    part_month: date,
    window_start: datetime,
    window_end: datetime,
) -> pd.DataFrame:
    pattern = month_partition_glob(stage_base, part_month)
    if not partition_exists(pattern):
        return pd.DataFrame()
    sql = f"""SELECT {LOAD_COLUMNS}
              FROM read_parquet('{pattern.replace("'", "''")}')
              WHERE acq_datetime_utc >= TIMESTAMPTZ '{sql_timestamp(window_start)}'
                AND acq_datetime_utc <  TIMESTAMPTZ '{sql_timestamp(window_end)}'"""
    return con.execute(sql).fetchdf()


def pair_dataframe(
    m: pd.DataFrame,
    v: pd.DataFrame,
    m_idx: np.ndarray,
    v_idx: np.ndarray,
    distance_km: np.ndarray,
    diff_minutes: np.ndarray,
    m_radius: np.ndarray,
    v_radius: np.ndarray,
    m_assumed: np.ndarray,
    v_assumed: np.ndarray,
) -> pd.DataFrame:
    # Reset both selected frames to a shared RangeIndex.  The source_row columns
    # below use pandas' nullable Int64 dtype (a Series); without resetting, pandas
    # aligns those Series by their original row labels when constructing the output
    # DataFrame.  MODIS and VIIRS selections have different labels, which can expand
    # the output index and cause unequal column lengths.
    ms = m.iloc[m_idx].reset_index(drop=True)
    vs = v.iloc[v_idx].reset_index(drop=True)
    m_epoch = ms["acq_epoch_us"].to_numpy(dtype=np.int64)
    v_epoch = vs["acq_epoch_us"].to_numpy(dtype=np.int64)
    radius_sum = m_radius[m_idx] + v_radius[v_idx]

    out = pd.DataFrame({
        "modis_row_id": as_string_array(ms["row_id"]),
        "viirs_row_id": as_string_array(vs["row_id"]),
        "distance_km": distance_km.astype(np.float64),
        "time_diff_minutes": diff_minutes.astype(np.float64),
        "modis_footprint_radius_km": m_radius[m_idx].astype(np.float64),
        "viirs_footprint_radius_km": v_radius[v_idx].astype(np.float64),
        "footprint_radius_sum_km": radius_sum.astype(np.float64),
        "max_rule_threshold_km": (radius_sum + BASE_BUFFER_KM).astype(np.float64),
        "modis_datetime_utc": utc_iso_array(m_epoch),
        "viirs_datetime_utc": utc_iso_array(v_epoch),
        "modis_latitude": ms["latitude"].to_numpy(dtype=np.float64),
        "modis_longitude": ms["longitude"].to_numpy(dtype=np.float64),
        "viirs_latitude": vs["latitude"].to_numpy(dtype=np.float64),
        "viirs_longitude": vs["longitude"].to_numpy(dtype=np.float64),
        "modis_scan_km": ms["scan_km"].to_numpy(dtype=np.float64),
        "modis_track_km": ms["track_km"].to_numpy(dtype=np.float64),
        "viirs_scan_km": vs["scan_km"].to_numpy(dtype=np.float64),
        "viirs_track_km": vs["track_km"].to_numpy(dtype=np.float64),
        "modis_satellite": as_string_array(ms["satellite"]),
        "viirs_satellite": as_string_array(vs["satellite"]),
        "modis_frp_mw": pd.to_numeric(ms["frp_mw"], errors="coerce").to_numpy(dtype=np.float64),
        "viirs_frp_mw": pd.to_numeric(vs["frp_mw"], errors="coerce").to_numpy(dtype=np.float64),
        "modis_confidence_raw": as_string_array(ms["confidence_raw"]),
        "viirs_confidence_raw": as_string_array(vs["confidence_raw"]),
        "modis_daynight": as_string_array(ms["daynight"]),
        "viirs_daynight": as_string_array(vs["daynight"]),
        "modis_version": as_string_array(ms["version"]),
        "viirs_version": as_string_array(vs["version"]),
        "modis_raw_version": as_string_array(ms["raw_version"]),
        "viirs_raw_version": as_string_array(vs["raw_version"]),
        "modis_hotspot_type": as_string_array(ms["hotspot_type"]),
        "viirs_hotspot_type": as_string_array(vs["hotspot_type"]),
        "modis_source_product": as_string_array(ms["source_product"]),
        "viirs_source_product": as_string_array(vs["source_product"]),
        "modis_source_file": as_string_array(ms["source_file"]),
        "viirs_source_file": as_string_array(vs["source_file"]),
        "modis_source_row": pd.to_numeric(ms["source_row"], errors="coerce").astype("Int64"),
        "viirs_source_row": pd.to_numeric(vs["source_row"], errors="coerce").astype("Int64"),
        "modis_brightness_k": pd.to_numeric(ms["brightness_modis_k"], errors="coerce").to_numpy(dtype=np.float64),
        "modis_brightness_t31_k": pd.to_numeric(ms["brightness_t31_k"], errors="coerce").to_numpy(dtype=np.float64),
        "viirs_brightness_ti4_k": pd.to_numeric(vs["brightness_ti4_k"], errors="coerce").to_numpy(dtype=np.float64),
        "viirs_brightness_ti5_k": pd.to_numeric(vs["brightness_ti5_k"], errors="coerce").to_numpy(dtype=np.float64),
        "modis_pixel_size_assumed": m_assumed[m_idx].astype(bool),
        "viirs_pixel_size_assumed": v_assumed[v_idx].astype(bool),
    })
    return out


def build_candidate_pairs(
    con: duckdb.DuckDBPyConnection,
    modis_stage: Path,
    viirs_stage: Path,
    output_path: Path,
    start_day: date,
    end_day: date,
    modis_nominal_km: float,
    viirs_nominal_km: float,
    batch_size: int,
) -> tuple[int, int, int, int]:
    """Generate the superset once, writing each bounded batch to Parquet."""
    start_dt = datetime.combine(start_day, dt_time.min, tzinfo=timezone.utc)
    end_exclusive = datetime.combine(end_day + timedelta(days=1), dt_time.min, tzinfo=timezone.utc)
    time_limit_us = int(BASE_TIME_HOURS * 60.0 * 60.0 * 1_000_000)

    writer: pq.ParquetWriter | None = None
    candidate_count = 0
    modis_processed = 0
    viirs_in_period = 0
    months_processed = 0

    for part_month in months_between(start_day, end_day):
        this_month_start = datetime.combine(part_month, dt_time.min, tzinfo=timezone.utc)
        this_month_end_day = next_month_start(part_month)
        this_month_end = datetime.combine(this_month_end_day, dt_time.min, tzinfo=timezone.utc)
        chunk_start = max(start_dt, this_month_start)
        chunk_end = min(end_exclusive, this_month_end)

        m = fetch_modis_month(con, modis_stage, part_month, chunk_start, chunk_end)
        v = fetch_partition_window(
            con,
            viirs_stage,
            chunk_start - timedelta(hours=BASE_TIME_HOURS),
            chunk_end + timedelta(hours=BASE_TIME_HOURS),
        )
        months_processed += 1
        modis_processed += len(m)
        if not v.empty:
            v_epoch_for_period = v["acq_epoch_us"].to_numpy(dtype=np.int64)
            start_epoch = int(chunk_start.timestamp() * 1_000_000)
            end_epoch = int(chunk_end.timestamp() * 1_000_000)
            viirs_in_period += int(np.count_nonzero(
                (v_epoch_for_period >= start_epoch) & (v_epoch_for_period < end_epoch)
            ))

        if m.empty or v.empty:
            print(
                f"Month {part_month:%Y-%m} | MODIS {len(m):,} | VIIRS window {len(v):,} | pairs {candidate_count:,}"
            )
            continue

        # Stable row ordering makes pilot samples and pair output reproducible.
        m = m.sort_values("row_id", kind="mergesort").reset_index(drop=True)
        v = v.sort_values("row_id", kind="mergesort").reset_index(drop=True)

        m_radius, m_assumed = radius_km(m, modis_nominal_km)
        v_radius, v_assumed = radius_km(v, viirs_nominal_km)

        v_coords = np.radians(v[["latitude", "longitude"]].to_numpy(dtype=np.float64))
        tree = BallTree(v_coords, metric="haversine")
        m_coords = np.radians(m[["latitude", "longitude"]].to_numpy(dtype=np.float64))
        v_times = v["acq_epoch_us"].to_numpy(dtype=np.int64)
        m_times = m["acq_epoch_us"].to_numpy(dtype=np.int64)
        max_v_radius = float(np.max(v_radius)) if len(v_radius) else 0.0

        for batch_start in range(0, len(m), batch_size):
            batch_end = min(batch_start + batch_size, len(m))
            batch_coords = m_coords[batch_start:batch_end]
            # No artificial radius cap: the exact candidate rule is applied after search.
            search_radii_rad = (
                m_radius[batch_start:batch_end] + max_v_radius + BASE_BUFFER_KM
            ) / EARTH_RADIUS_KM
            neighborhoods = tree.query_radius(
                batch_coords,
                r=search_radii_rad,
                return_distance=False,
            )
            neighbor_counts = np.fromiter(
                (len(items) for items in neighborhoods),
                dtype=np.int64,
                count=len(neighborhoods),
            )
            total_neighbors = int(neighbor_counts.sum())
            if total_neighbors == 0:
                continue

            pair_m_local = np.repeat(np.arange(len(neighborhoods), dtype=np.int64), neighbor_counts)
            pair_v = np.concatenate(neighborhoods).astype(np.int64, copy=False)
            pair_m = pair_m_local + batch_start

            diff_us = np.abs(v_times[pair_v] - m_times[pair_m])
            time_keep = diff_us <= time_limit_us
            if not np.any(time_keep):
                continue
            pair_m = pair_m[time_keep]
            pair_v = pair_v[time_keep]
            diff_minutes = diff_us[time_keep].astype(np.float64) / 60_000_000.0

            distances = haversine_pairs_km(
                m["latitude"].to_numpy(dtype=np.float64)[pair_m],
                m["longitude"].to_numpy(dtype=np.float64)[pair_m],
                v["latitude"].to_numpy(dtype=np.float64)[pair_v],
                v["longitude"].to_numpy(dtype=np.float64)[pair_v],
            )
            thresholds = m_radius[pair_m] + v_radius[pair_v] + BASE_BUFFER_KM
            spatial_keep = distances <= thresholds
            if not np.any(spatial_keep):
                continue

            pair_m = pair_m[spatial_keep]
            pair_v = pair_v[spatial_keep]
            distances = distances[spatial_keep]
            diff_minutes = diff_minutes[spatial_keep]

            out_df = pair_dataframe(
                m, v, pair_m, pair_v, distances, diff_minutes,
                m_radius, v_radius, m_assumed, v_assumed,
            )
            table = pa.Table.from_pandas(
                out_df,
                schema=PAIR_SCHEMA,
                preserve_index=False,
                safe=False,
            )
            if writer is None:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                writer = pq.ParquetWriter(output_path, PAIR_SCHEMA, compression="zstd")
            writer.write_table(table)
            candidate_count += len(out_df)

        print(
            f"Month {part_month:%Y-%m} | MODIS {len(m):,} | VIIRS window {len(v):,} | pairs {candidate_count:,}"
        )

    if writer is not None:
        writer.close()
    else:
        empty_arrays = [pa.array([], type=field.type) for field in PAIR_SCHEMA]
        pq.write_table(pa.Table.from_arrays(empty_arrays, schema=PAIR_SCHEMA), output_path, compression="zstd")

    return candidate_count, modis_processed, viirs_in_period, months_processed


def stage_dataset(
    con: duckdb.DuckDBPyConnection,
    source_path: Path,
    target_dir: Path,
    sensor_name: str,
    stage_start: datetime,
    stage_end: datetime,
) -> None:
    """Make one sequential pass and write year/month Hive-partitioned Parquet."""
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    source_sql = sql_path(source_path)
    target_sql = sql_path(target_dir)
    print(f"Staging {sensor_name} into UTC year/month partitions...")
    con.execute(f"""
        COPY (
            SELECT *,
                   YEAR(acq_datetime_utc)::INTEGER AS year,
                   MONTH(acq_datetime_utc)::INTEGER AS month
            FROM read_parquet('{source_sql}')
            WHERE acq_datetime_utc IS NOT NULL
              AND acq_datetime_utc >= TIMESTAMPTZ '{sql_timestamp(stage_start)}'
              AND acq_datetime_utc <  TIMESTAMPTZ '{sql_timestamp(stage_end)}'
              AND coordinates_valid = TRUE
              AND datetime_valid = TRUE
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
        ) TO '{target_sql}'
        (FORMAT PARQUET, PARTITION_BY (year, month), COMPRESSION ZSTD)
    """)


def write_version_report(
    con: duckdb.DuckDBPyConnection,
    source_path: Path,
    output_csv: Path,
) -> None:
    """Retain raw and normalized version values over the full common period."""
    source_sql = sql_path(source_path)
    df = con.execute(f"""
        SELECT
            YEAR(acq_datetime_utc) AS utc_year,
            version,
            raw_version,
            satellite,
            source_product,
            COUNT(*) AS detections,
            MIN(acq_datetime_utc) AS first_timestamp_utc,
            MAX(acq_datetime_utc) AS last_timestamp_utc
        FROM read_parquet('{source_sql}')
        GROUP BY ALL
        ORDER BY utc_year, version, raw_version, satellite
    """).fetchdf()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)


def run_experiments(
    con: duckdb.DuckDBPyConnection,
    pair_path: Path,
    output_csv: Path,
    modis_processed: int,
    viirs_processed: int,
) -> list[dict]:
    """Filter the one superset and calculate per-experiment pair ambiguity metrics."""
    pair_sql = sql_path(pair_path)
    results: list[dict] = []

    for experiment in EXPERIMENTS:
        time_minutes = experiment["time_hours"] * 60.0
        buffer_km = experiment["buffer_km"]
        metrics = con.execute(f"""
            WITH filtered_pairs AS (
                SELECT *
                FROM read_parquet('{pair_sql}')
                WHERE time_diff_minutes <= {time_minutes}
                  AND distance_km <= footprint_radius_sum_km + {buffer_km}
            ),
            m_counts AS (
                SELECT modis_row_id, COUNT(DISTINCT viirs_row_id) AS candidate_count
                FROM filtered_pairs GROUP BY modis_row_id
            ),
            v_counts AS (
                SELECT viirs_row_id, COUNT(DISTINCT modis_row_id) AS candidate_count
                FROM filtered_pairs GROUP BY viirs_row_id
            )
            SELECT
                COUNT(*) AS candidate_pair_count,
                COUNT(DISTINCT p.modis_row_id) AS modis_with_candidates,
                COUNT(DISTINCT p.viirs_row_id) AS viirs_with_candidates,
                COUNT(*) FILTER (
                    WHERE COALESCE(m.candidate_count, 0) > 1
                       OR COALESCE(v.candidate_count, 0) > 1
                ) AS ambiguous_candidate_pairs,
                COUNT(*) FILTER (
                    WHERE COALESCE(m.candidate_count, 0) <= 1
                      AND COALESCE(v.candidate_count, 0) <= 1
                ) AS single_relationship_pairs,
                QUANTILE_CONT(p.distance_km, 0.50) AS median_distance_km,
                QUANTILE_CONT(p.distance_km, 0.95) AS p95_distance_km,
                QUANTILE_CONT(p.time_diff_minutes, 0.50) AS median_time_diff_minutes,
                QUANTILE_CONT(p.time_diff_minutes, 0.95) AS p95_time_diff_minutes
            FROM filtered_pairs p
            LEFT JOIN m_counts m USING (modis_row_id)
            LEFT JOIN v_counts v USING (viirs_row_id)
        """).fetchdf().iloc[0].to_dict()

        def clean(value):
            if pd.isna(value):
                return None
            if isinstance(value, (np.integer,)):
                return int(value)
            if isinstance(value, (np.floating,)):
                return float(value)
            return value

        row = {
            **experiment,
            **{key: clean(value) for key, value in metrics.items()},
            "modis_rows_in_processing_period": int(modis_processed),
            "viirs_rows_in_processing_period": int(viirs_processed),
            "modis_rows_without_candidate_under_threshold": int(
                modis_processed - int(metrics["modis_with_candidates"] or 0)
            ),
            "viirs_rows_without_candidate_under_threshold": int(
                viirs_processed - int(metrics["viirs_with_candidates"] or 0)
            ),
            "exclusivity_interpretation": "coverage_unverified; no-candidate is not sensor-exclusive evidence",
        }
        results.append(row)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(output_csv, index=False)
    return results



def write_candidate_review_sample(
    con: duckdb.DuckDBPyConnection,
    pair_path: Path,
    output_csv: Path,
    sample_size_per_group: int = 100,
) -> int:
    """Export deterministic edge-oriented samples for manual inspection."""
    pair_sql = sql_path(pair_path)
    df = con.execute(f"""
        WITH p AS (SELECT * FROM read_parquet('{pair_sql}')),
        nearest AS (
            SELECT 'nearest_centres' AS sample_reason, *
            FROM p ORDER BY distance_km ASC, time_diff_minutes ASC
            LIMIT {int(sample_size_per_group)}
        ),
        spatial_edge AS (
            SELECT 'near_spatial_boundary' AS sample_reason, *
            FROM p ORDER BY (max_rule_threshold_km - distance_km) ASC
            LIMIT {int(sample_size_per_group)}
        ),
        temporal_edge AS (
            SELECT 'largest_time_difference' AS sample_reason, *
            FROM p ORDER BY time_diff_minutes DESC, distance_km ASC
            LIMIT {int(sample_size_per_group)}
        )
        SELECT sample_reason,
               modis_row_id, viirs_row_id,
               modis_datetime_utc, viirs_datetime_utc,
               time_diff_minutes, distance_km,
               footprint_radius_sum_km, max_rule_threshold_km,
               modis_latitude, modis_longitude, viirs_latitude, viirs_longitude,
               modis_satellite, viirs_satellite,
               modis_frp_mw, viirs_frp_mw,
               modis_confidence_raw, viirs_confidence_raw,
               modis_daynight, viirs_daynight,
               modis_version, viirs_version,
               modis_source_file, modis_source_row,
               viirs_source_file, viirs_source_row
        FROM (
            SELECT * FROM nearest
            UNION ALL SELECT * FROM spatial_edge
            UNION ALL SELECT * FROM temporal_edge
        ) AS sample_rows
        ORDER BY sample_reason, distance_km
    """).fetchdf()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    return len(df)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate coverage-aware MODIS–VIIRS candidate pairs from common-period Parquet files."
    )
    parser.add_argument("--root", default=".", help="FireScope project root")
    parser.add_argument("--start-date", default="2012-01-21", help="First MODIS date to process (UTC, inclusive)")
    parser.add_argument("--end-date", default="2026-07-14", help="Last MODIS date to process (UTC, inclusive)")
    parser.add_argument("--modis-nominal-km", type=float, default=1.0)
    parser.add_argument("--viirs-nominal-km", type=float, default=0.375)
    parser.add_argument("--batch-size", type=int, default=2048, help="MODIS rows per BallTree query batch")
    parser.add_argument("--threads", type=int, default=4, help="DuckDB worker threads")
    parser.add_argument("--reuse-staging", action="store_true", help="Reuse existing monthly staging folders")
    parser.add_argument("--drop-staging-after-success", action="store_true", help="Delete temporary monthly staging after successful outputs")
    args = parser.parse_args()

    try:
        args.start_day = date.fromisoformat(args.start_date)
        args.end_day = date.fromisoformat(args.end_date)
    except ValueError as exc:
        parser.error(f"Dates must use YYYY-MM-DD: {exc}")
    if args.start_day > args.end_day:
        parser.error("start-date must be on or before end-date")
    if args.batch_size <= 0 or args.threads <= 0:
        parser.error("batch-size and threads must be positive")
    if args.modis_nominal_km <= 0 or args.viirs_nominal_km <= 0:
        parser.error("nominal footprint dimensions must be positive")
    return args


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    modis_path = root / "data" / "processed" / "common_period" / "modis_common_20120121_20260714.parquet"
    viirs_path = root / "data" / "processed" / "common_period" / "viirs_common_20120121_20260714.parquet"
    if not modis_path.exists() or not viirs_path.exists():
        raise FileNotFoundError(
            "Common-period Parquet inputs were not found. Expected both files under data\\processed\\common_period."
        )

    stage_start = datetime.combine(args.start_day, dt_time.min, tzinfo=timezone.utc) - timedelta(hours=BASE_TIME_HOURS)
    stage_end = datetime.combine(args.end_day + timedelta(days=1), dt_time.min, tzinfo=timezone.utc) + timedelta(hours=BASE_TIME_HOURS)
    stage_name = f"_staging_utc_monthly_{args.start_day:%Y%m%d}_{args.end_day:%Y%m%d}"
    stage_root = root / "data" / "harmonized" / stage_name
    modis_stage = stage_root / "modis"
    viirs_stage = stage_root / "viirs"
    run_name = f"matching_{args.start_day:%Y%m%d}_{args.end_day:%Y%m%d}"
    output_dir = root / "data" / "harmonized" / run_name
    report_dir = root / "reports" / "audit" / run_name
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    pair_path = output_dir / "candidate_pairs_superset.parquet"
    experiment_csv = report_dir / "threshold_sensitivity.csv"
    modis_version_csv = report_dir / "modis_version_by_utc_year.csv"
    viirs_version_csv = report_dir / "viirs_version_by_utc_year.csv"
    review_sample_csv = report_dir / "candidate_pairs_review_sample.csv"
    metadata_path = report_dir / "matching_run_metadata.json"

    # Remove only this run's generated outputs so a failed rerun cannot leave stale results.
    for generated_path in [
        pair_path, experiment_csv, modis_version_csv, viirs_version_csv,
        review_sample_csv, metadata_path,
    ]:
        generated_path.unlink(missing_ok=True)

    started = time.time()
    con = duckdb.connect()
    try:
        # Critical: DuckDB TIMESTAMPTZ date extraction/display otherwise follows its session timezone.
        con.execute("SET TimeZone = 'UTC'")
        con.execute(f"SET threads = {int(args.threads)}")

        if args.reuse_staging:
            if not modis_stage.exists() or not viirs_stage.exists():
                raise FileNotFoundError(
                    "Monthly staging folders were not found; run once without --reuse-staging."
                )
            print("Reusing existing UTC monthly staging folders.")
        else:
            if stage_root.exists():
                shutil.rmtree(stage_root)
            stage_root.mkdir(parents=True, exist_ok=True)
            stage_dataset(con, modis_path, modis_stage, "MODIS", stage_start, stage_end)
            stage_dataset(con, viirs_path, viirs_stage, "VIIRS", stage_start, stage_end)

        # Version is retained verbatim and reported by UTC year; no normalization is inferred here.
        write_version_report(con, modis_path, modis_version_csv)
        write_version_report(con, viirs_path, viirs_version_csv)

        candidate_count, modis_processed, viirs_processed, months_processed = build_candidate_pairs(
            con=con,
            modis_stage=modis_stage,
            viirs_stage=viirs_stage,
            output_path=pair_path,
            start_day=args.start_day,
            end_day=args.end_day,
            modis_nominal_km=args.modis_nominal_km,
            viirs_nominal_km=args.viirs_nominal_km,
            batch_size=args.batch_size,
        )

        experiments = run_experiments(
            con,
            pair_path,
            experiment_csv,
            modis_processed,
            viirs_processed,
        )
        review_sample_rows = write_candidate_review_sample(
            con, pair_path, review_sample_csv, sample_size_per_group=100
        )

        elapsed = time.time() - started
        metadata = {
            "method": "UTC month-partitioned, footprint-aware BallTree candidate generation",
            "status": "candidate relationships only; no physical-fire identity is asserted",
            "processing_window_utc": {
                "start_date_inclusive": args.start_day.isoformat(),
                "end_date_inclusive": args.end_day.isoformat(),
            },
            "candidate_superset": {
                "maximum_time_difference_hours": BASE_TIME_HOURS,
                "additional_spatial_buffer_km": BASE_BUFFER_KM,
                "footprint_radius_formula": "0.5 * sqrt(scan_km^2 + track_km^2)",
                "centre_distance_method": "Haversine great-circle distance",
                "spatial_rule": "distance_km <= MODIS radius + VIIRS radius + extra buffer",
                "search_radius_cap": None,
            },
            "timezone": "UTC (DuckDB session explicitly set to UTC; epoch microseconds used for time differences)",
            "staging_window_utc": {
                "start_inclusive": stage_start.isoformat(),
                "end_exclusive": stage_end.isoformat(),
                "directory": str(stage_root),
                "note": "Only the requested processing interval plus the six-hour candidate margin is staged.",
            },
            "input_files": {
                "modis": str(modis_path),
                "viirs": str(viirs_path),
            },
            "processing": {
                "months_processed": int(months_processed),
                "modis_rows_processed": int(modis_processed),
                "viirs_rows_in_processing_period": int(viirs_processed),
                "candidate_pairs_in_superset": int(candidate_count),
                "modis_nominal_fallback_scan_track_km": args.modis_nominal_km,
                "viirs_nominal_fallback_scan_track_km": args.viirs_nominal_km,
                "modis_rows_per_balltree_batch": int(args.batch_size),
                "duckdb_threads": int(args.threads),
                "elapsed_seconds": round(elapsed, 2),
            },
            "threshold_experiments": experiments,
            "coverage_warning": (
                "No-candidate rows are not sensor-exclusive detections. Observation coverage is not independently verified; "
                "coverage status remains unverified."
            ),
            "version_warning": (
                "MODIS and VIIRS version/raw_version values are retained verbatim. Review the version-by-UTC-year reports; "
                "do not assume different version strings are interchangeable."
            ),
            "outputs": {
                "candidate_pairs_superset": str(pair_path),
                "threshold_sensitivity": str(experiment_csv),
                "modis_version_by_utc_year": str(modis_version_csv),
                "viirs_version_by_utc_year": str(viirs_version_csv),
                "candidate_pairs_review_sample": str(review_sample_csv),
                "metadata": str(metadata_path),
                "review_sample_rows": int(review_sample_rows),
            },
        }
        with metadata_path.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, default=str)

        if args.drop_staging_after_success:
            shutil.rmtree(stage_root, ignore_errors=True)

        print("\nCandidate superset completed.")
        print(f"Candidate pairs: {candidate_count:,}")
        print(f"MODIS rows processed: {modis_processed:,}")
        print(f"VIIRS rows in requested period: {viirs_processed:,}")
        print(f"Outputs: {output_dir}")
        print(f"Reports: {report_dir}")
        print(f"Manual review sample rows: {review_sample_rows:,}")
        print("Review threshold_sensitivity.csv and candidate_pairs_review_sample.csv before selecting a default threshold.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
