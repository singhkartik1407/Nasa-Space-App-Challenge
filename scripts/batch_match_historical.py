"""FireScope Historical Matching Batch Runner & Manifest Manager.

Tracks, executes, and audits monthly cross-sensor candidate matching across the 2012-2026
common observation archive, with automated skip-existing, resumability, memory benchmarking,
and atomic manifest state updates.

Supported Manifest States:
  - NOT_PROCESSED
  - RUNNING
  - COMPLETED
  - FAILED
  - VALIDATION_PENDING
  - VALIDATED
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import tracemalloc
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import pyarrow.parquet as pq

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
HARMONIZED_DIR = DATA_DIR / "harmonized"
AUDIT_DIR = ROOT_DIR / "reports" / "audit"
MANIFEST_PATH = HARMONIZED_DIR / "manifest.json"
LOG_FILE = AUDIT_DIR / "batch_matching.log"

AUDIT_DIR.mkdir(parents=True, exist_ok=True)
HARMONIZED_DIR.mkdir(parents=True, exist_ok=True)

# Configure logger
logger = logging.getLogger("firescope.batch_matching")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("[%(asctime)s UTC] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

# File handler
fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
fh.setFormatter(formatter)
logger.addHandler(fh)

# Stream handler
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(formatter)
logger.addHandler(sh)

# Authoritative Pilot Benchmark Months
AUDITED_PILOTS = {"2012-03", "2024-03"}

COMMON_PERIOD_START = date(2012, 1, 21)
COMMON_PERIOD_END = date(2026, 7, 14)


def get_all_archive_months() -> List[str]:
    """Return all YYYY-MM month keys in the common period archive (2012-01 to 2026-07)."""
    months = []
    for y in range(2012, 2027):
        max_m = 7 if y == 2026 else 12
        for m in range(1, max_m + 1):
            months.append(f"{y:04d}-{m:02d}")
    return months


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to read manifest.json: %s", e)
    return {
        "version": "1.0.0",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "description": "FireScope monthly candidate matching manifest tracking processed candidate supersets",
        "processed_months": {},
    }


def save_manifest_atomic(manifest: dict) -> None:
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp_path = MANIFEST_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    tmp_path.replace(MANIFEST_PATH)


def get_month_dates(year: int, month: int) -> Tuple[str, str]:
    first_day = date(year, month, 1)
    if year == 2012 and month == 1:
        first_day = COMMON_PERIOD_START
    last_day_num = monthrange(year, month)[1]
    if year == 2026 and month == 7:
        last_day_num = 14
    last_day = date(year, month, last_day_num)
    return first_day.isoformat(), last_day.isoformat()


def is_month_output_complete(year: int, month: int) -> Tuple[bool, Optional[Path], Optional[Path]]:
    s_date, e_date = get_month_dates(year, month)
    s_compact = s_date.replace("-", "")
    e_compact = e_date.replace("-", "")
    run_name = f"matching_{s_compact}_{e_compact}"
    pq_file = HARMONIZED_DIR / run_name / "candidate_pairs_superset.parquet"
    meta_file = AUDIT_DIR / run_name / "matching_run_metadata.json"
    sens_file = AUDIT_DIR / run_name / "threshold_sensitivity.csv"
    if pq_file.exists() and meta_file.exists() and sens_file.exists():
        return True, pq_file, meta_file
    return False, pq_file, meta_file


def update_manifest_from_run(year: int, month: int, status: str = "COMPLETED", error_msg: Optional[str] = None) -> None:
    manifest = load_manifest()
    m_key = f"{year:04d}-{month:02d}"
    s_date, e_date = get_month_dates(year, month)
    s_compact = s_date.replace("-", "")
    e_compact = e_date.replace("-", "")
    run_name = f"matching_{s_compact}_{e_compact}"

    if status == "FAILED":
        manifest["processed_months"][m_key] = {
            "month_key": m_key,
            "start_date": s_date,
            "end_date": e_date,
            "directory": run_name,
            "status": "FAILED",
            "error_message": error_msg or "Unknown error during matching run",
            "is_pilot": m_key in AUDITED_PILOTS,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        save_manifest_atomic(manifest)
        return

    run_dir = HARMONIZED_DIR / run_name
    pq_path = run_dir / "candidate_pairs_superset.parquet"
    meta_file = AUDIT_DIR / run_name / "matching_run_metadata.json"

    if not pq_path.exists() or not meta_file.exists():
        logger.warning("Incomplete output files for %s; marking FAILED", m_key)
        manifest["processed_months"][m_key] = {
            "month_key": m_key,
            "start_date": s_date,
            "end_date": e_date,
            "directory": run_name,
            "status": "FAILED",
            "error_message": "Missing candidate parquet or metadata output",
            "is_pilot": m_key in AUDITED_PILOTS,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        save_manifest_atomic(manifest)
        return

    modis_cnt = 0
    viirs_cnt = 0
    superset_cnt = 0
    prof_a_cnt = 0
    prof_b_cnt = 0
    elapsed_sec = 0.0

    try:
        with open(meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        proc = data.get("processing", {})
        modis_cnt = proc.get("modis_rows_processed", 0)
        viirs_cnt = proc.get("viirs_rows_in_processing_period", 0)
        superset_cnt = proc.get("candidate_pairs_in_superset", 0)
        elapsed_sec = proc.get("elapsed_seconds", 0.0)
        for exp in data.get("threshold_experiments", []):
            if exp.get("experiment") == "A_1h_0km":
                prof_a_cnt = int(exp.get("candidate_pair_count", 0))
            elif exp.get("experiment") == "B_3h_0km":
                prof_b_cnt = int(exp.get("candidate_pair_count", 0))
    except Exception as e:
        logger.error("Error reading metadata for %s: %s", m_key, e)

    # Actual parquet row count verification
    actual_rows = pq.read_metadata(pq_path).num_rows
    if actual_rows != superset_cnt:
        logger.warning("Superset count discrepancy for %s: meta says %d, parquet has %d", m_key, superset_cnt, actual_rows)
        superset_cnt = actual_rows

    final_status = "VALIDATED" if m_key in AUDITED_PILOTS else status

    manifest["processed_months"][m_key] = {
        "month_key": m_key,
        "start_date": s_date,
        "end_date": e_date,
        "directory": run_name,
        "parquet_file": f"{run_name}/candidate_pairs_superset.parquet",
        "modis_detections": modis_cnt,
        "viirs_detections": viirs_cnt,
        "superset_edges": superset_cnt,
        "profile_a_pairs": prof_a_cnt,
        "profile_b_pairs": prof_b_cnt,
        "elapsed_seconds": elapsed_sec,
        "status": final_status,
        "is_pilot": m_key in AUDITED_PILOTS,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    save_manifest_atomic(manifest)
    logger.info("Manifest updated for %s: Status=%s | Superset=%d | Profile A=%d | Profile B=%d (took %.2fs)",
                m_key, final_status, superset_cnt, prof_a_cnt, prof_b_cnt, elapsed_sec)


def process_month(year: int, month: int, force: bool = False) -> bool:
    m_key = f"{year:04d}-{month:02d}"
    manifest = load_manifest()
    existing = manifest.get("processed_months", {}).get(m_key)

    is_complete, pq_file, meta_file = is_month_output_complete(year, month)
    if is_complete and existing and existing.get("status") in ("COMPLETED", "VALIDATED") and not force:
        logger.info("[SKIP] Month %s already %s with %d superset edges", m_key, existing.get("status"), existing.get("superset_edges", 0))
        return True

    s_date, e_date = get_month_dates(year, month)
    logger.info("==================================================================")
    logger.info("Processing month %s (%s to %s)...", m_key, s_date, e_date)

    # Update manifest to RUNNING
    manifest["processed_months"][m_key] = {
        "month_key": m_key,
        "start_date": s_date,
        "end_date": e_date,
        "directory": f"matching_{s_date.replace('-', '')}_{e_date.replace('-', '')}",
        "status": "RUNNING",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "is_pilot": m_key in AUDITED_PILOTS,
    }
    save_manifest_atomic(manifest)

    cmd = [
        sys.executable,
        str(ROOT_DIR / "scripts" / "03_match_sensors_v2.py"),
        "--root", str(ROOT_DIR),
        "--start-date", s_date,
        "--end-date", e_date,
        "--drop-staging-after-success",
    ]

    t0 = time.time()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        elapsed = time.time() - t0
        logger.info("Execution succeeded for %s in %.2fs", m_key, elapsed)
        update_manifest_from_run(year, month, status="COMPLETED")
        return True
    except subprocess.CalledProcessError as exc:
        elapsed = time.time() - t0
        err_msg = exc.stderr[-500:] if exc.stderr else f"Exit code {exc.returncode}"
        logger.error("Matching failed for %s after %.2fs: %s", m_key, elapsed, err_msg)
        update_manifest_from_run(year, month, status="FAILED", error_msg=err_msg)
        return False
    except Exception as exc:
        elapsed = time.time() - t0
        logger.error("Unexpected error for %s after %.2fs: %s", m_key, elapsed, exc)
        update_manifest_from_run(year, month, status="FAILED", error_msg=str(exc))
        return False


def benchmark_month(year: int, month: int) -> dict:
    m_key = f"{year:04d}-{month:02d}"
    s_date, e_date = get_month_dates(year, month)
    logger.info("==================================================================")
    logger.info("[BENCHMARK] Testing candidate matching on %s (%s to %s)...", m_key, s_date, e_date)

    tracemalloc.start()
    t0 = time.time()

    success = process_month(year, month, force=True)
    t1 = time.time()
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    manifest = load_manifest()
    m_info = manifest.get("processed_months", {}).get(m_key, {})

    result = {
        "month_key": m_key,
        "success": success,
        "elapsed_seconds": round(t1 - t0, 3),
        "peak_memory_mb": round(peak_mem / (1024 * 1024), 2),
        "modis_detections": m_info.get("modis_detections", 0),
        "viirs_detections": m_info.get("viirs_detections", 0),
        "superset_edges": m_info.get("superset_edges", 0),
        "profile_a_pairs": m_info.get("profile_a_pairs", 0),
        "profile_b_pairs": m_info.get("profile_b_pairs", 0),
        "status": m_info.get("status"),
    }

    logger.info("[BENCHMARK RESULT] Month %s: Runtime=%.2fs | PeakMem=%.2fMB | MODIS=%d | VIIRS=%d | Superset=%d | ProfA=%d | ProfB=%d",
                m_key, result["elapsed_seconds"], result["peak_memory_mb"],
                result["modis_detections"], result["viirs_detections"],
                result["superset_edges"], result["profile_a_pairs"], result["profile_b_pairs"])
    return result


def verify_boundary_continuity(m1_key: str, m2_key: str) -> dict:
    """Verify that candidate pairs across adjacent months have no overlap and no duplicated MODIS pairs."""
    manifest = load_manifest()
    months = manifest.get("processed_months", {})
    if m1_key not in months or m2_key not in months:
        return {"verified": False, "reason": "Both months must be processed"}

    p1 = HARMONIZED_DIR / months[m1_key]["parquet_file"]
    p2 = HARMONIZED_DIR / months[m2_key]["parquet_file"]

    if not p1.exists() or not p2.exists():
        return {"verified": False, "reason": "Output parquet files missing"}

    con = duckdb.connect()
    try:
        # Check for intersection of candidate pair keys (modis_row_id + viirs_row_id)
        overlap = con.execute(f"""
            SELECT count(*)
            FROM read_parquet('{p1.as_posix()}') a
            JOIN read_parquet('{p2.as_posix()}') b
              ON a.modis_row_id = b.modis_row_id
             AND a.viirs_row_id = b.viirs_row_id
        """).fetchone()[0]

        # Check MODIS row ID overlap
        m_overlap = con.execute(f"""
            SELECT count(DISTINCT a.modis_row_id)
            FROM read_parquet('{p1.as_posix()}') a
            JOIN read_parquet('{p2.as_posix()}') b
              ON a.modis_row_id = b.modis_row_id
        """).fetchone()[0]

        return {
            "verified": (overlap == 0 and m_overlap == 0),
            "pair_overlap": overlap,
            "modis_overlap": m_overlap,
            "m1_edges": months[m1_key]["superset_edges"],
            "m2_edges": months[m2_key]["superset_edges"],
        }
    finally:
        con.close()


def print_status() -> None:
    manifest = load_manifest()
    all_months = get_all_archive_months()
    processed = manifest.get("processed_months", {})

    completed_cnt = sum(1 for m in processed.values() if m.get("status") in ("COMPLETED", "VALIDATED"))
    validated_cnt = sum(1 for m in processed.values() if m.get("status") == "VALIDATED")
    failed_cnt = sum(1 for m in processed.values() if m.get("status") == "FAILED")
    pending_cnt = len(all_months) - completed_cnt - failed_cnt

    total_superset = sum(m.get("superset_edges", 0) for m in processed.values() if m.get("status") in ("COMPLETED", "VALIDATED"))
    total_prof_a = sum(m.get("profile_a_pairs", 0) for m in processed.values() if m.get("status") in ("COMPLETED", "VALIDATED"))
    total_prof_b = sum(m.get("profile_b_pairs", 0) for m in processed.values() if m.get("status") in ("COMPLETED", "VALIDATED"))

    print("\n" + "=" * 95)
    print("FIRESCOPE CANDIDATE MATCHING MANIFEST STATUS")
    print("=" * 95)
    print(f"Total Common-Period Months: {len(all_months)} (2012-01 to 2026-07)")
    print(f"Completed: {completed_cnt} | Validated: {validated_cnt} | Failed: {failed_cnt} | Pending: {pending_cnt}")
    print(f"Total Superset Edges: {total_superset:,} | Profile A Pairs: {total_prof_a:,} | Profile B Pairs: {total_prof_b:,}")
    print("-" * 95)
    print(f"{'Month':<10} {'Start':<12} {'End':<12} {'MODIS':<8} {'VIIRS':<8} {'Superset':<10} {'Prof A':<8} {'Prof B':<8} {'Status'}")
    print("-" * 95)

    for k in all_months:
        if k in processed:
            info = processed[k]
            st = info.get("status", "NOT_PROCESSED")
            m_cnt = info.get("modis_detections", 0)
            v_cnt = info.get("viirs_detections", 0)
            s_cnt = info.get("superset_edges", 0)
            pa_cnt = info.get("profile_a_pairs", 0)
            pb_cnt = info.get("profile_b_pairs", 0)
            s_date = info.get("start_date", "")
            e_date = info.get("end_date", "")
            print(f"{k:<10} {s_date:<12} {e_date:<12} {m_cnt:<8} {v_cnt:<8} {s_cnt:<10} {pa_cnt:<8} {pb_cnt:<8} {st}")
        else:
            y, m = int(k[:4]), int(k[5:7])
            s_date, e_date = get_month_dates(y, m)
            print(f"{k:<10} {s_date:<12} {e_date:<12} {'-':<8} {'-':<8} {'-':<10} {'-':<8} {'-':<8} NOT_PROCESSED")
    print("=" * 95 + "\n")


def refresh_manifest() -> None:
    logger.info("Scanning harmonized directory for candidate outputs...")
    for folder in sorted(HARMONIZED_DIR.glob("matching_*_*")):
        if folder.is_dir() and (folder / "candidate_pairs_superset.parquet").exists():
            parts = folder.name.replace("matching_", "").split("_")
            if len(parts) == 2 and len(parts[0]) == 8:
                y = int(parts[0][:4])
                m = int(parts[0][4:6])
                update_manifest_from_run(y, m)
    logger.info("Manifest refresh complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="FireScope monthly candidate matching manager")
    parser.add_argument("--status", action="store_true", help="Print current manifest status")
    parser.add_argument("--refresh-manifest", action="store_true", help="Scan existing folders and update manifest")
    parser.add_argument("--benchmark", type=str, help="Benchmark single unprocessed month (YYYY-MM)")
    parser.add_argument("--process-month", type=str, help="Process a single month (YYYY-MM)")
    parser.add_argument("--year", type=int, help="Process all unprocessed months in a given calendar year")
    parser.add_argument("--year-range", nargs=2, type=int, metavar=("START_YEAR", "END_YEAR"), help="Process all unprocessed months in year range")
    parser.add_argument("--all", action="store_true", help="Process all unprocessed months across entire archive")
    parser.add_argument("--force", action="store_true", help="Force re-run even if already completed")
    args = parser.parse_args()

    if args.status:
        print_status()
        return

    if args.refresh_manifest:
        refresh_manifest()
        return

    if args.benchmark:
        parts = args.benchmark.split("-")
        y, m = int(parts[0]), int(parts[1])
        res = benchmark_month(y, m)
        print("\nBenchmark completed:")
        print(json.dumps(res, indent=2))
        return

    if args.process_month:
        parts = args.process_month.split("-")
        y, m = int(parts[0]), int(parts[1])
        success = process_month(y, m, force=args.force)
        sys.exit(0 if success else 1)

    if args.year:
        logger.info("Starting processing for year %d...", args.year)
        max_m = 7 if args.year == 2026 else 12
        for m in range(1, max_m + 1):
            process_month(args.year, m, force=args.force)
        print_status()
        return

    if args.year_range:
        sy, ey = args.year_range
        logger.info("Starting processing for year range %d to %d...", sy, ey)
        for y in range(sy, ey + 1):
            max_m = 7 if y == 2026 else 12
            for m in range(1, max_m + 1):
                process_month(y, m, force=args.force)
        print_status()
        return

    if args.all:
        logger.info("Starting batch matching for all missing common-period months (2012-01 to 2026-07)...")
        for y in range(2012, 2027):
            max_m = 7 if y == 2026 else 12
            for m in range(1, max_m + 1):
                process_month(y, m, force=args.force)
        print_status()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
