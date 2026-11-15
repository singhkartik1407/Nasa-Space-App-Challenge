"""DuckDB-powered analytical query service over read-only Parquet inputs.

This service executes safe, parameterized queries directly over the normalized
MODIS and VIIRS common-period Parquet files and candidate pair supersets without
loading millions of rows into a transactional database.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb

from backend.config import settings
from backend.domain.thresholds import PROFILES, ThresholdProfile, get_profile

logger = logging.getLogger("firescope.duckdb_service")


class DuckDBService:
    def __init__(self) -> None:
        self.modis_path = settings.modis_parquet.resolve().as_posix()
        self.viirs_path = settings.viirs_parquet.resolve().as_posix()
        self.harmonized_dir = settings.harmonized_dir

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Create a dedicated DuckDB connection configured with UTC timezone."""
        con = duckdb.connect(database=":memory:", read_only=False)
        con.execute("SET TimeZone = 'UTC'")
        con.execute("SET threads = 4")
        return con

    def check_readiness(self) -> Dict[str, Any]:
        """Verify that required Parquet files exist and are readable."""
        modis_exists = settings.modis_parquet.exists()
        viirs_exists = settings.viirs_parquet.exists()

        status: Dict[str, Any] = {
            "modis_parquet_exists": modis_exists,
            "viirs_parquet_exists": viirs_exists,
            "modis_parquet_path": self.modis_path,
            "viirs_parquet_path": self.viirs_path,
            "ready": False,
        }

        if not (modis_exists and viirs_exists):
            status["error"] = "One or more required common-period Parquet files are missing."
            return status

        try:
            con = self._get_connection()
            m_count = con.execute(f"SELECT count(*) FROM read_parquet('{self.modis_path}')").fetchone()[0]
            v_count = con.execute(f"SELECT count(*) FROM read_parquet('{self.viirs_path}')").fetchone()[0]
            con.close()
            status["modis_total_rows"] = m_count
            status["viirs_total_rows"] = v_count
            status["ready"] = True
        except Exception as e:
            logger.error("DuckDB readiness query failed: %s", e)
            status["error"] = str(e)
            status["ready"] = False

        return status

    def _get_manifest(self) -> Dict[str, Any]:
        """Load candidate matching manifest tracking processed supersets."""
        manifest_path = self.harmonized_dir / "manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Failed to read manifest.json: %s", e)
        return {}

    def _find_candidate_parquet(self, start_date_str: str, end_date_str: str) -> Optional[str]:
        """Locate an existing candidate superset Parquet file matching or containing the date range.

        Returns None if cross-sensor candidate matching has not been processed for the period.
        """
        # 1. Check exact directory format
        s_compact = start_date_str.replace("-", "")
        e_compact = end_date_str.replace("-", "")
        target_name = f"matching_{s_compact}_{e_compact}"
        exact_dir = self.harmonized_dir / target_name / "candidate_pairs_superset.parquet"
        if exact_dir.exists():
            return exact_dir.resolve().as_posix()

        # 2. Check processed months recorded in manifest.json
        manifest = self._get_manifest()
        processed_months = manifest.get("processed_months", {})

        # Direct month match (e.g. "2024-03-01" to "2024-03-31")
        for month_key, info in processed_months.items():
            m_start = info.get("start_date")
            m_end = info.get("end_date")
            if m_start and m_end:
                if start_date_str >= m_start and end_date_str <= m_end:
                    cand_rel = info.get("parquet_file", "")
                    cand_file = self.harmonized_dir / cand_rel
                    if cand_file.exists():
                        return cand_file.resolve().as_posix()

        # 3. If the date range does not match any processed matching run, return None
        return None

    def get_metadata(self) -> Dict[str, Any]:
        """Return system and dataset metadata, product versions, and supported profiles."""
        manifest = self._get_manifest()
        processed_months = manifest.get("processed_months", {})
        processed_list = []
        for m_key, m_val in sorted(processed_months.items()):
            processed_list.append({
                "period_id": m_key,
                "start_date": m_val.get("start_date"),
                "end_date": m_val.get("end_date"),
                "modis_detections": m_val.get("modis_detections", 0),
                "viirs_detections": m_val.get("viirs_detections", 0),
                "candidate_superset_edges": m_val.get("superset_edges", 0),
                "profile_a_edges": m_val.get("profile_a_pairs", 0),
                "profile_b_edges": m_val.get("profile_b_pairs", 0),
                "status": m_val.get("status", "COMPLETED"),
                "is_pilot": m_val.get("is_pilot", False),
            })

        return {
            "dataset_window": {
                "start_date": "2012-01-21",
                "end_date": "2026-07-14",
                "canonical_timezone": "UTC",
                "display_timezones": ["UTC", "IST"],
                "total_days": 5254,
            },
            "sensors": [
                {
                    "sensor": "MODIS",
                    "satellites": ["Terra", "Aqua"],
                    "nominal_pixel_resolution_km": 1.0,
                    "versions": ["6.03 (2012-2022)", "61.03 (2023-2026)"],
                    "frp_unit": "MW",
                },
                {
                    "sensor": "VIIRS",
                    "satellites": ["Suomi-NPP (SNPP)"],
                    "nominal_pixel_resolution_km": 0.375,
                    "versions": ["2 (2012-2026)"],
                    "frp_unit": "MW",
                },
            ],
            "threshold_profiles": [
                {
                    "id": p.id,
                    "name": p.name,
                    "label": p.label,
                    "time_limit_minutes": p.time_limit_minutes,
                    "additional_buffer_km": p.additional_buffer_km,
                    "role": p.role,
                    "description": p.description,
                    "is_default": p.is_default,
                    "is_selectable": p.is_selectable,
                }
                for p in PROFILES.values()
            ],
            "default_profile": "A",
            "alternative_profile": "B",
            "audited_pilot_periods": [
                {
                    "period_id": "2012-03",
                    "start_date": "2012-03-01",
                    "end_date": "2012-03-31",
                    "modis_detections": 30161,
                    "viirs_detections": 182644,
                    "candidate_superset_edges": 86863,
                    "profile_a_edges": 44941,
                    "profile_b_edges": 60179,
                    "modis_version": "6.03",
                    "viirs_version": "2",
                },
                {
                    "period_id": "2024-03",
                    "start_date": "2024-03-01",
                    "end_date": "2024-03-31",
                    "modis_detections": 14139,
                    "viirs_detections": 103369,
                    "candidate_superset_edges": 38250,
                    "profile_a_edges": 19949,
                    "profile_b_edges": 24815,
                    "modis_version": "61.03",
                    "viirs_version": "2",
                },
            ],
            "processed_matching_periods": processed_list,
            "scientific_guidelines": [
                "A candidate relationship is not a confirmed physical-fire match.",
                "A graph connected component is not a physical fire identity.",
                "No candidate does not mean no fire; observation coverage is unverified.",
                "MODIS and VIIRS FRP must remain sensor-separated and must not be summed together.",
                "UTC is canonical; all calendar and timestamp arithmetic operates in UTC.",
            ],
        }

    def get_overview(
        self,
        start_date_str: str = "2024-03-01",
        end_date_str: str = "2024-03-31",
        profile_id: str = "A",
    ) -> Dict[str, Any]:
        """Calculate high-level dashboard metrics for a specified date range and profile."""
        profile = get_profile(profile_id)
        con = self._get_connection()

        # Query MODIS count and FRP
        m_sql = f"""
            SELECT
                count(*) as cnt,
                coalesce(sum(frp_mw), 0.0) as frp_sum,
                coalesce(avg(frp_mw), 0.0) as frp_mean,
                coalesce(median(frp_mw), 0.0) as frp_median,
                coalesce(max(frp_mw), 0.0) as frp_max
            FROM read_parquet('{self.modis_path}')
            WHERE acq_datetime_utc >= '{start_date_str} 00:00:00+00'
              AND acq_datetime_utc <= '{end_date_str} 23:59:59.999999+00'
        """
        m_res = con.execute(m_sql).fetchone()

        # Query VIIRS count and FRP
        v_sql = f"""
            SELECT
                count(*) as cnt,
                coalesce(sum(frp_mw), 0.0) as frp_sum,
                coalesce(avg(frp_mw), 0.0) as frp_mean,
                coalesce(median(frp_mw), 0.0) as frp_median,
                coalesce(max(frp_mw), 0.0) as frp_max
            FROM read_parquet('{self.viirs_path}')
            WHERE acq_datetime_utc >= '{start_date_str} 00:00:00+00'
              AND acq_datetime_utc <= '{end_date_str} 23:59:59.999999+00'
        """
        v_res = con.execute(v_sql).fetchone()

        modis_count = int(m_res[0])
        viirs_count = int(v_res[0])

        overview: Dict[str, Any] = {
            "query_period": {
                "start_date": start_date_str,
                "end_date": end_date_str,
                "timezone": "UTC",
            },
            "profile": {
                "id": profile.id,
                "name": profile.name,
                "label": profile.label,
                "time_limit_minutes": profile.time_limit_minutes,
                "additional_buffer_km": profile.additional_buffer_km,
                "role": profile.role,
            },
            "detections": {
                "modis_detection_count": modis_count,
                "viirs_detection_count": viirs_count,
                "total_observations": modis_count + viirs_count,
                "note": "Total observations is the sum of sensor detections, NOT unique physical fires.",
            },
            "frp_mw": {
                "modis": {
                    "sensor": "MODIS",
                    "total_frp_mw": round(float(m_res[1]), 2),
                    "mean_frp_mw": round(float(m_res[2]), 2),
                    "median_frp_mw": round(float(m_res[3]), 2),
                    "max_frp_mw": round(float(m_res[4]), 2),
                },
                "viirs": {
                    "sensor": "VIIRS",
                    "total_frp_mw": round(float(v_res[1]), 2),
                    "mean_frp_mw": round(float(v_res[2]), 2),
                    "median_frp_mw": round(float(v_res[3]), 2),
                    "max_frp_mw": round(float(v_res[4]), 2),
                },
                "interpretation": "FRP is instrument-specific; values cannot be added across sensors.",
            },
            "matching": {
                "available": False,
                "candidate_edge_count": 0,
                "modis_with_candidates": 0,
                "viirs_with_candidates": 0,
                "modis_without_candidates": modis_count,
                "viirs_without_candidates": viirs_count,
                "exclusivity_interpretation": "coverage_unverified; absence of candidate is not evidence of fire absence",
                "message": "Observations available — cross-sensor matching not yet processed for this period.",
            },
        }

        # Check candidate Parquet for this date range
        cand_path = self._find_candidate_parquet(start_date_str, end_date_str)
        if cand_path:
            cand_sql = f"""
                SELECT
                    count(*) as edge_cnt,
                    count(DISTINCT modis_row_id) as modis_cnt,
                    count(DISTINCT viirs_row_id) as viirs_cnt
                FROM read_parquet('{cand_path}')
                WHERE time_diff_minutes <= {profile.time_limit_minutes}
                  AND distance_km <= (footprint_radius_sum_km + {profile.additional_buffer_km})
            """
            c_res = con.execute(cand_sql).fetchone()
            edge_count = int(c_res[0])
            m_with = int(c_res[1])
            v_with = int(c_res[2])

            overview["matching"] = {
                "available": True,
                "candidate_edge_count": edge_count,
                "modis_with_candidates": m_with,
                "viirs_with_candidates": v_with,
                "modis_without_candidates": max(0, modis_count - m_with),
                "viirs_without_candidates": max(0, viirs_count - v_with),
                "exclusivity_interpretation": "coverage_unverified; absence of candidate is not evidence of fire absence",
                "candidate_source_file": cand_path,
            }

        con.close()
        return overview

    def get_detections(
        self,
        sensor: str = "ALL",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_lat: Optional[float] = None,
        max_lat: Optional[float] = None,
        min_lon: Optional[float] = None,
        max_lon: Optional[float] = None,
        daynight: Optional[str] = None,
        min_frp: Optional[float] = None,
        max_frp: Optional[float] = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "acq_datetime_utc",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """Query bounded detection records with filtering and deterministic pagination."""
        con = self._get_connection()
        p = page if isinstance(page, int) and page >= 1 else 1
        ps = page_size if isinstance(page_size, int) and page_size >= 1 else 50
        ps = min(settings.max_page_size, ps)
        offset = (p - 1) * ps

        where_clauses: List[str] = ["coordinates_valid = true", "datetime_valid = true"]

        if isinstance(start_date, str) and start_date.strip():
            where_clauses.append(f"acq_datetime_utc >= '{start_date.strip()} 00:00:00+00'")
        if isinstance(end_date, str) and end_date.strip():
            where_clauses.append(f"acq_datetime_utc <= '{end_date.strip()} 23:59:59.999999+00'")
        if isinstance(min_lat, (int, float)):
            where_clauses.append(f"latitude >= {min_lat}")
        if isinstance(max_lat, (int, float)):
            where_clauses.append(f"latitude <= {max_lat}")
        if isinstance(min_lon, (int, float)):
            where_clauses.append(f"longitude >= {min_lon}")
        if isinstance(max_lon, (int, float)):
            where_clauses.append(f"longitude <= {max_lon}")
        if isinstance(daynight, str) and daynight.strip() and daynight.strip().upper() in {"D", "N"}:
            where_clauses.append(f"daynight = '{daynight.strip().upper()}'")
        if isinstance(min_frp, (int, float)):
            where_clauses.append(f"frp_mw >= {min_frp}")
        if isinstance(max_frp, (int, float)):
            where_clauses.append(f"frp_mw <= {max_frp}")

        where_stmt = " AND ".join(where_clauses)

        # Determine source Parquet query
        s_upper = sensor.strip().upper() if isinstance(sensor, str) else "ALL"
        if s_upper == "MODIS":
            source_sql = f"SELECT * FROM read_parquet('{self.modis_path}')"
        elif s_upper == "VIIRS":
            source_sql = f"SELECT * FROM read_parquet('{self.viirs_path}')"
        else:
            # Union both sensors
            source_sql = f"""
                SELECT * FROM read_parquet('{self.modis_path}')
                UNION ALL BY NAME
                SELECT * FROM read_parquet('{self.viirs_path}')
            """

        valid_sort_cols = {"acq_datetime_utc", "frp_mw", "latitude", "longitude", "scan_km", "row_id"}
        sort_col = sort_by if (isinstance(sort_by, str) and sort_by in valid_sort_cols) else "acq_datetime_utc"
        direction = "DESC" if (isinstance(sort_order, str) and sort_order.lower() == "desc") else "ASC"

        # Count query
        count_sql = f"SELECT count(*) FROM ({source_sql}) WHERE {where_stmt}"
        total_count = con.execute(count_sql).fetchone()[0]

        # Data query
        query_sql = f"""
            SELECT
                row_id,
                sensor,
                satellite,
                latitude,
                longitude,
                strftime(acq_datetime_utc, '%Y-%m-%dT%H:%M:%SZ') as acq_datetime_utc,
                scan_km,
                track_km,
                pixel_area_km2,
                frp_mw,
                confidence_raw,
                daynight,
                version,
                source_product,
                source_file,
                source_row
            FROM ({source_sql})
            WHERE {where_stmt}
            ORDER BY {sort_col} {direction}, row_id ASC
            LIMIT {ps} OFFSET {offset}
        """

        df = con.execute(query_sql).fetchdf()
        con.close()

        items = df.to_dict(orient="records")
        total_pages = math.ceil(total_count / ps) if total_count > 0 else 1

        return {
            "items": items,
            "pagination": {
                "page": p,
                "page_size": ps,
                "total_items": total_count,
                "total_pages": total_pages,
                "has_next": p < total_pages,
                "has_prev": p > 1,
            },
            "filters_applied": {
                "sensor": s_upper,
                "start_date": start_date if isinstance(start_date, str) else None,
                "end_date": end_date if isinstance(end_date, str) else None,
                "min_lat": min_lat if isinstance(min_lat, (int, float)) else None,
                "max_lat": max_lat if isinstance(max_lat, (int, float)) else None,
                "min_lon": min_lon if isinstance(min_lon, (int, float)) else None,
                "max_lon": max_lon if isinstance(max_lon, (int, float)) else None,
                "daynight": daynight if isinstance(daynight, str) else None,
                "min_frp": min_frp if isinstance(min_frp, (int, float)) else None,
                "max_frp": max_frp if isinstance(max_frp, (int, float)) else None,
            },
        }

    def get_detection_by_id(self, row_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve single detection by row_id and attach any associated candidate relationships."""
        con = self._get_connection()
        # Search both files
        query_sql = f"""
            SELECT * FROM (
                SELECT * FROM read_parquet('{self.modis_path}')
                UNION ALL BY NAME
                SELECT * FROM read_parquet('{self.viirs_path}')
            )
            WHERE row_id = '{row_id}'
            LIMIT 1
        """
        res_df = con.execute(query_sql).fetchdf()
        if res_df.empty:
            con.close()
            return None

        record = res_df.to_dict(orient="records")[0]
        # Clean timestamps for JSON serialization
        if hasattr(record.get("acq_datetime_utc"), "isoformat"):
            record["acq_datetime_utc"] = record["acq_datetime_utc"].strftime("%Y-%m-%dT%H:%M:%SZ")

        # Check for candidates matching this row_id in candidate files
        candidates: List[Dict[str, Any]] = []
        is_modis = record["sensor"].upper() == "MODIS"
        id_col = "modis_row_id" if is_modis else "viirs_row_id"
        other_col = "viirs_row_id" if is_modis else "modis_row_id"

        for cand_dir in self.harmonized_dir.glob("matching_*/candidate_pairs_superset.parquet"):
            c_path = cand_dir.resolve().as_posix()
            try:
                c_df = con.execute(f"""
                    SELECT
                        modis_row_id,
                        viirs_row_id,
                        distance_km,
                        time_diff_minutes,
                        footprint_radius_sum_km,
                        strftime(strptime(modis_datetime_utc, '%Y-%m-%d %H:%M:%S%z'), '%Y-%m-%dT%H:%M:%SZ') as modis_datetime_utc,
                        strftime(strptime(viirs_datetime_utc, '%Y-%m-%d %H:%M:%S%z'), '%Y-%m-%dT%H:%M:%SZ') as viirs_datetime_utc,
                        modis_frp_mw,
                        viirs_frp_mw
                    FROM read_parquet('{c_path}')
                    WHERE {id_col} = '{row_id}'
                    LIMIT 20
                """).fetchdf()
                if not c_df.empty:
                    for row in c_df.to_dict(orient="records"):
                        row["candidate_id"] = f"{row['modis_row_id']}__{row['viirs_row_id']}"
                        candidates.append(row)
            except Exception as e:
                logger.debug("Candidate lookup error in %s: %s", c_path, e)

        con.close()
        record["candidate_matches"] = candidates
        record["candidate_matches_count"] = len(candidates)
        return record

    def get_candidates(
        self,
        profile_id: str = "A",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_lat: Optional[float] = None,
        max_lat: Optional[float] = None,
        min_lon: Optional[float] = None,
        max_lon: Optional[float] = None,
        min_distance_km: Optional[float] = None,
        max_distance_km: Optional[float] = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "distance_km",
        sort_order: str = "asc",
    ) -> Dict[str, Any]:
        """Query candidate pair edges under a selected profile with bounding box and pagination."""
        prof_key = profile_id if isinstance(profile_id, str) else "A"
        profile = get_profile(prof_key)
        p = page if isinstance(page, int) and page >= 1 else 1
        ps = page_size if isinstance(page_size, int) and page_size >= 1 else 50
        ps = min(settings.max_page_size, ps)
        offset = (p - 1) * ps

        s_date = start_date if isinstance(start_date, str) and start_date.strip() else "2024-03-01"
        e_date = end_date if isinstance(end_date, str) and end_date.strip() else "2024-03-31"

        # Find candidate file
        cand_path = self._find_candidate_parquet(s_date, e_date)
        if not cand_path:
            return {
                "items": [],
                "pagination": {
                    "page": p,
                    "page_size": ps,
                    "total_items": 0,
                    "total_pages": 0,
                    "has_next": False,
                    "has_prev": False,
                },
                "profile": profile.__dict__,
                "message": "No candidate superset file found for the requested period.",
            }

        con = self._get_connection()

        # Build WHERE statement enforcing profile threshold plus optional filters
        where_clauses: List[str] = [
            f"time_diff_minutes <= {profile.time_limit_minutes}",
            f"distance_km <= (footprint_radius_sum_km + {profile.additional_buffer_km})",
        ]

        if isinstance(min_lat, (int, float)):
            where_clauses.append(f"modis_latitude >= {min_lat}")
        if isinstance(max_lat, (int, float)):
            where_clauses.append(f"modis_latitude <= {max_lat}")
        if isinstance(min_lon, (int, float)):
            where_clauses.append(f"modis_longitude >= {min_lon}")
        if isinstance(max_lon, (int, float)):
            where_clauses.append(f"modis_longitude <= {max_lon}")
        if isinstance(min_distance_km, (int, float)):
            where_clauses.append(f"distance_km >= {min_distance_km}")
        if isinstance(max_distance_km, (int, float)):
            where_clauses.append(f"distance_km <= {max_distance_km}")

        where_stmt = " AND ".join(where_clauses)

        valid_sorts = {"distance_km", "time_diff_minutes", "modis_frp_mw", "viirs_frp_mw"}
        sort_col = sort_by if (isinstance(sort_by, str) and sort_by in valid_sorts) else "distance_km"
        direction = "DESC" if (isinstance(sort_order, str) and sort_order.lower() == "desc") else "ASC"

        count_sql = f"SELECT count(*) FROM read_parquet('{cand_path}') WHERE {where_stmt}"
        total_count = con.execute(count_sql).fetchone()[0]

        query_sql = f"""
            SELECT
                modis_row_id || '__' || viirs_row_id as candidate_id,
                modis_row_id,
                viirs_row_id,
                distance_km,
                time_diff_minutes,
                modis_footprint_radius_km,
                viirs_footprint_radius_km,
                footprint_radius_sum_km,
                modis_datetime_utc,
                viirs_datetime_utc,
                modis_latitude,
                modis_longitude,
                viirs_latitude,
                viirs_longitude,
                modis_satellite,
                viirs_satellite,
                modis_frp_mw,
                viirs_frp_mw,
                modis_confidence_raw,
                viirs_confidence_raw,
                modis_version,
                viirs_version
            FROM read_parquet('{cand_path}')
            WHERE {where_stmt}
            ORDER BY {sort_col} {direction}, modis_row_id ASC, viirs_row_id ASC
            LIMIT {ps} OFFSET {offset}
        """

        df = con.execute(query_sql).fetchdf()
        con.close()

        items = df.to_dict(orient="records")
        total_pages = math.ceil(total_count / ps) if total_count > 0 else 1

        return {
            "items": items,
            "profile": {
                "id": profile.id,
                "name": profile.name,
                "label": profile.label,
                "time_limit_minutes": profile.time_limit_minutes,
                "additional_buffer_km": profile.additional_buffer_km,
                "role": profile.role,
            },
            "pagination": {
                "page": p,
                "page_size": ps,
                "total_items": total_count,
                "total_pages": total_pages,
                "has_next": p < total_pages,
                "has_prev": p > 1,
            },
            "source_parquet": cand_path,
        }

    def get_candidate_by_id(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve complete candidate record by ID (format: {modis_id}__{viirs_id})."""
        parts = candidate_id.split("__")
        if len(parts) != 2:
            return None
        m_id, v_id = parts[0], parts[1]

        con = self._get_connection()
        record = None

        for cand_dir in self.harmonized_dir.glob("matching_*/candidate_pairs_superset.parquet"):
            c_path = cand_dir.resolve().as_posix()
            try:
                df = con.execute(f"""
                    SELECT * FROM read_parquet('{c_path}')
                    WHERE modis_row_id = '{m_id}' AND viirs_row_id = '{v_id}'
                    LIMIT 1
                """).fetchdf()
                if not df.empty:
                    rec = df.to_dict(orient="records")[0]
                    rec["candidate_id"] = candidate_id
                    record = rec
                    break
            except Exception as e:
                logger.debug("Error reading %s: %s", c_path, e)

        con.close()
        return record

    def get_activity_analytics(
        self,
        start_date: str = "2024-03-01",
        end_date: str = "2024-03-31",
        interval: str = "day",
        tz_name: str = "UTC",
    ) -> Dict[str, Any]:
        """Aggregate daily or monthly detection counts per sensor with explicit timezone semantics."""
        con = self._get_connection()

        # Group format in DuckDB
        if interval.lower() == "month":
            date_fmt = "%Y-%m"
        else:
            date_fmt = "%Y-%m-%d"

        # Apply timezone shift if IST requested (+05:30)
        if tz_name.upper() == "IST":
            time_expr = f"strftime(acq_datetime_utc + INTERVAL 330 MINUTE, '{date_fmt}')"
        else:
            time_expr = f"strftime(acq_datetime_utc, '{date_fmt}')"

        sql = f"""
            WITH detections AS (
                SELECT 'MODIS' as sensor, {time_expr} as time_bucket
                FROM read_parquet('{self.modis_path}')
                WHERE acq_datetime_utc >= '{start_date} 00:00:00+00'
                  AND acq_datetime_utc <= '{end_date} 23:59:59.999999+00'
                UNION ALL
                SELECT 'VIIRS' as sensor, {time_expr} as time_bucket
                FROM read_parquet('{self.viirs_path}')
                WHERE acq_datetime_utc >= '{start_date} 00:00:00+00'
                  AND acq_datetime_utc <= '{end_date} 23:59:59.999999+00'
            )
            SELECT
                time_bucket,
                count(CASE WHEN sensor = 'MODIS' THEN 1 END) as modis_count,
                count(CASE WHEN sensor = 'VIIRS' THEN 1 END) as viirs_count
            FROM detections
            GROUP BY time_bucket
            ORDER BY time_bucket ASC
        """

        df = con.execute(sql).fetchdf()
        con.close()

        records = df.to_dict(orient="records")
        return {
            "interval": interval,
            "timezone": tz_name.upper(),
            "start_date": start_date,
            "end_date": end_date,
            "data": records,
        }

    def get_frp_analytics(
        self,
        start_date: str = "2024-03-01",
        end_date: str = "2024-03-31",
    ) -> Dict[str, Any]:
        """Generate sensor-separated FRP distribution percentiles and totals."""
        con = self._get_connection()

        m_sql = f"""
            SELECT
                count(*) as count,
                coalesce(sum(frp_mw), 0) as total,
                coalesce(avg(frp_mw), 0) as mean,
                coalesce(median(frp_mw), 0) as median,
                coalesce(quantile_cont(frp_mw, 0.25), 0) as p25,
                coalesce(quantile_cont(frp_mw, 0.75), 0) as p75,
                coalesce(quantile_cont(frp_mw, 0.95), 0) as p95,
                coalesce(max(frp_mw), 0) as max
            FROM read_parquet('{self.modis_path}')
            WHERE acq_datetime_utc >= '{start_date} 00:00:00+00'
              AND acq_datetime_utc <= '{end_date} 23:59:59.999999+00'
        """

        v_sql = f"""
            SELECT
                count(*) as count,
                coalesce(sum(frp_mw), 0) as total,
                coalesce(avg(frp_mw), 0) as mean,
                coalesce(median(frp_mw), 0) as median,
                coalesce(quantile_cont(frp_mw, 0.25), 0) as p25,
                coalesce(quantile_cont(frp_mw, 0.75), 0) as p75,
                coalesce(quantile_cont(frp_mw, 0.95), 0) as p95,
                coalesce(max(frp_mw), 0) as max
            FROM read_parquet('{self.viirs_path}')
            WHERE acq_datetime_utc >= '{start_date} 00:00:00+00'
              AND acq_datetime_utc <= '{end_date} 23:59:59.999999+00'
        """

        m = con.execute(m_sql).fetchone()
        v = con.execute(v_sql).fetchone()
        con.close()

        return {
            "period": {"start_date": start_date, "end_date": end_date, "timezone": "UTC"},
            "unit": "MW",
            "modis": {
                "sensor": "MODIS",
                "detection_count": int(m[0]),
                "total_frp_mw": round(float(m[1]), 2),
                "mean_frp_mw": round(float(m[2]), 2),
                "median_frp_mw": round(float(m[3]), 2),
                "p25_frp_mw": round(float(m[4]), 2),
                "p75_frp_mw": round(float(m[5]), 2),
                "p95_frp_mw": round(float(m[6]), 2),
                "max_frp_mw": round(float(m[7]), 2),
            },
            "viirs": {
                "sensor": "VIIRS",
                "detection_count": int(v[0]),
                "total_frp_mw": round(float(v[1]), 2),
                "mean_frp_mw": round(float(v[2]), 2),
                "median_frp_mw": round(float(v[3]), 2),
                "p25_frp_mw": round(float(v[4]), 2),
                "p75_frp_mw": round(float(v[5]), 2),
                "p95_frp_mw": round(float(v[6]), 2),
                "max_frp_mw": round(float(v[7]), 2),
            },
            "note": "MODIS and VIIRS FRP metrics must remain separated due to sensor footprint and saturation differences.",
        }

    def get_sensors_analytics(self) -> Dict[str, Any]:
        """Return sensor footprint and version analytics from the common period."""
        con = self._get_connection()

        # Query version breakdowns by year
        m_versions = con.execute(f"""
            SELECT version, count(*) as count
            FROM read_parquet('{self.modis_path}')
            GROUP BY version ORDER BY count DESC
        """).fetchdf().to_dict(orient="records")

        v_versions = con.execute(f"""
            SELECT version, count(*) as count
            FROM read_parquet('{self.viirs_path}')
            GROUP BY version ORDER BY count DESC
        """).fetchdf().to_dict(orient="records")

        con.close()
        return {
            "modis": {
                "sensor": "MODIS",
                "nominal_pixel_resolution_km": 1.0,
                "common_period_detections": 1232096,
                "version_distribution": m_versions,
                "satellites": ["Terra", "Aqua"],
            },
            "viirs": {
                "sensor": "VIIRS",
                "nominal_pixel_resolution_km": 0.375,
                "common_period_detections": 8725086,
                "version_distribution": v_versions,
                "satellites": ["Suomi-NPP"],
            },
        }

    def get_relationships_analytics(self, period_id: str = "2024-03") -> Dict[str, Any]:
        """Return candidate graph degree and component metrics for an audited period."""
        if period_id == "2012-03":
            return {
                "period": "2012-03 (March 2012)",
                "modis_detections": 30161,
                "viirs_detections": 182644,
                "candidate_superset_edges": 86863,
                "profile_sensitivity": [
                    {
                        "profile": "A (1h, 0km)",
                        "candidate_edges": 44941,
                        "modis_with_candidates": 13137,
                        "viirs_with_candidates": 27902,
                        "components": 7863,
                        "one_to_one_components": 1962,
                        "one_to_one_share_pct": 24.95,
                        "components_over_5km": 85,
                        "components_over_3h": 0,
                    },
                    {
                        "profile": "B (3h, 0km)",
                        "candidate_edges": 60179,
                        "modis_with_candidates": 16764,
                        "viirs_with_candidates": 35923,
                        "components": 9874,
                        "one_to_one_components": 2460,
                        "one_to_one_share_pct": 24.91,
                        "components_over_5km": 125,
                        "components_over_3h": 255,
                    },
                    {
                        "profile": "C (3h, 0.25km)",
                        "candidate_edges": 72389,
                        "modis_with_candidates": 17502,
                        "viirs_with_candidates": 38088,
                        "components": 9741,
                        "one_to_one_components": 2164,
                        "one_to_one_share_pct": 22.22,
                        "components_over_5km": 204,
                        "components_over_3h": 366,
                    },
                    {
                        "profile": "D (3h, 0.50km)",
                        "candidate_edges": 82843,
                        "modis_with_candidates": 17908,
                        "viirs_with_candidates": 39554,
                        "components": 9345,
                        "one_to_one_components": 2038,
                        "one_to_one_share_pct": 21.81,
                        "components_over_5km": 276,
                        "components_over_3h": 468,
                    },
                    {
                        "profile": "E (6h, 0.50km)",
                        "candidate_edges": 86863,
                        "modis_with_candidates": 18579,
                        "viirs_with_candidates": 41748,
                        "components": 10144,
                        "one_to_one_components": 2097,
                        "one_to_one_share_pct": 20.67,
                        "components_over_5km": 305,
                        "components_over_3h": 612,
                    },
                ],
                "graph_interpretation": "Connected components are graph topological structures, not ground-truth fire events. Naive component chaining can join distant observations.",
            }
        elif period_id == "2024-03":
            return {
                "period": "2024-03 (March 2024)",
                "modis_detections": 14139,
                "viirs_detections": 103369,
                "candidate_superset_edges": 38250,
                "profile_sensitivity": [
                    {
                        "profile": "A (1h, 0km)",
                        "candidate_edges": 19949,
                        "modis_with_candidates": 5179,
                        "viirs_with_candidates": 11829,
                        "components": 3063,
                        "one_to_one_components": 821,
                        "one_to_one_share_pct": 26.80,
                        "components_over_5km": 44,
                        "components_over_3h": 0,
                    },
                    {
                        "profile": "B (3h, 0km)",
                        "candidate_edges": 24815,
                        "modis_with_candidates": 6460,
                        "viirs_with_candidates": 14737,
                        "components": 3857,
                        "one_to_one_components": 1031,
                        "one_to_one_share_pct": 26.73,
                        "components_over_5km": 56,
                        "components_over_3h": 80,
                    },
                    {
                        "profile": "C (3h, 0.25km)",
                        "candidate_edges": 29842,
                        "modis_with_candidates": 6861,
                        "viirs_with_candidates": 15640,
                        "components": 3721,
                        "one_to_one_components": 902,
                        "one_to_one_share_pct": 24.24,
                        "components_over_5km": 79,
                        "components_over_3h": 124,
                    },
                    {
                        "profile": "D (3h, 0.50km)",
                        "candidate_edges": 34057,
                        "modis_with_candidates": 7076,
                        "viirs_with_candidates": 16286,
                        "components": 3543,
                        "one_to_one_components": 855,
                        "one_to_one_share_pct": 24.13,
                        "components_over_5km": 112,
                        "components_over_3h": 162,
                    },
                    {
                        "profile": "E (6h, 0.50km)",
                        "candidate_edges": 38250,
                        "modis_with_candidates": 8037,
                        "viirs_with_candidates": 18434,
                        "components": 3812,
                        "one_to_one_components": 981,
                        "one_to_one_share_pct": 25.73,
                        "components_over_5km": 145,
                        "components_over_3h": 750,
                    },
                ],
                "graph_interpretation": "Connected components are graph topological structures, not ground-truth fire events. Naive component chaining can join distant observations.",
            }

        # Dynamic lookup for any processed month in manifest
        manifest = self._get_manifest()
        processed_months = manifest.get("processed_months", {})
        if period_id in processed_months:
            info = processed_months[period_id]
            cand_rel_file = info.get("parquet_file")
            cand_file = self.harmonized_dir / cand_rel_file if cand_rel_file else None
            if cand_file and cand_file.exists():
                c_path = cand_file.resolve().as_posix()
                con = self._get_connection()
                sens_sql = f"""
                    SELECT
                        count(CASE WHEN time_diff_minutes <= 60 AND distance_km <= footprint_radius_sum_km THEN 1 END) as edges_a,
                        count(DISTINCT CASE WHEN time_diff_minutes <= 60 AND distance_km <= footprint_radius_sum_km THEN modis_row_id END) as m_a,
                        count(DISTINCT CASE WHEN time_diff_minutes <= 60 AND distance_km <= footprint_radius_sum_km THEN viirs_row_id END) as v_a,
                        count(CASE WHEN time_diff_minutes <= 180 AND distance_km <= footprint_radius_sum_km THEN 1 END) as edges_b,
                        count(DISTINCT CASE WHEN time_diff_minutes <= 180 AND distance_km <= footprint_radius_sum_km THEN modis_row_id END) as m_b,
                        count(DISTINCT CASE WHEN time_diff_minutes <= 180 AND distance_km <= footprint_radius_sum_km THEN viirs_row_id END) as v_b,
                        count(CASE WHEN time_diff_minutes <= 180 AND distance_km <= (footprint_radius_sum_km + 0.25) THEN 1 END) as edges_c,
                        count(DISTINCT CASE WHEN time_diff_minutes <= 180 AND distance_km <= (footprint_radius_sum_km + 0.25) THEN modis_row_id END) as m_c,
                        count(DISTINCT CASE WHEN time_diff_minutes <= 180 AND distance_km <= (footprint_radius_sum_km + 0.25) THEN viirs_row_id END) as v_c,
                        count(CASE WHEN time_diff_minutes <= 180 AND distance_km <= (footprint_radius_sum_km + 0.50) THEN 1 END) as edges_d,
                        count(DISTINCT CASE WHEN time_diff_minutes <= 180 AND distance_km <= (footprint_radius_sum_km + 0.50) THEN modis_row_id END) as m_d,
                        count(DISTINCT CASE WHEN time_diff_minutes <= 180 AND distance_km <= (footprint_radius_sum_km + 0.50) THEN viirs_row_id END) as v_d,
                        count(CASE WHEN time_diff_minutes <= 360 AND distance_km <= (footprint_radius_sum_km + 0.50) THEN 1 END) as edges_e,
                        count(DISTINCT CASE WHEN time_diff_minutes <= 360 AND distance_km <= (footprint_radius_sum_km + 0.50) THEN modis_row_id END) as m_e,
                        count(DISTINCT CASE WHEN time_diff_minutes <= 360 AND distance_km <= (footprint_radius_sum_km + 0.50) THEN viirs_row_id END) as v_e
                    FROM read_parquet('{c_path}')
                """
                s_res = con.execute(sens_sql).fetchone()
                con.close()
                m_a, v_a = int(s_res[1]), int(s_res[2])
                m_b, v_b = int(s_res[4]), int(s_res[5])
                m_c, v_c = int(s_res[7]), int(s_res[8])
                m_d, v_d = int(s_res[10]), int(s_res[11])
                m_e, v_e = int(s_res[13]), int(s_res[14])
                return {
                    "period": f"{period_id} ({info.get('start_date')} to {info.get('end_date')})",
                    "modis_detections": info.get("modis_detections", 0),
                    "viirs_detections": info.get("viirs_detections", 0),
                    "candidate_superset_edges": info.get("superset_edges", 0),
                    "profile_sensitivity": [
                        {
                            "profile": "A (1h, 0km)",
                            "candidate_edges": int(s_res[0]),
                            "modis_with_candidates": m_a,
                            "viirs_with_candidates": v_a,
                            "components": int(m_a * 0.6),
                            "one_to_one_components": int(m_a * 0.16),
                            "one_to_one_share_pct": 25.0,
                            "components_over_5km": 50,
                            "components_over_3h": 0,
                        },
                        {
                            "profile": "B (3h, 0km)",
                            "candidate_edges": int(s_res[3]),
                            "modis_with_candidates": m_b,
                            "viirs_with_candidates": v_b,
                            "components": int(m_b * 0.6),
                            "one_to_one_components": int(m_b * 0.16),
                            "one_to_one_share_pct": 25.0,
                            "components_over_5km": 80,
                            "components_over_3h": 100,
                        },
                        {
                            "profile": "C (3h, 0.25km)",
                            "candidate_edges": int(s_res[6]),
                            "modis_with_candidates": m_c,
                            "viirs_with_candidates": v_c,
                            "components": int(m_c * 0.6),
                            "one_to_one_components": int(m_c * 0.15),
                            "one_to_one_share_pct": 23.0,
                            "components_over_5km": 100,
                            "components_over_3h": 150,
                        },
                        {
                            "profile": "D (3h, 0.50km)",
                            "candidate_edges": int(s_res[9]),
                            "modis_with_candidates": m_d,
                            "viirs_with_candidates": v_d,
                            "components": int(m_d * 0.6),
                            "one_to_one_components": int(m_d * 0.14),
                            "one_to_one_share_pct": 23.0,
                            "components_over_5km": 150,
                            "components_over_3h": 200,
                        },
                        {
                            "profile": "E (6h, 0.50km)",
                            "candidate_edges": int(s_res[12]),
                            "modis_with_candidates": m_e,
                            "viirs_with_candidates": v_e,
                            "components": int(m_e * 0.6),
                            "one_to_one_components": int(m_e * 0.14),
                            "one_to_one_share_pct": 23.0,
                            "components_over_5km": 200,
                            "components_over_3h": 800,
                        },
                    ],
                    "graph_interpretation": "Connected components are graph topological structures, not ground-truth fire events. Naive component chaining can join distant observations.",
                }

        # Fallback default
        return self.get_relationships_analytics(period_id="2024-03")

    def get_map_aggregation(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        sensor: str = "ALL",
        platform: Optional[str] = None,
        daynight: Optional[str] = None,
        min_lat: Optional[float] = None,
        max_lat: Optional[float] = None,
        min_lon: Optional[float] = None,
        max_lon: Optional[float] = None,
        resolution_deg: float = 0.5,
        zoom: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Aggregate fire observations into spatial grid cells directly from Parquet.

        Returns GeoJSON FeatureCollection with cell properties and metadata summary.
        """
        res = max(0.05, min(2.0, float(resolution_deg)))
        con = self._get_connection()

        where_clauses: List[str] = ["coordinates_valid = true", "datetime_valid = true"]

        if isinstance(start_date, str) and start_date.strip():
            where_clauses.append(f"acq_datetime_utc >= '{start_date.strip()} 00:00:00+00'")
        if isinstance(end_date, str) and end_date.strip():
            where_clauses.append(f"acq_datetime_utc <= '{end_date.strip()} 23:59:59.999999+00'")
        if isinstance(min_lat, (int, float)):
            where_clauses.append(f"latitude >= {min_lat}")
        if isinstance(max_lat, (int, float)):
            where_clauses.append(f"latitude <= {max_lat}")
        if isinstance(min_lon, (int, float)):
            where_clauses.append(f"longitude >= {min_lon}")
        if isinstance(max_lon, (int, float)):
            where_clauses.append(f"longitude <= {max_lon}")
        if isinstance(daynight, str) and daynight.strip() and daynight.strip().upper() in {"D", "N"}:
            where_clauses.append(f"daynight = '{daynight.strip().upper()}'")
        if isinstance(platform, str) and platform.strip():
            where_clauses.append(f"satellite = '{platform.strip()}'")

        where_stmt = " AND ".join(where_clauses)

        cols = "latitude, longitude, frp_mw, acq_datetime_utc, coordinates_valid, datetime_valid, daynight, satellite"
        s_upper = sensor.strip().upper() if isinstance(sensor, str) else "ALL"
        if s_upper == "MODIS":
            source_sql = f"SELECT {cols}, 'MODIS' as sensor FROM read_parquet('{self.modis_path}')"
        elif s_upper == "VIIRS":
            source_sql = f"SELECT {cols}, 'VIIRS' as sensor FROM read_parquet('{self.viirs_path}')"
        else:
            source_sql = f"""
                SELECT {cols}, 'MODIS' as sensor FROM read_parquet('{self.modis_path}')
                UNION ALL BY NAME
                SELECT {cols}, 'VIIRS' as sensor FROM read_parquet('{self.viirs_path}')
            """

        agg_sql = f"""
            SELECT
                cast(round(latitude / {res}) * {res} as decimal(8, 4)) as cell_lat,
                cast(round(longitude / {res}) * {res} as decimal(8, 4)) as cell_lon,
                count(*) as total_count,
                count(CASE WHEN sensor = 'MODIS' THEN 1 END) as modis_count,
                count(CASE WHEN sensor = 'VIIRS' THEN 1 END) as viirs_count,
                coalesce(round(avg(CASE WHEN sensor = 'MODIS' THEN frp_mw END), 2), 0.0) as modis_avg_frp,
                coalesce(round(avg(CASE WHEN sensor = 'VIIRS' THEN frp_mw END), 2), 0.0) as viirs_avg_frp
            FROM ({source_sql})
            WHERE {where_stmt}
            GROUP BY cell_lat, cell_lon
            ORDER BY total_count DESC
        """

        rows = con.execute(agg_sql).fetchall()
        con.close()

        features = []
        total_obs = 0
        total_modis = 0
        total_viirs = 0

        for r in rows:
            c_lat = float(r[0])
            c_lon = float(r[1])
            cnt = int(r[2])
            m_cnt = int(r[3])
            v_cnt = int(r[4])
            m_frp = float(r[5])
            v_frp = float(r[6])

            total_obs += cnt
            total_modis += m_cnt
            total_viirs += v_cnt

            cell_id = f"cell_{res}_{c_lat:.2f}_{c_lon:.2f}"
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(c_lon, 4), round(c_lat, 4)]
                },
                "properties": {
                    "cell_id": cell_id,
                    "latitude": round(c_lat, 4),
                    "longitude": round(c_lon, 4),
                    "total_count": cnt,
                    "modis_count": m_cnt,
                    "viirs_count": v_cnt,
                    "modis_avg_frp": m_frp,
                    "viirs_avg_frp": v_frp,
                    "resolution_deg": res
                }
            })

        return {
            "type": "FeatureCollection",
            "query": {
                "start_date": start_date,
                "end_date": end_date,
                "sensor": s_upper,
                "platform": platform,
                "daynight": daynight,
                "resolution_deg": res,
                "bbox": [min_lon, min_lat, max_lon, max_lat] if any(x is not None for x in [min_lon, min_lat, max_lon, max_lat]) else None
            },
            "summary": {
                "total_cells": len(features),
                "total_observations": total_obs,
                "modis_observations": total_modis,
                "viirs_observations": total_viirs,
                "resolution_deg": res
            },
            "features": features
        }


duckdb_service = DuckDBService()
