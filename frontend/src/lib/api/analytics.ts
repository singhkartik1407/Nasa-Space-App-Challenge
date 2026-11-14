import type {
  FrpAnalyticsResponse,
  RelationshipAnalyticsResponse,
  SensorAnalyticsResponse,
} from "./types";
import { API_ENDPOINTS, apiGet } from "./client";

export async function getFrpAnalytics(
  startDate: string = "2024-03-01",
  endDate: string = "2024-03-31"
): Promise<FrpAnalyticsResponse> {
  return apiGet<FrpAnalyticsResponse>(API_ENDPOINTS.frp, {
    start_date: startDate,
    end_date: endDate,
  });
}

export async function getSensorAnalytics(): Promise<SensorAnalyticsResponse> {
  return apiGet<SensorAnalyticsResponse>(API_ENDPOINTS.sensors);
}

export async function getRelationshipAnalytics(
  period: string = "2024-03"
): Promise<RelationshipAnalyticsResponse> {
  return apiGet<RelationshipAnalyticsResponse>(API_ENDPOINTS.relationships, {
    period,
  });
}
