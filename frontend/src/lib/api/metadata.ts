import type { MetadataResponse, SystemReadiness } from "./types";
import { API_ENDPOINTS, apiGet } from "./client";

export async function getMetadata(): Promise<MetadataResponse> {
  return apiGet<MetadataResponse>(API_ENDPOINTS.metadata);
}

export async function getSystemReadiness(): Promise<SystemReadiness> {
  return apiGet<SystemReadiness>(API_ENDPOINTS.ready);
}

export async function getHealth(): Promise<{ status: string; app_name: string; app_version: string }> {
  return apiGet<{ status: string; app_name: string; app_version: string }>(API_ENDPOINTS.health);
}
