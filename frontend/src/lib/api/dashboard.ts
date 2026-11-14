import type { BackendOverviewResponse, DashboardFilters, DashboardSummary } from "./types";
import { API_ENDPOINTS, apiGet } from "./client";
import { mockDashboardSummary } from "../../mocks/dashboard";

export async function getDashboardSummary(
  filters?: Partial<DashboardFilters>,
  profile: string = "A"
): Promise<DashboardSummary> {
  const isMock = import.meta.env.VITE_USE_MOCK_DATA === "true";

  if (isMock) {
    return mockDashboardSummary;
  }

  const startDate = filters?.start_date || "2024-03-01";
  const endDate = filters?.end_date || "2024-03-31";

  const res = await apiGet<BackendOverviewResponse>(API_ENDPOINTS.overview, {
    start_date: startDate,
    end_date: endDate,
    profile: profile || "A",
  });

  return {
    comparison_period: {
      start_date: res.query_period.start_date,
      end_date: res.query_period.end_date,
    },
    modis_detection_records: res.detections.modis_detection_count,
    viirs_detection_records: res.detections.viirs_detection_count,
    candidate_match_pairs: res.matching.available ? res.matching.candidate_edge_count : null,
    modis_records_with_candidates: res.matching.available ? res.matching.modis_with_candidates : null,
    viirs_records_with_candidates: res.matching.available ? res.matching.viirs_with_candidates : null,
    ambiguous_candidate_relationships: res.matching.available
      ? Math.max(0, res.matching.candidate_edge_count - res.matching.modis_with_candidates)
      : null,
    modis_only_records: res.matching.available ? res.matching.modis_without_candidates : null,
    viirs_only_records: res.matching.available ? res.matching.viirs_without_candidates : null,
    frp_summary: {
      modis: res.frp_mw.modis,
      viirs: res.frp_mw.viirs,
    },
    matching_available: res.matching.available,
    profile: res.profile,
    data_status: "available",
  };
}
