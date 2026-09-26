import { apiGet } from "./client";
import type { MissionAlert, PaginatedResponse } from "./types";
export const getMissionAlerts = (missionId: string, signal?: AbortSignal) => apiGet<PaginatedResponse<MissionAlert>>(`/missions/${missionId}/alerts`, { signal, authenticated: true });
