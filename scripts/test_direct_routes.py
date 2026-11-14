"""Comprehensive smoke test directly calling backend route handlers."""
import time
from fastapi import Response

from backend.routers.health import get_health, get_ready
from backend.routers.metadata import get_metadata
from backend.routers.overview import get_overview
from backend.routers.detections import list_detections, get_detection
from backend.routers.candidates import list_candidates, get_candidate
from backend.routers.analytics import (
    get_activity,
    get_frp_analytics,
    get_sensors_analytics,
    get_relationship_analytics,
)
from backend.routers.jobs import (
    create_matching_job,
    get_matching_job,
    create_review_annotation,
    list_review_annotations,
)
from backend.schemas.jobs import CreateJobRequest, ReviewAnnotationCreate
from backend.database import SessionLocal, init_db

print("Initializing metadata database...", flush=True)
init_db()
db = SessionLocal()

print("\n--- 1. Testing /health & /ready ---", flush=True)
h = get_health()
print(f"Health: status={h.status}, app={h.app_name}, version={h.app_version}")
resp = Response()
r = get_ready(resp)
print(f"Ready: status={r.status}, modis_rows={r.modis_total_rows}, viirs_rows={r.viirs_total_rows}")
assert h.status == "ok"
assert r.ready is True

print("\n--- 2. Testing /api/v1/metadata ---", flush=True)
m = get_metadata()
print(f"Metadata: window={m.dataset_window.start_date} to {m.dataset_window.end_date}, sensors={len(m.sensors)}, profiles={len(m.threshold_profiles)}")
assert m.default_profile == "A"
assert len(m.threshold_profiles) == 5

print("\n--- 3. Testing /api/v1/overview for March 2012 (Profile A & B) ---", flush=True)
t0 = time.time()
o_2012_a = get_overview(start_date="2012-03-01", end_date="2012-03-31", profile="A")
print(f"Overview 2012-A ({time.time()-t0:.3f}s): MODIS={o_2012_a.detections.modis_detection_count}, VIIRS={o_2012_a.detections.viirs_detection_count}, Candidate Edges={o_2012_a.matching.candidate_edge_count}")
assert o_2012_a.detections.modis_detection_count == 30161
assert o_2012_a.detections.viirs_detection_count == 182644
assert o_2012_a.matching.candidate_edge_count == 44941
assert o_2012_a.matching.modis_with_candidates == 13137
assert o_2012_a.matching.viirs_with_candidates == 27902

o_2012_b = get_overview(start_date="2012-03-01", end_date="2012-03-31", profile="B")
print(f"Overview 2012-B: Candidate Edges={o_2012_b.matching.candidate_edge_count}")
assert o_2012_b.matching.candidate_edge_count == 60179

print("\n--- 4. Testing /api/v1/overview for March 2024 (Profile A & B) ---", flush=True)
t0 = time.time()
o_2024_a = get_overview(start_date="2024-03-01", end_date="2024-03-31", profile="A")
print(f"Overview 2024-A ({time.time()-t0:.3f}s): MODIS={o_2024_a.detections.modis_detection_count}, VIIRS={o_2024_a.detections.viirs_detection_count}, Candidate Edges={o_2024_a.matching.candidate_edge_count}")
assert o_2024_a.detections.modis_detection_count == 14139
assert o_2024_a.detections.viirs_detection_count == 103369
assert o_2024_a.matching.candidate_edge_count == 19949
assert o_2024_a.matching.modis_with_candidates == 5179
assert o_2024_a.matching.viirs_with_candidates == 11829

o_2024_b = get_overview(start_date="2024-03-01", end_date="2024-03-31", profile="B")
print(f"Overview 2024-B: Candidate Edges={o_2024_b.matching.candidate_edge_count}")
assert o_2024_b.matching.candidate_edge_count == 24815

print("\n--- 5. Testing /api/v1/detections (pagination, filtering, detail) ---", flush=True)
dets = list_detections(sensor="MODIS", start_date="2024-03-01", end_date="2024-03-05", page=1, page_size=10)
print(f"Detections queried: returned={len(dets.items)}, total={dets.pagination.total_items}")
assert len(dets.items) == 10
first_row_id = dets.items[0].row_id

det_detail = get_detection(first_row_id)
print(f"Detection detail: row_id={det_detail.row_id}, sensor={det_detail.sensor}, satellite={det_detail.satellite}, candidates={det_detail.candidate_matches_count}")
assert det_detail.row_id == first_row_id

print("\n--- 6. Testing /api/v1/candidates (Profile A & detail) ---", flush=True)
cands = list_candidates(profile="A", start_date="2024-03-01", end_date="2024-03-31", page=1, page_size=10)
print(f"Candidates queried: returned={len(cands.items)}, total={cands.pagination.total_items}")
assert len(cands.items) == 10
assert cands.pagination.total_items == 19949
first_cand_id = cands.items[0].candidate_id

cand_detail = get_candidate(first_cand_id)
print(f"Candidate detail: id={cand_detail.candidate_id}, dist={cand_detail.distance_km:.3f} km, time_diff={cand_detail.time_diff_minutes:.1f} min")
assert cand_detail.candidate_id == first_cand_id

print("\n--- 7. Testing /api/v1/analytics (activity, frp, sensors, relationships) ---", flush=True)
act = get_activity(start_date="2024-03-01", end_date="2024-03-07", interval="day", timezone="UTC")
print(f"Activity analytics: buckets={len(act.data)}, sample day 1 MODIS={act.data[0].modis_count}, VIIRS={act.data[0].viirs_count}")
assert len(act.data) == 7

frp = get_frp_analytics(start_date="2024-03-01", end_date="2024-03-31")
print(f"FRP analytics: MODIS mean={frp.modis.mean_frp_mw} MW, VIIRS mean={frp.viirs.mean_frp_mw} MW")
assert frp.modis.detection_count == 14139
assert frp.viirs.detection_count == 103369

sens = get_sensors_analytics()
print(f"Sensors analytics: MODIS total={sens.modis.common_period_detections}, VIIRS total={sens.viirs.common_period_detections}")
assert sens.modis.common_period_detections == 1232096
assert sens.viirs.common_period_detections == 8725086

rel = get_relationship_analytics(period="2024-03")
print(f"Relationships analytics: profiles={len(rel.profile_sensitivity)}, superset_edges={rel.candidate_superset_edges}")
assert rel.candidate_superset_edges == 38250

print("\n--- 8. Testing /api/v1/matching/jobs & review annotations ---", flush=True)
job_req = CreateJobRequest(start_date="2024-03-01", end_date="2024-03-31", profile_id="A")
job_res = create_matching_job(job_req, db)
print(f"Job created: id={job_res.job_id}, status={job_res.status}, edges={job_res.candidate_edges_count}")
assert job_res.status == "COMPLETED"
assert job_res.candidate_edges_count == 38250

job_get = get_matching_job(job_res.job_id, db)
assert job_get.job_id == job_res.job_id

ann_req = ReviewAnnotationCreate(
    candidate_pair_id="MODIS_M101__VIIRS_V202",
    modis_row_id="MODIS_M101",
    viirs_row_id="VIIRS_V202",
    adjudication="MATCH",
    notes="Test annotation for agricultural fire candidate pair",
    reviewer="Expert_Kartik",
)
ann_res = create_review_annotation(ann_req, db)
print(f"Annotation created: id={ann_res.id}, adjudication={ann_res.adjudication}")
assert ann_res.adjudication == "MATCH"

ann_list = list_review_annotations(db)
assert len(ann_list) >= 1
db.close()

print("\n========================================================")
print(" ALL 8 FOUNDATION & DATA ENDPOINTS TESTED SUCCESSFULLY! ")
print("========================================================")
