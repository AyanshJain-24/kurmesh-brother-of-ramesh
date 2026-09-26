import { apiGet } from "./client";
import type { EnvironmentObservation, EnvironmentSource, PaginatedResponse } from "./types";
export const getEnvironmentObservations = (signal?: AbortSignal) => apiGet<PaginatedResponse<EnvironmentObservation>>("/environment/observations", { signal, authenticated: true });
export const getEnvironmentSources = (signal?: AbortSignal) => apiGet<PaginatedResponse<EnvironmentSource>>("/environment/sources", { signal, authenticated: true });
