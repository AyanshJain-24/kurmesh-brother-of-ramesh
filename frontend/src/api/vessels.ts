import { apiGet, apiPost } from "./client";
import type { PaginatedResponse, Vessel } from "./types";

export interface VesselCreatePayload {
  name: string;
  vessel_type: string;
  imo_number?: string;
  specifications: Record<string, unknown>;
}

export const getVessels = (signal?: AbortSignal) => apiGet<PaginatedResponse<Vessel>>("/vessels", { signal, authenticated: true });
export const createVessel = (payload: VesselCreatePayload) => apiPost<Vessel>("/vessels", payload, { authenticated: true });
