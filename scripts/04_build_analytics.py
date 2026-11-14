"""Build monthly/annual activity tables, calendar matrices and robust anomalies."""
from __future__ import annotations
import argparse
import json
import calendar
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

MONTH_NAMES = [calendar.month_abbr[i] for i in range(1, 13)]


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def write_calendar(df: pd.DataFrame, value_col: str, out_path: Path):
    if df.empty:
        pd.DataFrame(columns=["year"] + MONTH_NAMES).to_csv(out_path, index=False)
        return
    pivot = df.pivot_table(index="year", columns="month", values=value_col, aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(columns=range(1, 13), fill_value=0)
    pivot.columns = MONTH_NAMES
    pivot.reset_index().to_csv(out_path, index=False)


def compute_anomalies(monthly: pd.DataFrame, sensor: str, data_start, data_end) -> pd.DataFrame:
    df = monthly[monthly["sensor"] == sensor].copy().sort_values(["month", "year"])
    if df.empty:
        return df
    start = pd.Timestamp(data_start).date() if data_start else None
    end = pd.Timestamp(data_end).date() if data_end else None
    results = []
    for _, row in df.iterrows():
        yr, mo = int(row["year"]), int(row["month"])
        # Exclude partial first/last calendar months from full-month comparisons.
        partial = ((start is not None and yr == start.year and mo == start.month and start.day > 1) or
                   (end is not None and yr == end.year and mo == end.month and end.day < calendar.monthrange(yr, mo)[1]))
        history_rows = df[(df["month"] == mo) & (df["year"] < yr)].copy()
        if start is not None:
            first_month_partial = (history_rows["year"] == start.year) & (history_rows["month"] == start.month) & (start.day > 1)
            history_rows = history_rows.loc[~first_month_partial]
        history = history_rows["detection_count"].astype(float)
        if partial:
            median = mad = robust_z = np.nan
            status = "partial_month_excluded_from_full_month_anomaly"
        elif len(history) < 3:
            median = float(history.median()) if len(history) else np.nan
            mad = float((history - median).abs().median()) if len(history) else np.nan
            robust_z = np.nan
            status = "insufficient_prior_years"
        else:
            median = float(history.median())
            mad = float((history - median).abs().median())
            if mad == 0:
                robust_z = np.nan
                status = "zero_historical_MAD"
            else:
                robust_z = float((float(row["detection_count"]) - median) / (1.4826 * mad))
                status = "calculated"
        results.append({
            "sensor": sensor, "year": yr, "month": mo,
            "detection_count": int(row["detection_count"]),
            "historical_years_used": int(len(history)),
            "historical_median": median,
            "historical_mad": mad,
            "robust_z_score": robust_z,
            "status": status,
        })
    return pd.DataFrame(results)


def main():
    parser = argparse.ArgumentParser(description="Build FireScope calendar and analytics CSV reports.")
    parser.add_argument("--root", default=".", help="FireScope project root")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    processed = root / "data" / "processed"
    harmonized = root / "data" / "harmonized"
    out = root / "reports" / "analytics"
    out.mkdir(parents=True, exist_ok=True)
    modis = processed / "modis_normalized.parquet"
    viirs = processed / "viirs_normalized.parquet"
    pairs = harmonized / "candidate_match_pairs_classified.parquet"
    unmatched_m = harmonized / "unmatched_modis.parquet"
    unmatched_v = harmonized / "unmatched_viirs.parquet"
    groups = harmonized / "event_groups.parquet"
    for path in [modis, viirs, pairs, unmatched_m, unmatched_v, groups]:
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}. Run conversion and matching scripts first.")

    con = duckdb.connect()
    mp, vp = sql_path(modis), sql_path(viirs)
    monthly_m = con.execute(f"""
        SELECT 'MODIS' AS sensor, EXTRACT(YEAR FROM acq_datetime_utc)::INTEGER AS year,
               EXTRACT(MONTH FROM acq_datetime_utc)::INTEGER AS month,
               COUNT(*)::BIGINT AS detection_count, SUM(frp_mw) AS total_frp_mw, AVG(frp_mw) AS mean_frp_mw
        FROM read_parquet('{mp}') WHERE acq_datetime_utc IS NOT NULL GROUP BY 1,2,3
    """).fetchdf()
    monthly_v = con.execute(f"""
        SELECT 'VIIRS' AS sensor, EXTRACT(YEAR FROM acq_datetime_utc)::INTEGER AS year,
               EXTRACT(MONTH FROM acq_datetime_utc)::INTEGER AS month,
               COUNT(*)::BIGINT AS detection_count, SUM(frp_mw) AS total_frp_mw, AVG(frp_mw) AS mean_frp_mw
        FROM read_parquet('{vp}') WHERE acq_datetime_utc IS NOT NULL GROUP BY 1,2,3
    """).fetchdf()
    monthly = pd.concat([monthly_m, monthly_v], ignore_index=True).sort_values(["sensor", "year", "month"])
    monthly.to_csv(out / "monthly_sensor_activity.csv", index=False)

    annual = con.execute(f"""
        SELECT sensor, EXTRACT(YEAR FROM acq_datetime_utc)::INTEGER AS year,
               COUNT(*)::BIGINT AS detection_count, SUM(frp_mw) AS total_frp_mw, AVG(frp_mw) AS mean_frp_mw
        FROM (
            SELECT 'MODIS' AS sensor, acq_datetime_utc, frp_mw FROM read_parquet('{mp}')
            UNION ALL
            SELECT 'VIIRS' AS sensor, acq_datetime_utc, frp_mw FROM read_parquet('{vp}')
        ) combined
        WHERE acq_datetime_utc IS NOT NULL GROUP BY 1,2 ORDER BY 1,2
    """).fetchdf()
    annual.to_csv(out / "annual_sensor_activity.csv", index=False)

    unmatched_m_counts = con.execute(f"""
        SELECT EXTRACT(YEAR FROM acq_datetime_utc)::INTEGER AS year,
               EXTRACT(MONTH FROM acq_datetime_utc)::INTEGER AS month, COUNT(*)::BIGINT AS modis_only_count
        FROM read_parquet('{sql_path(unmatched_m)}') WHERE acq_datetime_utc IS NOT NULL GROUP BY 1,2
    """).fetchdf()
    unmatched_v_counts = con.execute(f"""
        SELECT EXTRACT(YEAR FROM acq_datetime_utc)::INTEGER AS year,
               EXTRACT(MONTH FROM acq_datetime_utc)::INTEGER AS month, COUNT(*)::BIGINT AS viirs_only_count
        FROM read_parquet('{sql_path(unmatched_v)}') WHERE acq_datetime_utc IS NOT NULL GROUP BY 1,2
    """).fetchdf()
    pair_monthly = con.execute(f"""
        SELECT EXTRACT(YEAR FROM CAST(modis_datetime_utc AS TIMESTAMPTZ))::INTEGER AS year,
               EXTRACT(MONTH FROM CAST(modis_datetime_utc AS TIMESTAMPTZ))::INTEGER AS month,
               COUNT(*)::BIGINT AS candidate_pair_count,
               SUM(CASE WHEN candidate_relationship='ambiguous_candidate' THEN 1 ELSE 0 END)::BIGINT AS ambiguous_pair_count
        FROM read_parquet('{sql_path(pairs)}') GROUP BY 1,2
    """).fetchdf()
    groups_monthly = con.execute(f"""
        SELECT EXTRACT(YEAR FROM m.acq_datetime_utc)::INTEGER AS year,
               EXTRACT(MONTH FROM m.acq_datetime_utc)::INTEGER AS month,
               COUNT(*)::BIGINT AS provisional_group_count
        FROM read_parquet('{sql_path(groups)}') g
        JOIN read_parquet('{mp}') m ON m.row_id = g.modis_row_id
        GROUP BY 1,2
    """).fetchdf()

    keys = set()
    for frame in [monthly_m, monthly_v, unmatched_m_counts, unmatched_v_counts, pair_monthly, groups_monthly]:
        keys.update((int(r.year), int(r.month)) for r in frame.itertuples())
    activity = pd.DataFrame(sorted(keys), columns=["year", "month"])
    for frame in [monthly_m[["year", "month", "detection_count"]].rename(columns={"detection_count": "modis_detection_count"}),
                  monthly_v[["year", "month", "detection_count"]].rename(columns={"detection_count": "viirs_detection_count"}),
                  unmatched_m_counts, unmatched_v_counts, pair_monthly, groups_monthly]:
        activity = activity.merge(frame, on=["year", "month"], how="left")
    count_cols = [c for c in activity.columns if c not in ["year", "month"]]
    activity[count_cols] = activity[count_cols].fillna(0).astype("int64")
    activity.sort_values(["year", "month"]).to_csv(out / "monthly_harmonization_activity.csv", index=False)

    for sensor, metric in [("MODIS", "modis_detection_count"), ("VIIRS", "viirs_detection_count")]:
        write_calendar(activity.rename(columns={metric: "value"}), "value", out / f"calendar_{sensor.lower()}_detections.csv")
    for metric in ["modis_only_count", "viirs_only_count", "candidate_pair_count", "provisional_group_count"]:
        write_calendar(activity.rename(columns={metric: "value"}), "value", out / f"calendar_{metric}.csv")

    start_end = con.execute(f"""
        SELECT MIN(d)::DATE AS min_date, MAX(d)::DATE AS max_date FROM (
            SELECT CAST(acq_datetime_utc AS DATE) AS d FROM read_parquet('{mp}')
            UNION ALL SELECT CAST(acq_datetime_utc AS DATE) AS d FROM read_parquet('{vp}')
        )
    """).fetchone()
    anomalies = pd.concat([
        compute_anomalies(monthly, "MODIS", start_end[0], start_end[1]),
        compute_anomalies(monthly, "VIIRS", start_end[0], start_end[1]),
    ], ignore_index=True)
    anomalies.to_csv(out / "monthly_historical_anomalies.csv", index=False)

    # A compact machine-readable index of the analysis outputs and definitions.
    manifest = {
        "data_start": str(start_end[0]), "data_end": str(start_end[1]),
        "outputs": [
            "monthly_sensor_activity.csv", "annual_sensor_activity.csv",
            "monthly_harmonization_activity.csv", "calendar_modis_detections.csv",
            "calendar_viirs_detections.csv", "calendar_modis_only_count.csv",
            "calendar_viirs_only_count.csv", "calendar_candidate_pair_count.csv",
            "calendar_provisional_group_count.csv", "monthly_historical_anomalies.csv",
        ],
        "interpretation_notes": [
            "Detection counts are satellite pixel detections, not unique fires.",
            "Candidate pair counts can contain multiple possible cross-sensor relationships.",
            "Unmatched means no candidate was found under the chosen matching parameters; it does not mean false detection.",
            "Provisional groups are MODIS-anchored candidate groups, not confirmed physical fire events.",
            "First and last partial calendar months are excluded from full-month anomaly calculations.",
            "MODIS and VIIRS FRP sums are reported separately; do not add them as unique fire energy."
        ]
    }
    with (out / "analytics_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    con.close()
    print("Analytics reports created in:", out)


if __name__ == "__main__":
    main()
