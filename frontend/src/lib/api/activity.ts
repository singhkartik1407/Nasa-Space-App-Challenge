import type { BackendActivityResponse, DashboardFilters, MonthlyActivity } from "./types";
import { API_ENDPOINTS, apiGet } from "./client";

export interface ActivityResponse {
  items: MonthlyActivity[];
  data_status: "mock" | "available" | "unavailable";
  message: string;
}

export async function getMonthlyActivity(
  filters: DashboardFilters
): Promise<ActivityResponse> {
  const isMock = import.meta.env.VITE_USE_MOCK_DATA === "true";

  if (isMock) {
    return {
      items: [],
      data_status: "unavailable",
      message: "Monthly activity data has not been supplied yet.",
    };
  }

  const res = await apiGet<BackendActivityResponse>(API_ENDPOINTS.activity, {
    start_date: filters.start_date,
    end_date: filters.end_date,
    interval: "month",
    timezone: "UTC",
  });

  const items: MonthlyActivity[] = (res.data || []).map((bucket) => {
    const parts = bucket.time_bucket.split("-");
    const year = parseInt(parts[0], 10) || 2024;
    const month = parseInt(parts[1], 10) || 1;
    return {
      year,
      month,
      time_bucket: bucket.time_bucket,
      modis_detections: bucket.modis_count,
      viirs_detections: bucket.viirs_count,
      candidate_match_pairs: null,
      ambiguous_candidate_pairs: null,
    };
  });

  return {
    items,
    data_status: items.length > 0 ? "available" : "unavailable",
    message: items.length > 0 ? "Activity loaded" : "No detections found in this period.",
  };
}

export async function getYearlyMonthlyActivity(year: number): Promise<MonthlyActivity[]> {
  const isMock = import.meta.env.VITE_USE_MOCK_DATA === "true";
  if (isMock) return [];

  const res = await apiGet<BackendActivityResponse>(API_ENDPOINTS.activity, {
    start_date: `${year}-01-01`,
    end_date: `${year}-12-31`,
    interval: "month",
    timezone: "UTC",
  });

  return (res.data || []).map((b) => {
    const parts = b.time_bucket.split("-");
    return {
      year: parseInt(parts[0], 10) || year,
      month: parseInt(parts[1], 10) || 1,
      time_bucket: b.time_bucket,
      modis_detections: b.modis_count,
      viirs_detections: b.viirs_count,
      candidate_match_pairs: null,
      ambiguous_candidate_pairs: null,
    };
  });
}
