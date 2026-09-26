import { apiGet, apiPatch, apiPost } from "./client";
import type { Coordinate, Mission, PaginatedResponse } from "./types";
export const getMissions = (signal?: AbortSignal) => apiGet<PaginatedResponse<Mission>>("/missions", { signal, authenticated: true });

export interface MissionCreatePayload {
  name: string;
  vessel_id: string;
  departure_at: string;
  origin: Coordinate;
  destination: Coordinate;
}

export const createMission = (payload: MissionCreatePayload) => apiPost<Mission>("/missions", payload, { authenticated: true });
export const updateMissionCoordinates = (missionId: string, origin: Coordinate, destination: Coordinate) => apiPatch<Mission>(`/missions/${missionId}`, { origin, destination }, { authenticated: true });
