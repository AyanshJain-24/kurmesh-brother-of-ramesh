import { apiGet } from "./client";
import type { PaginatedResponse, Prediction } from "./types";
export const getPredictions = (signal?: AbortSignal) => apiGet<PaginatedResponse<Prediction>>("/predictions", { signal, authenticated: true });
