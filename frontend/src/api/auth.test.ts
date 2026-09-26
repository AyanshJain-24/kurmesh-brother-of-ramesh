import { afterEach, describe, expect, it, vi } from "vitest";
import { ACCESS_TOKEN_STORAGE_KEY } from "./client";
import { getCurrentUser, login, logout } from "./auth";

function response(payload: unknown, status = 200) { return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } }); }

afterEach(() => { localStorage.clear(); vi.unstubAllGlobals(); });

describe("authentication API", () => {
  it("stores the backend access token after a successful login", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(response({ access_token: "real-response-token", token_type: "Bearer", user: { id: "u1", email: "operator@example.test", full_name: "Operator", is_active: true, roles: ["user"] } })));
    vi.stubGlobal("fetch", fetchMock);
    await login("operator@example.test", "correct-password");
    expect(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe("real-response-token");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/auth/login", expect.objectContaining({ method: "POST", body: JSON.stringify({ email: "operator@example.test", password: "correct-password" }) }));
  });

  it("uses the stored bearer token for the current-user request and removes it on logout", async () => {
    localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "stored-token");
    const fetchMock = vi.fn(() => Promise.resolve(response({ id: "u1", email: "operator@example.test", full_name: "Operator", is_active: true, roles: ["user"] })));
    vi.stubGlobal("fetch", fetchMock);
    await getCurrentUser();
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/auth/me", expect.objectContaining({ headers: { Authorization: "Bearer stored-token" } }));
    logout();
    expect(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull();
  });
});
