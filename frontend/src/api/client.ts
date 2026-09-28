import type { ApiErrorBody } from "./types";

export function cleanApiBaseUrl(raw?: string): string {
  if (!raw) return "/api/v1";
  let cleaned = raw.trim();
  const markdownMatch = cleaned.match(/\((https?:\/\/[^)]+)\)/);
  if (markdownMatch) {
    cleaned = markdownMatch[1];
  }
  return cleaned.replace(/[\)\s/]+$/, "");
}

const rawBase =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.MODE === "test" ? "/api/v1" : "https://kurmesh-api.onrender.com/api/v1");

export const API_BASE_URL = cleanApiBaseUrl(rawBase);
export const apiBaseUrl = API_BASE_URL;
export const ACCESS_TOKEN_STORAGE_KEY = "kurmesh.accessToken";

export function buildApiUrl(path: string): string {
  const normalizedPath = `/${path.replace(/^\/+/, "")}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code?: string, message?: string) {
    super(message ?? "The API request failed.");
    this.name = "ApiError";
  }
}

export function hasAccessToken() {
  return Boolean(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY));
}

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => undefined) as T | ApiErrorBody | undefined;
  if (!response.ok) {
    const error = payload as ApiErrorBody | undefined;
    throw new ApiError(response.status, error?.error?.code, error?.error?.message ?? response.statusText);
  }
  if (payload === undefined) throw new ApiError(response.status, "INVALID_RESPONSE", "The API returned an empty response.");
  return payload as T;
}

export async function apiGet<T>(path: string, options: { signal?: AbortSignal; authenticated?: boolean } = {}): Promise<T> {
  const token = options.authenticated ? window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY) : null;
  const response = await fetch(buildApiUrl(path), {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    signal: options.signal,
  });
  return parseResponse<T>(response);
}

export async function apiPost<T>(path: string, body: unknown, options: { signal?: AbortSignal; authenticated?: boolean } = {}): Promise<T> {
  const token = options.authenticated ? window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY) : null;
  const response = await fetch(buildApiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
    signal: options.signal,
  });
  return parseResponse<T>(response);
}

export async function apiPatch<T>(path: string, body: unknown, options: { signal?: AbortSignal; authenticated?: boolean } = {}): Promise<T> {
  const token = options.authenticated ? window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY) : null;
  const response = await fetch(buildApiUrl(path), {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
    signal: options.signal,
  });
  return parseResponse<T>(response);
}
