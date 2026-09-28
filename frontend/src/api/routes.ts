import { apiGet, apiPost } from "./client";
import type { PaginatedResponse, Route, RouteCandidate, RouteCandidateGenerationResponse, RouteReview } from "./types";
export const getRouteCandidates = (missionId: string, signal?: AbortSignal) => apiGet<PaginatedResponse<RouteCandidate>>(`/missions/${missionId}/route-candidates`, { signal, authenticated: true });
export const getRoutes = (signal?: AbortSignal) => apiGet<PaginatedResponse<Route>>("/routes", { signal, authenticated: true });
export const getMissionRoutes = (missionId: string, signal?: AbortSignal) => apiGet<PaginatedResponse<Route>>(`/missions/${missionId}/routes`, { signal, authenticated: true });
export const generateRouteCandidates = (missionId: string) => apiPost<RouteCandidateGenerationResponse>(`/missions/${missionId}/route-candidates/generate`, {}, { authenticated: true });
export const createRoute = (missionId: string, routeCandidateId: string) => apiPost<Route>(`/missions/${missionId}/routes`, { route_candidate_id: routeCandidateId, metadata: {} }, { authenticated: true });
export const createRouteReview = (routeId: string, decision: RouteReview["decision"], comments: string) => apiPost<RouteReview>(`/routes/${routeId}/reviews`, { decision, comments: comments || undefined, metadata: {} }, { authenticated: true });
export const createRouteApproval = (routeId: string, decision: "APPROVED" | "REJECTED", comments: string) => apiPost<{ id: string; route_id: string; decision: "APPROVED" | "REJECTED" }>(`/routes/${routeId}/approvals`, { decision, comments: comments || undefined, metadata: {} }, { authenticated: true });
