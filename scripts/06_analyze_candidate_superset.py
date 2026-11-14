"""Analyze a FireScope MODIS-VIIRS candidate-pair superset with DuckDB.

Read-only: reads the candidate-pair Parquet and the two common-period source
Parquets, then writes compact audit CSV/JSON files. It never modifies inputs.

Default run: March 2012 pilot. Override both --start-date and --end-date for
another run whose output folders follow matching_YYYYMMDD_YYYYMMDD naming.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

try:
    import duckdb
except ImportError as exc:  # pragma: no cover - depends on the local venv
    raise SystemExit(
        "DuckDB is required. Activate D:\\FireScope\\.venv and install requirements.txt."
    ) from exc


def sql_path(path: Path) -> str:
    """Convert a Windows or POSIX path into a safely quoted DuckDB path value."""
    return str(path.resolve()).replace("\\", "/")


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def parse_iso_date(value: str, option: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{option} must use YYYY-MM-DD") from exc


def clean_json(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def fetch_one_as_dict(con: Any, query: str) -> dict[str, Any]:
    cursor = con.execute(query)
    columns = [item[0] for item in cursor.description]
    row = cursor.fetchone()
    if row is None:
        return {}
    return {name: clean_json(value) for name, value in zip(columns, row)}


def export_query(con: Any, query: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY ({query}) TO {sql_string(sql_path(destination))} "
        "(FORMAT CSV, HEADER TRUE, DELIMITER ',')"
    )


def write_dict_rows(destination: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if columns is None:
        columns = list(rows[0].keys()) if rows else []
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate full graph and threshold diagnostics from a FireScope candidate superset."
    )
    parser.add_argument("--root", default=".", help="FireScope project root")
    parser.add_argument("--start-date", help="Inclusive UTC start date (default: 2012-03-01)")
    parser.add_argument("--end-date", help="Inclusive UTC end date (default: 2012-03-31)")
    parser.add_argument("--threads", type=int, default=4, help="DuckDB threads (default: 4)")
    args = parser.parse_args()

    if args.threads < 1:
        parser.error("--threads must be at least 1")
    if bool(args.start_date) != bool(args.end_date):
        parser.error("Supply both --start-date and --end-date, or neither")

    start_day = parse_iso_date(args.start_date, "--start-date") if args.start_date else date(2012, 3, 1)
    end_day = parse_iso_date(args.end_date, "--end-date") if args.end_date else date(2012, 3, 31)
    if end_day < start_day:
        parser.error("--end-date must be on or after --start-date")

    root = Path(args.root).resolve()
    run_name = f"matching_{start_day:%Y%m%d}_{end_day:%Y%m%d}"
    audit_dir = root / "reports" / "audit" / run_name
    candidate_path = root / "data" / "harmonized" / run_name / "candidate_pairs_superset.parquet"
    modis_path = root / "data" / "processed" / "common_period" / "modis_common_20120121_20260714.parquet"
    viirs_path = root / "data" / "processed" / "common_period" / "viirs_common_20120121_20260714.parquet"
    metadata_path = audit_dir / "matching_run_metadata.json"
    output_dir = audit_dir / "candidate_graph_analysis"

    for required in (candidate_path, modis_path, viirs_path):
        if not required.is_file():
            raise FileNotFoundError(f"Required input file not found: {required}")
    output_dir.mkdir(parents=True, exist_ok=True)

    run_metadata: dict[str, Any] = {}
    if metadata_path.is_file():
        try:
            run_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            run_metadata = {}

    start_ts = f"{start_day.isoformat()} 00:00:00+00"
    end_exclusive = end_day + timedelta(days=1)
    end_ts = f"{end_exclusive.isoformat()} 00:00:00+00"
    start_literal = f"TIMESTAMPTZ {sql_string(start_ts)}"
    end_literal = f"TIMESTAMPTZ {sql_string(end_ts)}"

    con = duckdb.connect(database=":memory:")
    try:
        con.execute("SET TimeZone = 'UTC'")
        con.execute(f"SET threads = {int(args.threads)}")

        candidate_sql_path = sql_path(candidate_path)
        modis_sql_path = sql_path(modis_path)
        viirs_sql_path = sql_path(viirs_path)

        # The timestamp text in the pair file is explicitly parsed as UTC instants.
        con.execute(f"""
            CREATE TEMP VIEW candidate_raw AS
            SELECT *,
                   TRY_CAST(modis_datetime_utc AS TIMESTAMPTZ) AS _modis_ts,
                   TRY_CAST(viirs_datetime_utc AS TIMESTAMPTZ) AS _viirs_ts
            FROM read_parquet('{candidate_sql_path}')
        """)

        # A graph edge is a unique MODIS-row-ID / VIIRS-row-ID pair. Raw duplicate
        # rows are reported separately and do not inflate graph degree calculations.
        con.execute("""
            CREATE TEMP VIEW candidate_pairs AS
            SELECT *
            FROM candidate_raw
            WHERE modis_row_id IS NOT NULL AND TRIM(modis_row_id) <> ''
              AND viirs_row_id IS NOT NULL AND TRIM(viirs_row_id) <> ''
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY modis_row_id, viirs_row_id
                ORDER BY distance_km ASC NULLS LAST, time_diff_minutes ASC NULLS LAST
            ) = 1
        """)

        # Denominators come from the full common-period source files, filtered by UTC.
        modis_total = int(con.execute(f"""
            SELECT COUNT(*) FROM read_parquet('{modis_sql_path}')
            WHERE acq_datetime_utc >= {start_literal} AND acq_datetime_utc < {end_literal}
        """).fetchone()[0])
        viirs_total = int(con.execute(f"""
            SELECT COUNT(*) FROM read_parquet('{viirs_sql_path}')
            WHERE acq_datetime_utc >= {start_literal} AND acq_datetime_utc < {end_literal}
        """).fetchone()[0])

        con.execute("""
            CREATE TEMP VIEW modis_degree AS
            SELECT modis_row_id,
                   COUNT(DISTINCT viirs_row_id)::BIGINT AS candidate_degree,
                   MIN(_modis_ts) AS acquisition_utc,
                   MIN(modis_satellite) AS satellite
            FROM candidate_pairs
            GROUP BY modis_row_id
        """)
        con.execute(f"""
            CREATE TEMP VIEW viirs_degree AS
            SELECT viirs_row_id,
                   COUNT(DISTINCT modis_row_id)::BIGINT AS candidate_degree,
                   MIN(_viirs_ts) AS acquisition_utc,
                   MIN(viirs_satellite) AS satellite,
                   CASE
                     WHEN MIN(_viirs_ts) IS NULL THEN 'timestamp_unparsed'
                     WHEN MIN(_viirs_ts) >= {start_literal} AND MIN(_viirs_ts) < {end_literal}
                       THEN 'within_processing_window_utc'
                     ELSE 'outside_processing_window_utc'
                   END AS window_status
            FROM candidate_pairs
            GROUP BY viirs_row_id
        """)
        con.execute("""
            CREATE TEMP VIEW candidate_edges AS
            SELECT p.*,
                   m.candidate_degree AS modis_candidate_degree,
                   v.candidate_degree AS viirs_candidate_degree,
                   CASE
                     WHEN m.candidate_degree = 1 AND v.candidate_degree = 1 THEN 'one_to_one'
                     WHEN m.candidate_degree > 1 AND v.candidate_degree = 1 THEN 'one_modis_to_many_viirs'
                     WHEN m.candidate_degree = 1 AND v.candidate_degree > 1 THEN 'many_modis_to_one_viirs'
                     ELSE 'many_to_many'
                   END AS relationship_type
            FROM candidate_pairs p
            JOIN modis_degree m USING (modis_row_id)
            JOIN viirs_degree v USING (viirs_row_id)
        """)

        quality = fetch_one_as_dict(con, f"""
            SELECT
              (SELECT COUNT(*) FROM candidate_raw) AS raw_candidate_rows,
              (SELECT COUNT(*) FROM candidate_pairs) AS unique_candidate_pairs,
              (SELECT COUNT(*) FROM (
                 SELECT modis_row_id, viirs_row_id
                 FROM candidate_raw
                 WHERE modis_row_id IS NOT NULL AND TRIM(modis_row_id) <> ''
                   AND viirs_row_id IS NOT NULL AND TRIM(viirs_row_id) <> ''
                 GROUP BY modis_row_id, viirs_row_id HAVING COUNT(*) > 1
              )) AS duplicate_pair_groups,
              (SELECT COALESCE(SUM(n - 1), 0) FROM (
                 SELECT COUNT(*) AS n
                 FROM candidate_raw
                 WHERE modis_row_id IS NOT NULL AND TRIM(modis_row_id) <> ''
                   AND viirs_row_id IS NOT NULL AND TRIM(viirs_row_id) <> ''
                 GROUP BY modis_row_id, viirs_row_id HAVING COUNT(*) > 1
              )) AS duplicate_pair_excess_rows,
              (SELECT COUNT(*) FROM candidate_raw
               WHERE modis_row_id IS NULL OR TRIM(COALESCE(modis_row_id, '')) = ''
                  OR viirs_row_id IS NULL OR TRIM(COALESCE(viirs_row_id, '')) = '') AS rows_with_missing_pair_ids,
              (SELECT COUNT(*) FROM candidate_raw
               WHERE _modis_ts IS NULL OR _viirs_ts IS NULL) AS rows_with_unparseable_timestamps,
              (SELECT COUNT(*) FROM candidate_pairs
               WHERE distance_km IS NULL OR distance_km < 0) AS pairs_with_invalid_distance,
              (SELECT COUNT(*) FROM candidate_pairs
               WHERE time_diff_minutes IS NULL OR time_diff_minutes < 0) AS pairs_with_invalid_time_difference,
              (SELECT COUNT(*) FROM candidate_pairs
               WHERE max_rule_threshold_km IS NOT NULL
                 AND distance_km > max_rule_threshold_km + 0.000000001) AS pairs_outside_recorded_spatial_threshold,
              (SELECT COUNT(*) FROM candidate_pairs
               WHERE time_diff_minutes > 360) AS pairs_over_6_hour_superset_time_limit,
              (SELECT COUNT(DISTINCT modis_row_id) FROM candidate_pairs) AS modis_with_candidates,
              (SELECT COUNT(DISTINCT viirs_row_id) FROM candidate_pairs) AS viirs_with_candidates_including_margin,
              (SELECT COUNT(DISTINCT viirs_row_id) FROM candidate_pairs
               WHERE _viirs_ts >= {start_literal} AND _viirs_ts < {end_literal}) AS viirs_with_candidates_inside_window,
              (SELECT COUNT(DISTINCT viirs_row_id) FROM candidate_pairs
               WHERE _viirs_ts < {start_literal} OR _viirs_ts >= {end_literal}) AS viirs_with_candidates_outside_window,
              (SELECT COUNT(DISTINCT viirs_row_id) FROM candidate_pairs
               WHERE _viirs_ts IS NULL) AS viirs_with_unparsed_timestamp,
              (SELECT COUNT(*) FROM candidate_pairs
               WHERE _viirs_ts < {start_literal} OR _viirs_ts >= {end_literal}) AS candidate_pairs_using_margin_viirs_rows,
              (SELECT MIN(_modis_ts) FROM candidate_pairs) AS min_modis_candidate_timestamp_utc,
              (SELECT MAX(_modis_ts) FROM candidate_pairs) AS max_modis_candidate_timestamp_utc,
              (SELECT MIN(_viirs_ts) FROM candidate_pairs) AS min_viirs_candidate_timestamp_utc,
              (SELECT MAX(_viirs_ts) FROM candidate_pairs) AS max_viirs_candidate_timestamp_utc
        """)

        # Degree distribution with degree=0 inferred from authoritative source counts.
        degree_query = f"""
            WITH
            m_hist AS (
              SELECT candidate_degree AS degree, COUNT(*)::BIGINT AS detections
              FROM modis_degree GROUP BY candidate_degree
            ),
            v_hist AS (
              SELECT candidate_degree AS degree, COUNT(*)::BIGINT AS detections
              FROM viirs_degree
              WHERE window_status = 'within_processing_window_utc'
              GROUP BY candidate_degree
            ),
            v_margin_hist AS (
              SELECT candidate_degree AS degree, COUNT(*)::BIGINT AS detections
              FROM viirs_degree
              WHERE window_status = 'outside_processing_window_utc'
              GROUP BY candidate_degree
            ),
            m_connected AS (SELECT COUNT(*)::BIGINT AS n FROM modis_degree),
            v_connected AS (SELECT COUNT(*)::BIGINT AS n FROM viirs_degree
                            WHERE window_status = 'within_processing_window_utc')
            SELECT 'MODIS_IN_PERIOD' AS sensor_scope, degree, detections,
                   {modis_total}::BIGINT AS input_detections,
                   ROUND(100.0 * detections / NULLIF({modis_total}, 0), 4) AS pct_of_input
            FROM m_hist
            UNION ALL
            SELECT 'MODIS_IN_PERIOD', 0,
                   GREATEST({modis_total} - (SELECT n FROM m_connected), 0),
                   {modis_total},
                   ROUND(100.0 * GREATEST({modis_total} - (SELECT n FROM m_connected), 0)
                         / NULLIF({modis_total}, 0), 4)
            UNION ALL
            SELECT 'VIIRS_IN_PERIOD', degree, detections,
                   {viirs_total}, ROUND(100.0 * detections / NULLIF({viirs_total}, 0), 4)
            FROM v_hist
            UNION ALL
            SELECT 'VIIRS_IN_PERIOD', 0,
                   GREATEST({viirs_total} - (SELECT n FROM v_connected), 0),
                   {viirs_total},
                   ROUND(100.0 * GREATEST({viirs_total} - (SELECT n FROM v_connected), 0)
                         / NULLIF({viirs_total}, 0), 4)
            UNION ALL
            SELECT 'VIIRS_OUTSIDE_PERIOD_MARGIN', degree, detections,
                   NULL::BIGINT, NULL::DOUBLE
            FROM v_margin_hist
            ORDER BY sensor_scope, degree
        """
        export_query(con, degree_query, output_dir / "candidate_degree_distribution.csv")

        degree_summary_query = """
            SELECT 'MODIS' AS sensor,
                   COUNT(*) AS detections_with_candidates,
                   AVG(candidate_degree) AS mean_degree,
                   QUANTILE_CONT(candidate_degree, 0.5) AS median_degree,
                   QUANTILE_CONT(candidate_degree, 0.9) AS p90_degree,
                   QUANTILE_CONT(candidate_degree, 0.95) AS p95_degree,
                   QUANTILE_CONT(candidate_degree, 0.99) AS p99_degree,
                   MAX(candidate_degree) AS max_degree
            FROM modis_degree
            UNION ALL
            SELECT 'VIIRS_IN_PERIOD', COUNT(*), AVG(candidate_degree),
                   QUANTILE_CONT(candidate_degree, 0.5),
                   QUANTILE_CONT(candidate_degree, 0.9),
                   QUANTILE_CONT(candidate_degree, 0.95),
                   QUANTILE_CONT(candidate_degree, 0.99), MAX(candidate_degree)
            FROM viirs_degree
            WHERE window_status = 'within_processing_window_utc'
            UNION ALL
            SELECT 'VIIRS_OUTSIDE_PERIOD_MARGIN', COUNT(*), AVG(candidate_degree),
                   QUANTILE_CONT(candidate_degree, 0.5),
                   QUANTILE_CONT(candidate_degree, 0.9),
                   QUANTILE_CONT(candidate_degree, 0.95),
                   QUANTILE_CONT(candidate_degree, 0.99), MAX(candidate_degree)
            FROM viirs_degree
            WHERE window_status = 'outside_processing_window_utc'
        """
        export_query(con, degree_summary_query, output_dir / "candidate_degree_summary.csv")

        relationship_query = """
            SELECT relationship_type,
                   COUNT(*) AS candidate_pair_count,
                   COUNT(DISTINCT modis_row_id) AS distinct_modis_detections,
                   COUNT(DISTINCT viirs_row_id) AS distinct_viirs_detections,
                   ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 4) AS pct_of_candidate_pairs,
                   QUANTILE_CONT(distance_km, 0.5) AS median_distance_km,
                   QUANTILE_CONT(distance_km, 0.95) AS p95_distance_km,
                   QUANTILE_CONT(time_diff_minutes, 0.5) AS median_time_diff_minutes,
                   QUANTILE_CONT(time_diff_minutes, 0.95) AS p95_time_diff_minutes
            FROM candidate_edges
            GROUP BY relationship_type
            ORDER BY CASE relationship_type
              WHEN 'one_to_one' THEN 1
              WHEN 'one_modis_to_many_viirs' THEN 2
              WHEN 'many_modis_to_one_viirs' THEN 3
              ELSE 4 END
        """
        export_query(con, relationship_query, output_dir / "relationship_type_summary.csv")

        distance_bins = """
            CASE
              WHEN distance_km IS NULL THEN '99_missing'
              WHEN distance_km <= 0.05 THEN '00_0_to_0.05_km'
              WHEN distance_km <= 0.25 THEN '01_0.05_to_0.25_km'
              WHEN distance_km <= 0.50 THEN '02_0.25_to_0.50_km'
              WHEN distance_km <= 1.00 THEN '03_0.50_to_1.00_km'
              WHEN distance_km <= 1.50 THEN '04_1.00_to_1.50_km'
              WHEN distance_km <= 2.00 THEN '05_1.50_to_2.00_km'
              ELSE '06_over_2.00_km'
            END
        """
        time_bins = """
            CASE
              WHEN time_diff_minutes IS NULL THEN '99_missing'
              WHEN time_diff_minutes <= 15 THEN '00_0_to_15_min'
              WHEN time_diff_minutes <= 30 THEN '01_15_to_30_min'
              WHEN time_diff_minutes <= 60 THEN '02_30_to_60_min'
              WHEN time_diff_minutes <= 120 THEN '03_1_to_2_hours'
              WHEN time_diff_minutes <= 180 THEN '04_2_to_3_hours'
              WHEN time_diff_minutes <= 360 THEN '05_3_to_6_hours'
              ELSE '06_over_6_hours'
            END
        """
        export_query(con, f"""
            SELECT {distance_bins} AS distance_bin,
                   COUNT(*) AS candidate_pair_count,
                   COUNT(DISTINCT modis_row_id) AS distinct_modis,
                   COUNT(DISTINCT viirs_row_id) AS distinct_viirs
            FROM candidate_edges GROUP BY 1 ORDER BY 1
        """, output_dir / "distance_distribution.csv")
        export_query(con, f"""
            SELECT {time_bins} AS time_bin,
                   COUNT(*) AS candidate_pair_count,
                   COUNT(DISTINCT modis_row_id) AS distinct_modis,
                   COUNT(DISTINCT viirs_row_id) AS distinct_viirs
            FROM candidate_edges GROUP BY 1 ORDER BY 1
        """, output_dir / "time_difference_distribution.csv")
        export_query(con, f"""
            SELECT {distance_bins} AS distance_bin,
                   {time_bins} AS time_bin,
                   COUNT(*) AS candidate_pair_count,
                   COUNT(DISTINCT modis_row_id) AS distinct_modis,
                   COUNT(DISTINCT viirs_row_id) AS distinct_viirs
            FROM candidate_edges
            GROUP BY 1, 2 ORDER BY 1, 2
        """, output_dir / "distance_time_joint_bins.csv")

        export_query(con, """
            SELECT COALESCE(modis_satellite, 'UNKNOWN') AS modis_satellite,
                   COALESCE(viirs_satellite, 'UNKNOWN') AS viirs_satellite,
                   COALESCE(modis_daynight, 'UNKNOWN') AS modis_daynight,
                   COALESCE(viirs_daynight, 'UNKNOWN') AS viirs_daynight,
                   COALESCE(modis_version, 'UNKNOWN') AS modis_version,
                   COALESCE(viirs_version, 'UNKNOWN') AS viirs_version,
                   COUNT(*) AS candidate_pair_count,
                   COUNT(DISTINCT modis_row_id) AS distinct_modis,
                   COUNT(DISTINCT viirs_row_id) AS distinct_viirs,
                   QUANTILE_CONT(distance_km, 0.5) AS median_distance_km,
                   QUANTILE_CONT(time_diff_minutes, 0.5) AS median_time_diff_minutes
            FROM candidate_edges
            GROUP BY modis_satellite, viirs_satellite, modis_daynight, viirs_daynight,
                     modis_version, viirs_version
            ORDER BY candidate_pair_count DESC
        """, output_dir / "platform_daynight_version_counts.csv")

        export_query(con, """
            SELECT CAST(_modis_ts AS DATE) AS modis_utc_date,
                   COALESCE(modis_satellite, 'UNKNOWN') AS modis_satellite,
                   COUNT(*) AS candidate_pair_count,
                   COUNT(DISTINCT modis_row_id) AS distinct_modis,
                   COUNT(DISTINCT viirs_row_id) AS distinct_viirs
            FROM candidate_edges
            GROUP BY 1, 2 ORDER BY 1, 2
        """, output_dir / "candidate_pairs_by_modis_utc_day.csv")

        # Top-degree nodes, kept separate by sensor.
        hubs_query = """
            (SELECT 'MODIS' AS sensor, modis_row_id AS row_id,
                    candidate_degree, CAST(acquisition_utc AS VARCHAR) AS acquisition_utc,
                    COALESCE(satellite, 'UNKNOWN') AS satellite
             FROM modis_degree
             ORDER BY candidate_degree DESC, modis_row_id
             LIMIT 100)
            UNION ALL
            (SELECT 'VIIRS' AS sensor, viirs_row_id AS row_id,
                    candidate_degree, CAST(acquisition_utc AS VARCHAR) AS acquisition_utc,
                    COALESCE(satellite, 'UNKNOWN') AS satellite
             FROM viirs_degree
             ORDER BY candidate_degree DESC, viirs_row_id
             LIMIT 100)
        """
        export_query(con, hubs_query, output_dir / "highest_degree_detections.csv")

        # Relationship types and node degrees are recalculated within each experiment.
        experiments = [
            ("A_1h_0km", 60.0, 0.00),
            ("B_3h_0km", 180.0, 0.00),
            ("C_3h_025km", 180.0, 0.25),
            ("D_3h_050km", 180.0, 0.50),
            ("E_6h_050km", 360.0, 0.50),
        ]
        threshold_summary_rows: list[dict[str, Any]] = []
        threshold_degree_rows: list[dict[str, Any]] = []

        for experiment_name, max_minutes, extra_buffer in experiments:
            suffix = experiment_name.lower()
            con.execute(f"""
                CREATE OR REPLACE TEMP VIEW filtered_{suffix} AS
                SELECT * FROM candidate_pairs
                WHERE time_diff_minutes <= {max_minutes}
                  AND distance_km <= footprint_radius_sum_km + {extra_buffer}
            """)
            con.execute(f"""
                CREATE OR REPLACE TEMP VIEW modis_degree_{suffix} AS
                SELECT modis_row_id, COUNT(DISTINCT viirs_row_id)::BIGINT AS candidate_degree
                FROM filtered_{suffix} GROUP BY modis_row_id
            """)
            con.execute(f"""
                CREATE OR REPLACE TEMP VIEW viirs_degree_{suffix} AS
                SELECT viirs_row_id,
                       COUNT(DISTINCT modis_row_id)::BIGINT AS candidate_degree,
                       MIN(_viirs_ts) AS acquisition_utc,
                       CASE
                         WHEN MIN(_viirs_ts) IS NULL THEN 'timestamp_unparsed'
                         WHEN MIN(_viirs_ts) >= {start_literal} AND MIN(_viirs_ts) < {end_literal}
                           THEN 'within_processing_window_utc'
                         ELSE 'outside_processing_window_utc'
                       END AS window_status
                FROM filtered_{suffix} GROUP BY viirs_row_id
            """)
            con.execute(f"""
                CREATE OR REPLACE TEMP VIEW classified_{suffix} AS
                SELECT p.*,
                       m.candidate_degree AS modis_candidate_degree,
                       v.candidate_degree AS viirs_candidate_degree,
                       CASE
                         WHEN m.candidate_degree = 1 AND v.candidate_degree = 1 THEN 'one_to_one'
                         WHEN m.candidate_degree > 1 AND v.candidate_degree = 1 THEN 'one_modis_to_many_viirs'
                         WHEN m.candidate_degree = 1 AND v.candidate_degree > 1 THEN 'many_modis_to_one_viirs'
                         ELSE 'many_to_many'
                       END AS relationship_type
                FROM filtered_{suffix} p
                JOIN modis_degree_{suffix} m USING (modis_row_id)
                JOIN viirs_degree_{suffix} v USING (viirs_row_id)
            """)

            metrics = fetch_one_as_dict(con, f"""
                SELECT
                  {sql_string(experiment_name)} AS experiment,
                  {max_minutes / 60.0} AS time_hours,
                  {extra_buffer} AS additional_buffer_km,
                  COUNT(*) AS candidate_pair_count,
                  COUNT(DISTINCT modis_row_id) AS modis_with_candidates,
                  COUNT(DISTINCT viirs_row_id) FILTER (
                    WHERE _viirs_ts >= {start_literal} AND _viirs_ts < {end_literal}
                  ) AS viirs_with_candidates_in_period,
                  COUNT(DISTINCT viirs_row_id) FILTER (
                    WHERE _viirs_ts < {start_literal} OR _viirs_ts >= {end_literal}
                  ) AS viirs_with_candidates_in_margin,
                  COUNT(*) FILTER (WHERE relationship_type = 'one_to_one') AS one_to_one_pairs,
                  COUNT(*) FILTER (WHERE relationship_type = 'one_modis_to_many_viirs') AS one_modis_to_many_viirs_pairs,
                  COUNT(*) FILTER (WHERE relationship_type = 'many_modis_to_one_viirs') AS many_modis_to_one_viirs_pairs,
                  COUNT(*) FILTER (WHERE relationship_type = 'many_to_many') AS many_to_many_pairs,
                  COUNT(*) FILTER (WHERE modis_candidate_degree > 1 OR viirs_candidate_degree > 1) AS ambiguous_pairs,
                  AVG(modis_candidate_degree) AS mean_modis_degree_for_candidate_edges,
                  AVG(viirs_candidate_degree) AS mean_viirs_degree_for_candidate_edges,
                  QUANTILE_CONT(distance_km, 0.5) AS median_distance_km,
                  QUANTILE_CONT(time_diff_minutes, 0.5) AS median_time_diff_minutes
                FROM classified_{suffix}
            """)
            threshold_summary_rows.append(metrics)

            m_hist = con.execute(f"""
                SELECT candidate_degree, COUNT(*)
                FROM modis_degree_{suffix}
                GROUP BY candidate_degree ORDER BY candidate_degree
            """).fetchall()
            m_connected = sum(int(count) for _, count in m_hist)
            for degree, count in m_hist:
                threshold_degree_rows.append({
                    "experiment": experiment_name,
                    "sensor_scope": "MODIS_IN_PERIOD",
                    "candidate_degree": int(degree),
                    "detection_count": int(count),
                    "input_detections": modis_total,
                    "pct_of_input": round(100.0 * int(count) / modis_total, 4) if modis_total else None,
                })
            threshold_degree_rows.append({
                "experiment": experiment_name,
                "sensor_scope": "MODIS_IN_PERIOD",
                "candidate_degree": 0,
                "detection_count": max(modis_total - m_connected, 0),
                "input_detections": modis_total,
                "pct_of_input": round(100.0 * max(modis_total - m_connected, 0) / modis_total, 4) if modis_total else None,
            })

            v_hist = con.execute(f"""
                SELECT candidate_degree, COUNT(*)
                FROM viirs_degree_{suffix}
                WHERE window_status = 'within_processing_window_utc'
                GROUP BY candidate_degree ORDER BY candidate_degree
            """).fetchall()
            v_connected = sum(int(count) for _, count in v_hist)
            for degree, count in v_hist:
                threshold_degree_rows.append({
                    "experiment": experiment_name,
                    "sensor_scope": "VIIRS_IN_PERIOD",
                    "candidate_degree": int(degree),
                    "detection_count": int(count),
                    "input_detections": viirs_total,
                    "pct_of_input": round(100.0 * int(count) / viirs_total, 4) if viirs_total else None,
                })
            threshold_degree_rows.append({
                "experiment": experiment_name,
                "sensor_scope": "VIIRS_IN_PERIOD",
                "candidate_degree": 0,
                "detection_count": max(viirs_total - v_connected, 0),
                "input_detections": viirs_total,
                "pct_of_input": round(100.0 * max(viirs_total - v_connected, 0) / viirs_total, 4) if viirs_total else None,
            })

        if threshold_summary_rows:
            write_dict_rows(output_dir / "relationship_type_by_threshold.csv", threshold_summary_rows)
        write_dict_rows(
            output_dir / "degree_distribution_by_threshold.csv",
            threshold_degree_rows,
            ["experiment", "sensor_scope", "candidate_degree", "detection_count", "input_detections", "pct_of_input"],
        )

        # Deterministic review sample (up to 100 unique edges per graph relationship class).
        review_query = """
            SELECT * FROM candidate_edges
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY relationship_type
                ORDER BY MD5(modis_row_id || '|' || viirs_row_id)
            ) <= 100
            ORDER BY relationship_type, distance_km
        """
        export_query(con, review_query, output_dir / "relationship_stratified_review_sample.csv")

        pair_stats = fetch_one_as_dict(con, """
            SELECT COUNT(*) AS candidate_pair_count,
                   COUNT(DISTINCT modis_row_id) AS modis_with_candidates,
                   COUNT(DISTINCT viirs_row_id) AS viirs_with_candidates_including_margin,
                   AVG(distance_km) AS mean_distance_km,
                   QUANTILE_CONT(distance_km, 0.5) AS median_distance_km,
                   QUANTILE_CONT(distance_km, 0.9) AS p90_distance_km,
                   QUANTILE_CONT(distance_km, 0.95) AS p95_distance_km,
                   QUANTILE_CONT(distance_km, 0.99) AS p99_distance_km,
                   MAX(distance_km) AS max_distance_km,
                   AVG(time_diff_minutes) AS mean_time_diff_minutes,
                   QUANTILE_CONT(time_diff_minutes, 0.5) AS median_time_diff_minutes,
                   QUANTILE_CONT(time_diff_minutes, 0.9) AS p90_time_diff_minutes,
                   QUANTILE_CONT(time_diff_minutes, 0.95) AS p95_time_diff_minutes,
                   QUANTILE_CONT(time_diff_minutes, 0.99) AS p99_time_diff_minutes,
                   MAX(time_diff_minutes) AS max_time_diff_minutes,
                   AVG(max_rule_threshold_km - distance_km) AS mean_spatial_threshold_margin_km,
                   QUANTILE_CONT(max_rule_threshold_km - distance_km, 0.5) AS median_spatial_threshold_margin_km,
                   MIN(max_rule_threshold_km - distance_km) AS min_spatial_threshold_margin_km,
                   CORR(modis_frp_mw, viirs_frp_mw) AS pearson_frp_correlation_descriptive_only
            FROM candidate_edges
        """)
        relationship_counts = con.execute(
            "SELECT relationship_type, COUNT(*) FROM candidate_edges GROUP BY 1"
        ).fetchall()
        relationship_map = {str(name): int(count) for name, count in relationship_counts}

        summary = {
            "analysis": "Full candidate-pair graph diagnostics",
            "processing_window_utc": {
                "start_date_inclusive": start_day.isoformat(),
                "end_date_inclusive": end_day.isoformat(),
                "end_timestamp_exclusive": end_exclusive.isoformat() + "T00:00:00Z",
            },
            "candidate_superset_configuration": run_metadata.get("candidate_superset", {}),
            "input_files": {
                "candidate_superset": str(candidate_path),
                "modis_common_period": str(modis_path),
                "viirs_common_period": str(viirs_path),
            },
            "input_detection_counts_in_utc_window": {"modis": modis_total, "viirs": viirs_total},
            "candidate_graph_integrity": quality,
            "candidate_pair_statistics": pair_stats,
            "relationship_type_counts_for_superset": relationship_map,
            "interpretation": {
                "candidate_links_are_not_confirmed_physical_fire_identity": True,
                "degree_counts_are_graph_connectivity_not_confidence_scores": True,
                "threshold_degree_counts_are_recomputed_per_experiment": True,
                "zero_candidate_means_no_candidate_under_configured_rule_only": True,
                "sensor_exclusivity": "coverage_unverified; do not label unmatched observations as sensor-exclusive fires",
                "frp_correlation": "Descriptive only; candidate edges are dependent and sensor FRP values are not interchangeable.",
                "viirs_processing_margin": "VIIRS records outside the requested UTC interval may appear as temporal-margin candidates and are counted separately.",
            },
            "outputs": [
                "candidate_degree_distribution.csv",
                "candidate_degree_summary.csv",
                "relationship_type_summary.csv",
                "relationship_type_by_threshold.csv",
                "degree_distribution_by_threshold.csv",
                "distance_distribution.csv",
                "time_difference_distribution.csv",
                "distance_time_joint_bins.csv",
                "platform_daynight_version_counts.csv",
                "candidate_pairs_by_modis_utc_day.csv",
                "highest_degree_detections.csv",
                "relationship_stratified_review_sample.csv",
                "candidate_graph_summary.json",
                "README.txt",
            ],
        }
        (output_dir / "candidate_graph_summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        readme = f"""FireScope candidate graph analysis

Processing interval (UTC): {start_day.isoformat()} through {end_day.isoformat()} inclusive.
Raw candidate-pair rows: {quality.get('raw_candidate_rows')}.
Unique candidate edges used for graph calculations: {quality.get('unique_candidate_pairs')}.
MODIS source detections in UTC interval: {modis_total}.
VIIRS source detections in UTC interval: {viirs_total}.

Candidate relationships are not confirmed physical-fire identities. Degree is graph connectivity, not a confidence score. No-candidate observations remain coverage_unverified. VIIRS records outside the processing interval may be included as temporal-margin candidates and are reported separately.

All files here are derived diagnostics. Source Parquet files and the original candidate superset are not modified.
"""
        (output_dir / "README.txt").write_text(readme, encoding="utf-8")

        print("Candidate graph analysis completed.")
        print(f"Raw candidate rows: {quality.get('raw_candidate_rows'):,}")
        print(f"Unique candidate edges: {quality.get('unique_candidate_pairs'):,}")
        print(f"MODIS detections in UTC interval: {modis_total:,}")
        print(f"VIIRS detections in UTC interval: {viirs_total:,}")
        print(f"Output folder: {output_dir}")
        print("Upload candidate_graph_summary.json and the generated CSV files for review.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
