"""Create common-date MODIS and VIIRS Parquet datasets and date-bounded audit reports.

Default comparison window: 2012-01-21 through 2026-07-14 (inclusive).
The normalized source Parquet files are never modified.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def write_query_csv(con: duckdb.DuckDBPyConnection, query: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(query).fetchdf().to_csv(path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create MODIS and VIIRS Parquet files restricted to a shared date window."
    )
    parser.add_argument("--root", default=".", help="FireScope project root")
    parser.add_argument("--start-date", default="2012-01-21", help="Inclusive start date YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-07-14", help="Inclusive end date YYYY-MM-DD")
    args = parser.parse_args()

    start = pd.Timestamp(args.start_date).date()
    end = pd.Timestamp(args.end_date).date()
    if start > end:
        raise SystemExit("ERROR: --start-date must be on or before --end-date.")

    root = Path(args.root).resolve()
    source_dir = root / "data" / "processed"
    output_dir = source_dir / "common_period"
    report_dir = root / "reports" / "audit"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    sources = {
        "MODIS": source_dir / "modis_normalized.parquet",
        "VIIRS": source_dir / "viirs_normalized.parquet",
    }
    for sensor, path in sources.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}. Run scripts/02_convert_and_audit.py first.")

    start_sql = start.isoformat()
    end_sql = end.isoformat()
    suffix = f"{start:%Y%m%d}_{end:%Y%m%d}"
    outputs = {
        "MODIS": output_dir / f"modis_common_{suffix}.parquet",
        "VIIRS": output_dir / f"viirs_common_{suffix}.parquet",
    }

    con = duckdb.connect()
    summaries: dict[str, dict] = {}

    for sensor, source in sources.items():
        src = sql_path(source)
        dst = sql_path(outputs[sensor])
        con.execute(f"""
            COPY (
                SELECT *
                FROM read_parquet('{src}')
                WHERE acq_datetime_utc IS NOT NULL
                  AND CAST(acq_datetime_utc AS DATE)
                      BETWEEN DATE '{start_sql}' AND DATE '{end_sql}'
            ) TO '{dst}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)

        out = sql_path(outputs[sensor])
        summary = con.execute(f"""
            SELECT COUNT(*)::BIGINT AS rows,
                   MIN(CAST(acq_datetime_utc AS DATE))::VARCHAR AS min_date,
                   MAX(CAST(acq_datetime_utc AS DATE))::VARCHAR AS max_date,
                   COUNT(DISTINCT CAST(acq_datetime_utc AS DATE))::BIGINT AS days_with_detections,
                   COUNT(DISTINCT (EXTRACT(YEAR FROM acq_datetime_utc),
                                   EXTRACT(MONTH FROM acq_datetime_utc)))::BIGINT AS months_with_detections,
                   COUNT(DISTINCT satellite)::BIGINT AS satellite_values,
                   SUM(frp_mw)::DOUBLE AS total_frp_mw,
                   AVG(frp_mw)::DOUBLE AS mean_frp_mw,
                   QUANTILE_CONT(frp_mw, 0.5)::DOUBLE AS median_frp_mw,
                   QUANTILE_CONT(scan_km, 0.5)::DOUBLE AS median_scan_km,
                   QUANTILE_CONT(track_km, 0.5)::DOUBLE AS median_track_km
            FROM read_parquet('{out}')
        """).fetchdf().iloc[0].to_dict()
        summary = {
            k: (None if pd.isna(v) else (int(v) if k in {
                "rows", "days_with_detections", "months_with_detections", "satellite_values"
            } else float(v) if isinstance(v, (int, float)) else str(v)))
            for k, v in summary.items()
        }
        summary["output_file"] = str(outputs[sensor])
        summaries[sensor] = summary
        print(f"{sensor}: {summary['rows']:,} rows | {summary['min_date']} to {summary['max_date']}")

    modis = sql_path(outputs["MODIS"])
    viirs = sql_path(outputs["VIIRS"])

    monthly_query = f"""
        WITH all_months AS (
            SELECT 'MODIS' AS sensor,
                   EXTRACT(YEAR FROM acq_datetime_utc)::INTEGER AS year,
                   EXTRACT(MONTH FROM acq_datetime_utc)::INTEGER AS month,
                   COUNT(*)::BIGINT AS detection_count,
                   SUM(frp_mw)::DOUBLE AS total_frp_mw,
                   AVG(frp_mw)::DOUBLE AS mean_frp_mw
            FROM read_parquet('{modis}') GROUP BY 1,2,3
            UNION ALL
            SELECT 'VIIRS' AS sensor,
                   EXTRACT(YEAR FROM acq_datetime_utc)::INTEGER AS year,
                   EXTRACT(MONTH FROM acq_datetime_utc)::INTEGER AS month,
                   COUNT(*)::BIGINT AS detection_count,
                   SUM(frp_mw)::DOUBLE AS total_frp_mw,
                   AVG(frp_mw)::DOUBLE AS mean_frp_mw
            FROM read_parquet('{viirs}') GROUP BY 1,2,3
        )
        SELECT year, month,
               SUM(CASE WHEN sensor='MODIS' THEN detection_count ELSE 0 END)::BIGINT AS modis_detections,
               SUM(CASE WHEN sensor='VIIRS' THEN detection_count ELSE 0 END)::BIGINT AS viirs_detections,
               SUM(CASE WHEN sensor='MODIS' THEN total_frp_mw ELSE 0 END)::DOUBLE AS modis_total_frp_mw,
               SUM(CASE WHEN sensor='VIIRS' THEN total_frp_mw ELSE 0 END)::DOUBLE AS viirs_total_frp_mw,
               MAX(CASE WHEN sensor='MODIS' THEN mean_frp_mw END)::DOUBLE AS modis_mean_frp_mw,
               MAX(CASE WHEN sensor='VIIRS' THEN mean_frp_mw END)::DOUBLE AS viirs_mean_frp_mw,
               CASE WHEN SUM(CASE WHEN sensor='MODIS' THEN detection_count ELSE 0 END) > 0
                    THEN SUM(CASE WHEN sensor='VIIRS' THEN detection_count ELSE 0 END)::DOUBLE /
                         SUM(CASE WHEN sensor='MODIS' THEN detection_count ELSE 0 END)
                    ELSE NULL END AS viirs_to_modis_detection_ratio
        FROM all_months GROUP BY year, month ORDER BY year, month
    """
    write_query_csv(con, monthly_query, report_dir / "common_period_monthly_activity.csv")

    daily_query = f"""
        WITH m AS (
            SELECT CAST(acq_datetime_utc AS DATE) AS acq_date, COUNT(*)::BIGINT AS modis_detections
            FROM read_parquet('{modis}') GROUP BY 1
        ), v AS (
            SELECT CAST(acq_datetime_utc AS DATE) AS acq_date, COUNT(*)::BIGINT AS viirs_detections
            FROM read_parquet('{viirs}') GROUP BY 1
        )
        SELECT COALESCE(m.acq_date, v.acq_date)::DATE AS acq_date,
               COALESCE(m.modis_detections, 0)::BIGINT AS modis_detections,
               COALESCE(v.viirs_detections, 0)::BIGINT AS viirs_detections
        FROM m FULL OUTER JOIN v USING (acq_date)
        ORDER BY acq_date
    """
    write_query_csv(con, daily_query, report_dir / "common_period_daily_detection_counts.csv")

    platform_query = f"""
        SELECT sensor, satellite, COUNT(*)::BIGINT AS detections
        FROM (
            SELECT 'MODIS' AS sensor, satellite FROM read_parquet('{modis}')
            UNION ALL
            SELECT 'VIIRS' AS sensor, satellite FROM read_parquet('{viirs}')
        ) x GROUP BY 1,2 ORDER BY 1,3 DESC
    """
    write_query_csv(con, platform_query, report_dir / "common_period_platform_counts.csv")

    confidence_query = f"""
        SELECT sensor, confidence_raw, COUNT(*)::BIGINT AS detections
        FROM (
            SELECT 'MODIS' AS sensor, COALESCE(confidence_raw, 'MISSING') AS confidence_raw
            FROM read_parquet('{modis}')
            UNION ALL
            SELECT 'VIIRS' AS sensor, COALESCE(confidence_raw, 'MISSING') AS confidence_raw
            FROM read_parquet('{viirs}')
        ) x GROUP BY 1,2 ORDER BY 1,3 DESC
    """
    write_query_csv(con, confidence_query, report_dir / "common_period_confidence_counts.csv")

    daynight_query = f"""
        SELECT sensor, daynight, COUNT(*)::BIGINT AS detections
        FROM (
            SELECT 'MODIS' AS sensor, COALESCE(daynight, 'MISSING') AS daynight
            FROM read_parquet('{modis}')
            UNION ALL
            SELECT 'VIIRS' AS sensor, COALESCE(daynight, 'MISSING') AS daynight
            FROM read_parquet('{viirs}')
        ) x GROUP BY 1,2 ORDER BY 1,3 DESC
    """
    write_query_csv(con, daynight_query, report_dir / "common_period_daynight_counts.csv")

    frp_scan_query = f"""
        SELECT sensor,
               COUNT(frp_mw)::BIGINT AS frp_n,
               AVG(frp_mw)::DOUBLE AS frp_mean_mw,
               QUANTILE_CONT(frp_mw, 0.5)::DOUBLE AS frp_median_mw,
               QUANTILE_CONT(frp_mw, 0.9)::DOUBLE AS frp_p90_mw,
               QUANTILE_CONT(frp_mw, 0.95)::DOUBLE AS frp_p95_mw,
               MAX(frp_mw)::DOUBLE AS frp_max_mw,
               QUANTILE_CONT(scan_km, 0.5)::DOUBLE AS median_scan_km,
               QUANTILE_CONT(track_km, 0.5)::DOUBLE AS median_track_km
        FROM (
            SELECT 'MODIS' AS sensor, frp_mw, scan_km, track_km FROM read_parquet('{modis}')
            UNION ALL
            SELECT 'VIIRS' AS sensor, frp_mw, scan_km, track_km FROM read_parquet('{viirs}')
        ) x GROUP BY sensor ORDER BY sensor
    """
    write_query_csv(con, frp_scan_query, report_dir / "common_period_frp_scan_track_summary.csv")

    summary_path = report_dir / "common_period_summary.json"
    overall = {
        "comparison_window": {
            "start_date_inclusive": start_sql,
            "end_date_inclusive": end_sql,
            "interpretation": "A common calendar window. This does not by itself prove complete sensor observation coverage on every day."
        },
        "sensors": summaries,
        "important_notes": [
            "Original normalized Parquet files were not modified.",
            "The common-period files retain all source columns for detections in the selected date window.",
            "A day absent from a hotspot detection table means zero recorded detections in that file, not necessarily missing satellite coverage.",
            "MODIS and VIIRS detection counts are sensor pixel detections, not unique physical fire counts.",
            "FRP is summarized separately by sensor; do not add the two sensor totals and interpret them as unique fire energy."
        ],
        "outputs": {
            "modis_common_parquet": str(outputs["MODIS"]),
            "viirs_common_parquet": str(outputs["VIIRS"]),
            "monthly_activity": str(report_dir / "common_period_monthly_activity.csv"),
            "daily_detection_counts": str(report_dir / "common_period_daily_detection_counts.csv"),
            "platform_counts": str(report_dir / "common_period_platform_counts.csv"),
            "confidence_counts": str(report_dir / "common_period_confidence_counts.csv"),
            "daynight_counts": str(report_dir / "common_period_daynight_counts.csv"),
            "frp_scan_track_summary": str(report_dir / "common_period_frp_scan_track_summary.csv")
        }
    }
    summary_path.write_text(json.dumps(overall, indent=2), encoding="utf-8")
    con.close()

    print("\nCommon-period datasets created without modifying the original normalized files.")
    print(f"Window: {start_sql} through {end_sql} (inclusive)")
    print(f"MODIS: {outputs['MODIS']}")
    print(f"VIIRS: {outputs['VIIRS']}")
    print(f"Reports: {report_dir}")
    print("\nRemember: common dates do not guarantee full daily satellite coverage.")


if __name__ == "__main__":
    main()
