"""Generate exploratory MODIS–VIIRS spatial-temporal candidate matches.

This script does NOT claim that paired pixels are the same physical fire. It preserves
all original detections and writes candidate links plus unmatched records.
"""
from __future__ import annotations
import argparse
import json
from datetime import timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.neighbors import BallTree

EARTH_RADIUS_KM = 6371.0088
PAIR_COLUMNS = [
    "pair_id", "modis_row_id", "viirs_row_id", "distance_km", "time_diff_minutes",
    "spatial_threshold_km", "modis_datetime_utc", "viirs_datetime_utc",
    "modis_satellite", "viirs_satellite", "modis_frp_mw", "viirs_frp_mw",
    "modis_confidence_raw", "viirs_confidence_raw", "modis_daynight", "viirs_daynight",
    "modis_pixel_size_assumed", "viirs_pixel_size_assumed", "search_radius_capped",
    "match_status",
]


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def radius_km(df: pd.DataFrame, nominal_km: float) -> tuple[np.ndarray, np.ndarray]:
    """Approximate half-diagonal footprint radius; fallback dimensions are labelled assumed."""
    scan = pd.to_numeric(df["scan_km"], errors="coerce").to_numpy(dtype=float)
    track = pd.to_numeric(df["track_km"], errors="coerce").to_numpy(dtype=float)
    bad_scan = ~np.isfinite(scan) | (scan <= 0)
    bad_track = ~np.isfinite(track) | (track <= 0)
    assumed = bad_scan | bad_track

    # If the source provides pixel area but not both dimensions, infer an equivalent
    # square dimension. This remains an approximation and is flagged as assumed.
    if "pixel_area_km2" in df.columns:
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
        # If one dimension exists, infer the other from area / known dimension.
        fill_track = bad_track & can_infer_other & (scan > 0)
        fill_scan = bad_scan & can_infer_other & (track > 0)
        track[fill_track] = area[fill_track] / scan[fill_track]
        scan[fill_scan] = area[fill_scan] / track[fill_scan]

    scan[~np.isfinite(scan) | (scan <= 0)] = nominal_km
    track[~np.isfinite(track) | (track <= 0)] = nominal_km
    radii = 0.5 * np.hypot(scan, track)
    return radii, assumed


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def main():
    parser = argparse.ArgumentParser(description="Create exploratory MODIS–VIIRS candidate matches.")
    parser.add_argument("--root", default=".", help="FireScope project root")
    parser.add_argument("--time-hours", type=float, default=3.0, help="Maximum acquisition-time difference")
    parser.add_argument("--buffer-km", type=float, default=0.5, help="Additional exploratory spatial tolerance")
    parser.add_argument("--max-search-km", type=float, default=10.0, help="Safety cap for BallTree candidate search radius")
    parser.add_argument("--modis-nominal-km", type=float, default=1.0, help="Fallback scan/track dimension if missing")
    parser.add_argument("--viirs-nominal-km", type=float, default=0.375, help="Fallback scan/track dimension if missing")
    args = parser.parse_args()
    if args.time_hours <= 0 or args.buffer_km < 0 or args.max_search_km <= 0:
        parser.error("time-hours and max-search-km must be positive; buffer-km cannot be negative")

    root = Path(args.root).resolve()
    modis_path = root / "data" / "processed" / "modis_normalized.parquet"
    viirs_path = root / "data" / "processed" / "viirs_normalized.parquet"
    out_dir = root / "data" / "harmonized"
    report_dir = root / "reports" / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    if not modis_path.exists() or not viirs_path.exists():
        raise FileNotFoundError("Run scripts/02_convert_and_audit.py first; normalized Parquet files were not found.")

    con = duckdb.connect()
    mp, vp = sql_path(modis_path), sql_path(viirs_path)
    modis_days = con.execute(
        f"SELECT DISTINCT CAST(acq_datetime_utc AS DATE) AS d FROM read_parquet('{mp}') WHERE acq_datetime_utc IS NOT NULL ORDER BY d"
    ).fetchall()
    pair_path = out_dir / "match_candidates.parquet"
    writer = None
    writer_schema = None
    pair_count = 0
    pair_number = 0
    capped_search_queries = 0
    modis_missing_footprint_rows = 0
    viirs_missing_footprint_rows = 0
    time_limit_min = args.time_hours * 60.0

    for (day_value,) in modis_days:
        day = pd.Timestamp(day_value).date()
        start = day - timedelta(days=1)
        end = day + timedelta(days=1)
        m = con.execute(f"""
            SELECT row_id, latitude, longitude, acq_datetime_utc, scan_km, track_km,
                   satellite, frp_mw, confidence_raw, daynight
            FROM read_parquet('{mp}')
            WHERE CAST(acq_datetime_utc AS DATE) = DATE '{day.isoformat()}'
              AND coordinates_valid = TRUE AND datetime_valid = TRUE
        """).fetchdf()
        v = con.execute(f"""
            SELECT row_id, latitude, longitude, acq_datetime_utc, scan_km, track_km,
                   satellite, frp_mw, confidence_raw, daynight
            FROM read_parquet('{vp}')
            WHERE CAST(acq_datetime_utc AS DATE) BETWEEN DATE '{start.isoformat()}' AND DATE '{end.isoformat()}'
              AND coordinates_valid = TRUE AND datetime_valid = TRUE
        """).fetchdf()
        if m.empty or v.empty:
            continue

        m = m.dropna(subset=["latitude", "longitude", "acq_datetime_utc"]).reset_index(drop=True)
        v = v.dropna(subset=["latitude", "longitude", "acq_datetime_utc"]).reset_index(drop=True)
        if m.empty or v.empty:
            continue
        m_r, m_assumed = radius_km(m, args.modis_nominal_km)
        v_r, v_assumed = radius_km(v, args.viirs_nominal_km)
        modis_missing_footprint_rows += int(m_assumed.sum())
        viirs_missing_footprint_rows += int(v_assumed.sum())
        v_coords = np.radians(v[["latitude", "longitude"]].to_numpy(dtype=float))
        tree = BallTree(v_coords, metric="haversine")
        m_coords = np.radians(m[["latitude", "longitude"]].to_numpy(dtype=float))
        max_v_radius = float(np.nanmax(v_r)) if len(v_r) else args.viirs_nominal_km
        uncapped_search_km = m_r + max_v_radius + args.buffer_km
        search_capped = uncapped_search_km > args.max_search_km
        capped_search_queries += int(search_capped.sum())
        search_km = np.minimum(uncapped_search_km, args.max_search_km)
        neighborhoods = tree.query_radius(m_coords, r=search_km / EARTH_RADIUS_KM, return_distance=False)
        m_times = pd.to_datetime(m["acq_datetime_utc"], utc=True).astype("int64").to_numpy()
        v_times = pd.to_datetime(v["acq_datetime_utc"], utc=True).astype("int64").to_numpy()
        records = []

        for mi, candidate_indices in enumerate(neighborhoods):
            if len(candidate_indices) == 0:
                continue
            candidate_indices = np.asarray(candidate_indices, dtype=int)
            diff_min = np.abs(v_times[candidate_indices] - m_times[mi]) / 60_000_000_000.0
            time_ok = diff_min <= time_limit_min
            candidate_indices = candidate_indices[time_ok]
            diff_min = diff_min[time_ok]
            if len(candidate_indices) == 0:
                continue
            dist = haversine_km(
                float(m.iloc[mi]["latitude"]), float(m.iloc[mi]["longitude"]),
                v.iloc[candidate_indices]["latitude"].to_numpy(dtype=float),
                v.iloc[candidate_indices]["longitude"].to_numpy(dtype=float),
            )
            thresholds = m_r[mi] + v_r[candidate_indices] + args.buffer_km
            keep = dist <= thresholds
            for local_idx in np.where(keep)[0]:
                vi = int(candidate_indices[local_idx])
                pair_number += 1
                records.append({
                    "pair_id": f"PAIR_{pair_number:012d}",
                    "modis_row_id": str(m.iloc[mi]["row_id"]),
                    "viirs_row_id": str(v.iloc[vi]["row_id"]),
                    "distance_km": float(dist[local_idx]),
                    "time_diff_minutes": float(diff_min[local_idx]),
                    "spatial_threshold_km": float(thresholds[local_idx]),
                    "modis_datetime_utc": pd.Timestamp(m.iloc[mi]["acq_datetime_utc"]).isoformat(),
                    "viirs_datetime_utc": pd.Timestamp(v.iloc[vi]["acq_datetime_utc"]).isoformat(),
                    "modis_satellite": None if pd.isna(m.iloc[mi]["satellite"]) else str(m.iloc[mi]["satellite"]),
                    "viirs_satellite": None if pd.isna(v.iloc[vi]["satellite"]) else str(v.iloc[vi]["satellite"]),
                    "modis_frp_mw": None if pd.isna(m.iloc[mi]["frp_mw"]) else float(m.iloc[mi]["frp_mw"]),
                    "viirs_frp_mw": None if pd.isna(v.iloc[vi]["frp_mw"]) else float(v.iloc[vi]["frp_mw"]),
                    "modis_confidence_raw": None if pd.isna(m.iloc[mi]["confidence_raw"]) else str(m.iloc[mi]["confidence_raw"]),
                    "viirs_confidence_raw": None if pd.isna(v.iloc[vi]["confidence_raw"]) else str(v.iloc[vi]["confidence_raw"]),
                    "modis_daynight": None if pd.isna(m.iloc[mi]["daynight"]) else str(m.iloc[mi]["daynight"]),
                    "viirs_daynight": None if pd.isna(v.iloc[vi]["daynight"]) else str(v.iloc[vi]["daynight"]),
                    "modis_pixel_size_assumed": bool(m_assumed[mi]),
                    "viirs_pixel_size_assumed": bool(v_assumed[vi]),
                    "search_radius_capped": bool(search_capped[mi]),
                    "match_status": "candidate_not_confirmed",
                })

        if records:
            day_df = pd.DataFrame(records, columns=PAIR_COLUMNS)
            string_cols = ["pair_id", "modis_row_id", "viirs_row_id", "modis_datetime_utc", "viirs_datetime_utc",
                           "modis_satellite", "viirs_satellite", "modis_confidence_raw", "viirs_confidence_raw",
                           "modis_daynight", "viirs_daynight", "match_status"]
            float_cols = ["distance_km", "time_diff_minutes", "spatial_threshold_km", "modis_frp_mw", "viirs_frp_mw"]
            for col in string_cols:
                day_df[col] = day_df[col].astype("string")
            for col in float_cols:
                day_df[col] = pd.to_numeric(day_df[col], errors="coerce").astype("float64")
            for col in ["modis_pixel_size_assumed", "viirs_pixel_size_assumed", "search_radius_capped"]:
                day_df[col] = day_df[col].astype("bool")
            table = pa.Table.from_pandas(day_df, preserve_index=False)
            if writer is None:
                writer_schema = table.schema
                writer = pq.ParquetWriter(pair_path, writer_schema, compression="zstd")
            else:
                table = table.cast(writer_schema, safe=False)
            writer.write_table(table)
            pair_count += len(day_df)
        print(f"Matching {day.isoformat()} | candidate pairs so far: {pair_count:,}", end="\r")

    if writer is not None:
        writer.close()
    else:
        empty = pd.DataFrame({
            "pair_id": pd.Series(dtype="string"), "modis_row_id": pd.Series(dtype="string"),
            "viirs_row_id": pd.Series(dtype="string"), "distance_km": pd.Series(dtype="float64"),
            "time_diff_minutes": pd.Series(dtype="float64"), "spatial_threshold_km": pd.Series(dtype="float64"),
            "modis_datetime_utc": pd.Series(dtype="string"), "viirs_datetime_utc": pd.Series(dtype="string"),
            "modis_satellite": pd.Series(dtype="string"), "viirs_satellite": pd.Series(dtype="string"),
            "modis_frp_mw": pd.Series(dtype="float64"), "viirs_frp_mw": pd.Series(dtype="float64"),
            "modis_confidence_raw": pd.Series(dtype="string"), "viirs_confidence_raw": pd.Series(dtype="string"),
            "modis_daynight": pd.Series(dtype="string"), "viirs_daynight": pd.Series(dtype="string"),
            "modis_pixel_size_assumed": pd.Series(dtype="bool"), "viirs_pixel_size_assumed": pd.Series(dtype="bool"),
            "search_radius_capped": pd.Series(dtype="bool"), "match_status": pd.Series(dtype="string"),
        })
        empty.to_parquet(pair_path, index=False)

    pp = sql_path(pair_path)
    classified_path = out_dir / "candidate_match_pairs_classified.parquet"
    cp = sql_path(classified_path)
    con.execute(f"""
        COPY (
            WITH m_counts AS (SELECT modis_row_id, COUNT(DISTINCT viirs_row_id) AS viirs_candidate_count
                              FROM read_parquet('{pp}') GROUP BY modis_row_id),
                 v_counts AS (SELECT viirs_row_id, COUNT(DISTINCT modis_row_id) AS modis_candidate_count
                              FROM read_parquet('{pp}') GROUP BY viirs_row_id)
            SELECT p.*, COALESCE(m.viirs_candidate_count, 0) AS viirs_candidate_count_for_modis,
                   COALESCE(v.modis_candidate_count, 0) AS modis_candidate_count_for_viirs,
                   CASE WHEN COALESCE(m.viirs_candidate_count,0) > 1 OR COALESCE(v.modis_candidate_count,0) > 1
                        THEN 'ambiguous_candidate' ELSE 'single_candidate' END AS candidate_relationship
            FROM read_parquet('{pp}') p
            LEFT JOIN m_counts m USING (modis_row_id)
            LEFT JOIN v_counts v USING (viirs_row_id)
        ) TO '{cp}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    # Materialize both sides of each candidate pair for convenient inspection/analysis.
    matched_pairs_full = out_dir / "matched_detection_pairs.parquet"
    con.execute(f"""
        COPY (
            SELECT p.*,
                   m.latitude AS modis_latitude, m.longitude AS modis_longitude,
                   m.scan_km AS modis_scan_km, m.track_km AS modis_track_km,
                   m.version AS modis_version, m.hotspot_type AS modis_type,
                   v.latitude AS viirs_latitude, v.longitude AS viirs_longitude,
                   v.scan_km AS viirs_scan_km, v.track_km AS viirs_track_km,
                   v.version AS viirs_version, v.hotspot_type AS viirs_type,
                   v.brightness_ti4_k AS viirs_brightness_ti4_k,
                   v.brightness_ti5_k AS viirs_brightness_ti5_k,
                   m.brightness_modis_k AS modis_brightness_k,
                   m.brightness_t31_k AS modis_brightness_t31_k
            FROM read_parquet('{cp}') p
            LEFT JOIN read_parquet('{mp}') m ON m.row_id = p.modis_row_id
            LEFT JOIN read_parquet('{vp}') v ON v.row_id = p.viirs_row_id
        ) TO '{sql_path(matched_pairs_full)}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    # Unmatched records are unmatched only under the selected time/spatial parameters.
    unmatched_m = out_dir / "unmatched_modis.parquet"
    unmatched_v = out_dir / "unmatched_viirs.parquet"
    con.execute(f"""
        COPY (
            SELECT m.* FROM read_parquet('{mp}') m
            ANTI JOIN (SELECT DISTINCT modis_row_id FROM read_parquet('{pp}')) x
            ON m.row_id = x.modis_row_id
        ) TO '{sql_path(unmatched_m)}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    con.execute(f"""
        COPY (
            SELECT v.* FROM read_parquet('{vp}') v
            ANTI JOIN (SELECT DISTINCT viirs_row_id FROM read_parquet('{pp}')) x
            ON v.row_id = x.viirs_row_id
        ) TO '{sql_path(unmatched_v)}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    # MODIS-anchored candidate groups: a provisional index, not confirmed physical fire events.
    groups_path = out_dir / "event_groups.parquet"
    con.execute(f"""
        COPY (
            SELECT 'EG_' || modis_row_id AS event_group_id,
                   modis_row_id,
                   LIST(DISTINCT viirs_row_id) AS viirs_candidate_row_ids,
                   COUNT(DISTINCT viirs_row_id) AS viirs_candidate_count,
                   MIN(distance_km) AS min_candidate_distance_km,
                   MIN(time_diff_minutes) AS min_candidate_time_difference_minutes,
                   CASE WHEN COUNT(DISTINCT viirs_row_id) > 1 THEN 'multiple_viirs_candidates'
                        ELSE 'single_viirs_candidate' END AS group_status
            FROM read_parquet('{cp}')
            GROUP BY modis_row_id
        ) TO '{sql_path(groups_path)}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    # Candidate-pair diagnostics are descriptive only. Ambiguous pairs are not independent fires.
    pair_diagnostics = con.execute(f"""
        SELECT COUNT(*) AS candidate_pair_count,
               QUANTILE_CONT(distance_km, 0.5) AS median_distance_km,
               QUANTILE_CONT(distance_km, 0.95) AS p95_distance_km,
               AVG(time_diff_minutes) AS mean_time_difference_minutes,
               QUANTILE_CONT(time_diff_minutes, 0.5) AS median_time_difference_minutes,
               CORR(modis_frp_mw, viirs_frp_mw) AS candidate_pair_frp_correlation,
               SUM(CASE WHEN modis_pixel_size_assumed THEN 1 ELSE 0 END) AS pairs_using_modis_nominal_footprint,
               SUM(CASE WHEN viirs_pixel_size_assumed THEN 1 ELSE 0 END) AS pairs_using_viirs_nominal_footprint,
               SUM(CASE WHEN search_radius_capped THEN 1 ELSE 0 END) AS pairs_with_capped_search_radius
        FROM read_parquet('{cp}')
    """).fetchdf()
    pair_diagnostics.to_csv(report_dir / "candidate_pair_metrics.csv", index=False)
    relationship_counts = con.execute(f"""
        SELECT candidate_relationship, COUNT(*) AS candidate_pair_count
        FROM read_parquet('{cp}') GROUP BY 1 ORDER BY 1
    """).fetchdf()
    relationship_counts.to_csv(report_dir / "candidate_relationship_counts.csv", index=False)

    counts = con.execute(f"""
        SELECT
          (SELECT COUNT(*) FROM read_parquet('{mp}')) AS total_modis,
          (SELECT COUNT(*) FROM read_parquet('{vp}')) AS total_viirs,
          (SELECT COUNT(*) FROM read_parquet('{pp}')) AS candidate_pairs,
          (SELECT COUNT(DISTINCT modis_row_id) FROM read_parquet('{pp}')) AS modis_with_candidates,
          (SELECT COUNT(DISTINCT viirs_row_id) FROM read_parquet('{pp}')) AS viirs_with_candidates,
          (SELECT COUNT(*) FROM read_parquet('{sql_path(unmatched_m)}')) AS unmatched_modis,
          (SELECT COUNT(*) FROM read_parquet('{sql_path(unmatched_v)}')) AS unmatched_viirs,
          (SELECT COUNT(*) FROM read_parquet('{sql_path(groups_path)}')) AS provisional_modis_anchored_groups,
          (SELECT COUNT(*) FROM read_parquet('{cp}') WHERE candidate_relationship='ambiguous_candidate') AS ambiguous_candidate_pairs
    """).fetchdf().iloc[0].to_dict()
    report = {
        "method": "Exploratory footprint-aware spatial-temporal candidate matching",
        "time_window_hours": args.time_hours,
        "additional_spatial_buffer_km": args.buffer_km,
        "maximum_balltree_search_radius_km": args.max_search_km,
        "modis_rows_with_search_radius_capped": capped_search_queries,
        "modis_rows_using_nominal_footprint_fallback": modis_missing_footprint_rows,
        "viirs_rows_using_nominal_footprint_fallback_across_daily_windows": viirs_missing_footprint_rows,
        "modis_nominal_fallback_scan_track_km": args.modis_nominal_km,
        "viirs_nominal_fallback_scan_track_km": args.viirs_nominal_km,
        "footprint_radius_formula": "0.5 * sqrt(scan_km^2 + track_km^2)",
        "distance_method": "Haversine great-circle distance between pixel centres",
        "candidate_rule": "distance <= MODIS footprint radius + VIIRS footprint radius + buffer, AND time difference <= time window",
        "warning": "Candidate relationships are not proof of the same physical fire. Unmatched means no candidate under these selected parameters, not a false detection.",
        "counts": {k: (int(v) if pd.notna(v) else None) for k, v in counts.items()},
        "output_files": [str(pair_path), str(classified_path), str(matched_pairs_full), str(unmatched_m), str(unmatched_v), str(groups_path)],
    }
    with (root / "reports" / "audit" / "matching_summary.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    con.close()
    print(f"\nCandidate matching completed. Candidate pairs: {pair_count:,}")
    print("Outputs:", out_dir)
    print("Read matching_summary.json before interpreting the results.")


if __name__ == "__main__":
    main()
