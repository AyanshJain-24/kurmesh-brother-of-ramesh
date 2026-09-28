export type AvailabilityStatus = "LIVE" | "STALE" | "DEGRADED" | "UNAVAILABLE" | "ERROR";

export interface ApiErrorBody {
  error?: { code?: string; message?: string };
}

export interface ApiHealth {
  status: "LIVE";
  service: "kurmesh-api";
}

export interface PaginatedResponse<T> {
  items: T[];
  page?: number;
  page_size?: number;
  total?: number;
  limit?: number;
  offset?: number;
}

export interface Mission {
  id: string;
  name: string;
  state: string;
  vessel_id: string | null;
  departure_at: string | null;
  origin?: Coordinate | null;
  destination?: Coordinate | null;
}

export interface Coordinate {
  longitude: number;
  latitude: number;
}

export interface Vessel {
  id: string;
  name: string;
  vessel_type: string;
  imo_number: string | null;
  specifications: Record<string, unknown>;
}

export interface EnvironmentObservation {
  id: string;
  source_id: string;
  observation_type: string;
  status: AvailabilityStatus;
  value: Record<string, unknown> | null;
  units: string;
  quality: string | null;
  resolution: string | null;
  retrieved_at: string;
  valid_from: string | null;
  valid_to: string | null;
  location: { longitude: number; latitude: number } | null;
}

export interface EnvironmentSource {
  id: string;
  provider: string;
  source: string;
  url: string | null;
  metadata: Record<string, unknown>;
}

export interface Prediction {
  id: string;
  status: string;
  reason: string | null;
  output: Record<string, unknown> | null;
}

export interface RouteCandidate {
  id: string;
  mission_id: string;
  prediction_id: string | null;
  version: number;
  status: string;
  risk_data_status?: string | null;
  geometry: { type: "LineString"; coordinates: [number, number][] } | null;
  distance_nm: number | null;
  estimated_duration_hours: number | null;
  risk_score: number | null;
  risk_components: Record<string, unknown>;
  environmental_snapshot: Record<string, unknown>;
  algorithm_version: string;
  metadata: Record<string, unknown>;
}

export interface Route {
  id: string;
  route_candidate_id: string;
  status: string;
  geometry: { type: "LineString"; coordinates: [number, number][] } | null;
  metadata: Record<string, unknown>;
}

export interface RouteCandidateGenerationResponse {
  mission_id: string;
  candidate_count: number;
  candidates: RouteCandidate[];
  algorithm_version: string;
  environment_status: string[];
  warnings: string[];
}

export interface RouteReview {
  id: string;
  route_id: string;
  decision: "APPROVED" | "REJECTED" | "CHANGES_REQUESTED";
  comments: string | null;
}

export interface MissionAlert {
  id: string;
  mission_id: string;
  severity: "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  category: string;
  title: string;
  message: string;
  status: string;
  acknowledged_at: string | null;
}
