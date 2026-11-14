import type { CandidateListResponse, CandidateMatch } from "./types";
import { API_ENDPOINTS, apiGet } from "./client";

export interface CandidateQueryParams {
  profile?: string; // "A" | "B"
  startDate?: string;
  endDate?: string;
  minLat?: number;
  maxLat?: number;
  minLon?: number;
  maxLon?: number;
  minDistanceKm?: number;
  maxDistanceKm?: number;
  page?: number;
  pageSize?: number;
}

export async function getCandidates(
  params?: CandidateQueryParams
): Promise<CandidateListResponse> {
  const isMock = import.meta.env.VITE_USE_MOCK_DATA === "true";

  if (isMock) {
    return {
      items: [],
      profile: {
        id: "A",
        name: "A_1h_0km",
        label: "Profile A (1h limit, 0km buffer)",
        time_limit_minutes: 60,
        additional_buffer_km: 0,
        role: "Provisional MVP Default",
      },
      pagination: {
        page: 1,
        page_size: 50,
        total_items: 0,
        total_pages: 0,
        has_next: false,
        has_prev: false,
      },
    };
  }

  const query: Record<string, string | number | undefined> = {
    profile: params?.profile || "A",
    start_date: params?.startDate || "2024-03-01",
    end_date: params?.endDate || "2024-03-31",
    page: params?.page || 1,
    page_size: params?.pageSize || 50,
  };

  if (params?.minLat != null) query.min_lat = params.minLat;
  if (params?.maxLat != null) query.max_lat = params.maxLat;
  if (params?.minLon != null) query.min_lon = params.minLon;
  if (params?.maxLon != null) query.max_lon = params.maxLon;
  if (params?.minDistanceKm != null) query.min_distance_km = params.minDistanceKm;
  if (params?.maxDistanceKm != null) query.max_distance_km = params.maxDistanceKm;

  return apiGet<CandidateListResponse>(API_ENDPOINTS.candidates, query);
}

export async function getCandidateDetail(candidateId: string): Promise<CandidateMatch> {
  return apiGet<CandidateMatch>(API_ENDPOINTS.candidate(candidateId));
}
