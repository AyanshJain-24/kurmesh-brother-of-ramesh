import { ApiError, apiGet } from "./client";
import type { ApiHealth } from "./types";
export async function getHealth(signal?: AbortSignal) {
  const health = await apiGet<ApiHealth>("/health/live", { signal });
  if (health.status !== "LIVE" || health.service !== "kurmesh-api") throw new ApiError(200, "INVALID_RESPONSE", "The backend health response was not recognized.");
  return health;
}
