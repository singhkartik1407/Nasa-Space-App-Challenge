const DEFAULT_API_BASE = "http://127.0.0.1:8000/api/v1";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE
).replace(/\/$/, "");

// Server root for /health and /ready
export const SERVER_ROOT_URL = API_BASE_URL.replace(/\/api\/v1\/?$/, "");

export class ApiError extends Error {
  public status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiGet<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined>
): Promise<T> {
  const isRootEndpoint = path.startsWith("/health") || path.startsWith("/ready");
  const baseUrl = isRootEndpoint ? SERVER_ROOT_URL : API_BASE_URL;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${baseUrl}${normalizedPath}`);

  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
  }

  const response = await fetch(url.toString(), {
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    let errorDetail = response.statusText;
    try {
      const errJson = await response.json();
      if (errJson?.detail) {
        errorDetail = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // Ignore JSON parse error on non-JSON response
    }
    throw new ApiError(
      `API request failed (${response.status}): ${errorDetail}`,
      response.status
    );
  }

  return response.json() as Promise<T>;
}

export const API_ENDPOINTS = {
  health: "/health",
  ready: "/ready",
  metadata: "/metadata",
  overview: "/overview",
  detections: "/detections",
  detection: (rowId: string) => `/detections/${encodeURIComponent(rowId)}`,
  mapAggregate: "/map/aggregate",
  candidates: "/candidates",
  candidate: (candidateId: string) => `/candidates/${encodeURIComponent(candidateId)}`,
  activity: "/analytics/activity",
  frp: "/analytics/frp",
  sensors: "/analytics/sensors",
  relationships: "/analytics/relationships",
  matchingJobs: "/matching/jobs",
  matchingJob: (jobId: string) => `/matching/jobs/${encodeURIComponent(jobId)}`,
  reviewAnnotations: "/review/annotations",
};
