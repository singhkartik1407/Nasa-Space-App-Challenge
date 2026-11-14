import { API_ENDPOINTS, apiGet } from "./client";

export interface MapDetectionProperties {
  row_id: string;
  sensor: "MODIS" | "VIIRS";
  satellite: string;
  platform: "TERRA" | "AQUA" | "SNPP" | string;
  acquisition_datetime: string;
  confidence: number | string | null;
  frp: number | null;
  daynight: "D" | "N" | null;
  scan_km?: number | null;
  track_km?: number | null;
}

export interface MapDetectionFeature {
  type: "Feature";
  geometry: {
    type: "Point";
    coordinates: [number, number]; // [longitude, latitude]
  };
  properties: MapDetectionProperties;
}

export interface MapDetectionResponse {
  type: "FeatureCollection";
  features: MapDetectionFeature[];
  meta: {
    returned_features: number;
    total_matching_records: number | null;
    truncated: boolean;
    data_status: "mock" | "available" | "unavailable";
  };
}

interface RawDetectionItem {
  row_id: string;
  sensor: "MODIS" | "VIIRS";
  satellite: string;
  latitude: number;
  longitude: number;
  acq_datetime_utc: string;
  scan_km?: number | null;
  track_km?: number | null;
  pixel_area_km2?: number | null;
  frp_mw?: number | null;
  confidence_raw?: string | null;
  daynight?: "D" | "N" | null;
  version?: string | null;
}

interface RawDetectionListResponse {
  items: RawDetectionItem[];
  pagination: {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
}

export interface MapQueryOptions {
  bbox?: string; // "minLon,minLat,maxLon,maxLat"
  minLat?: number;
  maxLat?: number;
  minLon?: number;
  maxLon?: number;
  startDate?: string;
  endDate?: string;
  sensor?: string; // "ALL" | "MODIS" | "VIIRS"
  daynight?: string;
  limit?: number;
}

export async function getMapDetections(options?: MapQueryOptions): Promise<MapDetectionResponse> {
  const isMock = import.meta.env.VITE_USE_MOCK_DATA === "true";

  if (isMock) {
    return {
      type: "FeatureCollection",
      features: [],
      meta: {
        returned_features: 0,
        total_matching_records: null,
        truncated: false,
        data_status: "unavailable",
      },
    };
  }

  const params: Record<string, string | number | undefined> = {};

  if (options?.bbox) {
    const parts = options.bbox.split(",").map(Number);
    if (parts.length === 4 && parts.every((n) => !isNaN(n))) {
      params.min_lon = parts[0];
      params.min_lat = parts[1];
      params.max_lon = parts[2];
      params.max_lat = parts[3];
    }
  } else {
    if (options?.minLat != null) params.min_lat = options.minLat;
    if (options?.maxLat != null) params.max_lat = options.maxLat;
    if (options?.minLon != null) params.min_lon = options.minLon;
    if (options?.maxLon != null) params.max_lon = options.maxLon;
  }

  params.start_date = options?.startDate || "2024-03-01";
  params.end_date = options?.endDate || "2024-03-05";
  params.sensor = options?.sensor && options.sensor !== "BOTH" ? options.sensor : "ALL";
  if (options?.daynight && options.daynight !== "ALL") params.daynight = options.daynight;
  params.page_size = Math.min(500, options?.limit || 250);

  const res = await apiGet<RawDetectionListResponse>(API_ENDPOINTS.detections, params);

  const features: MapDetectionFeature[] = (res.items || []).map((item) => ({
    type: "Feature",
    geometry: {
      type: "Point",
      coordinates: [item.longitude, item.latitude],
    },
    properties: {
      row_id: item.row_id,
      sensor: item.sensor,
      satellite: item.satellite,
      platform: (item.satellite || "").toUpperCase(),
      acquisition_datetime: item.acq_datetime_utc,
      confidence: item.confidence_raw ?? null,
      frp: item.frp_mw != null ? Math.round(item.frp_mw * 10) / 10 : null,
      daynight: item.daynight ?? null,
      scan_km: item.scan_km,
      track_km: item.track_km,
    },
  }));

  return {
    type: "FeatureCollection",
    features,
    meta: {
      returned_features: features.length,
      total_matching_records: res.pagination?.total_items ?? features.length,
      truncated: (res.pagination?.total_items ?? 0) > features.length,
      data_status: "available",
    },
  };
}
