export type SensorFilter = "MODIS" | "VIIRS" | "BOTH";
export type DayNightFilter = "ALL" | "D" | "N";
export type PlatformFilter = "ALL" | "TERRA" | "AQUA" | "SNPP";
export type ProfileFilter = "A" | "B" | "C" | "D" | "E";

export type ActivityMetric =
  | "modis_detections"
  | "viirs_detections"
  | "candidate_match_pairs"
  | "ambiguous_candidate_pairs"
  | "modis_only"
  | "viirs_only";

export interface DashboardFilters {
  start_date: string;
  end_date: string;
  sensor: SensorFilter;
  platform: PlatformFilter;
  daynight: DayNightFilter;
  metric?: ActivityMetric;
  profile?: ProfileFilter;
}

export interface ComparisonPeriod {
  start_date: string;
  end_date: string;
}

export interface SensorFrpStats {
  sensor: string;
  total_frp_mw: number;
  mean_frp_mw: number;
  median_frp_mw: number;
  max_frp_mw: number;
}

export interface DashboardSummary {
  comparison_period: ComparisonPeriod;
  modis_detection_records: number | null;
  viirs_detection_records: number | null;
  candidate_match_pairs: number | null;
  modis_records_with_candidates: number | null;
  viirs_records_with_candidates: number | null;
  ambiguous_candidate_relationships: number | null;
  modis_only_records: number | null;
  viirs_only_records: number | null;
  frp_summary?: {
    modis: SensorFrpStats;
    viirs: SensorFrpStats;
  };
  matching_available?: boolean;
  profile?: {
    id: string;
    name: string;
    label: string;
    role: string;
  };
  data_status: "mock" | "available" | "unavailable";
}

export interface MonthlyActivity {
  year: number;
  month: number;
  time_bucket?: string;
  modis_detections: number | null;
  viirs_detections: number | null;
  candidate_match_pairs: number | null;
  ambiguous_candidate_pairs: number | null;
}

export interface DetectionProperties {
  row_id: string;
  sensor: "MODIS" | "VIIRS";
  satellite: "Terra" | "Aqua" | "Suomi-NPP" | string;
  platform?: "TERRA" | "AQUA" | "SNPP" | string;
  acquisition_datetime: string;
  confidence: number | string | null;
  frp: number | null;
  daynight: "D" | "N" | null;
  scan_km?: number | null;
  track_km?: number | null;
  pixel_area_km2?: number | null;
  latitude: number;
  longitude: number;
}

export interface CandidateMatch {
  candidate_id: string;
  pair_id?: string;
  modis_row_id: string;
  viirs_row_id: string;
  distance_km: number;
  time_diff_minutes: number;
  footprint_radius_sum_km: number;
  modis_datetime_utc: string;
  viirs_datetime_utc: string;
  modis_latitude: number;
  modis_longitude: number;
  viirs_latitude: number;
  viirs_longitude: number;
  modis_satellite: string;
  viirs_satellite: string;
  modis_frp_mw: number | null;
  viirs_frp_mw: number | null;
  modis_confidence_raw: string | null;
  viirs_confidence_raw: string | null;
  modis_version?: string | null;
  viirs_version?: string | null;
  relationship?: string;
}

export interface CandidateListResponse {
  items: CandidateMatch[];
  profile: {
    id: string;
    name: string;
    label: string;
    time_limit_minutes: number;
    additional_buffer_km: number;
    role: string;
  };
  pagination: {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
  source_parquet?: string;
}

export interface BackendOverviewResponse {
  query_period: {
    start_date: string;
    end_date: string;
    timezone: string;
  };
  profile: {
    id: string;
    name: string;
    label: string;
    time_limit_minutes: number;
    additional_buffer_km: number;
    role: string;
  };
  detections: {
    modis_detection_count: number;
    viirs_detection_count: number;
    total_observations: number;
    note: string;
  };
  frp_mw: {
    modis: SensorFrpStats;
    viirs: SensorFrpStats;
    interpretation: string;
  };
  matching: {
    available: boolean;
    candidate_edge_count: number;
    modis_with_candidates: number;
    viirs_with_candidates: number;
    modis_without_candidates: number;
    viirs_without_candidates: number;
    exclusivity_interpretation: string;
    candidate_source_file?: string;
  };
}

export interface BackendActivityBucket {
  time_bucket: string;
  modis_count: number;
  viirs_count: number;
}

export interface BackendActivityResponse {
  interval: string;
  timezone: string;
  start_date: string;
  end_date: string;
  data: BackendActivityBucket[];
}

export interface FrpDistribution {
  sensor: string;
  detection_count: number;
  total_frp_mw: number;
  mean_frp_mw: number;
  median_frp_mw: number;
  p25_frp_mw: number;
  p75_frp_mw: number;
  p95_frp_mw: number;
  max_frp_mw: number;
}

export interface FrpAnalyticsResponse {
  period: { start_date: string; end_date: string; timezone: string };
  unit: string;
  modis: FrpDistribution;
  viirs: FrpDistribution;
  note: string;
}

export interface SensorVersionItem {
  version: string;
  count: number;
}

export interface SensorSummaryDetail {
  sensor: string;
  nominal_pixel_resolution_km: number;
  common_period_detections: number;
  version_distribution: SensorVersionItem[];
  satellites: string[];
}

export interface SensorAnalyticsResponse {
  modis: SensorSummaryDetail;
  viirs: SensorSummaryDetail;
}

export interface ProfileSensitivityItem {
  profile: string;
  candidate_edges: number;
  modis_with_candidates: number;
  viirs_with_candidates: number;
  components: number;
  one_to_one_components: number;
  one_to_one_share_pct: number;
  components_over_5km: number;
  components_over_3h: number;
}

export interface RelationshipAnalyticsResponse {
  period: string;
  modis_detections: number;
  viirs_detections: number;
  candidate_superset_edges: number;
  profile_sensitivity: ProfileSensitivityItem[];
  graph_interpretation: string;
}

export interface SystemReadiness {
  ready: boolean;
  status: string;
  modis_parquet_exists: boolean;
  viirs_parquet_exists: boolean;
  modis_total_rows: number;
  viirs_total_rows: number;
  error?: string | null;
}

export interface ProcessedMatchingPeriod {
  period_id: string;
  start_date: string;
  end_date: string;
  modis_detections: number;
  viirs_detections: number;
  candidate_superset_edges: number;
  profile_a_edges: number;
  profile_b_edges: number;
  status: "VALIDATED" | "COMPLETED" | "RUNNING" | "FAILED" | "NOT_PROCESSED" | string;
  is_pilot: boolean;
}

export interface MetadataResponse {
  dataset_window: {
    start_date: string;
    end_date: string;
    canonical_timezone: string;
    display_timezones: string[];
    total_days: number;
  };
  sensors: Array<{
    sensor: string;
    satellites: string[];
    nominal_pixel_resolution_km: number;
    versions: string[];
    frp_unit: string;
  }>;
  threshold_profiles: Array<{
    id: string;
    name: string;
    label: string;
    time_limit_minutes: number;
    additional_buffer_km: number;
    role: string;
    description: string;
    is_default: boolean;
    is_selectable: boolean;
  }>;
  default_profile: string;
  alternative_profile: string;
  audited_pilot_periods: Array<{
    period_id: string;
    start_date: string;
    end_date: string;
    modis_detections: number;
    viirs_detections: number;
    candidate_superset_edges: number;
    profile_a_edges: number;
    profile_b_edges: number;
    modis_version: string;
    viirs_version: string;
  }>;
  processed_matching_periods?: ProcessedMatchingPeriod[];
}

export interface ApiResponse<T> {
  data: T;
  status: "success" | "error";
  message?: string;
}
