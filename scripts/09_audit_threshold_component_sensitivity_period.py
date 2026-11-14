#!/usr/bin/env python3
"""Audit connected-component sensitivity for any FireScope matching period.

Reads an existing candidate_pairs_superset.parquet and its threshold_sensitivity.csv,
filters the candidate superset under A-E, rebuilds bipartite connected components,
verifies filtered edge counts against the matcher report, and writes compact reports.

This is a graph-connectivity diagnostic only. Components are NOT physical-fire IDs.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


THRESHOLDS = [
    ("A_1h_0km", 1.0, 0.0),
    ("B_3h_0km", 3.0, 0.0),
    ("C_3h_025km", 3.0, 0.25),
    ("D_3h_050km", 3.0, 0.50),
    ("E_6h_050km", 6.0, 0.50),
]

ALIASES = {
    "modis_id": ["modis_row_id"],
    "viirs_id": ["viirs_row_id"],
    "distance": ["distance_km", "center_distance_km", "centroid_distance_km"],
    "time_diff": ["time_diff_minutes", "abs_time_diff_minutes", "time_difference_minutes"],
    "radius_sum": ["footprint_radius_sum_km", "radius_sum_km", "sum_footprint_radii_km"],
    "modis_lat": ["modis_latitude", "modis_lat", "latitude_modis"],
    "modis_lon": ["modis_longitude", "modis_lon", "longitude_modis", "modis_long"],
    "viirs_lat": ["viirs_latitude", "viirs_lat", "latitude_viirs"],
    "viirs_lon": ["viirs_longitude", "viirs_lon", "longitude_viirs", "viirs_long"],
    "modis_time": ["modis_acq_datetime_utc", "modis_acq_time_utc", "modis_datetime_utc", "modis_timestamp_utc", "modis_acq_datetime", "modis_timestamp"],
    "viirs_time": ["viirs_acq_datetime_utc", "viirs_acq_time_utc", "viirs_datetime_utc", "viirs_timestamp_utc", "viirs_acq_datetime", "viirs_timestamp"],
    "modis_sat": ["modis_satellite", "modis_platform", "modis_satellite_name"],
    "viirs_sat": ["viirs_satellite", "viirs_platform", "viirs_satellite_name"],
}


def resolve_column(columns: list[str], key: str, required: bool = True) -> str | None:
    lookup = {str(c).strip().lower(): str(c) for c in columns}
    for alias in ALIASES[key]:
        if alias.lower() in lookup:
            return lookup[alias.lower()]
    if required:
        raise ValueError(
            f"Could not identify required column for '{key}'. Tried {ALIASES[key]}.\n"
            f"Available columns: {columns}"
        )
    return None


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[tuple[str, str], tuple[str, str]] = {}
        self.rank: dict[tuple[str, str], int] = {}

    def add(self, x: tuple[str, str]) -> None:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0

    def find(self, x: tuple[str, str]) -> tuple[str, str]:
        p = self.parent[x]
        if p != x:
            self.parent[x] = self.find(p)
        return self.parent[x]

    def union(self, a: tuple[str, str], b: tuple[str, str]) -> None:
        self.add(a)
        self.add(b)
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=float), q))


def component_type(n_modis: int, n_viirs: int) -> str:
    if n_modis == 1 and n_viirs == 1:
        return "one_to_one_component"
    if n_modis == 1 and n_viirs > 1:
        return "one_modis_to_many_viirs_component"
    if n_modis > 1 and n_viirs == 1:
        return "many_modis_to_one_viirs_component"
    return "many_to_many_component"


def extent_band(diagonal: float) -> str:
    if diagonal < 1:
        return "0_to_1km"
    if diagonal < 2:
        return "1_to_2km"
    if diagonal < 5:
        return "2_to_5km"
    if diagonal < 10:
        return "5_to_10km"
    if diagonal < 20:
        return "10_to_20km"
    return "over_20km"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="FireScope project root (default: current directory)")
    parser.add_argument("--start-date", required=True, help="Period start YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="Period end YYYY-MM-DD")
    parser.add_argument("--top-n", type=int, default=50, help="Largest components to save per threshold")
    parser.add_argument("--parquet", default=None, help="Optional explicit candidate superset Parquet path")
    parser.add_argument("--threshold-report", default=None, help="Optional explicit threshold_sensitivity.csv path")
    args = parser.parse_args()

    start = pd.Timestamp(args.start_date).strftime("%Y%m%d")
    end = pd.Timestamp(args.end_date).strftime("%Y%m%d")
    period = f"{start}_{end}"
    root = Path(args.root).resolve()
    parquet_path = Path(args.parquet).resolve() if args.parquet else root / "data" / "harmonized" / f"matching_{period}" / "candidate_pairs_superset.parquet"
    threshold_path = Path(args.threshold_report).resolve() if args.threshold_report else root / "reports" / "audit" / f"matching_{period}" / "threshold_sensitivity.csv"
    out_dir = root / "reports" / "audit" / f"matching_{period}" / "threshold_component_sensitivity"

    if args.top_n < 1:
        raise ValueError("--top-n must be >= 1")
    if not parquet_path.exists():
        raise FileNotFoundError(f"Candidate superset not found: {parquet_path}")
    if not threshold_path.exists():
        raise FileNotFoundError(f"Threshold reference report not found: {threshold_path}")

    print(f"Reading candidate superset: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    if df.empty:
        raise ValueError("Candidate superset is empty; there is nothing to audit")

    cols = list(df.columns)
    c = {key: resolve_column(cols, key, required=key not in {"modis_sat", "viirs_sat"}) for key in ALIASES}
    # Coordinates and timestamps are required for extent/time diagnostics.
    # Satellite labels are optional because some exports may omit them.
    selected = [c[k] for k in ["modis_id", "viirs_id", "distance", "time_diff", "radius_sum",
                                "modis_lat", "modis_lon", "viirs_lat", "viirs_lon", "modis_time", "viirs_time"]]
    optional = [c["modis_sat"], c["viirs_sat"]]
    use_cols = list(dict.fromkeys([x for x in selected + optional if x is not None]))
    df = df[use_cols].copy()

    # Normalize types and validate the candidate superset before threshold filtering.
    for key in ["distance", "time_diff", "radius_sum", "modis_lat", "modis_lon", "viirs_lat", "viirs_lon"]:
        df[c[key]] = pd.to_numeric(df[c[key]], errors="coerce")
    df[c["modis_time"]] = pd.to_datetime(df[c["modis_time"]], utc=True, errors="coerce")
    df[c["viirs_time"]] = pd.to_datetime(df[c["viirs_time"]], utc=True, errors="coerce")
    if df[[c["modis_time"], c["viirs_time"]]].isna().any().any():
        raise ValueError("Missing or unparseable MODIS/VIIRS UTC timestamps in candidate superset")
    if df[[c["modis_lat"], c["modis_lon"], c["viirs_lat"], c["viirs_lon"]]].isna().any().any():
        raise ValueError("Missing or non-numeric coordinates in candidate superset")
    if not df[c["modis_lat"]].between(-90, 90).all() or not df[c["viirs_lat"]].between(-90, 90).all():
        raise ValueError("Latitude outside [-90, 90] detected")
    if not df[c["modis_lon"]].between(-180, 180).all() or not df[c["viirs_lon"]].between(-180, 180).all():
        raise ValueError("Longitude outside [-180, 180] detected")
    if df[[c["modis_id"], c["viirs_id"]]].isna().any().any():
        raise ValueError("Missing MODIS or VIIRS row IDs in candidate superset")
    if df[[c["distance"], c["time_diff"], c["radius_sum"]]].isna().any().any():
        raise ValueError("Missing/non-numeric distance, time difference, or footprint-radius sum")
    if (df[c["distance"]] < 0).any() or (df[c["time_diff"]] < 0).any() or (df[c["radius_sum"]] < 0).any():
        raise ValueError("Negative distance, time difference, or footprint-radius sum detected")

    df[c["modis_id"]] = df[c["modis_id"]].astype(str)
    df[c["viirs_id"]] = df[c["viirs_id"]].astype(str)
    edge_dupes = int(df.duplicated([c["modis_id"], c["viirs_id"]]).sum())
    if edge_dupes:
        raise ValueError(f"Candidate superset contains {edge_dupes} duplicate MODIS-VIIRS edges")

    ref = pd.read_csv(threshold_path)
    if not {"experiment", "candidate_pair_count"}.issubset(set(ref.columns)):
        raise ValueError("threshold_sensitivity.csv must contain experiment and candidate_pair_count columns")
    expected = {str(r.experiment): int(r.candidate_pair_count) for r in ref.itertuples(index=False)}

    # Cache numeric arrays for fast threshold masks and edge processing.
    dist = df[c["distance"]].to_numpy(dtype=float)
    dt = df[c["time_diff"]].to_numpy(dtype=float)
    radii = df[c["radius_sum"]].to_numpy(dtype=float)
    mid = df[c["modis_id"]].to_numpy(dtype=str)
    vid = df[c["viirs_id"]].to_numpy(dtype=str)
    mlat = df[c["modis_lat"]].to_numpy(dtype=float)
    mlon = df[c["modis_lon"]].to_numpy(dtype=float)
    vlat = df[c["viirs_lat"]].to_numpy(dtype=float)
    vlon = df[c["viirs_lon"]].to_numpy(dtype=float)
    mt = df[c["modis_time"]].astype("int64").to_numpy(dtype=np.int64) / 1e9
    vt = df[c["viirs_time"]].astype("int64").to_numpy(dtype=np.int64) / 1e9
    msat = df[c["modis_sat"]].fillna("").astype(str).to_numpy() if c["modis_sat"] else np.full(len(df), "")
    vsat = df[c["viirs_sat"]].fillna("").astype(str).to_numpy() if c["viirs_sat"] else np.full(len(df), "")

    summary_rows: list[dict[str, Any]] = []
    largest_rows: list[dict[str, Any]] = []
    extent_rows: list[dict[str, Any]] = []
    summary_json: dict[str, Any] = {
        "analysis": "Connected-component sensitivity across candidate threshold experiments A-E",
        "warning": "Components are graph connectivity only, not physical-fire events. Transitive chains can join distant detections even when every edge satisfies its own pairwise rule.",
        "input_candidate_superset": str(parquet_path),
        "threshold_reference_report": str(threshold_path),
        "input_candidate_rows": int(len(df)),
        "duplicate_edge_pairs": edge_dupes,
        "bbox_method": "111.32 km per latitude degree; longitude scaled by cosine of component mid-latitude; diagonal is approximate.",
        "experiments": [],
    }

    for name, hours, buffer_km in THRESHOLDS:
        mask = (dt <= hours * 60.0) & (dist <= radii + buffer_km)
        idx = np.flatnonzero(mask)
        pair_count = int(len(idx))
        if name not in expected:
            raise ValueError(f"Threshold reference report is missing experiment {name}")
        if pair_count != expected[name]:
            raise ValueError(
                f"Fail-fast count mismatch for {name}: filtered={pair_count:,}, "
                f"threshold_sensitivity.csv={expected[name]:,}. No reports written."
            )
        print(f"{name}: {pair_count:,} candidate edges — rebuilding components")

        uf = UnionFind()
        for i in idx:
            uf.union(("M", mid[i]), ("V", vid[i]))

        nodes_by_root: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
        for node in uf.parent:
            nodes_by_root[uf.find(node)].append(node)

        # Edge counts per final component root.
        edges_by_root: dict[tuple[str, str], int] = defaultdict(int)
        for i in idx:
            edges_by_root[uf.find(("M", mid[i]))] += 1

        # One observation record per graph node; same node should have consistent source metadata.
        node_meta: dict[tuple[str, str], tuple[float, float, float, str]] = {}
        for i in idx:
            node_meta.setdefault(("M", mid[i]), (mlat[i], mlon[i], mt[i], msat[i]))
            node_meta.setdefault(("V", vid[i]), (vlat[i], vlon[i], vt[i], vsat[i]))

        component_records = []
        for root_id, nodes in nodes_by_root.items():
            m_nodes = [x for x in nodes if x[0] == "M"]
            v_nodes = [x for x in nodes if x[0] == "V"]
            points = [node_meta[x] for x in nodes]
            latitudes = [p[0] for p in points if math.isfinite(p[0])]
            longitudes = [p[1] for p in points if math.isfinite(p[1])]
            timestamps = [p[2] for p in points if math.isfinite(p[2])]
            satellites = sorted({p[3] for p in points if p[3]})
            min_lat = min(latitudes) if latitudes else float("nan")
            max_lat = max(latitudes) if latitudes else float("nan")
            min_lon = min(longitudes) if longitudes else float("nan")
            max_lon = max(longitudes) if longitudes else float("nan")
            if latitudes and longitudes:
                mid_lat = (min_lat + max_lat) / 2.0
                height_km = (max_lat - min_lat) * 111.32
                width_km = (max_lon - min_lon) * 111.32 * math.cos(math.radians(mid_lat))
                diagonal = math.hypot(height_km, width_km)
            else:
                height_km = width_km = diagonal = float("nan")
            first_ts = min(timestamps) if timestamps else float("nan")
            last_ts = max(timestamps) if timestamps else float("nan")
            span_h = (last_ts - first_ts) / 3600.0 if timestamps else float("nan")
            n_edges = int(edges_by_root[root_id])
            record = {
                "component_root": root_id[1],
                "node_count": len(nodes),
                "modis_detection_count": len(m_nodes),
                "viirs_detection_count": len(v_nodes),
                "min_latitude": min_lat,
                "max_latitude": max_lat,
                "min_longitude": min_lon,
                "max_longitude": max_lon,
                "first_timestamp_utc": pd.to_datetime(first_ts, unit="s", utc=True).isoformat() if math.isfinite(first_ts) else "",
                "last_timestamp_utc": pd.to_datetime(last_ts, unit="s", utc=True).isoformat() if math.isfinite(last_ts) else "",
                "distinct_satellites": len(satellites),
                "candidate_edge_count": n_edges,
                "bbox_height_approx_km": height_km,
                "bbox_width_approx_km": width_km,
                "bbox_diagonal_approx_km": diagonal,
                "time_span_hours": span_h,
                "component_type": component_type(len(m_nodes), len(v_nodes)),
            }
            component_records.append(record)

        component_records.sort(key=lambda x: (x["candidate_edge_count"], x["node_count"]), reverse=True)
        edge_values = [float(x["candidate_edge_count"]) for x in component_records]
        bbox_values = [float(x["bbox_diagonal_approx_km"]) for x in component_records if math.isfinite(x["bbox_diagonal_approx_km"])]
        span_values = [float(x["time_span_hours"]) for x in component_records if math.isfinite(x["time_span_hours"])]
        type_counts = defaultdict(int)
        for rec in component_records:
            type_counts[rec["component_type"]] += 1
            extent_rows.append({"experiment": name, "extent_band": extent_band(rec["bbox_diagonal_approx_km"]), "_one": 1})
        summary = {
            "experiment": name,
            "time_hours": hours,
            "additional_buffer_km": buffer_km,
            "candidate_pair_count": pair_count,
            "modis_with_candidates": len({mid[i] for i in idx}),
            "viirs_with_candidates": len({vid[i] for i in idx}),
            "connected_component_count": len(component_records),
            "one_to_one_components": int(type_counts["one_to_one_component"]),
            "one_modis_to_many_viirs_components": int(type_counts["one_modis_to_many_viirs_component"]),
            "many_modis_to_one_viirs_components": int(type_counts["many_modis_to_one_viirs_component"]),
            "many_to_many_components": int(type_counts["many_to_many_component"]),
            "median_component_edges": float(np.median(edge_values)) if edge_values else None,
            "p95_component_edges": pct(edge_values, 95),
            "max_component_edges": int(max(edge_values)) if edge_values else 0,
            "median_bbox_diagonal_km": float(np.median(bbox_values)) if bbox_values else None,
            "p95_bbox_diagonal_km": pct(bbox_values, 95),
            "p99_bbox_diagonal_km": pct(bbox_values, 99),
            "max_bbox_diagonal_km": float(max(bbox_values)) if bbox_values else None,
            "components_over_5km": int(sum(x > 5 for x in bbox_values)),
            "components_over_10km": int(sum(x > 10 for x in bbox_values)),
            "components_over_20km": int(sum(x > 20 for x in bbox_values)),
            "median_time_span_hours": float(np.median(span_values)) if span_values else None,
            "p95_time_span_hours": pct(span_values, 95),
            "p99_time_span_hours": pct(span_values, 99),
            "max_time_span_hours": float(max(span_values)) if span_values else None,
            "components_over_3h": int(sum(x > 3 for x in span_values)),
            "components_over_4h": int(sum(x > 4 for x in span_values)),
        }
        if component_records:
            largest = component_records[0]
            summary.update({
                "largest_component_id": f"{name}_CC_{int(largest['component_root']):08d}" if str(largest["component_root"]).isdigit() else f"{name}_CC_{largest['component_root']}",
                "largest_component_edges": largest["candidate_edge_count"],
                "largest_component_modis": largest["modis_detection_count"],
                "largest_component_viirs": largest["viirs_detection_count"],
                "largest_component_bbox_diagonal_km": largest["bbox_diagonal_approx_km"],
                "largest_component_time_span_hours": largest["time_span_hours"],
            })
        else:
            summary.update({
                "largest_component_id": "", "largest_component_edges": 0,
                "largest_component_modis": 0, "largest_component_viirs": 0,
                "largest_component_bbox_diagonal_km": None, "largest_component_time_span_hours": None,
            })
        summary_rows.append(summary)
        summary_json["experiments"].append(summary)

        for rank, rec in enumerate(component_records[:args.top_n], start=1):
            largest_rows.append({
                "component_rank_by_edges": rank,
                "experiment": name,
                "component_id": f"{name}_CC_{int(rec['component_root']):08d}" if str(rec["component_root"]).isdigit() else f"{name}_CC_{rec['component_root']}",
                **rec,
            })

    # Consolidate extent-band counts (include zero-count bands for easy comparisons).
    band_order = ["0_to_1km", "1_to_2km", "2_to_5km", "5_to_10km", "10_to_20km", "over_20km"]
    extent_counts = defaultdict(int)
    for row in extent_rows:
        extent_counts[(row["experiment"], row["extent_band"])] += 1
    for name, _, _ in THRESHOLDS:
        for band in band_order:
            pass
    extent_df = pd.DataFrame([
        {"experiment": name, "extent_band": band, "component_count": extent_counts[(name, band)]}
        for name, _, _ in THRESHOLDS for band in band_order
    ])

    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summary_rows).to_csv(out_dir / "threshold_component_sensitivity.csv", index=False)
    pd.DataFrame(largest_rows).to_csv(out_dir / "largest_components_by_threshold.csv", index=False)
    extent_df.to_csv(out_dir / "component_extent_bands_by_threshold.csv", index=False)
    summary_json["outputs"] = [
        "threshold_component_sensitivity.csv",
        "largest_components_by_threshold.csv",
        "component_extent_bands_by_threshold.csv",
    ]
    (out_dir / "threshold_component_sensitivity_summary.json").write_text(
        json.dumps(summary_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "README.txt").write_text(
        "FireScope threshold component sensitivity\n\n"
        "This report rebuilds graph connected components after filtering the existing candidate superset with A-E rules. "
        "It does not regenerate candidate pairs. Components are not physical-fire identities. Transitive chains can join "
        "geographically distant detections even when each edge individually satisfies its pairwise rule. Bounding-box "
        "diagonals are approximate spatial extents, not exact maximum pairwise distances.\n",
        encoding="utf-8",
    )
    print(f"\nCompleted. Reports written to: {out_dir}")
    print(pd.DataFrame(summary_rows)[[
        "experiment", "candidate_pair_count", "connected_component_count", "one_to_one_components",
        "many_to_many_components", "components_over_5km", "components_over_10km", "max_bbox_diagonal_km",
        "components_over_3h", "max_time_span_hours",
    ]].to_string(index=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
