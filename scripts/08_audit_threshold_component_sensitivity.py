"""Compare bipartite candidate-graph components across FireScope thresholds A-E.

This is a read-only diagnostic. Connected components are graph-connectivity
artifacts, not confirmed physical-fire events. It reuses the March candidate
superset and filters edges; it does not rerun spatial candidate generation.
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
EXPERIMENTS = [
    ("A_1h_0km", 1.0, 0.0),
    ("B_3h_0km", 3.0, 0.0),
    ("C_3h_025km", 3.0, 0.25),
    ("D_3h_050km", 3.0, 0.50),
    ("E_6h_050km", 6.0, 0.50),
]


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        a, b = self.find(left), self.find(right)
        if a == b:
            return
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.parent[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def bbox_dimensions_km(min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> tuple[float, float, float]:
    """Approximate bounding-box height, width and diagonal (not point diameter)."""
    mid_lat_rad = math.radians((min_lat + max_lat) / 2.0)
    height = max(0.0, max_lat - min_lat) * EARTH_KM_PER_DEG
    width = max(0.0, max_lon - min_lon) * EARTH_KM_PER_DEG * abs(math.cos(mid_lat_rad))
    return height, width, math.hypot(height, width)


def quantile(values: pd.Series, q: float) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return float(clean.quantile(q)) if not clean.empty else None


def build_components(edges: pd.DataFrame, experiment: str) -> pd.DataFrame:
    """Build connected components for one already-filtered edge table."""
    if edges.empty:
        return pd.DataFrame()

    modis_nodes = (
        edges[["modis_row_id", "modis_latitude", "modis_longitude", "_modis_ts", "modis_satellite"]]
        .drop_duplicates("modis_row_id")
        .copy()
    )
    viirs_nodes = (
        edges[["viirs_row_id", "viirs_latitude", "viirs_longitude", "_viirs_ts", "viirs_satellite"]]
        .drop_duplicates("viirs_row_id")
        .copy()
    )

    modis_ids = modis_nodes["modis_row_id"].astype(str).tolist()
    viirs_ids = viirs_nodes["viirs_row_id"].astype(str).tolist()
    modis_index = {value: i for i, value in enumerate(modis_ids)}
    viirs_offset = len(modis_ids)
    viirs_index = {value: viirs_offset + i for i, value in enumerate(viirs_ids)}

    uf = UnionFind(len(modis_ids) + len(viirs_ids))
    for mid, vid in edges[["modis_row_id", "viirs_row_id"]].itertuples(index=False, name=None):
        uf.union(modis_index[str(mid)], viirs_index[str(vid)])

    modis_nodes = modis_nodes.rename(columns={
        "modis_row_id": "row_id", "modis_latitude": "latitude", "modis_longitude": "longitude",
        "_modis_ts": "timestamp_utc", "modis_satellite": "satellite",
    })
    viirs_nodes = viirs_nodes.rename(columns={
        "viirs_row_id": "row_id", "viirs_latitude": "latitude", "viirs_longitude": "longitude",
        "_viirs_ts": "timestamp_utc", "viirs_satellite": "satellite",
    })
    modis_nodes["sensor"] = "MODIS"
    viirs_nodes["sensor"] = "VIIRS"
    modis_nodes["component_root"] = [uf.find(i) for i in range(len(modis_ids))]
    viirs_nodes["component_root"] = [uf.find(viirs_offset + i) for i in range(len(viirs_ids))]
    nodes = pd.concat([modis_nodes, viirs_nodes], ignore_index=True)

    root_by_modis = dict(zip(modis_nodes["row_id"].astype(str), modis_nodes["component_root"].astype(int)))
    edge_roots = edges["modis_row_id"].astype(str).map(root_by_modis)
    edge_counts = edge_roots.value_counts().rename("candidate_edge_count")

    components = (
        nodes.groupby("component_root", sort=False)
        .agg(
            node_count=("row_id", "size"),
            modis_detection_count=("sensor", lambda s: int((s == "MODIS").sum())),
            viirs_detection_count=("sensor", lambda s: int((s == "VIIRS").sum())),
            min_latitude=("latitude", "min"), max_latitude=("latitude", "max"),
            min_longitude=("longitude", "min"), max_longitude=("longitude", "max"),
            first_timestamp_utc=("timestamp_utc", "min"), last_timestamp_utc=("timestamp_utc", "max"),
            distinct_satellites=("satellite", "nunique"),
        )
        .join(edge_counts, how="left")
        .reset_index()
    )

    bbox = components.apply(
        lambda r: bbox_dimensions_km(r.min_latitude, r.max_latitude, r.min_longitude, r.max_longitude), axis=1
    )
    components[["bbox_height_approx_km", "bbox_width_approx_km", "bbox_diagonal_approx_km"]] = pd.DataFrame(
        bbox.tolist(), index=components.index
    )
    components["time_span_hours"] = (
        components["last_timestamp_utc"] - components["first_timestamp_utc"]
    ).dt.total_seconds() / 3600.0

    def classify(row: pd.Series) -> str:
        m, v = int(row["modis_detection_count"]), int(row["viirs_detection_count"])
        if m == 1 and v == 1:
            return "one_to_one_component"
        if m == 1:
            return "one_modis_to_many_viirs_component"
        if v == 1:
            return "many_modis_to_one_viirs_component"
        return "many_to_many_component"

    components["component_type"] = components.apply(classify, axis=1)
    components = components.sort_values(
        ["candidate_edge_count", "bbox_diagonal_approx_km", "time_span_hours"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    components.insert(0, "component_rank_by_edges", np.arange(1, len(components) + 1))
    components.insert(1, "experiment", experiment)
    components.insert(2, "component_id", [f"{experiment}_CC_{int(x):08d}" for x in components["component_root"]])
    return components


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare connected-component structure under threshold experiments A-E.")
    parser.add_argument("--root", default=".", help="FireScope project root")
    parser.add_argument(
        "--input",
        default=r"data\harmonized\matching_20120301_20120331\candidate_pairs_superset.parquet",
        help="Candidate superset Parquet path, relative to root unless absolute",
    )
    parser.add_argument(
        "--threshold-report",
        default=r"reports\audit\matching_20120301_20120331\threshold_sensitivity.csv",
        help="Existing threshold_sensitivity.csv used for edge-count cross-check",
    )
    parser.add_argument(
        "--output",
        default=r"reports\audit\matching_20120301_20120331\threshold_component_sensitivity",
        help="Output directory, relative to root unless absolute",
    )
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--top-n", type=int, default=50, help="Largest components to export per threshold")
    args = parser.parse_args()
    if args.threads < 1 or args.top_n < 1:
        parser.error("threads and top-n must be positive")

    root = Path(args.root).resolve()
    def resolve(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    input_path = resolve(args.input)
    threshold_path = resolve(args.threshold_report)
    output_dir = resolve(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not input_path.exists():
        raise FileNotFoundError(f"Candidate superset not found: {input_path}")
    if not threshold_path.exists():
        raise FileNotFoundError(f"Threshold report not found: {threshold_path}")

    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute(f"SET threads = {int(args.threads)}")
    parquet = sql_path(input_path)
    required = [
        "modis_row_id", "viirs_row_id", "distance_km", "time_diff_minutes", "footprint_radius_sum_km",
        "modis_datetime_utc", "viirs_datetime_utc", "modis_latitude", "modis_longitude",
        "viirs_latitude", "viirs_longitude", "modis_satellite", "viirs_satellite",
    ]
    available = {row[0] for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet}')").fetchall()}
    missing = [column for column in required if column not in available]
    if missing:
        raise ValueError(f"Candidate superset is missing columns: {missing}")
    edges = con.execute(f"SELECT {', '.join(required)} FROM read_parquet('{parquet}')").fetchdf()
    con.close()
    if edges.empty:
        raise ValueError("Candidate superset contains no rows")
    if edges.duplicated(["modis_row_id", "viirs_row_id"]).any():
        raise ValueError("Candidate superset contains duplicate MODIS-VIIRS edge pairs")

    for column in ("distance_km", "time_diff_minutes", "footprint_radius_sum_km"):
        edges[column] = pd.to_numeric(edges[column], errors="coerce")
    if edges[["distance_km", "time_diff_minutes", "footprint_radius_sum_km"]].isna().any().any():
        raise ValueError("Candidate superset contains null or invalid spatial/temporal metrics")
    edges["_modis_ts"] = pd.to_datetime(edges["modis_datetime_utc"], utc=True, errors="coerce")
    edges["_viirs_ts"] = pd.to_datetime(edges["viirs_datetime_utc"], utc=True, errors="coerce")
    if edges[["_modis_ts", "_viirs_ts"]].isna().any().any():
        raise ValueError("Candidate superset contains unparseable timestamps")

    original_counts = pd.read_csv(threshold_path).set_index("experiment")["candidate_pair_count"].to_dict()
    sensitivity_rows: list[dict[str, Any]] = []
    top_frames: list[pd.DataFrame] = []
    distribution_rows: list[dict[str, Any]] = []
    component_types = [
        "one_to_one_component", "one_modis_to_many_viirs_component",
        "many_modis_to_one_viirs_component", "many_to_many_component",
    ]

    for experiment, time_hours, buffer_km in EXPERIMENTS:
        mask = (
            (edges["time_diff_minutes"] <= time_hours * 60.0)
            & (edges["distance_km"] <= edges["footprint_radius_sum_km"] + buffer_km)
        )
        selected = edges.loc[mask].copy().reset_index(drop=True)
        expected = int(round(float(original_counts[experiment]))) if experiment in original_counts else None
        if expected is not None and len(selected) != expected:
            raise RuntimeError(
                f"{experiment} edge filter produced {len(selected):,} pairs, "
                f"but threshold_sensitivity.csv reports {expected:,}. Stop and reconcile thresholds."
            )

        components = build_components(selected, experiment)
        if components.empty:
            raise RuntimeError(f"{experiment} produced no components")
        top_frames.append(components.head(args.top_n).copy())
        type_counts = components["component_type"].value_counts().to_dict()
        ext = components["bbox_diagonal_approx_km"]
        spans = components["time_span_hours"]
        largest = components.iloc[0]

        sensitivity_rows.append({
            "experiment": experiment,
            "time_hours": time_hours,
            "additional_buffer_km": buffer_km,
            "candidate_pair_count": int(len(selected)),
            "modis_with_candidates": int(selected["modis_row_id"].nunique()),
            "viirs_with_candidates": int(selected["viirs_row_id"].nunique()),
            "connected_component_count": int(len(components)),
            "one_to_one_components": int(type_counts.get(component_types[0], 0)),
            "one_modis_to_many_viirs_components": int(type_counts.get(component_types[1], 0)),
            "many_modis_to_one_viirs_components": int(type_counts.get(component_types[2], 0)),
            "many_to_many_components": int(type_counts.get(component_types[3], 0)),
            "median_component_edges": quantile(components["candidate_edge_count"], 0.50),
            "p95_component_edges": quantile(components["candidate_edge_count"], 0.95),
            "max_component_edges": int(components["candidate_edge_count"].max()),
            "median_bbox_diagonal_km": quantile(ext, 0.50),
            "p95_bbox_diagonal_km": quantile(ext, 0.95),
            "p99_bbox_diagonal_km": quantile(ext, 0.99),
            "max_bbox_diagonal_km": float(ext.max()),
            "components_over_5km": int((ext > 5).sum()),
            "components_over_10km": int((ext > 10).sum()),
            "components_over_20km": int((ext > 20).sum()),
            "median_time_span_hours": quantile(spans, 0.50),
            "p95_time_span_hours": quantile(spans, 0.95),
            "p99_time_span_hours": quantile(spans, 0.99),
            "max_time_span_hours": float(spans.max()),
            "components_over_3h": int((spans > 3).sum()),
            "components_over_4h": int((spans > 4).sum()),
            "largest_component_id": str(largest["component_id"]),
            "largest_component_edges": int(largest["candidate_edge_count"]),
            "largest_component_modis": int(largest["modis_detection_count"]),
            "largest_component_viirs": int(largest["viirs_detection_count"]),
            "largest_component_bbox_diagonal_km": float(largest["bbox_diagonal_approx_km"]),
            "largest_component_time_span_hours": float(largest["time_span_hours"]),
        })

        for band, lower, upper in [
            ("0_to_1km", 0, 1), ("1_to_2km", 1, 2), ("2_to_5km", 2, 5),
            ("5_to_10km", 5, 10), ("10_to_20km", 10, 20), ("over_20km", 20, math.inf),
        ]:
            distribution_rows.append({
                "experiment": experiment,
                "extent_band": band,
                "component_count": int(((ext > lower) & (ext <= upper)).sum()) if lower else int(((ext >= lower) & (ext <= upper)).sum()),
            })

    sensitivity = pd.DataFrame(sensitivity_rows)
    sensitivity.to_csv(output_dir / "threshold_component_sensitivity.csv", index=False)
    pd.concat(top_frames, ignore_index=True).to_csv(output_dir / "largest_components_by_threshold.csv", index=False)
    pd.DataFrame(distribution_rows).to_csv(output_dir / "component_extent_bands_by_threshold.csv", index=False)

    summary = {
        "analysis": "Connected-component sensitivity across candidate threshold experiments A-E",
        "warning": "Components are graph connectivity only, not physical-fire events. Transitive chains can join distant detections even when every edge satisfies its own pairwise rule.",
        "input_candidate_superset": str(input_path),
        "threshold_reference_report": str(threshold_path),
        "input_candidate_rows": int(len(edges)),
        "duplicate_edge_pairs": 0,
        "bbox_method": "111.32 km per latitude degree; longitude scaled by cosine of component mid-latitude; diagonal is approximate.",
        "experiments": sensitivity_rows,
        "outputs": [
            "threshold_component_sensitivity.csv",
            "largest_components_by_threshold.csv",
            "component_extent_bands_by_threshold.csv",
        ],
    }
    with (output_dir / "threshold_component_sensitivity_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)

    readme = (
        "FireScope threshold component sensitivity\n\n"
        "This report rebuilds graph connected components after filtering the existing candidate superset with A-E rules. "
        "It does not regenerate candidate pairs. Components are not physical-fire identities. A connected component can be "
        "geographically broad because of transitive chains of individually valid candidate edges. Bounding-box diagonals "
        "are approximate spatial extents, not exact maximum pairwise distances.\n"
    )
    (output_dir / "README.txt").write_text(readme, encoding="utf-8")

    print("Threshold component sensitivity completed.")
    print(sensitivity[[
        "experiment", "candidate_pair_count", "connected_component_count", "max_component_edges",
        "max_bbox_diagonal_km", "components_over_10km", "max_time_span_hours",
    ]].to_string(index=False))
    print(f"Outputs: {output_dir}")


if __name__ == "__main__":
    main()
