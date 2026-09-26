import { ACCESS_TOKEN_STORAGE_KEY, apiGet, apiPost } from "./client";

export interface AuthenticatedUser {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: string[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthenticatedUser;
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const response = await apiPost<LoginResponse>("/auth/login", { email, password });
  if (!response.access_token || response.token_type.toLowerCase() !== "bearer") {
    throw new Error("The API returned an invalid authentication response.");
  }
  window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, response.access_token);
  return response;
}

export function getCurrentUser(signal?: AbortSignal) {
  return apiGet<AuthenticatedUser>("/auth/me", { authenticated: true, signal });
}

export function logout() {
  window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
}
