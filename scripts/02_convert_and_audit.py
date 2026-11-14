"""Convert FIRMS CSV files to normalized Parquet and create audit reports.

The original source fields are retained as raw_<field> string columns. Standardized
numeric/time fields are added separately so that sensor-specific values are not lost.
"""
from __future__ import annotations
import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Iterator, TextIO

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ALIASES = {
    "lat": "latitude", "lon": "longitude",
    "acqdate": "acq_date", "date": "acq_date", "yyyymmdd": "acq_date",
    "hhmm": "acq_time", "time": "acq_time",
    "t4": "bright_ti4", "t5": "bright_ti5",
    "dnflag": "daynight", "dn_flag": "daynight",
    "pixarea": "pixel_area_km2", "pix_area": "pixel_area_km2",
    "frp": "frp", "bright_t31": "bright_t31",
}


def clean_name(name: str) -> str:
    value = str(name).replace("\ufeff", "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return ALIASES.get(value, value)


def csv_stream(path: Path) -> tuple[TextIO, object | None]:
    """Return a text stream and an optional ZIP owner that must remain open."""
    if path.suffix.lower() == ".zip":
        zf = zipfile.ZipFile(path)
        members = [n for n in zf.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
        if len(members) != 1:
            zf.close()
            raise ValueError(
                f"{path.name} contains {len(members)} CSV files. Extract the ZIP and pass one CSV file."
            )
        return zf.open(members[0], "r"), zf
    if path.suffix.lower() != ".csv":
        raise ValueError(f"Input must be a .csv or a .zip containing exactly one CSV: {path}")
    return path.open("r", encoding="utf-8-sig", newline=""), None


def parse_datetime(date_series: pd.Series, time_series: pd.Series) -> pd.Series:
    date_text = date_series.astype("string").str.strip()
    # Accept YYYYMMDD as well as YYYY-MM-DD.
    compact = date_text.str.fullmatch(r"\d{8}", na=False)
    date_text.loc[compact] = pd.to_datetime(date_text.loc[compact], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
    parsed_date = pd.to_datetime(date_text, errors="coerce")

    time_text = time_series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    time_text = time_text.str.replace(r"[^0-9]", "", regex=True).str.zfill(4).str[-4:]
    valid_time = time_text.str.fullmatch(r"\d{4}", na=False)
    timestamp_text = parsed_date.dt.strftime("%Y-%m-%d") + " " + time_text
    result = pd.to_datetime(timestamp_text.where(valid_time), format="%Y-%m-%d %H%M", errors="coerce", utc=True)
    return result


def numeric(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype="float64")
    return pd.to_numeric(series, errors="coerce")


def process_sensor(sensor: str, input_path: Path, output_path: Path, chunksize: int) -> dict:
    stream, zip_owner = csv_stream(input_path)
    writer = None
    writer_schema = None
    row_offset = 0
    raw_columns: list[str] | None = None
    total_rows = 0
    try:
        reader = pd.read_csv(stream, chunksize=chunksize, low_memory=False, dtype="string")
        for chunk_number, chunk in enumerate(reader, start=1):
            chunk.columns = [clean_name(c) for c in chunk.columns]
            # Preserve the incoming fields under raw_* names. Detect collisions explicitly.
            if len(set(chunk.columns)) != len(chunk.columns):
                raise ValueError("The input CSV has duplicate column names after normalization. Please inspect its header.")
            required = {"latitude", "longitude", "acq_date", "acq_time"}
            missing = required - set(chunk.columns)
            if missing:
                raise ValueError(
                    f"{input_path.name} is missing required fields {sorted(missing)}. "
                    f"Detected columns: {list(chunk.columns)}"
                )
            if raw_columns is None:
                raw_columns = list(chunk.columns)
            elif list(chunk.columns) != raw_columns:
                raise ValueError("CSV column names changed between chunks; use one consistent FIRMS CSV per sensor.")

            df = pd.DataFrame(index=chunk.index)
            for col in raw_columns:
                df[f"raw_{col}"] = chunk[col].astype("string")

            df["latitude"] = numeric(chunk["latitude"])
            df["longitude"] = numeric(chunk["longitude"])
            df["scan_km"] = numeric(chunk["scan"]) if "scan" in chunk else pd.NA
            df["track_km"] = numeric(chunk["track"]) if "track" in chunk else pd.NA
            df["frp_mw"] = numeric(chunk["frp"]) if "frp" in chunk else pd.NA
            df["brightness_modis_k"] = numeric(chunk["brightness"]) if "brightness" in chunk else pd.NA
            df["brightness_t31_k"] = numeric(chunk["bright_t31"]) if "bright_t31" in chunk else pd.NA
            df["brightness_ti4_k"] = numeric(chunk["bright_ti4"]) if "bright_ti4" in chunk else pd.NA
            df["brightness_ti5_k"] = numeric(chunk["bright_ti5"]) if "bright_ti5" in chunk else pd.NA
            df["pixel_area_km2"] = numeric(chunk["pixel_area_km2"]) if "pixel_area_km2" in chunk else pd.NA
            df["confidence_raw"] = chunk["confidence"].astype("string") if "confidence" in chunk else pd.NA
            df["satellite"] = chunk["satellite"].astype("string") if "satellite" in chunk else pd.NA
            df["daynight"] = chunk["daynight"].astype("string") if "daynight" in chunk else pd.NA
            df["version"] = chunk["version"].astype("string") if "version" in chunk else pd.NA
            df["hotspot_type"] = chunk["type"].astype("string") if "type" in chunk else pd.NA
            df["acq_date"] = chunk["acq_date"].astype("string")
            df["acq_time"] = chunk["acq_time"].astype("string")
            df["acq_datetime_utc"] = parse_datetime(chunk["acq_date"], chunk["acq_time"])
            df["sensor"] = sensor
            df["source_product"] = "MODIS_C6_1" if sensor == "MODIS" else "SUOMI_NPP_VIIRS_C2"
            df["source_file"] = input_path.name
            start_row = row_offset + 1
            end_row = row_offset + len(chunk)
            df["source_row"] = range(start_row, end_row + 1)
            df["row_id"] = [f"{sensor}_{input_path.stem}_{i:012d}" for i in range(start_row, end_row + 1)]
            df["coordinates_valid"] = df["latitude"].between(-90, 90) & df["longitude"].between(-180, 180)
            df["datetime_valid"] = df["acq_datetime_utc"].notna()

            # Make nullable fields stable between chunks for Arrow.
            for col in ["scan_km", "track_km", "frp_mw", "brightness_modis_k", "brightness_t31_k",
                        "brightness_ti4_k", "brightness_ti5_k", "pixel_area_km2"]:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
            for col in ["confidence_raw", "satellite", "daynight", "version", "hotspot_type"]:
                df[col] = df[col].astype("string")
            df["source_row"] = df["source_row"].astype("int64")
            df["coordinates_valid"] = df["coordinates_valid"].astype("bool")
            df["datetime_valid"] = df["datetime_valid"].astype("bool")

            table = pa.Table.from_pandas(df, preserve_index=False)
            if writer is None:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                writer_schema = table.schema
                writer = pq.ParquetWriter(output_path, writer_schema, compression="zstd")
            else:
                # Force all later chunks into the first chunk's exact schema.
                table = table.cast(writer_schema, safe=False)
            writer.write_table(table)
            row_offset += len(chunk)
            total_rows += len(chunk)
            print(f"{sensor}: converted {total_rows:,} rows...", end="\r")
    finally:
        if writer is not None:
            writer.close()
        stream.close()
        if zip_owner is not None:
            zip_owner.close()

    if total_rows == 0:
        raise ValueError(f"No data rows were found in {input_path}")
    print(f"\n{sensor}: wrote {total_rows:,} rows to {output_path}")
    return {"sensor": sensor, "input_file": str(input_path), "parquet_file": str(output_path), "rows_written": total_rows}


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def create_reports(sensor: str, parquet_path: Path, report_dir: Path) -> dict:
    report_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    p = sql_path(parquet_path)
    base = f"read_parquet('{p}')"
    summary = con.execute(f"""
        SELECT COUNT(*) AS rows,
               MIN(CAST(acq_datetime_utc AS DATE)) AS min_date,
               MAX(CAST(acq_datetime_utc AS DATE)) AS max_date,
               SUM(CASE WHEN NOT coordinates_valid THEN 1 ELSE 0 END) AS invalid_coordinates,
               SUM(CASE WHEN NOT datetime_valid THEN 1 ELSE 0 END) AS invalid_datetime,
               SUM(CASE WHEN frp_mw IS NULL THEN 1 ELSE 0 END) AS missing_frp,
               SUM(CASE WHEN scan_km IS NULL OR track_km IS NULL THEN 1 ELSE 0 END) AS missing_scan_track,
               COUNT(DISTINCT satellite) AS satellite_values
        FROM {base}
    """).fetchdf().iloc[0].to_dict()

    queries = {
        f"{sensor.lower()}_annual_counts.csv": f"""
            SELECT EXTRACT(YEAR FROM acq_datetime_utc)::INTEGER AS year, COUNT(*) AS detection_count
            FROM {base} WHERE acq_datetime_utc IS NOT NULL GROUP BY 1 ORDER BY 1""",
        f"{sensor.lower()}_monthly_counts.csv": f"""
            SELECT EXTRACT(YEAR FROM acq_datetime_utc)::INTEGER AS year,
                   EXTRACT(MONTH FROM acq_datetime_utc)::INTEGER AS month,
                   COUNT(*) AS detection_count,
                   SUM(frp_mw) AS total_frp_mw,
                   AVG(frp_mw) AS mean_frp_mw
            FROM {base} WHERE acq_datetime_utc IS NOT NULL GROUP BY 1,2 ORDER BY 1,2""",
        f"{sensor.lower()}_platform_counts.csv": f"""
            SELECT COALESCE(satellite, 'UNKNOWN') AS satellite, COUNT(*) AS detection_count
            FROM {base} GROUP BY 1 ORDER BY 2 DESC""",
        f"{sensor.lower()}_confidence_counts.csv": f"""
            SELECT COALESCE(confidence_raw, 'MISSING') AS confidence_raw, COUNT(*) AS detection_count
            FROM {base} GROUP BY 1 ORDER BY 2 DESC""",
        f"{sensor.lower()}_daynight_counts.csv": f"""
            SELECT COALESCE(daynight, 'MISSING') AS daynight, COUNT(*) AS detection_count
            FROM {base} GROUP BY 1 ORDER BY 2 DESC""",
        f"{sensor.lower()}_scan_track_summary.csv": f"""
            SELECT COUNT(scan_km) AS scan_n, AVG(scan_km) AS scan_mean_km,
                   QUANTILE_CONT(scan_km, 0.5) AS scan_median_km,
                   QUANTILE_CONT(scan_km, 0.95) AS scan_p95_km,
                   COUNT(track_km) AS track_n, AVG(track_km) AS track_mean_km,
                   QUANTILE_CONT(track_km, 0.5) AS track_median_km,
                   QUANTILE_CONT(track_km, 0.95) AS track_p95_km
            FROM {base}""",
    }
    for filename, query in queries.items():
        con.execute(query).fetchdf().to_csv(report_dir / filename, index=False)

    dup = con.execute(f"""
        SELECT COUNT(*) AS duplicate_key_groups, COALESCE(SUM(n - 1), 0) AS excess_duplicate_rows
        FROM (
            SELECT COUNT(*) AS n FROM {base}
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND acq_datetime_utc IS NOT NULL
            GROUP BY latitude, longitude, acq_datetime_utc, satellite, frp_mw, scan_km, track_km
            HAVING COUNT(*) > 1
        )
    """).fetchdf().iloc[0].to_dict()
    duplicate_groups = con.execute(f"""
        SELECT latitude, longitude, acq_datetime_utc, satellite, frp_mw, scan_km, track_km,
               COUNT(*) AS duplicate_count, LIST(row_id) AS row_ids
        FROM {base}
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND acq_datetime_utc IS NOT NULL
        GROUP BY latitude, longitude, acq_datetime_utc, satellite, frp_mw, scan_km, track_km
        HAVING COUNT(*) > 1 ORDER BY duplicate_count DESC
    """).fetchdf()
    duplicate_groups.to_csv(report_dir / f"{sensor.lower()}_duplicate_groups.csv", index=False)
    frp_stats = con.execute(f"""
        SELECT COUNT(frp_mw) AS frp_n, AVG(frp_mw) AS frp_mean_mw,
               QUANTILE_CONT(frp_mw, 0.5) AS frp_median_mw,
               QUANTILE_CONT(frp_mw, 0.9) AS frp_p90_mw,
               QUANTILE_CONT(frp_mw, 0.95) AS frp_p95_mw,
               MAX(frp_mw) AS frp_max_mw
        FROM {base}
    """).fetchdf()
    frp_stats.to_csv(report_dir / f"{sensor.lower()}_frp_summary.csv", index=False)
    summary.update({k: (v.isoformat() if hasattr(v, "isoformat") else (None if pd.isna(v) else v)) for k, v in summary.items()})
    summary.update({k: int(v) for k, v in dup.items()})
    summary["sensor"] = sensor
    summary["parquet_file"] = str(parquet_path)
    with (report_dir / f"{sensor.lower()}_audit_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    quality_rows = [
        {"sensor": sensor, "metric": k, "value": v}
        for k, v in summary.items() if k not in {"sensor", "parquet_file"}
    ]
    pd.DataFrame(quality_rows).to_csv(report_dir / f"{sensor.lower()}_data_quality_report.csv", index=False)
    con.close()
    return summary


def main():
    parser = argparse.ArgumentParser(description="Convert MODIS and VIIRS FIRMS CSVs to Parquet and audit them.")
    parser.add_argument("--modis", required=True, help="Path to MODIS CSV (or ZIP containing one CSV)")
    parser.add_argument("--viirs", required=True, help="Path to Suomi-NPP VIIRS CSV (or ZIP containing one CSV)")
    parser.add_argument("--root", default=".", help="FireScope project root")
    parser.add_argument("--chunksize", type=int, default=250_000, help="Rows per conversion chunk")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    processed = root / "data" / "processed"
    audit_dir = root / "reports" / "audit"
    processed.mkdir(parents=True, exist_ok=True)
    modis_in, viirs_in = Path(args.modis).resolve(), Path(args.viirs).resolve()
    modis_out, viirs_out = processed / "modis_normalized.parquet", processed / "viirs_normalized.parquet"
    process_sensor("MODIS", modis_in, modis_out, args.chunksize)
    process_sensor("VIIRS", viirs_in, viirs_out, args.chunksize)
    modis_summary = create_reports("MODIS", modis_out, audit_dir)
    viirs_summary = create_reports("VIIRS", viirs_out, audit_dir)
    combined = {"MODIS": modis_summary, "VIIRS": viirs_summary}
    with (audit_dir / "combined_audit_summary.json").open("w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, default=str)
    quality_frames = [pd.read_csv(audit_dir / "modis_data_quality_report.csv"),
                      pd.read_csv(audit_dir / "viirs_data_quality_report.csv")]
    pd.concat(quality_frames, ignore_index=True).to_csv(audit_dir / "data_quality_report.csv", index=False)
    print("\nAudit reports created in:", audit_dir)


if __name__ == "__main__":
    main()
