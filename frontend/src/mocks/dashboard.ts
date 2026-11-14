import type { DashboardSummary } from "../lib/api/types";

export const mockDashboardSummary: DashboardSummary = {
  comparison_period: {
    start_date: "2012-01-21",
    end_date: "2026-07-14",
  },
  modis_detection_records: 1232096,
  viirs_detection_records: 8725086,
  candidate_match_pairs: null,
  modis_records_with_candidates: null,
  viirs_records_with_candidates: null,
  ambiguous_candidate_relationships: null,
  modis_only_records: null,
  viirs_only_records: null,
  data_status: "mock",
};
