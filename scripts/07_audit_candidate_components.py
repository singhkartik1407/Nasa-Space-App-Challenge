"""Audit connected components and high-degree neighborhoods in FireScope candidate edges.

This is a diagnostic only. Connected components are NOT physical-fire events.
It reads the March candidate-pair Parquet and writes CSV/JSON reports only.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


EARTH_KM_PER_DEG = 111.32


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        parent = self.parent
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.rank[root_left] < self.rank[root_right]:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        if self.rank[root_left] == self.rank[root_right]:
            self.rank[root_left] += 1


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def bbox_dimensions_km(min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> tuple[float, float, float]:
    """Approximate bounding-box height, width and diagonal; not exact point diameter."""
    mid_lat_rad = math.radians((min_lat + max_lat) / 2.0)
    height_km = max(0.0, max_lat - min_lat) * EARTH_KM_PER_DEG
    width_km = max(0.0, max_lon - min_lon) * EARTH_KM_PER_DEG * abs(math.cos(mid_lat_rad))
    return height_km, width_km, math.hypot(height_km, width_km)


def distribution(values: pd.Series) -> dict[str, float | None]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return {"min": None, "median": None, "p90": None, "p95": None, "p99": None, "max": None}
    return {
        "min": float(clean.min()),
        "median": float(clean.median()),
        "p90": float(clean.quantile(0.90)),
        "p95": float(clean.quantile(0.95)),
        "p99": float(clean.quantile(0.99)),
        "max": float(clean.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit connected components and high-degree candidate neighborhoods.")
    parser.add_argument("--root", default=".", help="FireScope project root")
    parser.add_argument(
        "--input",
        default=r"data\harmonized\matching_20120301_20120331\candidate_pairs_superset.parquet",
        help="Candidate-pair superset Parquet path, relative to root unless absolute",
    )
    parser.add_argument(
        "--output",
        default=r"reports\audit\matching_20120301_20120331\candidate_component_audit",
        help="Output directory, relative to root unless absolute",
    )
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--top-n", type=int, default=30, help="Top high-degree detections to profile per sensor")
    args = parser.parse_args()

    if args.threads < 1 or args.top_n < 1:
        parser.error("threads and top-n must be positive")

    root = Path(args.root).resolve()
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = root / input_path
    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Candidate Parquet not found: {input_path}")

    required = [
        "modis_row_id", "viirs_row_id", "distance_km", "time_diff_minutes",
        "modis_datetime_utc", "viirs_datetime_utc", "modis_latitude", "modis_longitude",
        "viirs_latitude", "viirs_longitude", "modis_satellite", "viirs_satellite",
    ]

    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute(f"SET threads = {int(args.threads)}")
    parquet = sql_path(input_path)
    available = {row[0] for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet}')").fetchall()}
    missing = [col for col in required if col not in available]
    if missing:
        raise ValueError(f"Candidate Parquet is missing required columns: {missing}")

    query = f"""
        SELECT {', '.join(required)}
        FROM read_parquet('{parquet}')
    """
    edges = con.execute(query).fetchdf()
    con.close()

    if edges.empty:
        raise ValueError("Candidate Parquet contains no rows")
    if edges["modis_row_id"].isna().any() or edges["viirs_row_id"].isna().any():
        raise ValueError("Candidate Parquet contains missing endpoint IDs")

    edges["distance_km"] = pd.to_numeric(edges["distance_km"], errors="coerce")
    edges["time_diff_minutes"] = pd.to_numeric(edges["time_diff_minutes"], errors="coerce")
    edges["_modis_ts"] = pd.to_datetime(edges["modis_datetime_utc"], utc=True, errors="coerce")
    edges["_viirs_ts"] = pd.to_datetime(edges["viirs_datetime_utc"], utc=True, errors="coerce")
    if edges["_modis_ts"].isna().any() or edges["_viirs_ts"].isna().any():
        raise ValueError("Candidate Parquet contains unparseable endpoint timestamps")
    duplicate_edges = int(edges.duplicated(["modis_row_id", "viirs_row_id"]).sum())

    # Create one stable node record per original sensor detection.
    modis_nodes = edges[["modis_row_id", "modis_latitude", "modis_longitude", "_modis_ts", "modis_satellite"]].drop_duplicates("modis_row_id").copy()
    viirs_nodes = edges[["viirs_row_id", "viirs_latitude", "viirs_longitude", "_viirs_ts", "viirs_satellite"]].drop_duplicates("viirs_row_id").copy()
    modis_nodes.columns = ["row_id", "latitude", "longitude", "timestamp_utc", "satellite"]
    viirs_nodes.columns = ["row_id", "latitude", "longitude", "timestamp_utc", "satellite"]
    modis_nodes["sensor"] = "MODIS"
    viirs_nodes["sensor"] = "VIIRS"

    modis_ids = modis_nodes["row_id"].astype(str).tolist()
    viirs_ids = viirs_nodes["row_id"].astype(str).tolist()
    modis_index = {row_id: idx for idx, row_id in enumerate(modis_ids)}
    viirs_offset = len(modis_ids)
    viirs_index = {row_id: viirs_offset + idx for idx, row_id in enumerate(viirs_ids)}

    uf = UnionFind(len(modis_ids) + len(viirs_ids))
    for modis_id, viirs_id in edges[["modis_row_id", "viirs_row_id"]].itertuples(index=False, name=None):
        uf.union(modis_index[str(modis_id)], viirs_index[str(viirs_id)])

    modis_nodes["component_root"] = [uf.find(idx) for idx in range(len(modis_ids))]
    viirs_nodes["component_root"] = [uf.find(viirs_offset + idx) for idx in range(len(viirs_ids))]
    nodes = pd.concat([modis_nodes, viirs_nodes], ignore_index=True)

    # Each edge belongs to the component containing its MODIS endpoint.
    root_by_modis_id = dict(zip(modis_nodes["row_id"].astype(str), modis_nodes["component_root"].astype(int)))
    edges["component_root"] = edges["modis_row_id"].astype(str).map(root_by_modis_id).astype("int64")
    edge_counts = edges.groupby("component_root").size().rename("candidate_edge_count")

    components = (
        nodes.groupby("component_root", sort=False)
        .agg(
            node_count=("row_id", "size"),
            modis_detection_count=("sensor", lambda s: int((s == "MODIS").sum())),
            viirs_detection_count=("sensor", lambda s: int((s == "VIIRS").sum())),
            min_latitude=("latitude", "min"),
            max_latitude=("latitude", "max"),
            min_longitude=("longitude", "min"),
            max_longitude=("longitude", "max"),
            first_timestamp_utc=("timestamp_utc", "min"),
            last_timestamp_utc=("timestamp_utc", "max"),
            distinct_satellites=("satellite", "nunique"),
        )
        .join(edge_counts, how="left")
        .fillna({"candidate_edge_count": 0})
        .reset_index()
    )

    bbox_values = components.apply(
        lambda r: bbox_dimensions_km(r.min_latitude, r.max_latitude, r.min_longitude, r.max_longitude), axis=1
    )
    components[["bbox_height_approx_km", "bbox_width_approx_km", "bbox_diagonal_approx_km"]] = pd.DataFrame(
        bbox_values.tolist(), index=components.index
    )
    components["time_span_hours"] = (
        components["last_timestamp_utc"] - components["first_timestamp_utc"]
    ).dt.total_seconds() / 3600.0

    def component_type(row: pd.Series) -> str:
        m_count = int(row["modis_detection_count"])
        v_count = int(row["viirs_detection_count"])
        if m_count == 1 and v_count == 1:
            return "one_to_one_component"
        if m_count == 1:
            return "one_modis_to_many_viirs_component"
        if v_count == 1:
            return "many_modis_to_one_viirs_component"
        return "many_to_many_component"

    components["component_type"] = components.apply(component_type, axis=1)
    components = components.sort_values(
        ["candidate_edge_count", "bbox_diagonal_approx_km", "time_span_hours"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    components.insert(0, "component_rank_by_edges", np.arange(1, len(components) + 1))
    components.insert(1, "component_id", [f"CC_{i:08d}" for i in components["component_root"]])
    root_to_component_id = dict(zip(components["component_root"].astype(int), components["component_id"].astype(str)))
    nodes["component_id"] = nodes["component_root"].astype(int).map(root_to_component_id)
    nodes[["component_id", "sensor", "row_id", "latitude", "longitude", "timestamp_utc", "satellite"]].to_csv(
        output_dir / "candidate_component_node_membership.csv", index=False
    )

    # Degree per endpoint and high-degree counterpart neighborhood summaries.
    modis_degree = edges.groupby("modis_row_id")["viirs_row_id"].nunique().rename("candidate_degree")
    viirs_degree = edges.groupby("viirs_row_id")["modis_row_id"].nunique().rename("candidate_degree")
    high_rows: list[dict[str, Any]] = []
    high_edge_frames: list[pd.DataFrame] = []

    for sensor, degree_series in (("MODIS", modis_degree), ("VIIRS", viirs_degree)):
        top = degree_series.sort_values(ascending=False).head(args.top_n)
        for row_id, degree in top.items():
            if sensor == "MODIS":
                subset = edges.loc[edges["modis_row_id"].astype(str) == str(row_id)].copy()
                counterpart_lat = subset["viirs_latitude"]
                counterpart_lon = subset["viirs_longitude"]
                counterpart_ts = subset["_viirs_ts"]
                component_root = root_by_modis_id[str(row_id)]
                counterpart_id = "viirs_row_id"
            else:
                subset = edges.loc[edges["viirs_row_id"].astype(str) == str(row_id)].copy()
                counterpart_lat = subset["modis_latitude"]
                counterpart_lon = subset["modis_longitude"]
                counterpart_ts = subset["_modis_ts"]
                any_modis_id = str(subset.iloc[0]["modis_row_id"])
                component_root = root_by_modis_id[any_modis_id]
                counterpart_id = "modis_row_id"

            height, width, diagonal = bbox_dimensions_km(
                float(counterpart_lat.min()), float(counterpart_lat.max()),
                float(counterpart_lon.min()), float(counterpart_lon.max()),
            )
            high_rows.append({
                "sensor": sensor,
                "row_id": str(row_id),
                "candidate_degree": int(degree),
                "component_id": f"CC_{component_root:08d}",
                "counterpart_detection_count": int(subset[counterpart_id].nunique()),
                "counterpart_bbox_height_approx_km": height,
                "counterpart_bbox_width_approx_km": width,
                "counterpart_bbox_diagonal_approx_km": diagonal,
                "counterpart_first_timestamp_utc": counterpart_ts.min().isoformat(),
                "counterpart_last_timestamp_utc": counterpart_ts.max().isoformat(),
                "counterpart_time_span_hours": float((counterpart_ts.max() - counterpart_ts.min()).total_seconds() / 3600.0),
                "min_edge_distance_km": float(subset["distance_km"].min()),
                "median_edge_distance_km": float(subset["distance_km"].median()),
                "max_edge_distance_km": float(subset["distance_km"].max()),
                "min_time_difference_minutes": float(subset["time_diff_minutes"].min()),
                "median_time_difference_minutes": float(subset["time_diff_minutes"].median()),
                "max_time_difference_minutes": float(subset["time_diff_minutes"].max()),
            })
            subset.insert(0, "anchor_sensor", sensor)
            subset.insert(1, "anchor_row_id", str(row_id))
            subset.insert(2, "anchor_candidate_degree", int(degree))
            high_edge_frames.append(subset)

    high_summary = pd.DataFrame(high_rows).sort_values(
        ["sensor", "candidate_degree"], ascending=[True, False]
    )
    high_edges = pd.concat(high_edge_frames, ignore_index=True) if high_edge_frames else pd.DataFrame()
    if not high_edges.empty:
        keep = [
            "anchor_sensor", "anchor_row_id", "anchor_candidate_degree",
            "modis_row_id", "viirs_row_id", "distance_km", "time_diff_minutes",
            "modis_datetime_utc", "viirs_datetime_utc",
            "modis_latitude", "modis_longitude", "viirs_latitude", "viirs_longitude",
            "modis_satellite", "viirs_satellite", "modis_frp_mw", "viirs_frp_mw",
            "modis_daynight", "viirs_daynight", "modis_version", "viirs_version",
            "component_root",
        ]
        keep = [c for c in keep if c in high_edges.columns]
        high_edges[keep].to_csv(output_dir / "high_degree_candidate_edges.csv", index=False)

    components.to_csv(output_dir / "candidate_connected_components.csv", index=False)
    high_summary.to_csv(output_dir / "high_degree_neighborhood_summary.csv", index=False)

    component_type_counts = (
        components.groupby("component_type").size().to_dict()
    )
    summary: dict[str, Any] = {
        "analysis": "Bipartite candidate-graph connected-component and high-degree neighborhood audit",
        "warning": (
            "Connected components are graph-connectivity diagnostics only, not physical-fire events. "
            "Bounding-box diagonal is an approximate spatial extent, not an exact maximum pairwise distance. "
            "A component may span multiple fires through transitive candidate links."
        ),
        "input_file": str(input_path),
        "candidate_edge_count": int(len(edges)),
        "duplicate_edge_rows": duplicate_edges,
        "unique_modis_nodes": int(len(modis_nodes)),
        "unique_viirs_nodes": int(len(viirs_nodes)),
        "connected_component_count": int(len(components)),
        "component_type_counts": {str(k): int(v) for k, v in component_type_counts.items()},
        "largest_component_by_edges": {
            "component_id": str(components.iloc[0]["component_id"]),
            "candidate_edges": int(components.iloc[0]["candidate_edge_count"]),
            "modis_detections": int(components.iloc[0]["modis_detection_count"]),
            "viirs_detections": int(components.iloc[0]["viirs_detection_count"]),
            "bbox_diagonal_approx_km": float(components.iloc[0]["bbox_diagonal_approx_km"]),
            "time_span_hours": float(components.iloc[0]["time_span_hours"]),
        },
        "component_bbox_diagonal_distribution_km": distribution(components["bbox_diagonal_approx_km"]),
        "component_time_span_distribution_hours": distribution(components["time_span_hours"]),
        "components_over_extent_bands": {
            str(km): int((components["bbox_diagonal_approx_km"] > km).sum())
            for km in (1, 5, 10, 25, 50, 100)
        },
        "components_over_time_span_bands": {
            str(hours): int((components["time_span_hours"] > hours).sum())
            for hours in (1, 3, 6, 12, 24, 48, 72)
        },
        "high_degree_profiled_per_sensor": int(args.top_n),
        "output_files": [
            "candidate_connected_components.csv",
            "candidate_component_node_membership.csv",
            "high_degree_neighborhood_summary.csv",
            "high_degree_candidate_edges.csv",
            "candidate_component_audit_summary.json",
        ],
    }
    with (output_dir / "candidate_component_audit_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)

    print("Candidate component audit completed.")
    print(f"Edges: {len(edges):,}")
    print(f"MODIS nodes: {len(modis_nodes):,} | VIIRS nodes: {len(viirs_nodes):,}")
    print(f"Connected components: {len(components):,}")
    print(f"Largest component: {int(components.iloc[0]['candidate_edge_count']):,} edges | "
          f"{int(components.iloc[0]['modis_detection_count']):,} MODIS | "
          f"{int(components.iloc[0]['viirs_detection_count']):,} VIIRS | "
          f"{components.iloc[0]['bbox_diagonal_approx_km']:.2f} km bbox diagonal | "
          f"{components.iloc[0]['time_span_hours']:.2f} hours")
    print(f"Reports: {output_dir}")


if __name__ == "__main__":
    main()
